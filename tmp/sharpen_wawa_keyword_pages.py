from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "center"
TODAY = date.today().isoformat()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def title_from_html(source: str) -> str:
    match = re.search(r"<title>(.*?)</title>", source, re.S | re.I)
    if match:
        return clean_text(match.group(1)).split("|", 1)[0].strip()
    match = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S | re.I)
    return clean_text(match.group(1)) if match else ""


def json_scripts(source: str) -> list[tuple[re.Match[str], dict]]:
    result: list[tuple[re.Match[str], dict]] = []
    for match in re.finditer(
        r'<script([^>]*)type=["\']application/ld\+json["\']([^>]*)>(.*?)</script>',
        source,
        re.S | re.I,
    ):
        try:
            data = json.loads(match.group(3))
        except Exception:
            continue
        if isinstance(data, dict):
            result.append((match, data))
    return result


def breadcrumb_names(source: str) -> list[str]:
    def walk(node):
        if isinstance(node, dict):
            typ = node.get("@type")
            if typ == "BreadcrumbList":
                return [
                    str(item.get("name", "")).strip()
                    for item in node.get("itemListElement", [])
                    if isinstance(item, dict)
                ]
            for value in node.values():
                found = walk(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        return []

    for _match, data in json_scripts(source):
        found = walk(data)
        if found:
            return found
    return []


def page_context(page_dir: Path, source: str) -> dict:
    rel = page_dir.relative_to(CENTER_ROOT)
    parts = rel.parts
    crumbs = breadcrumb_names(source)
    region = crumbs[1] if len(crumbs) > 1 else (parts[0] if len(parts) > 0 else "")
    district = crumbs[2] if len(crumbs) > 2 else (parts[1] if len(parts) > 1 else "")
    neighborhood = crumbs[3] if len(crumbs) > 3 else (parts[2] if len(parts) > 2 else "")
    title = title_from_html(source)
    return {
        "title": title,
        "region": region,
        "district": district,
        "neighborhood": neighborhood,
        "child": parts[3] if len(parts) > 3 else "",
        "depth": len(parts),
    }


def grade_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(token in text for token in ("고등", "고1", "고2", "고3", "highschool")):
        return "고등반"
    if any(token in text for token in ("중등", "중학생", "중1", "중2", "중3", "middleschool")):
        return "중등반"
    if any(token in text for token in ("초등", "초등학생", "elementary", "초3", "초4", "초5", "초6")):
        return "초등반"
    return "초등·중등·고등"


def student_label(grade: str) -> str:
    if grade == "고등반":
        return "고등학생"
    if grade == "중등반":
        return "중학생"
    if grade == "초등반":
        return "초등학생"
    return "초등·중등·고등 학생"


def subject_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(token in text for token in ("국영수", "전과목", "all")):
        return "국어·영어·수학"
    if any(token in text for token in ("영수", "수학영어", "영어수학", "영어 수학", "영어·수학", "englishmath", "mathenglish")):
        return "영어·수학"
    if "english" in text or "영어" in text:
        return "영어"
    if "math" in text or "수학" in text:
        return "수학"
    return "영어·수학"


def subject_focus(subject: str, grade: str) -> str:
    if subject == "수학":
        return "개념 이해, 유형 풀이, 반복 오답, 시험 전 복습 순서"
    if subject == "영어":
        return "어휘·문법·독해 흐름, 학교별 시험 범위, 지문 분석과 반복 오답"
    if subject == "국어·영어·수학":
        return "국어 독해, 영어 어휘·문법, 수학 개념·유형을 나누어 보는 종합 관리"
    return "영어와 수학의 현재 진도, 과목별 약점, 주간 학습 실행 상태"


def description_for(ctx: dict) -> str:
    title = ctx["title"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    return (
        f"{title} 안내입니다. {ctx['region']} {ctx['district']} {ctx['neighborhood']} 기준으로 "
        f"{subject} 학습 진단, {grade} 수업 흐름, 플래너 관리, 오답 재학습, 상담 전 확인사항을 정리했습니다."
    )


def render_search_answer(ctx: dict) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    student = student_label(grade)
    focus = subject_focus(subject, grade)
    return f"""<section class="article-search-answer" aria-label="{html.escape(title)} 검색 의도 답변">
  <p class="article-answer-kicker">검색 의도 바로 답변</p>
  <h2>{html.escape(title)}, 상담 전 먼저 확인할 기준</h2>
  <p class="article-answer-lead">{html.escape(title)}을 찾는 학부모님이라면 단순히 가까운 위치만 보기보다 {html.escape(student)}에게 필요한 {html.escape(subject)} 진단, 수업 후 실행 점검, 오답 재학습이 실제로 이어지는지 먼저 확인하는 것이 좋습니다. 이 페이지는 {html.escape(area)} 기준으로 {html.escape(title)} 선택 전에 볼 핵심 기준을 먼저 정리했습니다.</p>
  <ul class="article-answer-points">
    <li><span>1. 검색어와 수업 대상 확인</span><p>{html.escape(title)} 페이지에서는 {html.escape(grade)} 학생에게 필요한 {html.escape(subject)} 관리 기준을 중심으로 확인할 수 있습니다.</p></li>
    <li><span>2. 수업 이후 관리 방식</span><p>{html.escape(focus)}가 수업 후 플래너와 오답 재학습으로 연결되는지 보는 것이 중요합니다.</p></li>
    <li><span>3. 상담 전 준비 자료</span><p>현재 교재, 최근 시험지, 자주 틀리는 단원, 숙제 수행 정도를 준비하면 {html.escape(area)} 학생에게 맞는 학습 방향을 더 정확히 잡을 수 있습니다.</p></li>
  </ul>
</section>"""


def render_intro(ctx: dict) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    focus = subject_focus(subject, grade)
    return f"""<p class="article-intro">
{html.escape(ctx['region'])} {html.escape(ctx['district'])} {html.escape(area)}에서 {html.escape(title)}을 알아볼 때는 학원 이름만 비교하기보다 학생의 현재 진도, 시험 범위, 숙제 실행, 반복 오답을 함께 보는 것이 중요합니다.
와와학습코칭센터는 {html.escape(subject)} 학습을 기준으로 {html.escape(focus)}를 점검하고, 진단 → 계획 → 수업 확인 → 오답 재학습 흐름이 이어지도록 관리합니다.
상담 전에는 학생의 최근 학습 자료를 바탕으로 {html.escape(grade)}에 필요한 우선순위를 정리하는 것이 좋습니다.
</p>"""


def render_ai_summary(ctx: dict) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    student = student_label(grade)
    focus = subject_focus(subject, grade)
    return f"""<section class="article-section article-ai-summary" aria-label="{html.escape(title)} 핵심 요약">
    <p class="article-ai-kicker">AI SUMMARY</p>
    <h2>{html.escape(title)} 한눈에 보기</h2>
    <p class="article-ai-lead">{html.escape(title)}을 찾는 학생과 학부모가 빠르게 판단할 수 있도록, {html.escape(area)} 기준의 수업 대상과 상담 전 확인할 내용을 요약했습니다.</p>
    <div class="article-ai-grid">
      <article class="article-ai-card"><strong>추천 대상</strong><p>{html.escape(student)} 중 현재 진도, 반복 오답, 시험 준비 순서가 흔들리는 학생에게 적합합니다.</p></article>
      <article class="article-ai-card"><strong>관리 과목</strong><p>{html.escape(subject)} 학습을 중심으로 {html.escape(focus)}를 함께 확인합니다.</p></article>
      <article class="article-ai-card"><strong>상담 준비</strong><p>최근 시험지, 현재 교재, 자주 틀리는 단원, 평소 공부 시간을 준비하면 더 정확한 상담이 가능합니다.</p></article>
    </div>
    <div class="article-ai-links"><a href="../../../../../guide/">학습가이드</a><a href="../../../../../교육정보/">교육정보</a><a href="../../../../../교육정보/수학-서술형-공부법/">관련 공부법</a></div>
  </section>"""


def render_core_points(ctx: dict) -> str:
    title = ctx["title"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    focus = subject_focus(subject, grade)
    return f"""<section class="article-section article-local-feature-section">
<h2>{html.escape(title)} 핵심 포인트</h2>
<div class="article-card-grid">
<article class="article-card">
<strong>대표 키워드 기준 진단</strong>
<p>{html.escape(title)}이라는 검색 의도에 맞춰 {html.escape(grade)} 학생의 현재 교재, 진도, 시험 범위, 반복 오답을 먼저 확인합니다.</p>
</article>
<article class="article-card">
<strong>{html.escape(subject)} 수업 후 관리</strong>
<p>{html.escape(focus)}를 수업 안에서만 끝내지 않고 플래너 실행과 오답 재학습으로 이어지도록 점검합니다.</p>
</article>
<article class="article-card">
<strong>학부모 상담 기준</strong>
<p>상담 때는 학생의 성적표보다 현재 공부 흐름, 숙제 수행 정도, 시험 전 복습 순서를 함께 보고 필요한 관리 방향을 정리합니다.</p>
</article>
</div>
</section>"""


def sharpen_visible_sections(source: str, ctx: dict) -> str:
    source = re.sub(
        r'<section\s+class=["\']article-search-answer["\'][\s\S]*?</section>',
        render_search_answer(ctx),
        source,
        count=1,
        flags=re.I,
    )
    source = re.sub(
        r'<p\s+class=["\']article-intro["\'][^>]*>[\s\S]*?</p>',
        render_intro(ctx),
        source,
        count=1,
        flags=re.I,
    )
    source = re.sub(
        r'<section\s+class=["\']article-section article-ai-summary["\'][\s\S]*?</section>',
        render_ai_summary(ctx),
        source,
        count=1,
        flags=re.I,
    )
    title = re.escape(ctx["title"])
    source = re.sub(
        rf'<section\s+class=["\']article-section article-local-feature-section["\']>\s*<h2>{title}\s*핵심 포인트</h2>[\s\S]*?</section>',
        render_core_points(ctx),
        source,
        count=1,
        flags=re.I,
    )
    if "child-page-links-head" in source:
        source = re.sub(
            r'(<div\s+class=["\']child-page-links-head["\']>\s*<p class=["\']parent-faq-eyebrow["\']>LOCAL LINKS</p>\s*<h2[^>]*>)(.*?)(</h2>\s*<p>)(.*?)(</p>)',
            lambda m: (
                m.group(1)
                + html.escape(f"{ctx['neighborhood']} 학습 페이지 이동")
                + m.group(3)
                + html.escape(
                    f"{ctx['neighborhood']} 안에서 연결되는 학년·과목별 상세 페이지입니다. 현재 보고 있는 {ctx['title']}과 함께 필요한 과정만 골라 확인하세요."
                )
                + m.group(5)
            ),
            source,
            count=1,
            flags=re.I | re.S,
        )
        source = source.replace("<small>바로가기</small>", "<small>상세 보기</small>")
    return source


def update_head_descriptions(source: str, ctx: dict) -> str:
    desc = html.escape(description_for(ctx))
    source = re.sub(
        r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta name="description" content="{desc}">',
        source,
        count=1,
        flags=re.I,
    )
    source = re.sub(
        r'<meta\s+property=["\']og:description["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta property="og:description" content="{desc}">',
        source,
        count=1,
        flags=re.I,
    )
    return source


def update_json_ld(source: str, ctx: dict) -> str:
    desc = description_for(ctx)
    subject = subject_label(ctx["title"], ctx["child"])
    grade = grade_label(ctx["title"], ctx["child"])
    changed = source
    scripts = json_scripts(source)
    for match, data in reversed(scripts):
        if not isinstance(data, dict):
            continue
        touched = False

        def walk(node):
            nonlocal touched
            if isinstance(node, dict):
                typ = node.get("@type")
                typ_set = set(typ) if isinstance(typ, list) else {typ}
                if "WebPage" in typ_set or "Article" in typ_set:
                    if node.get("description") is not None:
                        node["description"] = desc
                        touched = True
                if "Article" in typ_set:
                    node["dateModified"] = TODAY
                    touched = True
                if "Service" in typ_set and str(node.get("@id", "")).endswith("#service"):
                    node["description"] = (
                        f"{ctx['neighborhood']} 학생을 위한 {subject} {grade} 학습 진단, "
                        "플래너 관리, 오답 재학습 안내입니다."
                    )
                    touched = True
                if "WebPage" in typ_set and node.get("keywords"):
                    node["keywords"] = f"{ctx['title']}, {ctx['neighborhood']} 학원, {ctx['district']} 와와학습코칭센터, {subject}, 학습코칭, {grade}"
                    touched = True
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        if touched:
            rendered = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            changed = changed[: match.start(3)] + rendered + changed[match.end(3) :]
    return changed


def update_sitemap() -> int:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        return 0
    source = sitemap.read_text(encoding="utf-8", errors="ignore")
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        block = match.group(0)
        loc_match = re.search(r"<loc>(.*?)</loc>", block)
        if loc_match and "/center/" in loc_match.group(1):
            count += 1
            if "<lastmod>" in block:
                return re.sub(r"<lastmod>.*?</lastmod>", f"<lastmod>{TODAY}</lastmod>", block, count=1)
            return block.replace("</url>", f"    <lastmod>{TODAY}</lastmod>\n  </url>")
        return block

    updated = re.sub(r"  <url>[\s\S]*?  </url>", repl, source)
    if updated != source:
        sitemap.write_text(updated, encoding="utf-8")
    return count


def main() -> None:
    changed = 0
    targets = 0
    for index in CENTER_ROOT.rglob("index.html"):
        page_dir = index.parent
        rel = page_dir.relative_to(CENTER_ROOT)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth not in {3, 4}:
            continue
        source = index.read_text(encoding="utf-8", errors="ignore")
        ctx = page_context(page_dir, source)
        if not ctx["title"]:
            continue
        targets += 1
        updated = update_head_descriptions(source, ctx)
        updated = sharpen_visible_sections(updated, ctx)
        updated = update_json_ld(updated, ctx)
        if updated != source:
            index.write_text(updated, encoding="utf-8")
            changed += 1
    sitemap_count = update_sitemap()
    print(json.dumps({"targets": targets, "changed": changed, "sitemap_urls_touched": sitemap_count, "date": TODAY}, ensure_ascii=False))


if __name__ == "__main__":
    main()
