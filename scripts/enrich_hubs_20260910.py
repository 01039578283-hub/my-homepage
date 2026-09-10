"""Enrich the 35 selected static hubs without regenerating locality pages.

Run from a clean deployed baseline. Re-running on this release is intentionally
rejected to avoid duplicating schema. Manuscript data has no execution authority.
"""
from pathlib import Path
from html import escape
from urllib.parse import unquote
import argparse
import json
import re

SCRIPT_RE = re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)', re.S | re.I)
BASE = 'https://wawa-center.kr'
DATE = '2026-09-10'

def raw_read(path):
    return path.read_bytes().decode('utf-8-sig')

def schema_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')

def project_centers(root):
    centers = []
    for locality in ['명일동', '송촌동', '수완동']:
        source = root / '과목별학원' / '고등수학학원' / locality / 'index.html'
        matches = []
        for script in SCRIPT_RE.finditer(raw_read(source)):
            data = json.loads(script[2])
            for node in data.get('@graph', [data]):
                if node.get('@type') == 'EducationalOrganization' and node.get('address'):
                    matches.append(node)
        assert len(matches) == 1, (source, len(matches))
        node = matches[0]
        projection = {'@type': 'EducationalOrganization'}
        for field in ['@id', 'name', 'url', 'address', 'identifier']:
            projection[field] = node[field]
        assert (root / unquote(node['url'].removeprefix(BASE)).strip('/') / 'index.html').exists()
        centers.append(projection)
    return centers

def render_content(item, centers):
    e = escape
    parts = ['<!-- wawa-hub-enrichment:start -->\n<div class="wawa-hub-content" data-hub-enrichment="2026-09-10">']
    parts.append('<section class="wh-section" id="wh-learning" aria-labelledby="wh-learning-title"><p class="wh-eyebrow">학습 안내</p><h2 id="wh-learning-title">학생에게 맞는 학습을 고르는 기준</h2><div class="wh-reading">')
    for section in item['sections']:
        parts.append(f'<article id="{e(section["id"])}"><h3>{e(section["title"])}</h3>')
        parts.extend(f'<p>{e(p)}</p>' for p in section['paragraphs'])
        parts.append('</article>')
    parts.append('</div><nav class="wh-read-links" aria-label="함께 읽을 학습 가이드">')
    for link in item['readLinks']:
        parts.append(f'<a href="{e(link["href"])}">{e(link["label"])}</a>')
    parts.append('</nav></section>')
    parts.append('<section class="wh-section" id="wh-centers" aria-labelledby="wh-centers-title"><p class="wh-eyebrow">지역별 센터 정보</p><h2 id="wh-centers-title">센터의 위치와 상세 안내도 함께 확인하세요</h2><p>서울·대전·광주의 센터 안내를 예시로 살펴볼 수 있습니다. 아래 주소와 등록정보를 확인한 뒤, 원하는 지역의 상세 페이지에서 안내를 이어 보세요. 학생의 과목·학년에 맞는 수업과 현재 상담 가능한 일정은 센터별로 확인해 주세요.</p><div class="wh-center-grid">')
    for center in centers:
        path = center['url'].removeprefix(BASE)
        parts.append(f'<article class="wh-center-card"><h3>{e(center["name"])}</h3><p>{e(center["address"]["streetAddress"])}</p><p class="wh-registration">{e(center["identifier"]["value"])}</p><a href="{e(path)}">{e(center["name"].split()[-1])} 상세 안내</a></article>')
    parts.append(f'</div><div class="wh-photo-grid"><figure><img src="/assets/hub-reading/study-desks.webp" width="500" height="300" loading="lazy" decoding="async" alt="{e(item["label"])} 안내에 사용한 공통 학습 공간 예시"><figcaption>공통 학습 공간 예시 · 특정 센터의 실제 시설을 뜻하지 않습니다.</figcaption></figure><figure><img src="/assets/hub-reading/classroom.webp" width="800" height="600" loading="lazy" decoding="async" alt="{e(item["label"])} 안내에 사용한 공통 교실 예시"><figcaption>공통 교실 예시 · 방문할 센터의 공간은 상담 시 확인해 주세요.</figcaption></figure></div></section>')
    parts.append('<section class="wh-section wh-faq" id="wh-questions" aria-labelledby="wh-questions-title"><p class="wh-eyebrow">학습 선택 Q&amp;A</p><h2 id="wh-questions-title">학습을 선택하기 전 더 궁금한 점</h2>')
    for faq in item['faqs']:
        parts.append(f'<details><summary>{e(faq["question"])}</summary><p>{e(faq["answer"])}</p></details>')
    parts.append('</section></div>\n<!-- wawa-hub-enrichment:end -->\n')
    return '\n'.join(parts)

def enrich(root, copies):
    assert len(copies) == 35
    centers = project_centers(root)
    for route, item in copies.items():
        assert route.startswith(('/과목별학원/', '/학년별학원/', '/center/')) and route.endswith('/')
        assert len(item['sections']) == 3 and len(item['faqs']) == 4 and len(item['readLinks']) == 2
        path = root / route.strip('/') / 'index.html'
        raw = raw_read(path)
        assert 'wawa-hub-enrichment:start' not in raw, f'Already enriched: {route}'
        ids = set(re.findall(r'\bid=["\']([^"\']+)', raw))
        for section in item['sections']:
            assert re.fullmatch(r'[a-z][a-z0-9-]+', section['id'])
            assert section['id'] not in ids
            ids.add(section['id'])
            assert len(section['paragraphs']) == 2
        for link in item['readLinks']:
            assert link['href'].startswith('/guide/')
            assert (root / link['href'].strip('/') / 'index.html').exists(), link
        docs = [json.loads(m[2]) for m in SCRIPT_RE.finditer(raw)]
        graphs = [doc.get('@graph', [doc]) for doc in docs]
        all_nodes = [n for nodes in graphs for n in nodes]
        pages = [n for n in all_nodes if n.get('@type') == 'CollectionPage']
        assert len(pages) == 1, route
        page = pages[0]
        page_url = page.get('url', page['@id'].split('#')[0])
        assert unquote(page_url) == BASE + route, (route, page_url)
        new_elements = [{'@type': 'WebPageElement', '@id': page_url + '#' + s['id'], 'name': s['title'], 'text': '\n'.join(s['paragraphs']), 'isPartOf': {'@id': page['@id']}} for s in item['sections']]
        for field, additions in [('hasPart', [{'@id': n['@id']} for n in new_elements]), ('mentions', [{'@id': n['@id']} for n in centers])]:
            current = page.get(field, [])
            if not isinstance(current, list):
                current = [current]
            page[field] = current + [n for n in additions if n not in current]
        page['dateModified'] = DATE
        faq_nodes = [n for n in all_nodes if n.get('@type') == 'FAQPage']
        assert len(faq_nodes) <= 1
        questions = [{'@type': 'Question', 'name': f['question'], 'acceptedAnswer': {'@type': 'Answer', 'text': f['answer']}} for f in item['faqs']]
        graph_index = next(i for i, nodes in enumerate(graphs) if page in nodes)
        owner = docs[graph_index]
        assert '@graph' in owner
        if faq_nodes:
            old_q = faq_nodes[0].get('mainEntity', [])
            assert isinstance(old_q, list)
            assert not {q['name'] for q in old_q}.intersection(q['name'] for q in questions)
            faq_nodes[0]['mainEntity'] = old_q + questions
        else:
            owner['@graph'].append({'@type': 'FAQPage', '@id': page_url + '#wh-questions', 'isPartOf': {'@id': page['@id']}, 'mainEntity': questions})
        owner['@graph'].extend(new_elements)
        known_ids = {n.get('@id') for n in all_nodes}
        owner['@graph'].extend(n for n in centers if n['@id'] not in known_ids)
        iterator = iter(docs)
        raw = SCRIPT_RE.sub(lambda m: m[1] + schema_json(next(iterator)) + m[3], raw)
        def mark_body(match):
            tag = match[0]
            if re.search(r'\bclass=["\']', tag):
                return re.sub(r'(\bclass=["\'])([^"\']*)', lambda c: c[1] + c[2] + ' wawa-hub-page', tag, count=1)
            return tag[:-1] + ' class="wawa-hub-page">'
        raw = re.sub(r'<body\b[^>]*>', mark_body, raw, count=1)
        raw = raw.replace('</head>', '<link rel="stylesheet" href="/assets/hub-enrichment.css?v=20260910">\n</head>', 1)
        hero = re.search(r'<main\b[^>]*>.*?</section>', raw, re.S)
        assert hero is not None
        jump = '\n<nav class="wawa-hub-jump" aria-label="추가 학습 안내 바로가기"><a href="#wh-learning">학습 선택 기준</a><a href="#wh-centers">센터 정보</a><a href="#wh-questions">학습 Q&amp;A</a></nav>\n'
        raw = raw[:hero.end()] + jump + raw[hero.end():]
        assert raw.count('</main>') == 1
        raw = raw.replace('</main>', render_content(item, centers) + '</main>', 1)
        if route == '/과목별학원/고등수학학원/':
            old_link = '<a href="/교육정보/수학-단어-암기법/">단어 암기법</a>'
            assert raw.count(old_link) == 1
            raw = raw.replace(old_link, '<a href="/guide/highschool-math-study/">고등 수학 공부법</a>')
        path.write_bytes(raw.encode('utf-8'))
    sitemap = root / 'sitemap.xml'
    text = raw_read(sitemap)
    changed = set()
    def update_entry(match):
        block = match[0]
        loc = re.search(r'<loc>(.*?)</loc>', block)[1]
        route = unquote(loc.removeprefix(BASE))
        if route not in copies:
            return block
        assert route not in changed
        changed.add(route)
        assert '<lastmod>' in block
        return re.sub(r'<lastmod>.*?</lastmod>', f'<lastmod>{DATE}</lastmod>', block)
    text = re.sub(r'<url>.*?</url>', update_entry, text, flags=re.S)
    assert changed == set(copies), sorted(set(copies) - changed)
    sitemap.write_bytes(text.encode('utf-8'))
    print(json.dumps({'hubs': len(copies), 'reading_sections': len(copies)*3, 'additional_faqs': len(copies)*4, 'guide_links': len(copies)*2, 'confirmed_center_examples': len(centers), 'sitemap_dates': len(changed)}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--data', type=Path, required=True)
    args = parser.parse_args()
    enrich(args.root.resolve(), json.loads(args.data.read_text(encoding='utf-8-sig')))
