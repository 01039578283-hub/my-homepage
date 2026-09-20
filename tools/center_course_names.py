"""Rename legacy /center/ course labels without changing URLs or school facts.

Only public /center/ copy, links targeting /center/, and structured-data nodes
for those destinations are eligible. Other route families keep their own names.
HTML is patched by offsets, not reserialized. This is a finalizer for old CSV
generators, which must not be rerun merely to rename existing published pages.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

DOMAIN = 'https://wawa-center.kr'
NAMES = {'초등': '초등학생', '중등': '중학생', '고등': '고등학생'}
OLD = re.compile(r'(초등|중등|고등)(\s*)(영어|수학)(\s*)학원')
NEW = re.compile(r'(초등학생|중학생|고등학생)(\s*)(영어|수학)(\s*)학원')
COURSES = {'elementaryenglish', 'elementarymath', 'middleschoolenglish',
           'middleschoolmath', 'highschoolenglish', 'highschoolmath'}
ATTR = re.compile(r'(?P<name>[^\s=<>/]+)\s*=\s*(?P<quote>[\x22\x27])(?P<value>.*?)(?P=quote)', re.S)
LABEL_ATTRS = {'alt', 'title', 'aria-label', 'data-search', 'data-title', 'data-keywords'}
META = {'description', 'keywords', 'og:title', 'og:description', 'twitter:title', 'twitter:description'}


def rename(value: str) -> str:
    return OLD.sub(lambda m: NAMES[m[1]] + m[2] + m[3] + m[4] + '학원', value)


def mask(value: str) -> str:
    """For preservation audits: the only permitted semantic change is naming."""
    return NEW.sub(lambda m: {v: k for k, v in NAMES.items()}[m[1]] + m[2] + m[3] + m[4] + '학원', value)


def center_url(value: str, base: str) -> bool:
    url = urlsplit(urljoin(base, value))
    return url.hostname in ('wawa-center.kr', 'www.wawa-center.kr') and url.path.startswith('/center/')


def json_names(value, base, active, key=''):
    if isinstance(value, dict):
        destination = value.get('url') or value.get('@id') or value.get('item')
        if isinstance(destination, dict):
            destination = destination.get('@id') or destination.get('url')
        if isinstance(destination, str):
            active = center_url(destination, base)
        return {k: json_names(v, base, active, k) for k, v in value.items()}
    if isinstance(value, list):
        return [json_names(v, base, active, key) for v in value]
    if isinstance(value, str) and active:
        if key in {'@id', '@context', '@type', 'url', 'item', 'image', 'contentUrl', 'embedUrl', 'sameAs'}:
            return value
        if value.startswith(('https:', 'http:', '/', '#')):
            return value
        return rename(value)
    return value


class NameParser(HTMLParser):
    def __init__(self, raw, base):
        super().__init__(convert_charrefs=False)
        self.raw, self.base = raw, base
        self.own = center_url(base, base)
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer('\n', raw))
        self.edits = []
        self.anchor = None
        self.script = None
        self.in_style = False

    def source_position(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def add(self, start, old, new):
        if old != new:
            assert self.raw[start:start + len(old)] == old
            self.edits.append((start, start + len(old), new))

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == 'a':
            self.anchor = center_url(data.get('href', ''), self.base) if data.get('href') else self.own
        if tag == 'script':
            self.script = data.get('type', '').lower() == 'application/ld+json'
        if tag == 'style':
            self.in_style = True
        active = self.anchor if self.anchor is not None else self.own
        raw_tag, start = self.get_starttag_text(), self.source_position()
        for match in ATTR.finditer(raw_tag):
            name = match['name'].lower()
            eligible = active and name in LABEL_ATTRS
            if tag == 'meta' and name == 'content':
                eligible = self.own and (data.get('name') or data.get('property') or '').lower() in META
            if eligible:
                self.add(start + match.start('value'), match['value'], rename(match['value']))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor = None
        elif tag == 'script':
            self.script = None
        elif tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if self.script is not None:
            if self.script:
                before = json.loads(data)
                after = json_names(before, self.base, self.own)
                if before != after:
                    self.add(self.source_position(), data, json.dumps(after, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
            return
        if self.in_style:
            return
        if self.anchor if self.anchor is not None else self.own:
            self.add(self.source_position(), data, rename(data))


def transform(raw: str, url: str) -> str:
    parser = NameParser(raw, url)
    parser.feed(raw)
    parser.close()
    result = raw
    end = len(raw)
    for start, stop, value in sorted(parser.edits, reverse=True):
        if stop > end:
            raise ValueError('overlapping edits')
        result = result[:start] + value + result[stop:]
        end = start
    return result
