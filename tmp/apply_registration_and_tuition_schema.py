import csv
import html
import json
import os
import re
from pathlib import Path


ROOT = Path.cwd()
CSV_PATH = Path(os.environ["EDUCATIONAL_ORGANIZATION_CSV"])
ORG_RE = re.compile(
    r'(?P<prefix><script\s+type=["\']application/ld\+json["\']\s+data-parent-review-jsonld>)'
    r'(?P<json>.*?)'
    r'(?P<suffix></script>)',
    flags=re.S,
)


def normalize_parent(value: str) -> str:
    parts = value.strip().replace("\\", "/").strip("/").split("/")
    return "/".join(re.sub(r"\s+", "-", part.strip()) for part in parts if part.strip())


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def registration_number(text: str) -> str:
    lines = re.findall(
        r'<p\s+class=["\']wawa-register-line["\']>\s*<strong>(.*?)</strong>\s*:\s*(.*?)</p>',
        text,
        flags=re.S | re.I,
    )
    return clean_text(lines[1][1]) if len(lines) >= 2 else ""


def fee_tables(text: str) -> list[tuple[str, list[list[str]]]]:
    tables = []
    blocks = re.findall(
        r'<section\s+class=["\']wawa-fee-block["\']>\s*<h3>(.*?)</h3>.*?'
        r'<table\s+class=["\']wawa-fee-table["\'][^>]*>(.*?)</table>.*?</section>',
        text,
        flags=re.S | re.I,
    )
    for title, table_html in blocks:
        rows = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S | re.I):
            cells = [
                clean_text(cell)
                for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, flags=re.S | re.I)
            ]
            if cells:
                rows.append(cells)
        if len(rows) >= 2 and len(rows[0]) >= 2:
            tables.append((clean_text(title), rows))
    return tables


def offer_catalog(org_id: str, tables: list[tuple[str, list[list[str]]]]) -> dict | None:
    categories = []
    for group_index, (title, rows) in enumerate(tables, start=1):
        headers = rows[0]
        offers = []
        for row_index, row in enumerate(rows[1:], start=1):
            if len(row) != len(headers):
                continue
            for column_index in range(1, len(headers)):
                price = re.sub(r"[^0-9]", "", row[column_index])
                if not price:
                    continue
                offers.append(
                    {
                        "@type": "Offer",
                        "@id": f"{org_id}#tuition-{group_index}-{row_index}-{column_index}",
                        "name": f"{title} · {headers[column_index]} · {row[0]}",
                        "description": f"{title}. 화면에 표시된 교습비 기준입니다.",
                        "price": price,
                        "priceCurrency": "KRW",
                    }
                )
        if offers:
            categories.append(
                {
                    "@type": "OfferCatalog",
                    "@id": f"{org_id}#tuition-category-{group_index}",
                    "name": title,
                    "itemListElement": offers,
                }
            )
    if not categories:
        return None
    return {
        "@type": "OfferCatalog",
        "@id": f"{org_id}#tuition",
        "name": "와와학습코칭센터 교습비 안내",
        "itemListElement": categories,
    }


def update_page(page_file: Path) -> str:
    original = page_file.read_text(encoding="utf-8")
    match = ORG_RE.search(original)
    if not match:
        return "skipped"
    try:
        organization = json.loads(match.group("json"))
    except json.JSONDecodeError:
        return "skipped"

    number = registration_number(original)
    catalog = offer_catalog(organization.get("@id", ""), fee_tables(original))
    if not number or not catalog:
        return "skipped"

    organization["identifier"] = {
        "@type": "PropertyValue",
        "propertyID": "교육지원청 등록번호",
        "value": number,
    }
    organization["hasOfferCatalog"] = catalog
    replacement = match.group("prefix") + json.dumps(organization, ensure_ascii=False) + match.group("suffix")
    updated = original[: match.start()] + replacement + original[match.end() :]
    if updated == original:
        return "unchanged"
    page_file.write_text(updated, encoding="utf-8")
    return "updated"


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))[1:]
    counts = {"updated": 0, "unchanged": 0, "skipped": 0}
    for row in rows:
        parent_dir = ROOT / normalize_parent(row[0])
        for page_file in sorted(parent_dir.rglob("index.html")):
            counts[update_page(page_file)] += 1
    for key, value in counts.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
