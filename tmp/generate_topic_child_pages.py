import csv
import hashlib
import html
import json
import os
import random
import re
from pathlib import Path

ROOT = Path.cwd()
CSV_PATH = Path(r"C:\Users\얼짱김종범\Desktop\홈페이지 새로할거 자료\대량 등록할 파일.csv")
REVIEWS_PATH = ROOT / "tmp" / "parent_reviews.json"
FAQS_PATH = ROOT / "tmp" / "parent_faqs.json"
SITE_URL = "https://wawa-center.kr"
SITE_NAME = "와와학습코칭센터 영어수학 전문학원"
SITE_DESCRIPTION = "초등, 중등, 고등 영어·수학 학습코칭을 안내하는 와와학습코칭센터 문의 홈페이지입니다."

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


def read_rows():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))[1:]


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def load_parent_reviews():
    if not REVIEWS_PATH.exists():
        return []
    return json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))


def load_parent_faqs():
    if not FAQS_PATH.exists():
        return []
    data = json.loads(FAQS_PATH.read_text(encoding="utf-8"))
    return [
        {"question": clean_text(item.get("question", "")), "answer": clean_text(item.get("answer", ""))}
        for item in data
        if clean_text(item.get("question", "")) and clean_text(item.get("answer", ""))
    ]


PARENT_REVIEWS = load_parent_reviews()
PARENT_FAQS = load_parent_faqs()


def page_url(page_dir: Path) -> str:
    rel = page_dir.relative_to(ROOT).as_posix().strip("/")
    return f"{SITE_URL}/{rel}/"


def select_parent_reviews(page_dir: Path):
    if len(PARENT_REVIEWS) < 6:
        return []
    rel = page_dir.relative_to(ROOT).as_posix()
    seed = int(hashlib.sha256(rel.encode("utf-8")).hexdigest(), 16)
    return random.Random(seed).sample(PARENT_REVIEWS, 6)


def select_parent_faqs(page_dir: Path):
    if len(PARENT_FAQS) < 4:
        return []
    rel = page_dir.relative_to(ROOT).as_posix()
    seed = int(hashlib.sha256((rel + "::faq").encode("utf-8")).hexdigest(), 16)
    return random.Random(seed).sample(PARENT_FAQS, 4)


def parent_faq_markup(title: str, faqs) -> str:
    if not faqs:
        return ""
    items = []
    for index, item in enumerate(faqs):
        open_attr = " open" if index == 0 else ""
        items.append(
            f'''    <details class="parent-faq-item"{open_attr}>
      <summary><span class="parent-faq-q">Q</span>{html.escape(item["question"])}</summary>
      <p class="parent-faq-answer">{html.escape(item["answer"])}</p>
    </details>'''
        )
    return f'''<section class="parent-faq-section" aria-labelledby="parent-faq-title">
  <div class="parent-faq-head">
    <p class="parent-faq-eyebrow">PARENT FAQ</p>
    <h2 id="parent-faq-title">학부모 FAQ</h2>
    <p>{html.escape(title)} 상담 전 자주 확인하시는 질문과 답변입니다.</p>
  </div>
  <div class="parent-faq-list">
{chr(10).join(items)}
  </div>
</section>
'''


def parent_faq_json_ld(faqs) -> str:
    if not faqs:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in faqs
        ],
    }
    return f'  <script type="application/ld+json" data-parent-faq-jsonld>{json.dumps(data, ensure_ascii=False)}</script>\n'


def parent_review_markup(title: str, reviews) -> str:
    if not reviews:
        return ""
    cards = []
    for review in reviews:
        cards.append(
            f'''    <article class="parent-review-card">
      <p class="parent-review-text">{html.escape(review)}</p>
      <div class="parent-review-meta">
        <span class="parent-review-stars" aria-label="5점 만점 중 5점">★★★★★</span>
        <span class="parent-review-name">학부모 후기</span>
      </div>
    </article>'''
        )
    return f'''<section class="parent-review-section" aria-labelledby="parent-review-title">
  <div class="parent-review-head">
    <p class="parent-review-eyebrow">REAL PARENT REVIEWS</p>
    <h2 id="parent-review-title">수강생 학부모 후기</h2>
    <p>{html.escape(title)}을 확인하신 학부모님들이 남겨주신 실제 학습 후기입니다.</p>
  </div>
  <div class="parent-review-grid">
{chr(10).join(cards)}
  </div>
</section>
'''


def parent_review_json_ld(title: str, url: str, reviews) -> str:
    if not reviews:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "name": title,
        "url": url,
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "5",
            "bestRating": "5",
            "ratingCount": "6",
            "reviewCount": "6",
        },
        "review": [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": "학부모"},
                "reviewBody": review,
                "reviewRating": {"@type": "Rating", "ratingValue": "5", "bestRating": "5"},
            }
            for review in reviews
        ],
    }
    return f'  <script type="application/ld+json" data-parent-review-jsonld>{json.dumps(data, ensure_ascii=False)}</script>\n'


def seo_description(title: str, crumbs) -> str:
    crumb_names = [item["name"] for item in crumbs if item.get("name") and item["name"] != "전국센터"]
    local_name = crumb_names[-2] if len(crumb_names) >= 2 else ""
    topic_name = clean_text(title)
    place_text = f"{local_name} 와와학습코칭센터의 " if local_name and local_name not in topic_name else ""
    return (
        f"{topic_name} 안내입니다. {place_text}초등, 중등, 고등 영어·수학 학습코칭과 "
        "수업 방향, 센터 위치 정보를 확인해보세요."
    )


def seo_meta_tags(title: str, description: str) -> str:
    page_title = f"{title} | {SITE_NAME}"
    return f"""  <meta name="description" content="{html.escape(description)}">
  <meta name="robots" content="index, follow">
  <meta property="og:title" content="{html.escape(page_title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
"""


def normalize_slug(value: str) -> str:
    value = (value or "").strip().replace("\\", "/").strip("/")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


def clean_index_href(href: str) -> str:
    if href == "index.html":
        return "./"
    if href.endswith("/index.html"):
        return href[: -len("index.html")]
    if href.endswith("index.html"):
        return href[: -len("index.html")] or "./"
    return href


def rel_href(from_dir: Path, target: Path) -> str:
    return clean_index_href(os.path.relpath(target, start=from_dir).replace("\\", "/"))


def root_rel(page_dir: Path) -> str:
    depth = len(page_dir.relative_to(ROOT).parts)
    return "/".join([".."] * depth) if depth else "."


def read_page_title(page_file: Path, fallback: str) -> str:
    if not page_file.exists():
        return fallback
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    title = clean_text(match.group(1)).split("|", 1)[0].strip()
    return title or fallback


def read_current_breadcrumb_name(page_file: Path, fallback: str) -> str:
    if not page_file.exists():
        return fallback
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r'<span aria-current="page">(.*?)</span>', text, flags=re.S)
    if matches:
        return clean_text(matches[-1]) or fallback
    return fallback


def hidden_image_markup(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = value.replace('style="display:none;"', 'class="bulk-hidden-image"')
    value = value.replace("style='display:none;'", "class='bulk-hidden-image'")
    if "bulk-hidden-image" not in value and value.lower().startswith("<img"):
        value = value.replace("<img", '<img class="bulk-hidden-image"', 1)
    return f"  {value}\n"


def asset_src(page_dir: Path, folder: str, filename: str) -> str:
    filename = (filename or "").strip()
    if not filename:
        return ""

    requested = Path(filename)
    if re.match(r"^https?://", filename):
        return filename

    stems = []
    if requested.stem:
        stems.append(re.sub(r"\s+", "-", requested.stem))
        if requested.stem not in stems:
            stems.append(requested.stem)

    suffixes = [requested.suffix] if requested.suffix else []
    suffixes.extend(suffix for suffix in (".jpg", ".jpeg", ".png", ".webp") if suffix not in suffixes)

    for stem in stems:
        for suffix in suffixes:
            candidate = ROOT / folder / f"{stem}{suffix}"
            if candidate.exists():
                return f"{root_rel(page_dir)}/{folder}/{candidate.name}"

    return f"{root_rel(page_dir)}/{folder}/{filename}"


def image_block(label: str, src: str, alt: str) -> str:
    if not src:
        return ""
    return f"""  <section class="bulk-image-section">
    <h2>{html.escape(label)}</h2>
    <img class="bulk-page-image" src="{html.escape(src)}" alt="{html.escape(alt)}">
  </section>
"""


def breadcrumb_items(page_dir: Path, parent_dir: Path, title: str):
    items = [{"name": "전국센터", "url": rel_href(page_dir, ROOT / "center.html")}]
    try:
        parts = parent_dir.relative_to(ROOT / "center").parts
    except ValueError:
        parts = ()

    for index, part in enumerate(parts):
        item_dir = ROOT / "center" / Path(*parts[: index + 1])
        if index == 0:
            name = REGION_NAMES.get(part, part)
        else:
            name = read_current_breadcrumb_name(item_dir / "index.html", read_page_title(item_dir / "index.html", part))
        items.append({"name": name, "url": rel_href(page_dir, item_dir / "index.html")})

    items.append({"name": title, "url": ""})
    return items


def breadcrumb_markup(items) -> str:
    lines = ['  <nav class="breadcrumb-nav" aria-label="현재 위치">', '    <ol class="breadcrumb-list">']
    for item in items[:-1]:
        lines.append(f'      <li><a href="{html.escape(item["url"])}">{html.escape(item["name"])}</a></li>')
    lines.append(f'      <li><span aria-current="page">{html.escape(items[-1]["name"])}</span></li>')
    lines.extend(["    </ol>", "  </nav>", ""])
    return "\n".join(lines)


def breadcrumb_json_ld(items) -> str:
    item_list = []
    for position, item in enumerate(items, start=1):
        node = {"@type": "ListItem", "position": position, "name": item["name"]}
        if item.get("url"):
            node["item"] = item["url"]
        item_list.append(node)
    data = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": item_list}
    return f'  <script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>\n'


def fab_markup() -> str:
    return """  <div class="wawa-fixed-fab-container">
    <a href="tel:010-3957-8283" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a>
    <a href="https://blogsms.net/01039578283" target="_blank" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a>
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a>
  </div>"""


def create_child_page(row):
    title, hidden_image, class_image, map_image, article_html, center_html, parent_slug, slug = (row + [""] * 8)[:8]
    title = title.strip()
    parent_dir = ROOT / normalize_slug(parent_slug)
    slug = normalize_slug(slug)
    if not title or not parent_slug or not slug:
        return None

    page_dir = parent_dir / slug
    page_dir.mkdir(parents=True, exist_ok=True)

    class_src = asset_src(page_dir, "assets/centers/common", class_image)
    map_src = asset_src(page_dir, "assets/maps", map_image)
    crumbs = breadcrumb_items(page_dir, parent_dir, title)
    rr = root_rel(page_dir)
    description = seo_description(title, crumbs)
    reviews = select_parent_reviews(page_dir)
    faqs = select_parent_faqs(page_dir)

    content = "".join(
        [
            hidden_image_markup(hidden_image),
            image_block("수업 안내", class_src, f"{title} 수업 안내"),
            image_block("센터 지도", map_src, f"{title} 지도"),
            (article_html.strip() + "\n") if article_html.strip() else "",
            (center_html.strip() + "\n") if center_html.strip() else "",
        ]
    )

    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} | {SITE_NAME}</title>
{seo_meta_tags(title, description)}  <meta name="application-name" content="{SITE_NAME}">
  <meta name="tagline" content="{SITE_DESCRIPTION}">
  <link rel="icon" type="image/png" href="{rr}/assets/favicon.png">
  <link rel="apple-touch-icon" href="{rr}/assets/favicon.png">
  <link rel="stylesheet" href="{rr}/assets/fab.css">
  <link rel="stylesheet" href="{rr}/assets/center.css">
  <link rel="stylesheet" href="{rr}/assets/article.css">
  <link rel="stylesheet" href="{rr}/assets/local-center.css">
  <link rel="stylesheet" href="{rr}/assets/header.css">
{parent_faq_json_ld(faqs)}
{parent_review_json_ld(title, page_url(page_dir), reviews)}
{breadcrumb_json_ld(crumbs)}</head>
<body>
  <header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="logo" href="{rr}/"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a>
      <div class="nav-links" aria-label="페이지 이동">
        <a href="{rr}/">홈</a>
        <a href="{rr}/overview.html">학원소개</a>
        <a class="active" href="{rr}/center.html">전국센터</a>
      </div>
    </nav>
  </header>
{breadcrumb_markup(crumbs)}
{content}
{parent_faq_markup(title, faqs)}
{parent_review_markup(title, reviews)}
{fab_markup()}
</body>
</html>
"""
    (page_dir / "index.html").write_text(page, encoding="utf-8")
    return parent_dir, page_dir, title


def remove_topic_nav(text: str) -> str:
    return re.sub(
        r'\s*<section class="center-section local-topic-links-section">.*?</section>\s*',
        "\n",
        text,
        flags=re.S,
    )


def child_pages(parent_dir: Path):
    pages = []
    for child_dir in sorted([p for p in parent_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
        page_file = child_dir / "index.html"
        if not page_file.exists():
            continue
        pages.append({"dir": child_dir, "file": page_file, "title": read_page_title(page_file, child_dir.name)})
    return pages


def topic_nav(parent_dir: Path, page_dir: Path, include_parent: bool, current_file: Path | None = None) -> str:
    local_name = read_current_breadcrumb_name(parent_dir / "index.html", read_page_title(parent_dir / "index.html", parent_dir.name))
    local_main_label = local_name if local_name.endswith("학원") else f"{local_name} 학원"
    pages = child_pages(parent_dir)
    if not pages:
        return ""

    links = []
    if include_parent:
        links.append(
            f'        <a class="local-topic-button" href="{html.escape(rel_href(page_dir, parent_dir / "index.html"))}">'
            f'<span>센터 메인</span><strong>{html.escape(local_main_label)}</strong></a>'
        )

    for item in pages:
        active = " is-active" if current_file and item["file"].resolve() == current_file.resolve() else ""
        links.append(
            f'        <a class="local-topic-button{active}" href="{html.escape(rel_href(page_dir, item["file"]))}">'
            f'<span>관련 페이지</span><strong>{html.escape(item["title"])}</strong></a>'
        )

    return f"""  <section class="center-section local-topic-links-section">
    <div class="center-section-head">
      <h2>{html.escape(local_name)} 관련 학원 페이지</h2>
      <p>같은 지역의 주제별 학원 안내 페이지를 확인해보세요.</p>
    </div>
    <div class="local-topic-button-grid">
{chr(10).join(links)}
    </div>
  </section>
"""


def insert_before_fab(text: str, nav: str) -> str:
    text = remove_topic_nav(text)
    if not nav:
        return text
    marker = '  <div class="wawa-fixed-fab-container">'
    if marker in text:
        return text.replace(marker, nav + marker, 1)
    return text.replace("</body>", nav + "</body>", 1)


def refresh_nav_for_parent(parent_dir: Path):
    parent_file = parent_dir / "index.html"
    if not parent_file.exists():
        return 0

    changed = 0
    parent_text = parent_file.read_text(encoding="utf-8", errors="ignore")
    parent_nav = topic_nav(parent_dir, parent_dir, include_parent=False)
    parent_updated = insert_before_fab(parent_text, parent_nav)
    if parent_updated != parent_text:
        parent_file.write_text(parent_updated, encoding="utf-8")
        changed += 1

    for item in child_pages(parent_dir):
        text = item["file"].read_text(encoding="utf-8", errors="ignore")
        nav = topic_nav(parent_dir, item["dir"], include_parent=True, current_file=item["file"])
        updated = insert_before_fab(text, nav)
        if updated != text:
            item["file"].write_text(updated, encoding="utf-8")
            changed += 1

    return changed


def main():
    created = []
    parent_dirs = set()
    for row in read_rows():
        result = create_child_page(row)
        if result:
            created.append(result)
            parent_dirs.add(result[0])

    nav_updated = 0
    for parent_dir in sorted(parent_dirs):
        nav_updated += refresh_nav_for_parent(parent_dir)

    print(f"created_pages={len(created)}")
    print(f"parents_touched={len(parent_dirs)}")
    print(f"pages_with_nav_updated={nav_updated}")


if __name__ == "__main__":
    main()
