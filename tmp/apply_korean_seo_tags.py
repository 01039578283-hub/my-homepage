import html
import re
from pathlib import Path

ROOT = Path.cwd()
SITE_NAME = "와와학습코칭센터 영어수학 전문학원"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def page_title(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    title = clean_text(match.group(1)).split("|", 1)[0].strip()
    return title or fallback


def breadcrumb_names(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"<li>\s*(?:<a [^>]*>|<span [^>]*>)(.*?)(?:</a>|</span>)\s*</li>", text, flags=re.S):
        name = clean_text(match.group(1))
        if name:
            names.append(name)
    return names


def parent_local_name(path: Path) -> str:
    parent_index = path.parent.parent / "index.html"
    if not parent_index.exists():
        return ""
    text = parent_index.read_text(encoding="utf-8", errors="ignore")
    names = breadcrumb_names(text)
    return names[-1] if names else page_title(text, path.parent.parent.name)


def seo_description(path: Path, text: str, title: str) -> str:
    names = breadcrumb_names(text)
    try:
        parts = path.relative_to(ROOT / "center").parts
    except ValueError:
        parts = ()

    if len(parts) >= 5:
        local = parent_local_name(path)
        local_prefix = f"{local} 와와학습코칭센터의 " if local and local not in title else ""
        return (
            f"{title} 안내입니다. {local_prefix}초등, 중등, 고등 영어·수학 학습코칭과 "
            "수업 방향, 센터 위치 정보를 확인해보세요."
        )

    if len(parts) == 4:
        area = names[-1] if names else title
        return (
            f"{title} 안내입니다. {area} 지역의 초등, 중등, 고등 영어·수학 학습코칭과 "
            "수업 안내, 센터 위치 정보를 확인해보세요."
        )

    if len(parts) == 3:
        area = names[-1] if names else title
        return f"{area} 지역 와와학습코칭센터 안내입니다. 동네별 학원 정보와 관련 학습 페이지를 확인해보세요."

    if len(parts) == 2:
        area = names[-1] if names else title
        return f"{area} 와와학습코칭센터 안내입니다. 지역별 센터와 동네별 영어·수학 학원 정보를 확인해보세요."

    if len(parts) == 1:
        area = names[-1] if names else title
        return f"{area} 지역 와와학습코칭센터 안내입니다. 가까운 센터와 동네별 학습코칭 정보를 확인해보세요."

    return f"{title} 안내입니다. 와와학습코칭센터의 영어·수학 학습코칭과 센터 정보를 확인해보세요."


def seo_block(title: str, description: str) -> str:
    full_title = f"{title} | {SITE_NAME}"
    return f"""  <meta name="description" content="{html.escape(description)}">
  <meta name="robots" content="index, follow">
  <meta property="og:site_name" content="{html.escape(SITE_NAME)}">
  <meta property="og:title" content="{html.escape(full_title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
"""


def remove_existing_seo(text: str) -> str:
    patterns = [
        r'  <meta\s+name="description"\s+content="[^"]*">\n',
        r'  <meta\s+name="robots"\s+content="[^"]*">\n',
        r'  <meta\s+property="og:site_name"\s+content="[^"]*">\n',
        r'  <meta\s+property="og:title"\s+content="[^"]*">\n',
        r'  <meta\s+property="og:description"\s+content="[^"]*">\n',
        r'  <meta\s+property="og:type"\s+content="[^"]*">\n',
        r'  <meta\s+name="twitter:card"\s+content="[^"]*">\n',
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return text


def update_page(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = page_title(text, path.parent.name)
    description = seo_description(path, text, title)
    updated = remove_existing_seo(text)
    block = seo_block(title, description)
    if "</title>\n" in updated:
        updated = updated.replace("</title>\n", "</title>\n" + block, 1)
    elif "<meta name=\"viewport\"" in updated:
        updated = updated.replace("  <meta name=\"viewport\"", block + "  <meta name=\"viewport\"", 1)
    else:
        return False

    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main():
    pages = sorted((ROOT / "center").rglob("index.html"))
    updated = 0
    for page in pages:
        if update_page(page):
            updated += 1
    print(f"center_pages_checked={len(pages)}")
    print(f"seo_pages_updated={updated}")


if __name__ == "__main__":
    main()
