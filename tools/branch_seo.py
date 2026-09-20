"""Stable publication history and fact-preserving branch metadata.

Dates describe content, not build time. Social tags, JSON serialization, the
shared navigation and the date display itself cannot make an article newer.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from html import escape
from pathlib import Path

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
DATE_FILE = Path('tools/data/branch-directory/page-dates.json')
GRAPH = re.compile(r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)', re.S)
DATE_BLOCK = re.compile(r'<p class="branch-page-dates"[^>]*>.*?</p>\s*', re.S)
_stores = {}


def text(node):
    return re.sub(r'\s+', ' ', ' '.join(node.itertext()), flags=re.S).strip()


def content_hash(raw):
    """Hash reader-facing content, not cosmetic markup or schema boilerplate."""
    doc = html.fromstring(DATE_BLOCK.sub('', raw))
    main = doc.xpath('//main')
    if len(main) != 1:
        raise ValueError('Expected one main for dated branch content')
    for n in main[0].xpath('.//script | .//style'):
        n.drop_tree()
    payload = {
        'title': doc.xpath('//title/text()'),
        'description': doc.xpath('//meta[@name="description"]/@content'),
        'content': text(main[0]),
        'links': main[0].xpath('.//a/@href'),
        'images': [(n.get('src'), n.get('alt')) for n in main[0].xpath('.//img')],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class PageDates:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        file = self.root / DATE_FILE
        self.records = json.loads(file.read_text(encoding='utf-8'))['pages'] if file.exists() else {}

    def seed(self, path, raw, fallback):
        if path in self.records:
            return
        nodes = json.loads(GRAPH.search(raw)[2])['@graph']
        article = next((n for n in nodes if n.get('@type') == 'Article'), {})
        published = article.get('datePublished') or fallback
        modified = article.get('dateModified') or fallback
        date.fromisoformat(published)
        date.fromisoformat(modified)
        self.records[path] = {'datePublished': published, 'dateModified': modified, 'contentHash': content_hash(raw)}

    def resolve(self, path, raw, today=None):
        today = today or date.today().isoformat()
        date.fromisoformat(today)
        if path not in self.records:
            existing = self.root / path.strip('/') / 'index.html'
            if existing.exists():
                # An existing page without publication evidence must be seeded
                # explicitly, never relabeled as first published today.
                raise ValueError(f'Missing publication history; seed before regeneration: {path}')
            self.seed(path, raw, today)
        record = self.records[path]
        fingerprint = content_hash(raw)
        if fingerprint != record['contentHash']:
            if today < record['dateModified']:
                raise ValueError(f'Cannot move modification date backwards: {path}')
            record['dateModified'] = today
            record['contentHash'] = fingerprint
        return record

    def dates(self, path):
        record = self.records.get(path)
        if not record:
            return {'datePublished': date.today().isoformat(), 'dateModified': date.today().isoformat()}
        return {key: record[key] for key in ('datePublished', 'dateModified')}

    def save(self):
        file = self.root / DATE_FILE
        file.parent.mkdir(parents=True, exist_ok=True)
        data = {'version': 1, 'policy': 'Preserve first publication; update modified only on reader-facing content change. Source review dates are independent.', 'pages': dict(sorted(self.records.items()))}
        rendered = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if not file.exists() or file.read_text(encoding='utf-8') != rendered:
            file.write_text(rendered, encoding='utf-8')


def date_store(root=ROOT):
    key = str(Path(root).resolve())
    if key not in _stores:
        _stores[key] = PageDates(root)
    return _stores[key]


def page_dates(path, root=ROOT):
    return date_store(root).dates(path)


def save_dates(root=ROOT):
    date_store(root).save()


def set_meta(raw, key, value, attribute='name'):
    pattern = re.compile(rf'<meta\b(?=[^>]*\b{attribute}="{re.escape(key)}")[^>]*>', re.I)
    tag = f'<meta {attribute}="{key}" content="{escape(value, quote=True)}">'
    matches = list(pattern.finditer(raw))
    if len(matches) > 1:
        raise ValueError(f'Duplicate meta: {key}')
    if matches:
        return pattern.sub(lambda _: tag, raw)
    return raw.replace('</head>', tag + '\n</head>', 1)


def fix_parts(nodes):
    """A visible section is a CreativeWork; its ItemList is a separate entity."""
    for node in nodes:
        if node.get('@type') != 'ItemList' or not node.get('@id', '').endswith('#learning-pages'):
            continue
        old_id = node['@id']
        node['@id'] = old_id + '-list'
        for page in nodes:
            if page.get('@type') not in ('WebPage', 'CollectionPage'):
                continue
            page['hasPart'] = [
                {'@type': 'WebPageElement', '@id': old_id, 'name': node['name'], 'mainEntity': {'@id': node['@id']}}
                if part.get('@id') == old_id else part
                for part in page.get('hasPart', [])
            ]


def finalize_page(raw, path, *, description=None, store=None, today=None):
    store = store or date_store()
    if description is not None:
        raw = set_meta(raw, 'description', description)
        raw = set_meta(raw, 'og:description', description, 'property')
    doc = html.fromstring(raw)
    title = text(doc.xpath('//title')[0])
    meta_description = doc.xpath('//meta[@name="description"]/@content')[0]
    image = doc.xpath('//meta[@property="og:image"]/@content')[0]
    for key, value in [('twitter:card','summary_large_image'), ('twitter:title',title), ('twitter:description',meta_description), ('twitter:image',image)]:
        raw = set_meta(raw, key, value)
    matches = list(GRAPH.finditer(raw))
    if len(matches) != 1:
        raise ValueError(f'Expected a single branch graph: {path}')
    match = matches[0]
    payload = json.loads(match[2])
    nodes = payload['@graph']
    fix_parts(nodes)
    dates = store.resolve(path, raw, today)
    for node in nodes:
        if node.get('@type') in ('WebPage','CollectionPage','Article'):
            for key in ('datePublished','dateModified'):
                node[key] = dates[key]
            if description is not None:
                node['description'] = description
    raw = raw[:match.start(2)] + json.dumps(payload,ensure_ascii=False,separators=(',',':')) + raw[match.end(2):]
    raw = DATE_BLOCK.sub('', raw)
    # A small, wrapping date line keeps verification of center facts separate.
    block = '<p class="branch-page-dates"><span>최초 게시 <time datetime="{0}">{0}</time></span><span>최종 수정 <time datetime="{1}">{1}</time></span></p>'.format(dates['datePublished'],dates['dateModified'])
    raw = raw.replace('</main>', block + '\n</main>', 1)
    raw = re.sub(r'(/assets/branch-directory\.css)(?:\?[^"\s]*)?', r'\1?v=20260921-seo', raw)
    return raw


def checked_source_date(center):
    """This is a reviewed-source date, never the current build date."""
    from branch_course_guidance import rules_data
    result = center.get('informationReviewedAt') or rules_data()['reviewedAt']
    date.fromisoformat(result)
    return result
