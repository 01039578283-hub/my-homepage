import html
import re
from pathlib import Path

ROOT = Path.cwd()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def page_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S | re.I)
    if not match:
        return ""
    return clean_text(match.group(1)).split("|", 1)[0].strip()


def seo_h1(title: str) -> str:
    if "와와학습코칭센터" in title or "와와학습코칭학원" in title:
        return f"{title} 학습 안내"
    return f"{title} 와와학습코칭센터 학습 안내"


def replace_first_h1(text: str, title: str) -> str:
    return re.sub(
        r"<h1(?P<attrs>[^>]*)>.*?</h1>",
        lambda m: f"<h1{m.group('attrs')}>{html.escape(seo_h1(title))}</h1>",
        text,
        count=1,
        flags=re.S | re.I,
    )


def replace_bulk_image_h2(text: str, title: str) -> str:
    labels = [f"{title} 수업 안내", f"{title} 센터 지도"]

    def replace_section(match: re.Match) -> str:
        index = replace_section.index
        replace_section.index += 1
        if index >= len(labels):
            return match.group(0)
        section = match.group(0)
        return re.sub(
            r"<h2(?P<attrs>[^>]*)>.*?</h2>",
            lambda h: f"<h2{h.group('attrs')}>{html.escape(labels[index])}</h2>",
            section,
            count=1,
            flags=re.S | re.I,
        )

    replace_section.index = 0
    return re.sub(
        r'<section\s+class=["\']bulk-image-section["\'][^>]*>.*?</section>',
        replace_section,
        text,
        count=2,
        flags=re.S | re.I,
    )


def replace_feature_h2(text: str, title: str) -> str:
    pattern = r'(<section\s+class=["\'][^"\']*\barticle-local-feature-section\b[^"\']*["\'][^>]*>.*?<h2(?P<attrs>[^>]*)>).*?(</h2>)'
    return re.sub(
        pattern,
        lambda m: f"{m.group(1)}{html.escape(title)} 핵심 포인트{m.group(3)}",
        text,
        count=1,
        flags=re.S | re.I,
    )


def update_page(page_file: Path) -> bool:
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    if "data-parent-review-jsonld" not in text:
        return False
    title = page_title(text)
    if not title:
        return False

    updated = replace_first_h1(text, title)
    updated = replace_bulk_image_h2(updated, title)
    updated = replace_feature_h2(updated, title)

    if updated != text:
        page_file.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    pages = sorted((ROOT / "center").rglob("index.html"))
    target_pages = 0
    updated_pages = 0
    for page_file in pages:
        text = page_file.read_text(encoding="utf-8", errors="ignore")
        if "data-parent-review-jsonld" in text:
            target_pages += 1
            if update_page(page_file):
                updated_pages += 1
    print(f"target_pages={target_pages}")
    print(f"updated_pages={updated_pages}")


if __name__ == "__main__":
    main()
