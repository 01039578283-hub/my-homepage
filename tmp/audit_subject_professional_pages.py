from __future__ import annotations

from collections import Counter, defaultdict
import html
import itertools
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_subject_combined_pages as base_audit
import generate_subject_professional_pages as generator


ROOT = generator.ROOT
BAD_TERMS = (
    "D열",
    "구조화 데이터",
    "검색 의도",
    "질문 목록가",
    "학원로",
    "수업학교",
    "정보성 원고",
    "원고 형태",
    "학부모라면 학부모가",
    "관리 관리",
    "학생 학생",
    "상담 상담",
    "관리이",
    "임의의 학교명",
    "먼저 확인할 필요",
)

ADMIN_PATTERN = re.compile(
    r"(?:학원)?(?:매출관리|창업|전자계약|미납관리|회원관리|고객관리|문자발송|보안관리|출입관리|"
    r"운영자|관리프로그램|관리앱|온라인등록|상담관리|상담직원|데스크|행정|직원|원장|공지|"
    r"소식|알림톡|결제관리|수납관리|수강생관리|문서관리|안전관리|청결관리)"
)

GRAMMAR_PATTERN = re.compile(
    r"학부모라면\s+학부모가|학생\s+학생|상담\s+상담|관리\s+관리|확인\s+확인|"
    r"학교을|학원를|자료을|영어을|수학를|관리을|상담를|수업를|학생를|"
    r"태도가 확인할 필요|과정이 확인할 필요|훈련이 확인할 필요|연습이 확인할 필요|"
    r"시간이 확인할 필요|필요한 유형 학생에게|수업 가능 제공된 학교 자료"
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def graph(source: str) -> list[dict[str, object]]:
    match = re.search(
        r'<script\s+type="application/ld\+json">(.*?)</script>',
        source,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []
    value = json.loads(match.group(1))
    return value.get("@graph", []) if isinstance(value, dict) else []


def compact_signature(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def by_type(nodes: list[dict[str, object]], name: str) -> dict[str, object]:
    for node in nodes:
        value = node.get("@type")
        if value == name or isinstance(value, list) and name in value:
            return node
    return {}


def extract_region(source: str, pattern: str) -> str:
    match = re.search(pattern, source, re.DOTALL | re.IGNORECASE)
    return clean(match.group(1)) if match else ""


def normalize_text(value: str, local: str, label: str) -> str:
    value = value.replace(local, "지역명").replace(label, "전문학원")
    value = value.replace(label.replace(" ", ""), "전문학원")
    return re.sub(r"\s+", " ", value).strip().lower()


def ngrams(value: str, size: int = 5) -> set[tuple[str, ...]]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", value)
    if len(tokens) < size:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def similarity_metrics(values: list[tuple[str, str]], label: str) -> dict[str, float | int]:
    sets = [ngrams(normalize_text(value, local, label)) for local, value in values]
    scores: list[float] = []
    for left, right in itertools.combinations(sets, 2):
        union = len(left | right)
        scores.append(len(left & right) / union if union else 0.0)
    return {
        "pairs": len(scores),
        "mean": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "p95": round(percentile(scores, 0.95), 4),
        "max": round(max(scores, default=0.0), 4),
        "pairs_ge_0_5": sum(score >= 0.5 for score in scores),
        "rate_ge_0_5": round(sum(score >= 0.5 for score in scores) / len(scores), 6) if scores else 0.0,
    }


def exact_stats(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return {
        "values": len(values),
        "unique": len(counts),
        "duplicate_groups": sum(count > 1 for count in counts.values()),
        "duplicate_pages": sum(count for count in counts.values() if count > 1),
        "max_frequency": max(counts.values(), default=0),
    }


def main() -> None:
    generator.transformed_namespace = generator.shared.transformed_namespace
    generator.EXPECTED_MASTER_ITEMS = len(generator.ALL_TOPICS)
    base_audit.generator = generator
    base_audit.ROOT = ROOT
    base_audit.ERRORS.clear()
    base_audit.main()

    errors: list[str] = []
    report: dict[str, object] = {"categories": {}}
    organization_signatures: dict[str, set[str]] = defaultdict(set)
    business_signatures: dict[str, set[str]] = defaultdict(set)
    for config in generator.CATEGORIES:
        namespace = generator.shared.transformed_namespace(config)
        generator.configure_namespace(namespace, config)
        manuscripts = namespace["load_manuscripts"]()
        order, _ = namespace["ordered_locals_and_directory"]()
        bodies: list[tuple[str, str]] = []
        faqs: list[str] = []
        reviews: list[str] = []
        summaries: list[str] = []
        fact_checked = 0
        bad_term_hits = Counter()

        for local in order:
            path = ROOT / "과목별학원" / str(config["slug"]) / local / "index.html"
            source = path.read_text(encoding="utf-8")
            nodes = graph(source)
            education = by_type(nodes, "EducationalOrganization")
            business = by_type(nodes, "LocalBusiness")
            service = by_type(nodes, "Service")
            article = by_type(nodes, "Article")
            center = namespace["extract_center_data"](local)

            expected = {
                "name": center["organization_name"],
                "telephone": center["telephone"],
                "address": center["address"],
                "areaServed": {"@type": "Place", "name": local},
                "openingHoursSpecification": center["opening_hours"],
                "identifier": center["identifier"],
            }
            for key, value in expected.items():
                if education.get(key) != value:
                    errors.append(f"{config['slug']}/{local}: EducationalOrganization.{key} mismatch")
                if business.get(key) != value:
                    errors.append(f"{config['slug']}/{local}: LocalBusiness.{key} mismatch")
            for key in ("alternateName", "description", "educationalLevel", "teaches", "knowsAbout", "makesOffer"):
                if key in education:
                    errors.append(f"{config['slug']}/{local}: variable EducationalOrganization.{key}")
                if key in business:
                    errors.append(f"{config['slug']}/{local}: variable LocalBusiness.{key}")
            organization_signatures[str(education.get("@id", ""))].add(compact_signature(education))
            business_signatures[str(business.get("@id", ""))].add(compact_signature(business))

            offers = service.get("makesOffer", [])
            if center["tuition_url"]:
                if not offers or offers[0].get("url") != center["tuition_url"]:
                    errors.append(f"{config['slug']}/{local}: Service tuition offer mismatch")
            elif offers:
                errors.append(f"{config['slug']}/{local}: unexpected Service tuition offer")
            if service.get("serviceType") != config["label"]:
                errors.append(f"{config['slug']}/{local}: Service.serviceType mismatch")
            if not article.get("about") or not article.get("mentions") or not article.get("hasPart"):
                errors.append(f"{config['slug']}/{local}: Article entity links missing")
            verified_grades = [str(item) for item in center.get("verified_grades", [])]
            expected_audience = " · ".join(verified_grades)
            for node_name, node in (("Article", article), ("Service", service)):
                audience = node.get("audience")
                if verified_grades:
                    if not isinstance(audience, dict) or audience.get("audienceType") != expected_audience:
                        errors.append(f"{config['slug']}/{local}: {node_name}.audience mismatch")
                elif audience:
                    errors.append(f"{config['slug']}/{local}: unexpected {node_name}.audience")
            fact_checked += 1

            image_tags = re.findall(r"<img\b[^>]*>", source, re.IGNORECASE)
            if len(image_tags) < 3:
                errors.append(f"{config['slug']}/{local}: image count={len(image_tags)}")
            else:
                if 'style="display:none;"' not in image_tags[0] or 'loading="lazy"' in image_tags[0]:
                    errors.append(f"{config['slug']}/{local}: representative image attributes")
                if str(center["body_image"]) not in image_tags[1]:
                    errors.append(f"{config['slug']}/{local}: body image mismatch")
                if str(center["map_image"]) not in image_tags[2]:
                    errors.append(f"{config['slug']}/{local}: map image mismatch")

            for term in BAD_TERMS:
                if term in source:
                    bad_term_hits[term] += 1
            if re.search(r"(?<![가-힣])원고(?![가-힣])", clean(source)):
                bad_term_hits["standalone 원고"] += 1

            manuscript = manuscripts[local]
            manuscript_text = " ".join([
                *[str(item) for item in manuscript["intro"]],
                str(manuscript.get("meta", "")),
                str(manuscript.get("summary", "")),
                str(manuscript.get("answer_heading", "")),
                str(manuscript.get("answer_text", "")),
                *[
                    str(item)
                    for heading, paragraphs in manuscript["sections"]
                    for item in (heading, *paragraphs)
                ],
                *[f"{item['question']} {item['answer']}" for item in manuscript["faqs"]],
                *[f"{item.get('label', '')} {item['content']}" for item in manuscript["reviews"]],
            ])
            explicit_grades = {
                generator.canonical_grade(match.group("level"), match.group("number"))
                for match in generator.GRADE_PATTERN.finditer(manuscript_text)
            }
            if explicit_grades - set(verified_grades):
                errors.append(
                    f"{config['slug']}/{local}: unsupported grade claims "
                    f"{sorted(explicit_grades - set(verified_grades))}"
                )
            title_question_count = sum(
                str(manuscript["title"]) in str(item["question"])
                for item in manuscript["faqs"]
            )
            if not 1 <= title_question_count <= 2:
                errors.append(f"{config['slug']}/{local}: FAQ title questions={title_question_count}")
            if ADMIN_PATTERN.search(manuscript_text):
                errors.append(f"{config['slug']}/{local}: administrative keyword remains")
            remaining_context_terms = [
                term for term in generator.CONTEXT_TERM_REPLACEMENTS if term in manuscript_text
            ]
            if remaining_context_terms:
                errors.append(
                    f"{config['slug']}/{local}: unsupported operation terms {remaining_context_terms[:3]}"
                )
            grammar_values = [
                *[str(item) for item in manuscript["intro"]],
                str(manuscript.get("meta", "")),
                str(manuscript.get("summary", "")),
                str(manuscript.get("answer_heading", "")),
                str(manuscript.get("answer_text", "")),
                *[
                    str(item)
                    for heading, paragraphs in manuscript["sections"]
                    for item in (heading, *paragraphs)
                ],
                *[str(item["question"]) for item in manuscript["faqs"]],
                *[str(item["answer"]) for item in manuscript["faqs"]],
                *[str(item.get("label", "")) for item in manuscript["reviews"]],
                *[str(item["content"]) for item in manuscript["reviews"]],
            ]
            grammar_match = next(
                (match for value in grammar_values if (match := GRAMMAR_PATTERN.search(value))),
                None,
            )
            if grammar_match:
                errors.append(f"{config['slug']}/{local}: grammar residue {grammar_match.group(0)!r}")
            if config["focus"] in {"math", "english"}:
                review_text = " ".join(
                    f"{item.get('label', '')} {item['content']}" for item in manuscript["reviews"]
                )
                if "두 과목의 학습 흐름" in review_text:
                    errors.append(f"{config['slug']}/{local}: single-subject review label")
            if not 160 <= len(str(manuscript["summary"])) <= 320:
                errors.append(f"{config['slug']}/{local}: summary length={len(str(manuscript['summary']))}")
            body_title_count = " ".join(
                [*[str(item) for item in manuscript["intro"]], *[str(item) for section in manuscript["sections"] for item in (section[0], *section[1])]]
            ).count(str(manuscript["title"]))
            if body_title_count > 6:
                errors.append(f"{config['slug']}/{local}: body full-title count={body_title_count}")
            body = " ".join([
                *[str(item) for item in manuscript["intro"]],
                *[
                    str(item)
                    for heading, paragraphs in manuscript["sections"]
                    for item in (heading, *paragraphs)
                ],
            ])
            bodies.append((local, normalize_text(body, local, str(config["label"]))))
            faqs.append(normalize_text(" ".join(f"{item['question']} {item['answer']}" for item in manuscript["faqs"]), local, str(config["label"])))
            reviews.append(normalize_text(" ".join(item["content"] for item in manuscript["reviews"]), local, str(config["label"])))
            summaries.append(normalize_text(str(manuscript["summary"]), local, str(config["label"])))

        if bad_term_hits:
            errors.append(f"{config['slug']}: production terms {dict(bad_term_hits)}")

        report["categories"][str(config["slug"])] = {
            "fact_pages_checked": fact_checked,
            "bad_term_hits": dict(bad_term_hits),
            "exact_body": exact_stats([value for _, value in bodies]),
            "exact_faq": exact_stats(faqs),
            "exact_reviews": exact_stats(reviews),
            "exact_summary": exact_stats(summaries),
            "body_5gram_jaccard": similarity_metrics(bodies, str(config["label"])),
        }

    unstable_organizations = {key: len(values) for key, values in organization_signatures.items() if key and len(values) > 1}
    unstable_businesses = {key: len(values) for key, values in business_signatures.items() if key and len(values) > 1}
    if unstable_organizations:
        errors.append(f"EducationalOrganization identity variation: {len(unstable_organizations)}")
    if unstable_businesses:
        errors.append(f"LocalBusiness identity variation: {len(unstable_businesses)}")
    report["entity_identity"] = {
        "organization_ids": len(organization_signatures),
        "unstable_organizations": len(unstable_organizations),
        "business_ids": len(business_signatures),
        "unstable_businesses": len(unstable_businesses),
    }
    report["errors"] = len(errors)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        print("\n".join(errors[:200]), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
