from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "초등학생-공부법", "중학생-공부법", "고등학생-공부법", "시험기간-공부법",
    "수학-공부법", "영어-공부법", "국어-공부법", "오답노트-작성법",
    "자기주도학습-방법", "학부모-상담-체크리스트", "중학생-시험기간-계획표",
    "고등학생-내신-공부법", "고1-첫내신-준비법", "중1-공부법",
    "초등-공부습관-체크리스트", "공부를-안하는-아이-원인", "학원-선택-체크리스트",
    "영어-단어-암기법", "수학-서술형-공부법", "수행평가-준비법",
    "학습코칭학원-일반학원-차이", "내신관리학원-선택법", "오답관리-잘하는-학원",
    "영어수학학원-선택기준", "학부모가-물어볼-상담질문",
]


def build_summary_html(h1: str, desc: str, links: list[tuple[str, str]]) -> str:
    # Deliberately omits the ai-summary-grid cards: those would just repeat the
    # edu-answer-grid section that already follows immediately below, which is
    # redundant in-page duplication rather than a genuine AI-readable synopsis.
    link_html = "".join(f'<a href="{href}">{html.escape(text)}</a>' for text, href in links[:3])
    return (
        f'<section class="ai-entity-summary compact" aria-label="{html.escape(h1)} AI 요약">'
        f'<p class="ai-summary-kicker">AI SUMMARY</p>'
        f'<h2>{html.escape(h1)} 핵심 요약</h2>'
        f'<p class="ai-summary-lead">{html.escape(desc)}</p>'
        f'<div class="ai-summary-links">{link_html}</div>'
        f'</section>'
    )


def process_page(slug: str) -> bool:
    path = ROOT / "교육정보" / slug / "index.html"
    source = path.read_text(encoding="utf-8")
    if "ai-entity-summary" in source:
        return False

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S).group(1)
    h1 = re.sub(r"<[^>]+>", "", h1).strip()
    desc = re.search(r'name="description" content="([^"]*)"', source).group(1)

    links = re.findall(r'<div class="edu-related-links">(.*?)</div>', source, re.S)
    link_pairs = re.findall(r'<a href="([^"]*)">([^<]*)</a>', links[0]) if links else []
    link_pairs = [(text, href) for href, text in link_pairs]

    summary_html = build_summary_html(h1, desc, link_pairs)

    updated, count = re.subn(
        r'(<p class="edu-lead">.*?</p>)',
        lambda m: m.group(1) + summary_html,
        source,
        count=1,
        flags=re.S,
    )
    if count == 0:
        raise RuntimeError(f"edu-lead anchor not found in {slug}")

    # ensure ai-summary.css is linked
    if "ai-summary.css" not in updated:
        updated = updated.replace(
            '<link rel="stylesheet" href="../../assets/education.css">',
            '<link rel="stylesheet" href="../../assets/education.css">\n  <link rel="stylesheet" href="../../assets/ai-summary.css">',
            1,
        )

    # add "AI 검색 요약" to Article.mentions if not already present
    m = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', updated, re.S)
    data = json.loads(m.group(2))
    for node in data["@graph"]:
        if node.get("@type") == "Article":
            mentions = node.setdefault("mentions", [])
            if not any(x.get("name") == "AI 검색 요약" for x in mentions):
                mentions.append({"@type": "Thing", "name": "AI 검색 요약"})
    new_jsonld = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    updated = updated[: m.start()] + m.group(1) + new_jsonld + m.group(3) + updated[m.end():]

    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    for slug in PAGES:
        print(f"{slug}: changed={process_page(slug)}")


if __name__ == "__main__":
    main()
