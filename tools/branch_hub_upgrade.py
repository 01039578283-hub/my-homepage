"""Fact-bounded branch hub content and restrained, crawlable local navigation.

Source facts/manuscripts are never rewritten here. These postprocessors also run
after normal generation so the reviewed content and links survive future builds.
"""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from branch_course_guidance import course_guidance
from branch_learning_routes import guide_label, paired_routes
from branch_manuscript_editorial import learning_points
from site_navigation import NAV, unify_header

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://wawa-center.kr"
STYLE = '/assets/branch-hub-upgrade.css?v=20260920-nav1'
LEVELS = (("초등", "초"), ("중등", "중"), ("고등", "고"))
PRACTICE = {
    ("초등", "영어"): "소리 내어 읽은 문장과 뜻을 설명하기 어려운 문장을 나누어 보세요. 단어 암기량만 늘리기 전에 읽기와 이해 중 어디에서 막히는지 찾는 데 도움이 됩니다.",
    ("초등", "수학"): "계산은 맞았지만 설명하지 못한 문제와 문장의 조건을 놓친 문제를 따로 표시해 보세요. 풀이를 말로 설명한 뒤 비슷한 문제를 혼자 풀어 보는 순서로 준비할 수 있습니다.",
    ("중등", "영어"): "학교 본문에서 읽기 어려운 문장과 직접 쓰기 어려운 문장을 골라 보세요. 어휘·문장 구조·서술형 답안 중 먼저 보완할 부분을 구분해 상담할 수 있습니다.",
    ("중등", "수학"): "지금 단원에서 필요한 이전 개념과 풀이 중 생략한 과정을 표시해 보세요. 답을 고치는 데서 끝내지 말고 다음 날 같은 유형을 다시 풀어 본 기록을 준비하면 좋습니다.",
    ("고등", "영어"): "지문의 근거를 찾지 못한 문제와 문장 해석이 막힌 문제를 구분해 보세요. 학교 평가 범위와 현재 교재를 함께 보면 읽기·어법·답안 작성의 우선순위를 정하기 쉽습니다.",
    ("고등", "수학"): "현재 이수 과목과 학교 진도를 먼저 적고, 조건 해석·개념 선택·계산 중 풀이가 멈춘 지점을 표시해 보세요. 해결한 문제 수보다 혼자 설명할 수 있는 과정을 점검합니다.",
}
GUIDES = {
    ("초등", "영어"): ("초등 공부 습관을 만드는 방법", "/guide/elementary-study-habit/"),
    ("초등", "수학"): ("틀린 문제를 다시 공부하는 방법", "/guide/error-management/"),
    ("중등", "영어"): ("중등 영어 본문·문법 복습 순서", "/guide/middle-school-english-study/"),
    ("중등", "수학"): ("중등 수학 개념·유형 복습 순서", "/guide/middle-school-math-study/"),
    ("고등", "영어"): ("고등 영어 독해와 내신 준비", "/guide/highschool-english-study/"),
    ("고등", "수학"): ("고등 수학 개념과 문제풀이 점검", "/guide/highschool-math-study/"),
}


def esc(value):
    return escape(str(value), quote=True)


def url(path):
    return DOMAIN + quote(path, safe="/#")


def replace_block(raw, tag, attribute, value, replacement):
    # Replacement blocks deliberately contain no nested elements of this tag.
    pattern = rf'<{tag}\b(?=[^>]*\b{attribute}="{re.escape(value)}")[^>]*>.*?</{tag}>'
    matches = list(re.finditer(pattern, raw, re.S))
    if len(matches) != 1:
        raise ValueError(f"Expected one {tag}[{attribute}={value}], got {len(matches)}")
    m = matches[0]
    return raw[:m.start()] + replacement + raw[m.end():]


def update_graph(raw, callback):
    pattern = r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)'
    matches = list(re.finditer(pattern, raw, re.S))
    if len(matches) != 1:
        raise ValueError("Expected one branch schema graph")
    m = matches[0]
    payload = json.loads(m[2])
    callback(payload["@graph"])
    return raw[:m.start(2)] + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + raw[m.end(2):]


def upgrade_header(raw, active="/지점안내/"):
    raw = unify_header(raw, active)
    if active.startswith('/지점안내/') and STYLE not in raw:
        if raw.count('</head>') != 1:
            raise ValueError("Missing head")
        raw = raw.replace('</head>', f'<link rel="stylesheet" href="{STYLE}">\n</head>', 1)
    return raw


def center_learning(center):
    name = center['routeName']
    areas = '·'.join(center['neighborhoods'][:4]) or center['district']
    stages = []
    for level, prefix in LEVELS:
        views = {subject: course_guidance(center, subject, prefix) for subject in ('영어', '수학')}
        # A study-method card does not imply a course is offered. Pending or
        # unlisted ranges stay solely in the existing explicit course table.
        available = {subject: view for subject, view in views.items() if view['grades']}
        if not available:
            continue
        schools = center.get('schools', {}).get(level, [])[:3]
        school_text = (' · '.join(schools) + ' 등 인근 학교 학생이라면, 학교에서 받은 진도표와 현재 교재를 함께 준비해 보세요.') if schools else '재학 중인 학교와 학년, 현재 교재와 최근에 풀어 본 문제를 준비해 보세요.'
        rows = []
        for subject, view in available.items():
            notes = ' '.join(view['notes'])
            rows.append(f'<li><h4>{subject} · {esc(view["label"])}</h4><p>{PRACTICE[(level, subject)]}</p>{f"<p class=\"hub-condition\">{esc(notes)}</p>" if notes else ""}</li>')
        stages.append(f'<article class="hub-stage" data-learning-level="{level}"><h3>{level} 학습 준비</h3><p class="hub-school-context">{esc(school_text)}</p><ul>{"".join(rows)}</ul></article>')
    stage_html = f'<div class="hub-stage-grid">{"".join(stages)}</div>' if stages else '<p>먼저 아래 상담 준비 항목을 정리하고, 과목별 개설 학년은 위의 수업 조건 표에서 확인해 주세요.</p>'
    points = ''.join(f'<article><h3>{esc(title)}</h3><p>{esc(copy)}</p></article>' for title, copy in learning_points(center))
    is_wawa = '모두' not in center.get('brand', '')
    process_intro = ('홈페이지에서 소개하는 4C는 진단(Check), 학습 설계(Curriculum), 실행 점검(Coaching), 상담·조정(Consulting)의 흐름입니다. '
                     f'{name} 상담에서는 아래 질문으로 학생에게 필요한 도움을 구체화해 보세요.') if is_wawa else f'{name} 상담에서는 현재 상태, 시작할 공부, 복습 기록, 다음 계획을 순서대로 질문해 보세요.'
    source_link = '<a class="hub-text-link" href="/overview/#four-c">진단부터 상담까지 4C 흐름 살펴보기</a>' if is_wawa else '<a class="hub-text-link" href="/guide/consultation-diagnosis/">학습 진단 상담을 준비하는 방법</a>'
    ai = ('<p class="hub-ai-note">AI 학습 도구가 필요한 경우에는 결과 점수만 보지 말고, 영어의 영역별 이해도나 수학의 오답 유형을 다음 학습에 어떻게 활용하는지 질문해 보세요. '
          '본사 프로그램 소개와 지점의 실제 개설·이용 조건은 구분해 확인해야 합니다. '
          '<a class="hub-text-link" href="/overview/#ai-programs">AI 학습 기록의 활용 방식 보기</a></p>') if is_wawa else ''
    return f'''<section class="branch-section hub-learning-upgrade" id="learning" aria-labelledby="learning-title">
<div class="branch-section-head"><p class="branch-kicker">LEARNING GUIDE</p><h2 id="learning-title">{esc(name)} 상담에서 구체화할 학습 계획</h2><p>{esc(areas)}에서 학원을 알아본다면 학교 진도와 학생이 혼자 해 본 기록을 함께 살펴보세요. 아래 내용은 학습 준비 방법이며, 실제 수업 방식과 점검 주기는 상담에서 확인해 주세요.</p></div>
{stage_html}
<div class="hub-process"><h3>진단 결과를 다음 공부로 연결하는 질문</h3><p>{esc(process_intro)}</p><ol class="learning-flow"><li><b>1</b><span><strong>막힌 이유 확인</strong>개념을 모르는지, 문제의 조건을 놓치는지 실제 풀이로 설명해 보세요.</span></li><li><b>2</b><span><strong>시작 단원과 분량</strong>현재 학교 진도와 학생 수준 중 어떤 기준으로 첫 계획을 정할지 물어보세요.</span></li><li><b>3</b><span><strong>설명 후 혼자 풀기</strong>도움을 받고 고친 답과 혼자 다시 푼 답을 어떻게 나누어 점검할지 확인하세요.</span></li><li><b>4</b><span><strong>기록과 다음 계획</strong>학생·보호자가 어떤 기록을 보고 복습량을 조정할지 확인하세요.</span></li></ol>{source_link}{ai}</div>
<div class="hub-local-questions"><h3>{esc(name)}에서 함께 확인할 관리 항목</h3><div class="learning-grid">{points}</div><p>계획은 공부한 시간뿐 아니라 마친 내용과 남은 질문을 함께 적어 보세요. <a class="hub-text-link" href="/guide/study-planner/">실행 가능한 주간 플래너 작성법</a>으로 상담 전 기록을 준비할 수 있습니다.</p></div>
</section>'''


def child_directory(center):
    groups = []
    for locality in center['neighborhoods']:
        cards = []
        for level, prefix in LEVELS:
            for subject in ('수학', '영어'):
                path = f'/지점안내/{center["region"]}/{center["routeName"]}/{locality}{level}{subject}학원/'
                view = course_guidance(center, subject, prefix)
                detail = f'{view["label"]} · 학습 준비 확인' if view['grades'] else '개설 여부 확인 · 학습 준비 안내'
                cards.append(f'<a href="{esc(path)}"><strong>{esc(locality)} {level} {subject}학원</strong><span>{esc(detail)}</span></a>')
        groups.append(f'<div class="hub-neighborhood-group"><h3>{esc(locality)} 학습 안내</h3><div class="branch-topic-link-grid">{"".join(cards)}</div></div>')
    if not groups:
        return ''
    return f'<section class="branch-section branch-topic-links" id="learning-pages" aria-labelledby="learning-pages-title"><div class="branch-section-head"><p class="branch-kicker">LOCAL LEARNING PAGES</p><h2 id="learning-pages-title">동네별 영어·수학 학습 안내</h2><p>학생의 동네와 학교급을 골라 학습 준비 방법을 확인하세요. 안내 페이지가 있다고 모든 학년의 수업이 개설된 것은 아니며, 과목표의 안내 학년과 별도 확인 조건을 함께 살펴봐 주세요.</p></div>{"".join(groups)}</section>'


def related_entries(center, item, root=ROOT):
    locality, level, subject = (item[k] for k in ('locality', 'level', 'subject'))
    parent = f'/지점안내/{center["region"]}/{center["routeName"]}/'
    links = [(f'{center["routeName"]} 지점안내', parent, '주소·전체 과목·학년과 상담 준비를 함께 확인', False)]
    other = '영어' if subject == '수학' else '수학'
    links.append((f'{locality} {level} {other}학원', parent + f'{locality}{level}{other}학원/', '같은 동네·학교급의 다른 과목 학습 준비', False))
    levels = [pair[0] for pair in LEVELS]
    current = levels.index(level)
    for index in (current - 1, current + 1):
        if 0 <= index < len(levels):
            target = levels[index]
            links.append((f'{locality} {target} {subject}학원', parent + f'{locality}{target}{subject}학원/', '같은 과목의 이전 단계 복습' if index < current else '같은 과목의 다음 학교급 준비', False))
    label, path = GUIDES[(level, subject)]
    links.append((label, path, '상담 전 집에서 실천할 학습 방법', False))
    pair = paired_routes(center, item, root)
    if pair:
        links.append((guide_label(item), pair['guide'], '학습 상태와 상담 질문을 점검하는 안내', True))
    # Every child remains directly linked from its center. Do not add unrelated
    # neighborhood keyword lists or generate links to routes that do not exist.
    return links


def related_markup(center, item, root=ROOT):
    links = related_entries(center, item, root)
    cards = ''.join(f'<a{(" data-learning-route=\"guide\"" if legacy else "")} href="{esc(path)}"><strong>{esc(label)}</strong><span>{esc(detail)}</span></a>' for label, path, detail, legacy in links)
    schema = [{'@type': 'ListItem', 'position': i + 1, 'name': label, 'url': url(path)} for i, (label, path, _, _) in enumerate(links)]
    block = f'<section class="branch-section branch-related branch-topic-related" id="related-pages" aria-labelledby="topic-related-title"><div class="branch-section-head"><p class="branch-kicker">RELATED PAGES</p><h2 id="topic-related-title">다음으로 살펴볼 학습 안내</h2><p>지점 정보를 다시 확인하거나, 같은 동네의 과목·학교급 준비 내용을 이어서 읽어 보세요.</p></div><div class="related-grid">{cards}</div></section>'
    return block, schema


def upgrade_child(raw, center, item):
    block, entries = related_markup(center, item)
    raw = replace_block(raw, 'section', 'id', 'related-pages', block)
    def change(nodes):
        listing = next(n for n in nodes if n.get('@type') == 'ItemList' and n.get('@id', '').endswith('#related-pages'))
        listing['itemListElement'], listing['numberOfItems'] = entries, len(entries)
        page = next(n for n in nodes if n.get('@type') == 'WebPage')
        page['relatedLink'] = [entry['url'] for entry in entries]
    return upgrade_header(update_graph(raw, change))


def upgrade_center(raw, center):
    raw = replace_block(raw, 'section', 'id', 'learning', center_learning(center))
    if center['neighborhoods']:
        raw = replace_block(raw, 'section', 'id', 'learning-pages', child_directory(center))
        toc = re.search(r'<nav class="branch-toc"[^>]*>.*?</nav>', raw, re.S)
        if not toc:
            raise ValueError('Center table of contents missing')
        if 'href="#learning-pages"' not in toc[0]:
            expanded = toc[0].replace('</nav>', '<a href="#learning-pages">동네별 학습 안내</a></nav>')
            raw = raw[:toc.start()] + expanded + raw[toc.end():]
    related = f'<section class="branch-section branch-related" aria-labelledby="related-title"><div class="branch-section-head"><p class="branch-kicker">NEXT STEP</p><h2 id="related-title">방문 전 확인할 안내</h2></div><div class="related-grid"><a href="/지점안내/{esc(center["region"])}/"><strong>{esc(center["region"])}의 다른 센터</strong><span>통학 동선과 주소를 비교해 보세요.</span></a><a href="/guide/parent-consultation-checklist/"><strong>학부모 상담 체크리스트</strong><span>준비할 자료와 확인할 질문을 정리하세요.</span></a></div></section>'
    raw = replace_block(raw, 'section', 'aria-labelledby', 'related-title', related)
    def change(nodes):
        article = next(n for n in nodes if n.get('@type') == 'Article')
        article['articleSection'] = list(dict.fromkeys([*article['articleSection'], '학교급별 영어·수학 학습 준비', '학습 진단과 복습 계획']))
    return upgrade_header(update_graph(raw, change))


def directory_learning(centers, region=None):
    scope = f'{region} 지역' if region else '전국'
    subjects = {s: sum(bool(course_guidance(c, s)['grades']) for c in centers) for s in ('국어', '영어', '수학', '과학', '사회')}
    counts = ' · '.join(f'{s} {n}곳' for s, n in subjects.items() if n)
    summary = (f'{scope} {len(centers)}개 센터의 자료와 수업 조건을 대조하면, 안내 학년이 확인된 과목은 {counts}입니다. 같은 센터가 여러 과목에 포함될 수 있으며, 현재 시간표와 신규 등록 여부는 별도 확인이 필요합니다.')
    intro = ('센터를 정하기 전에는 통학 거리, 학생의 학년·희망 과목, 혼자 공부할 때 막히는 부분을 순서대로 정리해 보세요.' if region else '지역을 선택한 뒤 센터의 주소와 과목별 학년을 확인하고, 동네별 학습 안내에서 상담할 질문을 준비할 수 있습니다.')
    return f'''<section class="branch-section branch-system hub-directory-learning" id="coaching-system" aria-labelledby="coaching-system-title"><div class="branch-section-head"><p class="branch-kicker">CHOOSING A CENTER</p><h2 id="coaching-system-title">{esc(scope)} 센터를 고를 때 함께 볼 학습 기준</h2><p>{esc(intro)}</p></div>
<p class="hub-coverage">{esc(summary)}</p><div class="branch-system-grid"><article><span>PLAN</span><h3>시간표보다 먼저, 실행할 분량</h3><p>현재 학교 진도와 집에서 마칠 수 있는 공부량을 알려주세요. 새 진도와 부족한 단원 중 무엇을 먼저 다룰지 질문하면 계획을 구체화하기 좋습니다.</p></article><article><span>STUDY</span><h3>맞힌 답보다, 혼자 푸는 과정</h3><p>설명을 들은 뒤 고친 문제와 혼자 다시 풀어 본 문제를 구분해 보세요. 영어 문장 이해와 수학의 개념·조건 해석처럼 과목별로 막힌 이유를 확인합니다.</p></article><article><span>ROUTINE</span><h3>가정에서도 이어지는 확인</h3><p>미완료 과제와 남은 질문을 어떻게 전달할지, 보호자가 어떤 기록을 확인할지 물어보세요. 피드백 방식과 주기는 센터마다 확인해야 합니다.</p></article></div>
<p>홈페이지의 <a class="hub-text-link" href="/overview/#four-c">진단·설계·코칭·상담으로 이어지는 4C 안내</a>를 읽고 학생에게 필요한 도움을 정리해 보세요. AI 영어·수학·국어·독서 도구는 진단과 취약점 점검에 활용하는 본사 프로그램 안내이며, 각 지점의 개설 여부를 뜻하지는 않습니다. <a class="hub-text-link" href="/overview/#ai-programs">AI 프로그램별 학습 기록 확인하기</a></p><p>방문 전 자료는 <a class="hub-text-link" href="/guide/parent-consultation-checklist/">학부모 상담 체크리스트</a>로 정리하고, 가까운 센터는 아래 목록에서 찾아보세요.</p></section>'''


def upgrade_directory(raw, centers, region=None):
    raw = replace_block(raw, 'section', 'id', 'coaching-system', directory_learning(centers, region))
    # Keep the search/list above detailed learning explanations on mobile.
    pattern = r'<section\b[^>]*id="coaching-system"[^>]*>.*?</section>'
    m = re.search(pattern, raw, re.S)
    block = m[0]
    raw = raw[:m.start()] + raw[m.end():]
    marker = '<section class="branch-section branch-faq" id="faq"'
    if marker not in raw:
        raise ValueError('Directory FAQ insertion point missing')
    raw = raw.replace(marker, block + '\n' + marker, 1)
    # Region pages already have this checklist in the content above. One
    # contextual recommendation is enough; preserve navigation to subject hubs.
    if region:
        raw = raw.replace('<a href="/guide/parent-consultation-checklist/"><strong>상담 체크리스트</strong><span>상담 전 준비할 질문과 자료 확인하기</span></a>', '')
    return upgrade_header(raw)
