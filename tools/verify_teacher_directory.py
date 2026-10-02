"""Reconcile every imported row, photo, new page, and additive existing edit."""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlparse
from lxml import etree, html
from build_teacher_directory import ROOT, BASE, DATE, NAV, START, END, EXCLUDED, catalog, digest, enc, branch_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    report = args.report_dir
    baseline = json.loads((report/'baseline.json').read_text(encoding='utf-8'))
    changed = set(json.loads((report/'changed-public-files.json').read_text(encoding='utf-8')))
    manifest = json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8'))
    descriptions = json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8'))['pages']
    linked = json.loads((report/'linked-pages.json').read_text(encoding='utf-8'))
    source, centers, branches, excluded = catalog()
    errors = []
    def check(condition, detail):
        if not condition:
            errors.append(detail)
    check(sum(len(b['records']) for b in branches)+len(excluded)==len(source['records']), 'source row reconciliation')
    check(len(source['records'])==1002, 'source count')
    check(len({r['sourceRow'] for b in branches for r in b['records']})==962, 'source record IDs; do not merge masked names')
    check(not set(b['name'] for b in branches).intersection(EXCLUDED), 'excluded brands')
    navigation = len(baseline['files'])
    linked_by_file = {r['file']:r for r in linked}
    # Stripping only the three authorized literal additions must reconstruct
    # every original HTML byte, including old metadata, forms, images, copy.
    def verify_file(entry):
        name, expected = entry
        path = ROOT/name
        check(path.exists(), 'missing manifest file: '+name)
        if path.exists():
            raw = path.read_bytes()
            check(digest(raw)==expected, 'manifest bytes: '+name)
            if name in baseline['files']:
                text = raw.decode('utf-8')
                check(text.count('data-teacher-navigation')==1,name+': navigation count')
                preserved = text.replace(NAV,'').replace('header.css?v=20261002-teachers','header.css?v=20260920-nav1')
                blocks = re.findall(re.escape(START)+'(.*?)'+re.escape(END),preserved,flags=re.S)
                row = linked_by_file.get(name)
                if row:
                    check(len(blocks)==1,name+': link section count')
                    if blocks:
                        check(html.fromstring(blocks[0]).xpath('.//a/@href')==row['urls'],name+': branch link mapping')
                else:
                    check(not blocks,name+': unexpected branch link')
                preserved = re.sub(re.escape(START)+'.*?'+re.escape(END),'',preserved,flags=re.S)
                check(digest(preserved.encode('utf-8'))==baseline['files'][name],name+': unrelated original content changed')
            if name in manifest.get('textSha256',{}):
                check(digest(raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n').encode('utf-8'))==manifest['textSha256'][name], 'manifest text bytes: '+name)
    with ThreadPoolExecutor(max_workers=16) as pool:
        for index, _ in enumerate(pool.map(verify_file,manifest['files'].items()),1):
            if index % 5000==0:
                print(json.dumps({'publicFilesVerified':index,'total':len(manifest['files'])}),flush=True)
    for name, expected in baseline['manifest']['files'].items():
        if name not in changed:
            check(manifest['files'].get(name)==expected, 'unrelated manifest change: '+name)
    new_paths = ['/선생님찾기/']+[b['path'] for b in branches]
    expected_by_path = {b['path']: b for b in branches}
    rows = []
    for path in new_paths:
        name = path.strip('/')+'/index.html'
        document = html.fromstring((ROOT/name).read_bytes())
        canonical = document.xpath('//link[@rel="canonical"]/@href')
        check(canonical==[BASE+enc(path)], name+': canonical')
        check(document.xpath('//meta[@name="robots"]/@content')==['index, follow'], name+': robots')
        check(len(document.xpath('//main'))==1 and len(document.xpath('//h1'))==1, name+': landmarks')
        ids = document.xpath('//@id')
        check(len(ids)==len(set(ids)), name+': IDs')
        expected = descriptions[path.rstrip('/')]['description']
        check(len(expected)<=80 and expected.endswith('.'), name+': description length')
        check(document.xpath('//meta[@name="description"]/@content')==[expected], name+': description')
        check(document.xpath('//meta[@property="og:description"]/@content')==[expected], name+': OG')
        check(document.xpath('//meta[@name="twitter:description"]/@content')==[expected], name+': Twitter')
        graph = json.loads(document.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
        check(graph[0]['description']==expected and graph[0]['dateModified']==DATE, name+': schema')
        check(graph[0]['@type']=='CollectionPage', name+': role')
        check(graph[2]['@type']=='ItemList', name+': list')
        check(not any(s.get('@type')=='Person' for s in graph), name+': generic portrait is not verified person image')
        check(len(document.xpath('//header//a[@data-teacher-navigation and @aria-current="page"]'))==1, name+': active navigation')
        check(len(document.xpath('//script[@data-site="wawa-01"]'))==1, name+': analytics')
        body = document.xpath('//main')[0].text_content()
        check('편집 원칙' not in body and '�' not in body, name+': private/encoding')
        for link in document.xpath('//a[@href]|//img[@src]|//script[@src]|//link[@rel="stylesheet"]'):
            reference = link.get('href') or link.get('src')
            if reference.startswith(('/', '#')):
                parts = urlparse(reference)
                target = ROOT/unquote(parts.path).lstrip('/') if parts.path else ROOT/name
                if target.is_dir():
                    target = target/'index.html'
                check(target.exists(), name+': missing link '+reference)
                if parts.fragment and target.exists() and target.suffix=='.html':
                    linked_document = document if target == ROOT/name else html.fromstring(target.read_bytes())
                    check(bool(linked_document.xpath('//*[@id=$value]',value=unquote(parts.fragment))),name+': missing fragment '+reference)
        if path in expected_by_path:
            branch = expected_by_path[path]
            cards = document.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," td-teacher-card ")]')
            check(len(cards)==len(branch['records']), name+': introduction count')
            photos = [node.xpath('.//img/@src')[0] for node in cards]
            check(len(photos)==len(set(photos)), name+': duplicate branch photo')
            check(len({digest((ROOT/src.lstrip('/')).read_bytes()) for src in photos})==len(photos), name+': duplicate branch photo bytes')
            check(graph[2]['numberOfItems']==len(cards), name+': schema count')
            for card, record, schema in zip(cards, branch['records'], graph[2]['itemListElement']):
                check(card.get('id')==record['anchor'],name+': source record identity')
                check(card.xpath('.//h2')[0].text_content()==record['name']+' 선생님',name+': masked name')
                check(card.xpath('.//*[@class="td-introduction"]')[0].text_content()==record['introduction'],name+': source introduction')
                check([n.text_content() for n in card.xpath('.//*[@class="td-tags"]/span')]==[p.strip() for p in record['approach'].split('/')],name+': approach')
                check(schema['description']==record['introduction'],name+': schema introduction')
                image = card.xpath('.//img')[0]
                check(image.get('alt')=='선생님 소개용 공용 이미지' and image.get('width') and image.get('height'),name+': image honesty/dimensions')
            if branch['center']:
                check(branch['center']['address'] in body,name+': branch address')
                check(bool(document.xpath('//a[@href=$value]', value=enc(branch_url(branch)))),name+': branch backlink')
            else:
                check('이 지점의 주소와 수강 정보는 아직 안내하지 않습니다.' in body,name+': unverified location')
            rows.append({'branch':branch['name'],'introductions':len(cards),'uniquePhotos':len(set(photos))})
        else:
            check(len(document.xpath('//*[@data-branch-card]'))==194,name+': hub branch cards')
            check(graph[2]['numberOfItems']==194,name+': hub schema count')
    for row in linked:
        for url in row['urls']:
            check((ROOT/unquote(url).strip('/')/'index.html').exists(),row['file']+': target exists')
    ns = {'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    old_sitemap = etree.fromstring(baseline['sitemap'].encode('utf-8'))
    old_dates = {unquote(e.findtext('s:loc',namespaces=ns)):e.findtext('s:lastmod',namespaces=ns) for e in old_sitemap.findall('s:url',ns)}
    sitemap = etree.parse(str(ROOT/'sitemap.xml'))
    items = sitemap.findall('s:url',ns)
    locations = [unquote(e.findtext('s:loc',namespaces=ns)) for e in items]
    check(len(locations)==len(set(locations))==manifest['sitemapPages']==21746,'sitemap count')
    check(set(locations)-set(old_dates)=={BASE+p for p in new_paths},'sitemap exact additions')
    for e in items:
        location = unquote(e.findtext('s:loc',namespaces=ns))
        check(e.findtext('s:lastmod',namespaces=ns)==old_dates.get(location,DATE),'sitemap existing date changed: '+location)
    for key, value in baseline['descriptions']['pages'].items():
        check(descriptions[key]==value,'existing description changed: '+key)
    check(not re.search(r'\b(fetch|XMLHttpRequest|sendBeacon|localStorage|sessionStorage)\b',(ROOT/'assets/teacher-directory.js').read_text(encoding='utf-8')),'search transmission/storage')
    summary = {'publicBranches':len(branches),'publicIntroductions':sum(len(b['records']) for b in branches),'sourceRows':len(source['records']),'excludedRows':len(excluded),'navigationPages':navigation,'linkedPages':len(linked),'newPages':len(new_paths),'photoFiles':len(source['photos']),'sitemapURLs':len(locations),'publicFiles':len(manifest['files']),'preservedExistingHTML':len(baseline['files']),'errors':errors}
    (report/'validation.json').write_text(json.dumps({'summary':summary,'branches':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__=='__main__':
    main()
