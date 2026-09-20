"""Separate search previews, reader introductions and factual article summaries.

Input is the Step 3 edited manuscript, not the raw ZIP or generated HTML. The
learning topic stays manuscript-specific. Course availability is never inferred
from a manuscript; the visible course answer and FAQ remain authoritative.
"""

from __future__ import annotations

import re

from branch_course_guidance import course_guidance
from branch_manuscript_editorial import (
    AUTHORING, SENTENCE_SPLIT, clean_authoring, other_level_school_names,
    school_pattern,
)


# These nine metadata lists mixed school levels. Preserve the learning subject
# and replace only the list with the student's own school materials.
META_SCHOOL_LISTS = {
    ("산월동", "초등", "수학"): ("월봉초·천곡중 등 학교 자료", "초등학교 학습 자료"),
    ("관교동", "초등", "영어"): ("성리초·성리중 자료", "초등학교 학습 자료"),
    ("삼송", "초등", "영어"): ("신원초·신원중·신원고 자료", "초등학교 학습 자료"),
    ("월계동", "초등", "영어"): ("월봉초·천곡중·월봉중·장덕고 관련", "초등학교 학습 자료 관련"),
    ("이곡동", "초등", "영어"): ("와룡초·성산중·성서고 관련 자료", "초등학교 학습 자료"),
    ("세교", "중등", "수학"): ("문시중·세마중·세교고 관련 평가 자료", "중학교 평가 자료"),
    ("대구 장기동", "중등", "영어"): ("장동초·장기초·성당초·원화중 관련 자료", "중학교 평가 자료"),
    ("수완지구", "중등", "영어"): ("수완중·장덕중·수완고·장덕고 자료", "중학교 평가 자료"),
    ("신가동", "중등", "영어"): ("수완중·장덕중·수완고·장덕고 자료", "중학교 평가 자료"),
}


def sentences(value: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(value.strip()) if s.strip()]


def learning_lead(center: dict, item: dict) -> str:
    """An actual, standalone learning question/action from the edited article.

    Skip the generated school/address context: listing nearby schools is not an
    answer to the reader's learning question. Do not randomly paraphrase copy.
    """
    paragraphs = item["intro"] + [p for s in item["sections"] for p in s["paragraphs"]]
    for paragraph in paragraphs:
        for sentence in sentences(paragraph):
            if not 40 <= len(sentence) <= 150 or item["subject"] not in sentence:
                continue
            if school_pattern(center).search(sentence) or AUTHORING.search(sentence):
                continue
            if re.search(r"안내 주소|상담에서 참고할 학교|재학 학교와 현재 학년|^학생이 실제로 다니는 학교", sentence):
                continue
            if re.match(r"(?:이때|이후|이 과정|이 자료|이를|그다음|따라서|다만|예를 들어)", sentence):
                continue
            if not re.search(r"확인|살피|살펴|살필|비교|점검|질문|구분|준비|정리", sentence):
                continue
            return sentence
    raise ValueError(f"첫 학습 안내를 검토해야 합니다: {item['title']}")


def clean_abstract(center: dict, item: dict) -> str:
    kept = []
    for sentence in sentences(item["abstract"]):
        # Keep the learning explanation, not a stale list of another level's
        # schools or an aside about the original content-generation input.
        if other_level_school_names(center, item["level"], sentence):
            continue
        sentence = clean_authoring(sentence).replace(" तथा ", " 및 ")
        if sentence:
            kept.append(sentence)
    result = " ".join(kept)
    if len(result) < 85 or item["subject"] not in result:
        raise ValueError(f"본문 요약 수동 검토 필요: {item['title']}")
    return result


def topic_summaries(center: dict, item: dict) -> dict[str, str]:
    """Keep the original page focus; align the preview with course caveats."""
    description = item["description"]
    replacement = META_SCHOOL_LISTS.get((item["locality"], item["level"], item["subject"]))
    if replacement:
        old, new = replacement
        if old not in description:
            raise ValueError(f"검토한 메타 문구가 달라졌습니다: {item['title']}")
        description = description.replace(old, new)
    view = course_guidance(center, item["subject"], item["prefix"])
    name = center["routeName"]
    if not view["grades"]:
        # Put unresolved availability first, not after a possibly truncated
        # snippet. Unrecorded is not a declaration that classes are closed.
        description = f"{name} {item['level']} {item['subject']} 개설 여부는 상담 확인이 필요합니다. {description}"
    elif view["pendingGrades"]:
        description += f" {name}의 일부 학년은 조건 확인이 필요합니다."
    else:
        description += f" {name} 안내 학년·수업 조건도 확인하세요."
    return {
        "description": description,
        "abstract": clean_abstract(center, item),
        "lead": learning_lead(center, item),
    }


def center_summaries(center: dict) -> dict[str, str]:
    """Location preview, visit-preparation lead, then broader article abstract.

    These describe visible sections without presenting every grade as open or
    fabricating center-specific teaching outcomes and operating conditions.
    """
    areas = "·".join(center["neighborhoods"][:3]) or center["district"]
    name = center["routeName"]
    views = [course_guidance(center, subject) for subject in ("영어", "수학")]
    scope = " · ".join(f'{view["subject"]} {view["label"]}' for view in views)
    needs_check = any(not view['grades'] or view['pendingGrades'] or view['notes'] for view in views)
    caveat = " 일부 학년·수업 조건은 상담 확인이 필요합니다." if needs_check else " 시간표·등록 가능 여부는 상담에서 확인하세요."
    description = f'{name}은 {center["address"]}에 있습니다. 안내 학년: {scope}. {areas}의 상담 준비를 확인하세요.{caveat}'
    # Keep verified grade details intact; shorten location context, not caveats.
    if len(description) > 165:
        description = f'{name} · {center["address"]}. 안내 학년: {scope}.{caveat}'
    lead = (
        f"{areas}에서 방문 상담을 준비한다면 학생의 학년과 희망 과목부터 확인해 보세요. "
        f"아래에 {name}의 영어·수학 안내 학년과 확인할 수업 조건을 정리했습니다."
    )
    abstract = (
        f'{center["displayName"]}의 주소는 {center["address"]}입니다. '
        "과목별 안내 학년과 별도 확인할 수업 조건, 인근 학교와 동네를 정리합니다. "
        "학생의 최근 풀이와 복습 기록을 준비해 학습관리 방식과 피드백 주기를 질문하는 순서를 안내합니다. "
        "수업 요일·시간표와 신규 등록 가능 여부는 상담에서 확인해야 합니다."
    )
    return {"description": description, "abstract": abstract, "lead": lead}


def validate_summaries(center: dict, summary: dict, item: dict | None = None) -> None:
    if len(set(summary.values())) != 3:
        raise ValueError("메타 설명·본문 요약·첫 소개의 역할이 겹칩니다.")
    for field, value in summary.items():
        if AUTHORING.search(value) or re.search(r"[\u0900-\u097f\u0400-\u04ff]", value):
            raise ValueError(f"{field}: 작성용 표현 또는 외국어 오타")
        if item and other_level_school_names(center, item["level"], value):
            raise ValueError(f"{field}: 다른 학교급의 학교명")
    # Editorial review band, not a claimed search-engine character limit.
    if not 65 <= len(summary["description"]) <= 165:
        raise ValueError(f"설명문 편집 검토 범위 초과: {len(summary['description'])}")
    if item:
        body = " ".join(item["intro"] + [p for s in item["sections"] for p in s["paragraphs"]])
        if summary["lead"] not in body:
            raise ValueError("첫 학습 안내가 실제 본문에 없는 주장입니다.")


def summary_document_errors(document, graph: list[dict], expected: dict) -> list[str]:
    """Check published HTML/schema, not just the functions that generated it."""
    errors = []
    for xpath in ('//meta[@name="description"]/@content', '//meta[@property="og:description"]/@content'):
        if document.xpath(xpath) != [expected["description"]]:
            errors.append("meta/OG 설명문 불일치")
    leads = document.xpath('//p[@class="branch-lead"]')
    if len(leads) != 1 or leads[0].text_content() != expected["lead"]:
        errors.append("첫 학습 안내와 본문 근거 불일치")
    for kind in ("Article", "WebPage"):
        nodes = [node for node in graph if node.get("@type") == kind]
        if len(nodes) != 1 or nodes[0].get("description") != expected["description"]:
            errors.append(f"{kind} description 불일치")
        if kind == "Article" and (not nodes or nodes[0].get("abstract") != expected["abstract"]):
            errors.append("Article abstract와 검토된 본문 요약 불일치")
    return errors
