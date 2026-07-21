from __future__ import annotations

import json
import re
from pathlib import Path


BASE = Path(__file__).with_name("generate_subject_english_pages.py")
HIGH_SCHOOL_SLUG = "고등영어학원"
TODAY = "2026-07-21"


def transformed_generator() -> dict[str, object]:
    """Reuse the validated English-page generator with a separate high-school target."""
    source = BASE.read_text(encoding="utf-8")

    protected = {
        'ENGLISH_ROOT = ROOT / "과목별학원" / "영어학원"':
            'ENGLISH_ROOT = ROOT / "과목별학원" / "__HIGH_SCHOOL_ENGLISH_SLUG__"',
        'encoded_url("과목별학원", "영어학원"':
            'encoded_url("과목별학원", "__HIGH_SCHOOL_ENGLISH_SLUG__"',
        '/과목별학원/영어학원/': '/과목별학원/__HIGH_SCHOOL_ENGLISH_SLUG__/',
        'href="./영어학원/"': 'href="./__HIGH_SCHOOL_ENGLISH_SLUG__/"',
    }
    for old, new in protected.items():
        if old not in source:
            raise ValueError(f"base generator pattern not found: {old}")
        source = source.replace(old, new)

    source = source.replace(
        'REP_DEST = ROOT / "assets" / "representative-english"',
        'REP_DEST = ROOT / "assets" / "representative-highschool-english"',
    )
    source = source.replace("rep-english-", "rep-highschool-english-")
    source = source.replace(
        "/assets/representative-english/",
        "/assets/representative-highschool-english/",
    )
    source = source.replace(
        "wawa-english-academy-20260721",
        "wawa-highschool-english-academy-20260721",
    )

    # Text labels become high-school specific while protected URL slugs stay compact.
    source = source.replace("영어학원", "고등 영어학원")
    source = source.replace("__HIGH_SCHOOL_ENGLISH_SLUG__", HIGH_SCHOOL_SLUG)
    source = source.replace("LOCAL ENGLISH ACADEMY GUIDE", "HIGH SCHOOL ENGLISH LOCAL GUIDE")
    source = source.replace("ENGLISH ACADEMY DIRECTORY", "HIGH SCHOOL ENGLISH DIRECTORY")
    source = source.replace("영어 상담", "고등 영어 상담")
    source = source.replace("영어 수업 가능 학년", "고등 영어 수업 가능 학년")
    source = source.replace("영어 공부법", "고등 영어 공부법")
    source = source.replace("영어 학습관리", "고등 영어 학습관리")
    source = source.replace(
        "초등·중등·고등 고등 영어학원 선택 기준은 같나요?",
        "고등 영어학원은 학년별 선택 기준이 어떻게 다른가요?",
    )
    source = source.replace(
        "초등은 어휘와 문장 읽기, 중등은 문법 적용과 내신, 고등은 독해 근거와 서술형·시험 시간 관리까지 비중이 달라집니다.",
        "고1은 중등 문법과 고등 독해의 연결, 고2는 내신 범위와 지문 분석, 수능 준비 단계는 시간 안에 근거를 찾는 읽기 전략까지 확인하는 것이 좋습니다.",
    )

    namespace: dict[str, object] = {
        "__name__": "subject_highschool_english_generator",
        "__file__": str(BASE),
    }
    exec(compile(source, str(BASE), "exec"), namespace)
    return namespace


def update_subject_hub(namespace: dict[str, object]) -> None:
    root = Path(namespace["ROOT"])
    path = root / "과목별학원" / "index.html"
    source = path.read_text(encoding="utf-8")
    replacement = (
        '<a class="subject-category-card" id="high" data-number="07" '
        'href="./고등영어학원/"><small>HIGH SCHOOL ENGLISH</small>'
        '<h3>고등 영어학원</h3><p>학교별 내신 범위, 어휘·문법 연결, 독해 근거와 '
        '서술형 답안 과정을 371개 동네별 원고에서 확인합니다.</p>'
        '<span class="subject-status">371개 지역 안내 보기 →</span></a>'
    )
    source, count = re.subn(
        r'<(?:article|a) class="subject-category-card" id="high".*?</(?:article|a)>',
        replacement,
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("subject hub high-school card not found")

    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        source,
        re.DOTALL,
    )
    if not match:
        raise ValueError("subject hub JSON-LD not found")
    data = json.loads(match.group(1))
    high_url = namespace["encoded_url"]("과목별학원", HIGH_SCHOOL_SLUG)
    for item in data.get("@graph", []):
        if item.get("@type") == "EducationalOrganization":
            topics = item.setdefault("knowsAbout", [])
            if "고등 영어학원" not in topics:
                topics.append("고등 영어학원")
        if item.get("@type") == "CollectionPage":
            item["dateModified"] = TODAY
            about = item.get("about", [])
            for thing in about:
                if thing.get("name") == "고등학생학원":
                    thing["name"] = "고등 영어학원"
        if item.get("@type") == "ItemList" and str(item.get("@id", "")).endswith("#topics"):
            for list_item in item.get("itemListElement", []):
                thing = list_item.get("item", {})
                if thing.get("name") == "고등학생학원":
                    thing["name"] = "고등 영어학원"
                    thing["url"] = high_url
    source = source[: match.start(1)] + namespace["compact_json"](data) + source[match.end(1) :]
    path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    namespace = transformed_generator()

    original_center = namespace["extract_center_data"]
    original_reviews = namespace["parse_reviews"]
    original_manuscripts = namespace["load_manuscripts"]

    def high_school_reviews(text: str) -> list[dict[str, str]]:
        reviews = original_reviews(text)
        if reviews:
            return reviews
        value = re.sub(r"\s+", " ", text).strip()
        if not value:
            return []
        quoted = re.search(r"[“\"](.+?)[”\"]", value)
        content = quoted.group(1).strip() if quoted else value
        local_match = re.search(r"([^\s,]+(?:동|읍|지구|마을|신도시))\s+고등 영어학원", value)
        local = local_match.group(1) if local_match else "고등 영어"
        return [{"label": f"{local} 상담을 살펴본 학부모 관점", "content": content}]

    def high_school_center(local: str) -> dict[str, object]:
        center = original_center(local)
        high_grades = [grade for grade in center.get("grades", []) if str(grade).startswith("고")]
        center["grades"] = high_grades or ["고등 과정 제공 여부 상담 확인 필요"]
        return center

    def high_school_manuscripts() -> dict[str, dict[str, object]]:
        manuscripts = original_manuscripts()
        endings = [
            "현재 영어 수준과 학교별 내신 대비, 어휘·구문·독해 학습 및 상담 전 점검사항을 안내합니다.",
            "학생의 영어 학습 상태와 내신 범위 대응, 독해·서술형 복습 흐름, 상담 준비 기준을 정리했습니다.",
            "최근 학습자료로 진단할 영역, 내신·모의고사 준비, 주간 복습과 상담 확인사항을 설명합니다.",
        ]
        for local, manuscript in manuscripts.items():
            title = str(manuscript.get("title", f"{local} 고등 영어학원"))
            variant = sum(map(ord, local)) % len(endings)
            openings = [
                f"{title} 상담 전 확인할 고등 영어 학습 기준입니다.",
                f"{title} 선택을 위해 살펴볼 학습·내신 관리 기준입니다.",
                f"{title}에서 확인할 고등 영어 진단과 학습 안내입니다.",
            ]
            manuscript["meta"] = f"{openings[variant]} {endings[variant]}"
        return manuscripts

    def high_school_links(
        local: str,
        index: int,
        order: list[str],
        center_url: str,
    ) -> list[dict[str, str]]:
        encoded_url = namespace["encoded_url"]
        previous_local = order[index - 1] if index > 0 else order[-1]
        next_local = order[index + 1] if index + 1 < len(order) else order[0]
        links = [
            {"name": "고등 영어학원 전체 지역", "url": encoded_url("과목별학원", HIGH_SCHOOL_SLUG)},
            {"name": f"{local} 영어학원", "url": encoded_url("과목별학원", "영어학원", local)},
            {"name": f"{local} 수학학원", "url": encoded_url("과목별학원", "수학학원", local)},
        ]
        if center_url:
            links.append({"name": f"{local} 전국센터 안내", "url": center_url})
        links.extend(
            [
                {"name": "고등학생 영어 공부법", "url": encoded_url("교육정보", "고등학생-공부법")},
                {"name": f"이전 지역 · {previous_local}", "url": encoded_url("과목별학원", HIGH_SCHOOL_SLUG, previous_local)},
                {"name": f"다음 지역 · {next_local}", "url": encoded_url("과목별학원", HIGH_SCHOOL_SLUG, next_local)},
            ]
        )
        return links

    namespace["parse_reviews"] = high_school_reviews
    namespace["load_manuscripts"] = high_school_manuscripts
    namespace["extract_center_data"] = high_school_center
    namespace["internal_links"] = high_school_links
    namespace["update_subject_hub"] = lambda: update_subject_hub(namespace)
    namespace["main"]()


if __name__ == "__main__":
    main()
