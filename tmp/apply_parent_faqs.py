import hashlib
import html
import json
import random
import re
from pathlib import Path

ROOT = Path.cwd()
FAQS_PATH = ROOT / "tmp" / "parent_faqs.json"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def page_title(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    if not match:
        return fallback
    return clean_text(match.group(1)).split("|", 1)[0].strip() or fallback


def load_faqs() -> list[dict[str, str]]:
    if not FAQS_PATH.exists():
        return []
    data = json.loads(FAQS_PATH.read_text(encoding="utf-8"))
    return [
        {"question": clean_text(item.get("question", "")), "answer": clean_text(item.get("answer", ""))}
        for item in data
        if clean_text(item.get("question", "")) and clean_text(item.get("answer", ""))
    ]


FAQS = load_faqs()


def select_faqs(page_file: Path) -> list[dict[str, str]]:
    if len(FAQS) < 4:
        return []
    rel = page_file.relative_to(ROOT).as_posix()
    seed = int(hashlib.sha256((rel + "::faq").encode("utf-8")).hexdigest(), 16)
    return random.Random(seed).sample(FAQS, 4)


def faq_markup(title: str, faqs: list[dict[str, str]]) -> str:
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


def faq_json_ld(faqs: list[dict[str, str]]) -> str:
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


def remove_existing_faq(text: str) -> str:
    text = re.sub(
        r'  <script\s+type=["\']application/ld\+json["\']\s+data-parent-faq-jsonld>.*?</script>\n?',
        "",
        text,
        flags=re.S,
    )
    text = re.sub(
        r'\s*<section class="parent-faq-section" aria-labelledby="parent-faq-title">.*?</section>\s*',
        "\n",
        text,
        flags=re.S,
    )
    return text


def update_page(page_file: Path) -> bool:
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    if "parent-review-section" not in text:
        return False
    cleaned = remove_existing_faq(text)
    title = page_title(cleaned, page_file.parent.name)
    faqs = select_faqs(page_file)
    if not faqs:
        return False

    json_block = faq_json_ld(faqs)
    section = faq_markup(title, faqs)

    if "</head>" not in cleaned or '<section class="parent-review-section"' not in cleaned:
        return False

    updated = cleaned.replace("</head>", json_block + "</head>", 1)
    updated = updated.replace('<section class="parent-review-section"', section + '<section class="parent-review-section"', 1)

    if updated != text:
        page_file.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    if len(FAQS) < 4:
        raise SystemExit(f"FAQ data is too small: {len(FAQS)}")
    pages = sorted((ROOT / "center").rglob("index.html"))
    reviewed_pages = 0
    updated = 0
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="ignore")
        if "parent-review-section" in text:
            reviewed_pages += 1
        if update_page(page):
            updated += 1
    print(f"faq_items={len(FAQS)}")
    print(f"review_pages={reviewed_pages}")
    print(f"faq_pages_updated={updated}")


if __name__ == "__main__":
    main()
