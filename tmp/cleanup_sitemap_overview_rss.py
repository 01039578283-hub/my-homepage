from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://wawa-center.kr"
KST = timezone(timedelta(hours=9))
BUILD_DATE = format_datetime(datetime(2026, 7, 14, 18, 30, 0, tzinfo=KST))

OVERVIEW_DESCRIPTION = (
    "와와학습코칭센터 학원소개 페이지입니다. 초등·중등·고등 국어·영어·수학 코칭 방식, "
    "플래너 관리, 오답 재학습, 상담 전 확인할 기준을 한눈에 정리했습니다."
)

OVERVIEW_OG_DESCRIPTION = (
    "초등·중등·고등 국어·영어·수학 코칭 방식과 플래너·오답관리, 상담 기준을 정리한 "
    "와와학습코칭센터 학원소개입니다."
)


def dedupe_sitemap() -> dict[str, int]:
    path = ROOT / "sitemap.xml"
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(r"  <url>\n\s*<loc>(.*?)</loc>\n(?:\s*<lastmod>.*?</lastmod>\n)?\s*</url>\n", re.S)
    seen: set[str] = set()
    removed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal removed
        loc = match.group(1)
        if loc in seen:
            removed += 1
            return ""
        seen.add(loc)
        return match.group(0)

    updated = pattern.sub(repl, source)
    if updated != source:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return {"unique": len(seen), "removed": removed}


def update_overview_meta() -> bool:
    path = ROOT / "overview" / "index.html"
    source = path.read_text(encoding="utf-8")
    updated = source

    updated = re.sub(
        r'<meta name="description" content="[^"]*">',
        f'<meta name="description" content="{html.escape(OVERVIEW_DESCRIPTION, quote=True)}">',
        updated,
        count=1,
    )
    updated = re.sub(
        r'<meta property="og:description" content="[^"]*">',
        f'<meta property="og:description" content="{html.escape(OVERVIEW_OG_DESCRIPTION, quote=True)}">',
        updated,
        count=1,
    )

    script_re = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)

    def update_jsonld(match: re.Match[str]) -> str:
        raw = match.group(2)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        graph = data.get("@graph") if isinstance(data, dict) else None
        if isinstance(graph, list):
            for node in graph:
                if not isinstance(node, dict):
                    continue
                node_type = node.get("@type")
                node_url = node.get("url")
                node_id = node.get("@id")
                if node_type == "WebPage" and (
                    node_url == f"{DOMAIN}/overview/" or node_id == f"{DOMAIN}/overview/#webpage"
                ):
                    node["description"] = OVERVIEW_DESCRIPTION

        return match.group(1) + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + match.group(3)

    updated = script_re.sub(update_jsonld, updated, count=1)

    if updated != source:
        path.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


def page_url(page: Path) -> str:
    rel = page.parent.relative_to(ROOT).as_posix()
    if rel == ".":
        return f"{DOMAIN}/"
    encoded = quote(rel, safe="/")
    return f"{DOMAIN}/{encoded}/"


def extract_meta(content: str, name: str) -> str:
    patterns = [
        rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"',
        rf'<meta\s+property="{re.escape(name)}"\s+content="([^"]*)"',
    ]
    for pattern in patterns:
        m = re.search(pattern, content, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def extract_title(content: str) -> str:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.S | re.I)
    if h1:
        text = re.sub(r"<[^>]+>", " ", h1.group(1))
        text = " ".join(html.unescape(text).split())
        if text:
            return text
    title = re.search(r"<title[^>]*>(.*?)</title>", content, re.S | re.I)
    if title:
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", title.group(1))).split())
    return "와와학습코칭센터"


def extract_excerpt(content: str, description: str) -> str:
    clean = re.sub(r"<script.*?</script>", " ", content, flags=re.S | re.I)
    clean = re.sub(r"<style.*?</style>", " ", clean, flags=re.S | re.I)
    clean = re.sub(r"<[^>]+>", " ", clean)
    text = " ".join(html.unescape(clean).split())
    if description and description in text:
        return description
    if len(text) > 220:
        return text[:220].rstrip() + "…"
    return text or description


def collect_rss_pages() -> list[Path]:
    education = ROOT / "교육정보"
    guide = ROOT / "guide"

    preferred_education = [
        education / "index.html",
        education / "고등학생-공부법" / "index.html",
        education / "고등학생-내신-공부법" / "index.html",
        education / "고1-첫내신-준비법" / "index.html",
        education / "중학생-공부법" / "index.html",
        education / "중1-공부법" / "index.html",
        education / "중학생-시험기간-계획표" / "index.html",
        education / "초등학생-공부법" / "index.html",
        education / "초등-공부습관-체크리스트" / "index.html",
        education / "시험기간-공부법" / "index.html",
        education / "수학-공부법" / "index.html",
        education / "수학-서술형-공부법" / "index.html",
        education / "영어-공부법" / "index.html",
        education / "영어-단어-암기법" / "index.html",
        education / "국어-공부법" / "index.html",
        education / "오답노트-작성법" / "index.html",
        education / "오답관리-잘하는-학원" / "index.html",
        education / "자기주도학습-방법" / "index.html",
        education / "학부모-상담-체크리스트" / "index.html",
        education / "학부모가-물어볼-상담질문" / "index.html",
        education / "학원-선택-체크리스트" / "index.html",
        education / "내신관리학원-선택법" / "index.html",
        education / "영어수학학원-선택기준" / "index.html",
        education / "학습코칭학원-일반학원-차이" / "index.html",
        education / "수행평가-준비법" / "index.html",
        education / "공부를-안하는-아이-원인" / "index.html",
    ]
    preferred_guide = [
        guide / "index.html",
        guide / "consultation-diagnosis" / "index.html",
        guide / "study-planner" / "index.html",
        guide / "error-management" / "index.html",
        guide / "exam-period-plan" / "index.html",
        guide / "school-level-learning" / "index.html",
        guide / "subject-study-plan" / "index.html",
        guide / "highschool-math-study" / "index.html",
        guide / "highschool-english-study" / "index.html",
        guide / "middle-school-math-study" / "index.html",
        guide / "middle-school-english-study" / "index.html",
        guide / "elementary-study-habit" / "index.html",
        guide / "parent-consultation-checklist" / "index.html",
    ]

    ordered: list[Path] = []
    seen: set[Path] = set()
    for page in preferred_education + preferred_guide:
        if page.exists() and page not in seen:
            ordered.append(page)
            seen.add(page)
    return ordered


def generate_rss() -> dict[str, int]:
    pages = collect_rss_pages()
    items: list[str] = []
    for page in pages:
        content = page.read_text(encoding="utf-8", errors="ignore")
        title = extract_title(content)
        description = extract_meta(content, "description")
        if not description:
            description = extract_meta(content, "og:description")
        if not description:
            description = extract_excerpt(content, "")
        excerpt = extract_excerpt(content, description)
        url = page_url(page)
        item = f"""  <item>
    <title>{html.escape(title)}</title>
    <link>{html.escape(url)}</link>
    <guid isPermaLink="true">{html.escape(url)}</guid>
    <pubDate>{BUILD_DATE}</pubDate>
    <description>{html.escape(description)}</description>
    <content:encoded><![CDATA[<p>{html.escape(excerpt)}</p>]]></content:encoded>
  </item>"""
        items.append(item)

    channel_description = (
        "와와학습코칭센터의 교육정보, 학습가이드, 최근 보강한 공부법 콘텐츠를 중심으로 제공하는 RSS 피드입니다."
    )
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>와와학습코칭센터 교육정보 RSS</title>
  <link>{DOMAIN}/</link>
  <description>{html.escape(channel_description)}</description>
  <language>ko-KR</language>
  <lastBuildDate>{BUILD_DATE}</lastBuildDate>
  <atom:link href="{DOMAIN}/rss.xml" rel="self" type="application/rss+xml" />
{chr(10).join(items)}
</channel>
</rss>
"""
    (ROOT / "rss.xml").write_text(rss, encoding="utf-8", newline="\n")
    return {"items": len(items)}


def main() -> None:
    sitemap = dedupe_sitemap()
    overview_changed = update_overview_meta()
    rss = generate_rss()
    print(json.dumps({"sitemap": sitemap, "overview_changed": overview_changed, "rss": rss}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
