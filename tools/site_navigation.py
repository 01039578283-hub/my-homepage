"""One crawlable, server-rendered navigation contract for every public page.

No client-side fetch or framework is needed for the menu. The refresh command
applies this same renderer to older static templates after page generation.
"""
from __future__ import annotations

import re
from html import escape
from urllib.parse import unquote, urlsplit

NAV = (("홈", "/"), ("학원소개", "/overview/"), ("학습가이드", "/guide/"),
       ("교육정보", "/교육정보/"), ("학부모후기", "/학부모후기/"),
       ("과목별학원", "/과목별학원/"), ("학년별학원", "/학년별학원/"),
       ("전국센터", "/center/"), ("지점안내", "/지점안내/"))
HEADER_STYLE = '/assets/header.css?v=20260920-nav1'
FONT_URL = ('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700'
            '&family=Noto+Sans+KR:wght@400;500;700;900&display=swap')
FONT_BLOCK = ('<!-- shared-site-fonts:start -->\n'
              '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
              f'<link rel="stylesheet" href="{escape(FONT_URL, quote=True)}">\n'
              '<!-- shared-site-fonts:end -->\n')
HEADER_RE = re.compile(r'<header\b(?=[^>]*\bclass=["\'][^"\']*\bsite-header\b)[^>]*>.*?</header>', re.S | re.I)


def active_section(path):
    route = unquote(urlsplit(path).path)
    if not route.startswith('/'):
        route = '/' + route
    if route.endswith('index.html'):
        route = route[:-10]
    for _, href in NAV[1:]:
        if route == href.rstrip('/') or route.startswith(href):
            return href
    return '/'


def render_header(path):
    active = active_section(path)
    links = ''.join(f'<a href="{href}"' + (' class="active" aria-current="page"' if href == active else '')
                    + f'>{label}</a>' for label, href in NAV)
    return ('<header class="site-header" data-site-navigation="unified"><nav class="nav" aria-label="주요 메뉴">'
            '<a class="logo" href="/" aria-label="와와학습코칭센터 홈"><span class="brand-orange">와와</span>학습'
            '<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a>'
            f'<div class="nav-links" aria-label="페이지 이동">{links}</div></nav></header>')


def unify_header(raw, path):
    if len(HEADER_RE.findall(raw)) != 1:
        raise ValueError(f'{path}: expected exactly one public site header')
    raw = HEADER_RE.sub(lambda _: render_header(path), raw, count=1)
    # Older pages use ../assets/header.css or an unversioned root-relative URL.
    links = list(re.finditer(r'<link\b[^>]*>', raw, re.I))
    header_links = [m for m in links if re.search(r'href=["\'][^"\']*\bassets/header\.css(?:\?[^"\']*)?["\']', m[0])]
    if len(header_links) != 1:
        raise ValueError(f'{path}: expected one shared header stylesheet')
    match = header_links[0]
    raw = raw[:match.start()] + f'<link rel="stylesheet" href="{HEADER_STYLE}">' + raw[match.end():]
    # A single early font stylesheet replaces repeated nested CSS @imports.
    raw = re.sub(r'<!-- shared-site-fonts:start -->.*?<!-- shared-site-fonts:end -->\s*', '', raw, flags=re.S)
    first_style = re.search(r'<(?:link\b[^>]*rel=["\']stylesheet["\']|style\b)', raw, re.I)
    if first_style is None:
        raise ValueError(f'{path}: no stylesheet insertion point')
    raw = raw[:first_style.start()] + FONT_BLOCK + raw[first_style.start():]
    return raw
