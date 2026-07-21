from __future__ import annotations

import json
import re
from pathlib import Path


BASE = Path(__file__).with_name("generate_subject_english_pages.py")
HIGH_SCHOOL_SLUG = "고등수학학원"
HIGH_SCHOOL_ENGLISH_SLUG = "고등영어학원"
TODAY = "2026-07-21"


def transformed_generator() -> dict[str, object]:
    source = BASE.read_text(encoding="utf-8")
    protected = {
        'ENGLISH_ROOT = ROOT / "과목별학원" / "영어학원"':
            'ENGLISH_ROOT = ROOT / "과목별학원" / "__HIGH_SCHOOL_MATH_SLUG__"',
        'encoded_url("과목별학원", "영어학원"':
            'encoded_url("과목별학원", "__HIGH_SCHOOL_MATH_SLUG__"',
        '/과목별학원/영어학원/': '/과목별학원/__HIGH_SCHOOL_MATH_SLUG__/',
        'href="./영어학원/"': 'href="./__HIGH_SCHOOL_MATH_SLUG__/"',
    }
    for old, new in protected.items():
        if old not in source:
            raise ValueError(f"base generator pattern not found: {old}")
        source = source.replace(old, new)

    source = source.replace(
        'REP_DEST = ROOT / "assets" / "representative-english"',
        'REP_DEST = ROOT / "assets" / "representative-highschool-math"',
    )
    source = source.replace("rep-english-", "rep-highschool-math-")
    source = source.replace(
        "/assets/representative-english/",
        "/assets/representative-highschool-math/",
    )
    source = source.replace(
        "wawa-english-academy-20260721",
        "wawa-highschool-math-academy-20260721",
    )

    source = source.replace("영어학원", "고등 수학학원")
    source = source.replace("__HIGH_SCHOOL_MATH_SLUG__", HIGH_SCHOOL_SLUG)
    source = source.replace("영어", "수학")
    source = source.replace("수학 상담", "고등 수학 상담")
    source = source.replace("수학 수업 가능 학년", "고등 수학 수업 가능 학년")
    source = source.replace("수학 공부법", "고등 수학 공부법")
    source = source.replace("LOCAL ENGLISH ACADEMY GUIDE", "HIGH SCHOOL MATH LOCAL GUIDE")
    source = source.replace("ENGLISH ACADEMY DIRECTORY", "HIGH SCHOOL MATH DIRECTORY")
    source = source.replace("english-local-search", "highschool-math-local-search")
    source = source.replace("english-search-count", "highschool-math-search-count")
    source = source.replace("english-review-grid", "math-case-grid")
    source = source.replace("english-review-item", "math-case-item")
    source = source.replace(
        '<link rel="stylesheet" href="/assets/english-academy.css">',
        '<link rel="stylesheet" href="/assets/highschool-math-academy.css">',
    )
    source = source.replace(
        '<body class="math-academy-page english-academy-page">',
        '<body class="math-academy-page highschool-math-academy-page">',
    )

    replacements = [
        ("어휘·문법·독해·서술형", "개념·연산·문장제·서술형"),
        ("어휘, 문법, 독해 근거, 서술형 표현", "개념 이해, 계산 과정, 문장제 조건, 서술형 풀이"),
        ("어휘, 문장 구조, 문법 적용, 독해 근거와 쓰기 과정", "개념 연결, 연산 정확도, 문장제 조건 해석과 풀이 과정"),
        ("수학 어휘·문법 진단", "수학 개념·연산 진단"),
        ("수학 독해·서술형 학습", "수학 문장제·서술형 학습"),
        ("수학 독해 근거 찾기", "수학 문장제 조건 해석"),
        ("수학 어휘 학습", "수학 개념 이해"),
        ("수학 문법 적용", "수학 개념 적용"),
        ("수학 어휘", "수학 개념"),
        ("수학 문법", "수학 연산과 개념 적용"),
        ("수학 독해", "수학 문제 해석"),
        ("문장 구조 이해", "식과 조건 이해"),
        ("문장 안에서의 의미 확인", "개념을 문제에 적용하는 과정 확인"),
        ("현재 읽고 설명하는 과정", "현재 풀이를 설명하는 과정"),
        ("현재 읽고 쓰는 과정", "현재 풀이 과정"),
        ("읽기 전략", "풀이 전략"),
    ]
    for old, new in replacements:
        source = source.replace(old, new)

    namespace: dict[str, object] = {
        "__name__": "subject_highschool_math_generator",
        "__file__": str(BASE),
    }
    exec(compile(source, str(BASE), "exec"), namespace)
    return namespace


def update_subject_hub(namespace: dict[str, object]) -> None:
    root = Path(namespace["ROOT"])
    path = root / "과목별학원" / "index.html"
    source = path.read_text(encoding="utf-8")
    replacement = (
        '<a class="subject-category-card" id="high-math" data-number="08" '
        'href="./고등수학학원/"><small>HIGH SCHOOL MATH</small>'
        '<h3>고등 수학학원</h3><p>개념 연결, 계산 정확도, 문장제 조건 해석과 '
        '서술형 풀이·오답 재학습을 371개 동네별 원고에서 확인합니다.</p>'
        '<span class="subject-status">371개 지역 안내 보기 →</span></a>'
    )
    pattern = r'<(?:article|a) class="subject-category-card" id="high-math".*?</(?:article|a)>'
    if re.search(pattern, source, re.DOTALL):
        source = re.sub(pattern, replacement, source, count=1, flags=re.DOTALL)
    else:
        high_card = re.search(
            r'<(?:article|a) class="subject-category-card" id="high".*?</(?:article|a)>',
            source,
            re.DOTALL,
        )
        if not high_card:
            raise ValueError("subject hub high-school English card not found")
        source = source[: high_card.end()] + "\n          " + replacement + source[high_card.end() :]

    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
    if not match:
        raise ValueError("subject hub JSON-LD not found")
    data = json.loads(match.group(1))
    math_url = namespace["encoded_url"]("과목별학원", HIGH_SCHOOL_SLUG)
    for item in data.get("@graph", []):
        if item.get("@type") == "EducationalOrganization":
            topics = item.setdefault("knowsAbout", [])
            if "고등 수학학원" not in topics:
                topics.append("고등 수학학원")
        if item.get("@type") == "CollectionPage":
            item["dateModified"] = TODAY
            about = item.setdefault("about", [])
            if not any(thing.get("name") == "고등 수학학원" for thing in about):
                about.append({"@type": "Thing", "name": "고등 수학학원"})
        if item.get("@type") == "ItemList" and str(item.get("@id", "")).endswith("#topics"):
            entries = item.setdefault("itemListElement", [])
            target = next((entry for entry in entries if entry.get("item", {}).get("name") == "고등 수학학원"), None)
            if target is None:
                target = {"@type": "ListItem", "position": len(entries) + 1, "item": {"@type": "Thing"}}
                entries.append(target)
            target["item"].update({"name": "고등 수학학원", "url": math_url})
            for position, entry in enumerate(entries, start=1):
                entry["position"] = position
            item["numberOfItems"] = len(entries)
    source = source[: match.start(1)] + namespace["compact_json"](data) + source[match.end(1) :]
    path.write_text(source, encoding="utf-8", newline="\n")


def update_highschool_english_crosslinks(namespace: dict[str, object], order: list[str]) -> None:
    root = Path(namespace["ROOT"])
    encoded_url = namespace["encoded_url"]
    compact_json = namespace["compact_json"]
    for local in order:
        path = root / "과목별학원" / HIGH_SCHOOL_ENGLISH_SLUG / local / "index.html"
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        math_url = encoded_url("과목별학원", HIGH_SCHOOL_SLUG, local)
        if f'href="{math_url}"' not in source:
            container = re.search(r'<div class="math-links">(.*?)</div>', source, re.DOTALL)
            if not container:
                raise ValueError(f"related link container not found: {local}")
            addition = f'<a href="{math_url}">{local} 고등 수학학원</a>'
            source = source[: container.end(1)] + addition + source[container.end(1) :]

        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
        data = json.loads(match.group(1))
        for item in data.get("@graph", []):
            if item.get("@type") == "ItemList" and str(item.get("@id", "")).endswith("#links"):
                entries = item.setdefault("itemListElement", [])
                if not any(entry.get("url") == math_url for entry in entries):
                    entries.append({"@type": "ListItem", "position": len(entries) + 1, "name": f"{local} 고등 수학학원", "url": math_url})
                for position, entry in enumerate(entries, start=1):
                    entry["position"] = position
        source = source[: match.start(1)] + compact_json(data) + source[match.end(1) :]
        path.write_text(source, encoding="utf-8", newline="\n")


def polish_highschool_math_hub(namespace: dict[str, object]) -> None:
    root = Path(namespace["ROOT"])
    path = root / "과목별학원" / HIGH_SCHOOL_SLUG / "index.html"
    source = path.read_text(encoding="utf-8")
    faq = [
        {
            "name": "동네별 고등 수학학원 페이지에서는 무엇을 확인할 수 있나요?",
            "text": "지역별 원고와 제공된 센터 정보를 바탕으로 학생의 개념 이해, 계산 정확도, 문장제 조건 해석, 서술형 풀이와 오답 재학습 기준을 확인할 수 있습니다.",
        },
        {
            "name": "고등 수학학원 상담에는 어떤 자료를 준비하면 좋나요?",
            "text": "최근 수학 시험지와 풀이 흔적, 학교 시험 범위표, 교과서·프린트, 사용 교재와 일주일 학습 시간표를 준비하면 취약 단원과 복습 계획을 구체적으로 살펴볼 수 있습니다.",
        },
        {
            "name": "고등 수학 수업은 선행 진도만 빠르면 좋은가요?",
            "text": "선행 범위보다 배운 개념을 설명하고 조건을 식으로 옮기며 틀린 문제를 일정 뒤 다시 풀 수 있는지를 함께 봐야 합니다. 현재 학년의 내신 범위와 학생의 복습 가능 시간을 기준으로 진도를 정하는 편이 좋습니다.",
        },
    ]
    replacements = {
        "수학는 현재 풀이를 설명하는 과정에서 출발합니다": "고등 수학은 현재 풀이를 설명하는 과정에서 출발합니다",
        "학년보다 앞선 진도만 묻기보다 어휘 누적, 식과 조건 이해, 독해 근거와 오답 재도전 방식을 함께 확인하세요.": "학년보다 앞선 진도만 묻기보다 개념 연결, 계산 정확도, 조건 해석과 오답 재도전 방식을 함께 확인하세요.",
        "<span>어휘</span><span>독해</span><span>서술형</span>": "<span>개념</span><span>문장제</span><span>재풀이</span>",
        "<div><dt>어휘</dt><dd>누적 암기와 개념을 문제에 적용하는 과정 확인</dd></div>": "<div><dt>개념</dt><dd>교과 개념과 공식의 적용 조건 확인</dd></div>",
        "<div><dt>문법</dt><dd>개념 설명에서 문제 적용까지의 연결</dd></div>": "<div><dt>연산</dt><dd>풀이 과정의 계산 정확도와 검산</dd></div>",
        "<div><dt>독해</dt><dd>답의 근거와 문단 관계 표시</dd></div>": "<div><dt>문장제</dt><dd>조건을 식으로 옮기는 해석 과정</dd></div>",
    }
    for old, new in replacements.items():
        if old not in source:
            raise ValueError(f"high-school math hub phrase not found: {old}")
        source = source.replace(old, new)

    faq_markup = "".join(
        f'<details class="math-faq-item"{" open" if index == 0 else ""}><summary>{item["name"]}</summary><p>{item["text"]}</p></details>'
        for index, item in enumerate(faq)
    )
    source, count = re.subn(
        r'(<div class="math-faq-list">).*?(</div></div></section>)',
        lambda match: match.group(1) + faq_markup + match.group(2),
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("high-school math hub FAQ markup not found")

    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
    data = json.loads(match.group(1))
    for item in data.get("@graph", []):
        if item.get("@type") == "FAQPage":
            item["mainEntity"] = [
                {
                    "@type": "Question",
                    "name": entry["name"],
                    "acceptedAnswer": {"@type": "Answer", "text": entry["text"]},
                }
                for entry in faq
            ]
    source = source[: match.start(1)] + namespace["compact_json"](data) + source[match.end(1) :]
    path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    namespace = transformed_generator()
    original_center = namespace["extract_center_data"]
    original_reviews = namespace["parse_reviews"]
    original_manuscripts = namespace["load_manuscripts"]
    original_naturalize = namespace["naturalize_text"]

    def high_school_reviews(text: str) -> list[dict[str, str]]:
        reviews = original_reviews(text)
        if reviews:
            return reviews
        value = re.sub(r"\s+", " ", text).strip()
        if not value:
            return []
        quoted = re.search(r"[“\"](.+?)[”\"]", value)
        content = quoted.group(1).strip() if quoted else value
        local_match = re.search(r"([^\s,]+(?:동|읍|지구|마을|신도시))(?:에서|의)?\s+고등 수학학원", value)
        local = local_match.group(1) if local_match else "고등 수학"
        return [{"label": f"{local} 상담을 살펴본 학부모 관점", "content": content}]

    def high_school_naturalize(text: str, local: str) -> str:
        value = original_naturalize(text, local)
        value = re.sub(
            r"(?:학원\s+)?주소는\s+(.+?)로 제공되며",
            r"제공 자료에 기재된 주소는 \1이며",
            value,
        )
        value = re.sub(r"(\d+(?:층|호))로 제공", r"\1으로 제공", value)
        return value

    def high_school_center(local: str) -> dict[str, object]:
        center = original_center(local)
        high_grades = [grade for grade in center.get("grades", []) if str(grade).startswith("고")]
        center["grades"] = high_grades or ["고등 과정 제공 여부 상담 확인 필요"]
        return center

    def high_school_manuscripts() -> dict[str, dict[str, object]]:
        manuscripts = original_manuscripts()
        endings = [
            "현재 개념 이해와 계산 정확도, 학교별 내신 대비, 문장제·서술형 및 상담 전 점검사항을 안내합니다.",
            "학생의 수학 학습 상태와 내신 범위 대응, 풀이 기록·오답 재학습, 상담 준비 기준을 정리했습니다.",
            "최근 시험지로 진단할 영역, 내신·모의고사 준비, 주간 복습과 상담 확인사항을 설명합니다.",
        ]
        for local, manuscript in manuscripts.items():
            title = str(manuscript.get("title", f"{local} 고등 수학학원"))
            variant = sum(map(ord, local)) % len(endings)
            openings = [
                f"{title} 상담 전 확인할 고등 수학 학습 기준입니다.",
                f"{title} 선택을 위해 살펴볼 학습·내신 관리 기준입니다.",
                f"{title}에서 확인할 고등 수학 진단과 학습 안내입니다.",
            ]
            manuscript["meta"] = f"{openings[variant]} {endings[variant]}"
        return manuscripts

    def high_school_links(local: str, index: int, order: list[str], center_url: str) -> list[dict[str, str]]:
        encoded_url = namespace["encoded_url"]
        previous_local = order[index - 1] if index > 0 else order[-1]
        next_local = order[index + 1] if index + 1 < len(order) else order[0]
        links = [
            {"name": "고등 수학학원 전체 지역", "url": encoded_url("과목별학원", HIGH_SCHOOL_SLUG)},
            {"name": f"{local} 수학학원", "url": encoded_url("과목별학원", "수학학원", local)},
            {"name": f"{local} 고등 영어학원", "url": encoded_url("과목별학원", HIGH_SCHOOL_ENGLISH_SLUG, local)},
        ]
        if center_url:
            links.append({"name": f"{local} 전국센터 안내", "url": center_url})
        links.extend([
            {"name": "고등학생 수학 공부법", "url": encoded_url("교육정보", "고등학생-공부법")},
            {"name": f"이전 지역 · {previous_local}", "url": encoded_url("과목별학원", HIGH_SCHOOL_SLUG, previous_local)},
            {"name": f"다음 지역 · {next_local}", "url": encoded_url("과목별학원", HIGH_SCHOOL_SLUG, next_local)},
        ])
        return links

    namespace["parse_reviews"] = high_school_reviews
    namespace["naturalize_text"] = high_school_naturalize
    namespace["load_manuscripts"] = high_school_manuscripts
    namespace["extract_center_data"] = high_school_center
    namespace["internal_links"] = high_school_links
    namespace["update_subject_hub"] = lambda: update_subject_hub(namespace)
    namespace["main"]()

    order, _ = namespace["ordered_locals_and_directory"]()
    polish_highschool_math_hub(namespace)
    update_highschool_english_crosslinks(namespace, order)


if __name__ == "__main__":
    main()
