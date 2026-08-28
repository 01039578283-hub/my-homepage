#!/usr/bin/env python3
"""Add accessible, page-specific anchor tables of contents.

The script intentionally targets only descendants of ``과목별학원`` and
``학년별학원``. It skips the two top-level landing pages, builds links from
headings that already exist on each page, and can be safely run again after a
page generator has refreshed the static HTML.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACADEMY_ROOTS = (ROOT / "과목별학원", ROOT / "학년별학원")
TOC_START = "<!-- page-anchor-toc:start -->"
TOC_END = "<!-- page-anchor-toc:end -->"

TOC_BLOCK_RE = re.compile(
    rf"(?:[ \t]*\r?\n)+[ \t]*{re.escape(TOC_START)}.*?"
    rf"{re.escape(TOC_END)}(?:[ \t]*\r?\n)+[ \t]*",
    re.IGNORECASE | re.DOTALL,
)
H1_RE = re.compile(r"<h1\b[^>]*>(?P<body>.*?)</h1>", re.IGNORECASE | re.DOTALL)
H2_RE = re.compile(
    r"<h2(?P<attrs>[^>]*)>(?P<body>.*?)</h2>", re.IGNORECASE | re.DOTALL
)
PROSE_SECTION_RE = re.compile(
    r"<section(?P<attrs>[^>]*)>(?P<body>.*?)</section>",
    re.IGNORECASE | re.DOTALL,
)
CLASS_RE = re.compile(
    r"\bclass\s*=\s*([\"'])(?P<class_names>[^\"']+)\1", re.IGNORECASE
)
ID_RE = re.compile(r"\bid\s*=\s*([\"'])(?P<id>[^\"']+)\1", re.IGNORECASE)
ANY_ID_RE = re.compile(r"\bid\s*=\s*([\"'])(?P<id>[^\"']+)\1", re.IGNORECASE)
GENERATED_H2_ID_RE = re.compile(
    r"(<h2\b[^>]*?)\s+id\s*=\s*([\"'])section-\d{2}(?:-\d+)?\2",
    re.IGNORECASE,
)
HERO_OPEN_RE = re.compile(
    r"<section\b[^>]*class\s*=\s*([\"'])[^\"']*\bmath-hero\b[^\"']*\1[^>]*>",
    re.IGNORECASE,
)
GRADE_SOURCE_ALERT_OPEN_RE = re.compile(
    r"<section\b[^>]*class\s*=\s*([\"'])[^\"']*\bgrade-source-alert\b[^\"']*\1[^>]*>",
    re.IGNORECASE,
)
GRADE_SOURCE_ALERT_GAP_RE = re.compile(
    r"(</section>)(?:[ \t]*\r?\n)+[ \t]*"
    r"(?=<section\b[^>]*\bgrade-source-alert\b)",
    re.IGNORECASE,
)
SECTION_TAG_RE = re.compile(r"</?section\b[^>]*>", re.IGNORECASE)
ARTICLE_RE = re.compile(
    r"<article\b[^>]*class\s*=\s*([\"'])[^\"']*\bmath-article\b[^\"']*\1[^>]*>.*?</article>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class TocTarget:
    start: int
    end: int
    attrs: str
    text: str


def visible_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html.unescape(text).split())


def has_class(attrs: str, class_name: str) -> bool:
    match = CLASS_RE.search(attrs)
    return bool(match and class_name in match.group("class_names").split())


def academy_pages() -> list[Path]:
    pages: list[Path] = []
    for academy_root in ACADEMY_ROOTS:
        if not academy_root.exists():
            continue
        for path in academy_root.glob("*/*/index.html"):
            pages.append(path)
    return sorted(set(pages), key=lambda path: path.as_posix())


def page_kind(path: Path) -> str:
    for academy_root in ACADEMY_ROOTS:
        try:
            relative = path.relative_to(academy_root)
        except ValueError:
            continue
        return "detail" if len(relative.parts) == 3 else "unsupported"
    raise ValueError(f"Unexpected academy page: {path}")


def select_targets(source: str, kind: str) -> list[TocTarget]:
    if kind != "detail":
        return []
    article = ARTICLE_RE.search(source)
    if not article:
        return []
    fragment = article.group(0)
    selected: list[TocTarget] = []
    for section in PROSE_SECTION_RE.finditer(fragment):
        attrs = section.group("attrs")
        if not has_class(attrs, "math-prose-section"):
            continue
        heading = H2_RE.search(section.group("body"))
        if not heading:
            continue
        text = visible_text(heading.group("body"))
        if not text:
            continue
        opening_tag_end = article.start() + section.start("body")
        selected.append(
            TocTarget(
                start=article.start() + section.start(),
                end=opening_tag_end,
                attrs=attrs,
                text=text,
            )
        )
    return selected


def existing_target_id(target: TocTarget) -> str | None:
    match = ID_RE.search(target.attrs)
    return match.group("id") if match else None


def add_target_ids(source: str, targets: list[TocTarget]) -> tuple[str, list[tuple[str, str]]]:
    used_ids = {match.group("id") for match in ANY_ID_RE.finditer(source)}
    replacements: list[tuple[int, int, str]] = []
    links: list[tuple[str, str]] = []

    for section_number, target in enumerate(targets, start=1):
        target_id = existing_target_id(target)
        if not target_id:
            base_id = f"section-{section_number:02d}"
            target_id = base_id
            suffix = 2
            while target_id in used_ids:
                target_id = f"{base_id}-{suffix}"
                suffix += 1
            used_ids.add(target_id)
            replacement = f'<section id="{target_id}"{target.attrs}>'
            replacements.append((target.start, target.end, replacement))
        links.append((target_id, target.text))

    for start, end, replacement in reversed(replacements):
        source = source[:start] + replacement + source[end:]
    return source, links


def section_end(source: str, opening_pattern: re.Pattern[str]) -> int | None:
    opening = opening_pattern.search(source)
    if not opening:
        return None

    depth = 0
    for match in SECTION_TAG_RE.finditer(source, opening.start()):
        if match.group(0).lower().startswith("</section"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    return None


def toc_insertion_point(source: str) -> int | None:
    """Keep source-status disclosures ahead of navigational conveniences."""
    return section_end(source, GRADE_SOURCE_ALERT_OPEN_RE) or section_end(
        source, HERO_OPEN_RE
    )


def toc_markup(links: list[tuple[str, str]]) -> str:
    items = []
    for index, (heading_id, text) in enumerate(links, start=1):
        items.append(
            "          <li>"
            f'<a href="#{html.escape(heading_id, quote=True)}">'
            f'<span class="math-page-toc-number" aria-hidden="true">{index:02d}</span>'
            f'<span>{html.escape(text)}</span>'
            "</a></li>"
        )
    return (
        "\n\n    "
        + TOC_START
        + "\n"
        + '    <nav class="math-page-toc" aria-labelledby="math-page-toc-title">\n'
        + '      <div class="math-container">\n'
        + '        <div class="math-page-toc-heading">\n'
        + '          <p class="math-eyebrow">PAGE CONTENTS</p>\n'
        + '          <strong id="math-page-toc-title">이 페이지에서 확인할 내용</strong>\n'
        + "        </div>\n"
        + '        <ol class="math-page-toc-list">\n'
        + "\n".join(items)
        + "\n        </ol>\n"
        + "      </div>\n"
        + "    </nav>\n"
        + "    "
        + TOC_END
        + "\n\n    "
    )


def render_page(original: str, kind: str) -> tuple[str, int]:
    source = TOC_BLOCK_RE.sub("", original, count=1)
    source = GRADE_SOURCE_ALERT_GAP_RE.sub(r"\1\n    ", source, count=1)
    source = GENERATED_H2_ID_RE.sub(r"\1", source)
    targets = select_targets(source, kind)
    if len(targets) < 2:
        raise ValueError(f"Only {len(targets)} usable headings found")

    source, links = add_target_ids(source, targets)
    insertion_point = toc_insertion_point(source)
    if insertion_point is None:
        raise ValueError("TOC insertion point not found")
    tail = source[insertion_point:].lstrip()
    source = source[:insertion_point] + toc_markup(links) + tail
    return source, len(links)


def validate_page(source: str) -> list[str]:
    errors: list[str] = []
    if source.count(TOC_START) != 1 or source.count(TOC_END) != 1:
        errors.append("TOC marker count is not exactly one")

    toc_match = TOC_BLOCK_RE.search(source)
    if not toc_match:
        errors.append("TOC block missing")
        return errors

    hrefs = re.findall(r'href=["\']#([^"\']+)["\']', toc_match.group(0), re.IGNORECASE)
    if len(hrefs) < 2:
        errors.append("TOC contains fewer than two links")

    all_ids = [match.group("id") for match in ANY_ID_RE.finditer(source)]
    if len(all_ids) != len(set(all_ids)):
        errors.append("Duplicate id found")
    for target in hrefs:
        if all_ids.count(target) != 1:
            errors.append(f"Anchor target count for {target!r} is {all_ids.count(target)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="Write the generated TOCs to disk"
    )
    parser.add_argument(
        "--check", action="store_true", help="Fail if any target page is not current"
    )
    parser.add_argument(
        "--crlf",
        action="store_true",
        help="Write CRLF line endings (useful in this Windows checkout)",
    )
    args = parser.parse_args()

    pages = academy_pages()
    changed = 0
    category_count = 0
    detail_count = 0
    link_counts: list[int] = []
    failures: list[str] = []

    for path in pages:
        kind = page_kind(path)
        category_count += kind == "category"
        detail_count += kind == "detail"
        original_bytes = path.read_bytes()
        original = original_bytes.decode("utf-8")
        original_newline = "\r\n" if "\r\n" in original else "\n"
        canonical_original = original.replace("\r\n", "\n").replace("\r", "\n")
        try:
            rendered, link_count = render_page(canonical_original, kind)
        except Exception as exc:  # report all page-specific failures together
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        link_counts.append(link_count)
        validation_errors = validate_page(rendered)
        if validation_errors:
            failures.append(
                f"{path.relative_to(ROOT)}: " + "; ".join(validation_errors)
            )
            continue
        target_newline = "\r\n" if args.crlf else original_newline
        serialized = rendered.replace("\n", target_newline)
        if serialized != original:
            changed += 1
            if args.write:
                path.write_bytes(serialized.encode("utf-8"))

    print(f"pages={len(pages)} categories={category_count} details={detail_count}")
    if link_counts:
        print(
            "toc_links="
            f"min:{min(link_counts)} max:{max(link_counts)} "
            f"avg:{sum(link_counts) / len(link_counts):.2f}"
        )
    print(f"changed={changed} mode={'write' if args.write else 'dry-run'}")

    if failures:
        print(f"failures={len(failures)}", file=sys.stderr)
        for failure in failures[:50]:
            print(failure, file=sys.stderr)
        return 1
    if args.check and changed:
        print("Target pages are not up to date. Run with --write.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
