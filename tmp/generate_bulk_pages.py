import csv
import html
import json
import os
import re
from pathlib import Path

ROOT = Path.cwd()
CSV_PATH = ROOT / "tmp" / "bulk_pages.csv"

SITE_NAME = "와와학습코칭센터 영어수학 전문학원"
SITE_DESCRIPTION = "고등, 중등, 초등 학원입니다."

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


def cell(row: dict, index: int) -> str:
    values = list(row.values())
    return (values[index] if index < len(values) and values[index] else "").strip()


def rel_to_root(page_dir: Path) -> str:
    rel = page_dir.relative_to(ROOT)
    depth = len(rel.parts)
    return "/".join([".."] * depth) if depth else "."


def normalize_parent(parent: str) -> Path:
    parent = parent.strip().replace("\\", "/").strip("/")
    return ROOT / parent


def normalize_slug(slug: str) -> str:
    slug = slug.strip().strip("/").replace("\\", "/")
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def extract_place_name(title: str) -> str:
    plain = re.sub(r"\[[^\]]+\]", " ", strip_tags(title))
    tokens = [token.strip(" ,.|-") for token in plain.split()]
    for token in tokens:
        if token.endswith(("동", "읍", "면", "리", "가", "구")):
            return token
    return tokens[0] if tokens else plain


def local_card_name(title: str) -> str:
    title = strip_tags(title)
    title = re.sub(r"\s*영어\s*수학\s*학원\s*$", "", title).strip()
    return title or extract_place_name(title)


def page_title_name(page_dir: Path, fallback: str) -> str:
    page_file = page_dir / "index.html"
    if not page_file.exists():
        return fallback
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    title_match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not title_match:
        return fallback
    title = strip_tags(title_match.group(1))
    title = title.split("|", 1)[0].strip()
    title = re.sub(r"\s*센터\s*$", "", title).strip()
    return title or fallback


def page_place_name(page_dir: Path, fallback: str) -> str:
    return extract_place_name(page_title_name(page_dir, fallback))


def rel_href(from_dir: Path, target: Path) -> str:
    return os.path.relpath(target, start=from_dir).replace("\\", "/")


def breadcrumb_items(page_dir: Path, parent_dir: Path, current_title: str):
    try:
        center_rel = parent_dir.relative_to(ROOT / "center")
        parts = center_rel.parts
    except ValueError:
        parts = ()

    current_name = extract_place_name(current_title)

    items = [{"name": "전국센터", "url": rel_href(page_dir, ROOT / "center.html")}]
    for index, part in enumerate(parts):
        item_dir = ROOT / "center" / Path(*parts[: index + 1])
        if index == 0:
            name = REGION_NAMES.get(part, part)
        else:
            name = page_place_name(item_dir, part)
        items.append({"name": name, "url": rel_href(page_dir, item_dir / "index.html")})
    if current_name:
        items.append({"name": current_name, "url": ""})
    return items


def breadcrumb_markup(items) -> str:
    if not items:
        return ""
    lines = ['  <nav class="breadcrumb-nav" aria-label="현재 위치">', '    <ol class="breadcrumb-list">']
    for item in items[:-1]:
        lines.append(
            f'      <li><a href="{html.escape(item["url"])}">{html.escape(item["name"])}</a></li>'
        )
    lines.append(f'      <li><span aria-current="page">{html.escape(items[-1]["name"])}</span></li>')
    lines.extend(["    </ol>", "  </nav>", ""])
    return "\n".join(lines)


def breadcrumb_json_ld(items) -> str:
    if not items:
        return ""
    item_list = []
    for position, item in enumerate(items, start=1):
        data = {
            "@type": "ListItem",
            "position": position,
            "name": item["name"],
        }
        if item.get("url"):
            data["item"] = item["url"]
        item_list.append(data)
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": item_list,
    }
    return f'  <script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>\n'


def image_block(title: str, src: str, alt: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    return f"""    <section class="bulk-image-section">
      <h2>{html.escape(title)}</h2>
      <img class="bulk-page-image" src="{html.escape(src)}" alt="{html.escape(alt)}">
    </section>
"""


def asset_src(root_rel: str, folder: str, filename: str) -> str:
    filename = (filename or "").strip()
    if not filename:
        return ""
    stem = Path(filename).stem
    clean_stem = re.sub(r"\s+", "-", stem)
    stems = [clean_stem, stem] if clean_stem != stem else [stem]
    requested_suffix = Path(filename).suffix
    suffixes = [requested_suffix] if requested_suffix else []
    suffixes.extend(suffix for suffix in (".jpg", ".jpeg", ".png", ".webp") if suffix not in suffixes)

    for candidate_stem in stems:
        for suffix in suffixes:
            candidate = ROOT / folder / f"{candidate_stem}{suffix}"
            if candidate.exists():
                return f"{root_rel}/{folder}/{candidate.name}"
    return f"{root_rel}/{folder}/{filename}"


def create_page(row):
    title = cell(row, 0)
    hidden_image = cell(row, 1)
    class_image = cell(row, 2)
    map_image = cell(row, 3)
    article_html = cell(row, 4)
    center_html = cell(row, 5)
    parent_dir = normalize_parent(cell(row, 6))
    slug = normalize_slug(cell(row, 7))
    page_dir = parent_dir / slug
    page_dir.mkdir(parents=True, exist_ok=True)
    root_rel = rel_to_root(page_dir)
    crumbs = breadcrumb_items(page_dir, parent_dir, title)

    hidden_image = hidden_image.replace('style="display:none;"', 'class="bulk-hidden-image"')
    hidden_image = hidden_image.replace("style='display:none;'", "class='bulk-hidden-image'")

    class_src = asset_src(root_rel, "assets/centers/common", class_image)
    map_src = asset_src(root_rel, "assets/maps", map_image)

    content_parts = [
        f"    {hidden_image}\n" if hidden_image else "",
        image_block("수업 안내", class_src, f"{title} 수업 안내"),
        image_block("센터 지도", map_src, f"{title} 지도"),
        article_html + "\n" if article_html else "",
        center_html + "\n" if center_html else "",
    ]

    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} | {SITE_NAME}</title>
  <meta name="description" content="{SITE_DESCRIPTION}">
  <meta name="application-name" content="{SITE_NAME}">
  <meta name="tagline" content="{SITE_DESCRIPTION}">
  <link rel="icon" type="image/png" href="{root_rel}/assets/favicon.png">
  <link rel="apple-touch-icon" href="{root_rel}/assets/favicon.png">
  <link rel="stylesheet" href="{root_rel}/assets/fab.css">
  <link rel="stylesheet" href="{root_rel}/assets/center.css">
  <link rel="stylesheet" href="{root_rel}/assets/article.css">
  <link rel="stylesheet" href="{root_rel}/assets/local-center.css">
  <link rel="stylesheet" href="{root_rel}/assets/header.css">
{breadcrumb_json_ld(crumbs)}</head>
<body>
  <header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="logo" href="{root_rel}/index.html"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a>
      <div class="nav-links" aria-label="페이지 이동">
        <a href="{root_rel}/index.html">홈</a>
        <a href="{root_rel}/overview.html">학원소개</a>
        <a class="active" href="{root_rel}/center.html">전국센터</a>
      </div>
    </nav>
  </header>
{breadcrumb_markup(crumbs)}
{''.join(content_parts)}

  <div class="wawa-fixed-fab-container">
    <a href="tel:010-3957-8283" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a>
    <a href="https://blogsms.net/01039578283" target="_blank" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a>
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a>
  </div>
</body>
</html>
"""
    (page_dir / "index.html").write_text(page, encoding="utf-8")
    return parent_dir, page_dir, title, slug


def update_parent(parent_dir: Path, children):
    parent_file = parent_dir / "index.html"
    if not parent_file.exists():
        return False
    cards = []
    for _, _, title, slug in children:
        name = local_card_name(title)
        cards.append(
            f'        <a class="local-center-card" href="{html.escape(slug)}/index.html">'
            f'<span class="local-card-kicker">LOCAL CENTER</span>'
            f'<strong>{html.escape(name)}</strong>'
            f'<p>{html.escape(name)} 영어·수학 학원 정보를 확인해보세요.</p>'
            f'<em>센터 안내 보기</em></a>'
        )
    parent_name = page_title_name(parent_dir, parent_dir.name)
    section = f"""    <section class="center-section bulk-child-section local-list-section">
      <div class="center-section-head">
        <h2>{html.escape(parent_name)} 학원</h2>
        <p>{html.escape(parent_name)}에서 확인할 수 있는 와와학습코칭센터 동네별 안내입니다.</p>
      </div>
      <div class="local-center-grid">
{chr(10).join(cards)}
      </div>
    </section>
"""
    text = parent_file.read_text(encoding="utf-8")
    if '<section class="center-section bulk-child-section' in text:
        text = re.sub(
            r'    <section class="center-section bulk-child-section[^"]*">.*?    </section>\n',
            section,
            text,
            flags=re.S,
        )
    else:
        text = text.replace("  </main>", section + "  </main>")
    parent_file.write_text(text, encoding="utf-8")
    return True


def main():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    created = []
    for row in rows:
        if not cell(row, 6) or not cell(row, 7):
            continue
        created.append(create_page(row))

    by_parent = {}
    for item in created:
        by_parent.setdefault(item[0], []).append(item)
    updated = 0
    for parent, children in by_parent.items():
        if update_parent(parent, children):
            updated += 1

    print(f"created={len(created)}")
    print(f"parents_updated={updated}")
    for _, page_dir, title, _ in created:
        print(page_dir.relative_to(ROOT) / "index.html", title)


if __name__ == "__main__":
    main()
