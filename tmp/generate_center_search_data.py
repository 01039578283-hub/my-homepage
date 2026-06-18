import html
import json
import re
from pathlib import Path

ROOT = Path.cwd()
CENTER_ROOT = ROOT / "center"
OUT = ROOT / "assets" / "center-search-data.js"

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

KIND_ORDER = {"region": 0, "district": 1, "local": 2}


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def page_title(page: Path, fallback: str) -> str:
    text = page.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    title = clean_text(match.group(1)).split("|", 1)[0].strip()
    return title or fallback


def main():
    items = []
    for page in sorted(CENTER_ROOT.rglob("index.html")):
        rel_dir = page.parent.relative_to(CENTER_ROOT)
        parts = rel_dir.parts
        if not parts:
            continue

        region_slug = parts[0]
        region_name = REGION_NAMES.get(region_slug, region_slug)
        title = page_title(page, parts[-1])
        if len(parts) == 1:
            kind = "region"
            display = region_name
            parent = "전국센터"
        elif len(parts) == 2:
            kind = "district"
            display = title.replace(" 센터", "")
            parent = region_name
        else:
            kind = "local"
            display = title
            district_page = CENTER_ROOT.joinpath(parts[0], parts[1], "index.html")
            district_title = page_title(district_page, parts[1]).replace(" 센터", "")
            parent = f"{region_name} / {district_title}"

        items.append(
            {
                "title": display,
                "region": region_slug,
                "regionName": region_name,
                "kind": kind,
                "parent": parent,
                "url": "center/" + "/".join(parts) + "/index.html",
                "search": f"{display} {region_name} {parent} {' '.join(parts)}",
            }
        )

    items.sort(key=lambda item: (REGION_NAMES.get(item["region"], item["region"]), KIND_ORDER[item["kind"]], item["title"]))
    OUT.write_text(
        "window.WAWA_CENTER_INDEX = "
        + json.dumps(items, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"items={len(items)}")
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
