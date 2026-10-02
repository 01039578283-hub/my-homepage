"""Build the 65 learning guides from reviewed activities and an immutable HTML baseline.

Run with --baseline <before-guides.zip> --report-dir <directory>.
Only the two guide hubs, their articles, and release metadata are updated.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import html as stdhtml
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from lxml import etree, html
from learning_guide_content import BASE, CATEGORIES, DATE, GUIDES, SOURCES

ROOT = Path(__file__).resolve().parents[1]
AUDIENCE = {"student": "학생", "parent": "학부모", "elementary": "초등", "middle": "중등", "high": "고등"}
TRACKER = '<script defer src="https://wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js" data-site="wawa-01" crossorigin="anonymous" referrerpolicy="no-referrer"></script>'
BY_PATH = {g["path"]: g for g in GUIDES}
PUBLIC_FILES: list[str] = []
HTML_FILES: list[str] = []
EXTRACT_REPORT = []
ORG = {"@type": "Organization", "name": "와와학습코칭센터", "url": BASE + "/"}


def esc(value):
    return stdhtml.escape(str(value), quote=True)


def url(path):
    return "/" + quote(path.strip("/"), safe="/-") + "/"


def split(value):
    return value.split(":", 1)


def write(name, text, bom=False):
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    target.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.replace("\n", "\r\n").encode("utf-8"))
    PUBLIC_FILES.append(name)
    if name.endswith(".html"):
        HTML_FILES.append(name)


def serialize(element):
    return html.tostring(element, encoding="unicode", with_tail=False)


def schemas(document):
    result = []
    for node in document.xpath('//script[@type="application/ld+json"]'):
        value = json.loads(node.text)
        result.extend(value.get("@graph", [value]))
    return result


def original_date(document):
    for item in schemas(document):
        if item.get("@type") == "Article" and item.get("datePublished"):
            return item["datePublished"]
    return None


def clean_text(value):
    substitutions = {
        "학교 시험에 자주 나오는 대표 유형": "학교 수업 자료에서 다룬 대표 유형",
        "대부분 반복 주기가 부족하거나 뜻만 외우고 문장 속 활용을 확인하지 않기 때문입니다. 재시험과 예문 확인이 필요합니다.": "처음의 이해와 복습 과정, 문장 속 활용을 나누어 확인해 보세요. 답을 가린 확인에서 어려운 단어를 골라 뜻과 예문을 다시 연결합니다.",
        "간단한 단어장은 도움이 됩니다. 다만 초등은 쓰기보다 소리 내어 읽기, 뜻 말하기, 짧은 문장 활용부터 시작하는 것이 좋습니다.": "현재 학교 자료와 아이가 할 수 있는 활동을 먼저 확인하세요. 소리·뜻·짧은 문장 중 필요한 활동을 고르고 단어장은 다시 확인할 항목을 남기는 데 사용할 수 있습니다.",
        "새 문제 풀이 직후·시험 전처럼 최소 두 번 다시 보는 시간을 미리 계획합니다.": "새 문제 풀이 뒤와 시험 전 등 다시 확인할 기회를 일정에 넣고 실제 결과에 따라 범위와 날짜를 조정합니다.",
        "입학 직후부터 수업 자료를 정리하는 것이 가장 좋고, 시험 4주 전에는 범위별 복습 계획이 있어야 안정적입니다.": "학교 안내와 수업 자료를 확인할 때부터 준비할 항목을 모을 수 있습니다. 현재 남은 날짜와 수행에 맞게 범위와 다음 확인을 정하세요.",
        "시험 3주 전에는 범위 파악, 2주 전에는 단원별 복습, 1주 전에는 오답 재확인과 실전 시간을 관리합니다.": "학교 범위를 확인하고 필요한 단원 복습과 오답 재확인을 배치합니다. 남은 날짜와 실제 수행에 따라 활동의 순서와 양을 조정합니다.",
        "여러 학습법의 효과를 비교한 연구들에서 공통적으로 가장 효과가 크다고 나온 두 가지는 “스스로 인출해보는 연습”과 “나눠서 반복하기”입니다. 노트를 다시 읽거나 형광펜을 긋는 방식은 이런 연구들에서 상대적으로 효과가 낮게 나타났습니다. 개념을 보고 그대로 옮겨 적기보다, 책을 덮고 빈 종이에 스스로 설명해본 뒤 맞는지 확인하는 방식이 시험 직전 복습에 훨씬 효율적입니다.": "읽고 이해한 내용을 자료 없이 설명하거나 적용해 본 뒤 원문과 대조해 보세요. 시간이 지난 뒤 다시 확인할 기회를 정하고 실제 결과에 따라 질문과 범위를 조정합니다. 다시 읽기는 필요한 설명을 확인하는 데 사용하고, 읽은 결과와 혼자 가능한 수행을 구분합니다.",
        "한 번 틀린 문제는 원인을 적고 최소 2회 이상 다시 풀어야 시험장에서 같은 실수를 줄일 수 있습니다.": "틀린 문제의 첫 오류와 수정 이유를 적고 해설을 가린 재풀이로 남은 어려움을 확인하세요. 필요한 횟수와 다음 날짜는 실제 결과에 맞춰 정합니다.",
        "대부분의 경우 학교 자료가 먼저입니다. 학교 수업에서 다룬 내용과 프린트, 부교재를 확인한 뒤 부족한 유형을 문제집으로 보완하는 순서가 안정적입니다.": "학교가 안내한 범위와 평가 요구를 먼저 대조하세요. 교과서와 배부 자료에서 필요한 활동을 확인한 뒤 보충 자료가 어떤 어려움을 다룰지 정합니다.",
        "최소 3~4주 전에는 범위와 과목별 우선순위를 정리하는 것이 좋습니다. 암기 과목과 서술형 비중이 큰 과목은 더 일찍 시작해야 합니다.": "남은 날짜와 현재 수행, 제출 일정을 함께 보고 준비를 시작하세요. 모든 학생에게 같은 시작 주간을 정하지 않고 필요한 설명·연습·재확인을 나누어 계획합니다.",
        "매일 20~30분이라도 영어 어휘, 수학 개념, 그날 배운 내용을 확인하는 시간을 만듭니다.": "영어 어휘와 수학 개념, 그날 배운 내용 중 지금 확인할 항목을 고릅니다. 시간과 분량은 학교 일정과 실제 부담에 맞게 정합니다.",
        "틀린 문제는 시험 전날 몰아보면 원인 확인이 어렵습니다. 2~3일 간격으로 다시 풀 시간을 따로 잡습니다.": "오답의 원인을 확인하고 자료를 가린 재풀이를 별도로 계획하세요. 다음 날짜는 실제 결과와 남은 일정에 맞게 정합니다.",
        "시험 3주 전부터 쓰는 것이 가장 안정적입니다. 범위가 늦게 나와도 예상 범위와 수행평가 일정은 먼저 정리할 수 있습니다.": "현재 학교 안내와 남은 날짜를 기준으로 계획할 수 있습니다. 범위가 확정되지 않았다면 최근 수업과 제출 일정을 적되 예상과 확정 안내를 구분하세요.",
        "시험기간 4단계 계획": "마지막 주와 전날에 확인할 항목",
        "시험 공부에서 가장 검증된 두 가지 방법": "읽은 내용과 직접 수행한 결과 구분하기",
        "학교 공지와 과목별 안내를 확인하는 시간을 정해두고, 제출일보다 3~5일 전 알림을 만들어두는 것이 좋습니다.": "학교 공지와 과목별 안내를 확인할 기회를 정하고 준비·검토·제출 일정을 따로 기록하세요. 필요한 준비 기간은 과제 조건과 현재 진행에 맞게 정합니다.",
        "인지심리학 연구에서는 여러 학습법 중 “스스로 기억을 꺼내보는 연습”과 “나눠서 반복하기”를 가장 효과가 큰 방법으로 꼽습니다. 초등학생에게는 책을 덮고 방금 읽은 내용을 말로 설명하게 하는 것이 이 인출연습과 같은 효과를 냅니다. 밑줄을 긋거나 여러 번 읽기만 하는 방식은 익숙하다는 착각만 줄 뿐, 실제 기억에는 큰 도움이 되지 않는다는 점도 함께 알아두면 좋습니다.": "짧게 읽고 이해한 내용을 아이가 자료 없이 말하거나 그림으로 나타내 보게 할 수 있습니다. 막힌 부분은 원문과 함께 다시 보고 다른 날 같은 질문을 확인해 보세요. 이 활동 하나로 이해나 기억을 단정하지 않고 아이에게 필요한 설명과 도움을 조정합니다.",
        "오답은 크게 개념을 몰라서 틀린 경우, 문제의 조건이나 단서를 놓친 경우, 알고 있었지만 계산이나 표기에서 실수한 경우 세 가지로 나뉩니다. 원인을 구분하지 않고 정답만 옮겨 적으면 같은 실수가 반복되기 쉽습니다. 오답노트는 며칠 뒤가 아니라 2~3일 간격으로 다시 펼쳐보는 것이 권장되며, 원인과 함께 다음에 어떻게 다르게 풀지까지 적어두면 효과가 훨씬 커집니다. 이런 방식으로 틀린 문제를 다시 풀면 처음 풀 때보다 이해도가 눈에 띄게 올라간다는 것이 여러 학습 자료에서 공통적으로 확인됩니다.": "오답의 원인은 개념·조건 읽기·방법 선택·계산·표기 등 실제 답안에서 확인한 단계로 나눠 볼 수 있습니다. 여러 이유가 함께 있거나 아직 이유를 모를 수도 있습니다. 정답을 옮기는 데서 끝내지 말고 처음 어긋난 줄과 수정 이유, 다음에 확인할 질문을 남긴 뒤 혼자 다시 풀 결과를 기록하세요.",
        "단어 암기는 하루에 몰아서 많이 외우는 것보다 같은 단어를 시간 간격을 두고 여러 번 다시 보는 방식이 오래 기억에 남는다는 것이 학습 연구에서 공통적으로 확인된 결과입니다. 외운 날, 다음 날, 3일 후, 1주일 후처럼 간격을 점점 늘려가며 다시 확인하는 방식을 추천합니다. 하루 30개를 한 번 보고 끝내는 것보다 10개를 네 번 나눠 보는 쪽이 실제 시험에서 더 오래 기억납니다.": "단어의 뜻과 문장 사용을 확인한 뒤 시간을 두고 자료 없이 다시 떠올려 보세요. 결과에 따라 남은 단어와 다음 확인 날짜를 정합니다. 특정 단어 수나 복습 간격을 모든 학생의 시험 기억에 효과가 보장되는 공식으로 적용하지 않습니다.",
        "한 번 맞힌 단어도 2~3일 뒤 다시 확인해야 장기 기억으로 넘어갑니다.": "한 번 맞힌 단어도 시간을 두고 자료 없이 다시 확인해 보세요. 실제 결과에 따라 남은 어휘와 다음 날짜를 조정합니다.",
        "개수보다 반복 주기가 중요합니다. 학생이 정확히 기억할 수 있는 양을 정하고, 다음 날과 주말에 다시 확인해야 합니다.": "현재 자료와 실제 부담에 맞게 범위를 고르세요. 뜻·철자·문장 사용을 나눠 확인하고 시간이 지난 뒤 다시 본 결과로 다음 양과 날짜를 조정합니다.",
        "긴 지문을 매일 푸는 것보다 짧은 지문으로 구조 읽기와 문단 요약 연습을 꾸준히 반복하는 것이 효과적입니다.": "현재 어려움에 맞는 지문과 확인할 활동을 고르세요. 구조 읽기와 문단 요약을 해 보고 실제 결과와 부담에 따라 분량과 다음 날짜를 정합니다.",
        "정답 내용을 알아도 표현이 정확하지 않으면 감점됩니다. 핵심 어휘와 문장 구조에 맞춰 쓰는 연습을 반복해야 합니다.": "문항의 요구와 학교의 답안 조건을 확인하세요. 근거와 설명을 연결해 쓴 뒤 빠진 조건을 점검하고 실제 감점 이유는 채점 안내나 교사의 설명으로 확인합니다.",
        "하루 10분 이상 독서를 하는지": "읽은 내용에서 기억한 장면이나 궁금한 점을 말할 수 있는지",
    }
    for before, after in substitutions.items():
        value = value.replace(before, after)
    return value


def original_content(document, guide):
    containers = document.xpath('//main//*[contains(concat(" ",normalize-space(@class)," ")," guide-main ") or contains(concat(" ",normalize-space(@class)," ")," edu-main ") or contains(concat(" ",normalize-space(@class)," ")," pilot-article ")]')
    assert len(containers) == 1, guide["path"]
    container = containers[0]
    faqs = []
    for node in container.xpath('.//details[summary]'):
        question = " ".join(node.xpath("./summary")[0].text_content().split())
        answer = " ".join(" ".join(p.text_content().split()) for p in node.xpath("./p"))
        if question and answer:
            faqs.append((question, clean_text(answer)))
    content = []
    if not guide["steps"]:
        for child in container:
            classes = child.get("class", "")
            if child.tag not in {"section", "figure"}:
                continue
            if any(word in classes for word in ("faq", "related", "cta", "ai-entity", "academy-next")):
                continue
            heading = " ".join(child.xpath("./h2//text()"))
            if any(word in heading for word in ("함께 보면", "함께 읽", "함께 확인", "이어")):
                continue
            if guide['category'] != 'parents' and any(word in heading for word in ("학부모가", "상담 전", "상담에서")):
                continue
            # A related-link list is navigation, not instructional content.
            if child.xpath('.//a[contains(@href,"교육정보") or contains(@href,"%EA%B5%90%EC%9C%A1%EC%A0%95%EB%B3%B4")]') and not child.xpath('.//p'):
                continue
            node = copy.deepcopy(child)
            for old_link in node.xpath('.//*[contains(@class,"academy-context-link")]'):
                old_link.getparent().remove(old_link)
            for textnode in node.iter():
                if textnode.text:
                    textnode.text = clean_text(textnode.text)
                if textnode.tail:
                    textnode.tail = clean_text(textnode.tail)
            if re.search(r"[12347]주 전|[137]일 뒤|1일.*3일.*7일|4단계|하루 루틴|주간 루틴", node.text_content()):
                note = html.fromstring('<p class="lg-context-note">아래 순서와 기간은 계획을 설명하는 예시입니다. 학교 일정과 현재 수행, 실제 부담에 맞게 범위와 확인 날짜를 조정하세요.</p>')
                node.insert(1, note)
            content.append(serialize(node))
    EXTRACT_REPORT.append({"path": guide["path"], "retained_blocks": len(content), "original_faq": len(faqs)})
    return "\n".join(content), faqs


def head(title, description, canonical, graph, article=False):
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'''<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} | 와와학습코칭센터</title>
<meta name="description" content="{esc(description)}"><meta name="robots" content="index, follow">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="{'article' if article else 'website'}"><meta property="og:title" content="{esc(title)} | 와와학습코칭센터">
<meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:image" content="{BASE}/assets/title.png">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)} | 와와학습코칭센터"><meta name="twitter:description" content="{esc(description)}"><meta name="twitter:image" content="{BASE}/assets/title.png">
<link rel="icon" type="image/png" href="/assets/favicon.png"><link rel="alternate" type="application/rss+xml" title="와와학습코칭센터 교육정보 RSS" href="/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&family=Noto+Sans+KR:wght@400;500;700;900&display=swap">
<link rel="stylesheet" href="/assets/header.css?v=20260920-nav1"><link rel="stylesheet" href="/assets/learning-guides.css?v=20261002">
<script defer src="/assets/learning-guides.js?v=20261002"></script>
<script type="application/ld+json">{data}</script>
{TRACKER}
</head><body><a class="lg-skip" href="#main-content">본문으로 건너뛰기</a>'''


def footer():
    return '''<footer class="lg-footer"><div class="lg-container"><a class="lg-footer-brand" href="/">와와학습코칭센터</a><p>오늘 확인한 어려움을 다음 학습의 질문으로 이어 보세요.</p><nav aria-label="하단 메뉴"><a href="/guide/">학습가이드 전체</a><a href="/교육정보/">상황별 읽기 순서</a><a href="/center/">전국센터 안내</a></nav></div></footer></body></html>'''


def crumbs(items):
    nodes, markup = [], []
    for index, (label, path) in enumerate(items, 1):
        nodes.append({"@type": "ListItem", "position": index, "name": label, "item": BASE + url(path) if path else BASE + "/"})
        markup.append(f'<a href="{esc(url(path) if path else "/")}">{esc(label)}</a>' if index < len(items) else f'<span aria-current="page">{esc(label)}</span>')
    return {"@type": "BreadcrumbList", "itemListElement": nodes}, '<nav class="lg-breadcrumb" aria-label="현재 위치">' + '<span aria-hidden="true">/</span>'.join(markup) + '</nav>'


def card(guide, index=None):
    tags = " · ".join(AUDIENCE[a] for a in guide["audience"] if a in {"elementary", "middle", "high"}) or "학부모"
    marker = f'<span class="lg-card-number">{index:02d}</span>' if index else ""
    return f'''<article class="lg-card" data-guide-card data-category="{guide['category']}" data-audience="{' '.join(guide['audience'])}">
<p class="lg-card-meta">{esc(CATEGORIES[guide['category']][0])}<span>{esc(tags)}</span></p>
<h3>{marker}<a href="{esc(url(guide['path']))}">{esc(guide['title'])}</a></h3><p>{esc(guide['description'])}</p>
<span class="lg-card-action" aria-hidden="true">가이드 읽기 <span>↗</span></span></article>'''


def link_list(paths):
    return '<ul class="lg-reading-list">' + "".join(f'<li><a href="{esc(url(p))}">{esc(BY_PATH[p]["title"])}</a></li>' for p in paths) + "</ul>"


def worked_example(path):
    if path == 'guide/math-graphs':
        return '''<div class="lg-worked-example"><h3>한 관계를 세 가지로 보기</h3><div class="lg-representation-grid"><div><table><caption>식 y=2x+1의 값</caption><thead><tr><th scope="col">x</th><th scope="col">y</th></tr></thead><tbody><tr><td>0</td><td>1</td></tr><tr><td>1</td><td>3</td></tr><tr><td>2</td><td>5</td></tr></tbody></table><p class="lg-equation">x=1 → y=2×1+1=3<br>같은 값의 쌍: (1, 3)</p></div><figure><svg viewBox="0 0 340 250" role="img" aria-labelledby="lg-graph-title lg-graph-desc"><title id="lg-graph-title">y=2x+1에서 세 점을 연결한 그래프</title><desc id="lg-graph-desc">표시한 x 범위는 0부터 2까지입니다. 점 (0,1), (1,3), (2,5)가 같은 직선 위에 있으며 (1,3)을 강조했습니다. 축의 눈금 단위는 각각 1입니다.</desc><g stroke="#d8cbb5"><path d="M50 185H285M50 155H285M50 125H285M50 95H285M50 65H285M150 35V215M250 35V215"/></g><path d="M50 25V215H290" fill="none" stroke="#1a2440" stroke-width="2"/><path d="M50 185L250 65" fill="none" stroke="#1a2440" stroke-width="3"/><g fill="#1a2440"><circle cx="50" cy="185" r="5"/><circle cx="250" cy="65" r="5"/></g><circle cx="150" cy="125" r="7" fill="#936622"/><g font-family="sans-serif" font-size="13" fill="#1a2440"><text x="38" y="232">0</text><text x="146" y="232">1</text><text x="246" y="232">2</text><text x="28" y="190">1</text><text x="28" y="160">2</text><text x="28" y="130">3</text><text x="28" y="100">4</text><text x="28" y="70">5</text><text x="301" y="220">x</text><text x="44" y="18">y</text><text x="167" y="117" fill="#775324">(1, 3)</text></g></svg><figcaption>x=1일 때 y=3인 점을 표·식과 연결해 보세요. 표시한 범위의 연습용 그래프입니다.</figcaption></figure></div></div>'''
    if path == 'guide/science-data':
        return '''<div class="lg-worked-example"><h3>관찰과 판단을 나누는 연습</h3><table><caption>해석 연습용 가상 자료 · 실제 실험 아님</caption><thead><tr><th scope="col">조건 이름</th><th scope="col">가상 측정값</th></tr></thead><tbody><tr><th scope="row">A</th><td>2</td></tr><tr><th scope="row">B</th><td>4</td></tr><tr><th scope="row">C</th><td>3</td></tr></tbody></table><div class="lg-evidence-pair"><div><strong>자료에서 읽을 수 있는 것</strong><p>제시된 세 값 중 B의 값이 가장 큽니다.</p></div><div><strong>아직 확인할 수 없는 것</strong><p>측정 대상과 단위, 조건의 의미, 원인과 반복 여부는 이 표만으로 알 수 없습니다.</p></div></div></div>'''
    if path == 'guide/english-sentence-structure':
        return '''<div class="lg-worked-example"><h3>직접 만든 문장을 나눠 읽기</h3><p class="lg-english-example"><mark>The book</mark> <span class="lg-modifier">on the desk</span> <mark class="lg-verb">belongs</mark> to Mina.</p><dl class="lg-language-parts"><div><dt>The book · 주어</dt><dd>무엇에 대해 말하는지</dd></div><div><dt>belongs · 동사</dt><dd>소속 관계를 나타내는 중심 동사</dd></div><div><dt>on the desk · 수식</dt><dd>어떤 책인지 설명하는 부분</dd></div><div><dt>to Mina · 연결</dt><dd>누구에게 속하는지 나타내는 부분</dd></div></dl><p>각 부분을 연결한 뜻: 책상 위의 책은 미나의 것이다.</p></div>'''
    return ''


def render_article(guide, original, header):
    knowledge, faqs = original_content(original, guide) if original is not None else ("", [])
    if guide["steps"]:
        knowledge = '<ol class="lg-method-steps">' + "".join(f'<li><h3>{esc(split(s)[0])}</h3><p>{esc(split(s)[1])}</p></li>' for s in guide["steps"]) + "</ol>"
    if guide.get("background"):
        knowledge = "".join(f"<p>{esc(p)}</p>" for p in guide["background"]) + knowledge
    assert knowledge, guide["path"]
    if guide["faq"]:
        faqs = [tuple(split(item)) for item in guide["faq"]]
    if not faqs:
        # Topic-specific questions use the actual activity and next check.
        faqs = [("어디부터 확인하면 좋을까요?", guide["checks"][0] + " " + guide["example"][0]), ("한 번 기록한 뒤에는 무엇을 하나요?", guide["followup"])]
    guide["visible_faq"] = faqs
    canonical = BASE + url(guide["path"])
    breadcrumb, breadcrumb_html = crumbs([("홈", ""), ("학습가이드", "guide"), (guide["title"], guide["path"])])
    article = {"@type": "Article", "@id": canonical + "#article", "headline": guide["title"], "description": guide["description"], "image": BASE + "/assets/title.png", "inLanguage": "ko-KR", "author": ORG, "publisher": ORG, "dateModified": DATE, "mainEntityOfPage": {"@type": "WebPage", "@id": canonical, "description": guide["description"]}, "citation": [SOURCES[s]["url"] for s in guide["sources"]]}
    published = original_date(original) if original is not None else DATE
    if published:
        article["datePublished"] = published
    graph = [article, breadcrumb, {"@type": "FAQPage", "@id": canonical + "#lg-faq", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}]
    title = guide["title"]
    record_name = guide["path"].split("/")[-1] + ".txt"
    fields = [split(s) for s in guide["fields"]]
    blank = f'{title} · 학습 기록\n가이드: {canonical}\n작성일: ____________________\n\n' + "\n\n".join(f"{label}\n확인할 내용: {hint}\n기록: ____________________" for label, hint in fields) + f'\n\n다음 확인\n{guide["followup"]}\n\n참고\n{guide["caution"]}\n'
    write("assets/learning-guide-records/" + record_name, blank, bom=True)
    form_fields = "".join(f'<div class="lg-field"><label for="lg-field-{i}">{esc(label)}</label><p id="lg-hint-{i}">{esc(hint)}</p><textarea id="lg-field-{i}" name="field-{i}" rows="3" maxlength="4000" aria-describedby="lg-hint-{i}"></textarea></div>' for i, (label, hint) in enumerate(fields, 1))
    refs = "".join(f'<li><a href="{esc(SOURCES[s]["url"])}" target="_blank" rel="noopener noreferrer">{esc(SOURCES[s]["name"])} <span class="lg-external" aria-hidden="true">↗</span><span class="lg-visually-hidden"> (새 창)</span></a><span class="lg-ref-year">{esc(SOURCES[s]["year"])}</span><p>{esc(SOURCES[s]["scope"])}</p></li>' for s in guide["sources"])
    faqs_html = "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faqs)
    faq_alias = '<span id="faq" class="lg-anchor" aria-hidden="true"></span>' if original is not None and original.xpath('//*[@id="faq"]') else ''
    scope = " · ".join(AUDIENCE[a] for a in guide["audience"])
    image_note = '<p class="lg-context-note">본문 사진은 학습 활동의 이해를 돕는 이미지이며 특정 센터의 수업이나 학생 사례를 뜻하지 않습니다.</p>' if original is not None and original.xpath('//main//img') else ""
    page = head(title, guide["description"], canonical, graph, article=True) + header + f'''
<main id="main-content"><div class="lg-container">{breadcrumb_html}</div>
<article class="lg-article">
<header class="lg-article-hero lg-container"><p class="lg-eyebrow">{esc(CATEGORIES[guide['category']][0])} / 학습 실천 가이드</p><h1>{esc(title)}</h1><p class="lg-answer">{esc(guide['answer'])}</p><div class="lg-article-meta"><span>대상 · {esc(scope)}</span><span>내용 확인 · <time datetime="{DATE}">{DATE}</time></span></div></header>
<div class="lg-article-body">
<nav class="lg-toc" aria-label="이 글의 목차"><strong>이 글에서 해 볼 일</strong><a href="#lg-check">현재 상태 확인</a><a href="#lg-method">실행 방법</a><a href="#lg-example">연습 예시</a><a href="#lg-record">나의 기록</a><a href="#lg-parent">학부모의 도움</a><a href="#lg-faq">자주 묻는 질문</a><a href="#lg-sources">참고 자료</a></nav>
<section class="lg-section" id="lg-check"><p class="lg-step-label">01 · 시작하기 전에</p><h2>지금 상태를 먼저 확인하세요</h2><ul class="lg-checks">{''.join(f'<li>{esc(c)}</li>' for c in guide['checks'])}</ul><p>아직 확인하지 못한 항목은 그대로 남겨도 됩니다. 최근 과제나 답안을 하나 골라 살펴보세요.</p></section>
<section class="lg-section" id="lg-method"><p class="lg-step-label">02 · 실행하기</p><h2>무엇을 어떻게 해 볼까요?</h2><div class="lg-knowledge">{knowledge}</div>{image_note}</section>
<section class="lg-section lg-example-box" id="lg-example"><p class="lg-step-label">03 · 연습 예시</p><h2>실제 행동으로 바꿔 보기</h2>{''.join(f'<p>{esc(p)}</p>' for p in guide['example'])}{worked_example(guide['path'])}<p class="lg-small">활동을 설명하기 위해 만든 예시입니다. 실제 학교 자료와 학생의 상황에 맞게 바꿔 사용하세요.</p></section>
<section class="lg-section" id="lg-record"><p class="lg-step-label">04 · 기록하고 확인하기</p><h2>나의 학습 기록</h2><p>짧게 적어도 괜찮습니다. 기록에서 확인한 한 가지를 다음 활동으로 연결해 보세요.</p>
<div class="lg-record-download"><a class="lg-button lg-button-secondary" href="/assets/learning-guide-records/{quote(record_name)}" download="{esc(record_name)}">빈 기록 양식 받기 <span aria-hidden="true">↓</span></a><span>TXT · 메모 앱이나 인쇄에 사용</span></div>
<form class="lg-record-form" data-record-form data-title="{esc(title)}" data-filename="{esc(record_name)}" data-canonical="{esc(canonical)}"><div class="lg-field-grid">{form_fields}</div><div class="lg-form-actions" hidden data-record-actions><button class="lg-button" type="button" data-save-record>작성 내용 저장 ↓</button><button class="lg-button lg-button-secondary" type="button" data-print-record>이 페이지 인쇄</button><button class="lg-text-button" type="reset">입력 비우기</button></div><p class="lg-form-status" role="status" aria-live="polite" data-record-status></p><p class="lg-small">입력 내용은 이 페이지에서만 사용하며 전송하거나 자동 보관하지 않습니다. 페이지를 떠나기 전에 TXT로 저장하세요.</p><noscript><p>입력 내용 저장 기능은 자바스크립트가 필요합니다. 빈 양식을 내려받아 작성할 수 있습니다.</p></noscript></form>
<aside class="lg-next-check"><h3>다음에 확인할 것</h3><p>{esc(guide['followup'])}</p></aside></section>
<section class="lg-section lg-parent-box" id="lg-parent"><p class="lg-step-label">05 · 함께 돕기</p><h2>학부모는 이렇게 도와주세요</h2><p>{esc(guide['parent'])}</p><div class="lg-caution"><strong>적용할 때 확인하세요</strong><p>{esc(guide['caution'])}</p></div></section>
<section class="lg-section lg-faq" id="lg-faq">{faq_alias}<h2>자주 묻는 질문</h2>{faqs_html}</section>
<section class="lg-section lg-references" id="lg-sources"><h2>더 살펴볼 참고 자료</h2><p>아래 자료에서 학습 활동과 질문 구성에 참고할 내용을 확인할 수 있습니다. 실제 시험 범위와 과제 제출 조건은 학교 안내를 우선하세요.</p><ol>{refs}</ol></section>
<section class="lg-section" id="lg-related"><h2>다음 질문에 맞는 가이드</h2>{link_list(guide['related'])}<a class="lg-inline-link" href="/guide/">학습가이드 전체 보기 →</a></section>
</div></article></main>''' + footer()
    write(guide["path"] + "/index.html", page)
    return page


READING_PATHS = [
    ("공부를 시작해도 자꾸 멈춘다면", "최근 답안에서 막힌 부분을 찾고, 작은 계획을 실행한 뒤 다음 과제를 조정합니다.", ["guide/consultation-diagnosis", "guide/study-planner", "교육정보/주간-플래너-점검법"]),
    ("수학 오답이 계속 쌓인다면", "첫 오류를 찾고 필요한 개념을 보완한 뒤, 도움 없이 가능한지를 다시 확인합니다.", ["교육정보/수학-공부법", "교육정보/오답노트-작성법", "guide/error-management"]),
    ("영어를 외워도 문제에서 막힌다면", "어휘를 문장에 연결하고 글의 근거를 읽은 뒤, 답안 조건에 맞춰 직접 써 봅니다.", ["교육정보/영어-단어-암기법", "guide/english-sentence-structure", "교육정보/영어-독해-근거-찾기", "교육정보/영어-서술형-공부법"]),
    ("학교 시험 준비가 막막하다면", "학교 범위와 날짜를 확인하고 기간에 맞는 준비를 한 뒤, 실제 답안으로 다음 계획을 정합니다.", ["guide/exam-period-plan", "교육정보/중학생-시험기간-계획표", "교육정보/시험기간-공부법", "교육정보/시험결과-분석법"]),
    ("본문은 읽었는데 설명이 어렵다면", "읽을 목적과 근거를 찾고, 자료로 말할 수 있는 범위를 정한 뒤 답안을 점검합니다.", ["교육정보/국어-공부법", "guide/korean-written-answer", "guide/science-data", "교육정보/수학-서술형-공부법"]),
    ("상담 전에 무엇을 준비할지 고민된다면", "학생의 설명과 자료를 함께 살펴보고 상담의 대상에 맞는 질문과 수업 조건을 확인합니다.", ["교육정보/부모-자녀-공부-대화", "guide/parent-consultation-checklist", "교육정보/학부모-상담-체크리스트", "교육정보/학원-선택-체크리스트"]),
]


def render_hub(header, education=False):
    path = "교육정보" if education else "guide"
    title = "교육정보, 상황에 맞춰 읽는 학습 순서" if education else "학생·학부모 학습가이드"
    description = "공부 시작·오답·영어·시험·독해·상담의 상황별 읽기 순서를 따라 학습 질문을 정하세요." if education else "학생·학부모를 위한 과목별 공부법과 시험·계획·상담 가이드를 찾고 기록 양식으로 실천하세요."
    canonical = BASE + url(path)
    breadcrumb, breadcrumb_html = crumbs([("홈", ""), ("교육정보" if education else "학습가이드", path)])
    collection = {"@type": "CollectionPage", "@id": canonical + "#page", "name": title, "description": description, "url": canonical, "inLanguage": "ko-KR", "dateModified": DATE, "publisher": ORG}
    page_guides = [g for g in GUIDES if g["path"].startswith("교육정보/")] if education else GUIDES
    items = {"@type": "ItemList", "numberOfItems": len(page_guides), "itemListElement": [{"@type": "ListItem", "position": i, "name": g["title"], "url": BASE + url(g["path"])} for i, g in enumerate(page_guides, 1)]}
    page = head(title, description, canonical, [collection, breadcrumb, items]) + header + f'<main id="main-content"><div class="lg-container">{breadcrumb_html}</div>'
    if education:
        page += '<section class="lg-hub-hero lg-container"><p class="lg-eyebrow">교육정보 / 상황별 읽기 순서</p><h1>지금 겪는 어려움에서<br>다음 질문으로</h1><p class="lg-hub-lead">어떤 글부터 읽을지 고민된다면 지금 상황에 가까운 순서를 골라 보세요.<br>읽은 뒤에는 기록 하나를 남기고 다음 활동에서 확인합니다.</p><a class="lg-button" href="/guide/">전체 65개 학습가이드 찾기 →</a></section>'
        page += '<section class="lg-container lg-hub-section"><p class="lg-eyebrow">상황에 따라 골라 읽기</p><h2>6가지 학습 읽기 순서</h2><div class="lg-path-grid">' + "".join(f'<article class="lg-reading-path"><span class="lg-path-number">{i:02d}</span><h3>{esc(t)}</h3><p>{esc(d)}</p>{link_list(paths)}</article>' for i, (t, d, paths) in enumerate(READING_PATHS, 1)) + '</div></section>'
        page += '<section class="lg-container lg-hub-section"><h2>교육정보 글 전체 보기</h2><p class="lg-section-intro">기존 교육정보 주소에서 각 주제의 실행 방법과 기록 양식을 이어 볼 수 있습니다.</p>'
        for cat, (label, _) in CATEGORIES.items():
            guides = [g for g in page_guides if g["category"] == cat]
            if guides:
                page += f'<section class="lg-education-group"><h3>{esc(label)}</h3>{link_list([g["path"] for g in guides])}</section>'
        page += '</section>'
    else:
        page += '<section class="lg-hub-hero lg-container"><p class="lg-eyebrow">학습가이드 / 학생과 학부모를 위한 65개의 실천 가이드</p><h1>공부가 막힐 때,<br>다음 한 걸음 찾기</h1><p class="lg-hub-lead">과목별 공부법부터 계획·시험·상담까지.<br>지금 필요한 방법을 찾고, 연습하고, 나의 기록으로 확인해 보세요.</p><div class="lg-hero-links"><a class="lg-button" href="#lg-directory">필요한 가이드 찾기 ↓</a><a class="lg-inline-link" href="/교육정보/">상황별 읽기 순서 →</a></div><div class="lg-hub-stats"><span><strong>65</strong> 학습 주제</span><span><strong>6</strong> 분야</span><span><strong>65</strong> 내려받는 기록 양식</span></div></section>'
        featured = [BY_PATH[p] for p in ("guide/retrieval-spaced-review", "guide/learning-workload", "guide/parent-consultation-checklist")]
        page += '<section class="lg-container lg-hub-section lg-featured"><div class="lg-section-heading"><div><p class="lg-eyebrow">어디서 시작할지 고민된다면</p><h2>이 질문부터 살펴보세요</h2></div><p>기억 · 부담 · 상담</p></div><div class="lg-card-grid">' + "".join(card(g) for g in featured) + '</div></section>'
        counts = Counter(g["category"] for g in GUIDES)
        categories = '<button type="button" data-category-filter="all" aria-pressed="true">전체 <span>65</span></button>' + "".join(f'<button type="button" data-category-filter="{key}" aria-pressed="false">{esc(label)} <span>{counts[key]}</span></button>' for key, (label, _) in CATEGORIES.items())
        page += f'''<section class="lg-container lg-hub-section" id="lg-directory" data-guide-directory><p class="lg-eyebrow">주제와 대상에 맞게</p><h2>나에게 필요한 가이드 찾기</h2><p class="lg-section-intro">제목과 설명에서 찾습니다. 예: 오답, 서술형, 단어, 상담</p><div class="lg-filters" hidden data-guide-filters><div class="lg-search-row"><div><label for="lg-search">무엇이 궁금한가요?</label><input id="lg-search" type="search" placeholder="궁금한 주제를 입력하세요" autocomplete="off" data-guide-search></div><div><label for="lg-audience">누구를 위한 가이드인가요?</label><select id="lg-audience" data-guide-audience><option value="all">모든 대상</option>{''.join(f'<option value="{key}">{label}</option>' for key,label in AUDIENCE.items())}</select></div><button class="lg-text-button" type="button" data-reset-filters>선택 초기화</button></div><div class="lg-category-filters" role="group" aria-label="가이드 주제">{categories}</div></div><p class="lg-results-count" role="status" aria-live="polite" data-guide-count>65개의 가이드를 볼 수 있습니다.</p><noscript><p>전체 글을 분야별로 볼 수 있습니다. 검색과 대상 선택은 자바스크립트를 켜면 사용할 수 있습니다.</p></noscript><div class="lg-no-results" hidden data-guide-empty><h3>조건에 맞는 가이드가 없습니다</h3><p>단어를 짧게 바꾸거나 대상·주제 선택을 초기화해 보세요.</p><button class="lg-button lg-button-secondary" type="button" data-reset-filters>전체 가이드 보기</button></div>'''
        for category, (label, subtitle) in CATEGORIES.items():
            selected = [g for g in GUIDES if g["category"] == category]
            page += f'<section class="lg-category-section" data-guide-group><div class="lg-category-heading"><h3>{esc(label)}</h3><p>{esc(subtitle)}</p></div><div class="lg-card-grid">' + "".join(card(g) for g in selected) + '</div></section>'
        page += '</section><section class="lg-container lg-hub-section lg-howto"><h2>읽고 끝내지 않는 세 가지 순서</h2><ol><li><strong>최근 과제 하나 고르기</strong><p>지금 어려운 내용을 실제 자료에서 찾습니다.</p></li><li><strong>한 가지 활동 해 보기</strong><p>가이드의 예시를 자신의 과제에 맞춰 바꿉니다.</p></li><li><strong>기록하고 다시 확인하기</strong><p>도움받은 부분과 혼자 한 부분을 남깁니다.</p></li></ol><p class="lg-small">내용 확인 · 2026-10-02. 각 글에서 더 살펴볼 기관 자료와 적용할 때 확인할 조건을 볼 수 있습니다.</p></section>'
    page += '</main>' + footer()
    write(path + '/index.html', page)
    return description


def update_metadata(descriptions, report_dir):
    config_path = ROOT / 'seo-descriptions.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    for path, description in descriptions.items():
        key = '/' + path
        old = config['pages'].get(key, {})
        config['pages'][key] = dict(old, description=description, sources=list(dict.fromkeys(old.get('sources', []) + ([old['description']] if old.get('description') else []) + [description])))
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    sitemap = etree.parse(str(ROOT / 'sitemap.xml'))
    locations = {unquote(urlparse(e.find('s:loc', ns).text).path).strip('/'): e for e in sitemap.getroot().findall('s:url', ns)}
    for path in descriptions:
        node = locations.get(path)
        if node is None:
            node = etree.SubElement(sitemap.getroot(), '{%s}url' % ns['s'])
            etree.SubElement(node, '{%s}loc' % ns['s']).text = BASE + url(path)
        modified = node.find('s:lastmod', ns)
        if modified is None:
            modified = etree.SubElement(node, '{%s}lastmod' % ns['s'])
        modified.text = DATE
    write('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(sitemap, encoding='unicode'))
    feed = etree.parse(str(ROOT / 'rss.xml'))
    channel = feed.getroot().find('channel')
    # This is an update date, not a fabricated new publication date for older articles.
    feed_date = 'Fri, 02 Oct 2026 09:00:00 +0900'
    channel.find('lastBuildDate').text = feed_date
    existing = {unquote(urlparse(item.findtext('link')).path).strip('/'): item for item in channel.findall('item')}
    for guide in GUIDES:
        item = existing.get(guide['path'])
        new = item is None
        if new:
            item = etree.SubElement(channel, 'item')
            for tag in ('title', 'link', 'guid', 'pubDate', 'description'):
                etree.SubElement(item, tag)
            item.find('guid').set('isPermaLink', 'true')
            if guide['path'].startswith('guide/') and guide['path'] not in existing:
                # Existing guide URLs missing from the feed have no asserted original publication date.
                if guide.get('new'):
                    item.find('pubDate').text = feed_date
                else:
                    item.remove(item.find('pubDate'))
        item.find('title').text = guide['title']
        item.find('link').text = BASE + url(guide['path'])
        item.find('guid').text = BASE + url(guide['path'])
        item.find('description').text = guide['description']
        content = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
        if content is None:
            content = etree.SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded')
        document = html.fromstring((ROOT / guide['path'] / 'index.html').read_bytes())
        # RSS contains readable prose and references, without an unusable interactive form.
        main = copy.deepcopy(document.xpath('//main')[0])
        for form in main.xpath('.//form|.//nav[contains(@class,"lg-toc")]'):
            form.getparent().remove(form)
        for link in main.xpath('.//a[starts-with(@href,"/")]'):
            link.set('href', BASE + link.get('href'))
        for image in main.xpath('.//img[starts-with(@src,"/")]'):
            image.set('src', BASE + quote(image.get('src'), safe='/-'))
        content.text = etree.CDATA(serialize(main))
    write('rss.xml', '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(feed, encoding='unicode'))
    manifest_path = ROOT / 'release-public-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    manifest['updatedDate'] = DATE
    manifest['sitemapPages'] = len(sitemap.getroot().findall('s:url', ns))
    for name in PUBLIC_FILES:
        raw = (ROOT / name).read_bytes()
        manifest['files'][name] = hashlib.sha256(raw).hexdigest()
        normalized = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
        # Builder normalizes line endings but preserves a TXT BOM; include the BOM in its LF digest.
        if raw.startswith(b'\xef\xbb\xbf'):
            normalized = b'\xef\xbb\xbf' + normalized
        manifest.setdefault('textSha256', {})[name] = hashlib.sha256(normalized).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (report_dir / 'changed-html.json').write_text(json.dumps(HTML_FILES, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_dir / 'changed-public-files.json').write_text(json.dumps(PUBLIC_FILES, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_dir / 'guide-catalog.json').write_text(json.dumps(GUIDES, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_dir / 'original-content-reuse.json').write_text(json.dumps(EXTRACT_REPORT, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, default=ROOT / 'tools/learning-guides-baseline.zip')
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    assert len(GUIDES) == 65 and len(BY_PATH) == 65
    assert len({g['title'] for g in GUIDES}) == 65
    assert len({g['description'] for g in GUIDES}) == 65
    for guide in GUIDES:
        assert len(guide['description']) <= 80 and guide['description'].endswith('.'), guide['path']
        assert len(guide['fields']) == 4 and len(guide['checks']) == 2
        assert len(guide['related']) == 3 and all(p in BY_PATH and p != guide['path'] for p in guide['related']), guide['path']
        assert all(s in SOURCES for s in guide['sources'])
    with zipfile.ZipFile(args.baseline) as baseline:
        header_guide = serialize(html.fromstring(baseline.read('guide/study-planner/index.html')).xpath('//header')[0])
        header_education = serialize(html.fromstring(baseline.read('교육정보/영어-단어-암기법/index.html')).xpath('//header')[0])
        original_articles = {n.removesuffix('/index.html') for n in baseline.namelist() if n.count('/') == 2}
        assert original_articles.issubset(BY_PATH), original_articles.difference(BY_PATH)
        for guide in GUIDES:
            name = guide['path'] + '/index.html'
            original = html.fromstring(baseline.read(name)) if name in baseline.namelist() else None
            guide['new'] = original is None
            render_article(guide, original, header_education if guide['path'].startswith('교육정보/') else header_guide)
        descriptions = {g['path']: g['description'] for g in GUIDES}
        descriptions['guide'] = render_hub(header_guide)
        descriptions['교육정보'] = render_hub(header_education, education=True)
    for asset in ('assets/learning-guides.css', 'assets/learning-guides.js'):
        assert (ROOT / asset).exists(), asset
        PUBLIC_FILES.append(asset)
    update_metadata(descriptions, args.report_dir)
    print(json.dumps({'articles': len(GUIDES), 'existing': sum(not g['new'] for g in GUIDES), 'new': sum(g['new'] for g in GUIDES), 'htmlFiles': len(HTML_FILES), 'publicFilesUpdated': len(PUBLIC_FILES), 'categories': dict(Counter(g['category'] for g in GUIDES)), 'report': str(args.report_dir)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
