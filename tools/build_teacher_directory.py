"""Build a source-bounded teacher directory and additive, verified site links.

The owner approved shared introduction images, not name-to-portrait matching.
Input workbooks and image bytes remain unchanged. Excluded branch brands stay
excluded. Unmatched ordinary branch names get no inferred region or address.
"""
import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from lxml import etree, html

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://wawa-center.kr'
DATE = '2026-10-02'
SOURCE = ROOT / 'tools/teacher-profiles-source.json'
INPUT = Path('C:/Users/1992k/Desktop/홈페이지 작업 폴더/교사 프로필')
TEACHER_PATH = '/선생님찾기/'
NAV = '<a href="/%EC%84%A0%EC%83%9D%EB%8B%98%EC%B0%BE%EA%B8%B0/" data-teacher-navigation>선생님찾기</a>'
START, END = '<!-- teacher-links:start -->', '<!-- teacher-links:end -->'
REGIONS = ['서울', '경기', '인천', '부산', '대구', '광주', '대전', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
REGION_SLUG = dict(zip(['seoul', 'gyeonggi', 'incheon', 'busan', 'daegu', 'gwangju', 'daejeon', 'ulsan', 'sejong', 'gangwon', 'chungbuk', 'chungnam', 'jeonbuk', 'jeonnam', 'gyeongbuk', 'gyeongnam', 'jeju'], REGIONS))
EXCLUDED = {'다산점(W+)', '둔산점(W+)', '송도점(W+)', '수지점(W+)', '은평점(W+)', '중동점(W+)', '화정점(W+)', '후곡점(W+)', '수지점(글로리드)', '은평점(글로리드)', '대구역점2호관'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def enc(path):
    return quote(path, safe='/-#')


def esc(value):
    return escape(str(value), quote=True)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def import_source():
    from openpyxl import load_workbook
    from PIL import Image
    workbook = INPUT / '교사 프로필.xlsx'
    rows = list(load_workbook(workbook, read_only=True, data_only=True).active.values)
    assert len(rows) == 1002 and all(len(r) == 4 and all(isinstance(v, str) and v.strip() for v in r) for r in rows)
    records = []
    for number, row in enumerate(rows, 1):
        branch, name, approach, introduction = [v.strip() for v in row]
        assert '*' in name and introduction.startswith(branch + ' ' + name + ' 선생님입니다.'), number
        records.append({'sourceRow': number, 'branch': branch, 'name': name, 'approach': approach, 'introduction': introduction})
    photos = []
    # Supplied small portraits keep the directory light without editing images.
    for photo in sorted(INPUT.glob('collage-profile-*.png')):
        raw = photo.read_bytes()
        width, height = Image.open(photo).size
        photos.append({'file': photo.name, 'sha256': digest(raw), 'width': width, 'height': height})
    assert len(photos) == 12 and len({p['sha256'] for p in photos}) == 12
    save_json(SOURCE, {'workbook': workbook.name, 'workbookSha256': digest(workbook.read_bytes()), 'photoUse': 'owner-approved shared introduction images', 'records': records, 'photos': photos})


def catalog():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    centers = json.loads((ROOT / 'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    by_name = {c['sourceName']: c for c in centers}
    assert len(by_name) == len(centers)
    grouped = defaultdict(list)
    excluded = []
    for record in source['records']:
        if record['branch'] in EXCLUDED:
            excluded.append(record)
        else:
            grouped[record['branch']].append(dict(record))
    result = []
    for name, records in grouped.items():
        center = by_name.get(name)
        region = center['region'] if center else ''
        route = center['routeName'] if center else name
        path = TEACHER_PATH + ((region + '/') if region else '') + route + '/'
        seed = int(digest(name.encode('utf-8'))[:8], 16) % len(source['photos'])
        # A branch-local permutation gives every record a different source file.
        assert len(records) <= len(source['photos'])
        for index, record in enumerate(records):
            record['anchor'] = 'teacher-' + str(record['sourceRow'])
            record['photo'] = source['photos'][(seed + index) % len(source['photos'])]
        result.append({'name': name, 'region': region, 'routeName': route, 'path': path, 'center': center, 'records': records})
    result.sort(key=lambda b: (REGIONS.index(b['region']) if b['region'] in REGIONS else len(REGIONS), b['routeName']))
    return source, centers, result, excluded


def branch_url(branch):
    return '/지점안내/' + branch['region'] + '/' + branch['routeName'] + '/'


def related_for(name, document, branches, by_path):
    parts = name.split('/')
    if parts[0] == '지점안내' and len(parts) >= 4:
        found = by_path.get('/' + '/'.join(parts[:3]) + '/')
        return [found] if found else []
    if parts[0] not in ('center', '과목별학원', '학년별학원'):
        return []
    # Explicit current branch links are strongest. Do not use the global menu.
    direct = set()
    for href in document.xpath('//main//a/@href'):
        path = unquote(urlparse(href).path)
        path_parts = path.split('/')
        if path.startswith('/지점안내/') and len(path_parts) >= 5:
            match = by_path.get('/' + '/'.join(path_parts[1:4]) + '/')
            if match:
                direct.add(match['name'])
    if direct:
        return [b for b in branches if b['name'] in direct]
    # Legacy pages already describe a branch in their public organization data.
    # Require its exact name AND a neighborhood from that actual branch source.
    organizations, localities = [], set()
    for script in document.xpath('//script[@type="application/ld+json"]'):
        graph = json.loads(script.text or '{}')
        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                types = node.get('@type', [])
                types = [types] if isinstance(types, str) else types
                if 'EducationalOrganization' in types or 'LocalBusiness' in types:
                    organizations.append(node.get('name', ''))
                    areas = node.get('areaServed', [])
                    areas = [areas] if isinstance(areas, dict) else areas
                    for area in areas:
                        if isinstance(area, dict):
                            localities.add(area.get('name', ''))
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
        walk(graph)
    region = REGION_SLUG.get(parts[1]) if parts[0] == 'center' and len(parts) > 1 else None
    found = []
    for b in branches:
        center = b['center']
        if not center or (region and b['region'] != region):
            continue
        if not any(label == center['displayName'] or label.endswith(' ' + b['name']) or label.endswith(' ' + b['routeName']) for label in organizations):
            continue
        if not localities.intersection(center['neighborhoods']):
            continue
        found.append(b)
    # Names are matched within branch context; no teacher identity merging.
    return found


def add_navigation(text):
    if 'data-teacher-navigation' in text:
        return text
    def replace(match):
        return match.group(1) + match.group(2) + NAV + match.group(3)
    return re.sub(r'(<div class="nav-links"[^>]*>)(.*?)(</div>)', replace, text, count=1, flags=re.S)


def link_section(branches, is_branch):
    if not branches:
        return ''
    if is_branch and len(branches) == 1:
        b = branches[0]
        heading = b['routeName'] + ' 선생님 소개'
        text = '선생님이 학생의 질문과 풀이를 어떻게 살피는지 소개글에서 확인하고, 상담에서 물어볼 내용을 정리해 보세요.'
    else:
        heading = '이 동네를 안내하는 지점의 선생님'
        text = '학습 방법을 읽은 뒤, 관련 지점 선생님의 소개와 학생을 대하는 학습 방향도 함께 확인해 보세요.'
    links = ''.join('<a href="' + enc(b['path']) + '"><strong>' + esc(b['routeName']) + ' 선생님 소개</strong><span>' + str(len(b['records'])) + '개의 소개 · 질문과 학습을 살피는 방향</span></a>' for b in branches)
    return START + '<section class="teacher-related" aria-labelledby="teacher-related-title"><h2 id="teacher-related-title">' + esc(heading) + '</h2><p>' + text + '</p><div class="teacher-related-links">' + links + '</div></section>' + END


def head(title, description, path, graph):
    canonical = BASE + enc(path)
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical}"><link rel="icon" href="/assets/favicon.png">
<meta property="og:type" content="website"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="와와학습코칭센터">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&amp;family=Noto+Sans+KR:wght@400;500;700&amp;display=swap">
<link rel="stylesheet" href="/assets/header.css?v=20261002-teachers"><link rel="stylesheet" href="/assets/teacher-directory.css?v=20261002">
<script src="/assets/teacher-directory.js?v=20261002" defer></script>
<script type="application/ld+json">{json.dumps({'@context':'https://schema.org','@graph':graph}, ensure_ascii=False).replace('</', '<\\/')}</script>
<script defer src="https://wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js" data-site="wawa-01" crossorigin="anonymous" referrerpolicy="no-referrer"></script></head><body>
<a class="td-skip" href="#main-content">본문으로 바로 가기</a>'''


def page_schema(title, description, path, crumbs, items):
    canonical = BASE + enc(path)
    return [{'@type': 'CollectionPage', '@id': canonical + '#webpage', 'url': canonical, 'name': title, 'description': description, 'inLanguage': 'ko-KR', 'datePublished': DATE, 'dateModified': DATE, 'mainEntity': {'@id': canonical + '#list'}, 'breadcrumb': {'@id': canonical + '#breadcrumb'}},
            {'@type': 'BreadcrumbList', '@id': canonical + '#breadcrumb', 'itemListElement': [{'@type': 'ListItem', 'position': i, 'name': label, 'item': BASE + enc(href)} for i, (label, href) in enumerate(crumbs, 1)]},
            {'@type': 'ItemList', '@id': canonical + '#list', 'numberOfItems': len(items), 'itemListElement': [{'@type': 'ListItem', 'position': i, **item} for i, item in enumerate(items, 1)]}]


def breadcrumbs(crumbs):
    return '<nav class="td-breadcrumb" aria-label="현재 위치"><ol>' + ''.join('<li>' + ('<a href="' + enc(href) + '">' + esc(label) + '</a>' if i < len(crumbs)-1 else '<span aria-current="page">' + esc(label) + '</span>') + '</li>' for i, (label, href) in enumerate(crumbs)) + '</ol></nav>'


def footer():
    return '<footer class="td-footer"><strong>와와학습코칭센터</strong><p>상담 시 학생의 학년, 과목, 통학 가능한 지점을 함께 알려주세요.</p><p>김종범</p><a href="tel:01039578283">010-3957-8283</a></footer></body></html>\n'


def branch_card(branch):
    b = branch
    names = ' · '.join(r['name'] for r in b['records'])
    search = ' '.join([b['name'], b['region'], b['center']['district'] if b['center'] else ''] + (b['center']['neighborhoods'] if b['center'] else []) + [r['name'] + ' ' + r['approach'] for r in b['records']])
    themes = list(dict.fromkeys(part.strip() for r in b['records'] for part in r['approach'].split('/')))
    return f'''<article class="td-branch-card" data-branch-card data-region="{esc(b['region'])}" data-search="{esc(search)}"><p class="td-eyebrow">{esc(b['region'] + ' ' + b['center']['district'] if b['center'] else '지역 정보 확인 필요')}</p><h3><a href="{enc(b['path'])}">{esc(b['routeName'])} 선생님</a></h3><p class="td-card-count">소개 {len(b['records'])}개</p><p class="td-names">{esc(names)}</p><div class="td-tags">{''.join('<span>'+esc(t)+'</span>' for t in themes[:3])}</div><a class="td-card-link" href="{enc(b['path'])}">선생님 소개 읽기 <span aria-hidden="true">→</span></a></article>'''


def render_hub(branches, header):
    title = '선생님찾기 | 지점별 선생님 소개와 학습 방향'
    description = '지역과 지점별 선생님 소개를 찾아 학생의 질문과 학습을 살피는 방향을 확인하세요.'
    crumbs = [('홈', '/'), ('선생님찾기', TEACHER_PATH)]
    graph = page_schema(title, description, TEACHER_PATH, crumbs, [{'name': b['routeName'] + ' 선생님 소개', 'url': BASE + enc(b['path'])} for b in branches])
    regions = [r for r in REGIONS if any(b['region'] == r for b in branches)]
    options = '<option value="">전체 지역</option>' + ''.join('<option value="'+r+'">'+r+'</option>' for r in regions) + '<option value="unconfirmed">지역 확인 필요</option>'
    return (head(title, description, TEACHER_PATH, graph) + header + breadcrumbs(crumbs) + f'''<main class="td-shell" id="main-content"><section class="td-hero"><div><p class="td-eyebrow">TEACHER DIRECTORY</p><h1>우리 동네,<br>함께 배울 선생님</h1><p class="td-lead">지점별 선생님 소개를 읽고, 학생의 질문과 풀이를 어떻게 살피는지 알아보세요. 상담 전 학생에게 필요한 도움을 정리하는 데에도 활용할 수 있습니다.</p><a class="td-button" href="#teacher-directory">지점별 소개 찾기</a></div><aside class="td-hero-note"><span class="td-note-number">01</span><h2>학습 방향을 먼저 읽어보세요</h2><p>질문을 구체화하는 방법, 오답을 돌아보는 과정, 작은 목표를 실천하는 방향을 소개글에서 확인할 수 있습니다.</p><p>담당 과목·학년과 수업 일정은 지점 상담에서 확인해 주세요.</p></aside></section>
<section class="td-directory" id="teacher-directory" aria-labelledby="directory-title"><div class="td-section-head"><p class="td-eyebrow">FIND YOUR BRANCH</p><h2 id="directory-title">지점별 선생님찾기</h2><p>지점명, 동네, 가려진 선생님 이름, 학습 방향으로 찾아보세요.</p></div><form class="td-filters" data-teacher-filters role="search"><div><label for="teacher-region">지역</label><select id="teacher-region">{options}</select></div><div class="td-search-field"><label for="teacher-search">지점 · 동네 · 선생님 · 학습 방향</label><input id="teacher-search" type="search" placeholder="예: 하계동, 하계점, 오답" autocomplete="off"></div><button type="reset">초기화</button></form><p class="td-results" role="status" aria-live="polite" data-result-count>지점 {len(branches)}개 · 선생님 소개 {sum(len(b['records']) for b in branches)}개</p><p class="td-empty" data-empty hidden>조건에 맞는 지점이 없습니다. 검색어를 줄이거나 지역을 바꿔 보세요.</p><div class="td-branch-grid">{''.join(branch_card(b) for b in branches)}</div></section>
<section class="td-reading"><h2>소개를 읽은 뒤 준비할 상담 질문</h2><ol><li>학생이 어떤 문제에서 설명이나 질문을 어려워하는지 정리해 주세요.</li><li>현재 학년과 과목을 알려주고 담당 선생님과 수업 가능 여부를 확인해 주세요.</li><li>집에서 이어갈 활동과 수업에서 확인할 내용을 함께 물어보세요.</li></ol><a href="/guide/parent-consultation-checklist/">학부모 상담 체크리스트</a> <a href="/{enc('지점안내')}/">지점 주소와 수강 안내</a></section><p class="td-image-note">프로필 사진은 선생님 소개를 위한 공용 이미지이며, 실제 선생님 사진과 다를 수 있습니다.</p></main>''' + footer(), title, description)


def render_branch(b, header):
    title = b['routeName'] + ' 선생님 소개 | ' + ((b['region'] + ' ') if b['region'] else '') + '학습 방향'
    description = b['routeName'] + ' 선생님들의 소개와 학생의 질문, 풀이, 학습 습관을 살피는 방향을 확인하세요.'
    crumbs = [('홈', '/'), ('선생님찾기', TEACHER_PATH), (b['routeName'] + ' 선생님', b['path'])]
    graph = page_schema(title, description, b['path'], crumbs, [{'name': r['name'] + ' 선생님', 'url': BASE + enc(b['path']) + '#' + r['anchor'], 'description': r['introduction']} for r in b['records']])
    cards = []
    for r in b['records']:
        photo = r['photo']
        tags = ''.join('<span>' + esc(t.strip()) + '</span>' for t in r['approach'].split('/'))
        # Names, approaches and full introductions are exactly the source text.
        cards.append(f'''<article class="td-teacher-card" id="{r['anchor']}" aria-labelledby="{r['anchor']}-title"><figure><img src="/assets/teacher-directory/{photo['file']}" alt="선생님 소개용 공용 이미지" width="{photo['width']}" height="{photo['height']}" loading="lazy" decoding="async"><figcaption>소개용 이미지</figcaption></figure><div class="td-teacher-copy"><h2 id="{r['anchor']}-title">{esc(r['name'])} <span>선생님</span></h2><div class="td-tags">{tags}</div><p class="td-introduction">{esc(r['introduction'])}</p><a class="td-profile-anchor" href="#{r['anchor']}">이 소개 바로가기</a></div></article>''')
    if b['center']:
        c = b['center']
        location = f'''<section class="td-branch-context"><p class="td-eyebrow">BRANCH INFORMATION</p><h2>{esc(b['routeName'])} 방문 안내</h2><p>{esc(c['address'])}</p><a class="td-button" href="{enc(branch_url(b))}">지점 주소 · 과목별 수강 학년 확인</a><div class="td-local-links">{''.join('<a href="'+enc(branch_url(b)+locality+subject+'학원/')+'">'+esc(locality+' '+subject+' 학습 안내')+'</a>' for locality in c['neighborhoods'] for subject in ['수학','영어'])}</div></section>'''
        place = c['region'] + ' ' + c['district']
    else:
        location = '<section class="td-branch-context"><h2>방문 전 확인해 주세요</h2><p>이 지점의 주소와 수강 정보는 아직 안내하지 않습니다. 방문 위치와 현재 수업 가능 여부는 상담에서 확인해 주세요.</p><a href="tel:01039578283">전화로 지점 정보 확인하기</a></section>'
        place = '지점 선생님 소개'
    jump = ''.join('<a href="#'+r['anchor']+'">'+esc(r['name'])+' 선생님</a>' for r in b['records'])
    return (head(title, description, b['path'], graph) + header + breadcrumbs(crumbs) + f'''<main class="td-shell" id="main-content"><section class="td-branch-hero"><p class="td-eyebrow">{esc(place)}</p><h1>{esc(b['routeName'])} 선생님 소개</h1><p class="td-lead">선생님들이 학생의 질문과 학습을 어떻게 살피고자 하는지 소개글에서 확인해 보세요.</p><p class="td-image-note">사진은 소개용 공용 이미지이며 실제 선생님 사진과 다를 수 있습니다. 담당 과목·학년과 수업 일정은 상담에서 확인해 주세요.</p><nav class="td-teacher-jumps" aria-label="선생님 소개 바로가기">{jump}</nav></section><div class="td-teacher-grid">{''.join(cards)}</div>{location}<section class="td-reading"><h2>상담 전에 함께 살펴보세요</h2><p>최근 답안과 어려운 단원을 준비하면 학생에게 필요한 도움을 더 구체적으로 이야기할 수 있습니다.</p><a href="/guide/parent-consultation-checklist/">학부모 상담 체크리스트</a><a href="{enc(TEACHER_PATH)}">다른 지점 선생님찾기</a></section></main>''' + footer(), title, description)


def build(report):
    report.mkdir(parents=True, exist_ok=True)
    source, centers, branches, excluded = catalog()
    manifest = json.loads((ROOT / 'release-public-manifest.json').read_text(encoding='utf-8'))
    baseline_path = report / 'baseline.json'
    if not baseline_path.exists():
        save_json(baseline_path, {'files': {name: sha for name, sha in manifest['files'].items() if name.endswith('.html')}, 'manifest': manifest, 'descriptions': json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8')), 'sitemap': (ROOT/'sitemap.xml').read_text(encoding='utf-8')})
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    changed, html_files, linked = [], [], []
    by_path = {branch_url(b): b for b in branches if b['center']}
    def update_existing(name):
        path = ROOT / name
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        next_text = add_navigation(text)
        next_text = next_text.replace('header.css?v=20260920-nav1', 'header.css?v=20261002-teachers')
        document = html.fromstring(raw) if name.split('/')[0] in ('center','과목별학원','학년별학원') else None
        related = related_for(name, document, branches, by_path)
        if related:
            block = link_section(related, name.startswith('지점안내/'))
            if START in next_text:
                next_text = re.sub(re.escape(START)+'.*?'+re.escape(END), lambda _: block, next_text, flags=re.S)
            else:
                assert '</main>' in next_text, name
                next_text = next_text.replace('</main>', block + '</main>', 1)
            link_row = {'file': name, 'branches': [b['name'] for b in related], 'urls': [enc(b['path']) for b in related]}
        else:
            link_row = None
        if next_text != text:
            path.write_bytes(next_text.encode('utf-8'))
        return name, digest(next_text.encode('utf-8')) != baseline['files'][name], link_row
    with ThreadPoolExecutor(max_workers=16) as pool:
        for index, (name, was_changed, link_row) in enumerate(pool.map(update_existing, baseline['files']), 1):
            if was_changed:
                changed.append(name)
                html_files.append(name)
            if link_row:
                linked.append(link_row)
            if index % 5000 == 0:
                print(json.dumps({'existingHTMLProcessed':index,'total':len(baseline['files'])}),flush=True)
    original = html.fromstring((ROOT/'index.html').read_bytes())
    header_node = original.xpath('//header')[0]
    for a in header_node.xpath('.//a[@aria-current]'):
        del a.attrib['aria-current']
        a.attrib.pop('class', None)
    nav = header_node.xpath('.//a[@data-teacher-navigation]')[0]
    nav.set('class', 'active')
    nav.set('aria-current', 'page')
    header = html.tostring(header_node, encoding='unicode', with_tail=False)
    descriptions = json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8'))
    pages = [(TEACHER_PATH, render_hub(branches, header))] + [(b['path'], render_branch(b, header)) for b in branches]
    for path, (text, title, description) in pages:
        assert len(description) <= 80 and description.endswith('.')
        name = path.strip('/') + '/index.html'
        target = ROOT/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
        changed.append(name)
        html_files.append(name)
        descriptions['pages'][path.rstrip('/')] = {'description': description, 'sources': [description]}
    save_json(ROOT/'seo-descriptions.json', descriptions)
    for photo in source['photos']:
        name = 'assets/teacher-directory/'+photo['file']
        target = ROOT/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(INPUT/photo['file'], target)
        assert digest(target.read_bytes()) == photo['sha256']
        changed.append(name)
    changed.extend(['assets/header.css', 'assets/teacher-directory.css', 'assets/teacher-directory.js'])
    namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    sitemap = etree.parse(str(ROOT/'sitemap.xml'))
    existing = {unquote(e.findtext('s:loc', namespaces=namespace)) for e in sitemap.findall('s:url', namespace)}
    for path, _ in pages:
        if BASE+path not in existing:
            entry = etree.SubElement(sitemap.getroot(), '{'+namespace['s']+'}url')
            etree.SubElement(entry, '{'+namespace['s']+'}loc').text = BASE+enc(path)
            etree.SubElement(entry, '{'+namespace['s']+'}lastmod').text = DATE
    (ROOT/'sitemap.xml').write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n'+etree.tostring(sitemap, encoding='utf-8'))
    changed.append('sitemap.xml')
    manifest['sitemapPages'] = len(sitemap.findall('s:url', namespace))
    manifest['updatedDate'] = DATE
    for name in changed:
        raw = (ROOT/name).read_bytes()
        manifest['files'][name] = digest(raw)
        if Path(name).suffix in ('.html','.css','.js','.xml'):
            manifest.setdefault('textSha256',{})[name] = digest(raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n').encode('utf-8'))
    save_json(ROOT/'release-public-manifest.json', manifest)
    save_json(report/'catalog.json', branches)
    save_json(report/'linked-pages.json', linked)
    save_json(report/'changed-public-files.json', sorted(set(changed)))
    save_json(report/'changed-html.json', sorted(set(html_files)))
    summary = {'sourceRows':len(source['records']), 'sourceBranches':len({r['branch'] for r in source['records']}), 'publicBranches':len(branches), 'publicIntroductions':sum(len(b['records']) for b in branches), 'matchedBranches':sum(bool(b['center']) for b in branches), 'unmatchedBranches':[b['name'] for b in branches if not b['center']], 'excludedBranches':sorted({r['branch'] for r in excluded}), 'excludedRows':len(excluded), 'existingBranchesWithoutProfiles':[c['sourceName'] for c in centers if c['sourceName'] not in {b['name'] for b in branches}], 'newHTML':len(pages), 'navigationPages':len(html_files)-len(pages), 'linkedPages':len(linked), 'linkedFamilies':dict(Counter(r['file'].split('/')[0] for r in linked)), 'photoFiles':len(source['photos']), 'sitemapPages':manifest['sitemapPages']}
    save_json(report/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-source', action='store_true')
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.import_source:
        import_source()
    build(args.report_dir)


if __name__ == '__main__':
    main()
