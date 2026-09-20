"""Stage and verify this local hub upgrade; --write applies it, never deploys."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import html

import generate_branch_directory as directory
from branch_course_guidance import verify_source, course_guidance
from branch_hub_upgrade import ROOT, STYLE, upgrade_header, upgrade_child, related_entries
from branch_release_check import refresh_rss, refresh_sitemap

REPORT_ROOT = Path(r'C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-hub-upgrade-20260920')
CORE = ['index.html', 'overview/index.html', 'guide/index.html', '교육정보/index.html',
        '학부모후기/index.html', '과목별학원/index.html', '학년별학원/index.html', 'center/index.html']


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def graph(doc):
    return json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']


def protected_content(raw, kind):
    doc = html.fromstring(raw)
    allowed = '//header | //link[@href="' + STYLE + '"]'
    nodes = None if kind == 'core' else graph(doc)
    if nodes is not None:
        allowed += ' | //script[@type="application/ld+json"]'
        for node in nodes:
            if kind == 'center' and node.get('@type') == 'Article':
                node.pop('articleSection', None)
            if kind == 'child':
                if node.get('@type') == 'WebPage':
                    node.pop('relatedLink', None)
                if node.get('@id', '').endswith('#related-pages'):
                    node.pop('itemListElement', None)
                    node.pop('numberOfItems', None)
            if kind == 'region' and node.get('@type') == 'FAQPage':
                node['mainEntity'][1]['acceptedAnswer'].pop('text', None)
    if kind == 'center':
        allowed += ' | //section[@id="learning" or @id="learning-pages" or @aria-labelledby="related-title"] | //nav[@class="branch-toc"]/a[@href="#learning-pages"]'
    elif kind == 'child':
        allowed += ' | //section[@id="related-pages"]'
    elif kind in ('region', 'national'):
        allowed += ' | //section[@id="coaching-system"]'
        if kind == 'region':
            allowed += ' | //section[@id="faq"]/details[2]/p | //section[contains(@class,"branch-related")]//a[@href="/guide/parent-consultation-checklist/"]'
    for node in doc.xpath(allowed):
        node.getparent().remove(node)
    for node in doc.xpath('//link[starts-with(@href,"/assets/branch-directory.css?")]'):
        node.set('href', '/assets/branch-directory.css')
    for node in doc.iter():
        for field in ('text', 'tail'):
            value = getattr(node, field)
            if value is not None and not value.strip():
                setattr(node, field, None)
    return nodes, html.tostring(doc, encoding='unicode')


def validate_page(raw, kind, center=None, item=None):
    doc = html.fromstring(raw)
    assert len(doc.xpath('//h1')) == 1, 'H1 count'
    assert doc.xpath('//header//a[@href="/지점안내/"]'), 'Missing top-level entry'
    assert len(doc.xpath('//header//div[@class="nav-links"]/a')) == 9
    if kind == 'core':
        return
    nodes = graph(doc)
    faq = next(n for n in nodes if n.get('@type') == 'FAQPage')
    visible = doc.xpath('//section[@id="faq"]//details')
    assert len(visible) == len(faq['mainEntity'])
    for detail, entry in zip(visible, faq['mainEntity']):
        assert detail.xpath('summary')[0].text_content().strip() == entry['name']
        assert detail.xpath('p')[0].text_content().strip() == entry['acceptedAnswer']['text']
    if kind == 'child':
        expected = [path for _, path, _, _ in related_entries(center, item)]
        actual = doc.xpath('//*[@id="related-pages"]//a/@href')
        assert actual == expected and 4 <= len(actual) <= 5 and len(actual) == len(set(actual))
        listing = next(n for n in nodes if n.get('@id', '').endswith('#related-pages'))
        assert [unquote(urlsplit(n['url']).path) for n in listing['itemListElement']] == actual
        assert [n['position'] for n in listing['itemListElement']] == list(range(1, len(actual) + 1))
    if kind == 'center':
        expected = [f'/지점안내/{center["region"]}/{center["routeName"]}/{area}{level}{subject}학원/'
                    for area in center['neighborhoods'] for level in ('초등','중등','고등') for subject in ('수학','영어')]
        assert doc.xpath('//*[@id="learning-pages"]//a/@href') == expected, 'Child pages must all remain reachable'
        for level, prefix in (('초등','초'),('중등','중'),('고등','고')):
            stage = doc.xpath(f'//*[@id="learning"]//*[@data-learning-level="{level}"]')
            offered = [s for s in ('영어','수학') if course_guidance(center,s,prefix)['grades']]
            assert bool(stage) == bool(offered)
            if stage:
                assert stage[0].xpath('.//h4/text()') == [f'{s} · {course_guidance(center,s,prefix)["label"]}' for s in offered]
        if '모두' in center['brand']:
            assert not doc.xpath('//*[@id="learning"]//a[starts-with(@href,"/overview/")]')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    verify_source(directory.SOURCE_WORKBOOK)
    centers = json.loads((ROOT / 'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    records = json.loads((ROOT / 'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']
    by_name = {c['routeName']: c for c in centers}
    assert len(centers) == 193 and len(records) == 2226
    stage, backup = REPORT_ROOT / 'staged-site', REPORT_ROOT / 'before'
    directory.OUTPUT_ROOT = stage / '지점안내'
    targets = []
    # A full regeneration is limited to 210 hubs. Child manuscript HTML stays
    # byte-for-byte intact outside the specified header/related block/schema.
    targets.append((directory.generate_hub(centers).strip('/')+'/index.html', 'national', None, None))
    for region in directory.REGIONS:
        group = [c for c in centers if c['region'] == region]
        if group:
            path = directory.generate_region_page(region, group)
            targets.append((path.strip('/')+'/index.html', 'region', None, None))
    for center in centers:
        path = directory.generate_branch_page(center)
        targets.append((path.strip('/')+'/index.html', 'center', center, None))
    for item in records:
        center = by_name[item['center']]
        relative = Path(item['file']).as_posix()
        raw = (ROOT / relative).read_text(encoding='utf-8')
        dest = stage / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(upgrade_child(raw, center, item), encoding='utf-8')
        targets.append((relative, 'child', center, item))
    for relative in CORE:
        active = '/' if relative == 'index.html' else '/' + relative.removesuffix('index.html')
        dest = stage / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(upgrade_header((ROOT / relative).read_text(encoding='utf-8'), active), encoding='utf-8')
        targets.append((relative, 'core', None, None))

    changed, stats = [], Counter()
    link_targets, anchor_targets = set(), set()
    ids_cache = {}
    def resolve(path):
        candidate = stage / path
        return candidate if candidate.is_file() else ROOT / path
    for relative, kind, center, item in targets:
        old = (ROOT / relative).read_text(encoding='utf-8')
        new = (stage / relative).read_text(encoding='utf-8')
        if protected_content(old, kind) != protected_content(new, kind):
            raise ValueError(f'Unrelated content changed: {relative}')
        validate_page(new, kind, center, item)
        doc = html.fromstring(new)
        ids = doc.xpath('//@id')
        assert len(ids) == len(set(ids)), f'Duplicate DOM ID: {relative}'
        for href in doc.xpath('//a/@href'):
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or (parts.path and not parts.path.startswith('/')):
                continue
            path = unquote(parts.path)
            target = (path.strip('/') + '/index.html').lstrip('/') if path else relative
            if path and not path.endswith('/'):
                target = path.lstrip('/')
            assert '..' not in Path(target).parts
            file = resolve(target)
            if not file.is_file():
                raise ValueError(f'Broken internal link: {relative} -> {href}')
            link_targets.add(target)
            if parts.fragment:
                if target not in ids_cache:
                    ids_cache[target] = set(html.fromstring(file.read_bytes()).xpath('//@id'))
                assert unquote(parts.fragment) in ids_cache[target], f'Missing anchor: {relative} -> {href}'
                anchor_targets.add((target, parts.fragment))
        stats[kind] += 1
        if old != new:
            changed.append(relative)
        if kind == 'child':
            stats['relatedLinksBefore'] += len(html.fromstring(old).xpath('//*[@id="related-pages"]//a'))
            stats['relatedLinksAfter'] += len(doc.xpath('//*[@id="related-pages"]//a'))
    # Feed membership and original publication dates stay unchanged; update
    # only existing RSS bodies that actually changed, without refreshing 20k dates.
    import xml.etree.ElementTree as ET
    from branch_release_check import file_for_url
    rss = (ROOT / 'rss.xml').read_text(encoding='utf-8')
    for entry in ET.fromstring(rss).findall('channel/item'):
        file = file_for_url(entry.findtext('link'))
        relative = file.relative_to(ROOT)
        if not (stage / relative).is_file():
            (stage / relative).parent.mkdir(parents=True, exist_ok=True)
            (stage / relative).write_bytes(file.read_bytes())
    new_rss, rss_changes = refresh_rss(rss, datetime.now().astimezone(), stage)
    (stage / 'rss.xml').write_text(new_rss, encoding='utf-8')
    sitemap = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
    # Menu-only changes do not represent a new article publication.
    dates = {'/' + f.removesuffix('index.html'): directory.TODAY for f in changed if f not in CORE}
    new_sitemap, sitemap_changes = refresh_sitemap(sitemap, dates)
    (stage / 'sitemap.xml').write_text(new_sitemap, encoding='utf-8')
    applied = [*changed]
    if rss != new_rss:
        applied.append('rss.xml')
    if sitemap != new_sitemap:
        applied.append('sitemap.xml')
    if args.write:
        for relative in applied:
            destination = (ROOT / relative).resolve()
            assert destination.is_relative_to(ROOT.resolve()) and destination.is_file()
            before = backup / relative
            before.parent.mkdir(parents=True, exist_ok=True)
            if not before.exists():
                before.write_bytes(destination.read_bytes())
            destination.write_bytes((stage / relative).read_bytes())
    report = {'applied': args.write, 'counts': dict(stats), 'changedPages': len(changed),
              'checkedInternalDestinations': len(link_targets), 'checkedAnchorTargets': len(anchor_targets),
              'rssChangedItems': len(rss_changes), 'sitemapChangedDates': len(sitemap_changes),
              'files': applied, 'errors': [], 'stage': str(stage), 'backup': str(backup)}
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / ('verification.json' if args.write else 'dry-run.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
