import html
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path.cwd()
XLSX = ROOT / "tmp" / "districts.xlsx"
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

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

FAB = """  <div class="wawa-fixed-fab-container">
    <a href="tel:010-3957-8283" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a>
    <a href="https://blogsms.net/01039578283" target="_blank" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a>
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a>
  </div>"""


def read_rows(path: Path):
    with zipfile.ZipFile(path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", NS):
                shared.append("".join((t.text or "") for t in si.findall(".//a:t", NS)))

        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(".//a:sheetData/a:row", NS):
            values = {}
            for cell in row.findall("a:c", NS):
                ref = cell.attrib.get("r", "")
                match = re.match(r"[A-Z]+", ref)
                if not match:
                    continue
                col = match.group(0)
                value_node = cell.find("a:v", NS)
                value = ""
                if value_node is not None:
                    value = value_node.text or ""
                    if cell.attrib.get("t") == "s":
                        value = shared[int(value)]
                values[col] = value.strip()
            rows.append(values)
        return rows


def load_records():
    records = []
    seen = set()
    for row in read_rows(XLSX):
        parent_name = row.get("A", "").strip()
        region_slug = row.get("B", "").strip()
        district_name = row.get("C", "").strip()
        district_slug = row.get("D", "").strip()

        if not region_slug or not district_slug:
            continue
        if "지역" in parent_name or "지역" in region_slug or "구" in district_slug and district_slug.endswith("영어"):
            continue

        key = (region_slug, district_slug)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "parent_name": parent_name,
                "region_slug": region_slug,
                "district_name": district_name,
                "district_slug": district_slug,
            }
        )
    return records


def breadcrumb_json_ld(region_name: str, district_name: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "전국센터", "item": "../../../center.html"},
            {"@type": "ListItem", "position": 2, "name": region_name, "item": "../"},
            {"@type": "ListItem", "position": 3, "name": district_name},
        ],
    }
    return f'  <script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'


def breadcrumb_nav(region_name: str, district_name: str) -> str:
    return f"""  <nav class="breadcrumb-nav" aria-label="현재 위치">
    <ol class="breadcrumb-list">
      <li><a href="../../../center.html">전국센터</a></li>
      <li><a href="../">{html.escape(region_name)}</a></li>
      <li><span aria-current="page">{html.escape(district_name)}</span></li>
    </ol>
  </nav>"""


def preserved_child_section(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(
        r'    <section class="center-section bulk-child-section">.*?    </section>\n',
        text,
        flags=re.S,
    )
    return match.group(0) if match else ""


def district_page(record, child_section: str = ""):
    region_name = REGION_NAMES.get(record["region_slug"], record["parent_name"])
    district_name = record["district_name"]
    slug_label = record["district_slug"].upper()
    title = f"{district_name} 센터 | {SITE_NAME}"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{SITE_DESCRIPTION}">
  <meta name="application-name" content="{SITE_NAME}">
  <meta name="tagline" content="{SITE_DESCRIPTION}">
  <link rel="icon" type="image/png" href="../../../assets/favicon.png">
  <link rel="apple-touch-icon" href="../../../assets/favicon.png">
  <link rel="stylesheet" href="../../../assets/fab.css">
  <link rel="stylesheet" href="../../../assets/center.css">
  <link rel="stylesheet" href="../../../assets/header.css">
{breadcrumb_json_ld(region_name, district_name)}
</head>
<body>
  <header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="logo" href="../../../"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a>
      <div class="nav-links" aria-label="페이지 이동">
        <a href="../../../">홈</a>
        <a href="../../../overview.html">학원소개</a>
        <a class="active" href="../../../center.html">전국센터</a>
      </div>
    </nav>
  </header>
{breadcrumb_nav(region_name, district_name)}
  <main class="center-main">
    <section class="center-hero">
      <p class="center-eyebrow">{html.escape(slug_label)} CENTER</p>
      <h1>{html.escape(district_name)} 와와학습코칭센터 영어수학 전문학원</h1>
      <p>{html.escape(region_name)} {html.escape(district_name)} 지역의 동네별 학원 소개 페이지를 연결하기 위한 상위 페이지입니다.</p>
    </section>
    <section class="center-section">
      <div class="region-panel">
        <div class="region-info-card">
          <h2>{html.escape(district_name)} 지역 안내</h2>
          <p>추후 {html.escape(district_name)} 하위 동네별 상세 페이지와 고등, 중등, 초등 영어수학 학원 페이지를 이 아래에 확장할 수 있습니다.</p>
        </div>
        <div class="region-info-card">
          <h2>상담 신청</h2>
          <p>가까운 센터와 학생에게 맞는 코칭 방향은 상담을 통해 안내드립니다.</p>
          <div class="region-actions">
            <a class="center-button" href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform">상담 신청하기</a>
            <a class="center-button secondary" href="../">{html.escape(region_name)} 센터로 돌아가기</a>
          </div>
        </div>
      </div>
    </section>
{child_section}  </main>
{FAB}
</body>
</html>
"""


def update_parent(region_slug, items):
    parent = ROOT / "center" / region_slug / "index.html"
    if not parent.exists():
        return False

    region_name = REGION_NAMES.get(region_slug, items[0]["parent_name"])
    cards = []
    for item in items:
        cards.append(
            f'        <a class="district-card" href="{html.escape(item["district_slug"])}/"><strong>{html.escape(item["district_name"])}</strong><span>센터 보기</span></a>'
        )

    section = f"""    <section class="center-section district-list-section">
      <div class="center-section-head">
        <h2>{html.escape(region_name)} 세부 지역</h2>
        <p>원하는 구·시를 선택하면 해당 지역 상세 페이지로 이동합니다.</p>
      </div>
      <div class="district-grid">
{chr(10).join(cards)}
      </div>
    </section>
"""

    text = parent.read_text(encoding="utf-8")
    if '<section class="center-section district-list-section">' in text:
        text = re.sub(
            r'    <section class="center-section district-list-section">.*?    </section>\n',
            section,
            text,
            flags=re.S,
        )
    else:
        text = text.replace("  </main>", section + "  </main>")
    parent.write_text(text, encoding="utf-8")
    return True


def main():
    records = load_records()
    by_region = defaultdict(list)
    for record in records:
        by_region[record["region_slug"]].append(record)

    for items in by_region.values():
        items.sort(key=lambda row: row["district_name"])

    created = 0
    for record in records:
        path = ROOT / "center" / record["region_slug"] / record["district_slug"] / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(district_page(record, preserved_child_section(path)), encoding="utf-8")
        created += 1

    updated = 0
    for region_slug, items in by_region.items():
        if update_parent(region_slug, items):
            updated += 1

    print(f"records={len(records)}")
    print(f"district_pages_written={created}")
    print(f"parent_pages_updated={updated}")


if __name__ == "__main__":
    main()
