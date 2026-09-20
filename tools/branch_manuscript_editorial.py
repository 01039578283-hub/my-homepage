"""Reviewed, reproducible body-only edits over the immutable ZIP manuscripts.

Keep useful original explanations. Remove authoring instructions, use only the
linked center's same-level school list, and rewrite specifically reviewed
off-subject examples. This does not invent branch operations or outcomes.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

CORRECTIONS = Path(__file__).parent / "data/branch-topic-pages/editorial-corrections.json"
AUTHORING = re.compile(
    r"원고\s*(?:참고|작성)|(?:참고|보조|제공된|입력된)\s*(?:과목\s*)?키워드|"
    r"키워드.{0,18}(?:제시|제공|입력)|(?:제공된|입력된)\s*(?:참고\s*)?소재|"
    r"(?:제공된|주어진)\s*(?:(?:학습|보조)\s*)?주제|참고 소재|보조 위치|입력 자료|입력된 학교|"
    r"(?:제공된|입력에).{0,18}키워드|영어.{0,5}수학이라는.{0,5}키워드|이 페이지의 키워드|"
    r"제공된 영어.{0,5}수학.{0,5}(?:소재|관심사)|보조 소재|"
    r"(?:입력의|입력으로|입력된).{0,30}(?:소재|확인|키워드)|학원매출관리|"
    r"제공된.{0,16}소재"
)
SCHOOL_SOURCE = re.compile(r"(?:제공된|입력된|제공|입력|자료의|자료에|자료에는).{0,10}(?:학교|수업학교)|(?:학교|수업학교)\s*(?:정보|목록|명칭|명|표기)")
ADDRESS_SOURCE = re.compile(r"보조\s*(?:위치|주소)|(?:제공된|입력된|제공|자료의|자료에).{0,6}(?:주소|위치|소재지)|위치 자료로 제공된|제공된.{0,65}(?:주소 표기|학습코칭학원 표기)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
PREP = {
    ("초등", "수학"): "최근 수학 공책과 학교 학습지에서 계산한 줄과 문제를 읽고 표시한 부분",
    ("초등", "영어"): "현재 읽는 영어책과 학교 활동지에서 혼자 읽거나 써 본 부분",
    ("중등", "수학"): "학교에서 받은 평가 범위와 최근 수학 시험지의 풀이 과정",
    ("중등", "영어"): "교과서 학습 범위와 영어 학습지, 직접 쓴 서술형 답안",
    ("고등", "수학"): "현재 이수하는 수학 과목과 학교 평가 안내, 해설을 보기 전의 풀이",
    ("고등", "영어"): "학교 영어 평가 범위와 수업 자료, 지문 근거를 표시한 답안",
}


@lru_cache(maxsize=1)
def corrections() -> dict:
    data = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    return {tuple(row["key"]): row for row in data["pages"]}


def object_form(text: str) -> str:
    last = ord(text[-1])
    return text + ("을" if 0xAC00 <= last <= 0xD7A3 and (last - 0xAC00) % 28 else "를")


def school_aliases(school: str) -> set[str]:
    values = {school}
    for city in ("서울", "대구", "광주", "대전", "부산", "인천", "울산", "포항", "원주", "용인"):
        if school.startswith(city) and len(school[len(city):]) >= 5:
            values.add(school[len(city):])
    for value in list(values):
        for full, short in (("초등학교", "초"), ("중학교", "중"), ("고등학교", "고")):
            if value.endswith(full):
                values.add(value[:-len(full)] + short)
    values.update(v.replace("여자", "여").replace("남자", "남") for v in list(values))
    return {v for v in values if len(v) >= 3}


@lru_cache(maxsize=256)
def _school_pattern(names: tuple[str, ...]) -> re.Pattern:
    aliases = {a for name in names for a in school_aliases(name)}
    # Explicit name matching avoids deleting 발표 원고, 신원고, 학원고객관리,
    # mathematical input/output, or ordinary study "keywords".
    return re.compile(r"(?<![가-힣A-Za-z])(?:" + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r")(?=[^가-힣A-Za-z]|[은는이가의를와과에처럼등학라로도만을부])") if aliases else re.compile(r"(?!)")


def school_pattern(center: dict) -> re.Pattern:
    return _school_pattern(tuple(name for schools in center["schools"].values() for name in schools))


def other_level_school_names(center: dict, level: str, text: str) -> set[str]:
    allowed = {alias for name in center["schools"].get(level, []) for alias in school_aliases(name)}
    other = tuple(name for school_level, names in center["schools"].items() if school_level != level for name in names)
    return {match.group() for match in _school_pattern(other).finditer(text) if match.group() not in allowed}


def school_context(center: dict, item: dict, include_prep: bool = True) -> str:
    names = center["schools"].get(item["level"], [])
    # Prefer full names already present in the verified manifest, not guessed
    # expansions of ambiguous abbreviations.
    full = [name for name in names if name.endswith("학교")]
    chosen = (full or names)[:5]
    prep = PREP[(item["level"], item["subject"])]
    if chosen:
        listed = ", ".join(chosen) + (" 등" if len(full or names) > len(chosen) else "")
        first = f'{center["routeName"]}의 {item["level"]} 상담에서 참고할 학교는 {listed}입니다.'
        return first + (f' 학생이 실제로 다니는 학교를 알려주고, {object_form(prep)} 함께 준비해 주세요.' if include_prep else "")
    return f'{item["locality"]} {item["level"]} {item["subject"]} 상담에서는 재학 학교와 현재 학년을 먼저 알려주세요. {object_form(prep)} 준비하면 학습 범위를 구체적으로 이야기할 수 있습니다.'


def address_context(center: dict) -> str:
    return f'{center["displayName"]}의 안내 주소는 {center["address"]}입니다. 방문 전 상담 장소와 입실 방법을 확인하고, 학생의 출발 장소에서 실제 이동 시간을 살펴보세요.'


def clean_authoring(paragraph: str) -> str:
    sentences = []
    for sentence in SENTENCE_SPLIT.split(paragraph):
        if AUTHORING.search(sentence):
            continue
        # These sentences describe limitations of a manuscript-writing input,
        # not customer-facing uncertainty. Operational conditions remain in the
        # verified first answer and course FAQ; no availability is inferred.
        if re.search(r"제공(?:된)?\s*(?:정보|자료|내용|사실).{0,35}(?:없|알 수|판단|확인되지|단정)", sentence):
            continue
        sentence = re.sub(r"(?:제공된|입력된)\s+(?=(?:학교|수업학교|학습|과목|수업|주소|지역|위치))", "", sentence)
        sentence = sentence.replace("보조 키워드", "안내 표현").replace("학원데스크", "상담 창구")
        sentence = sentence.replace("이 키워드만으로", "명칭만으로").replace("제공된 자료 안에서", "현재 학습 자료에서")
        sentences.append(sentence)
    if not sentences:
        return ""
    result = " ".join(sentences).strip()
    # Once an editorial aside is removed, its contrastive lead-in is needless.
    if len(sentences) < len(SENTENCE_SPLIT.split(paragraph)):
        result = re.sub(r"^(?:다만|그러나|하지만)\s+", "", result)
    return result


def apply_correction(item: dict, correction: dict, events: list) -> None:
    pattern = re.compile(correction["pattern"])
    theme = correction["heading"]
    matches = [(i, len(pattern.findall(s["heading"] + " ".join(s["paragraphs"])))) for i, s in enumerate(item["sections"])]
    primary = max(matches, key=lambda pair: pair[1])[0]
    if not matches[primary][1]:
        raise ValueError(f'검토한 교정 대상이 원고에서 사라짐: {item["title"]}')
    item["sections"][primary] = {"heading": theme, "paragraphs": correction["paragraphs"][:], "_reviewed": True}
    for i, section in enumerate(item["sections"]):
        if i == primary:
            continue
        if pattern.search(section["heading"]):
            section["heading"] = "최근 학습 기록에서 다음 복습을 정하는 방법"
        result = []
        for p in section["paragraphs"]:
            retained = " ".join(s for s in SENTENCE_SPLIT.split(p) if not pattern.search(s))
            if retained:
                result.append(retained)
        section["paragraphs"] = result
    item["intro"] = [
        f'{item["locality"]}에서 {item["level"]} {item["subject"]} 수업을 알아본다면 {correction["focus"]}부터 살펴보세요. 최근 학습 자료를 가져와 혼자 해결한 부분과 도움이 필요했던 부분을 나누어 상담할 수 있습니다.'
        if pattern.search(p) else p for p in item["intro"]
    ]
    replacement_count = 0
    for index, faq in enumerate(item["faq"]):
        if pattern.search(faq["question"] + faq["answer"]):
            alternatives = [
                correction["faq"],
                {"question": "상담에 어떤 학습 기록을 가져가면 좋을까요?", "answer": f'{object_form(PREP[(item["level"], item["subject"])])} 준비해 주세요. 정답을 보고 고친 기록과 혼자 처음 해 본 기록을 나누면 어떤 설명이 필요한지 구체적으로 질문할 수 있습니다.'},
                {"question": "설명을 듣고 맞힌 답도 복습할 필요가 있나요?", "answer": "도움을 받고 해결한 내용은 표시해 두고 이후 답을 보지 않은 상태에서 다시 해 보세요. 여전히 막힌 부분을 다음 질문으로 남기면 이해한 내용과 더 연습할 내용을 나눌 수 있습니다."},
                {"question": "진도를 늘릴지 복습을 이어갈지 무엇으로 정하나요?", "answer": "최근 배운 내용을 혼자 설명하고 적용한 기록을 기준으로 상담해 보세요. 과제를 마친 양만으로 정하지 말고 반복해서 도움이 필요한 부분과 학생의 실제 공부 시간을 함께 확인하는 편이 좋습니다."},
            ]
            item["faq"][index] = copy.deepcopy(alternatives[replacement_count])
            replacement_count += 1
    if any(pattern.search(p) for p in item["example"]):
        item["example"] = [f'※ {item["title"]} 상담을 준비하는 가상 상황입니다. 보호자가 아이의 최근 학습 자료에서 {object_form(correction["focus"])} 확인해 보려 합니다. 답을 대신 고치기 전에 아이가 혼자 해 본 기록과 도움을 받은 기록을 나누어 가져갈 생각입니다. 상담에서는 처음 연습할 내용과 집에서 다시 확인할 방법을 질문하고, 안내받은 계획이 아이의 일정에 맞는지 살펴보려 합니다.']
    if pattern.search(item["description"]):
        item["description"] = f'{item["locality"]} {item["level"]} {item["subject"]} 상담 전 {object_form(correction["focus"])} 확인하는 방법을 안내합니다. 최근 풀이와 학교 자료를 준비하고, 복습 뒤 혼자 해결하는 과정과 피드백 질문을 구체적으로 살펴보세요.'
    if pattern.search(item["abstract"]):
        item["abstract"] = f'{item["title"]}을 알아보는 보호자를 위해 {object_form(correction["focus"])} 점검하는 순서를 설명합니다. 현재 배운 내용에서 학생의 이해를 확인하고, 학교 학습 자료와 복습 기록을 상담 질문으로 연결합니다.'
    events.append({"kind": "reviewed-topic-correction", "section": primary, "theme": theme})


def edit_manuscript(center: dict, original: dict) -> tuple[dict, list[dict]]:
    item = copy.deepcopy(original)
    events: list[dict] = []
    correction = corrections().get((item["locality"], item["level"], item["subject"]))
    if correction:
        apply_correction(item, correction, events)
    names = school_pattern(center)
    school_added = False
    address_added = False

    def paragraph(value: str, location: str) -> str:
        nonlocal school_added, address_added
        old = value
        if ADDRESS_SOURCE.search(value):
            # Keep learning advice in the same paragraph, but discard the old
            # uncertain location input and its dependent address disclaimer.
            kept = [s for s in SENTENCE_SPLIT.split(value) if not re.search(r"주소|위치|소재지|이동|통학|장소|호실|층수|보조|제공|이 자료|이 정보|두 정보", s)]
            value = " ".join(([address_context(center)] if not address_added else []) + kept)
            address_added = True
            events.append({"kind": "verified-address", "field": location})
        elif names.search(value) or SCHOOL_SOURCE.search(value):
            kept = []
            for s in SENTENCE_SPLIT.split(value):
                if names.search(s) or SCHOOL_SOURCE.search(s):
                    continue
                # No dangling reference to a removed, mixed-school-level list.
                if re.search(r"이 목록|이 이름|학교명만|학교 이름만|해당 학교|이 학교|이런 학교|자료에 적힌 학교", s):
                    continue
                kept.append(s)
            # Keep the original topic-specific preparation advice instead of
            # repeating a new generic preparation sentence immediately before it.
            include_prep = not any(re.search(r"준비|가져|챙겨", sentence) for sentence in kept)
            value = " ".join(([school_context(center, item, include_prep)] if not school_added else []) + kept)
            school_added = True
            events.append({"kind": "same-level-schools", "field": location})
        value = clean_authoring(value)
        if value != old:
            events.append({"kind": "paragraph-edit", "field": location, "before": old, "after": value})
        return value

    item["intro"] = [edited for i, p in enumerate(item["intro"]) if (edited := paragraph(p, f"intro/{i}"))]
    for i, section in enumerate(item["sections"]):
        h = section["heading"]
        previous_school_headings = {
            "효명중·이충중·은혜중 자료를 고등 학습으로 넘겨보기",
            "화정중·지도중·신능중 자료를 확인하는 질문",
        }
        if h in previous_school_headings:
            section["heading"] = "이전 학습 기록에서 고등 영어의 빈틈 찾기"
        elif names.search(h) or SCHOOL_SOURCE.search(h):
            section["heading"] = f'{item["locality"]} {item["level"]} {item["subject"]} 상담에 챙길 학교 자료'
        else:
            section["heading"] = h.replace("제공된 ", "").replace("학원데스크", "상담 창구").replace("영어 수학 키워드", "영어·수학 학습")
        section["paragraphs"] = [edited for j, p in enumerate(section["paragraphs"]) if (edited := paragraph(p, f"sections/{i}/{j}"))]
        section.pop("_reviewed", None)
        if not section["paragraphs"]:
            raise ValueError(f'본문 섹션이 비었습니다: {item["title"]}/{i}')
    for i, faq in enumerate(item["faq"]):
        faq["question"] = faq["question"].replace("학원데스크", "상담 창구")
        old = faq["answer"]
        # FAQ must stand alone, so do not depend on the body school/address flags.
        if names.search(faq["question"]):
            faq["question"] = "학교 자료는 어떤 기준으로 준비하면 좋을까요?"
            faq["answer"] = school_context(center, item)
        elif names.search(old) or SCHOOL_SOURCE.search(old):
            faq["answer"] = school_context(center, item)
        elif ADDRESS_SOURCE.search(old):
            faq["answer"] = address_context(center)
        else:
            faq["answer"] = clean_authoring(old)
        if not faq["answer"]:
            raise ValueError(f'FAQ 답이 비었습니다: {item["title"]}/{i}')
        if old != faq["answer"]:
            events.append({"kind": "faq-edit", "index": i, "before": old, "after": faq["answer"]})
    examples = []
    for p in item["example"]:
        # Keep the hypothetical vignette, but do not reintroduce schools of
        # other levels through its narrative. No invented enrollment history.
        retained = " ".join(s for s in SENTENCE_SPLIT.split(p) if not names.search(s))
        edited = clean_authoring(retained)
        if edited:
            examples.append(edited)
        if edited != p:
            events.append({"kind": "example-edit", "before": p, "after": edited})
    item["example"] = examples
    return item, events


def learning_points(center: dict) -> list[tuple[str, str]]:
    """Questions grounded in existing management categories, not new promises."""
    questions = {
        "플래너 점검": "계획한 분량과 실제 마친 분량을 어떻게 나누어 보는지, 미완료 과제는 다음 계획에 어떻게 반영하는지 질문해 보세요.",
        "오답 재학습": "정답을 고친 뒤 해설 없이 다시 푼 기록도 확인하는지, 같은 실수가 반복되면 설명과 문제를 어떻게 바꾸는지 물어보세요.",
        "학교별 내신 준비": "학생이 받은 평가 범위와 수업 자료를 가져와 학교 진도와 현재 교재의 차이를 어떤 순서로 조정할지 확인해 보세요.",
        "시험기간 계획": "시험까지 남은 기간과 과목별 범위를 알려주고, 새 진도와 오답 복습의 우선순위를 어떻게 나눌지 상담해 보세요.",
        "학습 기록": "기록에 완료한 진도뿐 아니라 혼자 해결한 내용과 다시 질문할 내용도 담기는지 확인해 보세요.",
        "보호자 피드백": "가정에서 확인할 내용이 출결·과제·이해도 중 어디까지인지, 질문을 전달하는 방법과 공유 주기를 확인해 보세요.",
        "독서 활동": "읽은 분량 외에 학생이 내용을 설명하거나 질문하는 활동이 있는지, 현재 독서 수준은 무엇으로 살펴보는지 물어보세요.",
        "고등 학습 상담": "현재 이수 과목과 학교 평가 일정을 알려주고, 교과 학습 계획과 진로 상담을 어디까지 함께 다룰 수 있는지 확인해 보세요.",
        "자습 운영": "자습을 이용할 수 있는 요일과 대상, 질문할 수 있는 범위 및 별도 예약 조건을 확인해 보세요.",
        "학습 도구 활용": "학습 도구를 사용하는 과목과 목적을 물어보고, 결과를 선생님의 설명과 다음 과제에 어떻게 연결하는지 확인해 보세요.",
        "과목 연계 관리": "과목별 과제가 같은 날 몰릴 때 학습량을 어떻게 조정할지, 우선 보완할 과목을 어떤 자료로 정하는지 질문해 보세요.",
        "수준별 교재와 학습량": "현재 사용하는 교재와 혼자 풀어 본 기록을 가져가, 시작할 단원과 과제량을 어떤 기준으로 정할지 질문해 보세요.",
        "학교 평가 준비": "수행평가 안내와 시험 범위를 준비하고, 준비 기간이 겹치는 과제와 복습을 어떤 순서로 나눌지 확인해 보세요.",
        "보호자와 학습 소통": "공유받을 학습 기록에 무엇이 담기는지, 가정에서 발견한 어려움은 어떤 방법으로 전달하면 되는지 확인해 보세요.",
    }
    listed = center.get("managementPoints", [])
    if listed:
        return [(title, questions[title]) for title, _ in listed]
    return [
        ("시작할 내용 정하기", "잘 풀린 문제와 막힌 문제를 함께 가져와 개념·읽기·계산 중 먼저 확인할 부분을 물어보세요."),
        ("집에서 이어갈 복습", "설명을 듣고 고친 기록과 다음 날 혼자 해 본 기록을 나누어, 다시 도움이 필요한 부분을 어떻게 질문할지 정해 보세요."),
        ("보호자가 확인할 내용", "과제 완료 여부 외에 학생이 이해한 내용과 남은 질문을 어떤 방법으로 공유받을 수 있는지 확인해 보세요."),
    ]
