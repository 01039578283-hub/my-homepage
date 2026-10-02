"""Whole-scope release/content checks for the learning-guide change."""
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse
from lxml import etree, html
from learning_guide_content import BASE, DATE, GUIDES, SOURCES

ROOT = Path(__file__).resolve().parents[1]


def old_json(name):
    return json.loads(subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-dir', type=Path, required=True)
    parser.add_argument('--teacher-report', type=Path)
    args = parser.parse_args()
    errors, rows = [], []
    baseline = json.loads((args.report_dir / 'baseline.json').read_text(encoding='utf-8'))
    before = {r['file']: r for r in baseline}
    files = json.loads((args.report_dir / 'changed-html.json').read_text(encoding='utf-8'))
    public_files = json.loads((args.report_dir / 'changed-public-files.json').read_text(encoding='utf-8'))
    teacher_public = json.loads((args.teacher_report / 'changed-public-files.json').read_text(encoding='utf-8')) if args.teacher_report else []
    teacher_catalog = json.loads((args.teacher_report / 'catalog.json').read_text(encoding='utf-8')) if args.teacher_report else []
    teacher_paths = {'/선생님찾기'} | {b['path'].rstrip('/') for b in teacher_catalog} if args.teacher_report else set()
    catalog = {g['path']: g for g in json.loads((args.report_dir / 'guide-catalog.json').read_text(encoding='utf-8'))}
    manifest = json.loads((ROOT / 'release-public-manifest.json').read_text(encoding='utf-8'))
    descriptions = json.loads((ROOT / 'seo-descriptions.json').read_text(encoding='utf-8'))['pages']
    documents = {name: html.fromstring((ROOT / name).read_bytes()) for name in files}

    def check(condition, message):
        if not condition:
            errors.append(message)

    for name, document in documents.items():
        path = name.removesuffix('/index.html')
        canonical = document.xpath('//link[@rel="canonical"]/@href')
        check(len(canonical) == 1 and unquote(canonical[0]) == BASE + '/' + path + '/', name + ': canonical')
        check(document.xpath('//meta[@name="robots"]/@content') == ['index, follow'], name + ': robots')
        check(len(document.xpath('//main')) == 1 and len(document.xpath('//h1')) == 1, name + ': main/h1')
        ids = document.xpath('//@id')
        check(len(ids) == len(set(ids)), name + ': duplicate IDs')
        expected = descriptions['/' + path]['description']
        check(len(expected) <= 80 and expected.endswith('.'), name + ': description length/sentence')
        check(document.xpath('//meta[@name="description"]/@content') == [expected], name + ': description')
        check(document.xpath('//meta[@property="og:description"]/@content') == [expected], name + ': OG description')
        check(document.xpath('//meta[@name="twitter:description"]/@content') == [expected], name + ': Twitter description')
        graph = []
        for script in document.xpath('//script[@type="application/ld+json"]'):
            value = json.loads(script.text)
            graph.extend(value.get('@graph', [value]))
        principal = [s for s in graph if s.get('@type') in ('Article', 'CollectionPage')]
        check(len(principal) == 1 and principal[0]['description'] == expected, name + ': schema description')
        check(principal[0].get('dateModified') == DATE, name + ': modification date')
        body = document.xpath('//main')[0].text_content()
        check(not re.search(r'편집\s*원칙|AI SUMMARY|검색 의도|240여|16만 명|장기 기억으로 넘어', body), name + ': obsolete/private copy')
        check('�' not in body, name + ': encoding')
        tracker = document.xpath('//script[@data-site="wawa-01"]')
        check(len(tracker) == 1 and tracker[0].get('src') == 'https://wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js', name + ': analytics')
        links_checked = 0
        for element in document.xpath('//a[@href]|//img[@src]|//link[@rel="stylesheet"]|//script[@src]'):
            reference = element.get('href') or element.get('src')
            if not reference or not reference.startswith(('/', '#')):
                continue
            target = urlparse(reference)
            if target.path:
                destination = ROOT / unquote(target.path).lstrip('/')
                destination = destination / 'index.html' if destination.is_dir() else destination
                check(destination.exists(), name + ': missing internal asset/link ' + reference)
                if target.fragment and destination.suffix == '.html' and destination.exists():
                    linked = documents.get(destination.relative_to(ROOT).as_posix())
                    if linked is None:
                        linked = html.fromstring(destination.read_bytes())
                    check(target.fragment in linked.xpath('//@id'), name + ': missing cross-page anchor ' + reference)
            elif target.fragment:
                check(target.fragment in ids, name + ': missing anchor ' + reference)
            links_checked += 1
        images = [dict(i.attrib) for i in document.xpath('//main//img')]
        if name in before:
            normalize_images = lambda items: [dict(item, src=unquote(item['src'])) for item in items]
            check(normalize_images(images) == normalize_images(before[name]['images']), name + ': original image URL/attributes/order')
            check(unquote(canonical[0]) == unquote(BASE + '/' + path + '/'), name + ': existing URL')
        if path in catalog:
            guide = catalog[path]
            visible = [(' '.join(n.xpath('./summary')[0].text_content().split()), ' '.join(' '.join(p.text_content().split()) for p in n.xpath('./p'))) for n in document.xpath('//*[@id="lg-faq"]/details')]
            schema_faq = next(s for s in graph if s.get('@type') == 'FAQPage')['mainEntity']
            check(visible == [(q['name'], q['acceptedAnswer']['text']) for q in schema_faq], name + ': visible/schema FAQ')
            check(len(visible) >= 2, name + ': insufficient FAQ')
            check(len(document.xpath('//*[@data-record-form]//textarea')) == 4, name + ': record fields')
            for textarea in document.xpath('//textarea'):
                check(len(document.xpath('//label[@for="%s"]' % textarea.get('id'))) == 1, name + ': input label')
            blank_link = document.xpath('//a[@download]/@href')[0]
            raw = (ROOT / unquote(blank_link).lstrip('/')).read_bytes()
            check(raw.startswith(b'\xef\xbb\xbf') and b'\r\n' in raw and b'\n' not in raw.replace(b'\r\n', b''), name + ': record BOM/CRLF')
            blank = raw.decode('utf-8-sig')
            check(guide['title'] in blank and canonical[0] in blank and all(f.split(':', 1)[0] in blank for f in guide['fields']), name + ': correct record contents')
            check(len(document.xpath('//*[@id="lg-sources"]//li')) == len(guide['sources']), name + ': source count')
            check(set(document.xpath('//*[@id="lg-sources"]//a/@href')) == {SOURCES[s]['url'] for s in guide['sources']}, name + ': source links')
            method_size = len(document.xpath('//*[@class="lg-knowledge"]')[0].text_content())
            check(method_size >= 280 and len(body) >= 2000, name + ': insufficient explanation')
            rows.append({'path': path, 'characters': len(body), 'methodCharacters': method_size, 'faq': len(visible), 'images': len(images), 'internalLinksChecked': links_checked, 'new': guide['new']})
    hub = documents['guide/index.html']
    directory_cards = hub.xpath('//*[@data-guide-directory]//*[@data-guide-card]')
    check(len(directory_cards) == 65, 'hub directory count')
    check({unquote(c.xpath('.//h3/a/@href')[0]).strip('/') for c in directory_cards} == set(catalog), 'hub all guide URLs')
    check(len(hub.xpath('//*[@data-category-filter]')) == 7, 'hub category filters')
    check(len(documents['교육정보/index.html'].xpath('//*[contains(@class,"lg-reading-path")]')) == 6, 'reading paths')
    for name in public_files:
        raw = (ROOT / name).read_bytes()
        check(hashlib.sha256(raw).hexdigest() == manifest['files'].get(name), 'manifest raw hash: ' + name)
        lf = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
        check(hashlib.sha256(lf).hexdigest() == manifest.get('textSha256', {}).get(name), 'manifest LF hash: ' + name)
    old_manifest = old_json('release-public-manifest.json')
    check(all(manifest['files'].get(k) == v for k, v in old_manifest['files'].items() if k not in set(public_files) | set(teacher_public)), 'manifest changed outside scope')
    old_descriptions = old_json('seo-descriptions.json')['pages']
    scope = {'/' + n.removesuffix('/index.html') for n in files}
    check(all(descriptions.get(k) == v for k, v in old_descriptions.items() if k not in scope | teacher_paths), 'description mapping changed outside scope')
    namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    sitemap = etree.parse(str(ROOT / 'sitemap.xml'))
    sitemap_urls = sitemap.findall('s:url', namespace)
    locations = [unquote(e.findtext('s:loc', namespaces=namespace)) for e in sitemap_urls]
    expected_pages = 21551 + len(teacher_paths)
    check(len(sitemap_urls) == expected_pages and len(set(locations)) == expected_pages, 'sitemap count/duplicates')
    check(manifest['sitemapPages'] == len(sitemap_urls), 'manifest sitemap count')
    old_sitemap = etree.fromstring(subprocess.check_output(['git', 'show', 'HEAD:sitemap.xml'], cwd=ROOT))
    old_dates = {unquote(e.findtext('s:loc', namespaces=namespace)): e.findtext('s:lastmod', namespaces=namespace) for e in old_sitemap.findall('s:url', namespace)}
    for element in sitemap_urls:
        location = unquote(element.findtext('s:loc', namespaces=namespace))
        date = element.findtext('s:lastmod', namespaces=namespace)
        check(date == (DATE if urlparse(location).path.rstrip('/') in scope | teacher_paths else old_dates.get(location)), 'sitemap lastmod: ' + location)
    rss = etree.parse(str(ROOT / 'rss.xml'))
    items = rss.findall('./channel/item')
    rss_paths = [unquote(urlparse(i.findtext('link')).path).strip('/') for i in items]
    check(set(catalog).issubset(rss_paths) and len(set(rss_paths)) == len(rss_paths), 'RSS guide coverage/duplicate links')
    old_rss = etree.fromstring(subprocess.check_output(['git', 'show', 'HEAD:rss.xml'], cwd=ROOT))
    old_publication = {i.findtext('guid'): i.findtext('pubDate') for i in old_rss.findall('./channel/item')}
    for item in items:
        if item.findtext('guid') in old_publication:
            check(item.findtext('pubDate') == old_publication[item.findtext('guid')], 'RSS changed original publication date')
    js = (ROOT / 'assets/learning-guides.js').read_text(encoding='utf-8')
    check(not re.search(r'\b(fetch|XMLHttpRequest|sendBeacon|localStorage|sessionStorage)\b', js), 'record data transmission/storage')
    allowed = set(public_files) | {'seo-descriptions.json', 'release-public-manifest.json', 'release-public-build.mjs', 'tools/learning_guide_content.py', 'tools/build_learning_guides.py', 'tools/verify_learning_guides.py', 'tools/LEARNING_GUIDES.md', 'tools/learning-guides-baseline.zip'}
    if args.teacher_report:
        allowed |= set(teacher_public) | {'tools/build_teacher_directory.py', 'tools/verify_teacher_directory.py', 'tools/teacher-profiles-source.json', 'tools/TEACHER_DIRECTORY.md'}
    status = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], cwd=ROOT).decode('utf-8')
    for row in status.split('\0'):
        if row:
            check(row[3:] in allowed, 'git change outside scope: ' + row[3:])
    summary = {'htmlPages': len(documents), 'articles': len(rows), 'existingArticles': sum(not r['new'] for r in rows), 'newArticles': sum(r['new'] for r in rows), 'recordFiles': 65, 'preservedImages': sum(r['images'] for r in rows), 'references': len(SOURCES), 'faq': sum(r['faq'] for r in rows), 'sitemapURLs': len(sitemap_urls), 'rssItems': len(items), 'minimumArticleCharacters': min(r['characters'] for r in rows), 'minimumMethodCharacters': min(r['methodCharacters'] for r in rows), 'errors': errors}
    (args.report_dir / 'validation.json').write_text(json.dumps({'summary': summary, 'pages': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
