import html
import json
import re
from pathlib import Path

ROOT = Path.cwd()
SITE_NAME = "와와학습코칭센터 영어수학 전문학원"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def breadcrumb_names(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"<li>\s*(?:<a [^>]*>|<span [^>]*>)(.*?)(?:</a>|</span>)\s*</li>", text, flags=re.S):
        name = clean_text(match.group(1))
        if name:
            names.append(name)
    return names


def title_of(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    return clean_text(match.group(1)).split("|", 1)[0].strip() or fallback


def upsert_meta(text: str, tag_pattern: str, tag: str) -> str:
    if re.search(tag_pattern, text, flags=re.I):
        return re.sub(tag_pattern, tag + "\n", text, count=1, flags=re.I)
    return text.replace("</title>\n", "</title>\n" + tag + "\n", 1)


def set_main_page_seo(path: Path, title: str, description: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text
    full_title = title if "|" in title else f"{title} | {SITE_NAME}"
    text = upsert_meta(text, r'  <meta name="robots" content="[^"]*">\n?', '  <meta name="robots" content="index, follow">')
    text = upsert_meta(text, r'  <meta property="og:title" content="[^"]*">\n?', f'  <meta property="og:title" content="{html.escape(full_title)}">')
    text = upsert_meta(text, r'  <meta property="og:description" content="[^"]*">\n?', f'  <meta property="og:description" content="{html.escape(description)}">')
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def set_district_page_title(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    names = breadcrumb_names(text)
    if len(names) < 3:
        return False
    region = names[-2]
    district = names[-1]
    old_title = title_of(text, district)
    new_title = f"{region} {district} 센터"
    if old_title == new_title:
        return False

    description = f"{region} {district} 지역 와와학습코칭센터 안내입니다. 동네별 학원 정보와 관련 학습 페이지를 확인해보세요."
    full_title = f"{new_title} | {SITE_NAME}"
    original = text
    text = re.sub(r"<title>.*?</title>", f"<title>{html.escape(full_title)}</title>", text, count=1, flags=re.S)
    text = upsert_meta(text, r'  <meta name="description" content="[^"]*">\n?', f'  <meta name="description" content="{html.escape(description)}">')
    text = upsert_meta(text, r'  <meta property="og:title" content="[^"]*">\n?', f'  <meta property="og:title" content="{html.escape(full_title)}">')
    text = upsert_meta(text, r'  <meta property="og:description" content="[^"]*">\n?', f'  <meta property="og:description" content="{html.escape(description)}">')

    # Keep BreadcrumbList names unchanged; only page-level SEO title/description changes.
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main():
    main_pages = [
        (ROOT / "index.html", "와와학습코칭센터 영어수학 전문학원", "초등, 중등, 고등 영어·수학 학습코칭을 안내하는 와와학습코칭센터 문의 홈페이지입니다."),
        (ROOT / "overview" / "index.html", "학원소개 | 와와학습코칭센터 영어수학 전문학원", "와와학습코칭센터의 영어·수학 학습코칭 방향, 수업 특징, 학습 관리 방식을 확인해보세요."),
        (ROOT / "center" / "index.html", "전국센터 | 와와학습코칭센터 영어수학 전문학원", "전국 주요 지역의 와와학습코칭센터와 동네별 영어·수학 학원 정보를 확인해보세요."),
    ]
    main_updated = sum(set_main_page_seo(*item) for item in main_pages)

    district_pages = sorted((ROOT / "center").glob("*/*/index.html"))
    district_updated = 0
    for page in district_pages:
        if set_district_page_title(page):
            district_updated += 1

    print(f"main_pages_updated={main_updated}")
    print(f"district_pages_checked={len(district_pages)}")
    print(f"district_pages_updated={district_updated}")


if __name__ == "__main__":
    main()
