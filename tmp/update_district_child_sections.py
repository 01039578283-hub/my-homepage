import html
import json
import os
import re
from pathlib import Path

ROOT = Path.cwd()
DATA_FILE = ROOT / "assets" / "center-search-data.js"


def load_data():
    text = DATA_FILE.read_text(encoding="utf-8")
    match = re.search(r"window\.WAWA_CENTER_INDEX\s*=\s*(.*);\s*$", text, flags=re.S)
    if not match:
        raise RuntimeError("center search data not found")
    return json.loads(match.group(1))


def local_name(title: str) -> str:
    return re.sub(r"\s*영어\s*수학\s*학원\s*$", "", title).strip()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def rel_href(from_file: Path, url: str) -> str:
    target = ROOT / url.replace("/", os.sep)
    return os.path.relpath(target, start=from_file.parent).replace("\\", "/")


def address_for(item) -> str:
    page_file = ROOT / item["url"].replace("/", os.sep)
    if not page_file.exists():
        return ""

    text = page_file.read_text(encoding="utf-8", errors="ignore")
    match = re.search(
        r'<span class="wawa-label">\s*주소\s*</span>\s*<p class="wawa-text[^"]*">(.*?)</p>',
        text,
        flags=re.S,
    )
    if match:
        return clean_text(match.group(1))

    match = re.search(r'"address"\s*:\s*"([^"]+)"', text)
    if match:
        return clean_text(match.group(1))

    return ""


def section_for(district, locals_, page_file: Path) -> str:
    cards = []
    for item in locals_:
        name = local_name(item["title"])
        address = address_for(item)
        card_title = f"{name} 와와학습코칭센터"
        card_text = address or f"{name} 와와학습코칭센터 정보를 확인해보세요."
        cards.append(
            f'        <a class="local-center-card" href="{html.escape(rel_href(page_file, item["url"]))}">'
            f'<span class="local-card-kicker">LOCAL CENTER</span>'
            f'<strong>{html.escape(card_title)}</strong>'
            f'<p>{html.escape(card_text)}</p>'
            f'<em>센터 안내 보기</em></a>'
        )

    return f"""    <section class="center-section bulk-child-section local-list-section">
      <div class="center-section-head">
        <h2>{html.escape(district["title"])} 학원</h2>
        <p>{html.escape(district["title"])}에서 확인할 수 있는 와와학습코칭센터 동네별 안내입니다.</p>
      </div>
      <div class="local-center-grid">
{chr(10).join(cards)}
      </div>
    </section>
"""


def main():
    data = load_data()
    districts = [item for item in data if item["kind"] == "district"]
    locals_ = [item for item in data if item["kind"] == "local"]
    updated = 0

    for district in districts:
        page_file = ROOT / district["url"].replace("/", os.sep)
        if not page_file.exists():
            continue
        prefix = district["url"].replace("index.html", "")
        children = [item for item in locals_ if item["url"].startswith(prefix)]
        if not children:
            continue

        text = page_file.read_text(encoding="utf-8")
        section = section_for(district, children, page_file)
        if '<section class="center-section bulk-child-section' in text:
            text = re.sub(
                r'    <section class="center-section bulk-child-section[^"]*">.*?    </section>\n',
                section,
                text,
                flags=re.S,
            )
        else:
            text = text.replace("  </main>", section + "  </main>")
        page_file.write_text(text, encoding="utf-8")
        updated += 1

    print(f"district_pages_updated={updated}")


if __name__ == "__main__":
    main()
