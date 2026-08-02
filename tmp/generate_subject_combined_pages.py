from __future__ import annotations

import hashlib
import html
import json
import random
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = Path(__file__).with_name("generate_subject_english_pages.py")
SOURCE_DIR = ROOT.parent / "참고자료" / "사용한 원고" / "wawa-center.kr 추가 원고"
SITE_URL = "https://wawa-center.kr"
TODAY = "2026-08-02"

CATEGORIES = (
    {
        "slug": "고등영수학원",
        "label": "고등 영수학원",
        "zip": "고등 영수학원.zip",
        "level": "고등",
        "grade_prefix": "고",
        "school_marker": "고등학교",
        "eyebrow": "HIGH SCHOOL ENGLISH & MATH LOCAL GUIDE",
        "directory": "HIGH SCHOOL ENGLISH & MATH DIRECTORY",
        "card_id": "high-combined",
        "card_number": "05",
        "card_small": "HIGH SCHOOL ENGLISH & MATH",
        "card_copy": "영어 내신·독해와 수학 개념·문제풀이를 시험 일정과 오답 재학습 흐름으로 함께 확인합니다.",
        "study_path": "고등학생-공부법",
        "study_name": "고등학생 공부법",
    },
    {
        "slug": "중등영수학원",
        "label": "중등 영수학원",
        "zip": "중등 영수학원.zip",
        "level": "중등",
        "grade_prefix": "중",
        "school_marker": "중학교",
        "eyebrow": "MIDDLE SCHOOL ENGLISH & MATH LOCAL GUIDE",
        "directory": "MIDDLE SCHOOL ENGLISH & MATH DIRECTORY",
        "card_id": "middle-combined",
        "card_number": "06",
        "card_small": "MIDDLE SCHOOL ENGLISH & MATH",
        "card_copy": "영어 문법·독해와 수학 개념·유형 학습을 학교 내신, 과제와 주간 복습 기준으로 연결합니다.",
        "study_path": "중학생-공부법",
        "study_name": "중학생 공부법",
    },
    {
        "slug": "초등영수학원",
        "label": "초등 영수학원",
        "zip": "초등 영수학원.zip",
        "level": "초등",
        "grade_prefix": "초",
        "school_marker": "초등학교",
        "eyebrow": "ELEMENTARY ENGLISH & MATH LOCAL GUIDE",
        "directory": "ELEMENTARY ENGLISH & MATH DIRECTORY",
        "card_id": "elementary-combined",
        "card_number": "07",
        "card_small": "ELEMENTARY ENGLISH & MATH",
        "card_copy": "영어 읽기·기초 문장과 수학 개념·연산을 학습 습관, 과제와 단계별 복습 기준으로 살펴봅니다.",
        "study_path": "초등학생-공부법",
        "study_name": "초등학생 공부법",
    },
)


COMMON_SENTENCE_OPENERS = (
    "최근 학습 기록을 기준으로 보면,",
    "상담 질문을 구체화하면,",
    "두 과목의 주간 계획을 나누어 보면,",
    "학생의 실제 풀이 과정을 놓고 보면,",
    "가정에서 확인할 기준으로 바꾸면,",
    "시험 준비 순서를 정할 때는,",
    "수업 이후의 복습까지 고려하면,",
    "과제와 오답 기록을 함께 살피면,",
    "학년별 목표와 현재 상태를 비교하면,",
    "학부모가 확인할 항목으로 정리하면,",
    "교재 진도보다 실행 과정을 먼저 보면,",
    "영어와 수학의 차이를 나누어 보면,",
    "상담 내용을 주간 계획으로 옮길 때는,",
    "최근 채점 결과를 바탕으로 보면,",
    "학생이 혼자 공부하는 시간까지 포함하면,",
    "수업 선택 기준을 실제 행동으로 바꾸면,",
    "시험 전후의 기록을 이어서 보면,",
    "설명보다 확인 가능한 자료를 먼저 놓으면,",
    "과목별 취약 지점을 구분해 보면,",
    "현재 단원과 누적 빈틈을 함께 보면,",
    "학교 일정과 복습 시간을 맞춰 보면,",
    "다음 상담에서 확인할 질문으로 바꾸면,",
    "학습량과 피드백 방식을 따로 보면,",
    "학생이 남긴 풀이 흔적을 중심으로 보면,",
    "한 주의 학습 흐름을 시간순으로 보면,",
    "영어 답안과 수학 풀이를 각각 살피면,",
    "첫 달의 변화를 기록으로 확인하려면,",
    "과장된 약속 대신 과정을 확인하면,",
    "등원 전후의 실행 가능 시간을 고려하면,",
    "학교 자료와 사용 중인 교재를 함께 보면,",
    "진단 결과를 과목별 행동으로 나누면,",
    "학부모와 학생이 같은 기준으로 점검하려면,",
)


FAQ_CONTEXT_OPENERS = (
    "최근 시험지와 교재를 기준으로,",
    "영어·수학의 진도 차이를 고려하면,",
    "학생의 주간 학습 기록을 놓고,",
    "과목별 오답 원인을 나누어 볼 때,",
    "학교 일정과 가정 복습 시간을 함께 보면,",
    "첫 상담에서 현재 상태를 확인한 뒤,",
    "숙제 수행과 질문 기록을 기준으로,",
    "수업 전후의 실행 가능 시간을 고려해,",
    "영어 답안과 수학 풀이를 따로 살펴보면,",
    "시험 범위와 남은 기간을 함께 놓고,",
    "학생이 혼자 공부하는 시간까지 포함해,",
    "교재 진도보다 이해 과정을 먼저 보면,",
    "과제량과 피드백 방식을 구분해서,",
    "틀린 문제의 재확인 시점을 기준으로,",
    "학년 전환기 학습 흐름을 고려하면,",
    "두 과목의 우선순위를 다시 정할 때,",
    "최근 한 달의 출결과 과제 기록을 바탕으로,",
    "상담 내용을 실제 계획으로 옮기려면,",
    "학부모가 확인 가능한 자료를 중심으로,",
    "학생의 설명과 풀이 흔적을 함께 보면,",
    "수업 횟수보다 남는 기록을 기준으로,",
    "내신 준비와 평소 복습을 구분해서,",
    "영어 문장 이해와 수학 조건 해석을 나누어,",
    "다음 등원 전 해야 할 일을 정할 때,",
    "학교 자료의 활용 방식을 점검하면서,",
    "학습량을 무리 없이 조정하려면,",
    "첫 달에 관찰할 변화를 정해 두고,",
    "성적 약속보다 관리 절차를 확인하며,",
    "학생 유형에 맞는 설명 방식을 찾을 때,",
    "가정과 학원의 역할을 나누어 보면,",
    "과목마다 필요한 복습 간격을 고려해,",
    "상담 후 비교 기준을 다시 정리하면서,",
)


SECTION_ORDERS = (
    (0, 1, 2, 3, 4, 5),
    (0, 2, 1, 3, 4, 5),
    (1, 0, 2, 4, 3, 5),
    (0, 1, 3, 2, 5, 4),
    (1, 2, 0, 3, 5, 4),
    (2, 0, 1, 4, 3, 5),
    (0, 3, 1, 2, 4, 5),
    (1, 0, 3, 2, 4, 5),
)


LEXICAL_BANKS = {
    "영어와 수학을": ("두 과목을", "수학과 영어를", "영어·수학을"),
    "영어 수학을": ("영어·수학을", "두 과목을", "수학과 영어를"),
    "영어·수학을": ("영어와 수학을", "두 과목을", "수학·영어를"),
    "영어와 수학은": ("두 과목은", "수학과 영어는", "영어·수학은"),
    "영어 수학은": ("영어·수학은", "두 과목은", "수학과 영어는"),
    "영어·수학은": ("영어와 수학은", "두 과목은", "수학·영어는"),
    "영어와 수학이": ("두 과목이", "수학과 영어가", "영어·수학이"),
    "영어 수학이": ("영어·수학이", "두 과목이", "수학과 영어가"),
    "영어·수학이": ("영어와 수학이", "두 과목이", "수학·영어가"),
    "영어와 수학의": ("두 과목의", "수학과 영어의", "영어·수학의"),
    "영어 수학의": ("영어·수학의", "두 과목의", "수학과 영어의"),
    "영어·수학의": ("영어와 수학의", "두 과목의", "수학·영어의"),
    "영어와 수학": ("두 과목", "수학과 영어", "영어·수학"),
    "영어 수학": ("영어·수학", "두 과목", "수학과 영어"),
    "영어·수학": ("영어와 수학", "두 과목", "수학·영어"),
    "학부모님은": ("보호자는", "학부모님께서는", "가정에서는"),
    "학부모는": ("보호자는", "학부모 입장에서는", "가정에서는"),
    "상담에서는": ("상담 자리에서는", "첫 상담에서는", "상담 과정에서는"),
    "상담에서": ("상담 과정에서", "첫 상담에서", "상담 자리에서"),
    "상담 전에는": ("상담을 앞두고는", "첫 상담을 준비할 때는", "상담 전에는"),
    "상담 전에": ("상담을 앞두고", "첫 상담에 앞서", "상담을 준비하며"),
    "상담 전": ("상담을 앞두고", "첫 상담에 앞서", "상담을 준비하며"),
    "수업 후": ("수업을 마친 뒤", "수업 이후", "등원을 마친 뒤"),
    "최근 시험지": ("가장 최근 시험지", "최근 채점지", "최근에 푼 시험지"),
    "학교 자료": ("학교에서 받은 자료", "학교 학습 자료", "제공된 학교 자료"),
    "오답 재풀이": ("틀린 문항 재풀이", "오답 재확인", "틀린 문제 다시 풀기"),
    "확인해야 합니다": ("점검할 필요가 있습니다", "상담에서 살펴보아야 합니다", "확인 항목으로 두는 편이 좋습니다"),
    "확인하는 것이 좋습니다": ("점검해 보는 편이 좋습니다", "상담 질문으로 구체화할 필요가 있습니다", "직접 살펴보는 것이 바람직합니다"),
    "살펴야 합니다": ("구체적으로 점검해야 합니다", "비교 기준에 넣어야 합니다", "차분히 확인할 필요가 있습니다"),
    "질문해 볼 수 있습니다": ("구체적으로 물어볼 수 있습니다", "상담 질문으로 정리할 수 있습니다", "확인 질문으로 삼을 수 있습니다"),
    "도움이 됩니다": ("실제 계획을 세우는 데 유용합니다", "비교 기준을 세우기 수월합니다", "다음 학습을 정하는 데 보탬이 됩니다"),
    "중요합니다": ("핵심 확인사항입니다", "우선 살펴볼 기준입니다", "놓치지 말아야 할 대목입니다"),
    "필요합니다": ("필요한 과정입니다", "먼저 마련되어야 합니다", "확인할 필요가 있습니다"),
}


QUESTION_ENDING_BANKS = {
    "어떤 학생에게 더 잘 맞나요?": ("어떤 학생이 우선 비교해 보면 좋을까요?", "어느 학습 유형에 더 적합한가요?", "어떤 상황의 학생에게 도움이 될까요?"),
    "어떤 중학생에게 먼저 맞을까요?": ("어떤 중학생이 먼저 비교해 보면 좋을까요?", "어느 학습 상황의 중학생에게 적합할까요?", "어떤 중학생에게 우선 상담이 필요할까요?"),
    "가장 중요한 기준은 무엇인가요?": ("무엇을 가장 먼저 비교해야 하나요?", "첫 번째로 확인할 기준은 무엇인가요?", "어떤 관리 절차부터 살펴봐야 하나요?"),
    "꼭 물어볼 질문은 무엇인가요?": ("어떤 질문을 빠뜨리지 말아야 하나요?", "무엇을 구체적으로 물어봐야 하나요?", "반드시 확인할 운영 기준은 무엇인가요?"),
    "부담이 크지 않을까요?": ("학습 부담을 어떻게 조정해야 하나요?", "두 과목 분량을 어떻게 나누면 좋을까요?", "무리 없는 주간 계획은 어떻게 확인하나요?"),
    "무엇을 가져가면 좋나요?": ("어떤 자료를 준비하면 좋을까요?", "상담 자료는 무엇부터 챙기면 되나요?", "현재 상태 확인에 필요한 자료는 무엇인가요?"),
    "어떻게 질문해야 하나요?": ("어떤 항목으로 나누어 물어봐야 하나요?", "상담 질문을 어떻게 구체화하면 좋을까요?", "무엇을 근거로 확인해야 하나요?"),
    "좋을까요?": ("적절할까요?", "먼저 확인해 보는 편이 나을까요?", "어떤 기준으로 판단하면 좋을까요?"),
    "어떻게 반영하나요?": ("어떤 절차로 연결하나요?", "수업 계획에 어떻게 활용하나요?", "어느 범위까지 확인해 반영하나요?"),
    "어디까지 반영되나요?": ("어느 범위까지 활용되나요?", "어떤 자료까지 수업에 연결하나요?", "반영 범위를 어떻게 확인할 수 있나요?"),
}


CONTEXT_OBJECTS = (
    "최근 학습 기록을", "첫 상담 자료를", "두 과목의 주간 계획을", "학생의 실제 풀이 과정을",
    "가정에서 확인한 내용을", "시험 준비 순서를", "수업 이후의 복습 기록을", "과제와 오답 기록을",
    "학년별 목표와 현재 상태를", "학부모가 확인할 항목을", "교재 진도와 실행 과정을", "영어와 수학의 차이를",
    "상담에서 나온 내용을", "최근 채점 결과를", "혼자 공부할 수 있는 시간을", "수업 선택 기준을",
    "시험 전후의 변화를", "확인 가능한 자료를", "과목별 취약 지점을", "현재 단원과 누적 빈틈을",
    "학교 일정과 복습 시간을", "다음 상담에서 물을 내용을", "학습량과 피드백 방식을", "학생이 남긴 풀이 흔적을",
)


CONTEXT_ACTIONS = (
    "기준으로 보면,", "함께 놓고 보면,", "상담 질문으로 바꾸면,", "주간 계획과 연결하면,",
    "다음 행동으로 구체화하면,", "과목별로 나누어 보면,", "시험 전후로 비교하면,", "학부모 관점에서 정리하면,",
    "학생의 설명과 대조하면,", "우선순위에 따라 배열하면,", "첫 달 점검표에 넣으면,", "등원 전후 시간과 맞춰 보면,",
    "영어·수학으로 구분하면,", "최근 자료와 다시 비교하면,", "가정 복습 기준으로 바꾸면,", "다음 점검 순서로 이어 보면,",
)


HEADING_CONTEXTS = (
    "최근 풀이 기록", "학교 자료", "영어·수학 우선순위", "주간 실행 계획",
    "과제·오답 기록", "가정 복습 시간", "시험 전후 변화", "첫 달 점검",
    "학생 설명과 풀이 흔적", "상담 준비 자료", "과목별 복습 간격", "재풀이 시점",
    "등원 전후 시간", "학년 전환기 계획", "피드백 공유 주기", "현재 단원과 누적 빈틈",
    "학습량 조정", "수업 이후 복습", "시험 범위와 남은 기간", "질문 기록",
    "교재 진도와 이해도", "영어 답안·수학 풀이", "숙제 수행과 오답", "과목별 취약 지점",
    "현재 학습 상태", "최근 채점 결과", "가정 확인 내용", "수업 선택 기준",
    "학생의 주간 기록", "진단 이후 행동", "학교 일정", "상담 후 실행 계획",
)


HEADING_LENSES = (
    "상담 질문", "과목별 점검", "복습 설계", "첫 달 확인",
    "가정 점검", "다음 실행", "오답 재확인", "시험 준비",
    "수업 피드백", "학습량 조정", "우선순위 비교", "자료 확인",
    "주간 계획", "학부모 확인", "학생 자기점검", "수업 전 준비",
)


def stable_number(*parts: object) -> int:
    value = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def contextual_opener(rank: int, slot: int, normalized: str) -> str:
    total = len(CONTEXT_OBJECTS) * len(CONTEXT_ACTIONS)
    serial = (stable_number(normalized, slot) + rank) % total
    conflicts = ("최근", "상담", "학부모")
    for _ in range(total):
        object_text = CONTEXT_OBJECTS[serial % len(CONTEXT_OBJECTS)]
        action_index = (serial // len(CONTEXT_OBJECTS)) % len(CONTEXT_ACTIONS)
        action_text = CONTEXT_ACTIONS[action_index]
        duplicated_inside = any(token in object_text and token in action_text for token in conflicts)
        duplicated_with_sentence = any(
            token in normalized and (token in object_text or token in action_text)
            for token in conflicts
        )
        if not duplicated_inside and not duplicated_with_sentence:
            break
        serial = (serial + 1) % total
    return f"{object_text} {action_text}"


def sentence_parts(value: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", value.strip()) if value.strip() else []


def reduce_recent_repetition(value: str) -> str:
    parts = re.split(r"(?<=[.!?])(\s+)", value)
    polished: list[str] = []
    for index, sentence in enumerate(parts):
        if index % 2 == 1:
            polished.append(sentence)
            continue
        occurrence = 0

        def replace(_match: re.Match[str]) -> str:
            nonlocal occurrence
            occurrence += 1
            return "최근" if occurrence == 1 else "직전"

        polished.append(re.sub(r"최근", replace, sentence))
    return "".join(polished)


def normalize_for_frequency(value: str, local: str) -> str:
    return re.sub(r"\s+", " ", value.replace(local, "{LOCAL}")).strip()


def lexical_variation(value: str, code: int) -> str:
    pattern = re.compile("|".join(re.escape(key) for key in sorted(LEXICAL_BANKS, key=len, reverse=True)))
    occurrence = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal occurrence
        options = LEXICAL_BANKS[match.group(0)]
        choice = options[(code // (3 ** occurrence)) % len(options)]
        occurrence += 1
        return choice

    return pattern.sub(replace, value)


def diversify_question(value: str, local: str, rank: int, slot: int, frequency: int) -> str:
    if frequency < 8:
        return value
    code = rank * 11 + slot * 37 + stable_number(value.replace(local, "{LOCAL}"))
    question = lexical_variation(value, code)
    for ending, options in sorted(QUESTION_ENDING_BANKS.items(), key=lambda item: len(item[0]), reverse=True):
        if question.endswith(ending):
            question = question[: -len(ending)] + options[(code // 7) % len(options)]
            break
    opener = contextual_opener(rank, 700 + slot, value.replace(local, "{LOCAL}"))
    return f"{opener} {question}"


def diversify_text(
    value: str,
    local: str,
    rank: int,
    slot: int,
    frequencies: dict[str, int],
    minimum_frequency: int = 4,
) -> str:
    diversified: list[str] = []
    for sentence_index, sentence in enumerate(sentence_parts(value)):
        normalized = normalize_for_frequency(sentence, local)
        frequency = frequencies.get(normalized, 0)
        if frequency < minimum_frequency or len(sentence) < 24:
            diversified.append(sentence)
            continue
        code = rank * 17 + slot * 41 + sentence_index * 13 + stable_number(normalized)
        transformed = lexical_variation(sentence, code)
        for connective in ("그래서 ", "결국 ", "따라서 ", "먼저 답변드리면, "):
            if transformed.startswith(connective):
                transformed = transformed[len(connective):]
                break
        opener = contextual_opener(rank, slot * 100 + sentence_index, normalized)
        diversified.append(f"{opener} {transformed}")
    return " ".join(diversified).replace(
        "과정이 필요한 과정",
        "과정을 보완해야 하는 상태",
    )


def diversify_heading(value: str, rank: int, slot: int, frequency: int) -> str:
    if frequency < 2:
        return value
    total = len(HEADING_CONTEXTS) * len(HEADING_LENSES)
    serial = (rank * 47 + slot * 131 + stable_number(value)) % total
    context = HEADING_CONTEXTS[serial % len(HEADING_CONTEXTS)]
    lens = HEADING_LENSES[(serial // len(HEADING_CONTEXTS)) % len(HEADING_LENSES)]
    separators = (" · ", " | ", " — ")
    separator = separators[(rank + slot) % len(separators)]
    return f"{value}{separator}{context} / {lens}"


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def transformed_namespace(config: dict[str, str]) -> dict[str, object]:
    source = BASE.read_text(encoding="utf-8")
    protected = {
        'ENGLISH_ROOT = ROOT / "과목별학원" / "영어학원"':
            'ENGLISH_ROOT = ROOT / "과목별학원" / "__COMBINED_SLUG__"',
        'encoded_url("과목별학원", "영어학원"':
            'encoded_url("과목별학원", "__COMBINED_SLUG__"',
        '/과목별학원/영어학원/': '/과목별학원/__COMBINED_SLUG__/',
        'href="./영어학원/"': 'href="./__COMBINED_SLUG__/"',
    }
    for old, new in protected.items():
        if old not in source:
            raise ValueError(f"base generator pattern not found: {old}")
        source = source.replace(old, new)

    source = re.sub(
        r'^ZIP_PATH\s*=.*$',
        f'ZIP_PATH = SOURCE_DIR / {config["zip"]!r}',
        source,
        count=1,
        flags=re.MULTILINE,
    )
    source = source.replace(
        'ROOT = Path(__file__).resolve().parents[1]',
        'ROOT = Path(__file__).resolve().parents[1]\nSOURCE_DIR = ROOT.parent / "참고자료" / "사용한 원고" / "wawa-center.kr 추가 원고"',
        1,
    )
    source = re.sub(r'^TODAY\s*=\s*"[^"]+"$', f'TODAY = "{TODAY}"', source, count=1, flags=re.MULTILINE)
    source = source.replace('"영어학원"', f'"{config["label"]}"')
    source = source.replace("영어학원", config["label"])
    source = source.replace("__COMBINED_SLUG__", config["slug"])
    source = source.replace("LOCAL ENGLISH ACADEMY GUIDE", config["eyebrow"])
    source = source.replace("ENGLISH ACADEMY DIRECTORY", config["directory"])
    source = source.replace("english-local-search", f'{config["card_id"]}-local-search')
    source = source.replace("english-search-count", f'{config["card_id"]}-search-count')

    namespace: dict[str, object] = {
        "__name__": f'subject_{config["slug"]}_generator',
        "__file__": str(BASE),
    }
    exec(compile(source, str(BASE), "exec"), namespace)
    return namespace


def flexible_reviews(text: str) -> list[dict[str, str]]:
    marker = re.compile(
        r"^\s*((?:후기\s*예시|상담\s*후\s*기록|보호자\s*추가\s*메모|예시\s*후기|후기)\s*\d*)\s*[｜:.\-]\s*",
        re.MULTILINE,
    )
    matches = list(marker.finditer(text.strip()))
    reviews: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = re.sub(r"\s+", " ", text[match.end():end]).strip().strip('“”"')
        if not content:
            continue
        reviews.append({"label": re.sub(r"\s+", " ", match.group(1)).strip(), "content": content})
    if reviews:
        return reviews

    blocks = [re.sub(r"\s+", " ", block).strip().strip('“”"') for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [{"label": f"학부모 상담 관점 {index}", "content": block} for index, block in enumerate(blocks, start=1)]


def representative_mapping(order: list[str], config: dict[str, str]) -> dict[str, str]:
    candidates: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for path in sorted((ROOT / "assets").glob("representative-*/*.gif")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        candidates.append((digest, path))
    if len(candidates) < len(order):
        raise ValueError(f"not enough existing representative images: {len(candidates)}")
    random.Random(f'wawa-{config["slug"]}-{TODAY}').shuffle(candidates)
    return {
        local: "/" + path.relative_to(ROOT).as_posix()
        for local, (_, path) in zip(order, candidates)
    }


def school_matches_level(name: str, marker: str) -> bool:
    return marker in name


def configure_namespace(namespace: dict[str, object], config: dict[str, str]) -> None:
    original_center = namespace["extract_center_data"]
    original_load = namespace["load_manuscripts"]
    original_naturalize = namespace["naturalize_text"]
    original_schema = namespace["page_schema"]
    original_render_page = namespace["render_page"]
    original_render_hub = namespace["render_hub"]

    def naturalize(value: str, _local: str) -> str:
        value = original_naturalize(value, _local)
        replacements = {
            "학부모님이 학부모가 빠르게 확인할 대목은": "학부모님이 빠르게 확인할 대목은",
            "초을 기준": "초를 기준",
            "중을 기준": "중을 기준",
            "고을 기준": "고를 기준",
            "학교을": "학교를",
            "수학과 영어을": "수학과 영어를",
            "영어와 수학를": "영어와 수학을",
            "관리을": "관리를",
            "대비을": "대비를",
            "학원를": "학원을",
            "자료을": "자료를",
            "영어을": "영어를",
            "수학를": "수학을",
            "코칭를": "코칭을",
            "정보을": "정보를",
            "상담를": "상담을",
            "수업를": "수업을",
            "학생를": "학생을",
            "학원로 제공": "학원으로 안내",
            "제공된 수업 학교 정보가 있으므로 제공된 학교 자료": "수업 가능 학교 정보가 확인되므로 해당 학교 자료",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        value = re.sub(
            r"D열에 학교명이 입력되어 있지 않은 (.*?) 원고에서는",
            r"제공된 자료에 학교명이 없는 경우, \1 페이지는",
            value,
        )
        value = value.replace("D열 학교명이", "제공된 학교명이")
        value = value.replace("D열에 입력된 학교명", "제공된 학교명")
        value = value.replace("수업학교", "수업 가능 학교")
        value = value.replace("수업 학교", "수업 가능 학교")
        value = value.replace("키워드를", "학습 항목을")
        value = value.replace("키워드는", "학습 항목은")
        value = value.replace("키워드가", "학습 항목이")
        value = value.replace("키워드", "학습 항목")
        value = value.replace("첫 상담을 준비할 때는 상담 자료는", "첫 상담을 준비할 때 필요한 자료는")
        value = value.replace("첫 상담에 앞서에", "첫 상담에 앞서")
        value = value.replace("구조화 데이터 설명문에 활용하기 좋습니다", "상담 전에 핵심 내용을 빠르게 확인하기 좋습니다")
        value = value.replace("구조화 데이터 설명에는", "페이지 핵심 안내에는")
        value = value.replace("구조화 데이터 설명", "페이지 핵심 안내")
        value = value.replace("구조화 데이터", "핵심 안내")
        value = re.sub(r"(?<![가-힣])원고에서는", "페이지에서는", value)
        value = re.sub(r"(?<![가-힣])원고는", "페이지는", value)
        value = re.sub(r"(?<![가-힣])원고를", "안내 내용을", value)
        value = re.sub(r"(?<![가-힣])원고로", "페이지로", value)
        value = re.sub(r"(?<![가-힣])원고에", "페이지에", value)
        value = re.sub(r"(?<![가-힣])원고의", "페이지의", value)
        value = re.sub(r"(?<![가-힣])원고가", "페이지가", value)
        value = re.sub(r"(?<![가-힣])원고와", "페이지와", value)
        value = re.sub(r"(?<![가-힣])원고(?![가-힣])", "페이지", value)
        value = value.replace("학원로", "학원으로")
        value = value.replace("과정이 필요한 과정", "과정을 보완해야 하는 상태")
        value = value.replace("자료에 제공된 수업 가능 학교는", "제공 자료에서 확인되는 수업 가능 학교는")
        value = value.replace("자료 확인 확인 가능한 자료", "자료 확인에 필요한 자료")
        value = value.replace("확인 확인 가능한 자료", "확인 가능한 자료")
        value = value.replace(f"{_local} {_local}", _local)
        return reduce_recent_repetition(value)

    def center_data(local: str) -> dict[str, object]:
        center = original_center(local)
        grades = [grade for grade in center.get("grades", []) if str(grade).startswith(config["grade_prefix"])]
        center["grades"] = grades or [f'{config["level"]} 과정 제공 여부 상담 확인 필요']
        center["schools"] = [
            school for school in center.get("schools", [])
            if school_matches_level(str(school), config["school_marker"])
        ]
        return center

    def manuscripts() -> dict[str, dict[str, object]]:
        values = original_load()
        rank_by_local = {local: rank for rank, local in enumerate(sorted(values))}
        sentence_frequencies: dict[str, int] = {}
        question_frequencies: dict[str, int] = {}
        heading_frequencies: dict[str, int] = {}

        def count_sentence(value: str, local: str) -> None:
            for sentence in sentence_parts(value):
                normalized = normalize_for_frequency(sentence, local)
                sentence_frequencies[normalized] = sentence_frequencies.get(normalized, 0) + 1

        for local, manuscript in values.items():
            for paragraph in manuscript.get("intro", []):
                count_sentence(str(paragraph), local)
            for _, paragraphs in manuscript.get("sections", []):
                for paragraph in paragraphs:
                    count_sentence(str(paragraph), local)
            for heading, _ in manuscript.get("sections", []):
                normalized_heading = normalize_for_frequency(str(heading), local)
                heading_frequencies[normalized_heading] = heading_frequencies.get(normalized_heading, 0) + 1
            for faq in manuscript.get("faqs", []):
                question = normalize_for_frequency(str(faq["question"]), local)
                question_frequencies[question] = question_frequencies.get(question, 0) + 1
                count_sentence(str(faq["answer"]), local)
            for review in manuscript.get("reviews", []):
                count_sentence(str(review["content"]), local)
            count_sentence(str(manuscript.get("summary", "")), local)

        review_roles = (
            "보호자가", "학부모가", "가정에서", "상담 후 보호자가",
            "학생과 함께", "첫 상담에서", "학습 기록을 바탕으로", "상담 내용을 토대로",
        )
        review_focuses = (
            "두 과목의 학습 흐름을", "주간 학습 계획을", "영어·수학 복습 간격을",
            "과제와 오답 관리를", "상담 준비 자료를", "첫 달 확인 기준을",
            "학생의 질문 기록을", "시험 전 우선순위를", "가정 복습 방식을",
            "수업 후 피드백을", "학년별 학습 목표를", "다음 상담 질문을",
        )
        review_forms = (
            "확인한 관점", "정리한 기록", "살펴본 내용",
            "점검한 메모", "비교한 기준", "구체화한 질문",
        )
        summary_frames = (
            "본문의 핵심 확인 항목은 다음과 같습니다: ‘{first}’, ‘{second}’.",
            "학생 기록과 대조해 볼 순서는 다음과 같습니다: ‘{first}’, ‘{second}’.",
            "실제 학습 자료와 함께 비교할 두 항목을 정리했습니다: ‘{first}’, ‘{second}’.",
            "이 페이지에서 차례로 다루는 내용은 다음과 같습니다: ‘{first}’, ‘{second}’.",
            "상담 전에 구분해 준비할 자료의 기준은 다음과 같습니다: ‘{first}’, ‘{second}’.",
            "학생 상황을 판단할 때 서로 나누어 볼 항목은 다음과 같습니다: ‘{first}’, ‘{second}’.",
            "과목별 계획 전에 확인할 두 단계는 다음과 같습니다: ‘{first}’, ‘{second}’.",
            "페이지의 답변 흐름은 두 항목으로 구성했습니다: ‘{first}’, ‘{second}’.",
        )
        answer_frames = (
            "이 페이지에서 구분해 볼 세 항목은 다음과 같습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "실제 학습 기록과 맞춰 볼 세 기준을 정리했습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "상담 판단을 구체화하는 순서는 다음과 같습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "학생에게 필요한 도움을 나누어 볼 기준은 다음과 같습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "두 과목을 함께 관리할 때 각각 확인할 내용은 다음과 같습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "최근 기록을 준비한 뒤 질문으로 바꿔 볼 항목은 다음과 같습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "페이지에서 바로 확인할 답변은 세 흐름으로 나뉩니다: ‘{first}’, ‘{second}’, ‘{third}’.",
            "먼저 볼 두 항목과 후속 점검 기준을 정리했습니다: ‘{first}’, ‘{second}’, ‘{third}’.",
        )
        answer_tag_sets = (
            ("현재 학습 상태", "영어·수학 계획", "상담 준비"),
            ("학년별 진단", "과목별 우선순위", "오답 재확인"),
            ("학교 자료 확인", "주간 실행 계획", "피드백 점검"),
            ("영어 취약 지점", "수학 취약 지점", "복습 가능 시간"),
            ("시험 준비 순서", "과제·오답 기록", "다음 상담 질문"),
            ("현재 단원 확인", "누적 빈틈 점검", "재풀이 계획"),
            ("학습량 조정", "과목별 관리", "가정 복습 기준"),
            ("상담 자료 준비", "수업 흐름 확인", "첫 달 점검"),
        )
        for local, manuscript in values.items():
            rank = rank_by_local[local]
            manuscript["intro"] = [
                diversify_text(str(paragraph), local, rank, index, sentence_frequencies)
                for index, paragraph in enumerate(manuscript.get("intro", []))
            ]
            diversified_sections: list[tuple[str, list[str]]] = []
            for section_index, (heading, paragraphs) in enumerate(manuscript.get("sections", [])):
                normalized_heading = normalize_for_frequency(str(heading), local)
                diversified_sections.append(
                    (
                        diversify_heading(
                            str(heading), rank, section_index,
                            heading_frequencies.get(normalized_heading, 0),
                        ),
                        [
                            diversify_text(
                                str(paragraph), local, rank, 100 + section_index * 10 + paragraph_index,
                                sentence_frequencies,
                            )
                            for paragraph_index, paragraph in enumerate(paragraphs)
                        ],
                    )
                )
            if len(diversified_sections) == 6:
                order = SECTION_ORDERS[(rank + stable_number(config["slug"])) % len(SECTION_ORDERS)]
                diversified_sections = [diversified_sections[index] for index in order]
            manuscript["sections"] = diversified_sections

            for faq_index, faq in enumerate(manuscript.get("faqs", [])):
                normalized_question = normalize_for_frequency(str(faq["question"]), local)
                faq["question"] = diversify_question(
                    str(faq["question"]), local, rank, faq_index,
                    question_frequencies.get(normalized_question, 0),
                )
                faq["answer"] = diversify_text(
                    str(faq["answer"]), local, rank, 300 + faq_index,
                    sentence_frequencies,
                )

            for index, review in enumerate(manuscript.get("reviews", [])):
                role = review_roles[(rank + index) % len(review_roles)]
                focus = review_focuses[(rank * 3 + index * 5) % len(review_focuses)]
                form = review_forms[(rank * 5 + index * 2) % len(review_forms)]
                review["label"] = f"{local} {role} {focus} {form}"
                review["content"] = diversify_text(
                    str(review["content"]), local, rank, 400 + index,
                    sentence_frequencies,
                )

            manuscript["summary"] = diversify_text(
                str(manuscript.get("summary", "")), local, rank, 500,
                sentence_frequencies, minimum_frequency=2,
            )
            headings = [str(heading) for heading, _ in manuscript["sections"]]
            if len(headings) >= 3:
                manuscript["summary"] = (
                    str(manuscript["summary"]).rstrip()
                    + " "
                    + summary_frames[rank % len(summary_frames)].format(first=headings[0], second=headings[1])
                )
                manuscript["answer_heading"] = f"{local}에서 먼저 확인할 {config['level']} 영수 학습 기준"
                manuscript["answer_text"] = answer_frames[(rank // len(summary_frames)) % len(answer_frames)].format(
                    first=headings[0], second=headings[1], third=headings[2]
                )
                manuscript["answer_tags"] = list(answer_tag_sets[rank % len(answer_tag_sets)])
        return values

    def mentions(center: dict[str, object], local: str) -> list[dict[str, str]]:
        pairs = [
            ("Place", str(center.get("region", ""))),
            ("Place", str(center.get("city", ""))),
            ("Place", local),
            ("Thing", config["label"]),
            ("Thing", f'{config["level"]} 영어 학습'),
            ("Thing", f'{config["level"]} 수학 학습'),
            ("Thing", "영어·수학 오답 재학습"),
        ]
        pairs.extend(("Organization", str(school)) for school in center.get("schools", []))
        result: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for type_name, name in pairs:
            if name and (type_name, name) not in seen:
                seen.add((type_name, name))
                result.append({"@type": type_name, "name": name})
        return result

    def links(local: str, index: int, order: list[str], center_url: str) -> list[dict[str, str]]:
        encoded_url = namespace["encoded_url"]
        previous_local = order[index - 1] if index else order[-1]
        next_local = order[index + 1] if index + 1 < len(order) else order[0]
        items = [
            {"name": f'{config["label"]} 전체 지역', "url": encoded_url("과목별학원", config["slug"])},
            {"name": f"{local} 영어학원", "url": encoded_url("과목별학원", "영어학원", local)},
            {"name": f"{local} 수학학원", "url": encoded_url("과목별학원", "수학학원", local)},
        ]
        if center_url:
            items.append({"name": f"{local} 전국센터 안내", "url": center_url})
        items.extend(
            [
                {"name": config["study_name"], "url": encoded_url("교육정보", config["study_path"])},
                {"name": f"이전 지역 · {previous_local}", "url": encoded_url("과목별학원", config["slug"], previous_local)},
                {"name": f"다음 지역 · {next_local}", "url": encoded_url("과목별학원", config["slug"], next_local)},
            ]
        )
        return items

    def schema(local: str, manuscript: dict[str, object], center: dict[str, object], representative: str, related: list[dict[str, str]]) -> dict[str, object]:
        data = original_schema(local, manuscript, center, representative, related)
        graph = data.get("@graph", [])
        by_type = {item.get("@type"): item for item in graph if isinstance(item, dict) and isinstance(item.get("@type"), str)}
        page_url = namespace["encoded_url"]("과목별학원", config["slug"], local)
        center_url = str(center.get("center_url") or page_url)
        organization_id = center_url + "#organization"
        local_business_id = center_url + "#localbusiness"
        body_image = str(center.get("body_image", ""))
        body_image_url = body_image if body_image.startswith("http") else SITE_URL + body_image
        subject_about = [
            {"@type": "Thing", "name": config["label"]},
            {"@type": "Thing", "name": f'{config["level"]} 영어 학습'},
            {"@type": "Thing", "name": f'{config["level"]} 수학 학습'},
            {"@type": "Thing", "name": "영어·수학 오답 재학습"},
        ]
        mention_values = mentions(center, local)

        web_page = by_type.get("WebPage", {})
        web_page["publisher"] = {"@id": organization_id}
        web_page["about"] = subject_about
        web_page["mentions"] = mention_values
        web_page["datePublished"] = TODAY
        web_page["dateModified"] = TODAY
        web_page["primaryImageOfPage"] = {"@type": "ImageObject", "url": SITE_URL + representative}
        headings = [str(heading) for heading, _ in manuscript["sections"]]
        keyword_values = [
            manuscript["title"], config["label"], local,
            f'{config["level"]} 영어', f'{config["level"]} 수학',
            *headings[:4],
        ]
        web_page["keywords"] = keyword_values
        web_page["significantLink"] = [str(item["url"]) for item in related[:5]]

        organization = by_type.get("EducationalOrganization", {})
        organization["@id"] = organization_id
        organization["name"] = center["organization_name"]
        organization["alternateName"] = manuscript["title"]
        organization["url"] = center_url
        organization["image"] = body_image_url
        organization["teaches"] = [
            f'{config["level"]} 영어', f'{config["level"]} 수학', "영어 어휘·문법·독해",
            "수학 개념·연산·문제풀이", "영어·수학 오답 재학습",
        ]
        organization["knowsAbout"] = [
            config["label"], f'{config["level"]} 영어 학습', f'{config["level"]} 수학 학습',
            *headings[:4], *[str(school) for school in center.get("schools", [])],
        ]

        local_business = by_type.get("LocalBusiness", {})
        local_business["@id"] = local_business_id
        local_business["name"] = center["organization_name"]
        local_business["alternateName"] = manuscript["title"]
        local_business["url"] = center_url
        local_business["image"] = body_image_url

        article = by_type.get("Article", {})
        article["author"] = {"@id": organization_id}
        article["publisher"] = {"@id": organization_id}
        article["articleSection"] = [config["label"], center.get("region", ""), center.get("city", ""), local, *[heading for heading, _ in manuscript["sections"]]]
        article["about"] = subject_about
        article["mentions"] = mention_values
        article["datePublished"] = TODAY
        article["dateModified"] = TODAY
        article["abstract"] = str(manuscript.get("summary") or manuscript.get("meta", ""))
        article["keywords"] = keyword_values
        article["isAccessibleForFree"] = True
        article_text = [*manuscript.get("intro", [])]
        for heading, paragraphs in manuscript.get("sections", []):
            article_text.append(str(heading))
            article_text.extend(str(paragraph) for paragraph in paragraphs)
        article["wordCount"] = len(re.findall(r"\S+", " ".join(str(value) for value in article_text)))
        article["audience"] = {
            "@type": "EducationalAudience",
            "educationalRole": "student",
            "audienceType": " · ".join(str(grade) for grade in center.get("grades", [])),
        }

        service = by_type.get("Service", {})
        service["name"] = f'{manuscript["title"]} 학습관리'
        service["serviceType"] = config["label"]
        service["provider"] = {"@id": organization_id}
        service["about"] = subject_about[1:]
        service["mentions"] = mention_values
        service["category"] = [f'{config["level"]} 영어 학습', f'{config["level"]} 수학 학습']
        service["audience"] = {
            "@type": "EducationalAudience",
            "educationalRole": "student",
            "audienceType": " · ".join(str(grade) for grade in center.get("grades", [])),
        }
        return data

    def render_page(local: str, index: int, order: list[str], manuscript: dict[str, object], center: dict[str, object], representative: str) -> str:
        output = original_render_page(local, index, order, manuscript, center, representative)
        answer_heading = html.escape(str(manuscript.get("answer_heading") or f'{local} {config["label"]} 판단 기준'))
        answer_text = html.escape(str(manuscript.get("answer_text") or manuscript.get("summary", "")))
        answer_tags = "".join(
            f"<span>{html.escape(str(tag))}</span>"
            for tag in manuscript.get("answer_tags", [])
        )
        answer_panel = (
            f'<aside class="math-hero-panel"><strong>{answer_heading}</strong>'
            f'<p>{answer_text}</p><div class="math-step-row">{answer_tags}</div></aside>'
        )
        output = re.sub(
            r'<aside class="math-hero-panel">.*?</aside>',
            lambda _match: answer_panel,
            output,
            count=1,
            flags=re.DOTALL,
        )
        output = output.replace(
            f"{local} 영어 상담은 현재 읽고 쓰는 과정부터 확인합니다",
            f'{local} {config["level"]} 영수 상담은 두 과목의 현재 학습 기록부터 확인합니다',
        )
        output = output.replace(
            "최근 교재와 시험지를 바탕으로 어휘, 문법, 독해 근거, 서술형 표현과 복습 순서를 나누어 살펴보세요.",
            "최근 영어·수학 교재와 시험지를 바탕으로 과목별 취약 영역, 풀이·답안 과정과 복습 순서를 나누어 살펴보세요.",
        )
        output = output.replace(
            "<dt>영어 수업 가능 학년</dt>",
            f'<dt>{config["level"]} 영어·수학 수업 가능 학년</dt>',
        )
        output = output.replace(
            f"<h2>{local} 영어 상담 참고 사례</h2>",
            f'<h2>{local} {config["level"]} 영수 상담 참고 사례</h2>',
        )
        review_note = (
            f'※ {local} {config["label"]} 상담에서 확인할 수 있는 학습 상황을 재구성한 참고 예시이며, '
            "실제 인물이나 특정 성적 결과를 단정하지 않습니다."
        )
        output = re.sub(
            r'<p class="math-review-note">.*?</p>',
            f'<p class="math-review-note">{html.escape(review_note)}</p>',
            output,
            count=1,
            flags=re.DOTALL,
        )
        return output

    def hub_faq() -> list[dict[str, object]]:
        level = config["level"]
        label = config["label"]
        return [
            {
                "@type": "Question",
                "name": f"동네별 {label} 페이지에서는 무엇을 확인할 수 있나요?",
                "acceptedAnswer": {"@type": "Answer", "text": f"제공된 지역별 안내 내용과 센터 정보를 바탕으로 {level} 학생의 영어·수학 학습 상태, 학교 자료 활용, 과목별 복습 순서와 상담 준비사항을 확인할 수 있습니다."},
            },
            {
                "@type": "Question",
                "name": f"{label} 상담에는 어떤 자료를 준비하면 좋나요?",
                "acceptedAnswer": {"@type": "Answer", "text": "최근 영어·수학 시험지와 교재, 학교 시험 범위표, 과목별 오답 기록과 일주일 학습 시간표를 준비하면 두 과목의 우선순위와 복습 계획을 구체적으로 살펴볼 수 있습니다."},
            },
            {
                "@type": "Question",
                "name": f"{level} 영어와 수학은 항상 같은 비중으로 공부해야 하나요?",
                "acceptedAnswer": {"@type": "Answer", "text": "두 과목을 같은 시간으로 나누기보다 최근 시험 결과, 취약 영역, 학교 일정과 혼자 복습할 수 있는 시간을 확인해 과목별 우선순위와 주간 분량을 다르게 정하는 편이 좋습니다."},
            },
        ]

    def render_hub(order: list[str], directory: str) -> str:
        output = original_render_hub(order, directory)
        old_description = f'371개 동네별 {config["label"]} 원고와 센터 정보를 바탕으로 어휘·문법·독해·서술형 학습과 상담 전 확인사항을 지역별로 안내합니다.'
        description = f'371개 동네별 {config["label"]} 안내 내용과 센터 정보를 바탕으로 영어·수학 학습 상태, 학교 자료 활용, 과목별 복습과 상담 전 확인사항을 안내합니다.'
        output = output.replace(old_description, description)
        output = output.replace(
            f'{config["label"]} 지역 안내 | 371개 동네별 영어 학습코칭',
            f'{config["label"]} 지역 안내 | 371개 동네별 영어·수학 학습코칭',
        )
        output = output.replace(
            f'371개 동네별 {config["label"]} 안내에서 지역과 학생 상황에 맞는 영어 상담 기준을 확인하세요.',
            f'371개 동네별 {config["label"]} 안내에서 학생 상황에 맞는 영어·수학 상담 기준을 확인하세요.',
        )
        output = output.replace(
            "어휘·문법·독해·서술형을 따로 나열하는 데 그치지 않고, 학생의 학년과 학교 자료, 복습 가능 시간을 함께 놓고 확인할 수 있도록 371개 지역별 안내를 정리했습니다.",
            f'{config["level"]} 학생의 영어와 수학을 한 묶음으로 나열하지 않고, 과목별 강약과 학교 자료, 시험 일정, 복습 가능 시간을 함께 확인할 수 있도록 371개 지역 안내를 정리했습니다.',
        )
        output = output.replace(
            "영어는 현재 읽고 설명하는 과정에서 출발합니다",
            f'{config["level"]} 영수 학습은 두 과목의 현재 기록을 나누어 보는 데서 출발합니다',
        )
        output = output.replace(
            "학년보다 앞선 진도만 묻기보다 어휘 누적, 문장 구조 이해, 독해 근거와 오답 재도전 방식을 함께 확인하세요.",
            "한 과목의 진도만 묻기보다 영어의 어휘·독해, 수학의 개념·풀이와 두 과목의 오답 재학습 방식을 함께 확인하세요.",
        )
        output = output.replace("<span>어휘</span><span>독해</span><span>서술형</span>", "<span>영어</span><span>수학</span><span>복습</span>")
        output = output.replace(
            f'<h2>지역과 학생 상황을 함께 보는 {config["label"]} 안내</h2><p>각 페이지는 제공된 동네별 원고와 센터·학교 자료를 사용합니다. 특정 결과를 약속하기보다 학생이 막히는 영어 영역, 학교 범위 대응, 복습 기록과 상담 준비 기준을 구체적으로 확인하도록 구성했습니다.</p>',
            f'<h2>지역과 학생 상황을 함께 보는 {config["label"]} 안내</h2><p>각 페이지는 제공된 동네별 안내 내용과 센터·학교 자료를 사용합니다. 두 과목의 현재 차이, 학교 범위 대응, 과목별 복습 기록과 상담 준비 기준을 구체적으로 확인하도록 구성했습니다.</p>',
        )
        output = re.sub(
            r'<aside class="math-info-card"><h2>영어 상담 핵심 기준</h2><dl>.*?</dl></aside>',
            f'<aside class="math-info-card"><h2>{config["level"]} 영수 상담 핵심 기준</h2><dl><div><dt>영어</dt><dd>어휘·문법·독해에서 막히는 과정 확인</dd></div><div><dt>수학</dt><dd>개념·연산·문제 해석과 풀이 기록 확인</dd></div><div><dt>학교</dt><dd>시험 범위와 제공 자료의 활용 방식 점검</dd></div><div><dt>복습</dt><dd>과목별 오답 원인과 일정 뒤 재풀이</dd></div></dl></aside>',
            output,
            count=1,
            flags=re.DOTALL,
        )
        faqs = hub_faq()
        faq_markup = "".join(
            f'<details class="math-faq-item"{" open" if index == 0 else ""}><summary>{html.escape(str(item["name"]))}</summary><p>{html.escape(str(item["acceptedAnswer"]["text"]))}</p></details>'
            for index, item in enumerate(faqs)
        )
        output = re.sub(
            r'(<div class="math-faq-list">).*?(</div></div></section>)',
            lambda match: match.group(1) + faq_markup + match.group(2),
            output,
            count=1,
            flags=re.DOTALL,
        )
        output = re.sub(
            r'<h2>영어 상담 전 함께 보면 좋은 안내</h2><div class="math-links">.*?</div>',
            f'<h2>{config["level"]} 영수 상담 전 함께 보면 좋은 안내</h2><div class="math-links"><a href="/교육정보/영어-공부법/">영어 공부법</a><a href="/교육정보/수학-공부법/">수학 공부법</a><a href="/교육정보/오답노트-작성법/">오답노트 작성</a><a href="/center/">전국센터 찾기</a></div>',
            output,
            count=1,
            flags=re.DOTALL,
        )

        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', output, re.DOTALL)
        if not match:
            raise ValueError(f'{config["slug"]}: hub JSON-LD not found')
        data = json.loads(match.group(1))
        for item in data.get("@graph", []):
            if item.get("@type") == "CollectionPage":
                item["description"] = description
                item["about"] = [
                    {"@type": "Thing", "name": config["label"]},
                    {"@type": "Thing", "name": f'{config["level"]} 영어 학습'},
                    {"@type": "Thing", "name": f'{config["level"]} 수학 학습'},
                ]
                item["datePublished"] = TODAY
                item["dateModified"] = TODAY
            elif item.get("@type") == "FAQPage":
                item["mainEntity"] = faqs
        output = output[:match.start(1)] + compact_json(data) + output[match.end(1):]
        output = output.replace("원고", "안내 내용")
        return output

    namespace["naturalize_text"] = naturalize
    namespace["parse_reviews"] = flexible_reviews
    namespace["extract_center_data"] = center_data
    namespace["load_manuscripts"] = manuscripts
    namespace["make_mentions"] = mentions
    namespace["internal_links"] = links
    namespace["page_schema"] = schema
    namespace["render_page"] = render_page
    namespace["render_hub"] = render_hub
    namespace["select_representatives"] = lambda order: representative_mapping(order, config)
    namespace["update_subject_hub"] = lambda: None


def update_master_subject_hub(namespaces: dict[str, dict[str, object]]) -> None:
    path = ROOT / "과목별학원" / "index.html"
    source = path.read_text(encoding="utf-8")
    insert_at = re.search(r'<a class="subject-category-card" id="high-math".*?</a>', source, re.DOTALL)
    if not insert_at:
        raise ValueError("high-school math category card not found")

    cards: list[str] = []
    for config in CATEGORIES:
        card = (
            f'<a class="subject-category-card" id="{config["card_id"]}" data-number="{config["card_number"]}" '
            f'href="./{config["slug"]}/"><small>{config["card_small"]}</small><h3>{config["label"]}</h3>'
            f'<p>{config["card_copy"]}</p><span class="subject-status">371개 지역 안내 보기 →</span></a>'
        )
        pattern = rf'<a class="subject-category-card" id="{re.escape(config["card_id"])}".*?</a>'
        if re.search(pattern, source, re.DOTALL):
            source = re.sub(pattern, card, source, count=1, flags=re.DOTALL)
        else:
            cards.append(card)
    if cards:
        insertion = "\n          " + "\n          ".join(cards)
        source = source[:insert_at.end()] + insertion + source[insert_at.end():]

    description = "수학학원·영어학원과 고등·중등·초등 영수학원 등 7개 지역별 안내를 학생의 학년과 학습 상황에 맞춰 확인할 수 있습니다."
    source = re.sub(r'(<meta name="description" content=")[^"]*(">)', rf'\g<1>{description}\g<2>', source, count=1)
    source = re.sub(
        r'(<meta property="og:description" content=")[^"]*(">)',
        r'\g<1>수학·영어 단과와 학년별 영수학원 지역 안내를 현재 학년과 두 과목의 학습 상태에 맞춰 확인할 수 있습니다.\g<2>',
        source,
        count=1,
    )
    source = source.replace(
        "현재 제공 중인 수학·영어 안내를 과목과 학년으로 구분했습니다. 학생의 시험지, 오답, 공부 습관을 기준으로 필요한 지역별 학습 안내를 바로 선택할 수 있습니다.",
        "수학·영어 단과와 고등·중등·초등 영수 안내를 과목과 학년으로 구분했습니다. 최근 시험지, 과목별 오답과 공부 습관을 기준으로 필요한 지역별 학습 안내를 선택할 수 있습니다.",
    )
    source = source.replace(
        "실제 지역 페이지가 준비된 네 가지 분류만 표시합니다.",
        "실제 지역 페이지가 준비된 일곱 가지 분류만 표시합니다.",
    )
    source = source.replace(
        "과목별학원은 수학학원·영어학원처럼 필요한 과목을 먼저 선택한 뒤 해당 동네의 학습 안내를 확인하는 구조입니다.",
        "과목별학원은 수학·영어 단과 또는 학년별 영수학원을 먼저 선택한 뒤 해당 동네의 학습 안내를 확인하는 구조입니다.",
    )

    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
    if not match:
        raise ValueError("master subject hub JSON-LD not found")
    data = json.loads(match.group(1))
    topics = [
        ("수학학원", "수학학원"),
        ("영어학원", "영어학원"),
        ("고등 영어학원", "고등영어학원"),
        ("고등 수학학원", "고등수학학원"),
        *[(config["label"], config["slug"]) for config in CATEGORIES],
    ]
    encoded_url = next(iter(namespaces.values()))["encoded_url"]
    for item in data.get("@graph", []):
        if item.get("@type") == "EducationalOrganization":
            current = list(item.get("knowsAbout", []))
            for name, _ in topics:
                if name not in current:
                    current.append(name)
            item["knowsAbout"] = current
        elif item.get("@type") == "CollectionPage":
            item["description"] = description
            item["about"] = [{"@type": "Thing", "name": name} for name, _ in topics]
            item["dateModified"] = TODAY
        elif item.get("@type") == "ItemList" and str(item.get("@id", "")).endswith("#topics"):
            item["numberOfItems"] = len(topics)
            item["itemListElement"] = [
                {
                    "@type": "ListItem",
                    "position": position,
                    "item": {"@type": "Thing", "name": name, "url": encoded_url("과목별학원", slug)},
                }
                for position, (name, slug) in enumerate(topics, start=1)
            ]
        elif item.get("@type") == "FAQPage":
            for faq in item.get("mainEntity", []):
                if faq.get("name") == "과목별학원 페이지는 전국센터 페이지와 무엇이 다른가요?":
                    faq["acceptedAnswer"]["text"] = "전국센터는 지역과 센터를 기준으로 찾는 구조이고, 과목별학원은 수학·영어 단과 또는 학년별 영수학원을 먼저 선택한 뒤 해당 동네의 학습 안내를 확인하는 구조입니다."
    source = source[:match.start(1)] + compact_json(data) + source[match.end(1):]
    path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    namespaces: dict[str, dict[str, object]] = {}
    for config in CATEGORIES:
        namespace = transformed_namespace(config)
        configure_namespace(namespace, config)
        namespace["main"]()
        namespaces[config["slug"]] = namespace
        print(f'{config["slug"]}: generated 371 detail pages and one hub')
    update_master_subject_hub(namespaces)
    print("updated master subject hub with seven live categories")


if __name__ == "__main__":
    main()
