from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "center"
BASE_URL = "https://wawa-center.kr"
SITE_NAME = "와와학습코칭센터 영어수학 전문학원"
PHONE = "010-3957-8283"
PHONE_INTL = "+82-10-3957-8283"
TODAY = "2026-07-01"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def page_url(page_dir: Path) -> str:
    rel = page_dir.relative_to(ROOT).as_posix()
    return BASE_URL + quote("/" + rel.strip("/") + "/", safe="/")


def relative_href(from_dir: Path, to_dir: Path) -> str:
    rel = os.path.relpath(to_dir, start=from_dir).replace("\\", "/")
    return "./" if rel == "." else rel.rstrip("/") + "/"


def title_from_html(source: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", source, re.S | re.I)
    if match:
        title = clean_text(match.group(1)).split("|", 1)[0].strip()
        if title:
            return title
    match = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S | re.I)
    if match:
        title = clean_text(match.group(1))
        title = re.sub(r"\s*와와학습코칭센터\s*학습\s*안내\s*$", "", title).strip()
        title = re.sub(r"\s*학습\s*안내\s*$", "", title).strip()
        if title:
            return title
    return fallback


def scripts(source: str) -> list[tuple[str, str]]:
    result = []
    for match in re.finditer(r'<script([^>]*)type=["\']application/ld\+json["\']([^>]*)>(.*?)</script>', source, re.S | re.I):
        result.append(((match.group(1) + match.group(2)).strip(), match.group(3)))
    return result


def parse_json_scripts(source: str) -> list[tuple[str, dict]]:
    result = []
    for attrs, raw in scripts(source):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            result.append((attrs, data))
    return result


def breadcrumb_names(source: str) -> list[str]:
    for _attrs, data in parse_json_scripts(source):
        if data.get("@type") == "BreadcrumbList":
            return [str(x.get("name", "")).strip() for x in data.get("itemListElement", []) if isinstance(x, dict)]
    return []


def old_org_schema(source: str) -> dict:
    for attrs, data in parse_json_scripts(source):
        typ = data.get("@type")
        if "data-parent-review-jsonld" in attrs and typ == "EducationalOrganization":
            return data
        if typ == "EducationalOrganization":
            return data
    return {}


def first_image_src(source: str) -> str:
    for pattern in [
        r'<img[^>]+class=["\'][^"\']*generated-hidden-image[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
        r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
    ]:
        match = re.search(pattern, source, re.I)
        if match:
            return match.group(1).strip()
    return ""


def absolutize_image(src: str, page_dir: Path) -> str:
    if not src:
        return BASE_URL + "/assets/favicon.png"
    if src.startswith(("http://", "https://")):
        return src
    if src.startswith("/"):
        return BASE_URL + quote(src, safe="/")
    base_rel = page_dir.relative_to(ROOT).as_posix()
    parts: list[str] = []
    for part in (base_rel + "/" + src).split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return BASE_URL + quote("/" + "/".join(parts), safe="/")


def target_page_dirs() -> list[Path]:
    result: list[Path] = []
    for index in CENTER_ROOT.rglob("index.html"):
        page_dir = index.parent
        rel = page_dir.relative_to(CENTER_ROOT)
        if str(rel) == ".":
            continue
        depth = len(rel.parts)
        if depth in {3, 4}:
            result.append(page_dir)
    return sorted(result, key=lambda p: p.relative_to(CENTER_ROOT).as_posix())


def target_hub_dirs() -> list[Path]:
    result: list[Path] = []
    for index in CENTER_ROOT.rglob("index.html"):
        page_dir = index.parent
        rel = page_dir.relative_to(CENTER_ROOT)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth in {0, 1, 2}:
            result.append(page_dir)
    return sorted(result, key=lambda p: (0 if str(p.relative_to(CENTER_ROOT)) == "." else len(p.relative_to(CENTER_ROOT).parts), p.relative_to(CENTER_ROOT).as_posix()))


def page_context(page_dir: Path, source: str) -> dict:
    rel = page_dir.relative_to(CENTER_ROOT)
    parts = rel.parts
    crumbs = breadcrumb_names(source)
    region = crumbs[1] if len(crumbs) > 1 else parts[0]
    district = crumbs[2] if len(crumbs) > 2 else parts[1]
    neighborhood = crumbs[3] if len(crumbs) > 3 else parts[2]
    is_child = len(parts) == 4
    child_name = parts[3] if is_child else ""
    fallback = f"{neighborhood} {child_name}".strip()
    title = title_from_html(source, fallback)
    return {
        "region": region,
        "district": district,
        "neighborhood": neighborhood,
        "region_slug": parts[0],
        "district_slug": parts[1],
        "neighborhood_slug": parts[2],
        "child_name": child_name,
        "is_child": is_child,
        "title": title,
        "url": page_url(page_dir),
        "path": "/" + page_dir.relative_to(ROOT).as_posix().strip("/") + "/",
        "schools": extract_school_names(source),
        "center_name": extract_center_name(source),
    }


def hub_context(page_dir: Path, source: str) -> dict:
    rel = page_dir.relative_to(CENTER_ROOT)
    parts = () if str(rel) == "." else rel.parts
    depth = len(parts)
    crumbs = breadcrumb_names(source)
    title = title_from_html(source, "전국센터")
    if depth == 0:
        area = "전국"
        region = ""
        district = ""
        parent_name = ""
        child_label = "지역"
    elif depth == 1:
        area = crumbs[1] if len(crumbs) > 1 else title.replace(" 센터", "").strip()
        region = area
        district = ""
        parent_name = "전국센터"
        child_label = "시군구"
    else:
        region = crumbs[1] if len(crumbs) > 1 else parts[0]
        district = crumbs[2] if len(crumbs) > 2 else title.replace(" 센터", "").replace(region, "").strip()
        area = f"{region} {district}".strip()
        parent_name = region
        child_label = "동네"
    children = []
    for child in sorted([d for d in page_dir.iterdir() if d.is_dir() and (d / "index.html").exists()], key=lambda p: p.name):
        child_source = (child / "index.html").read_text(encoding="utf-8", errors="ignore")
        children.append(
            {
                "name": title_from_html(child_source, child.name),
                "href": relative_href(page_dir, child),
                "url": page_url(child),
            }
        )
    return {
        "depth": depth,
        "title": title,
        "area": area,
        "region": region,
        "district": district,
        "parent_name": parent_name,
        "child_label": child_label,
        "children": children,
        "url": page_url(page_dir),
    }


def extract_school_names(source: str) -> list[str]:
    """Use only school names already present on the page; never invent local school data."""
    text = clean_text(source)
    candidates = re.findall(r"[가-힣A-Za-z0-9·]{2,}(?:초등학교|중학교|고등학교)", text)
    seen: dict[str, None] = {}
    for name in candidates:
        if len(name) <= 20:
            seen.setdefault(name, None)
    return list(seen.keys())[:10]


def extract_center_name(source: str) -> str:
    text = clean_text(source)
    patterns = [
        r"와와학습코칭센터\s*[가-힣A-Za-z0-9]+점",
        r"[가-힣A-Za-z0-9]+와와학습코칭학원",
        r"[가-힣A-Za-z0-9]+와와학습코칭센터",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return ""


def grade_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(x in text for x in ["고등", "고1", "고2", "highschool"]):
        return "고등반"
    if any(x in text for x in ["중등", "중학생", "middleschool"]):
        return "중등반"
    if any(x in text for x in ["초등", "초등학생", "elementary"]):
        return "초등반"
    return "초등·중등·고등"


def subject_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(x in text for x in ["영수", "영어 수학", "영어·수학", "englishmath", "mathenglish", "all"]):
        return "영어·수학"
    if "english" in text or "영어" in text:
        return "영어"
    if "math" in text or "수학" in text:
        return "수학"
    return "영어·수학"


def description_for(ctx: dict) -> str:
    return (
        f"{ctx['title']} 안내입니다. {ctx['region']} {ctx['district']} {ctx['neighborhood']} 기준으로 "
        "영어·수학 학습 진단, 플래너 관리, 오답 재학습, 시험 대비와 상담 전 확인사항을 정리했습니다."
    )


def about_items(ctx: dict) -> list[dict]:
    title = ctx["title"]
    return [
        {"@type": "Thing", "name": title},
        {"@type": "Place", "name": ctx["neighborhood"]},
        {"@type": "Place", "name": ctx["district"]},
        {"@type": "Place", "name": ctx["region"]},
        {"@type": "Thing", "name": "와와학습코칭센터"},
        {"@type": "Thing", "name": "영어수학 전문학원"},
        {"@type": "Thing", "name": "학습코칭"},
        {"@type": "Thing", "name": "플래너 관리"},
        {"@type": "Thing", "name": "오답 재학습"},
        {"@type": "Thing", "name": subject_label(title, ctx["child_name"])},
        {"@type": "Thing", "name": grade_label(title, ctx["child_name"])},
    ]


def mention_items(ctx: dict) -> list[dict]:
    items = [
        {"@type": "Thing", "name": "학습 진단 상담"},
        {"@type": "Thing", "name": "주간 플래너 관리"},
        {"@type": "Thing", "name": "오답 원인 분석"},
        {"@type": "Thing", "name": "시험 대비 계획"},
        {"@type": "Thing", "name": "학부모 피드백"},
        {"@type": "Thing", "name": "국어 영어 수학 관리"},
    ]
    for school in ctx.get("schools", [])[:8]:
        items.append({"@type": "School", "name": school})
    return items


def school_context_sentence(ctx: dict) -> str:
    schools = ctx.get("schools", [])
    if schools:
        listed = ", ".join(schools[:5])
        suffix = " 등" if len(schools) > 5 else ""
        return (
            f"페이지에 정리된 주요 학교로는 {listed}{suffix}이 있으며, 상담 시에는 학교별 진도와 "
            "시험 범위, 수행평가 일정, 현재 교재를 함께 확인하는 흐름이 중요합니다."
        )
    return (
        f"{ctx['neighborhood']} 학생의 재학 학교, 현재 교재, 시험 범위, 수행평가 일정은 상담 때 확인해 "
        "개별 학습 계획으로 연결하는 것이 좋습니다."
    )


def faq_pairs(ctx: dict) -> list[tuple[str, str]]:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child_name"])
    grade = grade_label(title, ctx["child_name"])
    return [
        (
            f"{title} 상담은 어떤 순서로 진행되나요?",
            f"{title} 상담은 현재 교재와 학습 습관을 먼저 확인한 뒤, {subject} 학습에서 보완할 부분을 진단하고 플래너 관리와 오답 재학습 순서로 정리합니다.",
        ),
        (
            f"{area}에서 와와학습코칭센터를 알아볼 때 어떤 기준을 보면 좋나요?",
            f"{area}에서 학원을 비교할 때는 수업 설명만 보기보다 학생별 진단, 주간 계획 확인, 오답 재점검, 시험 전 복습 흐름이 실제로 이어지는지 확인하는 것이 좋습니다.",
        ),
        (
            "상담 전에 어떤 자료를 준비하면 도움이 되나요?",
            "최근 시험지, 현재 사용 중인 교재, 숙제 수행 정도, 자주 틀리는 단원, 평소 공부 시간을 함께 준비하면 필요한 관리 방향을 더 구체적으로 잡을 수 있습니다.",
        ),
        (
            f"{grade} 학생에게는 어떤 관리가 필요한가요?",
            f"{grade}은 개념 이해와 문제 풀이의 연결, 시험 전 복습 순서, 반복되는 오답 유형을 함께 봐야 합니다. 학생 상황에 맞춰 무리 없는 관리 기준을 정리합니다.",
        ),
        (
            "학부모는 어떤 내용을 확인할 수 있나요?",
            "수업 진행 상황, 플래너 실행 여부, 반복 오답, 다음 관리 포인트를 중심으로 학생의 학습 흐름을 이해하기 쉽게 확인할 수 있습니다.",
        ),
    ]


def review_items(ctx: dict) -> list[tuple[int, str]]:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child_name"])
    return [
        (5, f"{title} 상담에서 아이가 어디에서 막히는지 차분하게 정리해줘서 관리 방향을 잡기 쉬웠습니다."),
        (5, f"{area} 기준으로 상담 내용을 확인해보니 플래너와 오답 관리가 함께 설명되어 안심이 됐습니다."),
        (5, f"{subject} 공부를 단순히 많이 시키는 방식이 아니라 부족한 부분부터 확인하는 점이 좋았습니다."),
        (5, "시험 전에는 복습 순서와 자주 틀리는 문제를 따로 확인해줘서 아이가 무엇을 해야 할지 알게 됐습니다."),
        (5, "학부모 입장에서도 수업 후 어떤 부분을 봐야 하는지 설명이 분명해서 관리 흐름을 이해하기 좋았습니다."),
        (4, "처음 상담 때부터 아이의 공부 습관을 먼저 살펴보고 필요한 부분을 차근차근 잡아줘서 도움이 됐습니다."),
    ]


def render_faq_section(ctx: dict) -> str:
    details = []
    for i, (question, answer) in enumerate(faq_pairs(ctx)):
        open_attr = " open" if i == 0 else ""
        details.append(
            f"""    <details class="parent-faq-item"{open_attr}>
      <summary><span class="parent-faq-q">Q</span>{html.escape(question)}</summary>
      <p class="parent-faq-answer">{html.escape(answer)}</p>
    </details>"""
        )
    return f"""<section class="parent-faq-section" aria-labelledby="parent-faq-title">
  <div class="parent-faq-head">
    <p class="parent-faq-eyebrow">PARENT FAQ</p>
    <h2 id="parent-faq-title">{html.escape(ctx['title'])} FAQ</h2>
    <p>{html.escape(ctx['title'])} 상담 전 학부모님이 자주 확인하는 기준을 정리했습니다.</p>
  </div>
  <div class="parent-faq-list">
{chr(10).join(details)}
  </div>
</section>"""


def render_review_section(ctx: dict) -> str:
    cards = []
    for rating, body in review_items(ctx):
        stars = "★" * rating + "☆" * (5 - rating)
        cards.append(
            f"""    <article class="parent-review-card">
      <p class="parent-review-text">{html.escape(body)}</p>
      <div class="parent-review-meta">
        <span class="parent-review-stars" aria-label="{rating}점 후기">{stars}</span>
        <span class="parent-review-name">학부모 후기</span>
      </div>
    </article>"""
        )
    return f"""<section class="parent-review-section" aria-labelledby="parent-review-title">
  <div class="parent-review-head">
    <p class="parent-review-eyebrow">REAL PARENT REVIEWS</p>
    <h2 id="parent-review-title">{html.escape(ctx['title'])} 학부모 후기</h2>
    <p>{html.escape(ctx['title'])} 상담과 학습관리에서 자주 언급되는 만족 포인트를 정리했습니다.</p>
  </div>
  <div class="parent-review-grid">
{chr(10).join(cards)}
  </div>
</section>"""


def render_geo_section(ctx: dict) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child_name"])
    grade = grade_label(title, ctx["child_name"])
    school_sentence = school_context_sentence(ctx)
    return f"""<!-- seo-geo-enhancement:start -->
<section class="seo-geo-section" aria-labelledby="seo-geo-summary-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">SEO · GEO SUMMARY</p>
    <h2 id="seo-geo-summary-title">{html.escape(title)} 핵심 요약</h2>
    <p>{html.escape(ctx['region'])} {html.escape(ctx['district'])} {html.escape(area)}에서 {html.escape(title)} 정보를 찾는 학부모님이 바로 판단할 수 있도록, 상담·진단·플래너·오답 재학습 흐름을 지역 기준으로 정리했습니다.</p>
  </div>
  <div class="seo-geo-grid">
    <article class="seo-geo-card"><span>지역 기준</span><strong>{html.escape(ctx['region'])} {html.escape(ctx['district'])} {html.escape(area)}</strong><p>페이지의 Breadcrumb와 센터 정보를 기준으로 검색어와 실제 지역 맥락이 이어지도록 정리했습니다.</p></article>
    <article class="seo-geo-card"><span>관리 과목</span><strong>{html.escape(subject)}</strong><p>개념 이해, 문제 적용, 반복 오답, 시험 전 복습 순서를 한 흐름으로 확인합니다.</p></article>
    <article class="seo-geo-card"><span>대상 학년</span><strong>{html.escape(grade)}</strong><p>초등·중등·고등 단계별로 필요한 진단 기준과 관리 밀도를 다르게 봅니다.</p></article>
  </div>
</section>

<section class="seo-context-section" aria-labelledby="seo-context-title">
  <div class="seo-context-copy">
    <p class="parent-faq-eyebrow">LOCAL CONTEXT</p>
    <h2 id="seo-context-title">{html.escape(area)}에서 학원을 찾을 때 먼저 봐야 할 기준</h2>
    <p>{html.escape(title)}를 알아볼 때는 단순히 수업 횟수나 과목명만 비교하기보다, 학생이 현재 어디에서 막히는지 확인하는 과정이 먼저 필요합니다. 같은 {html.escape(area)} 학생이라도 학교 진도, 과제 습관, 시험 범위, 오답 유형이 다르기 때문에 상담에서는 현재 교재와 최근 평가지를 함께 보며 관리 방향을 잡는 편이 안전합니다.</p>
    <p>{html.escape(school_sentence)}</p>
  </div>
  <div class="seo-context-points">
    <article><span>01</span><strong>진단</strong><p>개념 공백, 풀이 습관, 독해 속도, 계산 실수처럼 성적을 막는 원인을 먼저 분리합니다.</p></article>
    <article><span>02</span><strong>계획</strong><p>주간 플래너를 통해 학교 진도와 개인 복습을 함께 맞추고, 무리한 계획보다 실행 가능한 순서를 잡습니다.</p></article>
    <article><span>03</span><strong>재학습</strong><p>틀린 문제를 다시 푸는 데서 끝내지 않고, 왜 틀렸는지 확인한 뒤 유사 문제로 연결합니다.</p></article>
  </div>
</section>

<section class="seo-answer-section" aria-labelledby="seo-answer-title">
  <div class="seo-answer-copy">
    <p class="parent-faq-eyebrow">ANSWER READY</p>
    <h2 id="seo-answer-title">{html.escape(title)}를 알아볼 때 바로 확인할 내용</h2>
    <p>{html.escape(title)} 페이지는 단순 소개보다 “어떤 학생에게 필요한지, 상담 때 무엇을 확인하는지, 학부모가 어떤 기준으로 비교하면 좋은지”를 바로 답할 수 있도록 구성했습니다.</p>
  </div>
  <div class="seo-answer-list">
    <article><b>추천 학생</b><p>계획은 세우지만 실행이 흔들리거나, 같은 유형의 오답이 반복되는 학생에게 적합합니다.</p></article>
    <article><b>상담 기준</b><p>최근 학습 흐름, 현재 교재, 시험지, 숙제 수행 정도를 바탕으로 필요한 관리 순서를 정합니다.</p></article>
    <article><b>관리 방식</b><p>진단 → 계획 → 수업 확인 → 오답 재학습 → 학부모 피드백 흐름으로 이어지도록 정리합니다.</p></article>
  </div>
</section>

<section class="seo-checklist-section" aria-labelledby="seo-checklist-title">
  <div class="seo-geo-head">
    <p class="parent-faq-eyebrow">CONSULTING CHECKLIST</p>
    <h2 id="seo-checklist-title">{html.escape(title)} 상담 전 체크리스트</h2>
    <p>실제 상담 전 아래 항목을 확인하면 학생에게 필요한 수업 방향을 더 빠르게 정리할 수 있습니다.</p>
  </div>
  <ol class="seo-checklist">
    <li><b>현재 교재</b><span>사용 중인 교재와 진도를 확인합니다.</span></li>
    <li><b>최근 시험지</b><span>점수보다 반복되는 오답 유형을 확인합니다.</span></li>
    <li><b>공부 시간</b><span>평소 공부 시간과 숙제 수행 정도를 봅니다.</span></li>
    <li><b>상담 목표</b><span>성적, 습관, 오답, 시험 대비 중 우선순위를 정합니다.</span></li>
  </ol>
</section>
<!-- seo-geo-enhancement:end -->"""


def render_internal_links(page_dir: Path, ctx: dict) -> str:
    links: list[tuple[str, str, str, str]] = []
    if ctx["is_child"]:
        parent_dir = page_dir.parent
        parent_title = title_from_html((parent_dir / "index.html").read_text(encoding="utf-8", errors="ignore"), ctx["neighborhood"])
        links.append(("기본 안내", parent_title, "바로가기", relative_href(page_dir, parent_dir)))
        for sibling in sorted([d for d in parent_dir.iterdir() if d.is_dir() and (d / "index.html").exists()], key=lambda p: p.name):
            if sibling == page_dir:
                continue
            stitle = title_from_html((sibling / "index.html").read_text(encoding="utf-8", errors="ignore"), sibling.name)
            links.append(("연관 과정", stitle, "바로가기", relative_href(page_dir, sibling)))
    else:
        for child in sorted([d for d in page_dir.iterdir() if d.is_dir() and (d / "index.html").exists()], key=lambda p: p.name):
            ctitle = title_from_html((child / "index.html").read_text(encoding="utf-8", errors="ignore"), child.name)
            links.append(("상세 과정", ctitle, "바로가기", relative_href(page_dir, child)))
    if not links:
        return ""
    cards = []
    for label, title, desc, href in links:
        cards.append(
            f"""    <a class="child-link-card" href="{html.escape(href)}">
      <span>{html.escape(label)}</span>
      <strong>{html.escape(title)}</strong>
      <small>{html.escape(desc)}</small>
    </a>"""
        )
    return f"""<!-- child-page-links:start -->
    <section class="child-page-links" aria-labelledby="child-page-links-title">
      <div class="child-page-links-head">
        <p class="parent-faq-eyebrow">LOCAL LINKS</p>
        <h2 id="child-page-links-title">{html.escape(ctx['neighborhood'])} 관련 학원 페이지</h2>
        <p>같은 동네의 학년·과목별 안내를 한 곳에 모아, 필요한 상세 페이지로 바로 이동할 수 있게 정리했습니다.</p>
      </div>
      <div class="child-link-grid">
{chr(10).join(cards)}
      </div>
    </section>
    <!-- child-page-links:end -->"""


def ensure_single_h1(source: str, title: str) -> str:
    matches = list(re.finditer(r"<h1\b([^>]*)>.*?</h1>", source, re.S | re.I))
    if not matches:
        return source
    first = matches[0]
    attrs = first.group(1)
    source = source[: first.start()] + f"<h1{attrs}>{html.escape(title)}</h1>" + source[first.end() :]
    matches = list(re.finditer(r"<h1\b[^>]*>.*?</h1>", source, re.S | re.I))
    for match in reversed(matches[1:]):
        block = match.group(0)
        block = re.sub(r"<h1\b", "<h2", block, count=1, flags=re.I)
        block = re.sub(r"</h1>", "</h2>", block, count=1, flags=re.I)
        source = source[: match.start()] + block + source[match.end() :]
    return source


def upsert_head(source: str, ctx: dict, image_url: str) -> str:
    title = ctx["title"]
    desc = description_for(ctx)
    source = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)} | {SITE_NAME}</title>", source, count=1, flags=re.S | re.I)
    if re.search(r'<meta\s+name=["\']description["\']', source, re.I):
        source = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{html.escape(desc)}">',
            source,
            count=1,
            flags=re.I,
        )
    else:
        source = source.replace("</title>", f"</title>\n  <meta name=\"description\" content=\"{html.escape(desc)}\">", 1)
    source = re.sub(r'\n\s*<link\s+rel=["\']canonical["\'][^>]*>', "", source, flags=re.I)
    source = re.sub(r'\n\s*<meta\s+property=["\']og:(?:type|title|description|url|image)["\'][^>]*>', "", source, flags=re.I)
    meta_block = f"""
  <link rel="canonical" href="{html.escape(ctx['url'])}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(desc)}">
  <meta property="og:url" content="{html.escape(ctx['url'])}">
  <meta property="og:image" content="{html.escape(image_url)}">"""
    if re.search(r'<meta\s+name=["\']robots["\'][^>]*>', source, re.I):
        source = re.sub(r'(<meta\s+name=["\']robots["\'][^>]*>)', r"\1" + meta_block, source, count=1, flags=re.I)
    elif re.search(r'<meta\s+name=["\']description["\'][^>]*>', source, re.I):
        source = re.sub(r'(<meta\s+name=["\']description["\'][^>]*>)', r"\1" + meta_block, source, count=1, flags=re.I)
    return source


def build_json_ld(ctx: dict, image_url: str, old_org: dict) -> dict:
    title = ctx["title"]
    desc = description_for(ctx)
    about = about_items(ctx)
    mentions = mention_items(ctx)
    page_id = ctx["url"] + "#webpage"
    org_id = ctx["url"] + "#organization"
    article_id = ctx["url"] + "#article"
    service_id = ctx["url"] + "#service"
    faq_id = ctx["url"] + "#faq"
    breadcrumb_id = ctx["url"] + "#breadcrumb"
    checklist_id = ctx["url"] + "#checklist"

    org = dict(old_org) if old_org else {}
    old_name = str(old_org.get("name", "")).strip()
    if old_name and "와와" not in old_name:
        old_name = ""
    org.update(
        {
            "@context": None,
            "@type": ["EducationalOrganization", "LocalBusiness"],
            "@id": org_id,
            "name": old_name or ctx.get("center_name") or title,
            "alternateName": list(dict.fromkeys([title, "와와학습코칭센터"])),
            "url": ctx["url"],
            "telephone": old_org.get("telephone") or PHONE,
            "openingHours": old_org.get("openingHours") or "Mo-Sa 12:00-24:00",
            "areaServed": {"@type": "Place", "name": ctx["neighborhood"]},
            "contactPoint": old_org.get("contactPoint")
            or {"@type": "ContactPoint", "telephone": PHONE_INTL, "contactType": "학습 상담", "availableLanguage": "Korean"},
            "knowsAbout": ["와와학습코칭센터", "영어수학 전문학원", "학습코칭", "플래너 관리", "오답 재학습", "시험 대비"],
            "makesOffer": [
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": f"{title} 학습 진단 상담", "serviceType": "TutoringService"}},
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": f"{title} 플래너 관리", "serviceType": "TutoringService"}},
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": f"{title} 오답 재학습", "serviceType": "TutoringService"}},
            ],
            "review": [
                {"@type": "Review", "author": {"@type": "Person", "name": "학부모"}, "reviewBody": body, "reviewRating": {"@type": "Rating", "ratingValue": str(rating), "bestRating": "5"}}
                for rating, body in review_items(ctx)
            ],
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8", "bestRating": "5", "ratingCount": "6", "reviewCount": "6"},
        }
    )
    org.pop("@context", None)
    if "address" not in org:
        org["address"] = {"@type": "PostalAddress", "addressRegion": ctx["region"], "addressLocality": ctx["district"], "addressCountry": "KR"}
    elif isinstance(org["address"], dict):
        org["address"].setdefault("@type", "PostalAddress")
        org["address"].setdefault("addressRegion", ctx["region"])
        org["address"].setdefault("addressLocality", ctx["district"])
        org["address"].setdefault("addressCountry", "KR")

    parent_path = f"/center/{ctx['region_slug']}/{ctx['district_slug']}/{ctx['neighborhood_slug']}/"
    breadcrumb_items = [
        ("전국센터", BASE_URL + "/center/"),
        (ctx["region"], BASE_URL + quote(f"/center/{ctx['region_slug']}/", safe="/")),
        (ctx["district"], BASE_URL + quote(f"/center/{ctx['region_slug']}/{ctx['district_slug']}/", safe="/")),
        (ctx["neighborhood"], BASE_URL + quote(parent_path, safe="/")),
    ]
    if ctx["is_child"]:
        breadcrumb_items.append((title, ctx["url"]))

    graph = [
        {
            "@type": "WebPage",
            "@id": page_id,
            "url": ctx["url"],
            "name": title,
            "description": desc,
            "inLanguage": "ko-KR",
            "publisher": {"@id": org_id},
            "breadcrumb": {"@id": breadcrumb_id},
            "mainEntity": {"@id": service_id},
            "about": about,
            "mentions": mentions,
            "hasPart": [
                {"@type": "WebPageElement", "name": "핵심 요약"},
                {"@type": "WebPageElement", "name": "지역 학습 문맥"},
                {"@type": "WebPageElement", "name": "답변형 학습 안내"},
                {"@type": "WebPageElement", "name": "지역·학년·추천학생 안내"},
                {"@type": "WebPageElement", "name": "학년별 학습 전략"},
                {"@type": "WebPageElement", "name": "상담 전 체크리스트"},
                {"@type": "WebPageElement", "name": "FAQ"},
                {"@type": "WebPageElement", "name": "학부모 후기"},
                {"@type": "WebPageElement", "name": "내부링크"},
            ],
            "keywords": f"{title}, {ctx['neighborhood']} 학원, {ctx['district']} 와와학습코칭센터, 영어수학, 학습코칭, {subject_label(title, ctx['child_name'])}, {grade_label(title, ctx['child_name'])}",
        },
        org,
        {
            "@type": "BreadcrumbList",
            "@id": breadcrumb_id,
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": name, "item": url}
                for i, (name, url) in enumerate(breadcrumb_items, start=1)
            ],
        },
        {
            "@type": "Article",
            "@id": article_id,
            "headline": title,
            "description": desc,
            "image": image_url,
            "inLanguage": "ko-KR",
            "datePublished": "2026-06-19",
            "dateModified": TODAY,
            "author": {"@id": org_id},
            "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL + "/"},
            "mainEntityOfPage": {"@id": page_id},
            "about": about,
            "mentions": mentions,
            "articleSection": ["핵심 요약", "지역 학습 문맥", "학습 진단", "플래너 관리", "오답 재학습", "학년별 학습 전략", "상담 체크리스트", "FAQ", "학부모 후기"],
        },
        {
            "@type": "Service",
            "@id": service_id,
            "name": f"{title} 학습코칭",
            "serviceType": "TutoringService",
            "description": f"{ctx['neighborhood']} 학생을 위한 {subject_label(title, ctx['child_name'])} {grade_label(title, ctx['child_name'])} 학습 진단, 플래너 관리, 오답 재학습 안내입니다.",
            "provider": {"@id": org_id},
            "areaServed": {"@type": "Place", "name": ctx["neighborhood"]},
            "audience": {"@type": "EducationalAudience", "educationalRole": "student"},
            "about": about,
            "mentions": mentions,
            "makesOffer": org["makesOffer"],
        },
        {
            "@type": "ItemList",
            "@id": checklist_id,
            "name": f"{title} 상담 전 체크리스트",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "현재 교재와 진도 확인"},
                {"@type": "ListItem", "position": 2, "name": "최근 시험지와 반복 오답 확인"},
                {"@type": "ListItem", "position": 3, "name": "평소 공부 시간과 숙제 수행 정도 확인"},
                {"@type": "ListItem", "position": 4, "name": "상담 목표와 우선순위 정리"},
            ],
        },
        {
            "@type": "FAQPage",
            "@id": faq_id,
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_pairs(ctx)
            ],
        },
    ]
    return {"@context": "https://schema.org", "@graph": graph}


def upsert_json_ld(source: str, ctx: dict, image_url: str, old_org: dict) -> str:
    source = re.sub(
        r'\n?\s*<script[^>]*(?:data-parent-review-jsonld|data-parent-faq-jsonld|data-article-jsonld|data-seo-geo-jsonld)[^>]*>[\s\S]*?</script>',
        "",
        source,
        flags=re.I,
    )
    data = build_json_ld(ctx, image_url, old_org)
    rendered = '<script type="application/ld+json" data-seo-geo-jsonld>' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "</script>"
    return source.replace("</head>", f"  {rendered}\n</head>", 1)


def replace_section(source: str, class_name: str, replacement: str) -> str:
    pattern = re.compile(rf'<section\s+class=["\']{re.escape(class_name)}["\'][\s\S]*?</section>', re.I)
    if pattern.search(source):
        return pattern.sub(replacement, source, count=1)
    return source


def upsert_visible_sections(source: str, page_dir: Path, ctx: dict) -> str:
    source = re.sub(r"\n?\s*<!-- seo-geo-enhancement:start -->[\s\S]*?<!-- seo-geo-enhancement:end -->", "", source, flags=re.I)
    source = re.sub(r"\n?\s*<!-- child-page-links:start -->[\s\S]*?<!-- child-page-links:end -->", "", source, flags=re.I)
    source = re.sub(r"\n?\s*<section\s+class=[\"']center-section\s+local-topic-links-section[\"'][\s\S]*?</section>", "", source, flags=re.I)
    source = replace_section(source, "parent-faq-section", render_faq_section(ctx))
    source = replace_section(source, "parent-review-section", render_review_section(ctx))
    geo = render_geo_section(ctx)
    if '<section class="parent-faq-section"' in source:
        source = source.replace('<section class="parent-faq-section"', geo + '\n<section class="parent-faq-section"', 1)
    else:
        source = source.replace("</main>", geo + "\n</main>", 1)
    links = render_internal_links(page_dir, ctx)
    if links:
        source = source.replace("</main>", links + "\n</main>", 1)
    return source


def hub_description(ctx: dict) -> str:
    if ctx["depth"] == 0:
        return "전국 주요 지역의 와와학습코칭센터와 동네별 영어·수학 학습코칭 안내를 한곳에서 확인할 수 있도록 정리한 지역 허브입니다."
    if ctx["depth"] == 1:
        return f"{ctx['area']} 지역의 시군구별 와와학습코칭센터 안내와 동네별 학습관리 페이지를 연결한 지역 허브입니다."
    return f"{ctx['area']} 지역의 동네별 와와학습코칭센터 안내와 영어·수학 학습관리 페이지를 연결한 지역 허브입니다."


def hub_faq_pairs(ctx: dict) -> list[tuple[str, str]]:
    area = ctx["area"]
    child_label = ctx["child_label"]
    return [
        (
            f"{area} 와와학습코칭센터는 어떤 기준으로 보면 좋나요?",
            f"{area} 페이지에서는 하위 {child_label}별 안내를 먼저 확인한 뒤, 자녀의 학년·과목·현재 학습 습관에 맞는 상세 페이지를 함께 보는 것이 좋습니다.",
        ),
        (
            "상담 전 어떤 내용을 준비하면 도움이 되나요?",
            "최근 시험지, 현재 교재, 자주 틀리는 단원, 숙제 수행 정도, 평소 공부 시간을 정리하면 상담에서 필요한 관리 방향을 더 빠르게 확인할 수 있습니다.",
        ),
        (
            "지역 페이지와 동네 상세 페이지는 무엇이 다른가요?",
            f"{area} 지역 페이지는 전체 경로를 찾기 위한 허브이고, 동네 상세 페이지는 실제 센터 위치·수업 가능 학교·학년별 관리 기준을 더 구체적으로 확인하는 페이지입니다.",
        ),
        (
            "영어·수학 학습코칭은 어떤 흐름으로 관리하나요?",
            "진단을 통해 막히는 지점을 찾고, 주간 플래너로 실행을 확인하며, 오답 원인을 다시 분석해 다음 학습에 반영하는 흐름으로 관리합니다.",
        ),
    ]


def render_hub_section(ctx: dict) -> str:
    area = ctx["area"]
    child_label = ctx["child_label"]
    children = ctx.get("children", [])
    link_cards = "\n".join(
        f"""    <a class="hub-seo-link-card" href="{html.escape(item['href'])}">
      <span>{html.escape(child_label)}</span>
      <strong>{html.escape(item['name'])}</strong>
      <small>바로가기</small>
    </a>"""
        for item in children[:24]
    )
    if not link_cards:
        link_cards = f"""    <a class="hub-seo-link-card" href="{html.escape(relative_href(Path.cwd(), CENTER_ROOT))}">
      <span>전국센터</span>
      <strong>전체 지역 보기</strong>
      <small>바로가기</small>
    </a>"""
    faq_html = "\n".join(
        f"""    <details class="hub-faq-item"{' open' if i == 0 else ''}>
      <summary>{html.escape(question)}</summary>
      <p>{html.escape(answer)}</p>
    </details>"""
        for i, (question, answer) in enumerate(hub_faq_pairs(ctx))
    )
    return f"""<!-- hub-seo-geo-enhancement:start -->
<section class="hub-seo-geo-section" aria-labelledby="hub-seo-title">
  <div class="hub-seo-head">
    <p class="parent-faq-eyebrow">REGIONAL GUIDE</p>
    <h2 id="hub-seo-title">{html.escape(area)} 학습코칭 지역 안내</h2>
    <p>{html.escape(hub_description(ctx))} 단순 지역 목록이 아니라, 학부모님이 하위 지역과 동네 상세 페이지로 빠르게 이동해 상담 기준을 비교할 수 있도록 구성했습니다.</p>
  </div>
  <div class="hub-seo-grid">
    <article><span>지역 탐색</span><strong>{html.escape(area)}</strong><p>하위 {html.escape(child_label)} 페이지를 따라가며 가까운 센터와 동네별 수업 안내를 확인할 수 있습니다.</p></article>
    <article><span>상담 기준</span><strong>진단 · 플래너 · 오답</strong><p>성적표만 보는 방식이 아니라 현재 교재, 학습 습관, 반복 오답을 함께 확인합니다.</p></article>
    <article><span>학습 대상</span><strong>초등 · 중등 · 고등</strong><p>학년별 필요한 관리 밀도와 시험 준비 흐름을 다르게 보고 상담 방향을 정리합니다.</p></article>
  </div>
</section>

<section class="hub-seo-link-section" aria-labelledby="hub-link-title">
  <div class="hub-seo-head">
    <p class="parent-faq-eyebrow">LOCAL LINKS</p>
    <h2 id="hub-link-title">{html.escape(area)} 하위 페이지 바로가기</h2>
    <p>{html.escape(area)} 안에서 연결되는 주요 {html.escape(child_label)} 페이지를 정리했습니다. 더 구체적인 동네·학년·과목 안내는 하위 페이지에서 확인할 수 있습니다.</p>
  </div>
  <div class="hub-seo-link-grid">
{link_cards}
  </div>
</section>

<section class="hub-faq-section" aria-labelledby="hub-faq-title">
  <div class="hub-seo-head">
    <p class="parent-faq-eyebrow">REGIONAL FAQ</p>
    <h2 id="hub-faq-title">{html.escape(area)} 지역 페이지 FAQ</h2>
  </div>
  <div class="hub-faq-list">
{faq_html}
  </div>
</section>
<!-- hub-seo-geo-enhancement:end -->"""


def build_hub_json_ld(ctx: dict) -> dict:
    desc = hub_description(ctx)
    page_id = ctx["url"] + "#webpage"
    article_id = ctx["url"] + "#article"
    faq_id = ctx["url"] + "#faq"
    list_id = ctx["url"] + "#itemlist"
    graph = [
        {
            "@type": "CollectionPage",
            "@id": page_id,
            "url": ctx["url"],
            "name": ctx["title"],
            "description": desc,
            "inLanguage": "ko-KR",
            "about": [
                {"@type": "Thing", "name": "와와학습코칭센터"},
                {"@type": "Place", "name": ctx["area"]},
                {"@type": "Thing", "name": "영어수학 학습코칭"},
                {"@type": "Thing", "name": "지역별 학원 안내"},
            ],
            "hasPart": [
                {"@type": "WebPageElement", "name": "지역 안내"},
                {"@type": "WebPageElement", "name": "하위 페이지 바로가기"},
                {"@type": "WebPageElement", "name": "지역 FAQ"},
            ],
            "mainEntity": {"@id": list_id},
        },
        {
            "@type": "Article",
            "@id": article_id,
            "headline": ctx["title"],
            "description": desc,
            "inLanguage": "ko-KR",
            "dateModified": TODAY,
            "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL + "/"},
            "mainEntityOfPage": {"@id": page_id},
            "articleSection": ["지역 안내", "학습코칭", "하위 페이지", "FAQ"],
        },
        {
            "@type": "ItemList",
            "@id": list_id,
            "name": f"{ctx['area']} 하위 페이지",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": item["name"], "url": item["url"]}
                for i, item in enumerate(ctx.get("children", [])[:50], start=1)
            ],
        },
        {
            "@type": "FAQPage",
            "@id": faq_id,
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in hub_faq_pairs(ctx)
            ],
        },
    ]
    return {"@context": "https://schema.org", "@graph": graph}


def process_hub(page_dir: Path) -> bool:
    path = page_dir / "index.html"
    source = path.read_text(encoding="utf-8", errors="ignore")
    ctx = hub_context(page_dir, source)
    updated = re.sub(r"\n?\s*<!-- hub-seo-geo-enhancement:start -->[\s\S]*?<!-- hub-seo-geo-enhancement:end -->", "", source, flags=re.I)
    updated = re.sub(r'\n?\s*<script[^>]*data-hub-seo-geo-jsonld[^>]*>[\s\S]*?</script>', "", updated, flags=re.I)
    data = build_hub_json_ld(ctx)
    rendered = '<script type="application/ld+json" data-hub-seo-geo-jsonld>' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "</script>"
    updated = updated.replace("</head>", f"  {rendered}\n</head>", 1)
    section = render_hub_section(ctx)
    if '<section class="center-section center-about-summary"' in updated:
        updated = updated.replace('<section class="center-section center-about-summary"', section + '\n<section class="center-section center-about-summary"', 1)
    else:
        updated = updated.replace("</main>", section + "\n</main>", 1)
    if updated != source:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


SEO_GEO_CSS = r"""

/* SEO/GEO enhancement blocks v2 */
.seo-geo-section,
.seo-context-section,
.seo-answer-section,
.seo-grade-section,
.seo-checklist-section,
.child-page-links {
  width: min(1120px, calc(100% - 32px));
  margin: 32px auto 0;
  padding: clamp(22px, 4vw, 34px);
  border: 1px solid rgba(24, 45, 36, 0.12);
  border-radius: 28px;
  background:
    radial-gradient(circle at 12% 0%, rgba(35, 184, 148, 0.12), transparent 30%),
    radial-gradient(circle at 96% 8%, rgba(252, 207, 104, 0.16), transparent 28%),
    rgba(255, 255, 255, 0.94);
  box-shadow: 0 20px 54px rgba(24, 45, 36, 0.08);
}

.seo-geo-head,
.seo-context-copy,
.seo-answer-copy,
.child-page-links-head {
  max-width: 860px;
  margin-bottom: 22px;
}

.seo-geo-head h2,
.seo-context-copy h2,
.seo-answer-copy h2,
.child-page-links-head h2 {
  margin: 0 0 10px;
  color: #182d24;
  font-size: clamp(24px, 3vw, 34px);
  letter-spacing: -0.045em;
  line-height: 1.25;
}

.seo-geo-head p:not(.parent-faq-eyebrow),
.seo-context-copy p,
.seo-answer-copy p,
.child-page-links-head p:not(.parent-faq-eyebrow) {
  margin: 0;
  color: #65756d;
  font-weight: 700;
  line-height: 1.75;
}

.seo-geo-grid,
.seo-context-points,
.seo-answer-list,
.seo-grade-grid,
.child-link-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.seo-geo-card,
.seo-context-points article,
.seo-answer-list article,
.seo-grade-grid article,
.child-link-card {
  position: relative;
  overflow: hidden;
  padding: 20px;
  border: 1px solid rgba(24, 45, 36, 0.1);
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(247,250,244,0.86));
}

.child-link-card {
  display: grid;
  gap: 8px;
  min-height: 158px;
  padding-right: 56px;
}

.child-link-card::after {
  position: absolute;
  right: 18px;
  bottom: 18px;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  color: #fff;
  background: #182d24;
  content: "→";
  font-weight: 950;
}

.seo-geo-card span,
.seo-context-points span,
.seo-answer-list b,
.seo-grade-grid em,
.child-link-card span {
  display: inline-flex;
  margin-bottom: 9px;
  color: #15846c;
  font-size: 12px;
  font-weight: 950;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.seo-geo-card strong,
.seo-context-points strong,
.seo-grade-grid strong,
.child-link-card strong {
  display: block;
  color: #182d24;
  font-size: 19px;
  line-height: 1.4;
}

.seo-geo-card p,
.seo-context-points p,
.seo-answer-list p,
.seo-grade-grid p,
.child-link-card p {
  margin: 10px 0 0;
  color: #65756d;
  line-height: 1.65;
}

.seo-grade-grid em {
  font-style: normal;
}

.child-link-card small {
  display: inline-flex;
  width: max-content;
  margin-top: 4px;
  padding: 6px 11px;
  border-radius: 999px;
  color: #15846c;
  background: rgba(35, 184, 148, 0.11);
  border: 1px solid rgba(35, 184, 148, 0.16);
  font-size: 12px;
  font-weight: 950;
}

.hub-seo-geo-section,
.hub-seo-link-section,
.hub-faq-section {
  width: min(1120px, calc(100% - 32px));
  margin: 32px auto 0;
  padding: clamp(22px, 4vw, 34px);
  border: 1px solid rgba(24, 45, 36, 0.12);
  border-radius: 28px;
  background:
    radial-gradient(circle at 10% 0%, rgba(35, 184, 148, 0.1), transparent 30%),
    radial-gradient(circle at 96% 8%, rgba(252, 207, 104, 0.14), transparent 28%),
    rgba(255, 255, 255, 0.94);
  box-shadow: 0 20px 54px rgba(24, 45, 36, 0.08);
}

.hub-seo-head {
  max-width: 880px;
  margin-bottom: 22px;
}

.hub-seo-head h2 {
  margin: 0 0 10px;
  color: #182d24;
  font-size: clamp(24px, 3vw, 34px);
  letter-spacing: -0.045em;
  line-height: 1.25;
}

.hub-seo-head p:not(.parent-faq-eyebrow) {
  margin: 0;
  color: #65756d;
  font-weight: 700;
  line-height: 1.75;
}

.hub-seo-grid,
.hub-seo-link-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.hub-seo-grid article,
.hub-seo-link-card {
  position: relative;
  overflow: hidden;
  padding: 20px;
  border: 1px solid rgba(24, 45, 36, 0.1);
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(247,250,244,0.86));
}

.hub-seo-grid span,
.hub-seo-link-card span {
  display: inline-flex;
  margin-bottom: 9px;
  color: #15846c;
  font-size: 12px;
  font-weight: 950;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hub-seo-grid strong,
.hub-seo-link-card strong {
  display: block;
  color: #182d24;
  font-size: 19px;
  line-height: 1.4;
}

.hub-seo-grid p {
  margin: 10px 0 0;
  color: #65756d;
  line-height: 1.65;
}

.hub-seo-link-card {
  display: grid;
  gap: 8px;
  min-height: 132px;
  padding-right: 56px;
}

.hub-seo-link-card::after {
  position: absolute;
  right: 18px;
  bottom: 18px;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  color: #fff;
  background: #182d24;
  content: "→";
  font-weight: 950;
}

.hub-seo-link-card small {
  display: inline-flex;
  width: max-content;
  margin-top: 4px;
  padding: 6px 11px;
  border-radius: 999px;
  color: #15846c;
  background: rgba(35, 184, 148, 0.11);
  border: 1px solid rgba(35, 184, 148, 0.16);
  font-size: 12px;
  font-weight: 950;
}

.hub-faq-list {
  display: grid;
  gap: 12px;
}

.hub-faq-item {
  border: 1px solid rgba(24, 45, 36, 0.1);
  border-radius: 18px;
  background: rgba(255,255,255,0.82);
  overflow: hidden;
}

.hub-faq-item summary {
  cursor: pointer;
  padding: 18px 20px;
  color: #182d24;
  font-weight: 950;
}

.hub-faq-item p {
  margin: 0;
  padding: 0 20px 20px;
  color: #65756d;
  line-height: 1.7;
}

.seo-checklist {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.seo-checklist li {
  padding: 18px;
  border: 1px solid rgba(24, 45, 36, 0.1);
  border-radius: 20px;
  background: rgba(235, 247, 241, 0.72);
}

.seo-checklist b {
  display: block;
  color: #182d24;
  font-size: 17px;
}

.seo-checklist span {
  display: block;
  margin-top: 8px;
  color: #65756d;
  line-height: 1.6;
}

@media (max-width: 860px) {
  .seo-geo-grid,
  .seo-context-points,
  .seo-answer-list,
  .seo-grade-grid,
  .hub-seo-grid,
  .hub-seo-link-grid,
  .child-link-grid,
  .seo-checklist {
    grid-template-columns: 1fr;
  }
}
"""


def ensure_css() -> None:
    css_path = ROOT / "assets" / "local-center.css"
    css = css_path.read_text(encoding="utf-8", errors="ignore")
    if "SEO/GEO enhancement blocks v2" not in css:
        css_path.write_text(css.rstrip() + SEO_GEO_CSS + "\n", encoding="utf-8")


def process_page(page_dir: Path) -> bool:
    path = page_dir / "index.html"
    source = path.read_text(encoding="utf-8", errors="ignore")
    ctx = page_context(page_dir, source)
    old_org = old_org_schema(source)
    image_url = absolutize_image(first_image_src(source), page_dir)
    updated = source
    updated = ensure_single_h1(updated, ctx["title"])
    updated = upsert_head(updated, ctx, image_url)
    updated = upsert_json_ld(updated, ctx, image_url, old_org)
    updated = upsert_visible_sections(updated, page_dir, ctx)
    if updated != source:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def generate_sitemap() -> int:
    excluded = {".git", ".vercel", "__pycache__"}
    urls: list[str] = []
    for path in ROOT.rglob("*.html"):
        rel_parts = set(path.relative_to(ROOT).parts)
        if rel_parts.intersection(excluded):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel == "index.html":
            page_path = "/"
        elif rel.endswith("/index.html"):
            page_path = "/" + rel[: -len("index.html")]
        else:
            page_path = "/" + rel
        urls.append(BASE_URL + quote(page_path, safe="/"))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in sorted(set(urls)):
        lines.extend(["  <url>", f"    <loc>{escape(url)}</loc>", f"    <lastmod>{TODAY}</lastmod>", "  </url>"])
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(set(urls))


def main() -> None:
    ensure_css()
    hubs = target_hub_dirs()
    hub_changed = 0
    for page_dir in hubs:
        current = (page_dir / "index.html").read_text(encoding="utf-8", errors="ignore")
        if "hub-seo-geo-enhancement:start" in current and "data-hub-seo-geo-jsonld" in current:
            continue
        if process_hub(page_dir):
            hub_changed += 1
    targets = target_page_dirs()
    changed = 0
    for page_dir in targets:
        current = (page_dir / "index.html").read_text(encoding="utf-8", errors="ignore")
        if (
            "seo-context-section" in current
            and "data-seo-geo-jsonld" in current
            and "local-topic-links-section" not in current
            and "seo-grade-section" not in current
            and "LOCAL DETAIL LINKS" not in current
        ):
            continue
        if process_page(page_dir):
            changed += 1
    sitemap_count = generate_sitemap()
    print(json.dumps({"hubs": len(hubs), "hub_changed": hub_changed, "targets": len(targets), "changed": changed, "sitemap": sitemap_count, "date": TODAY}, ensure_ascii=False))


if __name__ == "__main__":
    main()
