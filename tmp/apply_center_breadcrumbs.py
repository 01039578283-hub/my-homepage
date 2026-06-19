import html
import json
import os
import re
from pathlib import Path

ROOT = Path.cwd()
CENTER_ROOT = ROOT / "center"
CENTER_PAGE = ROOT / "center" / "index.html"

REGION_NAMES = {
    "seoul": "서울",
    "gyeonggi": "경기",
    "incheon": "인천",
    "daejeon": "대전",
    "chungcheong": "충청",
    "daegu": "대구",
    "ulsan": "울산",
    "busan": "부산",
    "gyeongsang": "경상",
    "gwangju": "광주",
    "jeolla": "전라",
    "gangwon": "강원",
    "jeju": "제주",
}


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def rel_href(from_dir: Path, target: Path) -> str:
    return os.path.relpath(target, start=from_dir).replace("\\", "/")


def page_title(page_file: Path, fallback: str) -> str:
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    title = clean_text(match.group(1)).split("|", 1)[0].strip()
    title = re.sub(r"\s*센터\s*$", "", title).strip()
    return title or fallback


def place_name(page_file: Path, fallback: str) -> str:
    title = page_title(page_file, fallback)
    title = re.sub(r"\[[^\]]+\]", " ", title)
    tokens = [token.strip(" ,.|-") for token in title.split()]
    for token in tokens:
        if token.endswith(("동", "읍", "면", "리", "가", "구")):
            return token
    return tokens[0] if tokens else fallback


def breadcrumb_for(page_file: Path):
    page_dir = page_file.parent

    if page_file == CENTER_PAGE:
        return [{"name": "전국센터", "target": None}]

    try:
        rel_parts = page_dir.relative_to(CENTER_ROOT).parts
    except ValueError:
        return []

    if not rel_parts:
        return [{"name": "전국센터", "target": None}]

    items = [{"name": "전국센터", "target": CENTER_PAGE}]

    for index, part in enumerate(rel_parts):
        current = index == len(rel_parts) - 1
        item_file = CENTER_ROOT.joinpath(*rel_parts[: index + 1], "index.html")
        if index == 0:
            name = REGION_NAMES.get(part, part)
        elif current:
            name = place_name(page_file, part)
        else:
            name = place_name(item_file, part)
        items.append({"name": name, "target": None if current else item_file})
    return items


def breadcrumb_nav(page_file: Path, items) -> str:
    page_dir = page_file.parent
    lines = ['  <nav class="breadcrumb-nav" aria-label="현재 위치">', '    <ol class="breadcrumb-list">']
    for item in items[:-1]:
        href = rel_href(page_dir, item["target"])
        lines.append(f'      <li><a href="{html.escape(href)}">{html.escape(item["name"])}</a></li>')
    lines.append(f'      <li><span aria-current="page">{html.escape(items[-1]["name"])}</span></li>')
    lines.extend(["    </ol>", "  </nav>"])
    return "\n".join(lines)


def breadcrumb_json_ld(page_file: Path, items) -> str:
    page_dir = page_file.parent
    item_list = []
    for position, item in enumerate(items, start=1):
        data = {
            "@type": "ListItem",
            "position": position,
            "name": item["name"],
        }
        if item["target"] is not None:
            data["item"] = rel_href(page_dir, item["target"])
        item_list.append(data)
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": item_list,
    }
    return f'  <script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'


def update_page(page_file: Path) -> bool:
    items = breadcrumb_for(page_file)
    if not items:
        return False

    text = page_file.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(
        r'\s*<script type="application/ld\+json">[^<]*"BreadcrumbList"[^<]*</script>\s*',
        "\n",
        text,
        flags=re.S,
    )
    text = re.sub(
        r'\s*<nav class="breadcrumb-nav" aria-label="현재 위치">.*?</nav>\s*',
        "\n",
        text,
        flags=re.S,
    )

    json_ld = breadcrumb_json_ld(page_file, items)
    text = text.replace("</head>", f"{json_ld}\n</head>", 1)

    nav = breadcrumb_nav(page_file, items)
    text = text.replace("</header>", f"</header>\n{nav}", 1)

    page_file.write_text(text, encoding="utf-8")
    return True


def main():
    pages = [CENTER_PAGE]
    pages.extend(sorted(CENTER_ROOT.rglob("index.html")))
    updated = sum(1 for page in pages if page.exists() and update_page(page))
    print(f"breadcrumbs_updated={updated}")


if __name__ == "__main__":
    main()
