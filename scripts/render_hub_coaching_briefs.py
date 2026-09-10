"""Scoped, repeatable hub summaries on the approved 2026-09-11 public baseline.

Never regenerate the locality pages. Refuse overlapping edits; manuscript JSON
is data only. Rendering twice produces identical bytes.
"""
import json
import re
import subprocess
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '9df4d54785a69304919f40f9c430710f12a19431'
ORIGIN = 'https://wawa-center.kr'
DATE = '2026-09-11'
DATA_FILE = ROOT / 'scripts/data/hub-coaching-briefs-20260911.json'
CSS_HREF = '/assets/hub-coaching-brief.css?v=20260911'
NOTE = 'AI 프로그램과 수업 운영은 센터별 상담에서 확인해 주세요.'
SCRIPT_RE = re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)', re.S | re.I)
ASIDE_RE = re.compile(r'<aside class="(?:math|subject)-hero-panel">.*?</aside>', re.S)
MARKER = '<!-- wawa-hub-coaching:start -->'
BRIEF_RE = re.compile(r'<!-- wawa-hub-coaching:start -->.*?<!-- wawa-hub-coaching:end -->', re.S)
OLD_FAQ = '전국센터는 지역과 센터를 기준으로 찾는 구조이고, 과목별학원은 단과·학년별 영수·전문학원 분류를 먼저 선택한 뒤 해당 동네의 학습 안내를 확인하는 구조입니다.'
CORRECT_FAQ = '전국센터는 지역과 센터를 기준으로 찾는 구조이고, 과목별학원은 단과·학년별 영수·영어수학·전문·내신·근처 학원 찾기 분류를 먼저 선택한 뒤 해당 동네의 학습 안내를 확인하는 구조입니다.'


def baseline(path):
    return subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT).decode('utf-8-sig')


def copies():
    items = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    prior = json.loads((ROOT / 'scripts/data/hub-copy-20260910.json').read_text(encoding='utf-8-sig'))
    assert len(items) == 35 and set(items) == set(prior)
    assert len({v['title'] for v in items.values()}) == 35
    assert len({v['summary'] for v in items.values()}) == 35
    for route, item in items.items():
        assert 70 <= len(item['summary']) <= 165, (route, len(item['summary']))
        assert len(item['title']) <= 34 and len(item['links']) == 2
        for href, label in item['links']:
            parsed = urlsplit(href)
            assert parsed.path == '/overview/' and parsed.fragment
            assert f'id="{parsed.fragment}"' in (ROOT / 'overview/index.html').read_text(encoding='utf-8')
            assert 2 <= len(label) <= 7
    assert 'id="wawa-videos"' in (ROOT / 'index.html').read_text(encoding='utf-8')
    return items


def render_brief(item):
    links = item['links'] + [['/#wawa-videos', '수업 영상']]
    return '\n'.join([
        MARKER,
        '<aside class="wawa-brief" id="hub-coaching" aria-labelledby="hub-coaching-title">',
        '<div class="wcb-copy">',
        f'<h2 id="hub-coaching-title">{escape(item["title"])}</h2>',
        f'<p class="wcb-summary">{escape(item["summary"])}</p>',
        '</div>',
        '<nav class="wcb-links" aria-label="코칭과 AI 학습 상세 안내">',
        *[f'<a href="{escape(href)}">{escape(label)}</a>' for href, label in links],
        '</nav>',
        f'<p class="wcb-note">{escape(NOTE)}</p>',
        '</aside>',
        '<!-- wawa-hub-coaching:end -->',
    ])


def render_page(route, item):
    path = route.strip('/') + '/index.html'
    text = baseline(path)
    assert MARKER not in text and 'id="hub-coaching"' not in text
    html = render_brief(item)
    if route == '/center/':
        hero = re.search(r'<section class="center-hero">.*?</section>', text, re.S)
        assert hero
        text = text[:hero.end()-len('</section>')] + html + text[hero.end()-len('</section>'):]
    else:
        text, count = ASIDE_RE.subn(lambda _: html, text)
        assert count == 1, (route, count)
    if route == '/과목별학원/':
        assert text.count('<p>'+OLD_FAQ+'</p>') == 1
        text = text.replace('<p>'+OLD_FAQ+'</p>', '<p>'+CORRECT_FAQ+'</p>')
    assert text.count('</head>') == 1
    text = text.replace('</head>', f'<link rel="stylesheet" href="{CSS_HREF}">\n</head>', 1)
    docs = [json.loads(m[2]) for m in SCRIPT_RE.finditer(text)]
    owners = [(doc, node) for doc in docs for node in doc.get('@graph', [doc]) if node.get('@type') == 'CollectionPage']
    assert len(owners) == 1
    owner, page = owners[0]
    assert '@graph' in owner
    page_url = page.get('url', page['@id'].split('#')[0])
    assert unquote(page_url) == ORIGIN + route
    element_id = page_url + '#hub-coaching'
    parts = page.get('hasPart', [])
    if not isinstance(parts, list):
        parts = [parts]
    assert not any(p.get('@id') == element_id for p in parts)
    page['hasPart'] = parts + [{'@id': element_id}]
    page['dateModified'] = DATE
    owner['@graph'].append({
        '@type': 'WebPageElement', '@id': element_id,
        'name': item['title'], 'text': item['summary'] + '\n' + NOTE,
        'isPartOf': {'@id': page['@id']},
        'url': element_id,
    })
    iterator = iter(docs)
    text = SCRIPT_RE.sub(lambda m: m[1] + json.dumps(next(iterator), ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c') + m[3], text)
    return path, text


def render_sitemap(items):
    text = baseline('sitemap.xml')
    seen = set()
    def replace(m):
        route = unquote(re.search(r'<loc>(.*?)</loc>', m[0])[1].removeprefix(ORIGIN))
        if route not in items:
            return m[0]
        assert route not in seen and '<lastmod>' in m[0]
        seen.add(route)
        return re.sub(r'<lastmod>.*?</lastmod>', f'<lastmod>{DATE}</lastmod>', m[0])
    text = re.sub(r'<url>.*?</url>', replace, text, flags=re.S)
    assert seen == set(items)
    return text


def is_own_previous_render(current, original, route):
    """Allow updates to our generated area, never overwrite other edits."""
    if len(BRIEF_RE.findall(current)) != 1:
        return False
    prior_aside = '' if route == '/center/' else ASIDE_RE.search(original)[0]
    restored = BRIEF_RE.sub(lambda _: prior_aside, current)
    restored = restored.replace(f'<link rel="stylesheet" href="{CSS_HREF}">\n', '')
    if route == '/과목별학원/':
        restored = restored.replace('<p>'+CORRECT_FAQ+'</p>', '<p>'+OLD_FAQ+'</p>')
    current_docs = [json.loads(m[2]) for m in SCRIPT_RE.finditer(restored)]
    old_docs = [json.loads(m[2]) for m in SCRIPT_RE.finditer(original)]
    for doc in current_docs:
        for page in doc.get('@graph', [doc]):
            if page.get('@type') != 'CollectionPage': continue
            page_url = page.get('url', page['@id'].split('#')[0])
            element_id = page_url + '#hub-coaching'
            if page.get('dateModified') != DATE: return False
            old_page = next(n for d in old_docs for n in d.get('@graph',[d]) if n.get('@id') == page['@id'])
            page['dateModified'] = old_page['dateModified']
            page['hasPart'] = [n for n in page['hasPart'] if n.get('@id') != element_id]
            doc['@graph'] = [n for n in doc['@graph'] if n.get('@id') != element_id]
    return current_docs == old_docs and SCRIPT_RE.sub('', restored) == SCRIPT_RE.sub('', original)


def main():
    items = copies()
    outputs = dict(render_page(route, item) for route, item in items.items())
    outputs['sitemap.xml'] = render_sitemap(items)
    # Validate the entire write set before changing any file.
    for path, generated in outputs.items():
        current = (ROOT / path).read_text(encoding='utf-8-sig')
        original = baseline(path).replace('\r\n', '\n')
        safe = current in (original, generated)
        if not safe and path.endswith('/index.html'):
            safe = is_own_previous_render(current, original, '/'+path.removesuffix('index.html'))
        assert safe, f'Overlapping edit: {path}'
    for path, generated in outputs.items():
        (ROOT / path).write_bytes(generated.encode('utf-8'))
    print(json.dumps({'hubs': len(items), 'summary_links': len(items)*3, 'new_images': 0, 'new_javascript': 0, 'sitemap_dates': len(items)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
