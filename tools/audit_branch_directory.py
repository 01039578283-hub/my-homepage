"""Technical and content audit for the generated Korean branch directory."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import html

from branch_course_guidance import branch_course_answer, course_guidance, weekend_guidance
from branch_page_summaries import center_summaries, summary_document_errors


ROOT = Path(__file__).resolve().parents[1]
BRANCH_ROOT = ROOT / "지점안내"
BRANCH_MANIFEST = ROOT / "tools" / "data" / "branch-directory" / "branches.json"
REPORT = ROOT / "reports" / "branch-directory" / "technical-audit.json"
DOMAIN = "wawa-center.kr"
EXCLUDED_TERMS = ("(W+)", "글로리드", "대구역점2호관", "홍보 이미지")


def local_path_from_url(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and parsed.netloc != DOMAIN:
        return None
    path = unquote(parsed.path or value.split("#", 1)[0])
    if not path.startswith("/"):
        return None
    relative = path.strip("/")
    target = ROOT / relative
    if path.endswith("/"):
        target = target / "index.html"
    return target


def main() -> None:
    branch_data = json.loads(BRANCH_MANIFEST.read_text(encoding="utf-8"))
    centers_by_path = {
        f'지점안내/{center["region"]}/{center["routeName"]}/index.html': center
        for center in branch_data["centers"]
    }
    files = sorted(BRANCH_ROOT.rglob("index.html"))
    errors: list[str] = []
    warnings: list[str] = []
    canonicals: list[str] = []
    titles: list[str] = []
    descriptions: list[str] = []
    branch_pages = 0
    region_pages = 0
    primary_media_pages = 0
    system_hub_pages = 0

    for file in files:
        relative = file.relative_to(ROOT).as_posix()
        raw = file.read_text(encoding="utf-8")
        document = html.fromstring(raw)
        title = "".join(document.xpath("//title/text()")).strip()
        description = "".join(document.xpath('//meta[@name="description"]/@content')).strip()
        canonical = "".join(document.xpath('//link[@rel="canonical"]/@href')).strip()
        h1s = [" ".join(item.text_content().split()) for item in document.xpath("//h1")]
        scripts = document.xpath('//script[@type="application/ld+json"]/text()')

        if not title:
            errors.append(f"{relative}: title 없음")
        if not description:
            errors.append(f"{relative}: meta description 없음")
        if len(h1s) != 1:
            errors.append(f"{relative}: H1 수 {len(h1s)}")
        if not canonical:
            errors.append(f"{relative}: canonical 없음")
        if not scripts:
            errors.append(f"{relative}: JSON-LD 없음")

        for script in scripts:
            try:
                data = json.loads(script)
            except json.JSONDecodeError as exc:
                errors.append(f"{relative}: JSON-LD 파싱 실패 {exc}")
                continue
            graph = data.get("@graph", []) if isinstance(data, dict) else []
            ids = [item.get("@id") for item in graph if isinstance(item, dict) and item.get("@id")]
            duplicates = [value for value, count in Counter(ids).items() if count > 1]
            if duplicates:
                errors.append(f"{relative}: JSON-LD @id 중복 {duplicates}")

            if len(file.relative_to(BRANCH_ROOT).parts) == 3:
                branch_pages += 1
                article = next((item for item in graph if item.get("@type") == "Article"), None)
                service = next((item for item in graph if item.get("@type") == "Service"), None)
                academy = next((item for item in graph if item.get("@id", "").endswith("#academy")), None)
                webpage = next((item for item in graph if item.get("@id", "").endswith("#webpage")), None)
                if not article:
                    errors.append(f"{relative}: Article 없음")
                elif len(article.get("image", [])) != 3:
                    errors.append(f"{relative}: Article image 3종 미연결")
                if not service:
                    errors.append(f"{relative}: Service 없음")
                if not academy or not academy.get("makesOffer"):
                    errors.append(f"{relative}: EducationalOrganization makesOffer 없음")
                if not webpage or not webpage.get("hasPart") or not webpage.get("primaryImageOfPage"):
                    errors.append(f"{relative}: WebPage 관계 또는 대표 이미지 없음")
                reviewed_properties = academy.get("additionalProperty", {}) if academy else {}
                expected_center = centers_by_path.get(relative)
                if expected_center:
                    errors.extend(f"{relative}: {error}" for error in summary_document_errors(document, graph, center_summaries(expected_center)))
                reviewed_at = expected_center.get("informationReviewedAt", "") if expected_center else ""
                if not reviewed_at or reviewed_properties.get("value") != reviewed_at:
                    errors.append(f"{relative}: 구조화 데이터 정보 확인 기준일 오류")
                visible_reviewed = document.xpath('//dt[normalize-space()="정보 확인 기준일"]/following-sibling::dd[1]')
                if not visible_reviewed or reviewed_at not in visible_reviewed[0].text_content():
                    errors.append(f"{relative}: 표시 정보 확인 기준일 오류")
                overview = document.xpath('//section[@id="overview"]')
                if not overview or not expected_center:
                    errors.append(f"{relative}: 상단 학년 요약 없음")
                else:
                    for subject in ("영어", "수학"):
                        actual = overview[0].xpath(f'.//div[@data-subject="{subject}"]//strong/text()')
                        if actual != [course_guidance(expected_center, subject)["label"]]:
                            errors.append(f"{relative}: 상단 {subject} 학년 범위 불일치")
                    for subject in ("국어", "영어", "수학", "과학", "사회"):
                        view = course_guidance(expected_center, subject)
                        actual = document.xpath(f'//section[@id="subjects"]//tr[@data-subject="{subject}"]//strong/text()')
                        if actual != [view["label"]]:
                            errors.append(f"{relative}: {subject} 표의 학년 범위 불일치")
                    faq = next(item for item in graph if item.get("@type") == "FAQPage")
                    if faq["mainEntity"][1]["acceptedAnswer"]["text"] != branch_course_answer(expected_center):
                        errors.append(f"{relative}: 학년 FAQ 내용 불일치")
                    if faq["mainEntity"][3]["acceptedAnswer"]["text"] != weekend_guidance(expected_center):
                        errors.append(f"{relative}: 주말 FAQ 내용 불일치")
                    for element, entry in zip(document.xpath('//section[@id="faq"]//details'), faq["mainEntity"]):
                        if " ".join(element.xpath('./p')[0].text_content().split()) != entry["acceptedAnswer"]["text"]:
                            errors.append(f"{relative}: 표시 FAQ와 스키마 불일치")
                    expected_offers = {v["subject"]: v for v in [course_guidance(expected_center, s) for s in ("국어", "영어", "수학", "과학", "사회")] if v["grades"]}
                    offers = academy.get("makesOffer", [])
                    if expected_offers and len(offers) != len(expected_offers):
                        errors.append(f"{relative}: 검토된 학년과 과목 Offer 수 불일치")
                    for subject, view in expected_offers.items():
                        offered = next((o["itemOffered"] for o in offers if o["itemOffered"]["name"] == f'{expected_center["routeName"]} {subject} 학습코칭'), {})
                        if offered.get("audience", {}).get("audienceType") != view["label"]:
                            errors.append(f"{relative}: {subject} Offer 학년 범위 불일치")
                primary_sections = document.xpath('//section[contains(concat(" ", normalize-space(@class), " "), " branch-primary-media ")]')
                if len(primary_sections) != 1:
                    errors.append(f"{relative}: 대표·본문·지도 섹션 수 {len(primary_sections)}")
                else:
                    primary_media_pages += 1
                    primary = primary_sections[0]
                    if overview and overview[0].sourceline >= primary.sourceline:
                        errors.append(f"{relative}: 상단 학년 요약이 이미지 아래에 있음")
                    representative = primary.xpath('.//img[contains(concat(" ", normalize-space(@class), " "), " branch-representative-image ")]')
                    body_images = primary.xpath('.//figure[contains(concat(" ", normalize-space(@class), " "), " branch-body-image ")]//img')
                    map_images = primary.xpath('.//figure[contains(concat(" ", normalize-space(@class), " "), " branch-map-image ")]//img')
                    if len(representative) != 1 or representative[0].get("style") != "display:none;":
                        errors.append(f"{relative}: 숨김 대표이미지 형식 오류")
                    if len(body_images) != 1 or len(map_images) != 1:
                        errors.append(f"{relative}: 본문·지도 이미지 수 오류")
                    pictures = primary.xpath('.//figure[contains(concat(" ", normalize-space(@class), " "), " branch-body-image ")]/picture')
                    if len(pictures) != 1:
                        errors.append(f"{relative}: 본문 반응형 picture 없음")
                    else:
                        source_types = set(pictures[0].xpath('.//source/@type'))
                        srcsets = pictures[0].xpath('.//source/@srcset')
                        if source_types != {"image/avif", "image/webp"} or len(srcsets) != 2:
                            errors.append(f"{relative}: 본문 AVIF/WebP source 오류")
                        for srcset in srcsets:
                            for entry in srcset.split(','):
                                src = entry.strip().split(' ', 1)[0]
                                target = local_path_from_url(src)
                                if target is not None and not target.exists():
                                    errors.append(f"{relative}: 반응형 이미지 없음 {src}")
                    ordered_images = primary.xpath('.//img')
                    if len(ordered_images) != 3 or ordered_images != [*representative, *body_images, *map_images]:
                        errors.append(f"{relative}: 대표→본문→지도 순서 오류")
                    page_name = h1s[0] if h1s else ""
                    for label, images in (("대표", representative), ("본문", body_images), ("지도", map_images)):
                        if images:
                            image = images[0]
                            if page_name not in image.get("alt", "") or label not in image.get("alt", ""):
                                errors.append(f"{relative}: {label} 이미지 ALT 개별화 오류")
                            if not image.get("width") or not image.get("height"):
                                errors.append(f"{relative}: {label} 이미지 크기 속성 없음")
                    if raw.index('class="branch-primary-media"') > raw.index('class="branch-media'):
                        errors.append(f"{relative}: 기본 이미지가 LEARNING SPACE 아래에 배치됨")
                topic_links = document.xpath('//section[@id="learning-pages"]//a/@href')
                expected_topic_count = len(expected_center.get("neighborhoods", [])) * 6 if expected_center else 0
                if len(topic_links) != expected_topic_count:
                    errors.append(f"{relative}: 동네별 하위 페이지 링크 수 {len(topic_links)} (예상 {expected_topic_count})")
                item_list = next((item for item in graph if item.get("@type") == "ItemList" and item.get("@id", "").endswith("#learning-pages-list")), None)
                if expected_topic_count:
                    if not item_list or item_list.get("numberOfItems") != expected_topic_count or len(item_list.get("itemListElement", [])) != expected_topic_count:
                        errors.append(f"{relative}: 하위 페이지 ItemList 수 오류")
                    page_node = next((item for item in graph if item.get("@type") == "WebPage"), {})
                    learning_section = next((part for part in page_node.get("hasPart", []) if part.get("@id", "").endswith("#learning-pages")), {})
                    if learning_section.get("@type") != "WebPageElement" or not item_list or learning_section.get("mainEntity", {}).get("@id") != item_list["@id"]:
                        errors.append(f"{relative}: 학습 안내 구역과 ItemList 연결 오류")
                elif item_list:
                    errors.append(f"{relative}: 연결 동네 없이 하위 페이지 ItemList 존재")
                media_sections = document.xpath('//section[contains(concat(" ", normalize-space(@class), " "), " branch-media ")]')
                if len(media_sections) != 1:
                    errors.append(f"{relative}: 학습 공간 이미지 섹션 수 {len(media_sections)}")
                else:
                    photo_source = media_sections[0].get("data-photo-source")
                    if photo_source not in {"center", "common"}:
                        errors.append(f"{relative}: 사진 출처 구분 없음")
                    media_images = media_sections[0].xpath('.//img')
                    if not media_images:
                        errors.append(f"{relative}: 학습 공간 이미지 없음")
                    if photo_source == "common" and "학습 공간과 운영 환경" not in media_sections[0].text_content():
                        errors.append(f"{relative}: 학습 공간 안내 문구 없음")
            elif len(file.relative_to(BRANCH_ROOT).parts) == 2:
                region_pages += 1
                system_sections = document.xpath('//section[contains(concat(" ", normalize-space(@class), " "), " branch-system ")]')
                if len(system_sections) != 1:
                    errors.append(f"{relative}: 지역 허브 학습 시스템 섹션 수 {len(system_sections)}")
                else:
                    system_hub_pages += 1
                visible_faqs = document.xpath('//section[@id="faq"]//details')
                if len(visible_faqs) < 3:
                    errors.append(f"{relative}: 지역 허브 FAQ 부족")

        if len(file.relative_to(BRANCH_ROOT).parts) == 1:
            system_sections = document.xpath('//section[contains(concat(" ", normalize-space(@class), " "), " branch-system ")]')
            if len(system_sections) != 1:
                errors.append(f"{relative}: 전국 허브 학습 시스템 섹션 수 {len(system_sections)}")
            else:
                system_hub_pages += 1

        for value in document.xpath("//img/@src"):
            target = local_path_from_url(value)
            if target is not None and not target.exists():
                errors.append(f"{relative}: 이미지 없음 {value}")
        for value in document.xpath("//a/@href"):
            target = local_path_from_url(value)
            if target is not None and not target.exists():
                errors.append(f"{relative}: 내부 링크 없음 {value}")

        for term in EXCLUDED_TERMS:
            if term in raw:
                errors.append(f"{relative}: 제외 표현 포함 {term}")

        if len(description) < 65 or len(description) > 165:
            warnings.append(f"{relative}: meta description 길이 {len(description)}")
        if len(title) > 65:
            warnings.append(f"{relative}: title 길이 {len(title)}")

        titles.append(title)
        descriptions.append(description)
        canonicals.append(canonical)

    duplicates = {
        "titles": [value for value, count in Counter(titles).items() if value and count > 1],
        "descriptions": [value for value, count in Counter(descriptions).items() if value and count > 1],
        "canonicals": [value for value, count in Counter(canonicals).items() if value and count > 1],
    }
    for kind, values in duplicates.items():
        if values:
            errors.append(f"중복 {kind}: {len(values)}")

    result = {
        "files": len(files),
        "branchPages": branch_pages,
        "regionPages": region_pages,
        "primaryMediaPages": primary_media_pages,
        "systemHubPages": system_hub_pages,
        "errors": errors,
        "warnings": warnings,
        "duplicateCounts": {key: len(value) for key, value in duplicates.items()},
    }
    report = REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
