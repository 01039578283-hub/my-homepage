import csv
import hashlib
import html
import json
import os
import re
from pathlib import Path


ROOT = Path.cwd()
CSV_PATH = Path(os.environ["EDUCATIONAL_ORGANIZATION_CSV"])
SITE_URL = "https://wawa-center.kr"
ORG_RE = re.compile(
    r'(?P<indent>\s*)<script\s+type=["\']application/ld\+json["\']\s+data-parent-review-jsonld>'
    r'(?P<json>.*?)</script>',
    flags=re.S,
)
SERVICE_RE = re.compile(
    r'\s*<script\s+type=["\']application/ld\+json["\']\s+data-service-jsonld>.*?</script>',
    flags=re.S,
)


def normalize_parent(value: str) -> str:
    parts = value.strip().replace("\\", "/").strip("/").split("/")
    return "/".join(re.sub(r"\s+", "-", part.strip()) for part in parts if part.strip())


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def page_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S | re.I)
    return clean_text(match.group(1)).split("|", 1)[0].strip() if match else ""


def page_description(text: str) -> str:
    match = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        text,
        flags=re.S | re.I,
    )
    return clean_text(match.group(1)) if match else ""


def canonical_url(text: str, page_file: Path) -> str:
    match = re.search(
        r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']',
        text,
        flags=re.S | re.I,
    )
    if match:
        return html.unescape(match.group(1)).strip()
    return f"{SITE_URL}/{page_file.parent.relative_to(ROOT).as_posix().strip('/')}/"


def opening_hours(value: str) -> str:
    match = re.fullmatch(r"\s*(\d{1,2})시\s*-\s*(\d{1,2})시\s*", value or "")
    if not match:
        return value.strip()
    return f"{int(match.group(1)):02d}:00-{int(match.group(2)):02d}:00"


def organization_id(center_name: str, address: str) -> str:
    source = f"{center_name}|{address}".encode("utf-8")
    return f"{SITE_URL}/#educational-organization-{hashlib.sha256(source).hexdigest()[:16]}"


def organization_schema(row: dict[str, str]) -> dict:
    center_name = row["center_name"]
    address = row["address"]
    schema = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "@id": organization_id(center_name, address),
        "name": center_name,
        "url": row["homepage"],
        "telephone": row["phone"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": address,
            "addressCountry": "KR",
        },
        "openingHours": opening_hours(row["hours"]),
        "areaServed": {"@type": "Place", "name": row["area"]},
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": row["phone"],
            "contactType": "customer service",
            "availableLanguage": "ko",
        },
    }
    return schema


def service_schema(title: str, description: str, url: str, org: dict, area: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Service",
        "@id": f"{url}#service",
        "name": title,
        "serviceType": title,
        "description": description,
        "url": url,
        "inLanguage": "ko-KR",
        "provider": {"@id": org["@id"], "name": org["name"]},
        "areaServed": {"@type": "Place", "name": area},
    }


def update_page(page_file: Path, parent_dir: Path, row: dict[str, str]) -> bool:
    original = page_file.read_text(encoding="utf-8")
    cleaned = SERVICE_RE.sub("", original)
    match = ORG_RE.search(cleaned)
    if not match:
        return False

    try:
        existing = json.loads(match.group("json"))
    except json.JSONDecodeError:
        return False

    organization = organization_schema(row)
    for key in ("aggregateRating", "review"):
        if key in existing:
            organization[key] = existing[key]

    indent = match.group("indent")
    organization_tag = (
        f'{indent}<script type="application/ld+json" data-parent-review-jsonld>'
        f'{json.dumps(organization, ensure_ascii=False)}</script>'
    )

    replacement = organization_tag
    if page_file.parent != parent_dir:
        title = page_title(cleaned)
        url = canonical_url(cleaned, page_file)
        service = service_schema(title, page_description(cleaned), url, organization, row["area"])
        replacement += (
            f'\n{indent}<script type="application/ld+json" data-service-jsonld>'
            f'{json.dumps(service, ensure_ascii=False)}</script>'
        )

    updated = cleaned[: match.start()] + replacement + cleaned[match.end() :]
    if updated == original:
        return False
    page_file.write_text(updated, encoding="utf-8")
    return True


def read_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
        records = list(csv.reader(file))
    data = []
    for values in records[1:]:
        values = (values + [""] * 7)[:7]
        data.append(
            {
                "parent_slug": normalize_parent(values[0]),
                "center_name": values[1].strip(),
                "address": values[2].strip(),
                "phone": values[3].strip(),
                "hours": values[4].strip(),
                "area": values[5].strip(),
                "homepage": values[6].strip(),
            }
        )
    return data


def main() -> None:
    rows = read_rows()
    updated = 0
    missing_parents = []
    skipped_pages = []
    for row in rows:
        parent_dir = ROOT / row["parent_slug"]
        if not (parent_dir / "index.html").exists():
            missing_parents.append(row["parent_slug"])
            continue
        for page_file in sorted(parent_dir.rglob("index.html")):
            if update_page(page_file, parent_dir, row):
                updated += 1
            else:
                skipped_pages.append(page_file.relative_to(ROOT).as_posix())
    print(f"csv_rows={len(rows)}")
    print(f"pages_updated={updated}")
    print(f"missing_parents={len(missing_parents)}")
    print(f"pages_without_update={len(skipped_pages)}")


if __name__ == "__main__":
    main()
