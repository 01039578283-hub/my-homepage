import html
import re
from pathlib import Path

ROOT = Path.cwd()
CENTER_ROOT = ROOT / "center"

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


def page_title(page_file: Path, fallback: str) -> str:
    if not page_file.exists():
        return fallback
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    title = clean_text(match.group(1)).split("|", 1)[0].strip()
    title = re.sub(r"\s*센터\s*$", "", title).strip()
    title = re.sub(r"\s*영어\s*수학\s*학원\s*$", "", title).strip()
    return title or fallback


def local_name(title: str) -> str:
    title = re.sub(r"\s*영어\s*수학\s*학원\s*$", "", title).strip()
    return title


def local_pills(local_names, limit=10):
    shown = local_names[:limit]
    if not shown:
        return '<span class="center-local-pill muted">하위 동네 준비 중</span>'

    pills = [
        f'<span class="center-local-pill">{html.escape(local_name(name))}</span>'
        for name in shown
    ]
    if len(local_names) > len(shown):
        pills.append(f'<span class="center-local-pill more">+{len(local_names) - len(shown)}</span>')
    return "".join(pills)


def district_cards(region_dir: Path, region_name: str):
    cards = []
    district_dirs = [p for p in region_dir.iterdir() if p.is_dir()]
    district_dirs.sort(key=lambda p: page_title(p / "index.html", p.name))

    for district_dir in district_dirs:
        district_file = district_dir / "index.html"
        if not district_file.exists():
            continue

        district_name = page_title(district_file, district_dir.name)
        local_dirs = [p for p in district_dir.iterdir() if p.is_dir()]
        local_dirs.sort(key=lambda p: page_title(p / "index.html", p.name))

        locals_ = []
        for local_dir in local_dirs:
            local_file = local_dir / "index.html"
            if local_file.exists():
                locals_.append(page_title(local_file, local_dir.name))

        cards.append(
            f'        <a class="center-result-card center-district-card" href="{html.escape(district_dir.name)}/index.html">'
            f'<span class="center-result-meta">지역 · {html.escape(region_name)}</span>'
            f'<strong>{html.escape(district_name)}</strong>'
            f'<div class="center-local-list">{local_pills(locals_)}</div>'
            f'<em>{html.escape(region_name)} 센터 보기</em></a>'
        )
    return cards


def update_region_page(region_dir: Path):
    region_file = region_dir / "index.html"
    if not region_file.exists():
        return False

    region_name = REGION_NAMES.get(region_dir.name, page_title(region_file, region_dir.name))
    cards = district_cards(region_dir, region_name)
    if not cards:
        return False

    section = f"""    <section class="center-section district-list-section">
      <div class="center-section-head">
        <h2>{html.escape(region_name)}</h2>
        <p>원하는 지역을 선택하면 해당 지역 상세 페이지로 이동합니다.</p>
      </div>
      <div class="center-search-results region-district-results">
{chr(10).join(cards)}
      </div>
    </section>
"""

    text = region_file.read_text(encoding="utf-8")
    if '<section class="center-section district-list-section">' not in text:
        return False

    text = re.sub(
        r'    <section class="center-section district-list-section">.*?    </section>\n',
        section,
        text,
        flags=re.S,
    )
    region_file.write_text(text, encoding="utf-8")
    return True


def main():
    updated = 0
    for region_dir in sorted([p for p in CENTER_ROOT.iterdir() if p.is_dir()]):
        if update_region_page(region_dir):
            updated += 1
    print(f"region_pages_updated={updated}")


if __name__ == "__main__":
    main()
