"""Strict audit for generated neighborhood school-level subject pages."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from lxml import etree, html

from branch_course_guidance import course_answer, course_guidance
from branch_manuscript_editorial import AUTHORING, corrections, edit_manuscript, other_level_school_names
from branch_page_summaries import topic_summaries, validate_summaries, summary_document_errors
from generate_branch_topic_pages import load_manuscripts


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools" / "data" / "branch-topic-pages" / "pages.json"
BRANCH_MANIFEST = ROOT / "tools" / "data" / "branch-directory" / "branches.json"
SITEMAP = ROOT / "sitemap.xml"
REPORT = ROOT / "reports" / "branch-topic-pages" / "technical-audit.json"
DOMAIN = "https://wawa-center.kr"
EXPECTED_PAGES = 2226
EXPECTED_SKIPPED = 0
TOPICS = [
    ("초등", "수학"), ("초등", "영어"),
    ("중등", "수학"), ("중등", "영어"),
    ("고등", "수학"), ("고등", "영어"),
]
EXCLUDED_TERMS = ("실제 수강 후기", "홍보 이미지")


def encoded_url(path: str) -> str:
    return DOMAIN + quote(path, safe="/#")


def normalized_text(node: object) -> str:
    if hasattr(node, "text_content"):
        value = node.text_content()
    else:
        value = str(node)
    return " ".join(value.split())


def schema_types(node: dict[str, object]) -> set[str]:
    value = node.get("@type", [])
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def local_file(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and parsed.netloc != "wawa-center.kr":
        return None
    path = unquote(parsed.path or value.split("#", 1)[0])
    if not path.startswith("/"):
        return None
    target = ROOT / path.strip("/")
    if path.endswith("/"):
        target = target / "index.html"
    return target


def srcset_entries(value: str) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for part in value.split(","):
        match = re.fullmatch(r"\s*(\S+)\s+(\d+)w\s*", part)
        if match:
            entries.append((match.group(1), int(match.group(2))))
    return entries


def main() -> None:
    manuscripts = load_manuscripts()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    branches = json.loads(BRANCH_MANIFEST.read_text(encoding="utf-8"))["centers"]
    center_by_route = {center["routeName"]: center for center in branches}
    pages = data.get("pages", [])
    skipped = data.get("skipped", [])
    errors: list[str] = []
    warnings: list[str] = []
    titles: list[str] = []
    descriptions: list[str] = []
    canonicals: list[str] = []
    responsive_pages = 0
    reviewed_pages = 0
    service_pages = 0

    if data.get("pageCount") != EXPECTED_PAGES or len(pages) != EXPECTED_PAGES:
        errors.append(f"생성 페이지 수 오류: manifest={data.get('pageCount')} list={len(pages)}")
    if data.get("skippedCount") != EXPECTED_SKIPPED or len(skipped) != EXPECTED_SKIPPED:
        errors.append(f"제외 페이지 수 오류: manifest={data.get('skippedCount')} list={len(skipped)}")
    if data.get("sourceManuscriptCount") != len(pages):
        errors.append("원고 수와 생성 페이지 수가 다름")
    locality_counts = Counter(item.get("locality") for item in pages)
    if len(locality_counts) != 371 or any(count != len(TOPICS) for count in locality_counts.values()):
        errors.append("371개 동네별 6개 주제 구성이 다름")
    taean_pages = [item for item in pages if item.get("locality") == "화성태안"]
    if {(item.get("level"), item.get("subject")) for item in taean_pages} != set(TOPICS):
        errors.append("화성태안의 6개 주제 중 누락 또는 중복")
    if any(item.get("center") != "화성태안점" for item in taean_pages):
        errors.append("화성태안 원고가 다른 지점에 연결됨")

    expected_paths = {item["path"] for item in pages}
    if len(expected_paths) != len(pages):
        errors.append("manifest path 중복")

    for record in pages:
        relative = record["file"]
        file = ROOT / relative
        label = relative
        if not file.is_file():
            errors.append(f"{label}: 파일 없음")
            continue
        center = center_by_route.get(record["center"])
        if not center:
            errors.append(f"{label}: 센터 manifest 연결 실패")
            continue
        raw = file.read_text(encoding="utf-8")
        document = html.fromstring(raw)
        head_title = normalized_text("".join(document.xpath("//title/text()")))
        h1s = document.xpath("//h1")
        h1 = normalized_text(h1s[0]) if len(h1s) == 1 else ""
        description = "".join(document.xpath('//meta[@name="description"]/@content')).strip()
        canonical = "".join(document.xpath('//link[@rel="canonical"]/@href')).strip()
        og_url = "".join(document.xpath('//meta[@property="og:url"]/@content')).strip()
        expected_canonical = encoded_url(record["path"])

        if len(h1s) != 1:
            errors.append(f"{label}: H1 수 {len(h1s)}")
        if h1 != record["title"]:
            errors.append(f"{label}: H1과 manifest title 불일치")
        if not head_title.startswith(record["title"] + " | "):
            errors.append(f"{label}: title 접미사 구성 오류")
        if not description:
            errors.append(f"{label}: meta description 없음")
        if canonical != expected_canonical or og_url != expected_canonical:
            errors.append(f"{label}: canonical/og:url 불일치")
        titles.append(head_title)
        descriptions.append(description)
        canonicals.append(canonical)

        crumbs = document.xpath('//nav[contains(@class,"branch-breadcrumb")]//li')
        if len(crumbs) != 5 or normalized_text(crumbs[-1]) != record["title"]:
            errors.append(f"{label}: 브레드크럼 5단계 오류")

        status_text = normalized_text(" ".join(document.xpath('//dl[contains(@class,"branch-topic-status")]//text()')))
        reviewed_at = record.get("informationReviewedAt", "")
        if not reviewed_at or reviewed_at not in status_text:
            errors.append(f"{label}: 상단 정보 확인 기준일 없음")
        else:
            reviewed_pages += 1

        quick = document.xpath('//section[contains(@class,"branch-answer")]')
        quick_paragraphs = quick[0].xpath('./p[not(contains(@class,"branch-kicker"))]') if quick else []
        prefix = record["level"][0]
        view = course_guidance(center, record["subject"], prefix)
        expected_answer = course_answer(center, record["subject"], prefix)
        if not quick_paragraphs or normalized_text(quick_paragraphs[0]) != expected_answer:
            errors.append(f"{label}: 첫 요약과 검토된 학년·수업 조건 불일치")
        if record.get("publishedGrades") != view["grades"] or record.get("confirmationGrades") != view["pendingGrades"]:
            errors.append(f"{label}: 학년 검토 결과 manifest 불일치")

        primary = document.xpath('//section[contains(@class,"branch-primary-media")]')
        if len(primary) != 1:
            errors.append(f"{label}: 대표·본문·지도 섹션 수 {len(primary)}")
        else:
            section = primary[0]
            if not quick or quick[0].sourceline >= section.sourceline:
                errors.append(f"{label}: 첫 학년 안내가 이미지 아래에 있음")
            representative = section.xpath('.//img[contains(@class,"branch-representative-image")]')
            body_picture = section.xpath('.//figure[contains(@class,"branch-body-image")]/picture')
            body_images = section.xpath('.//figure[contains(@class,"branch-body-image")]//img')
            map_images = section.xpath('.//figure[contains(@class,"branch-map-image")]//img')
            ordered = section.xpath('.//img')
            if len(representative) != 1 or representative[0].get("style") != "display:none;":
                errors.append(f"{label}: 숨김 대표이미지 형식 오류")
            if len(body_picture) != 1 or len(body_images) != 1 or len(map_images) != 1:
                errors.append(f"{label}: 본문 picture 또는 지도 이미지 오류")
            if len(ordered) != 3 or ordered != [*representative, *body_images, *map_images]:
                errors.append(f"{label}: 대표→본문→지도 순서 오류")
            for kind, nodes in (("대표", representative), ("본문", body_images), ("지도", map_images)):
                if nodes:
                    image = nodes[0]
                    if record["title"] not in image.get("alt", "") or kind not in image.get("alt", ""):
                        errors.append(f"{label}: {kind} ALT 개별화 오류")
                    if not image.get("width") or not image.get("height"):
                        errors.append(f"{label}: {kind} 이미지 크기 속성 없음")
            if body_picture:
                # lxml's HTML parser may nest consecutive void <source> nodes;
                # browser parsing still treats both as picture sources.
                sources = body_picture[0].xpath('.//source')
                source_types = {source.get("type") for source in sources}
                fallback_width = int(body_images[0].get("width", "0")) if body_images else 0
                widths_by_type: dict[str, set[int]] = {}
                for source in sources:
                    entries = srcset_entries(source.get("srcset", ""))
                    widths_by_type[source.get("type", "")] = {width for _, width in entries}
                    for src, _ in entries:
                        target = local_file(src)
                        if target is not None and not target.is_file():
                            errors.append(f"{label}: srcset 이미지 없음 {src}")
                required_widths = {480, 768, fallback_width}
                if source_types != {"image/avif", "image/webp"}:
                    errors.append(f"{label}: AVIF/WebP source 구성 오류")
                elif any(not required_widths.issubset(widths_by_type.get(kind, set())) for kind in source_types):
                    errors.append(f"{label}: 반응형 srcset 폭 구성 오류")
                else:
                    responsive_pages += 1

        for src in document.xpath('//img/@src'):
            target = local_file(src)
            if target is not None and not target.is_file():
                errors.append(f"{label}: 이미지 없음 {src}")

        scripts = document.xpath('//script[@type="application/ld+json"]/text()')
        if len(scripts) != 1:
            errors.append(f"{label}: JSON-LD 스크립트 수 {len(scripts)}")
            graph: list[dict[str, object]] = []
        else:
            try:
                payload = json.loads(scripts[0])
                graph = payload.get("@graph", [])
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: JSON-LD 파싱 실패 {exc}")
                graph = []
        types = Counter(kind for node in graph for kind in schema_types(node))
        source = manuscripts[(record["locality"], record["level"], record["subject"])]
        edited, _ = edit_manuscript(center, source)
        expected_summary = topic_summaries(center, edited)
        try:
            validate_summaries(center, expected_summary, edited)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
        errors.extend(f"{label}: {error}" for error in summary_document_errors(document, graph, expected_summary))
        for required in ("WebSite", "WebPage", "BreadcrumbList", "EducationalOrganization", "LocalBusiness", "Article", "FAQPage", "ItemList"):
            if types[required] < 1:
                errors.append(f"{label}: JSON-LD {required} 없음")
        has_service = types["Service"] > 0
        if has_service != bool(view["grades"]):
            errors.append(f"{label}: 검토된 과목·학년과 Service 스키마 불일치")
        if has_service:
            service_pages += 1
            service = next(node for node in graph if "Service" in schema_types(node))
            if service.get("audience", {}).get("audienceType") != view["label"] or service.get("description") != expected_answer:
                errors.append(f"{label}: Service 학년·조건 불일치")
        if "schema.org/InStock" in raw:
            errors.append(f"{label}: 실제 정원 확인 없는 InStock 표시")
        academy = next((node for node in graph if str(node.get("@id", "")).endswith("#academy")), None)
        properties = academy.get("additionalProperty", {}) if academy else {}
        if not academy or properties.get("value") != reviewed_at:
            errors.append(f"{label}: 구조화 데이터 정보 확인 기준일 오류")
        faq_node = next((node for node in graph if "FAQPage" in schema_types(node)), None)
        visible_faqs = document.xpath('//section[@id="faq"]//details')
        schema_faqs = faq_node.get("mainEntity", []) if faq_node else []
        if len(visible_faqs) < 3 or len(visible_faqs) != len(schema_faqs):
            errors.append(f"{label}: FAQ 표시/스키마 수 불일치")
        for element, entry in zip(visible_faqs, schema_faqs):
            if normalized_text(element.xpath('./summary')[0]) != entry["name"] or normalized_text(' '.join(element.xpath('./p//text()'))) != entry["acceptedAnswer"]["text"]:
                errors.append(f"{label}: FAQ 본문/스키마 내용 불일치")
        if not schema_faqs or schema_faqs[0]["acceptedAnswer"]["text"] != expected_answer:
            errors.append(f"{label}: 첫 요약과 학년 FAQ 불일치")

        editorial_nodes = document.xpath('//*[@id="article"] | //section[@id="faq"] | //section[contains(@class,"branch-topic-example")]')
        editorial_text = " ".join(normalized_text(node) for node in editorial_nodes)
        if AUTHORING.search(editorial_text):
            errors.append(f"{label}: 작성용 표현 잔존")
        misplaced_schools = other_level_school_names(center, record["level"], editorial_text)
        if misplaced_schools:
            errors.append(f"{label}: 다른 학교급 학교명 잔존 {sorted(misplaced_schools)}")
        correction = corrections().get((record["locality"], record["level"], record["subject"]))
        if correction and re.search(correction["pattern"], editorial_text):
            errors.append(f"{label}: 검토 후 교정한 부적합 예시가 다시 나타남")
        faq_questions = [entry["name"] for entry in schema_faqs]
        if len(faq_questions) != len(set(faq_questions)):
            errors.append(f"{label}: FAQ 질문 중복")

        related_hrefs = document.xpath('//section[@id="related-pages"]//a/@href')
        expected_siblings = {
            f'/지점안내/{center["region"]}/{center["routeName"]}/{record["locality"]}{level}{subject}학원/'
            for level, subject in TOPICS
            if (level, subject) != (record["level"], record["subject"])
        }
        if not expected_siblings.issubset(set(related_hrefs)):
            errors.append(f"{label}: 같은 동네 5개 관련 페이지 링크 부족")
        parent_path = f'/지점안내/{center["region"]}/{center["routeName"]}/'
        if parent_path not in document.xpath('//a/@href'):
            errors.append(f"{label}: 상위 지점 링크 없음")
        for href in related_hrefs:
            if href.startswith("/지점안내/") and href.endswith("학원/") and href not in expected_paths:
                errors.append(f"{label}: 존재하지 않는 생성 페이지 링크 {href}")

        for term in EXCLUDED_TERMS:
            if term in raw:
                errors.append(f"{label}: 부적절한 표현 포함 {term}")
        if len(description) < 65 or len(description) > 165:
            warnings.append(f"{label}: meta description 길이 {len(description)}")

    for name, values in (("title", titles), ("description", descriptions), ("canonical", canonicals)):
        duplicates = [value for value, count in Counter(values).items() if value and count > 1]
        if duplicates:
            errors.append(f"중복 {name}: {len(duplicates)}")

    sitemap_tree = etree.parse(str(SITEMAP))
    locations = [normalized_text(value) for value in sitemap_tree.xpath('//*[local-name()="loc"]/text()')]
    location_counts = Counter(locations)
    for path in expected_paths:
        url = encoded_url(path)
        if location_counts[url] != 1:
            errors.append(f"sitemap URL 수 오류: {url}={location_counts[url]}")

    available_count = sum(bool(item["availableInCenterData"]) for item in pages)
    result = {
        "pageCount": len(pages),
        "skippedCount": len(skipped),
        "responsiveBodyImagePages": responsive_pages,
        "informationReviewedPages": reviewed_pages,
        "serviceSchemaPages": service_pages,
        "availableRecorded": available_count,
        "availabilityConfirmationNeeded": len(pages) - available_count,
        "errors": errors,
        "warnings": warnings,
        "duplicateCounts": {
            "titles": len(titles) - len(set(titles)),
            "descriptions": len(descriptions) - len(set(descriptions)),
            "canonicals": len(canonicals) - len(set(canonicals)),
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
