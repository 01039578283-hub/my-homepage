"""Generate neighborhood topic pages below the reviewed branch directory.

The supplied ZIP files are treated as manuscript data only.  This generator
parses their labelled fields, connects each neighborhood to the verified
branch manifest, and avoids claiming a course is open when the current center
data does not list the requested school level and subject.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import date
from html import escape
from pathlib import Path, PurePosixPath
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
BRANCH_MANIFEST = ROOT / "tools" / "data" / "branch-directory" / "branches.json"
DATA_ROOT = ROOT / "tools" / "data" / "branch-topic-pages"
REPORT_ROOT = ROOT / "reports" / "branch-topic-pages"
SITEMAP = ROOT / "sitemap.xml"

DOMAIN = "https://wawa-center.kr"
PHONE_DISPLAY = "010-3957-8283"
PHONE_LINK = "01039578283"
CONSULT_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform"
TODAY = date.today().isoformat()

MANUSCRIPT_ROOT = Path(r"C:\Users\1992k\Desktop\프로그램 원고")
TOPICS = [
    {"level": "초등", "subject": "수학", "zip": "초등 수학학원.zip", "prefix": "초"},
    {"level": "초등", "subject": "영어", "zip": "초등 영어학원.zip", "prefix": "초"},
    {"level": "중등", "subject": "수학", "zip": "중등 수학학원.zip", "prefix": "중"},
    {"level": "중등", "subject": "영어", "zip": "중등 영어학원.zip", "prefix": "중"},
    {"level": "고등", "subject": "수학", "zip": "고등 수학학원.zip", "prefix": "고"},
    {"level": "고등", "subject": "영어", "zip": "고등 영어학원.zip", "prefix": "고"},
]


def clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def encoded_url(path: str) -> str:
    return DOMAIN + quote(path, safe="/#")


def clean_html(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()) + "\n"


def labelled_section(text: str, label: str) -> str:
    pattern = rf"(?ms)^\[{re.escape(label)}\]\s*\n(.*?)(?=^\[[^\]]+\]\s*$|\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def split_paragraphs(text: str) -> list[str]:
    return [clean(part) for part in re.split(r"\n\s*\n", text) if clean(part)]


def parse_article(body: str) -> tuple[list[str], list[dict[str, object]]]:
    intro: list[str] = []
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            heading, _, remainder = block.partition("\n")
            current = {"heading": clean(heading[3:]), "paragraphs": []}
            sections.append(current)
            if clean(remainder):
                current["paragraphs"].append(clean(remainder))
            continue
        paragraph = clean(block)
        if current is None:
            intro.append(paragraph)
        else:
            current["paragraphs"].append(paragraph)
    return intro, sections


def parse_faq(text: str) -> list[dict[str, str]]:
    items = []
    pattern = r"(?ms)^Q\d+\.\s*(.*?)\nA\d+\.\s*(.*?)(?=^Q\d+\.|\Z)"
    for question, answer in re.findall(pattern, text.strip()):
        items.append({"question": clean(question), "answer": clean(answer)})
    return items


def parse_manuscript(text: str, expected_level: str, expected_subject: str) -> dict[str, object]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    title = clean(labelled_section(text, "페이지타이틀"))
    description = clean(labelled_section(text, "메타설명"))
    body = labelled_section(text, "본문")
    faq = parse_faq(labelled_section(text, "FAQ"))
    example = split_paragraphs(labelled_section(text, "학부모후기"))
    json_summary = clean(labelled_section(text, "JSON-LD 요약"))
    intro, sections = parse_article(body)
    match = re.match(rf"(.+?)\s+{expected_level}\s+{expected_subject}학원$", title)
    if not match:
        raise ValueError(f"원고 제목 형식이 맞지 않습니다: {title}")
    if not description or not sections or len(faq) < 3:
        raise ValueError(f"원고 필수 구성이 부족합니다: {title}")
    return {
        "title": title,
        "description": description,
        "locality": match.group(1).strip(),
        "intro": intro,
        "sections": sections,
        "faq": faq,
        "example": example,
        "abstract": json_summary or description,
    }


def load_manuscripts() -> dict[tuple[str, str, str], dict[str, object]]:
    manuscripts: dict[tuple[str, str, str], dict[str, object]] = {}
    for topic in TOPICS:
        archive_path = MANUSCRIPT_ROOT / topic["zip"]
        if not archive_path.is_file():
            raise FileNotFoundError(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith(".txt"):
                    continue
                text = archive.read(member).decode("utf-8-sig")
                item = parse_manuscript(text, topic["level"], topic["subject"])
                filename = PurePosixPath(member).stem
                expected = f'{item["locality"]} {topic["level"]} {topic["subject"]}학원'
                if clean(filename) != expected:
                    raise ValueError(f"파일명과 제목 지역이 다릅니다: {member} / {expected}")
                key = (item["locality"], topic["level"], topic["subject"])
                if key in manuscripts:
                    raise ValueError(f"중복 원고: {key}")
                item["level"] = topic["level"]
                item["subject"] = topic["subject"]
                item["prefix"] = topic["prefix"]
                item["sourceZip"] = topic["zip"]
                manuscripts[key] = item
    return manuscripts


def branch_topic_slug(locality: str, level: str, subject: str) -> str:
    return f"{locality}{level}{subject}학원"


def topic_path(center: dict[str, object], locality: str, level: str, subject: str) -> str:
    slug = branch_topic_slug(locality, level, subject)
    return f'/지점안내/{center["region"]}/{center["routeName"]}/{slug}/'


def course_recorded(center: dict[str, object], prefix: str, subject: str) -> bool:
    return any(grade.startswith(prefix) for grade in center.get("subjects", {}).get(subject, []))


def subject_hub(subject: str, level: str) -> tuple[str, str]:
    exact = ROOT / "과목별학원" / f"{level}{subject}학원" / "index.html"
    if exact.exists():
        return f"{level} {subject}학원 허브", f"/과목별학원/{level}{subject}학원/"
    return f"{subject}학원 허브", f"/과목별학원/{subject}학원/"


def responsive_picture(media: dict[str, object], alt: str) -> str:
    avif = ", ".join(f'{item["src"]} {item["width"]}w' for item in media.get("variants", {}).get("avif", []))
    webp = ", ".join(f'{item["src"]} {item["width"]}w' for item in media.get("variants", {}).get("webp", []))
    sizes = "(max-width: 760px) calc(100vw - 32px), 760px"
    return (
        f'<picture>'
        f'<source type="image/avif" srcset="{esc(avif)}" sizes="{sizes}">'
        f'<source type="image/webp" srcset="{esc(webp)}" sizes="{sizes}">'
        f'<img src="{esc(media["src"])}" width="{media["width"]}" height="{media["height"]}" '
        f'alt="{esc(alt)}" loading="lazy" decoding="async" fetchpriority="low">'
        f'</picture>'
    )


def media_markup(center: dict[str, object], title: str) -> str:
    media = center["primaryMedia"]
    representative = media["representative"]
    body = media["body"]
    map_asset = media["map"]
    return f'''<section class="branch-primary-media" aria-label="{esc(title)} 본문 및 지도 이미지">
  <img class="branch-representative-image" src="{esc(representative["src"])}" width="{representative["width"]}" height="{representative["height"]}" alt="{esc(title)} 와와학습코칭센터 대표" style="display:none;" loading="lazy" decoding="async">
  <figure class="branch-body-image">{responsive_picture(body, title + " 본문")}<figcaption>{esc(center["region"])} 지역 학습코칭·수업 안내</figcaption></figure>
  <figure class="branch-map-image"><img src="{esc(map_asset["src"])}" width="{map_asset["width"]}" height="{map_asset["height"]}" alt="{esc(title)} 지도" loading="lazy" decoding="async"><figcaption>{esc(center["routeName"])} 위치 참고 지도 · 방문 전 주소와 운영 여부를 다시 확인해 주세요.</figcaption></figure>
</section>'''


def header() -> str:
    return '''<header class="site-header"><nav class="nav" aria-label="주요 메뉴"><a class="logo" href="/"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a><div class="nav-links" aria-label="페이지 이동"><a href="/">홈</a><a href="/overview/">학원소개</a><a href="/guide/">학습가이드</a><a href="/교육정보/">교육정보</a><a href="/학부모후기/">학부모후기</a><a href="/과목별학원/">과목별학원</a><a href="/학년별학원/">학년별학원</a><a class="active" href="/지점안내/">지점안내</a></div></nav></header>'''


def footer() -> str:
    return f'''<footer class="branch-footer"><strong>와와학습코칭센터</strong><p>센터별 운영 과목·학년·요일은 다를 수 있으므로 방문 전 상담에서 확인해 주세요.</p><a href="tel:{PHONE_LINK}">{PHONE_DISPLAY}</a></footer>
<div class="wawa-fixed-fab-container" aria-label="빠른 상담"><a href="tel:{PHONE_DISPLAY}" class="wawa-fab-item fab-call"><span class="fab-icon" aria-hidden="true">☎</span><span class="fab-text">전화문의</span></a><a href="https://blogsms.net/{PHONE_LINK}" target="_blank" rel="noopener noreferrer" class="wawa-fab-item fab-sms"><span class="fab-icon" aria-hidden="true">✉</span><span class="fab-text">문자문의</span></a><a href="{CONSULT_URL}" target="_blank" rel="noopener noreferrer" class="wawa-fab-item fab-consult"><span class="fab-icon" aria-hidden="true">✓</span><span class="fab-text">상담신청</span></a></div>'''


def breadcrumb(center: dict[str, object], title: str) -> str:
    return f'''<nav class="branch-breadcrumb" aria-label="현재 위치"><ol><li><a href="/">홈</a></li><li><a href="/지점안내/">지점안내</a></li><li><a href="/지점안내/{esc(center["region"])}/">{esc(center["region"])}</a></li><li><a href="/지점안내/{esc(center["region"])}/{esc(center["routeName"])}/">{esc(center["routeName"])}</a></li><li><span aria-current="page">{esc(title)}</span></li></ol></nav>'''


def article_markup(item: dict[str, object]) -> str:
    blocks = []
    if item["intro"]:
        blocks.append('<section aria-labelledby="article-intro-title"><h2 id="article-intro-title">학습 안내 핵심 정리</h2>' + "".join(f'<p>{esc(p)}</p>' for p in item["intro"]) + "</section>")
    for index, section in enumerate(item["sections"], start=1):
        paragraphs = "".join(f'<p>{esc(p)}</p>' for p in section["paragraphs"])
        blocks.append(f'<section id="article-{index:02d}" aria-labelledby="article-{index:02d}-title"><h2 id="article-{index:02d}-title">{esc(section["heading"])}</h2>{paragraphs}</section>')
    return '<div class="branch-topic-article" id="article">' + "".join(blocks) + "</div>"


def faq_markup(item: dict[str, object]) -> str:
    details = "".join(f'<details><summary>{esc(entry["question"])}</summary><p>{esc(entry["answer"])}</p></details>' for entry in item["faq"])
    return f'<section class="branch-section branch-faq" id="faq" aria-labelledby="topic-faq-title"><div class="branch-section-head"><p class="branch-kicker">FAQ</p><h2 id="topic-faq-title">{esc(item["title"])} 자주 묻는 질문</h2></div>{details}</section>'


def example_markup(item: dict[str, object]) -> str:
    if not item["example"]:
        return ""
    paragraphs = "".join(f'<p>{esc(p)}</p>' for p in item["example"])
    return f'<section class="branch-section branch-topic-example" aria-labelledby="topic-example-title"><div class="branch-section-head"><p class="branch-kicker">CONSULTATION EXAMPLE</p><h2 id="topic-example-title">상담 준비 상황 예시</h2><p>상담할 질문과 확인 자료를 구체화하기 위한 가상 상황 예시입니다.</p></div>{paragraphs}</section>'


def related_markup(center: dict[str, object], item: dict[str, object]) -> tuple[str, list[dict[str, object]]]:
    locality = item["locality"]
    level = item["level"]
    subject = item["subject"]
    links: list[tuple[str, str, str]] = []
    for topic in TOPICS:
        if topic["level"] == level and topic["subject"] == subject:
            continue
        path = topic_path(center, locality, topic["level"], topic["subject"])
        links.append((f'{locality} {topic["level"]} {topic["subject"]}학원', path, "같은 동네의 다른 학교급·과목 안내"))
    links.append((f'{center["routeName"]} 지점안내', f'/지점안내/{center["region"]}/{center["routeName"]}/', "주소·가능 과목·학년·인근 학교 확인"))
    hub_label, hub_path = subject_hub(subject, level)
    links.append((hub_label, hub_path, "과목별 학습관리 기준 확인"))
    for other in center["neighborhoods"]:
        if other == locality:
            continue
        links.append((f"{other} {level} {subject}학원", topic_path(center, other, level, subject), "같은 센터의 다른 수업 가능 동네"))
    links = links[:9]
    cards = "".join(f'<a href="{esc(path)}"><strong>{esc(label)}</strong><span>{esc(copy)}</span></a>' for label, path, copy in links)
    schema = [{"@type": "ListItem", "position": index + 1, "name": label, "url": encoded_url(path)} for index, (label, path, _) in enumerate(links)]
    markup = f'<section class="branch-section branch-related branch-topic-related" id="related-pages" aria-labelledby="topic-related-title"><div class="branch-section-head"><p class="branch-kicker">RELATED PAGES</p><h2 id="topic-related-title">함께 확인할 학습 안내</h2></div><div class="related-grid">{cards}</div></section>'
    return markup, schema


def schema_graph(center: dict[str, object], item: dict[str, object], path: str, available: bool, related_schema: list[dict[str, object]]) -> list[dict[str, object]]:
    page_url = encoded_url(path)
    parent_path = f'/지점안내/{center["region"]}/{center["routeName"]}/'
    parent_url = encoded_url(parent_path)
    media = center["primaryMedia"]
    image_urls = [DOMAIN + quote(media[kind]["src"], safe="/") for kind in ("representative", "body", "map")]
    crumbs = [
        ("홈", "/"), ("지점안내", "/지점안내/"),
        (center["region"], f'/지점안내/{center["region"]}/'),
        (center["routeName"], parent_path), (item["title"], path),
    ]
    academy_id = parent_url + "#academy"
    graph: list[dict[str, object]] = [
        {"@type": "WebSite", "@id": DOMAIN + "/#website", "url": DOMAIN + "/", "name": "와와학습코칭센터", "inLanguage": "ko-KR"},
        {"@type": "WebPage", "@id": page_url + "#webpage", "url": page_url, "name": item["title"], "description": item["description"], "inLanguage": "ko-KR", "isPartOf": {"@id": DOMAIN + "/#website"}, "breadcrumb": {"@id": page_url + "#breadcrumb"}, "mainEntity": {"@id": page_url + "#article"}, "primaryImageOfPage": {"@type": "ImageObject", "url": image_urls[0]}, "about": [{"@id": academy_id}, {"@type": "Place", "name": item["locality"]}, {"@type": "Thing", "name": f'{item["level"]} {item["subject"]} 학습'}], "mentions": [{"@type": "Place", "name": center["region"]}, {"@type": "Place", "name": center["district"]}, {"@type": "Thing", "name": "학습 진단"}, {"@type": "Thing", "name": "오답 재학습"}]},
        {"@type": "BreadcrumbList", "@id": page_url + "#breadcrumb", "itemListElement": [{"@type": "ListItem", "position": index + 1, "name": name, "item": encoded_url(url)} for index, (name, url) in enumerate(crumbs)]},
        {"@type": ["EducationalOrganization", "LocalBusiness"], "@id": academy_id, "name": center["displayName"], "legalName": center["registeredName"], "url": parent_url, "address": {"@type": "PostalAddress", "streetAddress": center["address"], "addressRegion": center["region"], "addressLocality": center["district"], "addressCountry": "KR"}, "identifier": center["registrationNumber"], "areaServed": [{"@type": "Place", "name": name} for name in center["neighborhoods"]], "additionalProperty": {"@type": "PropertyValue", "name": "센터 정보 확인 기준일", "value": center["informationReviewedAt"]}},
        {"@type": "Article", "@id": page_url + "#article", "headline": item["title"], "description": item["description"], "abstract": item["abstract"], "inLanguage": "ko-KR", "datePublished": TODAY, "dateModified": TODAY, "mainEntityOfPage": {"@id": page_url + "#webpage"}, "author": {"@id": DOMAIN + "/#organization"}, "publisher": {"@id": DOMAIN + "/#organization"}, "about": [{"@type": "Place", "name": item["locality"]}, {"@type": "Thing", "name": f'{item["level"]} {item["subject"]} 학습'}], "articleSection": [section["heading"] for section in item["sections"]], "image": image_urls},
        {"@type": "FAQPage", "@id": page_url + "#faq", "mainEntity": [{"@type": "Question", "name": faq["question"], "acceptedAnswer": {"@type": "Answer", "text": faq["answer"]}} for faq in item["faq"]]},
        {"@type": "ItemList", "@id": page_url + "#related-pages", "name": f'{item["title"]} 관련 안내', "numberOfItems": len(related_schema), "itemListElement": related_schema},
    ]
    if available:
        graph.append({"@type": "Service", "@id": page_url + "#service", "name": f'{item["locality"]} {item["level"]} {item["subject"]} 학습 상담', "serviceType": f'{item["level"]} {item["subject"]} 학습코칭', "provider": {"@id": academy_id}, "areaServed": {"@type": "Place", "name": item["locality"]}, "audience": {"@type": "EducationalAudience", "educationalRole": "student"}, "offers": {"@type": "Offer", "availability": "https://schema.org/InStock", "url": page_url}})
    return graph


def render_page(center: dict[str, object], item: dict[str, object]) -> tuple[str, str]:
    path = topic_path(center, item["locality"], item["level"], item["subject"])
    page_url = encoded_url(path)
    title = item["title"]
    description = item["description"]
    available = course_recorded(center, item["prefix"], item["subject"])
    availability = (
        f'제공된 센터 자료에 {item["level"]} {item["subject"]} 가능 학년이 기록돼 있습니다.'
        if available else
        f'제공된 센터 자료에는 {item["level"]} {item["subject"]} 개설 여부가 기록돼 있지 않습니다. 이 페이지는 학습 선택 정보이며 실제 수업 여부는 상담에서 확인해 주세요.'
    )
    related, related_schema = related_markup(center, item)
    graph = schema_graph(center, item, path, available, related_schema)
    schema = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))
    school_names = center.get("schools", {}).get(item["level"], [])
    schools = " · ".join(school_names[:10]) if school_names else "상담에서 학교와 학년 확인"
    html = f'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} | {esc(center["routeName"])} 학습 안내</title>
  <meta name="description" content="{esc(description)}">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <link rel="canonical" href="{esc(page_url)}">
  <link rel="icon" type="image/png" href="/assets/favicon.png">
  <link rel="apple-touch-icon" href="/assets/favicon.png">
  <link rel="alternate" type="application/rss+xml" href="{DOMAIN}/rss.xml" title="와와학습코칭센터 RSS">
  <meta property="og:locale" content="ko_KR">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="와와학습코칭센터">
  <meta property="og:title" content="{esc(title)} | {esc(center["routeName"])} 학습 안내">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{esc(page_url)}">
  <meta property="og:image" content="{DOMAIN}{esc(center["primaryMedia"]["representative"]["src"])}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="/assets/header.css">
  <link rel="stylesheet" href="/assets/fab.css">
  <link rel="stylesheet" href="/assets/branch-directory.css?v=20260920c">
  <script type="application/ld+json">{schema}</script>
</head>
<body class="branch-directory-page branch-topic-page">
{header()}
{breadcrumb(center, title)}
<main id="main" class="branch-shell">
<section class="branch-topic-hero">
  <p class="branch-kicker">{esc(center["region"])} · {esc(center["district"])} · {esc(center["routeName"])} LEARNING GUIDE</p>
  <h1>{esc(title)}</h1>
  <p class="branch-lead">{esc(description)}</p>
  <dl class="branch-topic-status"><div><dt>연결 센터</dt><dd>{esc(center["displayName"])}</dd></div><div><dt>개설 자료 확인</dt><dd>{esc(availability)}</dd></div><div><dt>정보 확인 기준일</dt><dd>{esc(center["informationReviewedAt"])} · 제공 자료 기준</dd></div></dl>
  <div class="branch-hero-actions"><a class="branch-button primary" href="#overview">핵심 안내</a><a class="branch-button" href="/지점안내/{esc(center["region"])}/{esc(center["routeName"])}/">{esc(center["routeName"])} 지점안내</a></div>
</section>
{media_markup(center, title)}
<nav class="branch-toc" aria-label="페이지 목차"><strong>목차</strong><a href="#overview">핵심 안내</a><a href="#center-reference">센터 정보</a><a href="#article">본문</a><a href="#faq">FAQ</a><a href="#related-pages">관련 페이지</a></nav>
<section class="branch-answer" id="overview"><p class="branch-kicker">QUICK ANSWER</p><h2>{esc(title)} 핵심 안내</h2><p>{esc(description)}</p><p>{esc(availability)}</p></section>
<section class="branch-section" id="center-reference" aria-labelledby="center-reference-title"><div class="branch-section-head"><p class="branch-kicker">CENTER REFERENCE</p><h2 id="center-reference-title">{esc(center["routeName"])} 기준 확인 정보</h2><p>원고의 학습 선택 기준과 센터 제공 자료를 구분해 확인할 수 있도록 정리했습니다.</p></div><dl class="info-list"><div><dt>주소</dt><dd>{esc(center["address"])}</dd></div><div><dt>등록 명칭</dt><dd>{esc(center["registeredName"])}</dd></div><div><dt>{esc(item["level"])} 인근 학교</dt><dd>{esc(schools)}</dd></div><div><dt>정보 확인 기준일</dt><dd>{esc(center["informationReviewedAt"])} · 제공 자료 기준</dd></div></dl></section>
{article_markup(item)}
{example_markup(item)}
{faq_markup(item)}
{related}
<section class="branch-section consult-section" aria-labelledby="topic-consult-title"><div class="branch-section-head"><p class="branch-kicker">CONSULTATION</p><h2 id="topic-consult-title">수업 가능 여부와 학습 계획 확인</h2><p>현재 학교·학년, 최근 시험지, 사용 교재와 희망 요일을 알려주면 상담 범위를 구체적으로 확인하기 좋습니다.</p></div><div class="consult-cta"><div><strong>{esc(center["displayName"])} 상담</strong><p>개설 과목·학년과 시간표는 상담에서 최종 확인해 주세요.</p></div><a class="branch-button primary" href="{CONSULT_URL}" target="_blank" rel="noopener noreferrer">상담 신청</a></div></section>
</main>
{footer()}
</body>
</html>'''
    output = ROOT / path.strip("/") / "index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(clean_html(html), encoding="utf-8")
    return path, str(output.relative_to(ROOT))


def delete_previous_pages() -> None:
    manifest = DATA_ROOT / "pages.json"
    if not manifest.exists():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for item in data.get("pages", []):
        page_file = ROOT / item["file"]
        page_dir = page_file.parent.resolve()
        if page_file.name != "index.html" or "지점안내" not in page_dir.parts:
            continue
        if page_file.exists():
            page_file.unlink()
        if page_dir.exists() and not any(page_dir.iterdir()):
            page_dir.rmdir()


def update_sitemap(paths: list[str]) -> None:
    text = SITEMAP.read_text(encoding="utf-8")
    start = "  <!-- branch-topic-pages:start -->"
    end = "  <!-- branch-topic-pages:end -->"
    text = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\s*", "", text, flags=re.S)
    entries = [f"  <url>\n    <loc>{encoded_url(path)}</loc>\n    <lastmod>{TODAY}</lastmod>\n  </url>" for path in paths]
    block = start + "\n" + "\n".join(entries) + "\n" + end + "\n"
    text = text.replace("</urlset>", block + "</urlset>")
    SITEMAP.write_text(text, encoding="utf-8")


def main() -> None:
    branch_data = json.loads(BRANCH_MANIFEST.read_text(encoding="utf-8"))
    centers = branch_data["centers"]
    manuscripts = load_manuscripts()
    neighborhood_map = {}
    for center in centers:
        for locality in center.get("neighborhoods", []):
            if locality in neighborhood_map:
                raise ValueError(f"동네가 둘 이상의 지점에 연결되었습니다: {locality}")
            neighborhood_map[locality] = center

    delete_previous_pages()
    pages = []
    skipped = []
    for key in sorted(manuscripts):
        item = manuscripts[key]
        center = neighborhood_map.get(item["locality"])
        if not center:
            skipped.append({
                "locality": item["locality"], "level": item["level"],
                "subject": item["subject"], "title": item["title"],
                "reason": "현재 지점 원본에 대응 센터가 없음",
            })
            continue
        path, file_name = render_page(center, item)
        pages.append({
            "path": path, "file": file_name, "title": item["title"],
            "locality": item["locality"], "level": item["level"],
            "subject": item["subject"], "center": center["routeName"],
            "availableInCenterData": course_recorded(center, item["prefix"], item["subject"]),
            "informationReviewedAt": center["informationReviewedAt"],
        })

    paths = [item["path"] for item in pages]
    update_sitemap(paths)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": TODAY,
        "pageCount": len(pages),
        "sourceManuscriptCount": len(manuscripts),
        "skippedCount": len(skipped),
        "pages": pages,
        "skipped": skipped,
    }
    (DATA_ROOT / "pages.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "generatedAt": TODAY,
        "pageCount": len(pages),
        "availableRecorded": sum(item["availableInCenterData"] for item in pages),
        "availabilityConfirmationNeeded": sum(not item["availableInCenterData"] for item in pages),
        "skipped": skipped,
    }
    (REPORT_ROOT / "generation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
