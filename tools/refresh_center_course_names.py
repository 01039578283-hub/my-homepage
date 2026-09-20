"""Audited, idempotent finalizer for the six legacy school-stage courses.

Usage: python -B tools/refresh_center_course_names.py --write
       python -B tools/refresh_center_course_names.py --check
Reports/backups are outside the public site. No URL, image, fee or grade fact
is changed. Search rows retain their original identity, count and ordering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from lxml import html

from center_course_names import COURSES, DOMAIN, LABEL_ATTRS, META, mask, rename, transform
from compact_center_search import read_source, render

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r'C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-course-names-20260920')
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pages():
    tree = ET.parse(ROOT / 'sitemap.xml')
    rows = []
    for loc in tree.findall('.//s:loc', NS):
        url = loc.text
        if urlsplit(url).hostname != 'wawa-center.kr':
            raise ValueError('unexpected sitemap host')
        path = unquote(urlsplit(url).path)
        file = ROOT / path.lstrip('/')
        if path.endswith('/'):
            file /= 'index.html'
        elif not file.is_file():
            file = file / 'index.html' if (file / 'index.html').is_file() else file.with_suffix('.html')
        if not file.is_file() or file.suffix != '.html':
            raise ValueError(f'missing page: {url}')
        rows.append((url, file))
    if len(rows) != len({str(f) for _, f in rows}):
        raise ValueError('duplicate sitemap page')
    return rows


def masked_json(value):
    if isinstance(value, dict):
        return {k: masked_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [masked_json(v) for v in value]
    return mask(value) if isinstance(value, str) else value


def protected_signature(doc):
    out = []
    for el in doc.iter():
        attrs = []
        for key, value in sorted(el.attrib.items()):
            can_mask = key in LABEL_ATTRS
            if el.tag == 'meta' and key == 'content':
                can_mask = (el.get('name') or el.get('property') or '').lower() in META
            attrs.append((key, mask(value) if can_mask else value))
        text = el.text or ''
        if el.tag == 'script':
            if el.get('type', '').lower() == 'application/ld+json':
                text = json.dumps(masked_json(json.loads(text)), ensure_ascii=False, sort_keys=True)
        elif el.tag != 'style':
            text = mask(text)
        out.append((el.tag, attrs, text, mask(el.tail or '')))
    return out


def prepare(row):
    url, file = row
    before = file.read_bytes()
    raw = before.decode('utf-8')
    new = transform(raw, url)
    before_doc = html.fromstring(raw)
    title_before = before_doc.xpath('string(//title)')
    title_after = title_before
    changed = new != raw
    primary = urlsplit(url).path.startswith('/center/') and urlsplit(url).path.strip('/').split('/')[-1] in COURSES
    result = {'path': file.relative_to(ROOT).as_posix(), 'url': url,
              'beforeSha256': sha(before), 'changed': changed, 'primary': primary,
              'titleBefore': title_before}
    if changed:
        after_doc = html.fromstring(new)
        if protected_signature(before_doc) != protected_signature(after_doc):
            raise ValueError(f'non-name change: {url}')
        if transform(new, url) != new:
            raise ValueError(f'not idempotent: {url}')
        title_after = after_doc.xpath('string(//title)')
        rel = file.relative_to(ROOT)
        for folder, data in [('before', before), ('staged', new.encode('utf-8'))]:
            target = OUT / folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if folder == 'before' and target.exists():
                if target.read_bytes() != data:
                    raise ValueError('refusing to overwrite different backup')
            else:
                target.write_bytes(data)
    if primary:
        doc = html.fromstring(new) if changed else before_doc
        h1 = doc.xpath('//h1')
        if len(h1) != 1 or not any(level in h1[0].text_content() for level in ('초등학생', '중학생', '고등학생')):
            raise ValueError(f'incorrect renamed H1: {url}')
    result['titleAfter'] = title_after
    result['afterSha256'] = sha(new.encode('utf-8'))
    return result


def search_update():
    before = read_source()
    after = [{**r, 'title': rename(r['title']), 'search': rename(r['search'])} for r in before]
    if len(after) != 6025 or [r['url'] for r in after] != [r['url'] for r in before]:
        raise ValueError('search inventory changed')
    source = 'window.WAWA_CENTER_INDEX = ' + json.dumps(after, ensure_ascii=False, indent=2) + ';\n'
    return {'assets/center-search-data.js': source, 'assets/center-search-index.js': render(after)}, sum(a != b for a, b in zip(before, after))


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = pages()
    if args.check:
        def needs_update(row):
            url, file = row
            raw = file.read_text(encoding='utf-8')
            return file.relative_to(ROOT).as_posix() if transform(raw, url) != raw else None
        with ThreadPoolExecutor(max_workers=8) as pool:
            failures = [v for v in pool.map(needs_update, rows) if v]
        expected, _ = search_update()
        # Source formatting is not significant; delivery must decode the same rows.
        if (ROOT / 'assets/center-search-index.js').read_text(encoding='utf-8') != expected['assets/center-search-index.js']:
            failures.append('assets/center-search-index.js')
        report = {'pages': len(rows), 'pending': failures}
        (OUT / 'check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'pages': len(rows), 'pendingCount': len(failures), 'examples': failures[:10]}, ensure_ascii=False), flush=True)
        raise SystemExit(bool(failures))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = []
        for result in pool.map(prepare, rows):
            results.append(result)
            if len(results) % 2000 == 0:
                print(f'Validated {len(results)}/{len(rows)} pages', flush=True)
    primary = [r for r in results if r['primary']]
    if len(primary) != 2226:
        raise ValueError(f'expected 2226 primary pages, got {len(primary)}')
    changed = [r for r in results if r['changed']]
    # Verify the complete precondition before applying any file.
    for row in results:
        if sha((ROOT / row['path']).read_bytes()) != row['beforeSha256']:
            raise ValueError(f'concurrent change: {row["path"]}')
    extra, search_rows = search_update()
    for rel, text in extra.items():
        backup = OUT / 'before' / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes((ROOT / rel).read_bytes())
        stage = OUT / 'staged' / rel
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(text.encode('utf-8'))
    (OUT / 'changes.json').write_text(json.dumps(changed, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in changed:
        (ROOT / row['path']).write_bytes((OUT / 'staged' / row['path']).read_bytes())
    for rel in extra:
        (ROOT / rel).write_bytes((OUT / 'staged' / rel).read_bytes())
    counts = {}
    for key in ('titleBefore', 'titleAfter'):
        counter = Counter(r[key] for r in results)
        counts[key] = {'duplicateGroups': sum(n > 1 for n in counter.values()),
                       'pagesInDuplicateGroups': sum(n for n in counter.values() if n > 1)}
    report = {'pagesAudited': len(rows), 'primaryPages': len(primary), 'changedHtml': len(changed),
              'searchRowsRenamed': search_rows, 'searchRows': 6025, 'duplicates': counts,
              'protectedContentErrors': 0, 'urlChanges': 0, 'deployed': False}
    (OUT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
