import csv
import os
from datetime import date
from pathlib import Path

ROOT = Path.cwd()
CSV_PATH = Path(os.environ["WAWA_TOPIC_CSV"])
SITE_URL = "https://wawa-center.kr"


def normalize(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/").replace(" ", "-")


with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
    rows = list(csv.reader(file))[1:]

urls = [
    f"{SITE_URL}/{normalize(row[6])}/{normalize(row[7])}/"
    for row in rows
    if len(row) >= 8 and row[6].strip() and row[7].strip()
]

sitemap = ROOT / "sitemap.xml"
text = sitemap.read_text(encoding="utf-8")
new_urls = [url for url in urls if f"<loc>{url}</loc>" not in text]
entries = "".join(
    f"  <url>\n    <loc>{url}</loc>\n    <lastmod>{date.today().isoformat()}</lastmod>\n  </url>\n"
    for url in new_urls
)
if entries:
    text = text.replace("</urlset>", entries + "</urlset>")
    sitemap.write_text(text, encoding="utf-8")

print(f"urls_added={len(new_urls)}")
