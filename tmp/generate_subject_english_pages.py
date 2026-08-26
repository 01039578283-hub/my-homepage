from __future__ import annotations

import hashlib
import html
import json
import random
import re
import shutil
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SITE_URL = "https://wawa-center.kr"
SITE_NAME = "와와학습코칭센터"
TITLE_SUFFIX = "와와학습코칭센터 영어수학 전문학원"
TODAY = "2026-07-21"
MATH_ROOT = ROOT / "과목별학원" / "수학학원"
ENGLISH_ROOT = ROOT / "과목별학원" / "영어학원"
REP_SOURCE = ROOT.parent / "참고자료" / "공통자료" / "대표이미지"
REP_DEST = ROOT / "assets" / "representative-english"
ZIP_PATH = Path.home() / "Desktop" / "wawa-center.kr 추가 원고" / "영어학원.zip"


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def encoded_url(*parts: str) -> str:
    encoded = "/".join(quote(part, safe="") for part in parts)
    return f"{SITE_URL}/{encoded}/"


def parse_manuscript(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^\[([^\]]+)\]\s*$", text, re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[match.end() : end].strip()
    return sections


def parse_body(body: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    parts = re.split(r"^##\s+(.+?)\s*$", body.strip(), flags=re.MULTILINE)
    intro = [item.strip() for item in re.split(r"\n\s*\n", parts[0]) if item.strip()]
    sections: list[tuple[str, list[str]]] = []
    for index in range(1, len(parts), 2):
        heading = parts[index].strip()
        content = parts[index + 1].strip() if index + 1 < len(parts) else ""
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", content) if item.strip()]
        sections.append((heading, paragraphs))
    return intro, sections


def parse_faqs(text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r"^Q\d+\.\s*(.*?)\s*\nA\d+\.\s*(.*?)(?=^Q\d+\.|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    return [
        {"question": re.sub(r"\s+", " ", q).strip(), "answer": re.sub(r"\s+", " ", a).strip()}
        for q, a in pattern.findall(text.strip())
    ]


def parse_reviews(text: str) -> list[dict[str, str]]:
    pattern = re.compile(r"^후기 예시\s*\d+｜\s*(.*?)(?=^후기 예시\s*\d+｜|\Z)", re.MULTILINE | re.DOTALL)
    reviews = []
    for raw in pattern.findall(text.strip()):
        value = re.sub(r"\s+", " ", raw).strip()
        if ":" in value:
            label, content = value.split(":", 1)
        else:
            label, content = "학부모 상담 사례", value
        reviews.append({"label": label.strip(), "content": content.strip()})
    return reviews


def naturalize_text(text: str, local: str) -> str:
    """Remove mechanical lead-ins without changing facts or instructional meaning."""
    value = text
    value = value.replace("학부모님이 학부모가 빠르게 확인할 대목은", "학부모님이 빠르게 확인할 대목은")
    value = value.replace("초을 기준", "초를 기준")
    value = value.replace("고을 기준", "고를 기준")
    value = value.replace("학교을", "학교를")
    value = value.replace("학원로 제공", "학원으로 안내")
    value = value.replace(
        f"{local} 영어학원을 찾는 학부모를 위한 정보성 페이지입니다.",
        f"{local} 영어학원 상담 전에 확인할 내용을 정리했습니다.",
    )

    patterns = [
        f"{local} 영어학원 페이지에서는,",
        f"{local} 영어학원 기준으로 보면,",
        f"{local} 영어 학습 상황에 맞춰 보면,",
        f"{local} 학부모가 확인할 때는,",
        f"{local} 영어학원을 검토하는 경우,",
        f"{local} 영어학원 상담 맥락에서는,",
    ]
    alternatives = [
        f"{local} 영어학원을 살펴보면,",
        f"{local}에서 영어 학습을 계획할 때는,",
        f"{local} 영어 상담에서 중요한 점은,",
        "학생의 현재 영어 학습 흐름을 기준으로 보면,",
        "실제 상담 질문으로 바꾸어 보면,",
        "영어 수업의 진행 과정을 확인하면,",
        "학교 학습과 복습을 함께 놓고 보면,",
        "학생이 혼자 공부하는 시간까지 고려하면,",
        "수업 선택 기준을 구체적으로 정리하면,",
        "최근 시험지와 학습 기록을 중심으로 보면,",
        "학부모 상담에서 이 부분을 확인하려면,",
        "영어 학습의 다음 단계를 정할 때는,",
        "교재 진도보다 학습 과정을 먼저 보면,",
        "학생에게 필요한 도움을 구분해 보면,",
        "학년별 목표와 현재 상태를 함께 보면,",
        "상담 내용을 실제 계획으로 연결하려면,",
        "영어 학습 습관을 점검하는 관점에서는,",
        "수업 이후의 복습까지 확인해 보면,",
    ]
    occurrence = 0
    base = int.from_bytes(hashlib.sha256(local.encode("utf-8")).digest()[:4], "big") % len(alternatives)
    combined = re.compile("|".join(re.escape(pattern) for pattern in patterns))

    def replace_lead_in(_: re.Match[str]) -> str:
        nonlocal occurrence
        replacement = alternatives[(base + occurrence * 5) % len(alternatives)]
        occurrence += 1
        return replacement

    value = combined.sub(replace_lead_in, value)
    return value


def load_manuscripts() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    with ZipFile(ZIP_PATH) as archive:
        for name in archive.namelist():
            if not name.endswith(".txt"):
                continue
            sections = parse_manuscript(archive.read(name).decode("utf-8-sig"))
            title = sections.get("페이지타이틀", "").strip()
            local = re.sub(r"\s*영어학원\s*$", "", title).strip()
            sections = {
                key: value if key == "페이지타이틀" else naturalize_text(value, local)
                for key, value in sections.items()
            }
            intro, body_sections = parse_body(sections.get("본문", ""))
            result[local] = {
                "title": title,
                "meta": sections.get("메타설명", "").strip(),
                "intro": intro,
                "sections": body_sections,
                "faqs": parse_faqs(sections.get("FAQ", "")),
                "reviews": parse_reviews(sections.get("학부모후기", "")),
                "summary": sections.get("JSON-LD 요약", "").strip(),
            }
    return result


def first_json_ld(source: str) -> dict[str, object]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError("JSON-LD block not found")
    return json.loads(match.group(1))


def graph_item(graph: list[dict[str, object]], type_name: str) -> dict[str, object]:
    for item in graph:
        if item.get("@type") == type_name:
            return item
    raise ValueError(f"{type_name} not found")


def extract_tags(source: str, label_pattern: str) -> list[str]:
    match = re.search(
        rf"<dt>{label_pattern}</dt><dd><div class=\"math-tag-list\">(.*?)</div></dd>",
        source,
        re.DOTALL,
    )
    if not match:
        return []
    return [html.unescape(value).strip() for value in re.findall(r"<span>(.*?)</span>", match.group(1), re.DOTALL)]


def extract_center_data(local: str) -> dict[str, object]:
    page_path = MATH_ROOT / local / "index.html"
    source = page_path.read_text(encoding="utf-8")
    data = first_json_ld(source)
    graph = data.get("@graph", [])
    organization = graph_item(graph, "EducationalOrganization")
    web_page = graph_item(graph, "WebPage")
    item_list = graph_item(graph, "ItemList")
    address = dict(organization.get("address", {}))
    links = item_list.get("itemListElement", [])
    center_url = next((item.get("url", "") for item in links if "/center/" in str(item.get("url", ""))), "")
    images = re.findall(r'<img\b[^>]*src="([^"]+)"[^>]*>', source, re.IGNORECASE)
    if len(images) < 3:
        raise ValueError(f"{local}: image mapping not found")
    tuition_match = re.search(r'class="math-tuition-link"\s+href="([^"]+)"', source)
    identifier = organization.get("identifier") if isinstance(organization.get("identifier"), dict) else None
    schools = extract_tags(source, "제공 학교 참고")
    grades = extract_tags(source, "수학 수업 가능 학년") or list(organization.get("educationalLevel", []))
    return {
        "organization_name": organization.get("name", f"{SITE_NAME} {local}점"),
        "telephone": organization.get("telephone", "010-3957-8283"),
        "address": address,
        "region": address.get("addressRegion", ""),
        "city": address.get("addressLocality", ""),
        "street_address": address.get("streetAddress", ""),
        "opening_hours": organization.get("openingHoursSpecification", []),
        "identifier": identifier,
        "grades": grades,
        "schools": schools,
        "tuition_url": html.unescape(tuition_match.group(1)) if tuition_match else "",
        "center_url": center_url,
        "body_image": images[1],
        "map_image": images[2],
        "source_mentions": web_page.get("mentions", []),
    }


def ordered_locals_and_directory() -> tuple[list[str], str]:
    source = (MATH_ROOT / "index.html").read_text(encoding="utf-8")
    start = source.index('<div class="math-region-list">')
    marker = '</div></div></section>\n    <section class="math-section"><div class="math-narrow math-links-card">'
    end = source.index(marker, start)
    directory = source[start : end + len("</div>")]
    locals_in_order = [html.unescape(value) for value in re.findall(r'href="\./([^"/]+)/" data-local=', directory)]
    return locals_in_order, directory


def select_representatives(locals_in_order: list[str]) -> dict[str, str]:
    unique_sources: list[Path] = []
    seen_hashes: set[str] = set()
    for path in sorted(REP_SOURCE.rglob("*.gif"), key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        unique_sources.append(path)
    if len(unique_sources) < len(locals_in_order):
        raise ValueError(f"not enough unique representative images: {len(unique_sources)}")
    random.Random("wawa-english-academy-20260721").shuffle(unique_sources)
    REP_DEST.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for index, (local, source) in enumerate(zip(locals_in_order, unique_sources), start=1):
        filename = f"rep-english-{index:03d}.gif"
        destination = REP_DEST / filename
        if not destination.exists() or hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            shutil.copy2(source, destination)
        result[local] = f"/assets/representative-english/{filename}"
    return result


def make_mentions(center: dict[str, object], local: str) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for type_name, name in [
        ("Place", str(center.get("region", ""))),
        ("Place", str(center.get("city", ""))),
        ("Place", local),
        ("Thing", "영어학원"),
        ("Thing", "영어 어휘 학습"),
        ("Thing", "영어 문법 적용"),
        ("Thing", "영어 독해 근거 찾기"),
        ("Thing", "영어 오답관리"),
    ]:
        if name and (type_name, name) not in seen:
            seen.add((type_name, name))
            values.append({"@type": type_name, "name": name})
    for school in center.get("schools", []):
        key = ("Thing", str(school))
        if key not in seen:
            seen.add(key)
            values.append({"@type": "Thing", "name": str(school)})
    return values


def internal_links(local: str, index: int, order: list[str], center_url: str) -> list[dict[str, str]]:
    previous_local = order[index - 1] if index > 0 else order[-1]
    next_local = order[index + 1] if index + 1 < len(order) else order[0]
    links = [
        {"name": "영어학원 전체 지역", "url": encoded_url("과목별학원", "영어학원")},
        {"name": f"{local} 수학학원", "url": encoded_url("과목별학원", "수학학원", local)},
    ]
    if center_url:
        links.append({"name": f"{local} 전국센터 안내", "url": center_url})
    links.extend(
        [
            {"name": "영어 공부법", "url": encoded_url("교육정보", "영어-공부법")},
            {"name": f"이전 지역 · {previous_local}", "url": encoded_url("과목별학원", "영어학원", previous_local)},
            {"name": f"다음 지역 · {next_local}", "url": encoded_url("과목별학원", "영어학원", next_local)},
        ]
    )
    return links


def page_schema(
    local: str,
    manuscript: dict[str, object],
    center: dict[str, object],
    representative: str,
    links: list[dict[str, str]],
) -> dict[str, object]:
    title = str(manuscript["title"])
    description = str(manuscript["meta"])
    summary = str(manuscript["summary"] or description)
    page_url = encoded_url("과목별학원", "영어학원", local)
    image_url = SITE_URL + representative
    organization_id = page_url + "#organization"
    page_id = page_url + "#webpage"
    breadcrumb_id = page_url + "#breadcrumb"
    service_id = page_url + "#service"
    section_names = [heading for heading, _ in manuscript["sections"]]
    mentions = make_mentions(center, local)
    parts = [{"@type": "WebPageElement", "name": heading} for heading in section_names]
    parts.extend(
        [
            {"@type": "WebPageElement", "name": "자주 묻는 질문"},
            {"@type": "WebPageElement", "name": "학부모 상담 참고 사례"},
            {"@type": "WebPageElement", "name": "관련 학습 페이지"},
        ]
    )
    offer = None
    if center.get("tuition_url"):
        offer = {
            "@type": "Offer",
            "name": f"{title} 상담 및 학습관리",
            "itemOffered": {"@type": "Service", "name": title, "serviceType": "영어학원"},
            "url": center["tuition_url"],
        }
    organization: dict[str, object] = {
        "@type": "EducationalOrganization",
        "@id": organization_id,
        "name": center["organization_name"],
        "alternateName": title,
        "url": page_url,
        "telephone": center["telephone"],
        "description": summary,
        "address": center["address"],
        "areaServed": {"@type": "Place", "name": local},
        "openingHoursSpecification": center["opening_hours"],
        "educationalLevel": center["grades"],
        "teaches": ["영어", "영어 어휘", "영어 문법", "영어 독해", "영어 서술형", "영어 오답관리"],
    }
    if offer:
        organization["makesOffer"] = [offer]
    if center.get("identifier"):
        organization["identifier"] = center["identifier"]
    local_business: dict[str, object] = {
        "@type": "LocalBusiness",
        "@id": page_url + "#localbusiness",
        "name": title,
        "url": page_url,
        "image": image_url,
        "telephone": center["telephone"],
        "address": center["address"],
        "areaServed": {"@type": "Place", "name": local},
        "openingHoursSpecification": center["opening_hours"],
    }
    if offer:
        local_business["makesOffer"] = [offer]
    if center.get("identifier"):
        local_business["identifier"] = center["identifier"]
    faq_entities = [
        {
            "@type": "Question",
            "name": item["question"],
            "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
        }
        for item in manuscript["faqs"]
    ]
    item_list = [
        {"@type": "ListItem", "position": index, "name": item["name"], "url": item["url"]}
        for index, item in enumerate(links, start=1)
    ]
    graph: list[dict[str, object]] = [
        {
            "@type": "WebPage",
            "@id": page_id,
            "url": page_url,
            "name": f"{title} | {TITLE_SUFFIX}",
            "description": description,
            "inLanguage": "ko-KR",
            "isPartOf": {"@id": SITE_URL + "/#website"},
            "publisher": {"@id": organization_id},
            "breadcrumb": {"@id": breadcrumb_id},
            "mainEntity": {"@id": service_id},
            "about": [{"@type": "Thing", "name": title}, {"@type": "Thing", "name": "영어학원"}],
            "mentions": mentions,
            "hasPart": parts,
            "datePublished": TODAY,
            "dateModified": TODAY,
        },
        organization,
        local_business,
        {
            "@type": "BreadcrumbList",
            "@id": breadcrumb_id,
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_URL + "/"},
                {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": encoded_url("과목별학원")},
                {"@type": "ListItem", "position": 3, "name": "영어학원", "item": encoded_url("과목별학원", "영어학원")},
                {"@type": "ListItem", "position": 4, "name": title, "item": page_url},
            ],
        },
        {
            "@type": "Article",
            "@id": page_url + "#article",
            "headline": title,
            "description": summary,
            "image": image_url,
            "inLanguage": "ko-KR",
            "datePublished": TODAY,
            "dateModified": TODAY,
            "mainEntityOfPage": {"@id": page_id},
            "author": {"@id": organization_id},
            "publisher": {"@id": organization_id},
            "articleSection": ["영어학원", center["region"], center["city"], local, *section_names],
            "about": [{"@type": "Thing", "name": title}, {"@type": "Thing", "name": "영어 학습관리"}],
            "mentions": mentions,
            "hasPart": [{"@type": "WebPageElement", "name": heading} for heading in section_names],
        },
        {
            "@type": "Service",
            "@id": service_id,
            "name": f"{title} 학습관리",
            "serviceType": "영어학원",
            "provider": {"@id": organization_id},
            "areaServed": {"@type": "Place", "name": local},
            "description": summary,
            "audience": {
                "@type": "EducationalAudience",
                "educationalRole": "student",
                "audienceType": " · ".join(center["grades"]),
            },
            "about": [
                {"@type": "Thing", "name": "영어 어휘·문법 진단"},
                {"@type": "Thing", "name": "영어 독해·서술형 학습"},
            ],
            "mentions": mentions,
            **({"makesOffer": [offer]} if offer else {}),
        },
        {"@type": "FAQPage", "@id": page_url + "#faq", "mainEntity": faq_entities},
        {
            "@type": "ItemList",
            "@id": page_url + "#links",
            "name": f"{title} 관련 페이지",
            "itemListElement": item_list,
        },
    ]
    return {"@context": "https://schema.org", "@graph": graph}


def paragraph_markup(paragraphs: list[str]) -> str:
    return "\n".join(f"<p>{esc(paragraph)}</p>" for paragraph in paragraphs)


def render_page(
    local: str,
    index: int,
    order: list[str],
    manuscript: dict[str, object],
    center: dict[str, object],
    representative: str,
) -> str:
    title = str(manuscript["title"])
    description = str(manuscript["meta"])
    summary = str(manuscript["summary"] or description)
    page_url = encoded_url("과목별학원", "영어학원", local)
    image_url = SITE_URL + representative
    links = internal_links(local, index, order, str(center.get("center_url", "")))
    schema = page_schema(local, manuscript, center, representative, links)
    region_text = " ".join(value for value in [str(center.get("region", "")), str(center.get("city", "")), local] if value)
    intro = paragraph_markup(manuscript["intro"])
    prose = []
    for section_index, (heading, paragraphs) in enumerate(manuscript["sections"], start=1):
        prose.append(
            f'''<section class="math-prose-section" data-index="{section_index:02d}">
          <h2>{esc(heading)}</h2>
          {paragraph_markup(paragraphs)}
        </section>'''
        )
    faq_markup = []
    for faq_index, item in enumerate(manuscript["faqs"]):
        open_attribute = " open" if faq_index == 0 else ""
        faq_markup.append(
            f'''<details class="math-faq-item"{open_attribute}>
          <summary>{esc(item["question"])}</summary><p>{esc(item["answer"])}</p>
        </details>'''
        )
    review_markup = []
    for review in manuscript["reviews"]:
        review_markup.append(
            f'''<article class="english-review-item"><strong>{esc(review["label"])}</strong><p>{esc(review["content"])}</p></article>'''
        )
    grades = "".join(f"<span>{esc(grade)}</span>" for grade in center["grades"])
    schools = "".join(f"<span>{esc(school)}</span>" for school in center["schools"])
    info_rows = [
        f"<div><dt>지역</dt><dd>{esc(region_text)}</dd></div>",
        f"<div><dt>센터 기준</dt><dd>{esc(center['organization_name'])}</dd></div>",
        f"<div><dt>제공 주소</dt><dd>{esc(center['street_address'])}</dd></div>",
        f'<div><dt>영어 수업 가능 학년</dt><dd><div class="math-tag-list">{grades}</div></dd></div>',
    ]
    if center.get("identifier"):
        info_rows.append(
            f"<div><dt>교육지원청 등록번호</dt><dd>{esc(center['identifier'].get('value', ''))}</dd></div>"
        )
    if schools:
        info_rows.append(f'<div><dt>제공 학교 참고</dt><dd><div class="math-tag-list">{schools}</div></dd></div>')
    if center.get("tuition_url"):
        info_rows.append(
            f'''<div><dt>센터 교습비</dt><dd><a class="math-tuition-link" href="{esc(center['tuition_url'])}" target="_blank" rel="noopener noreferrer">센터별 교습비 안내 <span aria-hidden="true">↗</span></a></dd></div>'''
        )
    link_markup = "".join(f'<a href="{esc(item["url"])}">{esc(item["name"])}</a>' for item in links)
    return f'''<!doctype html>
<html lang="ko"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} | {TITLE_SUFFIX}</title>
  <meta name="description" content="{esc(description)}">
  <meta name="robots" content="index,follow"><link rel="canonical" href="{page_url}">
  <meta property="og:type" content="article"><meta property="og:title" content="{esc(title)} | {TITLE_SUFFIX}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{page_url}"><meta property="og:image" content="{image_url}">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)} | {TITLE_SUFFIX}"><meta name="twitter:description" content="{esc(description)}"><meta name="twitter:image" content="{image_url}">
  <link rel="icon" href="/assets/favicon.png"><link rel="stylesheet" href="/assets/fab.css"><link rel="stylesheet" href="/assets/header.css"><link rel="stylesheet" href="/assets/math-academy.css"><link rel="stylesheet" href="/assets/english-academy.css">
  <script type="application/ld+json">{compact_json(schema)}</script>
</head>
<body class="math-academy-page english-academy-page">
  <header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="logo" href="/"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a>
      <div class="nav-links" aria-label="페이지 이동">
        <a href="/">홈</a><a href="/overview/">학원소개</a><a href="/guide/">학습가이드</a><a href="/교육정보/">교육정보</a><a href="/학부모후기/">학부모후기</a><a class="active" href="/과목별학원/">과목별학원</a><a href="/center/">전국센터</a>
      </div>
    </nav>
  </header>
  <main>
    <section class="math-hero"><div class="math-container">
      <nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><a href="/과목별학원/영어학원/">영어학원</a><span>›</span><span aria-current="page">{esc(title)}</span></nav>
      <div class="math-hero-grid"><div><p class="math-eyebrow">LOCAL ENGLISH ACADEMY GUIDE</p><h1>{esc(title)}</h1><p class="math-hero-lead">{esc(description)}</p></div>
      <aside class="math-hero-panel"><strong>{esc(local)} 영어 상담은 현재 읽고 쓰는 과정부터 확인합니다</strong><p>최근 교재와 시험지를 바탕으로 어휘, 문법, 독해 근거, 서술형 표현과 복습 순서를 나누어 살펴보세요.</p><div class="math-step-row"><span>진단</span><span>적용</span><span>복습</span></div></aside></div>
    </div></section>

    <section class="math-media-section" aria-label="{esc(title)} 이미지 안내"><div class="math-container math-media-stack">
      <img src="{representative}" alt="{esc(title)} {SITE_NAME} 대표" style="display:none;">
      <figure class="math-visible-image"><img src="{esc(center['body_image'])}" alt="{esc(title)} 본문 {SITE_NAME}"></figure>
      <figure class="math-map-card"><img src="{esc(center['map_image'])}" alt="{esc(title)} 지도 {SITE_NAME}" loading="lazy"><figcaption class="math-map-caption">{esc(region_text)}에서 영어학원 상담 전 이동 동선과 수업 일정을 함께 확인할 때 참고할 수 있는 센터 위치 안내입니다.</figcaption></figure>
    </div></section>

    <section class="math-section paper"><div class="math-container math-quick-grid">
      <article class="math-summary-card"><strong>30초 핵심 안내</strong><h2>{esc(title)} 상담에서 확인할 내용</h2><p>{esc(summary)}</p></article>
      <aside class="math-info-card"><h2>수업·상담 핵심정보</h2><dl>{''.join(info_rows)}</dl></aside>
    </div></section>

    <section class="math-section"><article class="math-narrow math-article">
      <div class="math-article-intro">{intro}</div>
      {''.join(prose)}
    </article></section>

    <section class="math-section paper"><div class="math-narrow math-faq-card"><p class="math-eyebrow">FAQ</p><h2>{esc(title)} 자주 묻는 질문</h2><div class="math-faq-list">{''.join(faq_markup)}</div></div></section>
    <section class="math-section"><div class="math-narrow math-review-card"><p class="math-eyebrow">PARENT CONSULTATION CASES</p><h2>{esc(local)} 영어 상담 참고 사례</h2><div class="english-review-grid">{''.join(review_markup)}</div><p class="math-review-note">※ 위 내용은 실제 인물이나 특정 성적 결과를 단정한 후기가 아니라, 제공된 원고를 바탕으로 상담에서 살펴볼 수 있는 상황을 정리한 사례형 예시입니다.</p></div></section>
    <section class="math-section paper"><div class="math-narrow math-links-card"><p class="math-eyebrow">RELATED PAGES</p><h2>{esc(local)} 관련 학습 페이지</h2><div class="math-links">{link_markup}</div></div></section>
  </main>
  <div class="wawa-fixed-fab-container">
    <a href="tel:010-3957-8283" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a>
    <a href="https://blogsms.net/01039578283" target="_blank" rel="noopener" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a>
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" rel="noopener" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a>
  </div>
  <footer class="math-footer"><strong>{SITE_NAME}</strong><br>페이지의 학교·센터 정보는 제공된 자료를 기준으로 안내하며, 실제 수업 조건과 비용은 상담 시 최신 내용을 확인해 주세요.</footer>
</body></html>
'''


def render_hub(order: list[str], directory: str) -> str:
    page_url = encoded_url("과목별학원", "영어학원")
    description = "371개 동네별 영어학원 원고와 센터 정보를 바탕으로 어휘·문법·독해·서술형 학습과 상담 전 확인사항을 지역별로 안내합니다."
    list_items = [
        {
            "@type": "ListItem",
            "position": index,
            "item": {"@type": "WebPage", "name": f"{local} 영어학원", "url": encoded_url("과목별학원", "영어학원", local)},
        }
        for index, local in enumerate(order, start=1)
    ]
    faq = [
        {
            "@type": "Question",
            "name": "동네별 영어학원 페이지에서는 무엇을 확인할 수 있나요?",
            "acceptedAnswer": {"@type": "Answer", "text": "지역별 원고와 제공된 센터 정보를 바탕으로 학생의 어휘·문법·독해·서술형 상태, 학교 자료 활용, 복습 방식과 상담 전 확인사항을 살펴볼 수 있습니다."},
        },
        {
            "@type": "Question",
            "name": "영어학원 상담에는 어떤 자료를 준비하면 좋나요?",
            "acceptedAnswer": {"@type": "Answer", "text": "최근 영어 시험지, 교과서와 학교 프린트, 사용 중인 단어장, 틀린 문제의 풀이 흔적과 일주일 학습 시간표를 준비하면 진단과 계획을 더 구체적으로 확인할 수 있습니다."},
        },
        {
            "@type": "Question",
            "name": "초등·중등·고등 영어학원 선택 기준은 같나요?",
            "acceptedAnswer": {"@type": "Answer", "text": "초등은 읽기 습관과 기초 어휘, 중등은 문법 적용과 내신 서술형, 고등은 긴 지문에서 근거를 찾는 독해와 시간 관리 비중이 커지므로 학년과 현재 상태에 맞춰 기준을 나누어야 합니다."},
        },
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": page_url + "#webpage",
                "url": page_url,
                "name": f"영어학원 지역 안내 | {TITLE_SUFFIX}",
                "description": description,
                "inLanguage": "ko-KR",
                "isPartOf": {"@id": SITE_URL + "/#website"},
                "publisher": {"@id": SITE_URL + "/#organization"},
                "breadcrumb": {"@id": page_url + "#breadcrumb"},
                "about": [{"@type": "Thing", "name": "영어학원"}, {"@type": "Thing", "name": "영어 학습코칭"}],
                "datePublished": TODAY,
                "dateModified": TODAY,
            },
            {
                "@type": "BreadcrumbList",
                "@id": page_url + "#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_URL + "/"},
                    {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": encoded_url("과목별학원")},
                    {"@type": "ListItem", "position": 3, "name": "영어학원 지역 안내", "item": page_url},
                ],
            },
            {"@type": "ItemList", "@id": page_url + "#directory", "name": "동네별 영어학원 안내", "numberOfItems": len(order), "itemListElement": list_items},
            {"@type": "FAQPage", "@id": page_url + "#faq", "mainEntity": faq},
        ],
    }
    return f'''<!doctype html>
<html lang="ko"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>영어학원 지역 안내 | 371개 동네별 영어 학습코칭 | {TITLE_SUFFIX}</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="index,follow"><link rel="canonical" href="{page_url}">
  <meta property="og:type" content="website"><meta property="og:title" content="영어학원 지역 안내 | {TITLE_SUFFIX}"><meta property="og:description" content="371개 동네별 영어학원 안내에서 지역과 학생 상황에 맞는 영어 상담 기준을 확인하세요."><meta property="og:url" content="{page_url}"><meta property="og:image" content="{SITE_URL}/assets/title.png">
  <link rel="icon" href="/assets/favicon.png"><link rel="stylesheet" href="/assets/fab.css"><link rel="stylesheet" href="/assets/header.css"><link rel="stylesheet" href="/assets/math-academy.css"><link rel="stylesheet" href="/assets/english-academy.css">
  <script type="application/ld+json">{compact_json(schema)}</script>
</head><body class="math-academy-page english-academy-page">
  <header class="site-header"><nav class="nav" aria-label="주요 메뉴"><a class="logo" href="/"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a><div class="nav-links" aria-label="페이지 이동"><a href="/">홈</a><a href="/overview/">학원소개</a><a href="/guide/">학습가이드</a><a href="/교육정보/">교육정보</a><a href="/학부모후기/">학부모후기</a><a class="active" href="/과목별학원/">과목별학원</a><a href="/center/">전국센터</a></div></nav></header>
  <main>
    <section class="math-hero"><div class="math-container"><nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><span aria-current="page">영어학원 지역 안내</span></nav><div class="math-hero-grid"><div><p class="math-eyebrow">ENGLISH ACADEMY DIRECTORY</p><h1>동네별 영어학원 안내</h1><p class="math-hero-lead">어휘·문법·독해·서술형을 따로 나열하는 데 그치지 않고, 학생의 학년과 학교 자료, 복습 가능 시간을 함께 놓고 확인할 수 있도록 371개 지역별 안내를 정리했습니다.</p></div><aside class="math-hero-panel"><strong>영어는 현재 읽고 설명하는 과정에서 출발합니다</strong><p>학년보다 앞선 진도만 묻기보다 어휘 누적, 문장 구조 이해, 독해 근거와 오답 재도전 방식을 함께 확인하세요.</p><div class="math-step-row"><span>어휘</span><span>독해</span><span>서술형</span></div></aside></div></div></section>
    <section class="math-section paper"><div class="math-container math-quick-grid"><article class="math-summary-card"><strong>371 LOCAL GUIDES</strong><h2>지역과 학생 상황을 함께 보는 영어학원 안내</h2><p>각 페이지는 제공된 동네별 원고와 센터·학교 자료를 사용합니다. 특정 결과를 약속하기보다 학생이 막히는 영어 영역, 학교 범위 대응, 복습 기록과 상담 준비 기준을 구체적으로 확인하도록 구성했습니다.</p></article><aside class="math-info-card"><h2>영어 상담 핵심 기준</h2><dl><div><dt>어휘</dt><dd>누적 암기와 문장 안에서의 의미 확인</dd></div><div><dt>문법</dt><dd>개념 설명에서 문제 적용까지의 연결</dd></div><div><dt>독해</dt><dd>답의 근거와 문단 관계 표시</dd></div><div><dt>복습</dt><dd>오답 원인 기록과 일정 뒤 재풀이</dd></div></dl></aside></div></section>
    <section class="math-section"><div class="math-container"><p class="math-eyebrow">FIND YOUR LOCAL PAGE</p><h2 style="margin:0;font-family:'Noto Serif KR',serif;font-size:clamp(28px,4vw,44px);">동네명으로 영어학원 찾기</h2><div class="math-directory-tools"><input class="math-search" id="english-local-search" type="search" placeholder="예: 명일동, 불당동, 가경동" aria-label="동네명 검색"><div class="math-count" id="english-search-count">전체 371개 지역</div></div>{directory}</div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card"><p class="math-eyebrow">FAQ</p><h2>영어학원 안내 이용 전 확인사항</h2><div class="math-faq-list">{''.join(f'<details class="math-faq-item"{" open" if index == 0 else ""}><summary>{esc(item["name"])}</summary><p>{esc(item["acceptedAnswer"]["text"])}</p></details>' for index, item in enumerate(faq))}</div></div></section>
    <section class="math-section"><div class="math-narrow math-links-card"><p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>영어 상담 전 함께 보면 좋은 안내</h2><div class="math-links"><a href="/교육정보/영어-공부법/">영어 공부법</a><a href="/교육정보/영어-단어-암기법/">단어 암기법</a><a href="/교육정보/오답노트-작성법/">오답노트 작성</a><a href="/center/">전국센터 찾기</a></div></div></section>
  </main>
  <div class="wawa-fixed-fab-container"><a href="tel:010-3957-8283" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a><a href="https://blogsms.net/01039578283" target="_blank" rel="noopener" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a><a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" rel="noopener" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a></div>
  <footer class="math-footer"><strong>{SITE_NAME}</strong><br>동네별 영어학원 페이지는 제공된 센터·학교·원고 자료를 기준으로 구성했습니다.</footer>
  <script>(()=>{{const input=document.getElementById('english-local-search');const count=document.getElementById('english-search-count');const links=[...document.querySelectorAll('.math-local-grid a')];input.addEventListener('input',()=>{{const query=input.value.trim().toLowerCase();let visible=0;links.forEach(link=>{{const show=!query||link.dataset.local.toLowerCase().includes(query);link.hidden=!show;if(show)visible+=1;}});document.querySelectorAll('.math-city').forEach(city=>{{city.hidden=![...city.querySelectorAll('a')].some(link=>!link.hidden);}});document.querySelectorAll('.math-region').forEach(region=>{{const show=[...region.querySelectorAll('.math-city')].some(city=>!city.hidden);region.hidden=!show;if(query&&show)region.open=true;}});count.textContent=query?`${{visible}}개 지역 검색됨`:'전체 371개 지역';}});}})();</script>
</body></html>'''


def update_subject_hub() -> None:
    path = ROOT / "과목별학원" / "index.html"
    source = path.read_text(encoding="utf-8")
    replacement = '<a class="subject-category-card" id="english" data-number="02" href="./영어학원/"><small>CORE SUBJECT</small><h3>영어학원</h3><p>어휘, 문장 구조, 문법 적용, 독해 근거와 쓰기 과정의 연결을 동네별 원고에서 확인합니다.</p><span class="subject-status">371개 지역 안내 보기 →</span></a>'
    source, count = re.subn(
        r'<(?:article|a) class="subject-category-card" id="english".*?</(?:article|a)>',
        replacement,
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("subject hub english card not found")
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
    data = json.loads(match.group(1))
    for item in data.get("@graph", []):
        if item.get("@type") == "CollectionPage":
            item["dateModified"] = TODAY
        if item.get("@type") == "ItemList":
            for list_item in item.get("itemListElement", []):
                thing = list_item.get("item", {})
                if thing.get("name") == "영어학원":
                    thing["url"] = encoded_url("과목별학원", "영어학원")
    source = source[: match.start(1)] + compact_json(data) + source[match.end(1) :]
    path.write_text(source, encoding="utf-8", newline="\n")


def update_sitemap(order: list[str]) -> None:
    path = ROOT / "sitemap.xml"
    source = path.read_text(encoding="utf-8")
    urls = [encoded_url("과목별학원", "영어학원")]
    urls.extend(encoded_url("과목별학원", "영어학원", local) for local in order)
    additions = []
    for url in urls:
        if f"<loc>{url}</loc>" not in source:
            additions.append(f"  <url>\n    <loc>{url}</loc>\n    <lastmod>{TODAY}</lastmod>\n  </url>\n")
    source = source.replace("</urlset>", "".join(additions) + "</urlset>")
    path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    manuscripts = load_manuscripts()
    order, directory = ordered_locals_and_directory()
    if len(manuscripts) != 371 or len(order) != 371 or set(manuscripts) != set(order):
        raise ValueError(
            f"mapping mismatch manuscripts={len(manuscripts)} order={len(order)} missing={set(order) - set(manuscripts)} extra={set(manuscripts) - set(order)}"
        )
    representatives = select_representatives(order)
    ENGLISH_ROOT.mkdir(parents=True, exist_ok=True)
    for index, local in enumerate(order):
        center = extract_center_data(local)
        target = ENGLISH_ROOT / local
        target.mkdir(parents=True, exist_ok=True)
        output = render_page(local, index, order, manuscripts[local], center, representatives[local])
        (target / "index.html").write_text(output, encoding="utf-8", newline="\n")
    (ENGLISH_ROOT / "index.html").write_text(render_hub(order, directory), encoding="utf-8", newline="\n")
    update_subject_hub()
    update_sitemap(order)
    print(f"generated={len(order)} hub=1 representatives={len(representatives)}")


if __name__ == "__main__":
    main()
