import csv
import html
import json
import os
import re
from pathlib import Path


ROOT = Path.cwd()
CSV_PATH = Path(os.environ["EDUCATIONAL_ORGANIZATION_CSV"])
SITE_URL = "https://wawa-center.kr"
ARTICLE_RE = re.compile(
    r'\s*<script\s+type=["\']application/ld\+json["\']\s+data-article-jsonld>.*?</script>',
    flags=re.S,
)


def normalize_parent(value: str) -> str:
    parts = value.strip().replace("\\", "/").strip("/").split("/")
    return "/".join(re.sub(r"\s+", "-", part.strip()) for part in parts if part.strip())


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.S | re.I)
    return html.unescape(match.group(1)).strip() if match else ""


def page_data(text: str) -> dict[str, str]:
    title = clean_text(extract(r"<title>(.*?)</title>", text)).split("|", 1)[0].strip()
    description = clean_text(
        extract(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', text)
    )
    canonical = extract(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', text)
    image = extract(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', text)
    article_main = extract(
        r'<main\s+class=["\'][^"\']*\barticle-main\b[^"\']*["\'][^>]*>(.*?)</main>', text
    )
    h1 = clean_text(extract(r"<h1\b[^>]*>(.*?)</h1>", text))
    return {
        "title": title,
        "description": description,
        "canonical": canonical,
        "image": image,
        "article_text": clean_text(article_main),
        "h1": h1,
    }


def existing_schema(text: str, schema_type: str) -> dict | None:
    for raw in re.findall(
        r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, flags=re.S | re.I
    ):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == schema_type:
            return data
    return None


def article_schema(data: dict[str, str], organization: dict, service: dict | None) -> dict:
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "@id": f'{data["canonical"]}#article',
        "headline": data["title"],
        "description": data["description"],
        "image": data["image"],
        "inLanguage": "ko-KR",
        "author": {"@id": organization["@id"], "name": organization["name"]},
        "publisher": {
            "@type": "Organization",
            "name": "와와학습코칭센터",
            "url": SITE_URL,
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": data["canonical"]},
    }
    if service:
        article["about"] = {"@id": service["@id"], "name": service["name"]}
    return article


def update_page(page_file: Path) -> str:
    original = page_file.read_text(encoding="utf-8")
    cleaned = ARTICLE_RE.sub("", original)
    data = page_data(cleaned)
    organization = existing_schema(cleaned, "EducationalOrganization")
    service = existing_schema(cleaned, "Service")
    required = (data["title"], data["description"], data["canonical"], data["image"], data["h1"], organization)
    if not all(required) or len(data["article_text"]) < 300:
        return "skipped"

    schema = article_schema(data, organization, service)
    script = (
        f'  <script type="application/ld+json" data-article-jsonld>'
        f'{json.dumps(schema, ensure_ascii=False)}</script>\n'
    )
    updated = cleaned.replace("</head>", script + "</head>", 1)
    if updated == original:
        return "unchanged"
    page_file.write_text(updated, encoding="utf-8")
    return "updated"


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))[1:]
    counts = {"updated": 0, "skipped": 0, "unchanged": 0}
    skipped = []
    for row in rows:
        parent_dir = ROOT / normalize_parent(row[0])
        for page_file in sorted(parent_dir.rglob("index.html")):
            result = update_page(page_file)
            counts[result] += 1
            if result == "skipped":
                skipped.append(page_file.relative_to(ROOT).as_posix())
    print(f"updated={counts['updated']}")
    print(f"skipped={counts['skipped']}")
    print(f"unchanged={counts['unchanged']}")
    for item in skipped:
        print(f"skip={item}")


if __name__ == "__main__":
    main()
