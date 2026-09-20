"""Unify all public menus and delivery hints without changing page content.

Default stages a reviewed copy outside the site. --write applies only after all
pages pass preservation checks. --check fails on future template/menu drift.
This command never commits, pushes, deploys, or updates sitemap dates.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from lxml import html
from PIL import Image

from compact_center_search import read_source, render as render_search
from site_navigation import FONT_URL, HEADER_STYLE, NAV, active_section, render_header, unify_header

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path(r'C:\Users\1992k\Desktop\CodexData\audit-output\wawa-site-navigation-20260920')
IMG_RE = re.compile(r'<img\b[^>]*>', re.I)
LINK_RE = re.compile(r'<link\b[^>]*>', re.I)
SCRIPT_RE = re.compile(r'<script\b[^>]*\bsrc=["\'][^"\']+["\'][^>]*>', re.I)
STYLE_VERSIONS = {'header.css', 'branch-directory.css', 'math-academy.css', 'subject-academy.css',
                  'learning-upgrade.css', 'branch-hub-upgrade.css'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def url_for(relative):
    return 'https://wawa-center.kr/' + relative.removesuffix('index.html')


def attr(tag, name, value):
    escaped = str(value).replace('&', '&amp;').replace('"', '&quot;')
    pattern = rf'(?<![\w-]){re.escape(name)}\s*=\s*(["\']).*?\1'
    replacement = f'{name}="{escaped}"'
    if re.search(pattern, tag, re.I | re.S):
        return re.sub(pattern, lambda _: replacement, tag, count=1, flags=re.I | re.S)
    position = tag.rfind('/>') if tag.endswith('/>') else tag.rfind('>')
    return tag[:position].rstrip() + ' ' + replacement + tag[position:]


@lru_cache(maxsize=None)
def dimensions(source):
    parts = urlsplit(source)
    if parts.netloc != 'wawa-center.kr':
        return None
    path = (ROOT / unquote(parts.path).lstrip('/')).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError):
        return None


def image_hints(tag, page_url, stats):
    node = html.fragment_fromstring(tag)
    before = tag
    classes = node.get('class', '').split()
    hidden = bool(re.search(r'display\s*:\s*none', node.get('style', ''), re.I)) or 'hidden' in node.attrib or 'bulk-hidden-image' in classes
    source = urljoin(page_url, node.get('src', ''))
    map_image = '/assets/maps/' in source or '/branch-directory/maps/' in source or '지도' in node.get('alt', '')
    # Only invisible representatives and below-body maps change loading policy.
    # Visible body images, source paths, order, cropping and existing priority stay intact.
    if (hidden or map_image) and node.get('loading') != 'lazy':
        tag = attr(tag, 'loading', 'lazy')
        stats['hiddenImagesDeferred' if hidden else 'mapImagesDeferred'] += 1
    if not node.get('decoding'):
        tag = attr(tag, 'decoding', 'async')
        stats['asyncDecodingAdded'] += 1
    if not node.get('width') and not node.get('height'):
        size = dimensions(source)
        if size:
            tag = attr(attr(tag, 'width', size[0]), 'height', size[1])
            stats['imageDimensionsAdded'] += 1
    if before != tag:
        stats['imageTagsUpdated'] += 1
    return tag


def transform(raw, relative, stats=None):
    stats = stats if stats is not None else Counter()
    result = unify_header(raw, '/' + relative)

    def stylesheet(match):
        tag = match[0]
        node = html.fragment_fromstring(tag)
        href = node.get('href', '')
        file = urlsplit(href).path.split('/')[-1]
        if file == 'branch-hub-upgrade.css' and not relative.startswith('지점안내/'):
            return ''
        if file in STYLE_VERSIONS:
            return attr(tag, 'href', '/assets/' + file + '?v=20260920-nav1')
        return tag

    result = LINK_RE.sub(stylesheet, result)

    def script(match):
        tag = match[0]
        node = html.fragment_fromstring(tag)
        file = urlsplit(node.get('src', '')).path.split('/')[-1]
        if file in ('center-search-data.js', 'center-search-index.js', 'center-search.js'):
            file = 'center-search-index.js' if file in ('center-search-data.js', 'center-search-index.js') else file
            tag = attr(tag, 'src', '/assets/' + file + '?v=20260920-nav1')
            if 'defer' not in node.attrib:
                tag = tag[:-1] + ' defer>'
        return tag

    result = SCRIPT_RE.sub(script, result)
    result = IMG_RE.sub(lambda m: image_hints(m[0], url_for(relative), stats), result)
    return result


def protected_content(raw, relative):
    """Everything outside explicitly allowed navigation/delivery changes is immutable."""
    doc = html.fromstring(raw)
    for node in list(doc.xpath('//header[contains(concat(" ",normalize-space(@class)," ")," site-header ")]')):
        node.getparent().remove(node)
    for node in list(doc.xpath('//comment()')):
        if (node.text or '').strip().startswith('shared-site-fonts:'):
            node.getparent().remove(node)
    for node in list(doc.xpath('//link[@href]')):
        href = node.get('href')
        parts = urlsplit(href)
        if parts.netloc in ('fonts.googleapis.com', 'fonts.gstatic.com'):
            node.getparent().remove(node)
            continue
        name = parts.path.split('/')[-1]
        if name == 'branch-hub-upgrade.css' and not relative.startswith('지점안내/'):
            node.getparent().remove(node)
        elif name in STYLE_VERSIONS:
            node.set('href', '/assets/' + name)
    for node in doc.xpath('//img'):
        for key in ('loading', 'decoding', 'width', 'height'):
            node.attrib.pop(key, None)
    for node in doc.xpath('//script[@src]'):
        name = urlsplit(node.get('src')).path.split('/')[-1]
        if name in ('center-search-data.js', 'center-search-index.js', 'center-search.js'):
            node.set('src', '/assets/' + ('center-search-data.js' if name == 'center-search-index.js' else name))
            node.attrib.pop('defer', None)
    for node in doc.iter():
        for key in ('text', 'tail'):
            value = getattr(node, key)
            if value is not None and not value.strip():
                setattr(node, key, None)
    return sha(html.tostring(doc, encoding='utf-8'))


def validate(before, after, relative):
    if protected_content(before, relative) != protected_content(after, relative):
        raise ValueError(f'Protected content changed: {relative}')
    doc = html.fromstring(after)
    expected = list(NAV)
    actual = [(a.text_content(), a.get('href')) for a in doc.xpath('//header//*[@class="nav-links"]/a')]
    if actual != expected:
        raise ValueError(f'Incorrect shared navigation: {relative}')
    if doc.xpath('//header//a[@aria-current="page"]/@href') != [active_section('/' + relative)]:
        raise ValueError(f'Incorrect active section: {relative}')
    if doc.xpath('//link[contains(@href,"fonts.googleapis.com") and @rel="stylesheet"]/@href') != [FONT_URL]:
        raise ValueError(f'Font declaration is not singular: {relative}')
    if doc.xpath('//link[contains(@href,"/assets/header.css")]/@href') != [HEADER_STYLE]:
        raise ValueError(f'Header style is not singular: {relative}')
    if transform(after, relative) != after:
        raise ValueError(f'Non-idempotent transformation: {relative}')
    old_images = html.fromstring(before).xpath('//img')
    new_images = doc.xpath('//img')
    if len(old_images) != len(new_images):
        raise ValueError(f'Image count changed: {relative}')
    for old, new in zip(old_images, new_images):
        for key in ('src', 'srcset', 'sizes', 'alt', 'style', 'class', 'fetchpriority'):
            if old.get(key) != new.get(key):
                raise ValueError(f'Image {key} changed: {relative}')
        for key in ('width', 'height'):
            if old.get(key) and old.get(key) != new.get(key):
                raise ValueError(f'Existing image dimension changed: {relative}')


def public_files():
    files = subprocess.check_output(['git', 'ls-files', '-z', '*.html'], cwd=ROOT).decode('utf-8').split('\0')
    return [p for p in files if p and not p.startswith(('tmp/', 'tools/', 'scripts/', 'reports/'))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.write and args.check:
        parser.error('--write and --check are mutually exclusive')
    REPORT.mkdir(parents=True, exist_ok=True)
    stage = REPORT / 'staged-site'
    changed, stats, families = [], Counter(), Counter()
    protected = {name: sha((ROOT / name).read_bytes()) for name in ('sitemap.xml', 'rss.xml', 'robots.txt', 'vercel.json')}
    files = public_files()
    for i, relative in enumerate(files, 1):
        source = (ROOT / relative).read_bytes()
        raw = source.decode('utf-8-sig').replace('\r\n', '\n')
        after = transform(raw, relative, stats)
        if not args.check or raw != after:
            validate(raw, after, relative)
        families[relative.split('/')[0]] += 1
        if raw != after:
            payload = after.encode('utf-8')
            changed.append({'file': relative, 'before': sha(source), 'after': sha(payload), 'byteChange': len(payload) - len(source)})
            if not args.check:
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        if i % 2000 == 0:
            print(f'Validated {i}/{len(files)} pages; changed {len(changed)}', flush=True)
    search_source = (ROOT / 'assets/center-search-data.js').read_bytes()
    rows = read_source()
    compact = render_search(rows).encode('utf-8')
    search_target = ROOT / 'assets/center-search-index.js'
    search_change = not search_target.is_file() or search_target.read_bytes() != compact
    if args.write:
        # Verify the entire plan against concurrent edits before writing anything.
        for row in changed:
            if sha((ROOT / row['file']).read_bytes()) != row['before'] or sha((stage / row['file']).read_bytes()) != row['after']:
                raise ValueError(f'Concurrent file change: {row["file"]}')
        for row in changed:
            (ROOT / row['file']).write_bytes((stage / row['file']).read_bytes())
        if search_change:
            search_target.write_bytes(compact)
    for name, digest in protected.items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError(f'Unexpected discovery/config change: {name}')
    if not args.check:
        (stage / 'assets').mkdir(parents=True, exist_ok=True)
        (stage / 'assets/center-search-index.js').write_bytes(compact)
    result = {'publicPages': len(files), 'changedPages': len(changed), 'families': families, 'imageUpdates': stats,
              'protectedContentErrors': 0, 'navigationLinksPerPage': 9, 'sourceSearchEntries': len(rows),
              'searchBeforeBytes': len(search_source), 'searchAfterBytes': len(compact),
              'searchBeforeGzipBytes': len(gzip.compress(search_source, mtime=0)),
              'searchAfterGzipBytes': len(gzip.compress(compact, mtime=0)),
              'protectedConfigHashes': protected, 'written': args.write, 'deployed': False, 'changes': changed}
    name = 'check.json' if args.check else ('verification.json' if args.write else 'dry-run.json')
    (REPORT / name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'changes'}, ensure_ascii=False, indent=2))
    if args.check and (changed or search_change):
        raise SystemExit('Navigation/delivery output drift detected. Run this tool with --write and repeat QA before release.')


if __name__ == '__main__':
    main()
