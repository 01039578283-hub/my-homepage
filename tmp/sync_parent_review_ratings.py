import csv
import json
import os
import re
from pathlib import Path


ROOT = Path.cwd()
CSV_PATH = Path(os.environ["EDUCATIONAL_ORGANIZATION_CSV"])
REVIEW_JSON_RE = re.compile(
    r'(?P<prefix><script\s+type=["\']application/ld\+json["\']\s+data-parent-review-jsonld>)'
    r'(?P<json>.*?)'
    r'(?P<suffix></script>)',
    flags=re.S,
)
CARD_RE = re.compile(r'(?P<card><article\s+class=["\']parent-review-card["\']>.*?</article>)', flags=re.S)
STAR_RE = re.compile(
    r'<span\s+class=["\']parent-review-stars["\']\s+aria-label=["\'].*?["\']>.*?</span>',
    flags=re.S,
)


def normalize_parent(value: str) -> str:
    parts = value.strip().replace("\\", "/").strip("/").split("/")
    return "/".join(re.sub(r"\s+", "-", part.strip()) for part in parts if part.strip())


def sync_page(page_file: Path) -> str:
    original = page_file.read_text(encoding="utf-8")
    json_match = REVIEW_JSON_RE.search(original)
    cards = list(CARD_RE.finditer(original))
    if not json_match or len(cards) != 6:
        return "skipped"
    try:
        data = json.loads(json_match.group("json"))
    except json.JSONDecodeError:
        return "skipped"
    reviews = data.get("review") or []
    if len(reviews) != 6:
        return "skipped"

    for index, review in enumerate(reviews):
        rating = review.setdefault("reviewRating", {"@type": "Rating"})
        rating["@type"] = "Rating"
        rating["ratingValue"] = "4" if index == 5 else "5"
        rating["bestRating"] = "5"
    aggregate = data.setdefault("aggregateRating", {"@type": "AggregateRating"})
    aggregate["@type"] = "AggregateRating"
    aggregate["ratingValue"] = "4.8"
    aggregate["bestRating"] = "5"
    aggregate["ratingCount"] = "6"
    aggregate["reviewCount"] = "6"
    json_updated = (
        original[: json_match.start()]
        + json_match.group("prefix")
        + json.dumps(data, ensure_ascii=False)
        + json_match.group("suffix")
        + original[json_match.end() :]
    )

    def update_card(match: re.Match, index: int) -> str:
        rating = 4 if index == 5 else 5
        stars = "★★★★☆" if rating == 4 else "★★★★★"
        replacement = f'<span class="parent-review-stars" aria-label="5점 만점 중 {rating}점">{stars}</span>'
        return STAR_RE.sub(replacement, match.group("card"), count=1)

    rebuilt = []
    previous = 0
    for index, match in enumerate(CARD_RE.finditer(json_updated)):
        rebuilt.append(json_updated[previous : match.start()])
        rebuilt.append(update_card(match, index))
        previous = match.end()
    rebuilt.append(json_updated[previous:])
    updated = "".join(rebuilt)
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
            counts[sync_page(page_file)] += 1
    for key, value in counts.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
