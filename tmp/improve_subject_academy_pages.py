from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_URL = "https://wawa-center.kr"
CATEGORIES = ("수학학원", "영어학원", "고등영어학원", "고등수학학원")


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def graph_item(graph: list[dict[str, object]], type_name: str) -> dict[str, object]:
    return next((item for item in graph if item.get("@type") == type_name), {})


def center_url_from_graph(graph: list[dict[str, object]]) -> str:
    item_list = graph_item(graph, "ItemList")
    return next(
        (
            str(item.get("url", ""))
            for item in item_list.get("itemListElement", [])
            if "/center/" in str(item.get("url", ""))
        ),
        "",
    )


def replace_references(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: replace_references(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_references(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def rotate(values: list[str], offset: int) -> list[str]:
    offset %= len(values)
    return values[offset:] + values[:offset]


LIST_CONNECTORS = [
    " 항목을 같은 순서로 놓고 ",
    " 항목 각각이 ",
    " 항목을 기준으로 ",
    " 항목을 함께 살피며 ",
    " 항목 가운데 빠진 부분 없이 ",
    " 항목을 순서대로 짚어 ",
]


def varied_sentence(index: int, openings: list[str], points: list[str], endings: list[str]) -> str:
    opening = openings[index % len(openings)]
    point_offset = (index // len(openings)) % len(points)
    ending = endings[(index // (len(openings) * len(points))) % len(endings)]
    ordered = "·".join(rotate(points, point_offset))
    connector = LIST_CONNECTORS[index % len(LIST_CONNECTORS)]
    return f"{opening} {ordered}{connector}{ending}"


def vary_existing_article_connectors(source: str, index: int) -> str:
    article_match = re.search(r'(<article class="math-narrow math-article">)(.*?)(</article>)', source, re.DOTALL)
    if not article_match:
        return source
    occurrence = 0

    def replace_connector(match: re.Match[str]) -> str:
        nonlocal occurrence
        connector = LIST_CONNECTORS[(index + occurrence) % len(LIST_CONNECTORS)]
        occurrence += 1
        return match.group(1) + connector

    article = re.sub(r"((?:[^.!?<>\n]*·){3,}[^.!?<>\n]*) 항목이 ", replace_connector, article_match.group(2))
    return source[: article_match.start(2)] + article + source[article_match.end(2) :]


CHECK_ENDINGS = [
    "한 흐름으로 이어지는지 구체적으로 확인해야 합니다.",
    "서로 분리되지 않고 실제 수업 계획에 반영되는지 살펴보는 편이 좋습니다.",
    "학생의 주간 계획 안에서 언제 확인되는지 질문해야 합니다.",
    "기록과 피드백으로 남는지 비교하면 수업 차이를 판단하기 쉽습니다.",
    "상담 설명에 그치지 않고 실행 과정에서 확인되는지 점검해야 합니다.",
    "학생의 현재 어려움과 연결되는지 순서대로 확인하는 것이 좋습니다.",
    "수업 전후의 행동 변화로 이어지는지 확인해야 선택 기준이 분명해집니다.",
    "누가 언제 점검하는지까지 물어보면 관리 방식을 구체적으로 비교할 수 있습니다.",
]


def math_replacements(local: str, region_text: str, index: int) -> dict[str, str]:
    travel_openings = [
        f"{local}에서 통학 조건을 비교할 때는",
        f"{region_text} 학생의 실제 이동 부담을 계산하려면",
        f"{local} 수학학원 상담에서 통학 지속성을 확인할 때는",
        f"{local} 가정이 등원 일정을 검토할 때는",
        f"{region_text}에서 수업 시간표를 정할 때는",
        f"{local} 학생의 하교 이후 동선을 살펴볼 때는",
        f"{local} 수학 수업의 이동 조건을 비교할 때는",
        f"{region_text} 학부모가 통학 계획을 세울 때는",
    ]
    travel_points = ["하교 시간", "출발 위치", "수업 종료 시각", "귀가 방식", "다른 과목 일정", "주간 등원 횟수"]
    lesson_openings = [
        f"{local} 수학 상담에서 실제 수업 시간을 확인할 때는",
        f"{region_text} 학생에게 맞는 수업 흐름을 비교하려면",
        f"{local} 수학 수업의 참여 방식을 살펴볼 때는",
        f"{local} 학부모가 강의식 설명과 학생 활동을 구분하려면",
        f"{region_text}에서 수학 학습관리를 상담할 때는",
        f"{local} 학생의 독립 풀이 시간을 확인하려면",
        f"{local} 수학학원의 수업 구성을 비교할 때는",
        f"{region_text} 학부모가 진도표 이면의 과정을 확인할 때는",
    ]
    lesson_points = ["학생의 직접 설명", "해설 없는 재풀이", "질문 전 시도", "오답 수정", "변형 문항 확인", "다음 회차 재점검"]
    diagnosis_openings = [
        f"{local} 수학 진단의 근거를 남길 때는",
        f"{region_text} 학생의 현재 수준을 확인하려면",
        f"{local} 상담에서 정답률 이외의 정보를 살펴볼 때는",
        f"{local} 학생의 문제 해결 과정을 기록할 때는",
        f"{region_text} 학부모가 진단 결과를 비교할 때는",
        f"{local} 수학학원 상담에서 첫 계획을 세우려면",
        f"{local} 학생의 도움 의존도를 구분하려면",
        f"{region_text}에서 수학 진단의 실효성을 확인할 때는",
    ]
    diagnosis_points = ["첫 시도 시간", "질문 전 시도한 방법", "해설 뒤 독립 재현", "조건 표시", "풀이 근거 설명", "재확인 날짜"]
    return {
        f"{local} 단위로 수학학원을 비교하더라도 하교 후 출발 위치, 수업 종료 시각, 귀가 방식이 달라지면 실제 체감 거리는 달라질 수 있습니다.": varied_sentence(index + 31, travel_openings, travel_points, CHECK_ENDINGS),
        f"{local} 상담에서는 강의 진도표뿐 아니라 학생이 직접 설명하는 시간과 해설 없이 다시 푸는 시간이 실제로 확보되는지 질문하는 것이 좋습니다.": varied_sentence(index + 173, lesson_openings, lesson_points, CHECK_ENDINGS),
        f"{local} 상담에서는 정답 여부뿐 아니라 첫 시도 시간, 질문 전 시도한 방법, 해설 뒤 독립 재현 여부를 기록해 달라고 요청하는 것이 좋습니다.": varied_sentence(index + 307, diagnosis_openings, diagnosis_points, CHECK_ENDINGS),
    }


def english_replacements(local: str, region_text: str, address_text: str, index: int) -> dict[str, str]:
    compare_openings = [
        f"{local} 영어학원을 비교할 때는",
        f"{region_text}의 영어 수업을 알아볼 때는",
        f"{local}에서 영어 학습관리를 상담할 때는",
        f"{local} 영어 수업의 운영 방식을 살펴볼 때는",
        f"{region_text} 학부모가 영어학원을 선택할 때는",
        f"{local} 영어 상담 내용을 서로 비교할 때는",
        f"{local}에서 학생에게 맞는 영어 수업을 찾을 때는",
        f"{region_text}의 영어 학습 계획을 검토할 때는",
    ]
    compare_points = ["학교 시험 범위 반영", "지문 해석 기준", "단어 누적 관리", "오답 복습 간격", "과제 점검", "피드백 주기"]
    schedule_openings = [
        f"{region_text} 학생의 영어 복습 시간을 점검할 때는",
        f"{local} 학생이 복습을 미루는 시점을 살펴보면",
        f"{local}에서 주간 영어 계획을 세울 때는",
        f"{region_text} 학생의 실제 공부 가능 시간을 계산할 때는",
        f"{local} 영어 과제가 밀리는 원인을 확인할 때는",
        f"{local} 학생의 일주일 학습 흐름을 정리할 때는",
        f"{region_text}에서 영어 복습 간격을 조정할 때는",
        f"{local} 학생이 혼자 복습할 시간을 확보하려면",
    ]
    schedule_points = ["학교 일정", "수행평가", "다른 과목 학습", "등원 시간", "과제 분량", "시험 준비 기간"]
    operation_openings = [
        f"{region_text}에서 영어학원을 찾는 보호자는",
        f"{local} 영어 상담을 준비하는 학부모는",
        f"{local}에서 수업 운영을 확인할 때는",
        f"{region_text} 학부모가 영어 수업을 비교하려면",
        f"{local} 영어학원 방문 전에는",
        f"{local}에서 학습관리를 상담할 때는",
        f"{region_text}의 영어 수업 정보를 검토할 때는",
        f"{local} 학생에게 맞는 수업을 고르려면",
    ]
    operation_points = ["수업 시간과 비용", "진단 방식", "학교 자료 반영", "숙제 기준", "결석 보완", "학부모 피드백"]
    purpose_openings = [
        f"{local} 영어학원 페이지에서는",
        f"{region_text} 영어 학습 안내에서는",
        f"{local} 학부모가 이 페이지를 확인할 때는",
        f"{local} 영어 상담 기준을 정리하면",
        f"{region_text}에서 영어학원을 알아보는 과정에서는",
        f"{local} 학생의 수업 적합성을 판단하려면",
        f"{local} 영어 학습 정보를 활용할 때는",
        f"{region_text} 학부모의 실제 질문을 기준으로 보면",
    ]
    purpose_points = ["현재 수준 진단", "학교 자료 확인", "복습 관리", "상담 준비", "통학 지속성", "다음 점검 계획"]
    diagnosis_points = ["최근 시험지 진단", "교재 난도", "취약 영역", "설명 방식", "피드백 주기", "다음 점검 기준"]
    address_points = ["실제 이동 시간", "수업 시간", "과제 확인", "오답 재풀이", "귀가 방식", "가정 학습 일정"]
    return {
        f"{local} 영어학원을 비교할 때는 수강료나 시간표만 보지 말고 학교 시험 범위, 지문 해석 방식, 단어 누적 관리, 오답 복습 간격이 실제로 연결되는지 확인해야 합니다.": varied_sentence(index, compare_openings, compare_points, CHECK_ENDINGS),
        f"{region_text} 학생은 학교 일정, 수행평가, 다른 과목 학습이 겹치면 영어 복습이 뒤로 밀리기 쉽습니다.": varied_sentence(index + 73, schedule_openings, schedule_points, CHECK_ENDINGS),
        f"{region_text}에서 영어학원을 찾는 보호자는 학원 운영 정보와 학습 관리 정보를 함께 확인해야 합니다.": varied_sentence(index + 149, operation_openings, operation_points, CHECK_ENDINGS),
        f"{region_text} 학부모님은 아이가 학원에 다녀온 뒤 무엇을 다시 봐야 하는지 모를 때 답답함을 느끼기 쉽습니다.": varied_sentence(index + 211, schedule_openings, purpose_points, CHECK_ENDINGS),
        f"{region_text}에서 영어학원을 알아보는 과정은 결국 아이가 혼자 공부할 수 있는 구조를 만들 수 있는지 확인하는 일입니다.": varied_sentence(index + 277, purpose_openings, purpose_points, CHECK_ENDINGS),
        f"{local} 영어학원 페이지의 핵심은 지역명만 바꾼 소개가 아니라 {region_text} 학부모가 실제로 묻는 진단, 학교 자료, 복습 관리, 상담 준비를 한 페이지에서 확인하도록 돕는 데 있습니다.": varied_sentence(index + 331, purpose_openings, purpose_points, CHECK_ENDINGS),
        f"{local} 영어학원을 검토할 때는 빠른 진도보다 정확한 진단과 꾸준한 피드백을 우선으로 보셔야 합니다.": varied_sentence(index + 389, operation_openings, diagnosis_points, CHECK_ENDINGS),
        f"{region_text} 학부모님은 주소 {address_text}와 함께 수업 시간, 과제 확인, 오답 재풀이 방식이 가정 일정과 맞는지 확인하면 더 현실적인 선택을 할 수 있습니다.": varied_sentence(index + 443, schedule_openings, address_points, CHECK_ENDINGS),
        f"주소는 {address_text}이며, 학생별 수업 적합성은 현재 교재와 최근 오답을 함께 본 뒤 판단하는 것이 좋습니다.": varied_sentence(index + 509, purpose_openings, diagnosis_points, CHECK_ENDINGS),
        f"{local} 영어학원 상담에서는 숙제량뿐 아니라 미완료 과제 처리, 오답 재풀이 날짜, 학부모 피드백 방식까지 질문해 보시는 것이 좋습니다.": varied_sentence(index + 571, operation_openings, ["미완료 과제 처리", "오답 재풀이 날짜", "학부모 피드백", "숙제 기준", "결석 보완", "다음 점검 시점"], CHECK_ENDINGS),
        f"{local} 영어학원의 커리큘럼은 학생 상태에 따라 어휘 누적, 문법 적용, 지문 구조 분석, 시험 범위 암기를 다르게 배치해야 합니다.": varied_sentence(index + 631, purpose_openings, ["어휘 누적", "문법 적용", "지문 구조 분석", "시험 범위 암기", "서술형 재작성", "주간 복습"], CHECK_ENDINGS),
        f"{local} 영어학원은 이런 질문을 중심으로 비교할 때 정보성 판단이 가능합니다.": varied_sentence(index + 691, compare_openings, compare_points, CHECK_ENDINGS),
    }


def high_english_replacements(local: str, region_text: str, index: int) -> dict[str, str]:
    material_openings = [
        f"{local} 고등 영어의 학교 자료를 관리할 때는",
        f"{region_text}에서 내신 영어 대비 방식을 확인하려면",
        f"{local} 고등 영어학원 상담에서 학교 자료 활용을 물어볼 때는",
        f"{local} 학생의 실제 시험 범위를 정리할 때는",
        f"{region_text} 학부모가 공통 교재와 학교 자료를 구분하려면",
        f"{local} 고등 영어 수업의 내신 준비 과정을 비교할 때는",
        f"{local}에서 학교별 영어 계획을 세울 때는",
        f"{region_text} 학생의 내신 자료를 목록화할 때는",
    ]
    material_points = ["교과서 본문", "부교재", "학교 프린트", "서술형 과제", "시험 범위표", "수업 필기"]
    process_openings = [
        f"{local} 고등 영어 수업의 관리 흐름을 확인할 때는",
        f"{region_text} 학부모가 상담 설명을 검토할 때는",
        f"{local} 학생의 진단 이후 과정을 살펴볼 때는",
        f"{local} 고등 영어학원 선택 기준을 세울 때는",
        f"{region_text}에서 수업 전후의 연결을 비교하려면",
        f"{local} 학부모가 추가로 확인할 질문을 정할 때는",
        f"{local} 고등 영어의 피드백 과정을 점검할 때는",
        f"{region_text} 학생의 주간 학습 흐름을 확인할 때는",
    ]
    process_points = ["진단 근거", "수업 연습", "과제 수행", "오답 수정", "다음 시간 재확인", "학부모 피드백"]
    review_openings = [
        f"{local} 고등 영어의 주간 복습을 설계할 때는",
        f"{region_text} 학생의 재학습 여부를 확인하려면",
        f"{local} 고등 영어학원에서 과제를 점검할 때는",
        f"{local} 학생이 배운 내용을 다시 꺼내 쓰게 하려면",
        f"{region_text} 학부모가 확인 가능한 과제를 비교할 때는",
        f"{local} 고등 영어의 누적 복습 흐름을 살펴볼 때는",
        f"{local}에서 영어 오답을 다음 주까지 연결하려면",
        f"{region_text} 학생의 재확인 기록을 남길 때는",
    ]
    review_points = ["단어 재시험", "같은 지문 재해석", "오답 재풀이", "서술형 재작성", "문법 근거 설명", "다음 주 재확인"]
    return {
        f"{local} 고등 영어학원에서는 학교 자료를 공통 독해 교재와 섞지 않고 별도로 목록화하며, 교과서 본문과 부교재, 프린트, 서술형 과제를 구분해 관리하는지 확인해야 합니다.": varied_sentence(index + 43, material_openings, material_points, CHECK_ENDINGS),
        f"{local} 학부모는 이 흐름이 설명되지 않을 때 추가 질문을 남기는 편이 좋습니다.": varied_sentence(index + 179, process_openings, process_points, CHECK_ENDINGS),
        f"{local} 고등 영어학원에서는 주간 단어 재시험, 같은 지문 재해석, 오답 재풀이, 서술형 재작성처럼 다시 확인할 수 있는 과제를 남기는지가 중요합니다.": varied_sentence(index + 311, review_openings, review_points, CHECK_ENDINGS),
    }


def high_math_replacements(local: str, region_text: str, index: int) -> dict[str, str]:
    school_openings = [
        f"{local}의 학교별 내신 계획을 세울 때는",
        f"{region_text}에서 고등 수학 내신을 준비할 때는",
        f"{local} 고등 수학의 학교별 범위를 정리할 때는",
        f"{local} 학생의 내신 진도를 조정하려면",
        f"{region_text} 학부모가 학교별 대비를 확인할 때는",
        f"{local}에서 시험 전 수학 계획을 다시 세울 때는",
        f"{local} 고등 수학 상담에서 내신 자료를 확인할 때는",
        f"{region_text} 학생의 학교 진도와 개인 진도를 맞추려면",
    ]
    school_points = ["학교 범위표", "수업 필기", "교과서 진도", "서술형 요구", "학교 프린트", "최근 평가 자료"]
    plan_openings = [
        f"{local}에서 학교별 내신 준비 방식을 비교할 때는",
        f"{region_text}의 고등 수학 수업을 검토할 때는",
        f"{local} 학부모가 내신 대비의 실제 과정을 확인하려면",
        f"{local} 고등 수학의 시험 전 계획을 살펴볼 때는",
        f"{region_text}에서 학교 자료 활용 방식을 물어볼 때는",
        f"{local} 학생의 주간 내신 계획을 점검할 때는",
        f"{local} 고등 수학 상담에서 학교 대응을 확인할 때는",
        f"{region_text} 학부모가 학교명 홍보와 실제 대비를 구분하려면",
    ]
    plan_points = ["학교 정보", "주간 진도표", "시험 전 보완 계획", "오답 회수 일정", "서술형 점검", "범위 변경 대응"]
    compare_openings = [
        f"{local} 고등 수학학원을 검토할 때는",
        f"{region_text}에서 고등 수학 수업을 비교할 때는",
        f"{local} 고등 수학 상담 전에는",
        f"{local} 학생에게 맞는 수업을 고르려면",
        f"{region_text} 학부모가 여러 수업의 차이를 확인할 때는",
        f"{local}에서 학습관리 조건을 비교할 때는",
        f"{local} 고등 수학 수업의 운영 기준을 살펴볼 때는",
        f"{region_text}의 고등 수학 학원을 알아볼 때는",
    ]
    compare_points = ["반 인원", "질문 방식", "숙제 기준", "결석 보완", "피드백 주기", "비용 범위"]
    diagnosis_openings = [
        f"{local}에서 진단 결과를 수업과 연결하려면",
        f"{region_text} 고등 수학 상담에서 진단 활용을 확인할 때는",
        f"{local} 학생의 진단 뒤 계획을 살펴볼 때는",
        f"{local} 고등 수학 수업의 시작점을 판단하려면",
        f"{region_text} 학부모가 진단의 실효성을 확인할 때는",
        f"{local}에서 현재 수준에 맞는 수업을 찾으려면",
        f"{local} 고등 수학 상담 결과를 비교할 때는",
        f"{region_text} 학생의 취약점을 수업에 반영하려면",
    ]
    diagnosis_points = ["진단 결과", "반 편성", "설명 속도", "과제 난도", "질문 시간", "재점검 일정"]
    record_openings = [
        f"{local}의 고등 수학 학습 기록을 남길 때는",
        f"{region_text} 학생의 오답 관리를 확인할 때는",
        f"{local}에서 과제 완료 이후를 점검하려면",
        f"{local} 고등 수학의 재학습 과정을 살펴볼 때는",
        f"{region_text} 학부모가 학습관리 기록을 확인할 때는",
        f"{local} 학생의 오답이 다시 반복되지 않게 하려면",
        f"{local} 고등 수학 수업의 점검 과정을 비교할 때는",
        f"{region_text}에서 주간 학습 결과를 정리할 때는",
    ]
    record_points = ["틀린 이유", "질문 내용", "재풀이 날짜", "도움 없이 푼 결과", "다음 복습 범위", "과제 조정 근거"]
    feedback_openings = [
        f"{region_text} 학부모에게 학습 피드백을 전달할 때는",
        f"{local} 고등 수학 상담 뒤 피드백을 확인할 때는",
        f"{local} 학생의 주간 변화를 설명하려면",
        f"{region_text}에서 학부모 피드백의 내용을 비교할 때는",
        f"{local} 고등 수학 수업의 점검 결과를 공유할 때는",
        f"{local} 학부모가 다음 학습 계획을 이해하려면",
        f"{region_text} 학생의 학습 과정을 전달할 때는",
        f"{local}에서 수업 이후의 변화를 확인하려면",
    ]
    feedback_points = ["이번 주에 달라진 행동", "완료한 학습 근거", "반복된 어려움", "다음 주 목표", "질문이 남은 단원", "재확인 날짜"]
    level_points = ["혼자 설명할 수 있는 개념", "힌트가 필요한 유형", "현재 학교 범위", "자습 가능 시간", "풀이 기록", "다시 틀리는 문제"]
    grade_points = ["고1의 학습 습관", "고2의 내신 범위 대응", "고3의 실전 시간 관리", "현재 개념 수준", "과제 난도", "복습 가능 시간"]
    exam_points = ["개념 확인", "유형 적용", "서술형 점검", "오답 회수", "지연 시 조정 기준", "시험 직전 재확인"]
    return {
        f"{local}의 학교별 내신 계획은 학교 이름만으로 추정하지 말고 재학 학교가 공지한 범위표, 수업 필기, 교과서 진도, 서술형 요구를 기준으로 다시 짜야 합니다.": varied_sentence(index, school_openings, school_points, CHECK_ENDINGS),
        f"{local}에서 학교별 내신 준비를 확인할 때는 학교 정보가 주간 진도표와 시험 전 보완 계획에 연결되는지 물어야 단순한 학교명 나열과 실질적인 대비를 구분할 수 있습니다.": varied_sentence(index + 61, plan_openings, plan_points, CHECK_ENDINGS),
        f"{local} 고등 수학학원을 검토할 때는 반 인원, 질문 방식, 숙제 기준, 결석 보완, 피드백 주기, 비용 포함 항목을 같은 순서로 물어 여러 곳의 답을 비교하는 편이 좋습니다.": varied_sentence(index + 127, compare_openings, compare_points, CHECK_ENDINGS),
        f"{local}에서 상담할 때는 진단 결과가 반 편성, 설명 속도, 과제 난도에 어떻게 반영되는지 질문해야 정보가 실제 선택 기준이 됩니다.": varied_sentence(index + 193, diagnosis_openings, diagnosis_points, CHECK_ENDINGS),
        f"{local}의 학습 관리는 완료 여부만 체크하는 데서 끝내지 않고, 틀린 이유와 질문 내용, 재풀이 날짜가 함께 남도록 구성해야 합니다.": varied_sentence(index + 257, record_openings, record_points, CHECK_ENDINGS),
        f"{region_text} 학부모에게 전달되는 피드백은 “잘했다”나 “부족하다”보다 이번 주에 바뀐 행동과 다음 주에 확인할 한 가지 목표를 구체적으로 알려주는 편이 유용합니다.": varied_sentence(index + 319, feedback_openings, feedback_points, CHECK_ENDINGS),
        f"{local} 고등 수학학원을 비교하는 학부모라면 학생이 혼자 설명할 수 있는 개념과 힌트가 있어야 풀 수 있는 유형을 따로 적어 가는 것이 좋습니다.": varied_sentence(index + 383, compare_openings, level_points, CHECK_ENDINGS),
        f"{local}의 학년별 계획에서는 같은 관리 방식이라도 고1의 습관 형성과 고3의 실전 시간 관리가 서로 다른 목표를 가진다는 점을 반영해야 합니다.": varied_sentence(index + 449, diagnosis_openings, grade_points, CHECK_ENDINGS),
        f"{local} 고등 수학학원을 고를 때는 학년 이름만으로 반을 고정하기보다 현재 개념 수준, 학교 범위, 자습 가능 시간에 따라 과제와 설명 속도를 조정할 수 있는지 확인해야 합니다.": varied_sentence(index + 521, compare_openings, grade_points, CHECK_ENDINGS),
        f"{local}의 시험 대비 계획은 수업 횟수를 단순히 늘리는 방식보다 각 단계에서 무엇을 확인하고 지연됐을 때 무엇을 줄일지 설명할 수 있어야 합니다.": varied_sentence(index + 587, plan_openings, exam_points, CHECK_ENDINGS),
        f"{region_text} 학부모는 시험이 끝난 뒤 점수만 묻지 말고 시간 부족, 조건 누락, 계산 실수, 서술 근거 중 어떤 항목이 줄었는지 함께 확인하는 편이 좋습니다.": varied_sentence(index + 653, feedback_openings, exam_points, CHECK_ENDINGS),
        f"{local} 수업에서는 설명을 들은 시간보다 학생이 직접 풀이를 적고 수정한 시간이 충분한지 확인해야 개념과 응용의 연결 정도를 판단할 수 있습니다.": varied_sentence(index + 719, diagnosis_openings, level_points, CHECK_ENDINGS),
        f"{local} 수업을 평가할 때는 소개 문구보다 힌트가 몇 단계로 제공되고 오답이 다음 회차에 어떻게 다시 등장하는지 물어보는 편이 유용합니다.": varied_sentence(index + 773, compare_openings, record_points, CHECK_ENDINGS),
        f"{local} 고등 수학학원을 고를 때는 어려운 문제를 많이 푸는 곳인지보다 쉬운 문제의 근거까지 정확히 설명하게 하는지에서 기본적인 수업 품질을 판단할 수 있습니다.": varied_sentence(index + 827, compare_openings, level_points, CHECK_ENDINGS),
    }


def math_meta(local: str, region_text: str, schools: list[str], index: int) -> str:
    school_text = f"{schools[0]}·{schools[1]} 등 학교 자료와 " if len(schools) >= 2 else (f"{schools[0]} 학교 자료와 " if schools else "학교별 수업 자료와 ")
    variants = [
        f"{region_text} 수학학원 상담 전, 현재 학년·취약 단원·오답 관리 기준과 {school_text}센터 주소·등록 정보를 확인하세요.",
        f"{local} 수학학원을 알아보는 학부모를 위해 학년별 진단, 취약 단원과 재풀이 관리, {school_text}상담 전 확인사항을 정리했습니다.",
        f"{region_text} 수학학원 선택에 필요한 시험지 진단, 개념·응용 점검, 오답 재학습과 {school_text}센터 운영 정보를 안내합니다.",
        f"{local} 수학학원 상담에서 확인할 현재 수준, 학교 진도, 풀이 기록과 복습 계획, {school_text}통학·운영 기준을 살펴보세요.",
    ]
    value = variants[index % len(variants)]
    if len(value) > 110:
        value = value.replace("센터 주소·등록 정보를", "주소·등록 정보를").replace("학부모를 위해 ", "")
    return value


def source_info(source: str) -> tuple[dict[str, object], re.Match[str]]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
    if not match:
        raise ValueError("JSON-LD block not found")
    return json.loads(match.group(1)), match


def collect_center_facts() -> dict[str, dict[str, object]]:
    facts: dict[str, dict[str, object]] = {}
    for path in sorted((ROOT / "과목별학원" / "수학학원").glob("*/index.html")):
        source = path.read_text(encoding="utf-8")
        data, _ = source_info(source)
        graph = data.get("@graph", [])
        organization = graph_item(graph, "EducationalOrganization")
        local_business = graph_item(graph, "LocalBusiness")
        service = graph_item(graph, "Service")
        center_url = center_url_from_graph(graph)
        if not center_url:
            raise ValueError(f"center URL missing: {path}")
        offer = next(iter(organization.get("makesOffer", []) or service.get("makesOffer", [])), None)
        page_images = re.findall(r'<img\b[^>]*src="([^"]+)"[^>]*>', source, re.IGNORECASE)
        visible_image = page_images[1] if len(page_images) > 1 else ""
        facts[path.parent.name] = {
            "center_url": center_url,
            "name": organization.get("name", local_business.get("name", "와와학습코칭센터")),
            "telephone": organization.get("telephone", "010-3957-8283"),
            "address": organization.get("address", {}),
            "areaServed": organization.get("areaServed", {"@type": "Place", "name": path.parent.name}),
            "openingHoursSpecification": organization.get("openingHoursSpecification", []),
            "educationalLevel": organization.get("educationalLevel", []),
            "identifier": organization.get("identifier"),
            "tuition_url": offer.get("url", "") if isinstance(offer, dict) else "",
            "image": SITE_URL + visible_image if visible_image.startswith("/") else visible_image,
        }
    return facts


def stable_offer(local: str, tuition_url: str) -> dict[str, object] | None:
    if not tuition_url:
        return None
    return {
        "@type": "Offer",
        "name": f"{local} 영어·수학 학습상담 및 학습관리",
        "itemOffered": {"@type": "Service", "name": f"{local} 영어·수학 학습관리", "serviceType": "학습코칭"},
        "url": tuition_url,
    }


def stabilize_entities(data: dict[str, object], local: str, facts: dict[str, object]) -> dict[str, object]:
    graph = data.get("@graph", [])
    organization = graph_item(graph, "EducationalOrganization")
    local_business = graph_item(graph, "LocalBusiness")
    old_org_id = str(organization.get("@id", ""))
    old_local_id = str(local_business.get("@id", ""))
    center_url = str(facts["center_url"])
    org_id = center_url + "#organization"
    local_id = center_url + "#localbusiness"
    data = replace_references(data, {old_org_id: org_id, old_local_id: local_id})
    graph = data.get("@graph", [])
    organization = graph_item(graph, "EducationalOrganization")
    local_business = graph_item(graph, "LocalBusiness")
    address = facts.get("address", {})
    region_text = " ".join(
        value
        for value in [str(address.get("addressRegion", "")), str(address.get("addressLocality", "")), local]
        if value
    )
    address_text = str(address.get("streetAddress", ""))
    description = f"{facts['name']}은 {region_text} 지역의 영어·수학 학습상담과 학습관리를 안내합니다."
    if address_text:
        description += f" 제공된 주소는 {address_text}이며, 수업 가능 학년과 교습비는 상담 전 최신 안내를 확인합니다."
    offer = stable_offer(local, str(facts.get("tuition_url", "")))
    organization.clear()
    organization.update(
        {
            "@type": "EducationalOrganization",
            "@id": org_id,
            "name": facts["name"],
            "url": center_url,
            "telephone": facts["telephone"],
            "description": description,
            "address": address,
            "areaServed": facts["areaServed"],
            "openingHoursSpecification": facts["openingHoursSpecification"],
            "educationalLevel": facts["educationalLevel"],
            "teaches": ["영어", "수학", "학습코칭"],
        }
    )
    if offer:
        organization["makesOffer"] = [offer]
    if facts.get("identifier"):
        organization["identifier"] = facts["identifier"]
    local_business.clear()
    local_business.update(
        {
            "@type": "LocalBusiness",
            "@id": local_id,
            "name": facts["name"],
            "url": center_url,
            "telephone": facts["telephone"],
            "address": address,
            "areaServed": facts["areaServed"],
            "openingHoursSpecification": facts["openingHoursSpecification"],
            "parentOrganization": {"@id": org_id},
        }
    )
    if facts.get("image"):
        local_business["image"] = facts["image"]
    if offer:
        local_business["makesOffer"] = [offer]
    if facts.get("identifier"):
        local_business["identifier"] = facts["identifier"]
    return data


def improve_page(path: Path, category: str, index: int, facts: dict[str, object]) -> tuple[int, int]:
    source = path.read_text(encoding="utf-8")
    local = path.parent.name
    address = facts.get("address", {})
    region_text = " ".join(
        value
        for value in [str(address.get("addressRegion", "")), str(address.get("addressLocality", "")), local]
        if value
    )
    replaced = 0
    replacements: dict[str, str] = {}
    if category == "수학학원":
        replacements = math_replacements(local, region_text, index)
    elif category == "영어학원":
        replacements = english_replacements(local, region_text, str(address.get("streetAddress", "")), index)
    elif category == "고등영어학원":
        replacements = high_english_replacements(local, region_text, index)
    elif category == "고등수학학원":
        replacements = high_math_replacements(local, region_text, index)
    for old, new in replacements.items():
        if old in source:
            source = source.replace(old, new)
            replaced += 1

    source = source.replace("학생 학생에게", "학생에게").replace("학생 학생이", "학생이")
    source = source.replace("비용 포함 항목·", "비용 범위·").replace("·비용 포함 항목 ", "·비용 범위 ")
    source = re.sub(r"<strong>“([^<]*관점)</strong>", r"<strong>“\1”</strong>", source)
    source = vary_existing_article_connectors(source, index)

    data, match = source_info(source)
    graph = data.get("@graph", [])
    if category == "수학학원":
        article = graph_item(graph, "Article")
        schools = [
            str(item.get("name", ""))
            for item in article.get("mentions", [])
            if isinstance(item, dict) and re.search(r"(?:초|중|고|학교)$", str(item.get("name", "")))
        ]
        description = math_meta(local, region_text, schools, index)
        source = re.sub(
            r'(<meta\s+name="description"\s+content=")[^"]*(")',
            lambda item: item.group(1) + html.escape(description, quote=True) + item.group(2),
            source,
            count=1,
        )
        source = re.sub(
            r'(<meta\s+property="og:description"\s+content=")[^"]*(")',
            lambda item: item.group(1) + html.escape(description, quote=True) + item.group(2),
            source,
            count=1,
        )
        graph_item(graph, "WebPage")["description"] = description

    data = stabilize_entities(data, local, facts)
    _, refreshed = source_info(source)
    source = source[: refreshed.start(1)] + compact_json(data) + source[refreshed.end(1) :]
    path.write_text(source, encoding="utf-8", newline="\n")
    return replaced, len(source)


def main() -> None:
    center_facts = collect_center_facts()
    totals: dict[str, dict[str, int]] = {}
    for category in CATEGORIES:
        files = sorted((ROOT / "과목별학원" / category).glob("*/index.html"))
        replacements = 0
        for index, path in enumerate(files):
            local = path.parent.name
            if local not in center_facts:
                raise ValueError(f"center facts missing: {category}/{local}")
            count, _ = improve_page(path, category, index, center_facts[local])
            replacements += count
        totals[category] = {"pages": len(files), "sentence_replacements": replacements}
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
