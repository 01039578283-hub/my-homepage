from __future__ import annotations

from collections import Counter
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

import generate_subject_combined_pages as generator


ROOT = generator.ROOT
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value or ""))).strip()


def first(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(1)).strip() if match else ""


def graph_types(data: dict[str, object]) -> set[str]:
    values: set[str] = set()
    for node in data.get("@graph", []):
        value = node.get("@type")
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, list):
            values.update(item for item in value if isinstance(item, str))
    return values


def node_by_type(data: dict[str, object], type_name: str) -> dict[str, object]:
    for node in data.get("@graph", []):
        value = node.get("@type")
        if value == type_name or isinstance(value, list) and type_name in value:
            return node
    return {}


def local_target(page: Path, value: str) -> Path | None:
    if not value or value.startswith(("tel:", "mailto:", "#", "javascript:")):
        return None
    parsed = urlparse(html.unescape(value))
    if parsed.scheme and parsed.netloc and parsed.netloc not in {"wawa-center.kr", "www.wawa-center.kr"}:
        return None
    raw_path = unquote(parsed.path if parsed.scheme else value.split("#", 1)[0].split("?", 1)[0])
    if not raw_path:
        return None
    if raw_path.startswith("/"):
        target = ROOT / raw_path.lstrip("/")
    else:
        target = page.parent / raw_path
    target = target.resolve()
    if raw_path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target


def visible_faq(source: str) -> list[tuple[str, str]]:
    match = re.search(r'<div class="math-faq-list">(.*?)</div></div></section>', source, re.DOTALL)
    if not match:
        return []
    return [(clean(question), clean(answer)) for question, answer in re.findall(r"<summary>(.*?)</summary>\s*<p>(.*?)</p>", match.group(1), re.DOTALL)]


def schema_faq(data: dict[str, object]) -> list[tuple[str, str]]:
    faq = node_by_type(data, "FAQPage")
    return [
        (clean(str(item.get("name", ""))), clean(str(item.get("acceptedAnswer", {}).get("text", ""))))
        for item in faq.get("mainEntity", [])
    ]


def manuscript_sentence_stats(values: list[str]) -> dict[str, float | int]:
    sentence_counter: Counter[str] = Counter()
    total = 0
    for value in values:
        sentences = {
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", value)
            if len(re.sub(r"\s+", " ", sentence).strip()) >= 28
        }
        sentence_counter.update(sentences)
        total += len(sentences)
    repeated = sum(count for count in sentence_counter.values() if count > 1)
    return {
        "sentences": total,
        "unique_sentences": len(sentence_counter),
        "repeated_occurrence_rate": round(repeated / total, 4) if total else 0.0,
        "max_sentence_frequency": max(sentence_counter.values(), default=0),
    }


def main() -> None:
    expected_types = {
        "WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList",
        "Article", "Service", "FAQPage", "ItemList",
    }
    report: dict[str, object] = {"categories": {}}
    all_expected_urls: set[str] = set()

    for config in generator.CATEGORIES:
        namespace = generator.transformed_namespace(config)
        generator.configure_namespace(namespace, config)
        manuscripts = namespace["load_manuscripts"]()
        order, _ = namespace["ordered_locals_and_directory"]()
        category_root = ROOT / "과목별학원" / config["slug"]
        category_urls: set[str] = set()
        meta_values: set[str] = set()
        body_values: list[str] = []
        faq_values: set[str] = set()
        review_values: set[str] = set()
        reviewed_pages = 0
        offer_pages = 0
        checked_links = 0

        if len(manuscripts) != 371 or set(manuscripts) != set(order):
            fail(f'{config["slug"]}: manuscript/order mismatch')

        for local in order:
            page = category_root / local / "index.html"
            if not page.exists():
                fail(f'{config["slug"]}/{local}: missing page')
                continue
            source = page.read_text(encoding="utf-8")
            manuscript = manuscripts[local]
            title = str(manuscript["title"])
            expected_url = namespace["encoded_url"]("과목별학원", config["slug"], local)
            title_tag = clean(first(r"<title>(.*?)</title>", source))
            h1s = [clean(value) for value in re.findall(r"<h1\b[^>]*>(.*?)</h1>", source, re.DOTALL | re.IGNORECASE)]
            description = first(r'<meta\s+name="description"\s+content="([^"]*)"', source)
            canonical = first(r'<link\s+rel="canonical"\s+href="([^"]+)"', source)
            og_url = first(r'<meta\s+property="og:url"\s+content="([^"]+)"', source)
            if title_tag != f"{title} | 와와학습코칭센터 영어수학 전문학원":
                fail(f'{config["slug"]}/{local}: title mismatch')
            if h1s != [title]:
                fail(f'{config["slug"]}/{local}: H1 mismatch/count={len(h1s)}')
            if description != manuscript["meta"]:
                fail(f'{config["slug"]}/{local}: meta mismatch')
            if canonical != expected_url or og_url != expected_url:
                fail(f'{config["slug"]}/{local}: canonical/og mismatch')
            category_urls.add(canonical)
            meta_values.add(description)

            scripts = re.findall(r'<script\s+type="application/ld\+json">(.*?)</script>', source, re.DOTALL | re.IGNORECASE)
            if len(scripts) != 1:
                fail(f'{config["slug"]}/{local}: JSON-LD count={len(scripts)}')
                continue
            try:
                data = json.loads(scripts[0])
            except Exception as exc:
                fail(f'{config["slug"]}/{local}: invalid JSON-LD {exc}')
                continue
            missing_types = expected_types - graph_types(data)
            if missing_types:
                fail(f'{config["slug"]}/{local}: missing schema {sorted(missing_types)}')
            article = node_by_type(data, "Article")
            for prop in ("about", "mentions", "hasPart", "articleSection"):
                if not article.get(prop):
                    fail(f'{config["slug"]}/{local}: Article.{prop} empty')
            service = node_by_type(data, "Service")
            organization = node_by_type(data, "EducationalOrganization")
            if service.get("makesOffer") and organization.get("makesOffer"):
                offer_pages += 1
            screen_faq = visible_faq(source)
            json_faq = schema_faq(data)
            if not screen_faq or screen_faq != json_faq:
                fail(f'{config["slug"]}/{local}: visible/schema FAQ mismatch')

            images = re.findall(r"<img\b([^>]*)>", source, re.IGNORECASE)
            if len(images) < 3:
                fail(f'{config["slug"]}/{local}: images={len(images)}')
            else:
                if 'style="display:none;"' not in images[0] or 'loading="lazy"' in images[0]:
                    fail(f'{config["slug"]}/{local}: representative image attributes')
                for image_index, attributes in enumerate(images[:3]):
                    src = first(r'src="([^"]+)"', attributes)
                    alt = first(r'alt="([^"]*)"', attributes)
                    if not alt:
                        fail(f'{config["slug"]}/{local}: image {image_index + 1} missing alt')
                    target = local_target(page, src)
                    if target is not None and not target.exists():
                        fail(f'{config["slug"]}/{local}: broken image {src}')

            for href in re.findall(r'<a\b[^>]*href="([^"]+)"', source, re.IGNORECASE):
                checked_links += 1
                target = local_target(page, href)
                if target is not None and not target.exists():
                    fail(f'{config["slug"]}/{local}: broken link {href}')

            body_chunks = [*manuscript["intro"]]
            for heading, paragraphs in manuscript["sections"]:
                body_chunks.append(heading)
                body_chunks.extend(paragraphs)
            for value in body_chunks:
                if html.escape(str(value), quote=True) not in source:
                    fail(f'{config["slug"]}/{local}: manuscript body text missing')
                    break
            for item in manuscript["faqs"]:
                if html.escape(item["question"], quote=True) not in source or html.escape(item["answer"], quote=True) not in source:
                    fail(f'{config["slug"]}/{local}: manuscript FAQ text missing')
                    break
            for review in manuscript["reviews"]:
                if html.escape(review["content"], quote=True) not in source:
                    fail(f'{config["slug"]}/{local}: manuscript review text missing')
                    break
            rendered_review_labels = [
                clean(value)
                for value in re.findall(
                    r'<article class="english-review-item"><strong>(.*?)</strong>',
                    source,
                    re.DOTALL,
                )
            ]
            if (
                len(rendered_review_labels) != len(manuscript["reviews"])
                or len(rendered_review_labels) != len(set(rendered_review_labels))
            ):
                fail(f'{config["slug"]}/{local}: review labels missing or duplicated')
            if manuscript["reviews"]:
                reviewed_pages += 1
            if html.escape(str(manuscript["summary"]), quote=True) not in source:
                fail(f'{config["slug"]}/{local}: manuscript summary missing')

            body_values.append("\n".join(str(value) for value in body_chunks))
            faq_values.add("\n".join(f'{item["question"]}|{item["answer"]}' for item in manuscript["faqs"]))
            review_values.add("\n".join(item["content"] for item in manuscript["reviews"]))

        hub = category_root / "index.html"
        if not hub.exists():
            fail(f'{config["slug"]}: hub missing')
            hub_links: list[str] = []
        else:
            hub_source = hub.read_text(encoding="utf-8")
            hub_links = re.findall(r'href="\./([^"/]+)/"\s+data-local=', hub_source)
            if len(hub_links) != 371 or len(set(hub_links)) != 371 or set(hub_links) != set(order):
                fail(f'{config["slug"]}: hub local links={len(hub_links)}/{len(set(hub_links))}')
            hub_scripts = re.findall(r'<script\s+type="application/ld\+json">(.*?)</script>', hub_source, re.DOTALL)
            if len(hub_scripts) != 1:
                fail(f'{config["slug"]}: hub JSON-LD count={len(hub_scripts)}')
            else:
                hub_data = json.loads(hub_scripts[0])
                hub_item_list = node_by_type(hub_data, "ItemList")
                if hub_item_list.get("numberOfItems") != 371 or len(hub_item_list.get("itemListElement", [])) != 371:
                    fail(f'{config["slug"]}: hub ItemList mismatch')
                if visible_faq(hub_source) != schema_faq(hub_data):
                    fail(f'{config["slug"]}: hub visible/schema FAQ mismatch')

        category_hub_url = namespace["encoded_url"]("과목별학원", config["slug"])
        all_expected_urls.add(category_hub_url)
        all_expected_urls.update(category_urls)
        report["categories"][config["slug"]] = {
            "detail_pages": len(category_urls),
            "unique_canonicals": len(category_urls),
            "unique_meta_descriptions": len(meta_values),
            "unique_manuscript_bodies": len(set(body_values)),
            "unique_faq_sets": len(faq_values),
            "unique_review_sets": len(review_values),
            "pages_with_reviews": reviewed_pages,
            "pages_with_verified_offer_data": offer_pages,
            "hub_local_links": len(hub_links),
            "internal_links_checked": checked_links,
            "sentence_metrics": manuscript_sentence_stats(body_values),
        }

    master_source = (ROOT / "과목별학원" / "index.html").read_text(encoding="utf-8")
    expected_master_items = int(getattr(generator, "EXPECTED_MASTER_ITEMS", 7))
    master_cards = re.findall(r'<a class="subject-category-card"', master_source)
    if len(master_cards) != expected_master_items:
        fail(f"master subject cards={len(master_cards)}")
    master_data = json.loads(first(r'<script type="application/ld\+json">(.*?)</script>', master_source))
    master_items = node_by_type(master_data, "ItemList")
    if (
        master_items.get("numberOfItems") != expected_master_items
        or len(master_items.get("itemListElement", [])) != expected_master_items
    ):
        fail("master subject ItemList mismatch")

    sitemap = ET.parse(ROOT / "sitemap.xml").getroot()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_urls = [node.text for node in sitemap.findall("s:url/s:loc", ns) if node.text]
    missing_sitemap = all_expected_urls - set(sitemap_urls)
    if missing_sitemap:
        fail(f"sitemap missing new URLs={len(missing_sitemap)}")
    if len(sitemap_urls) != len(set(sitemap_urls)):
        fail(f"sitemap duplicate URLs={len(sitemap_urls) - len(set(sitemap_urls))}")
    report["new_urls_expected"] = len(all_expected_urls)
    report["sitemap_urls"] = len(sitemap_urls)
    report["sitemap_unique"] = len(set(sitemap_urls))
    report["errors"] = len(ERRORS)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if ERRORS:
        print("\n".join(ERRORS[:200]), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
