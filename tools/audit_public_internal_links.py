"""Read-only complete sitemap HTML/fragment/link and structured-data audit."""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from urllib.parse import urljoin, urlsplit, unquote

from lxml import html

from refresh_center_course_names import ROOT, OUT, pages
from center_course_names import OLD, COURSES


@lru_cache(maxsize=None)
def local_target(path):
    file = ROOT / path.lstrip('/')
    if file.is_file():
        return file
    if (file / 'index.html').is_file():
        return file / 'index.html'
    if not file.suffix and file.with_suffix('.html').is_file():
        return file.with_suffix('.html')
    return None


def main():
    rows = pages()
    ids, cross, broken, stale, metadata = {}, [], [], [], []
    counters = Counter()
    unique = set()
    for index, (url, file) in enumerate(rows, 1):
        doc = html.fromstring(file.read_bytes())
        ids[file] = set(doc.xpath('//@id')) | set(doc.xpath('//a/@name'))
        own_path = unquote(urlsplit(url).path)
        for script in doc.xpath('//script[@type="application/ld+json"]'):
            json.loads(script.text or '')
            counters['jsonLdBlocks'] += 1
        title, h1, description, canonical = [doc.xpath(expr) for expr in (
            '//title', '//h1', '//meta[@name="description"]/@content', '//link[@rel="canonical"]/@href')]
        if len(title) != 1 or len(h1) != 1 or len(description) != 1 or len(canonical) != 1:
            metadata.append({'url': url, 'counts': list(map(len, [title, h1, description, canonical]))})
        elif unquote(urlsplit(canonical[0]).path).rstrip('/') != own_path.rstrip('/'):
            metadata.append({'url': url, 'canonical': canonical[0]})
        for link in doc.xpath('//a[@href]'):
            raw = link.get('href', '')
            resolved = urlsplit(urljoin(url, raw))
            if resolved.scheme not in ('http', 'https') or resolved.hostname not in ('wawa-center.kr', 'www.wawa-center.kr'):
                continue
            path = unquote(resolved.path)
            fragment = unquote(resolved.fragment)
            counters['internalLinkOccurrences'] += 1
            unique.add(path)
            dest = local_target(path)
            if dest is None:
                broken.append({'source': own_path, 'href': raw, 'target': path, 'label': link.text_content().strip()[:100]})
            elif fragment and not fragment.startswith(':~:text=') and dest.suffix == '.html':
                cross.append((file, dest, fragment, raw))
            if path.startswith('/center/') and path.strip('/').split('/')[-1] in COURSES and OLD.search(link.text_content()):
                stale.append({'source': own_path, 'href': raw, 'label': link.text_content().strip()})
        if index % 3000 == 0:
            print(f'Audited {index}/{len(rows)} pages', flush=True)
    missing_fragments = []
    for source, target, fragment, href in cross:
        if target not in ids:
            doc = html.fromstring(target.read_bytes())
            ids[target] = set(doc.xpath('//@id')) | set(doc.xpath('//a/@name'))
        # Text-fragment suffix does not change the element fragment.
        element_id = fragment.split(':~:text=')[0]
        if element_id and element_id not in ids[target]:
            missing_fragments.append({'source': source.relative_to(ROOT).as_posix(), 'href': href,
                                      'target': target.relative_to(ROOT).as_posix(), 'fragment': element_id})
    report = {'pages': len(rows), **counters, 'uniqueInternalTargets': len(unique),
              'fragmentLinks': len(cross), 'brokenPages': broken, 'missingFragments': missing_fragments,
              'staleCourseLabels': stale, 'metadataErrors': metadata}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'internal-links.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(broken or missing_fragments or stale or metadata))


if __name__ == '__main__':
    main()
