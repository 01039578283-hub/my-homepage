"""Step 8: local release audit and narrowly scoped sitemap/RSS synchronization.

No HTML, original manuscripts, images, routing, Git or remote state is written.
The 742 sitemap dates require the actual Step 6/7 page hashes as evidence.
RSS keeps its existing items, titles, URLs, order and publication dates.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from email.utils import format_datetime, parsedate_to_datetime
from functools import lru_cache
from html import escape, unescape
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

from lxml import html

from branch_learning_routes import ROOT, canonical, paired_routes
from subject_guide_facts import targets as reviewed_targets
from subject_guide_schema import load_targets as other_targets

DOMAIN = 'https://wawa-center.kr'
REVIEW_DATE = '2026-09-20'
AUDIT_ROOT = Path(r'C:\Users\1992k\Desktop\CodexData\audit-output')
REPORT_ROOT = AUDIT_ROOT / 'wawa-center-step8-20260920'
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
CONTENT = '{http://purl.org/rss/1.0/modules/content/}encoded'
ITEM = re.compile(r'<item>.*?</item>', re.S)
URL_BLOCK = re.compile(r'<url>.*?</url>', re.S)
INTERNAL_SNAPSHOTS = {
    'scripts/data/brand-upgrade-20260911/home.html',
    'scripts/data/brand-upgrade-20260911/overview.html',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_hashes(paths) -> dict[str, str]:
    ordered = sorted({Path(p) for p in paths})
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip((str(p) for p in ordered), pool.map(sha, ordered)))


def normalized_url(value: str) -> tuple[str, str, str, str, str]:
    """Korean IRI/percent-encoded equivalence, not a route/redirect guess."""
    url = urlsplit(value)
    if re.search(r'%(?:2f|5c)', url.path, re.I):
        raise ValueError(f'encoded path separator: {value}')
    path = unquote(url.path, errors='strict')
    if '\\' in path or '\0' in path or any(p in ('.', '..') for p in path.split('/')):
        raise ValueError(f'unsafe URL path: {value}')
    return url.scheme.lower(), url.netloc.lower(), path, url.query, unquote(url.fragment)


def file_for_url(value: str, root: Path = ROOT) -> Path:
    scheme, host, path, _, _ = normalized_url(value)
    if scheme != 'https' or host != 'wawa-center.kr' or not path.startswith('/'):
        raise ValueError(f'not a site URL: {value}')
    candidate = root / path.lstrip('/')
    if path.endswith('/'):
        return candidate / 'index.html'
    if candidate.is_file():
        return candidate
    if candidate.suffix:
        return candidate
    if (candidate / 'index.html').is_file():
        return candidate / 'index.html'
    return candidate.with_name(candidate.name + '.html')


def page_url(file: Path, root: Path = ROOT) -> str:
    relative = file.relative_to(root).as_posix()
    return canonical('/' + (relative[:-10] if relative.endswith('index.html') else relative))


def scoped_paths(root: Path = ROOT) -> list[Path]:
    centers = json.loads((root / 'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    records = json.loads((root / 'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']
    by_name = {center['routeName']: center for center in centers}
    expected = {'/지점안내/'}
    expected |= {f'/지점안내/{center["region"]}/' for center in centers}
    expected |= {f'/지점안내/{c["region"]}/{c["routeName"]}/' for c in centers}
    expected |= {record['path'] for record in records}
    hub_manifest = root / 'tools/data/local-subject-hubs/hubs.json'
    hubs = json.loads(hub_manifest.read_text(encoding='utf-8'))['pages'] if hub_manifest.exists() else []
    expected |= {record['path'] for record in hubs}
    actual = {unquote(urlsplit(page_url(p, root)).path) for p in (root / '지점안내').rglob('index.html')}
    if len(centers) != 193 or len(records) != 2226 or len(expected) != 2436 + len(hubs) or expected != actual:
        raise ValueError('branch manifest/file inventory mismatch')
    guides = {paired_routes(by_name[r['center']], r, root)['guide'] for r in records if r['level'] == '고등'}
    if len(guides) != 742:
        raise ValueError('expected 742 high-school guides')
    return sorted(file_for_url(canonical(path), root) for path in expected | guides)


def reviewed_date_evidence() -> dict[str, str]:
    """Do not derive content modification dates from checkout/build mtimes."""
    paths = {r['path'] for r in reviewed_targets()}
    others, _ = other_targets()
    paths |= {r['path'] for r in others}
    evidence = []
    for step in (6, 7):
        file = AUDIT_ROOT / f'wawa-center-step{step}-20260920' / 'changes.json'
        evidence.extend(json.loads(file.read_text(encoding='utf-8')))
    if len(evidence) != 742 or {r['path'] for r in evidence} != paths:
        raise ValueError('missing or duplicate prior review evidence')
    for record in evidence:
        if sha(file_for_url(canonical(record['path']))) != record['afterSha256']:
            raise ValueError(f'page changed after review: {record["path"]}')
    return {path: REVIEW_DATE for path in sorted(paths)}


def refresh_sitemap(raw: str, dates: dict[str, str]) -> tuple[str, list[dict]]:
    """Change only lastmod text, preserving URLs, comments, order and bytes."""
    ET.fromstring(raw)
    seen, changes = Counter(), []

    def replace(match):
        block = match.group()
        loc = re.search(r'<loc>(.*?)</loc>', block, re.S)
        if not loc:
            raise ValueError('missing sitemap loc')
        path = normalized_url(unescape(loc.group(1)))[2]
        if path not in dates:
            return block
        seen[path] += 1
        date.fromisoformat(dates[path])
        old = re.search(r'(<lastmod>)(.*?)(</lastmod>)', block, re.S)
        if not old:
            raise ValueError(f'missing lastmod: {path}')
        if old.group(2) != dates[path]:
            changes.append({'path': path, 'before': old.group(2), 'after': dates[path]})
        return block[:old.start(2)] + dates[path] + block[old.end(2):]

    result = URL_BLOCK.sub(replace, raw)
    if set(seen) != set(dates) or any(n != 1 for n in seen.values()):
        raise ValueError('missing/duplicate reviewed sitemap URLs')
    ET.fromstring(result)
    return result, changes


def feed_body(document, url: str) -> str:
    mains = document.xpath('//main')
    if len(mains) != 1:
        raise ValueError(f'expected one source main: {url}')
    main = copy.deepcopy(mains[0])
    # Remove executable/UI-only controls, not article sections, maps or images.
    for element in list(main.xpath('.//script | .//style | .//form | .//button | .//input | .//select | .//textarea')):
        if element.getparent() is not None:
            element.drop_tree()
    for element in main.iter():
        # Remove indentation-only blank lines from the extracted feed, while
        # preserving inline spaces and preformatted content in the source.
        for field in ('text', 'tail'):
            context = element if field == 'text' else element.getparent()
            value = getattr(element, field)
            if value and '\n' in value and not value.strip() and context is not None and not context.xpath('ancestor-or-self::pre | ancestor-or-self::code'):
                normalized = value.replace('\r\n', '\n').replace('\r', '\n')
                setattr(element, field, re.sub(r'(?m)^[ \t]+$', '', normalized))
        for key in list(element.attrib):
            if key.lower().startswith('on') or key.lower() == 'srcdoc':
                del element.attrib[key]
        for key in ('href', 'src', 'poster'):
            value = element.get(key)
            if value is not None:
                target = urljoin(url, value)
                if urlsplit(target).scheme.lower() not in ('http', 'https', 'tel', 'mailto', 'sms'):
                    del element.attrib[key]
                else:
                    element.set(key, target)
        if element.get('srcset'):
            values = []
            for entry in element.get('srcset').split(','):
                source, *descriptor = entry.strip().split()
                target = urljoin(url, source)
                if urlsplit(target).scheme not in ('http', 'https'):
                    raise ValueError(f'unsafe feed srcset: {source}')
                values.append(' '.join([target, *descriptor]))
            element.set('srcset', ', '.join(values))
    # XML parsers normalize CR/CRLF even inside CDATA. Normalize the extracted
    # copy once, so the published feed body round-trips without false diffs.
    return html.tostring(main, encoding='unicode', method='html', with_tail=False).replace('\r\n', '\n').replace('\r', '\n')


def cdata(value: str) -> str:
    return '<![CDATA[' + value.replace(']]>', ']]]]><![CDATA[>') + ']]>'


def refresh_rss(raw: str, now: datetime, root: Path = ROOT) -> tuple[str, list[dict]]:
    """Existing feed membership/publication dates are immutable in this step."""
    original = ET.fromstring(raw)
    newline = '\r\n' if '\r\n' in raw else '\n'
    changes = []

    def replace(match):
        block = match.group()
        # Namespace prefixes are declared at rss root, so parse within a shell.
        node = ET.fromstring('<rss xmlns:content="http://purl.org/rss/1.0/modules/content/">' + block + '</rss>')[0]
        url = node.findtext('link')
        document = html.fromstring(file_for_url(url, root).read_bytes())
        canonicals = document.xpath('//link[@rel="canonical"]/@href')
        if len(canonicals) != 1 or normalized_url(canonicals[0]) != normalized_url(url):
            raise ValueError(f'feed canonical mismatch: {url}')
        descriptions = document.xpath('//meta[@name="description"]/@content')
        if len(descriptions) != 1 or not descriptions[0].strip():
            raise ValueError(f'feed source description missing: {url}')
        description = re.search(r'(<description>)(.*?)(</description>)', block, re.S)
        if not description:
            raise ValueError('missing RSS description element')
        result = block[:description.start(2)] + escape(descriptions[0], quote=False) + block[description.end(2):]
        body = feed_body(document, url)
        element = '<content:encoded>' + cdata(body) + '</content:encoded>'
        content = re.compile(r'<content:encoded>.*?</content:encoded>', re.S)
        if len(content.findall(result)) > 1:
            raise ValueError('duplicate RSS content elements')
        if content.search(result):
            result = content.sub(lambda _: element, result)
        else:
            result = result.replace('</item>', '  ' + element + newline + '  </item>')
        if result != block:
            changes.append({'url': unquote(url), 'descriptionChanged': node.findtext('description') != descriptions[0], 'bodyBytes': len(body.encode('utf-8'))})
        return result

    result = ITEM.sub(replace, raw)
    if result != raw:
        if len(re.findall(r'<lastBuildDate>.*?</lastBuildDate>', result)) != 1 or now.tzinfo is None:
            raise ValueError('invalid feed build date')
        result = re.sub(r'(<lastBuildDate>).*?(</lastBuildDate>)', lambda m: m.group(1) + format_datetime(now) + m.group(2), result)
    generated = ET.fromstring(result)
    before, after = original.findall('channel/item'), generated.findall('channel/item')
    fields = ('title', 'link', 'guid', 'pubDate')
    if [[n.findtext(k) for k in fields] for n in before] != [[n.findtext(k) for k in fields] for n in after]:
        raise ValueError('RSS item identity/order/publication date changed')
    return result, changes


def audit(root: Path, sitemap: str, rss: str, scope: list[Path]) -> dict:
    errors = []
    all_html = set(root.rglob('*.html'))
    sitemap_nodes = ET.fromstring(sitemap).findall('s:url', NS)
    urls = [n.findtext('s:loc', namespaces=NS) for n in sitemap_nodes]
    identities = [normalized_url(u) for u in urls]
    if len(set(identities)) != len(identities):
        errors.append('duplicate sitemap URLs')
    if len(urls) > 50000 or len(sitemap.encode('utf-8')) >= 10 * 1024 * 1024:
        errors.append('sitemap exceeds Naver URL/size limits')
    for identity in identities:
        if identity[:2] != ('https', 'wawa-center.kr') or identity[3] or identity[4]:
            errors.append(f'noncanonical sitemap URL: {identity}')
    mapped_files = {file_for_url(u, root) for u in urls}
    if mapped_files - all_html:
        errors.append('sitemap target file missing')
    unlisted = {p.relative_to(root).as_posix() for p in all_html - mapped_files}
    if unlisted != INTERNAL_SNAPSHOTS:
        errors.append(f'unexpected HTML not in sitemap: {sorted(unlisted - INTERNAL_SNAPSHOTS)}')
    dates = [n.findtext('s:lastmod', namespaces=NS) for n in sitemap_nodes]
    for value in dates:
        if value and date.fromisoformat(value[:10]) > date.today():
            errors.append(f'future sitemap date: {value}')
    robots = RobotFileParser()
    robots.parse((root / 'robots.txt').read_text(encoding='utf-8').splitlines())
    if DOMAIN + '/sitemap.xml' not in (robots.site_maps() or []):
        errors.append('robots sitemap reference missing')

    # Check all sitemap entries against the real canonical/indexing directives.
    def scan_head(url):
        found = []
        file = file_for_url(url, root)
        if file not in all_html:
            return found
        raw = file.read_text(encoding='utf-8')
        head = re.split(r'</head\s*>', raw, maxsplit=1, flags=re.I)[0] + '</head></html>'
        doc = html.fromstring(head)
        canonicals = doc.xpath('//link[@rel="canonical"]/@href')
        if len(canonicals) != 1 or normalized_url(canonicals[0]) != normalized_url(url):
            found.append(f'sitemap canonical mismatch: {unquote(url)}')
        directives = doc.xpath('//meta[translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="robots" or @name="googlebot"]/@content')
        if any(re.search(r'\b(noindex|none)\b', value, re.I) for value in directives):
            found.append(f'noindex in sitemap: {unquote(url)}')
        if not all(robots.can_fetch(agent, url) for agent in ('Yeti', 'Googlebot')):
            found.append(f'robots disallow in sitemap: {unquote(url)}')
        return found

    with ThreadPoolExecutor(max_workers=8) as pool:
        for found in pool.map(scan_head, urls):
            errors.extend(found)
    print(f'{len(urls)} sitemap canonical/indexing checks finished', flush=True)

    @lru_cache(maxsize=None)
    def document(file):
        return html.fromstring(file.read_bytes())

    @lru_cache(maxsize=None)
    def target_for(value):
        return file_for_url(value, root)

    @lru_cache(maxsize=None)
    def ids(file):
        return set(document(file).xpath('//@id | //a/@name'))

    @lru_cache(maxsize=None)
    def exists(file):
        return file.is_file()

    link_count, fragments, resources = 0, set(), set()
    titles, descriptions = Counter(), Counter()
    for file in scope:
        label = file.relative_to(root).as_posix()
        doc, url = document(file), page_url(file, root)
        canonicals = doc.xpath('//link[@rel="canonical"]/@href')
        og = doc.xpath('//meta[@property="og:url"]/@content')
        title = doc.xpath('//title/text()')
        description = doc.xpath('//meta[@name="description"]/@content')
        if len(doc.xpath('//h1')) != 1 or len(title) != 1 or not title[0].strip() or len(description) != 1 or not description[0].strip():
            errors.append(f'title/H1/description contract: {label}')
        if len(og) != 1 or len(canonicals) != 1 or normalized_url(og[0]) != normalized_url(canonicals[0]):
            errors.append(f'canonical/og:url mismatch: {label}')
        titles[''.join(title)] += 1
        descriptions[''.join(description)] += 1
        for value in doc.xpath('//a/@href'):
            target = urljoin(url, value)
            parsed = urlsplit(target)
            if parsed.netloc != 'wawa-center.kr' or parsed.scheme not in ('http', 'https'):
                continue
            link_count += 1
            dest = target_for(target)
            if not exists(dest):
                errors.append(f'link target missing: {label} -> {value}')
            elif parsed.fragment:
                fragments.add((dest, unquote(parsed.fragment)))
        values = doc.xpath('//img/@src | //script/@src | //link[@rel="stylesheet"]/@href | //video/@poster | //source/@src')
        for srcset in doc.xpath('//*[@srcset]/@srcset'):
            values.extend(v.strip().split()[0] for v in srcset.split(',') if v.strip())
        for value in values:
            target = urljoin(url, value)
            if urlsplit(target).netloc == 'wawa-center.kr':
                resources.add(target_for(target))
        for payload in doc.xpath('//script[@type="application/ld+json"]/text()'):
            data = json.loads(payload)
            graph = data.get('@graph', [])
            graph_ids = [n['@id'] for n in graph if '@id' in n]
            if len(graph_ids) != len(set(graph_ids)):
                errors.append(f'duplicate schema node IDs: {label}')
            defined, references = set(), []

            def visit(value):
                if isinstance(value, dict):
                    if '@id' in value:
                        if set(value) == {'@id'}:
                            references.append(value['@id'])
                        else:
                            defined.add(value['@id'])
                    for item in value.values():
                        visit(item)
                elif isinstance(value, list):
                    for item in value:
                        visit(item)

            visit(data)
            defined_urls = {normalized_url(urljoin(url, value)) for value in defined}
            for value in references:
                ref = normalized_url(urljoin(url, value))
                if ref[:4] == normalized_url(url)[:4] and ref not in defined_urls and ref[4] not in ids(file):
                    errors.append(f'dangling local JSON-LD reference: {label} -> {value}')
    for file, fragment in fragments:
        if fragment not in ids(file):
            errors.append(f'fragment missing: {file.relative_to(root)}#{fragment}')
    for file in resources:
        if not exists(file):
            errors.append(f'local media/script/style missing: {file.relative_to(root)}')
    if any(n > 1 for n in titles.values()) or any(n > 1 for n in descriptions.values()):
        errors.append('duplicate titles/descriptions in scoped pages')

    channel = ET.fromstring(rss).find('channel')
    items = channel.findall('item')
    if not items or len(rss.encode('utf-8')) >= 10 * 1024 * 1024:
        errors.append('RSS item count/size invalid')
    feed_urls = [normalized_url(n.findtext('link')) for n in items]
    if len(feed_urls) != len(set(feed_urls)):
        errors.append('duplicate RSS item URLs')
    for item in items:
        url = item.findtext('link')
        file = file_for_url(url, root)
        if normalized_url(url) not in set(identities) or not file.is_file():
            errors.append(f'RSS target absent: {url}')
            continue
        doc = document(file)
        if normalized_url(item.findtext('guid')) != normalized_url(url):
            errors.append(f'RSS guid mismatch: {url}')
        if item.findtext('description') != doc.xpath('//meta[@name="description"]/@content')[0]:
            errors.append(f'RSS summary mismatch: {url}')
        if item.findtext(CONTENT) != feed_body(doc, url):
            errors.append(f'RSS full body mismatch: {url}')
        if parsedate_to_datetime(item.findtext('pubDate')) > datetime.now().astimezone():
            errors.append(f'RSS publication date in future: {url}')
    return {
        'scopePages': len(scope), 'sitemapUrls': len(urls), 'sitemapBytes': len(sitemap.encode('utf-8')),
        'siteHtmlFiles': len(all_html), 'unlistedInternalSnapshots': sorted(unlisted),
        'sitemapDates': dict(Counter(dates)), 'rssItems': len(items), 'rssBytes': len(rss.encode('utf-8')),
        'localLinkOccurrences': link_count, 'uniqueFragmentTargets': len(fragments), 'uniqueResources': len(resources),
        'duplicateTitles': sum(n - 1 for n in titles.values()), 'duplicateDescriptions': sum(n - 1 for n in descriptions.values()),
        'errors': errors, 'errorCount': len(errors),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='update only sitemap.xml and rss.xml locally; never deploy')
    args = parser.parse_args()
    print('Preparing scoped inventory and previous review evidence', flush=True)
    scope = scoped_paths()
    dates = reviewed_date_evidence()
    previous = json.loads((AUDIT_ROOT / 'wawa-center-step7-20260920/verification.json').read_text(encoding='utf-8'))
    protected = {Path(p) for p in previous['protectedHashes']} - {ROOT / 'sitemap.xml', ROOT / 'rss.xml'}
    protected |= set(ROOT.rglob('*.html'))
    print(f'Hashing {len(protected)} protected files', flush=True)
    before = file_hashes(protected)
    for path, digest in before.items():
        if not Path(path).is_relative_to(ROOT) and digest != previous['protectedHashes'].get(path):
            raise ValueError(f'original source changed after the previous review: {path}')
    print(f'{len(scope)} scoped pages, {len(before)} protected files: auditing sitemap/RSS and links', flush=True)
    sources = {name: (ROOT / name).read_bytes() for name in ('sitemap.xml', 'rss.xml')}
    sitemap, sitemap_changes = refresh_sitemap(sources['sitemap.xml'].decode('utf-8'), dates)
    rss, rss_changes = refresh_rss(sources['rss.xml'].decode('utf-8'), datetime.now().astimezone())
    generated = {'sitemap.xml': sitemap.encode('utf-8'), 'rss.xml': rss.encode('utf-8')}
    result = audit(ROOT, sitemap, rss, scope)
    result |= {'sitemapDateUpdatesThisRun': len(sitemap_changes), 'rssItemUpdatesThisRun': len(rss_changes),
               'rssDescriptionUpdatesThisRun': sum(c['descriptionChanged'] for c in rss_changes),
               'protectedFileCount': len(before), 'protectedHashes': before, 'appliedLocally': False, 'deployed': False,
               'sitemapChanges': sitemap_changes, 'rssChanges': rss_changes,
               'feedHashes': {name: hashlib.sha256(value).hexdigest() for name, value in generated.items()}}
    baseline = REPORT_ROOT / 'before-step8'
    baseline_sitemap = (baseline / 'sitemap.xml').read_bytes() if (baseline / 'sitemap.xml').is_file() else sources['sitemap.xml']
    baseline_rss = (baseline / 'rss.xml').read_bytes() if (baseline / 'rss.xml').is_file() else sources['rss.xml']
    _, total_sitemap_changes = refresh_sitemap(baseline_sitemap.decode('utf-8'), dates)
    _, total_rss_changes = refresh_rss(baseline_rss.decode('utf-8'), datetime.now().astimezone())
    result |= {'sitemapDateUpdatesTotal': len(total_sitemap_changes), 'rssItemUpdatesTotal': len(total_rss_changes),
               'rssDescriptionUpdatesTotal': sum(c['descriptionChanged'] for c in total_rss_changes)}
    print('Rechecking protected content hashes after audit', flush=True)
    if file_hashes(before) != before:
        raise ValueError('protected files changed during audit')
    if any((ROOT / name).read_bytes() != value for name, value in sources.items()):
        raise ValueError('feed changed concurrently during audit')
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    for name, value in generated.items():
        stage = REPORT_ROOT / 'staged' / name
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(value)
    if args.write and not result['errors']:
        for name, value in sources.items():
            backup = REPORT_ROOT / 'before-step8' / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(value)
            if value != generated[name]:
                (ROOT / name).write_bytes(generated[name])
        if file_hashes(before) != before:
            raise ValueError('protected files changed after feed write')
        if any(sha(ROOT / name) != digest for name, digest in result['feedHashes'].items()):
            raise ValueError('applied feed hash mismatch')
        result['appliedLocally'] = True
    (REPORT_ROOT / ('verification.json' if args.write else 'dry-run.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('protectedHashes', 'sitemapChanges', 'rssChanges', 'errors')}, ensure_ascii=False, indent=2))
    if result['errors']:
        print(json.dumps(result['errors'][:30], ensure_ascii=False, indent=2))
        raise SystemExit('Integration audit failed; no feeds applied.')


if __name__ == '__main__':
    main()
