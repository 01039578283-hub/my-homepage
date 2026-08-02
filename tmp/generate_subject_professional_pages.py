from __future__ import annotations

import csv
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_subject_combined_pages as shared


ROOT = Path(__file__).resolve().parents[1]
SITE_URL = "https://wawa-center.kr"
SITE_NAME = "와와학습코칭센터"
TODAY = "2026-08-02"
CENTER_INFO_PATH = ROOT.parent / "참고자료" / "공통자료" / "센터정보 정리.csv"


CATEGORIES = (
    {
        "slug": "수학전문학원",
        "label": "수학 전문학원",
        "zip": "수학 전문학원.zip",
        "focus": "math",
        "level": "초·중·고",
        "grade_prefix": "",
        "school_marker": "",
        "eyebrow": "LOCAL MATH SPECIALIST ACADEMY GUIDE",
        "directory": "MATH SPECIALIST ACADEMY DIRECTORY",
        "card_id": "math-specialist",
        "card_number": "08",
        "card_small": "MATH SPECIALIST",
        "card_copy": "현재 개념 수준, 풀이 과정, 서술형 감점과 오답 재풀이 흐름을 지역별 학습 기록과 함께 확인합니다.",
        "study_path": "수학-공부법",
        "study_name": "수학 공부법",
        "subjects": ("수학",),
        "topics": ("수학 개념 진단", "수학 연산 정확도", "수학 문제 해석", "수학 서술형 풀이", "수학 오답 재학습"),
        "hero_copy": "최근 수학 시험지와 풀이 흔적을 바탕으로 개념 이해, 계산 과정, 문제 조건 해석과 오답 재도전 순서를 확인합니다.",
        "hero_tags": (("개념 진단", "풀이 과정", "오답 재학습"), ("현재 단원", "조건 해석", "재풀이 기록"), ("연산 정확도", "서술형 풀이", "주간 복습"), ("시험 범위", "취약 유형", "다음 계획")),
        "hub_lead": "문제 수나 선행 진도만 비교하지 않고 학생이 개념을 설명하고 풀이를 끝까지 이어 가는 과정, 오답을 다시 확인하는 간격까지 살펴볼 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "영어전문학원",
        "label": "영어 전문학원",
        "zip": "영어 전문학원.zip",
        "focus": "english",
        "level": "초·중·고",
        "grade_prefix": "",
        "school_marker": "",
        "eyebrow": "LOCAL ENGLISH SPECIALIST ACADEMY GUIDE",
        "directory": "ENGLISH SPECIALIST ACADEMY DIRECTORY",
        "card_id": "english-specialist",
        "card_number": "09",
        "card_small": "ENGLISH SPECIALIST",
        "card_copy": "어휘 누적, 문법 적용, 독해 근거와 서술형 표현을 학교 자료와 복습 기록을 기준으로 점검합니다.",
        "study_path": "영어-공부법",
        "study_name": "영어 공부법",
        "subjects": ("영어",),
        "topics": ("영어 어휘 누적", "영어 문법 적용", "영어 독해 근거", "영어 서술형 표현", "영어 오답 재학습"),
        "hero_copy": "최근 영어 시험지와 교재를 바탕으로 어휘, 문법, 독해 근거, 서술형 표현과 수업 이후 복습 순서를 나누어 확인합니다.",
        "hero_tags": (("어휘 누적", "문법 적용", "독해 근거"), ("문장 구조", "서술형 표현", "오답 복습"), ("학교 범위", "답안 근거", "주간 복습"), ("현재 독해", "취약 문법", "다음 계획")),
        "hub_lead": "단어 암기량만 비교하지 않고 문장 구조를 이해하는 과정, 독해 답의 근거, 서술형 표현과 오답 복습까지 살펴볼 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "영수전문학원",
        "label": "영수 전문학원",
        "zip": "영수 전문학원.zip",
        "focus": "combined",
        "level": "초·중·고",
        "grade_prefix": "",
        "school_marker": "",
        "eyebrow": "LOCAL ENGLISH & MATH SPECIALIST GUIDE",
        "directory": "ENGLISH & MATH SPECIALIST DIRECTORY",
        "card_id": "combined-specialist",
        "card_number": "10",
        "card_small": "ENGLISH & MATH SPECIALIST",
        "card_copy": "영어와 수학의 현재 차이, 과목별 우선순위, 주간 계획과 오답 재학습 흐름을 함께 살펴봅니다.",
        "study_path": "오답노트-작성법",
        "study_name": "오답노트 작성법",
        "subjects": ("영어", "수학"),
        "topics": ("영어 어휘·문법·독해", "수학 개념·연산·문제풀이", "영어·수학 과목별 우선순위", "주간 학습계획", "영어·수학 오답 재학습"),
        "hero_copy": "최근 영어·수학 교재와 시험지를 바탕으로 두 과목의 취약 영역, 답안·풀이 과정과 서로 다른 복습 순서를 확인합니다.",
        "hero_tags": (("영어 진단", "수학 진단", "과목별 복습"), ("학교 범위", "두 과목 우선순위", "주간 계획"), ("영어 답안", "수학 풀이", "오답 재학습"), ("현재 상태", "학습량 조정", "다음 점검")),
        "hub_lead": "영어와 수학을 같은 분량으로 묶기보다 두 과목의 현재 차이, 학교 일정, 혼자 복습할 수 있는 시간을 나누어 살펴볼 수 있도록 371개 지역 안내를 정리했습니다.",
    },
)


ALL_TOPICS = (
    ("수학학원", "수학학원"),
    ("영어학원", "영어학원"),
    ("고등 영어학원", "고등영어학원"),
    ("고등 수학학원", "고등수학학원"),
    ("고등 영수학원", "고등영수학원"),
    ("중등 영수학원", "중등영수학원"),
    ("초등 영수학원", "초등영수학원"),
    *((config["label"], config["slug"]) for config in CATEGORIES),
)


def split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，]", value or "") if item.strip()]


def unique_values(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def load_center_rows() -> dict[str, dict[str, str]]:
    with CENTER_INFO_PATH.open(encoding="utf-8-sig", newline="") as file:
        return {
            row["근처 수업가능 동네"].strip(): row
            for row in csv.DictReader(file)
            if row.get("근처 수업가능 동네", "").strip()
        }


CENTER_ROWS = load_center_rows()


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clean_manuscript_text(value: str, local: str) -> str:
    replacements = {
        "학부모라면 학부모가": "학부모라면",
        "질문 목록가": "질문 목록이",
        "는지점을": "는 지점을",
        "수업학교": "수업 가능 학교",
        "정보성 원고": "정보성 안내",
        "원고 형태": "안내 형식",
        "검색 의도": "상담 질문",
        "운영 키워드": "운영 항목",
        "참고 키워드": "참고 항목",
        "핵심 키워드": "핵심 학습 항목",
        "키워드": "학습 항목",
        "구조화 데이터 설명문": "페이지 핵심 요약",
        "구조화 데이터 설명": "페이지 핵심 요약",
        "구조화 데이터": "핵심 안내",
        "학원로": "학원으로",
    }
    text = value
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"D열에\s*(?:입력|제공)된\s*학교명", "제공된 학교명", text)
    text = re.sub(r"D열에\s*학교명이\s*입력되어\s*있지\s*않은", "제공 자료에 학교명이 없는", text)
    text = text.replace("D열 학교명이", "제공된 학교명이")
    text = text.replace("D열", "제공 학교 자료")
    guarded = (
        (r"(?<![가-힣])원고에서는", "페이지에서는"),
        (r"(?<![가-힣])원고에서", "페이지에서"),
        (r"(?<![가-힣])원고에는", "페이지에는"),
        (r"(?<![가-힣])원고에", "페이지에"),
        (r"(?<![가-힣])원고의", "페이지의"),
        (r"(?<![가-힣])원고를", "안내 내용을"),
        (r"(?<![가-힣])원고로", "페이지로"),
        (r"(?<![가-힣])원고가", "페이지가"),
        (r"(?<![가-힣])원고는", "페이지는"),
        (r"(?<![가-힣])원고(?![가-힣])", "페이지"),
    )
    for pattern, replacement in guarded:
        text = re.sub(pattern, replacement, text)
    text = text.replace(f"{local} {local}", local)
    return re.sub(r"[ \t]+", " ", text)


def reader_facing_text(value: str, local: str, config: dict[str, object]) -> str:
    """Remove production-language residue without changing supplied facts."""
    text = value
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 페이지는 (.*?)을 설명하는 지역 기반 학원 원고입니다\.",
        rf"{local} {config['label']}에서는 \1을 상담 전에 구체적으로 확인할 수 있습니다.",
        text,
    )
    text = re.sub(
        r"([가-힣A-Za-z0-9 ·]+?)의 영수 전문학원 원고라면 지역명만 바꾼 설명으로는 부족합니다\.",
        r"\1에서 영수 전문학원을 비교할 때는 지역명보다 학생의 영어·수학 학습 기록과 복습 여건을 구체적으로 살펴야 합니다.",
        text,
    )
    text = text.replace("지역 기반 학원 원고입니다", "지역별 학습 상황을 바탕으로 상담 기준을 정리한 안내입니다")
    text = text.replace("학원 원고입니다", "학원 상담 기준을 정리한 안내입니다")
    text = text.replace("원고처럼", "일반적인 안내처럼")
    text = text.replace("원고라면", "안내라면")
    text = text.replace("원고입니다", "안내입니다")
    text = text.replace("정보성 페이지 형식으로 안내합니다", "상담 전에 살펴볼 기준으로 안내합니다")
    text = text.replace("정보성 페이지로 정리합니다", "확인하기 쉬운 순서로 정리합니다")
    text = text.replace("정보성 페이지로 안내합니다", "학습 상황에 맞춘 기준으로 안내합니다")
    text = text.replace("정보성 페이지입니다", "상담 기준을 정리한 안내입니다")
    text = text.replace("정보성 페이지", "학습 안내")
    text = text.replace("정보성 학원 페이지", "학습 상담 안내")
    text = text.replace("자료상 학원 주소", "센터 안내에 기재된 주소")
    text = text.replace("자료상 주소", "센터 안내 주소")
    text = text.replace("자료상 제공 주소", "센터 안내에 기재된 주소")
    text = text.replace("자료상", "센터 안내 기준으로")
    text = text.replace("자료에 포함된 주소", "센터 안내에 기재된 주소")
    text = text.replace("제공된 자료만 사용하며", "확인된 학교 정보를 기준으로 하며")
    text = text.replace("제공된 학교명 외의 명칭은 추가하지 않았습니다", "학교별 수업 가능 여부는 상담에서 자녀 학교를 기준으로 확인할 수 있습니다")
    text = text.replace("제공된 수업 가능 제공된 학교 자료", "확인된 학교 자료")
    text = text.replace("제공된 수업 가능 학교 학습 자료", "확인된 학교 학습 자료")
    text = text.replace("제공된 수업 가능 학교에서 받은 자료", "확인된 학교에서 받은 자료")
    text = text.replace("제공된 수업 가능 학교", "확인된 수업 가능 학교")
    text = text.replace("페이지는 제공된 학교명 범위 안에서 내신 대비 설명을 구성합니다", "확인된 학교 범위 안에서 자녀 학교의 내신 자료 활용 방법을 안내합니다")
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 페이지는 (.*?)처럼 제공된 학교명만 활용해 설명합니다\.",
        rf"{local} {config['label']}에서는 \1 가운데 자녀가 재학 중인 학교의 시험 범위와 자료 활용 방식을 상담에서 구체적으로 확인합니다.",
        text,
    )
    text = text.replace("영어 수학 같은 참고 학습 항목", "영어와 수학의 주간 시간 배분")
    text = text.replace("영어 수학이라는 참고 학습 항목", "영어와 수학의 주간 시간 배분")
    text = text.replace("참고 학습 항목이", "함께 살펴볼 항목이")
    text = re.sub(r"참고 학습 항목\s*'([^']+)'\s*항목", r"함께 확인할 '\1' 기준", text)
    text = text.replace("참고 학습 항목", "추가 확인 항목")
    text = text.replace("진단이 먼저 확인할 필요가 있습니다", "진단이 먼저 이루어져야 합니다")
    text = text.replace("확인하는 과정을 보완해야 하는 상태입니다", "확인하는 과정부터 보완해야 합니다")
    text = text.replace("페이지의 학교·센터 정보는 제공된 자료를 기준으로 안내하며", "센터·학교 정보는 확인된 등록 자료를 기준으로 안내하며")
    text = text.replace("첫 첫 상담", "첫 상담")
    text = text.replace("페이지를 길게 읽기 전에 결론부터 보면", "결론부터 정리하면")
    text = text.replace("검색자가 바로 확인해야 할 핵심", "학부모가 먼저 확인할 핵심")
    text = text.replace("페이지에서 바로 답해야 할 질문", "상담에서 먼저 확인해야 할 질문")
    text = text.replace("이 페이지에서 차례로 다루는 내용", "상담 전에 차례로 확인할 내용")
    text = text.replace("페이지의 답변 흐름", "상담 전 확인 흐름")
    text = text.replace("검색 만족도가 높아집니다", "상담 판단이 더 구체적입니다")
    text = text.replace("학교명이 제공되지 않은 경우에도 페이지 안내 내용을 만들 수 있나요?", "수업 가능 학교 정보가 없는 경우에는 무엇을 확인해야 하나요?")
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 자료에는 특정 수업 가능 학교명이 제공되지 않았으므로 이 안내에서는 임의의 학교명을 만들지 않습니다\.",
        "수업 가능 학교 정보가 없는 경우에는 자녀 학교의 최근 시험 범위표와 학습 자료를 상담에 준비해 수업 적용 범위를 확인해야 합니다.",
        text,
    )
    text = text.replace(
        "특정 수업 가능 학교명이 제공되지 않았으므로 이 안내에서는 임의의 학교명을 만들지 않습니다",
        "수업 가능 학교 정보가 없는 경우에는 자녀 학교의 최근 시험 범위표와 학습 자료를 상담에 준비해 수업 적용 범위를 확인해야 합니다",
    )
    text = text.replace(
        "이 목록 밖의 학교명을 새로 넣지 않고",
        "확인된 학교 정보와 자녀가 준비한 실제 자료를 바탕으로",
    )
    text = text.replace("제공된 학교 정보에는", "확인된 학교 정보에는")
    text = text.replace("제공된 학교 정보를 기준으로", "확인된 학교 정보를 기준으로")
    text = text.replace("제공된 학원 주소는", "센터 주소는")
    text = text.replace("임의의 학교명", "확인되지 않은 학교명")
    text = text.replace(
        "해석 절차와 답의 근거를 말하는 연습이 먼저 확인할 필요가 있습니다",
        "해석 절차와 답의 근거를 말하는 연습부터 점검할 필요가 있습니다",
    )
    text = text.replace("구성이 확인할 필요가 있습니다", "구성을 확인할 필요가 있습니다")
    text = text.replace("상담을 준비하며 준비하면", "상담에 준비하면")
    text = text.replace("학부모라면 학부모가", "학부모라면")
    text = text.replace("학생 학생", "학생")
    text = text.replace("상담 상담", "상담")
    text = text.replace("관리 관리", "관리")
    text = text.replace("관리이", "관리가")
    text = re.sub(
        r"함께 놓고 보면,\s*([^,.]+?)을 함께 놓고 보면,",
        r"확인한 뒤, \1을 함께 놓고 보면,",
        text,
    )
    text = text.replace("CSV의 추가 확인 항목은 영어·수학이지만", "영어와 수학을 함께 관리하는 상황도 살펴보지만")
    text = text.replace("CSV의 추가 확인 항목은 수학과 영어가지만", "영어와 수학을 함께 관리하는 상황에서도")
    text = text.replace("CSV의 추가 확인 항목은 두 과목이지만", "영어와 수학을 함께 관리하는 상황에서도")
    text = text.replace("영어 전문학원 페이지의 중심은 영어입니다", "영어 전문 수업에서는 어휘·문법·독해와 서술형 학습을 우선합니다")
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 페이지는",
        f"{local} {config['label']}에서는",
        text,
    )
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 페이지에서",
        f"{local} {config['label']} 상담에서",
        text,
    )
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 페이지에서는 본문에 적은 학교 목록을 기준으로 범위 확인을 안내합니다\.",
        f"{local} {config['label']} 상담에서는 확인된 학교 범위와 자녀의 시험 자료를 기준으로 진도 활용 방법을 점검합니다.",
        text,
    )
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 수업은 제공되지 않은 학교명을 임의로 넣지 않고, {re.escape(local)} 학생이 가져온 실제 학교 학습 자료와 시험 범위표를 기준으로 조정해야 합니다\.",
        f"{local} {config['label']} 상담에서는 학생이 가져온 실제 학교 학습 자료와 시험 범위표를 기준으로 수업 계획을 조정해야 합니다.",
        text,
    )
    text = re.sub(
        rf"{re.escape(local)} {re.escape(str(config['label']))} 페이지는 임의 학교명을 더하지 않고 제공된 학교명만 기준으로 진도 점검을 설명합니다\.",
        f"{local} {config['label']} 상담에서는 확인된 학교 정보와 자녀의 시험 자료를 기준으로 진도 활용 방법을 점검합니다.",
        text,
    )
    text = text.replace(
        "본문에 적은 학교 목록을 기준으로 범위 확인을 안내합니다",
        "확인된 학교 범위와 자녀의 시험 자료를 기준으로 진도 활용 방법을 점검합니다",
    )
    text = text.replace(
        "임의 학교명을 더하지 않고 제공된 학교명만 기준으로 진도 점검을 설명합니다",
        "확인된 학교 정보와 자녀의 시험 자료를 기준으로 진도 활용 방법을 점검합니다",
    )
    text = text.replace(
        "제공되지 않은 학교명을 임의로 넣지 않고",
        "학생이 가져온 실제 학교 자료를 바탕으로",
    )
    text = re.sub(
        rf"수업 가능 학교명이 제공되지 않아 {re.escape(local)} {re.escape(str(config['label']))} 요약에서는 임의 학교명을 사용하지 않고 실제 상담 시 (?:제공된 학교 자료|학교에서 받은 자료|학교 학습 자료) 확인을 권합니다\.",
        "수업 가능 학교 정보가 없는 경우에는 상담 시 자녀 학교의 시험 범위표와 학습 자료를 기준으로 수업 적용 범위를 확인해야 합니다.",
        text,
    )
    text = text.replace("임의 학교명을 사용하지 않고", "자녀 학교의 실제 자료를 기준으로")
    text = text.replace("임의 학교명", "확인되지 않은 학교명")
    text = text.replace("제공 학교 정보", "확인된 학교 정보")
    text = text.replace("제공된 학교명 범위", "확인된 학교 범위")
    text = text.replace("제공 주소는", "센터 주소는")
    text = text.replace("상담 페이지는", "상담에서는")
    text = text.replace("영어 전문학원 페이지에서는", "영어 전문 수업 상담에서는")
    text = text.replace("영어 전문학원 페이지에서", "영어 전문 수업 상담에서")
    text = text.replace("영어 전문학원 페이지의", "영어 전문 수업 안내의")
    text = text.replace("영어 전문학원 페이지로,", "영어 전문 수업을 알아보는 가정을 위한 안내로,")
    text = text.replace("이 페이지의 기준 학생 유형", "우선 살펴볼 학생 유형")
    text = text.replace("이 페이지는", "이 안내에서는")
    text = text.replace("이 페이지에서는", "이 안내에서는")
    text = text.replace("이 페이지의", "이 안내의")
    text = text.replace("이 페이지에서", "이 안내에서")
    text = text.replace("페이지는 특정 점수 상승이나 결과를 보장하지 않고", "상담에서는 특정 점수 상승이나 결과를 단정하지 않고")
    text = text.replace("페이지에서 수업보다 진단과 오답 루틴을 먼저 보라는 설명", "상담 안내에서 수업 횟수보다 진단과 오답 루틴을 먼저 보라는 설명")
    text = text.replace("학교 일정과 주간 시간표를 학교 일정과 함께 살펴보면", "학교 일정과 주간 시간표를 함께 살펴보면")
    text = text.replace("영어의 주간 계획을 주간 계획과 연결하면", "영어의 주간 계획을 실행 기록과 연결하면")
    text = text.replace("수학의 주간 계획을 주간 계획과 연결하면", "수학의 주간 계획을 실행 기록과 연결하면")
    text = re.sub(r"(?<![가-힣])페이지(?=(?:에서는|에서|의|는|로|를|가|에|입니다|형식|안내|$|[\s,.]))", "안내", text)
    text = text.replace("안내 안내", "학습 안내")
    text = text.replace("학습관리 절차자", "학습관리 절차")
    text = text.replace("제공된 제공된 학교 자료", "확인된 학교 자료")
    text = text.replace("실제 제공된 학교 자료", "실제 학교 자료")
    text = text.replace("입시결과", "학습 결과")
    text = text.replace("점검’라는", "점검’이라는")
    text = text.replace("점검'라는", "점검'이라는")
    text = text.replace("점검’를", "점검’을")
    text = text.replace("점검'를", "점검'을")
    text = re.sub(
        r"([^.!?]+?)이며\s*[‘']([^’']+)[’'](?:이라는|라는) 상담 질문까지 함께 점검해야 하는 학생",
        r"\1이고 ‘\2’ 기준도 함께 확인해야 하는 학생",
        text,
    )

    if config["focus"] == "math":
        replacements = {
            "두 과목의 주간 계획을": "수학의 주간 계획을",
            "영어와 수학의 차이를": "개념 이해와 풀이 과정의 차이를",
            "영어·수학으로 구분하면": "개념 이해와 문제풀이로 구분하면",
            "영어·수학 우선순위": "수학 단원 우선순위",
            "영어 답안·수학 풀이": "수학 답안과 풀이 과정",
            "과목별 취약 지점을": "수학 취약 지점을",
            "과목별로 나누어 보면": "수학 영역별로 나누어 보면",
            "과목별 복습 간격": "수학 복습 간격",
            "영어·수학 계획": "수학 학습 계획",
        }
    elif config["focus"] == "english":
        replacements = {
            "두 과목의 주간 계획을": "영어의 주간 계획을",
            "영어와 수학의 차이를": "어휘·문법·독해의 차이를",
            "영어·수학으로 구분하면": "어휘·문법·독해로 구분하면",
            "영어·수학 우선순위": "영어 영역 우선순위",
            "영어 답안·수학 풀이": "영어 답안과 독해 근거",
            "과목별 취약 지점을": "영어 취약 지점을",
            "과목별로 나누어 보면": "영어 영역별로 나누어 보면",
            "과목별 복습 간격": "영어 복습 간격",
            "영어·수학 계획": "영어 학습 계획",
        }
    else:
        replacements = {}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"[ \t]+", " ", text).strip()


ADMIN_TERM_PATTERN = re.compile(
    r"(?:학원)?(?:매출관리|창업|전자계약|미납관리|회원관리|고객관리|문자발송|보안관리|출입관리|"
    r"운영자|관리프로그램|관리앱|온라인등록|상담관리|상담직원|데스크|행정|직원|원장|공지|"
    r"소식|알림톡|결제관리|수납관리|수강생관리|문서관리|안전관리|청결관리)"
)

PARENT_FACING_TERMS = {
    "math": (
        "오답 점검", "풀이 기록", "개념 복습", "과제 피드백", "검산 습관", "재풀이 일정",
        "시험 범위 확인", "주간 학습 계획", "서술형 풀이", "학습 기록 공유", "교재 활용", "상담 준비",
    ),
    "english": (
        "어휘 누적", "문법 적용", "독해 근거", "서술형 교정", "과제 피드백", "오답 점검",
        "시험 범위 확인", "주간 학습 계획", "문장 해석", "학습 기록 공유", "교재 활용", "상담 준비",
    ),
    "combined": (
        "과목별 우선순위", "영어 답안 점검", "수학 풀이 기록", "과제 피드백", "오답 점검", "복습 일정",
        "시험 범위 확인", "주간 시간 배분", "과목별 학습량", "학습 기록 공유", "교재 활용", "상담 준비",
    ),
}

CONTEXT_TERM_REPLACEMENTS = {
    "학원개인정보관리": "학습 기록 정리",
    "학원데이터관리": "학습 기록 정리",
    "학원관리솔루션": "학습관리 기준",
    "학원온라인수업": "가정 복습 안내",
    "학원실시간수업": "수업 피드백 과정",
    "학원수준별수업": "학생별 학습 점검",
    "학원화상수업": "가정 복습 안내",
    "학원대면수업": "수업 진행 과정",
    "학원맞춤수업": "학생별 학습 점검",
    "학원개별지도": "학생별 학습 점검",
    "학원일대일": "개별 학습 점검",
    "학원코디네이터": "학습 기록 공유",
    "학원결제시스템": "상담 준비 항목",
    "학원방역관리": "학습 환경 관리",
    "학원출결앱": "학습 기록",
    "학원예약관리": "상담 준비",
    "학원정규반": "수업 구성",
    "학원집중반": "보완 학습",
    "학원소수정예": "개별 지도",
    "학원커리큘럼": "학습 계획",
    "학원프로그램": "학습 계획",
    "학원스터디룸": "자습 계획",
    "학원상담실": "상담 준비 항목",
    "학원자료실": "학습 자료 활용",
    "학원강의실": "학습 환경",
    "학원시간표": "주간 시간표",
    "학원알림장": "학습 기록 공유",
    "학원사물함": "교재 준비 항목",
    "학원휴게실": "학습 휴식 계획",
    "학원자습실": "자습 계획",
    "학원분위기": "학습 분위기",
    "학원교통": "등원 동선",
    "학원차량": "등원 동선",
    "학원셔틀": "등원 동선",
    "학원주차": "방문 경로",
    "학원등원": "등원 동선",
    "학원하원": "하원 시간",
    "학원보충": "보완 학습",
    "학원보강": "보완 학습",
    "학원특강": "보완 학습",
    "학원매니저": "학습 기록 공유",
    "학원브랜드": "수업 가치",
    "학원운영": "학습관리 절차",
    "학원환경": "학습 환경",
    "학원시설": "학습 환경",
    "학원강사": "수업 지도",
    "학원강의": "학습 안내",
    "학원수업": "수업 과정",
    "학원진도": "학습 진도",
    "학원일정": "주간 학습 계획",
    "학원출결": "학습 실행 기록",
    "학원위치": "센터 위치",
}

GRADE_PATTERN = re.compile(
    r"(?P<level>초등학교|초등|초|중학교|중등|중|고등학교|고등|고)\s*(?P<number>[1-6])\s*(?P<suffix>학년)?"
)


def canonical_grade(level: str, number: str) -> str:
    if level.startswith("초"):
        return f"초{number}"
    if level.startswith("중"):
        return f"중{number}"
    return f"고{number}"


def display_grade(code: str, original: str) -> str:
    level_names = {"초": "초등", "중": "중등", "고": "고등"}
    if "학교" in original:
        return f"{level_names[code[0]]}학교 {code[1]}학년"
    if "학년" in original or original.startswith(("초등", "중등", "고등")):
        return f"{level_names[code[0]]} {code[1]}학년"
    return code


def sanitize_grade_claims(value: str, verified_grades: list[str]) -> str:
    """Keep explicit grade claims inside verified center facts only."""
    allowed = [grade for grade in verified_grades if re.fullmatch(r"[초중고][1-6]", grade)]

    def replace(match: re.Match[str]) -> str:
        original = match.group(0)
        code = canonical_grade(match.group("level"), match.group("number"))
        if code in allowed:
            return display_grade(code, original)
        same_level = [grade for grade in allowed if grade[0] == code[0]]
        if same_level:
            nearest = min(same_level, key=lambda grade: (abs(int(grade[1]) - int(code[1])), int(grade[1])))
            return display_grade(nearest, original)
        return "해당 학년"

    text = GRADE_PATTERN.sub(replace, value)
    text = text.replace("해당 학년 학년", "해당 학년")
    return text


def replace_admin_terms(value: str, local: str, config: dict[str, object]) -> str:
    bank = PARENT_FACING_TERMS[str(config["focus"])]
    text = value
    for old, new in sorted(CONTEXT_TERM_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(old, new)

    def replace(match: re.Match[str]) -> str:
        code = shared.stable_number(config["slug"], local, match.group(0))
        return bank[code % len(bank)]

    text = ADMIN_TERM_PATTERN.sub(replace, text)
    spacing = {
        "학원과제": "과제 피드백",
        "학원숙제": "숙제 점검",
        "학원교재": "교재 활용",
        "시험범위관리": "시험 범위 관리",
        "학습분량관리": "학습 분량 관리",
        "오답관리": "오답 관리",
        "진도관리": "진도 관리",
    }
    for old, new in spacing.items():
        text = text.replace(old, new)
    return text


def normalize_school_separators(value: str, schools: list[str]) -> str:
    text = value
    ordered = sorted(unique_values(schools), key=len, reverse=True)
    for left in ordered:
        for right in ordered:
            if left == right:
                continue
            text = re.sub(
                rf"{re.escape(left)}\s+{re.escape(right)}",
                f"{left}, {right}",
                text,
            )
    return text


def collapse_repeated_terms(value: str) -> str:
    words = "학생|학부모|상담|관리|확인|자료|학습|수업|학교"
    text = re.sub(
        rf"(?<![가-힣])({words})(?:\s+\1)+(?![가-힣])",
        r"\1",
        value,
    )
    return re.sub(
        rf"(?<![가-힣])({words})(?:\s+\1)+(?=(?:에서|으로|은|는|이|가|을|를|과|와|의|에|도|만|부터|까지))",
        r"\1",
        text,
    )


def final_polish(
    value: str,
    local: str,
    config: dict[str, object],
    verified_grades: list[str],
    schools: list[str],
) -> str:
    text = replace_admin_terms(value, local, config)
    text = sanitize_grade_claims(text, verified_grades)
    text = normalize_school_separators(text, schools)
    grammar = {
        "필요한 유형 학생에게": "필요한 유형의 학생에게",
        "태도가 확인할 필요가 있습니다": "태도를 확인할 필요가 있습니다",
        "과정이 확인할 필요가 있습니다": "과정을 확인할 필요가 있습니다",
        "훈련이 확인할 필요가 있습니다": "훈련을 확인할 필요가 있습니다",
        "연습이 확인할 필요가 있습니다": "연습을 확인할 필요가 있습니다",
        "시간이 확인할 필요가 있습니다": "시간을 확인할 필요가 있습니다",
        "학교을": "학교를",
        "학원를": "학원을",
        "자료을": "자료를",
        "영어을": "영어를",
        "수학를": "수학을",
        "관리을": "관리를",
        "상담를": "상담을",
        "수업를": "수업을",
        "학생를": "학생을",
        "교재 활용와": "교재 활용과",
        "과제 피드백를": "과제 피드백을",
        "어휘·문법·독해과": "어휘·문법·독해와",
        "수학 풀이과": "수학 풀이와",
        "영어 답안과 수학 풀이을": "영어 답안과 수학 풀이를",
        "확인와": "확인과",
        "확인를": "확인을",
        "수업 가능 제공된 학교 자료": "확인된 수업 가능 학교 자료",
        "제공된 수업 가능 제공된 학교 자료": "확인된 수업 가능 학교 자료",
        "결과을": "결과를",
        "변화을": "변화를",
        "변화과": "변화와",
        "표시과": "표시와",
        "계획를": "계획을",
        "점검를": "점검을",
    }
    for old, new in grammar.items():
        text = text.replace(old, new)
    if config["focus"] == "math":
        text = text.replace("두 과목의 학습 흐름", "수학 풀이와 복습 흐름")
        text = text.replace("영어·수학 복습 간격", "수학 오답 재확인 간격")
        text = text.replace("과목별 취약", "수학 영역별 취약")
    elif config["focus"] == "english":
        text = text.replace("두 과목의 학습 흐름", "영어 학습과 복습 흐름")
        text = text.replace("영어·수학 복습 간격", "영어 어휘·독해 복습 간격")
        text = text.replace("과목별 취약", "영어 영역별 취약")
    text = collapse_repeated_terms(text)
    text = re.sub(r"(?<=[초중고][1-6])(?=[가-힣])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = reader_facing_text(text, local, config).strip()
    for old, new in grammar.items():
        text = text.replace(old, new)
    text = collapse_repeated_terms(text)
    text = re.sub(r"(?<=[초중고][1-6])(?=[가-힣])", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def grounded_paragraph(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> str:
    grades = [str(item) for item in center.get("verified_grades", [])]
    schools = [str(item) for item in center.get("schools", [])]
    if not grades:
        grade_text = ""
    elif len(grades) == 1:
        grade_text = grades[0]
    else:
        grade_text = "·".join(grades)
    if schools:
        offset = rank % len(schools)
        selected = [schools[(offset + index) % len(schools)] for index in range(min(2, len(schools)))]
        school_text = "·".join(selected)
        school_clause = f" 확인된 학교 정보에는 {school_text} 등이 있으므로, 자녀 학교의 실제 시험 일정과 자료 활용 범위는 상담에서 다시 맞춰 보는 것이 좋습니다."
    else:
        school_clause = " 수업 가능한 학교와 시험 자료 활용 범위는 상담에서 자녀 학교를 기준으로 확인하는 것이 좋습니다."
    city_local = " ".join(unique_values([str(center.get("region", "")), str(center.get("city", "")), local]))
    if not grades:
        subject = "영어와 수학" if config["focus"] == "combined" else str(config["subjects"][0])
        frames = (
            f"{city_local}에서 {subject} 수업을 상담할 때는 먼저 수업 가능 학년을 확인한 뒤 최근 교재와 시험 자료를 기준으로 현재 상태를 나누어 보는 편이 좋습니다.",
            f"{local} {subject} 학습은 학년 적용 범위를 상담에서 확인하고, 학생이 혼자 해낸 부분과 설명이 필요한 부분을 구분해야 다음 계획이 구체화됩니다.",
            f"{city_local} 상담에서는 {subject} 수업 가능 학년을 먼저 확인하고 최근 답안·풀이 기록과 주간 복습 시간을 함께 살펴보는 과정이 필요합니다.",
            f"{local}에서 {subject} 학습을 이어 갈 때는 특정 학년을 미리 단정하지 않고 현재 교재와 시험 범위, 오답 재확인 기록을 기준으로 수업 적용 범위를 확인해야 합니다.",
        )
        return frames[rank % len(frames)] + school_clause
    if config["focus"] == "math":
        frames = (
            f"{city_local}에서 {grade_text} 수학 수업을 상담한다면 최근 시험지의 정오답뿐 아니라 풀이가 멈춘 단계와 재풀이 날짜를 함께 표시해 준비하는 편이 좋습니다.",
            f"{local} 학생의 수학 계획은 {grade_text}이라는 학년 범위보다 현재 단원의 개념 설명, 계산 과정, 조건 해석 중 어느 부분이 흔들리는지부터 나누어야 구체화됩니다.",
            f"{city_local} 수학 상담에서는 {grade_text} 학생이 혼자 다시 풀 수 있는 문제와 설명을 들어야 풀 수 있는 문제를 구분하면 수업 후 복습량을 현실적으로 정할 수 있습니다.",
            f"{local}에서 수학 학습을 이어 갈 때는 {grade_text} 학생의 최근 오답을 개념 부족·계산 실수·문제 해석으로 분류해 다음 점검 순서를 정하는 과정이 필요합니다.",
            f"{city_local}의 {grade_text} 수학 상담 자료에는 최근 교재, 학교 시험 범위, 풀이 흔적과 재도전 결과를 함께 담아야 현재 진도와 누적 빈틈을 구분하기 쉽습니다.",
            f"{local} 수학 수업을 비교할 때 {grade_text} 학생에게 필요한 것은 문제 수의 증가보다 틀린 이유를 말로 설명하고 일정 뒤 같은 유형을 다시 푸는 절차인지 확인하는 일입니다.",
        )
    elif config["focus"] == "english":
        frames = (
            f"{city_local}에서 {grade_text} 영어 수업을 상담한다면 최근 단어 시험, 문법 오답, 독해 지문과 서술형 답안을 함께 준비해 막히는 지점을 나누어 보는 편이 좋습니다.",
            f"{local} 학생의 영어 계획은 {grade_text}이라는 학년 범위만으로 정하기보다 어휘 누적, 문장 구조 해석, 독해 근거 표시 중 우선 보완할 영역을 먼저 확인해야 합니다.",
            f"{city_local} 영어 상담에서는 {grade_text} 학생이 읽고도 근거를 찾지 못하는지, 문법을 알고도 문장에 적용하지 못하는지 구분하면 복습 순서를 구체화할 수 있습니다.",
            f"{local}에서 영어 학습을 이어 갈 때는 {grade_text} 학생의 최근 답안을 어휘·문법·독해·서술형으로 나누고 각 영역의 반복 주기를 다르게 잡는 과정이 필요합니다.",
            f"{city_local}의 {grade_text} 영어 상담 자료에는 학교 범위, 최근 교재, 단어 누적 기록과 틀린 답의 근거를 함께 담아야 현재 상태를 정확히 설명하기 쉽습니다.",
            f"{local} 영어 수업을 비교할 때 {grade_text} 학생에게 필요한 것은 암기량만 늘리는 방식보다 문장 구조를 설명하고 지문에서 답의 근거를 다시 찾는 절차인지 확인하는 일입니다.",
        )
    else:
        frames = (
            f"{city_local}에서 {grade_text} 영수 수업을 상담한다면 영어 답안과 수학 풀이를 따로 준비해 두 과목의 취약 영역과 복습 가능 시간을 각각 확인하는 편이 좋습니다.",
            f"{local} 학생의 영수 계획은 {grade_text}이라는 학년 범위보다 영어와 수학 중 먼저 보완할 과목, 학교 일정, 혼자 공부할 수 있는 시간을 함께 놓고 정해야 합니다.",
            f"{city_local} 영수 상담에서는 {grade_text} 학생의 영어 어휘·독해 기록과 수학 개념·오답 기록을 분리해 살펴야 한 과목의 과제가 다른 과목의 복습을 밀어내지 않습니다.",
            f"{local}에서 영어와 수학을 함께 관리할 때는 {grade_text} 학생에게 두 과목을 같은 분량으로 주기보다 현재 차이에 따라 주간 시간과 재확인 날짜를 달리 잡아야 합니다.",
            f"{city_local}의 {grade_text} 영수 상담 자료에는 두 과목의 최근 시험지, 교재 진도, 오답과 일주일 시간표를 함께 담아야 실행 가능한 우선순위를 정하기 쉽습니다.",
            f"{local} 영수 수업을 비교할 때 {grade_text} 학생에게 필요한 것은 단순한 과제 묶음보다 영어 답안과 수학 풀이의 피드백이 서로 다른 기준으로 기록되는지 확인하는 일입니다.",
        )
    return frames[rank % len(frames)] + school_clause


SUBJECT_CONTEXT_BANKS = {
    "math": (
        "최근 풀이 순서를", "개념 설명과 계산 과정을", "틀린 문제의 재풀이 기록을", "현재 단원과 누적 빈틈을",
        "서술형 답안의 전개를", "학교 시험 범위와 교재를", "문제 조건을 표시한 흔적을", "수업 뒤 혼자 푼 결과를",
        "연산 정확도와 검산 습관을", "주간 수학 학습량을", "오답 원인과 재도전 날짜를", "학생이 말로 설명한 내용을",
    ),
    "english": (
        "최근 영어 답안을", "어휘 누적 기록과 단어 시험을", "문법 개념의 문장 적용을", "독해 답의 근거 표시를",
        "서술형 표현과 교정 기록을", "학교 시험 범위와 교재를", "긴 문장 해석 과정을", "수업 뒤 혼자 복습한 결과를",
        "어휘·문법·독해의 차이를", "주간 영어 학습량을", "오답 근거와 재확인 날짜를", "학생이 문장을 설명한 내용을",
    ),
    "combined": (
        "영어 답안과 수학 풀이를", "두 과목의 최근 시험지를", "영어·수학 복습 간격을", "과목별 과제 완료 기록을",
        "학교 일정과 주간 시간표를", "두 과목의 오답 원인을", "영어 근거 표시와 수학 검산을", "수업 뒤 혼자 공부한 결과를",
        "과목별 현재 차이를", "영어·수학 학습량을", "재확인 날짜와 다음 계획을", "학생이 설명한 두 과목 내용을",
    ),
}

SUBJECT_ACTION_BANK = (
    "상담 자료와 맞춰 보면,", "현재 수준을 판단하는 기준으로 삼으면,", "학교 일정과 함께 살펴보면,",
    "수업 뒤 행동으로 연결하면,", "첫 달 점검 항목으로 정리하면,", "가정 복습 기록과 대조하면,",
    "시험 전후 변화로 비교하면,", "학생의 설명과 나란히 놓으면,", "다음 학습 순서로 구체화하면,",
    "주간 실행 여부와 함께 보면,", "과제·오답 피드백과 연결하면,", "상담 질문으로 다시 나누면,",
)

QUESTION_CONTEXT_BANK = (
    "최근 학습 기록을 기준으로 보면,", "학교 시험지와 함께 살펴볼 때,", "수업 뒤 복습까지 고려하면,",
    "학생의 현재 답안과 대조하면,", "상담 전에 기준을 나누어 보면,", "첫 달 학습 계획을 세울 때,",
    "가정에서 확인한 내용까지 포함하면,", "오답 재확인 절차를 기준으로 보면,",
)

MATH_EVIDENCE_BANK = (
    "최근 시험지의 풀이 흔적", "현재 교재의 단원별 답안", "오답 노트의 재풀이 기록",
    "서술형 답안의 식과 설명", "과제 완료 뒤 혼자 다시 푼 결과", "주간 학습표와 실제 실행량",
    "계산 과정의 검산 표시", "문제 조건을 표시한 흔적", "개념을 말로 설명한 기록",
    "학교 시험 범위와 남은 기간", "같은 유형을 다시 푼 날짜", "수업 전후 정답률의 변화",
)

MATH_DIAGNOSIS_BANK = (
    "개념을 알고도 식을 세우지 못하는지", "계산 실수가 검산 과정에서 걸러지는지",
    "문제 조건을 끝까지 읽고 표시하는지", "틀린 이유를 개념·계산·해석으로 나누는지",
    "서술형 풀이의 근거를 문장으로 설명하는지", "일정이 지난 뒤 같은 유형을 다시 풀 수 있는지",
    "현재 단원과 이전 단원의 빈틈을 구분하는지", "수업 설명 없이 첫 풀이를 시작할 수 있는지",
    "오답 정리가 다음 주 계획으로 이어지는지", "시험 범위 안에서 우선순위를 정할 수 있는지",
    "풀이 속도보다 정확한 과정을 유지하는지", "문제 수보다 재도전 결과가 기록되는지",
)

MATH_ACTION_BANK = (
    "상담 질문을 구체화할 수 있습니다", "첫 달 점검 순서를 정하기 좋습니다",
    "수업과 가정 복습의 역할을 나눌 수 있습니다", "다음 단원으로 넘어갈 시점을 판단하기 쉽습니다",
    "학생에게 필요한 피드백 방식을 비교할 수 있습니다", "주간 학습량을 현실적으로 조정할 수 있습니다",
    "학교 시험 대비와 누적 복습을 함께 설계할 수 있습니다", "오답 재확인 간격을 정하는 근거가 됩니다",
)


def math_rewrite_sentence(sentence: str, local: str, code: int) -> str | None:
    """Replace shared generic math copy while leaving source facts untouched."""
    if len(sentence) < 32 or re.search(r"\d|주소|전화|학교 정보|수업 가능 학교", sentence):
        return None
    evidence = MATH_EVIDENCE_BANK[code % len(MATH_EVIDENCE_BANK)]
    diagnosis = MATH_DIAGNOSIS_BANK[(code // len(MATH_EVIDENCE_BANK)) % len(MATH_DIAGNOSIS_BANK)]
    action = MATH_ACTION_BANK[(code // (len(MATH_EVIDENCE_BANK) * len(MATH_DIAGNOSIS_BANK))) % len(MATH_ACTION_BANK)]
    frames = (
        f"{local} 수학 상담에서는 {evidence}을 바탕으로 {diagnosis}를 확인하면 {action}.",
        f"{evidence}에서 {diagnosis}를 먼저 살펴보면, {local} 학생의 수학 계획과 관련해 {action}.",
        f"수학 학습을 비교할 때는 {evidence}만 모으는 데 그치지 않고 {diagnosis}를 확인해야 {action}.",
        f"{local} 학생이 수학에서 반복해 막힌다면 {evidence}과 함께 {diagnosis}를 점검하는 과정이 {action}.",
        f"학부모 상담 전 {evidence}을 준비하고 {diagnosis}를 질문하면 {local} 수학 수업에서 {action}.",
        f"현재 진도를 정하기 전에 {evidence}을 통해 {diagnosis}부터 나누어 보면 {action}.",
    )
    return frames[(code // 17) % len(frames)]


def professional_diversify_text(
    value: str,
    local: str,
    rank: int,
    slot: int,
    frequencies: dict[str, int],
    config: dict[str, object],
) -> str:
    result: list[str] = []
    objects = SUBJECT_CONTEXT_BANKS[str(config["focus"])]
    for sentence_index, sentence in enumerate(shared.sentence_parts(value)):
        normalized = shared.normalize_for_frequency(sentence, local)
        if frequencies.get(normalized, 0) < 2 or len(sentence) < 28:
            result.append(sentence)
            continue
        code = shared.stable_number(config["slug"], normalized, rank, slot, sentence_index)
        if config["focus"] == "math":
            rewritten = math_rewrite_sentence(sentence, local, code)
            if rewritten:
                result.append(rewritten)
                continue
        varied = shared.lexical_variation(sentence, code)
        opener = f"{objects[code % len(objects)]} {SUBJECT_ACTION_BANK[(code // len(objects)) % len(SUBJECT_ACTION_BANK)]}"
        result.append(f"{opener} {varied}")
    return reader_facing_text(" ".join(result), local, config)


def professional_diversify_question(
    value: str,
    local: str,
    rank: int,
    slot: int,
    frequency: int,
    config: dict[str, object],
) -> str:
    if frequency < 2:
        return value
    code = shared.stable_number(config["slug"], value.replace(local, "{LOCAL}"), rank, slot)
    varied = shared.lexical_variation(value, code)
    return reader_facing_text(
        f"{QUESTION_CONTEXT_BANK[code % len(QUESTION_CONTEXT_BANK)]} {varied}",
        local,
        config,
    )


def concise_meta(value: str, title: str, config: dict[str, object]) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) > 110:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        selected: list[str] = []
        for sentence in sentences:
            candidate = " ".join([*selected, sentence]).strip()
            if len(candidate) > 110:
                break
            selected.append(sentence)
        text = " ".join(selected).strip()
        if not text:
            cropped = value[:107].rsplit(" ", 1)[0].rstrip(" ,·")
            text = cropped + "."
    if len(text) < 70:
        suffix = f" {title} 상담 전 현재 학습 기록과 {config['subjects'][0]} 학습 순서를 확인해 보세요."
        text = text.rstrip(".") + "." + suffix
    if len(text) < 70:
        text += " 학교 자료와 복습 가능 시간도 함께 점검합니다."
    text = text[:110].rstrip()
    return text


def focus_terms(config: dict[str, object]) -> tuple[str, str, str]:
    if config["focus"] == "math":
        return "수학", "개념·계산·문제 해석", "풀이 흔적과 오답 재확인"
    if config["focus"] == "english":
        return "영어", "어휘·문법·독해", "답의 근거와 서술형 교정"
    return "영어·수학", "영어 답안과 수학 풀이", "과목별 오답과 복습 일정"


def verified_grade_text(center: dict[str, object]) -> str:
    grades = [str(item) for item in center.get("verified_grades", [])]
    return "·".join(grades) if grades else "상담 시 확인"


def verified_school_text(center: dict[str, object], limit: int = 3) -> str:
    schools = [str(item) for item in center.get("schools", [])]
    return "·".join(schools[:limit])


def title_references(local: str, config: dict[str, object]) -> tuple[str, ...]:
    subject, _, _ = focus_terms(config)
    if config["focus"] == "combined":
        return (
            f"{local} 영수 수업",
            f"{local} 영수 상담",
            "이 영수 학습 과정",
            "해당 영수 관리 방식",
            "영수 전문 수업",
            "지역별 영수 학습 기준",
        )
    return (
        f"{local} {subject} 수업",
        f"{local} {subject} 상담",
        f"이 {subject} 학습 과정",
        f"해당 {subject} 관리 방식",
        f"{subject} 전문 수업",
        f"지역별 {subject} 학습 기준",
    )


def replace_title_repetition(
    value: str,
    title: str,
    local: str,
    config: dict[str, object],
    slot: int,
    keep_first: bool = False,
) -> str:
    references = title_references(local, config)
    seen = 0

    def replace(_match: re.Match[str]) -> str:
        nonlocal seen
        seen += 1
        if keep_first and seen == 1:
            return title
        code = shared.stable_number(config["slug"], local, slot, seen)
        return references[code % len(references)]

    text = re.sub(re.escape(title), replace, value)
    text = text.replace("관리을", "관리를").replace("관리이", "관리가")
    return collapse_repeated_terms(text)


def build_intro(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> list[str]:
    title = f"{local} {config['label']}"
    subject, diagnostic, evidence = focus_terms(config)
    location = " ".join(unique_values([str(center.get("region", "")), str(center.get("city", "")), local]))
    grade_text = verified_grade_text(center)
    school_text = verified_school_text(center, 2)
    code = shared.stable_number(config["slug"], local, rank)
    answer_frames = (
        f"{title}을 알아볼 때는 진도보다 학생이 {diagnostic} 중 어디에서 멈추는지 먼저 확인해야 합니다.",
        f"{title} 상담의 출발점은 문제 수가 아니라 최근 {evidence}에서 반복되는 어려움을 구분하는 일입니다.",
        f"{location}에서 {subject} 수업을 비교한다면 선행 범위보다 학생이 혼자 설명하고 다시 풀 수 있는 과정을 먼저 살펴보는 편이 좋습니다.",
        f"{title} 선택 전에는 최근 시험 결과만 보지 말고 {diagnostic}의 차이와 수업 뒤 복습 가능 시간을 함께 점검해야 합니다.",
        f"{local} 학생에게 맞는 {subject} 수업은 현재 교재와 {evidence}을 기준으로 다음 학습 순서를 구체적으로 설명할 수 있어야 합니다.",
        f"{title}을 찾는 학부모라면 수업 횟수보다 진단 결과가 과제·오답·재확인 일정으로 이어지는지를 먼저 질문해 보세요.",
    )
    if center.get("verified_grades"):
        fact_sentence = f"센터 등록 자료에서 확인된 {config['label']} 수업 가능 학년은 {grade_text}입니다."
    else:
        fact_sentence = f"이 센터의 {config['label']} 수업 가능 학년은 상담에서 먼저 확인해야 합니다."
    if school_text:
        school_sentence = f"확인된 학교 정보에는 {school_text} 등이 있으며, 실제 시험 범위와 자료 활용 방식은 자녀 학교를 기준으로 상담에서 맞춥니다."
    else:
        school_sentence = "수업 가능 학교 정보가 따로 확인되지 않은 경우에는 자녀 학교의 최근 시험 범위표와 학습 자료를 준비해 적용 범위를 상담에서 확인해야 합니다."
    preparation_frames = (
        f"{fact_sentence} {school_sentence}",
        f"{school_sentence} {fact_sentence}",
        f"상담에는 최근 시험지·교재·일주일 학습표를 준비하는 것이 좋습니다. {fact_sentence} {school_sentence}",
        f"{fact_sentence} 현재 학습 상태를 정확히 나누기 위해 최근 교재와 오답 기록을 함께 준비하세요. {school_sentence}",
    )
    return [answer_frames[code % len(answer_frames)], preparation_frames[(code // 7) % len(preparation_frames)]]


def build_summary(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> str:
    title = f"{local} {config['label']}"
    subject, diagnostic, evidence = focus_terms(config)
    location = " ".join(unique_values([str(center.get("region", "")), str(center.get("city", "")), local]))
    grades = [str(item) for item in center.get("verified_grades", [])]
    schools = verified_school_text(center, 2)
    grade_clause = f"확인된 수업 가능 학년은 {'·'.join(grades)}이며" if grades else "수업 가능 학년은 상담 확인이 필요하며"
    school_clause = f"수업 가능 학교 정보에는 {schools} 등이 포함됩니다" if schools else "자녀 학교의 시험 자료를 준비해 수업 적용 범위를 확인해야 합니다"
    frames = (
        f"{title} 안내는 {location}에서 {subject} 수업을 비교하는 학부모를 위해 {diagnostic}, {evidence}, 상담 준비 기준을 정리합니다. {grade_clause}, {school_clause}. 최근 시험지와 교재를 준비하면 현재 상태와 다음 복습 순서를 더 구체적으로 확인할 수 있습니다.",
        f"{title}에서는 {location} 학생의 {subject} 학습을 진단할 때 볼 {diagnostic}과 {evidence}을 안내합니다. {grade_clause}, {school_clause}. 상담 전 최근 답안·풀이 기록과 주간 학습표를 준비해 수업 뒤 실행 계획까지 비교해 보세요.",
        f"{title} 상담 기준은 {location} 학생의 {diagnostic}을 나누고 {evidence}을 다음 계획으로 연결하는 데 초점을 둡니다. {grade_clause}, {school_clause}. 특정 결과보다 진단·피드백·재확인 절차를 확인하는 것이 중요합니다.",
        f"{title}을 찾는 가정이 먼저 확인할 내용은 현재 {diagnostic}, 수업 후 {evidence}, 학교 자료 활용 방식입니다. {grade_clause}, {school_clause}. 상담에는 최근 교재와 시험 범위표, 오답 기록을 함께 준비하는 편이 좋습니다.",
    )
    evidence_bank = (
        "최근 시험지의 오답 원인", "현재 교재의 풀이·답안 흔적", "학교 시험 범위와 남은 기간",
        "과제 완료 뒤 혼자 다시 풀어 본 기록", "일주일 학습표와 실제 실행량", "수업 전후의 설명 과정",
        "같은 유형을 다시 확인한 날짜", "학생이 말로 설명한 내용", "가정에서 확인한 복습 기록",
        "단원별로 반복되는 어려움", "시험 전후 달라진 학습 리듬", "교재 진도와 누적 빈틈",
        "답을 고친 뒤 남은 질문", "학교 일정과 등원 가능 시간", "수업 뒤 과제 피드백",
        "다음 상담까지의 재확인 기록",
    )
    action_bank = (
        "진단 순서를 정합니다", "첫 달 점검 항목으로 연결합니다", "주간 복습량을 조정합니다",
        "수업과 가정 학습의 역할을 나눕니다", "우선 보완할 영역을 정합니다", "다음 학습 계획과 대조합니다",
        "과제 피드백 질문으로 바꿉니다", "학생에게 필요한 설명 방식을 비교합니다", "오답 재확인 간격을 정합니다",
        "학교 자료 활용 범위와 맞춥니다", "현재 진도와 이전 빈틈을 구분합니다", "상담에서 확인할 질문으로 정리합니다",
        "혼자 공부할 수 있는 시간과 맞춥니다", "시험 대비와 누적 복습을 구분합니다", "다음 교재 단계의 기준으로 삼습니다",
        "특정 결과보다 실행 과정으로 확인합니다",
    )
    code = shared.stable_number(config["slug"], local, "summary-detail")
    detail = f"상담에서는 {evidence_bank[code % len(evidence_bank)]}을 기준으로 {action_bank[(code // len(evidence_bank)) % len(action_bank)]}."
    return f"{frames[rank % len(frames)]} {detail}"


def build_meta(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> str:
    title = f"{local} {config['label']}"
    subject, diagnostic, evidence = focus_terms(config)
    schools = verified_school_text(center, 1)
    detail = f"{schools} 등 확인된 학교 정보와 " if schools else "자녀 학교 자료와 "
    frames = (
        f"{title} 상담 전 {diagnostic}, {evidence}, 수업 가능 학년과 학교 자료 활용 기준을 확인하세요.",
        f"{title}의 {subject} 진단·복습 흐름과 {detail}상담 준비사항을 지역 정보에 맞춰 안내합니다.",
        f"{title} 선택에 필요한 현재 학습 진단, 학교 범위 확인, 과제·오답 재학습과 상담 기준을 정리했습니다.",
        f"{title}에서 확인할 {diagnostic}, 주간 복습 계획, 수업 가능 학년·학교 정보와 상담 준비 자료를 안내합니다.",
    )
    return concise_meta(frames[rank % len(frames)], title, config)


def build_answer(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> tuple[str, str, list[str]]:
    subject, diagnostic, evidence = focus_terms(config)
    heading_frames = (
        f"{local} {subject} 상담, 무엇부터 확인할까요?",
        f"{local} 학생의 {subject} 학습을 나누어 보는 기준",
        f"수업 선택 전 확인할 {local} {subject} 학습 기록",
        f"{local} {subject} 수업의 진단·복습 확인 순서",
    )
    text_frames = (
        f"최근 시험지와 교재에서 {diagnostic}을 나눈 뒤, {evidence}이 수업 후 일정으로 이어지는지 확인합니다.",
        f"현재 진도만 묻기보다 학생이 혼자 설명할 수 있는 부분과 다시 도움이 필요한 부분을 구분해 다음 복습 순서를 정합니다.",
        f"학교 시험 범위, 최근 답안·풀이, 일주일 학습 시간을 함께 놓고 수업과 가정 복습의 역할을 구체적으로 확인합니다.",
        f"진단 결과가 과제 피드백과 오답 재확인 날짜로 남는지 살펴보면 학생에게 맞는 관리 방식을 비교하기 쉽습니다.",
    )
    tags = list(config["hero_tags"][rank % len(config["hero_tags"])])
    return heading_frames[rank % len(heading_frames)], text_frames[(rank // 3) % len(text_frames)], tags


def build_faqs(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> list[dict[str, str]]:
    title = f"{local} {config['label']}"
    subject, diagnostic, evidence = focus_terms(config)
    grades = [str(item) for item in center.get("verified_grades", [])]
    schools = [str(item) for item in center.get("schools", [])]
    grade_answer = (
        f"센터 등록 자료에서 확인된 수업 가능 학년은 {'·'.join(grades)}입니다. 학생의 현재 교재와 시험 범위를 함께 준비하면 학년 범위 안에서 적용할 수업 순서를 구체적으로 상담할 수 있습니다."
        if grades
        else "등록 자료에서 구체적인 수업 가능 학년이 확인되지 않았으므로 상담에서 자녀 학년의 수업 가능 여부를 먼저 확인해야 합니다. 특정 학년을 미리 단정하지 않습니다."
    )
    school_answer = (
        f"확인된 수업 가능 학교 정보에는 {'·'.join(schools[:3])} 등이 있습니다. 실제 내신 범위와 자료 활용 방식은 자녀 학교의 최근 시험 범위표와 교재를 기준으로 상담에서 다시 확인합니다."
        if schools
        else "확인된 수업 가능 학교 정보가 없는 경우에는 자녀 학교의 최근 시험 범위표와 교재를 상담에 준비해 수업 적용 범위를 먼저 확인해야 합니다. 확인되지 않은 학교명은 임의로 사용하지 않습니다."
    )
    questions = (
        "{subject} 상담에는 어떤 학습 자료를 준비하면 좋나요?",
        "{subject}에서 학생의 현재 수준은 어떻게 진단하나요?",
        "{subject}의 수업 가능 학교와 내신 자료는 어떻게 확인하나요?",
        "{subject}은 어느 학년이 상담할 수 있나요?",
        "{subject}을 비교할 때 성적보다 먼저 볼 기준은 무엇인가요?",
    )
    answer_variants = (
        f"최근 시험지, 현재 교재, 틀린 문제의 답안·풀이, 일주일 학습표를 준비하세요. 이 자료를 통해 {diagnostic}의 현재 상태와 {evidence}의 실행 여부를 나누면 상담에서 우선순위를 구체적으로 정할 수 있습니다.",
        f"정답 수만 보지 않고 {diagnostic} 중 어디에서 멈추는지 확인합니다. 학생이 혼자 설명한 과정과 일정 뒤 다시 푼 결과를 함께 보면 수업 뒤 필요한 복습 방식을 판단하기 쉽습니다.",
        school_answer,
        grade_answer,
        "특정 점수 상승을 단정하는 표현보다 진단 결과가 수업 계획, 과제 피드백, 오답 재확인 날짜로 이어지는지 확인하세요. 학생이 혼자 다시 해낸 기록을 남기는지도 중요한 비교 기준입니다.",
    )
    closers = (
        "준비한 내용은 첫 상담의 진단 순서를 정하는 데 활용합니다.",
        "확인 결과는 첫 달 학습 계획과 비교해 보는 편이 좋습니다.",
        "학생이 혼자 다시 해낸 기록도 함께 남겨 두세요.",
        "학교 일정과 가정 복습 시간을 함께 놓고 판단해야 합니다.",
        "다음 상담에서 달라진 점을 확인할 기준으로 삼을 수 있습니다.",
        "수업 횟수보다 피드백이 다음 행동으로 이어지는지 살펴보세요.",
        "최근 자료와 일정이 바뀌면 상담 기준도 다시 맞추는 것이 좋습니다.",
        "학생의 설명과 실제 답안·풀이를 함께 비교하면 더 구체적입니다.",
        "과제 완료 여부와 오답 재확인 날짜를 함께 기록해 두세요.",
        "현재 진도와 누적 빈틈을 구분해 질문하면 판단하기 쉽습니다.",
        "가정에서 가능한 복습량까지 포함해 계획을 확인하세요.",
        "특정 결과보다 진단·실행·재확인 절차를 기준으로 보세요.",
        "시험 전후의 학습 기록을 나란히 놓고 변화를 살펴보세요.",
        "자녀가 설명 없이 다시 할 수 있는지도 확인할 필요가 있습니다.",
        "교재 단계보다 막힌 원인과 다음 확인 시점을 먼저 정하세요.",
        "상담에서 합의한 기준은 주간 기록으로 다시 점검하는 것이 좋습니다.",
    )
    keep = {rank % len(questions), (rank + 2) % len(questions)}
    short_phrase = f"{local} {subject} 수업"
    result: list[dict[str, str]] = []
    for index, template in enumerate(questions):
        phrase = title if index in keep else short_phrase
        variant = (index + rank) % 3
        question = template.format(subject=phrase)
        if variant == 1:
            question = question.replace("어떻게", "어떤 기준으로").replace("무엇인가요", "어떤 점인가요")
        elif variant == 2:
            question = question.replace("어떤 학습 자료", "무슨 자료").replace("어느 학년", "어떤 학년")
        answer_code = shared.stable_number(config["slug"], local, "faq", index)
        answer = f"{answer_variants[index]} {closers[answer_code % len(closers)]}"
        result.append({"question": question, "answer": answer})
    return result


def parse_professional_reviews(value: str) -> list[dict[str, str]]:
    marker = re.compile(
        r"^\s*(?:-\s*)?((?:후기\s*예시|예시\s*후기|상담\s*후\s*기록|보호자\s*추가\s*메모|후기)\s*\d*)\s*(?:[｜|:.\-])\s*",
        re.MULTILINE,
    )
    matches = list(marker.finditer(value.strip()))
    reviews: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        raw = re.sub(r"\s+", " ", value[match.end():end]).strip().strip('“”"')
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        prefix = re.match(r"^([^:]{2,80}):\s*(.+)$", raw)
        if prefix:
            label = prefix.group(1).strip()
            raw = prefix.group(2).strip().strip('“”"')
        if raw:
            reviews.append({"label": label, "content": raw})
    return reviews


def subject_mentions(center: dict[str, object], local: str, config: dict[str, object]) -> list[dict[str, str]]:
    values: list[tuple[str, str]] = [
        ("Place", str(center.get("region", ""))),
        ("Place", str(center.get("city", ""))),
        ("Place", local),
        ("Thing", str(config["label"])),
    ]
    values.extend(("Thing", str(topic)) for topic in config["topics"])
    values.extend(("Organization", str(school)) for school in center.get("schools", []))
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for type_name, name in values:
        if name and (type_name, name) not in seen:
            seen.add((type_name, name))
            result.append({"@type": type_name, "name": name})
    return result


def configure_namespace(namespace: dict[str, object], config: dict[str, object]) -> None:
    shared.configure_namespace(namespace, config)
    parent_naturalize = namespace["naturalize_text"]
    parent_load = namespace["load_manuscripts"]
    parent_center = namespace["extract_center_data"]
    parent_schema = namespace["page_schema"]
    parent_render_page = namespace["render_page"]
    encoded_url = namespace["encoded_url"]

    def naturalize(value: str, local: str) -> str:
        return reader_facing_text(
            clean_manuscript_text(parent_naturalize(value, local), local),
            local,
            config,
        )

    def center_data(local: str) -> dict[str, object]:
        center = parent_center(local)
        row = CENTER_ROWS.get(local, {})
        english_grades = split_values(row.get("가능학년\n(영어)", ""))
        math_grades = split_values(row.get("가능학년\n(수학)", ""))
        if config["focus"] == "math":
            grades = math_grades
            fallback = "수학 수업 가능 학년 상담 확인 필요"
        elif config["focus"] == "english":
            grades = english_grades
            fallback = "영어 수업 가능 학년 상담 확인 필요"
        else:
            math_set = set(math_grades)
            grades = [grade for grade in english_grades if grade in math_set]
            fallback = "영어·수학 공통 수업 가능 학년 상담 확인 필요"
        center["verified_grades"] = grades
        center["grade_status"] = "" if grades else fallback
        center["grades"] = grades or [fallback]
        center["schools"] = unique_values([str(item) for item in center.get("schools", [])])
        return center

    def manuscripts() -> dict[str, dict[str, object]]:
        values = parent_load()
        for rank, local in enumerate(sorted(values)):
            manuscript = values[local]
            center = center_data(local)
            verified_grades = [str(item) for item in center.get("verified_grades", [])]
            schools = [str(item) for item in center.get("schools", [])]
            manuscript["intro"] = build_intro(local, center, config, rank)
            polished_sections: list[tuple[str, list[str]]] = []
            for heading, paragraphs in manuscript.get("sections", []):
                polished_sections.append(
                    (
                        final_polish(str(heading), local, config, verified_grades, schools),
                        [final_polish(str(paragraph), local, config, verified_grades, schools) for paragraph in paragraphs],
                    )
                )
            if polished_sections:
                target = rank % len(polished_sections)
                polished_sections[target][1].append(grounded_paragraph(local, center, config, rank))
            manuscript["sections"] = polished_sections
            manuscript["faqs"] = build_faqs(local, center, config, rank)
            for review in manuscript.get("reviews", []):
                review["label"] = final_polish(str(review.get("label", "")), local, config, verified_grades, schools)
                review["content"] = final_polish(str(review["content"]), local, config, verified_grades, schools)
            manuscript["summary"] = build_summary(local, center, config, rank)
            manuscript["meta"] = build_meta(local, center, config, rank)
            answer_heading, answer_text, answer_tags = build_answer(local, center, config, rank)
            manuscript["answer_heading"] = answer_heading
            manuscript["answer_text"] = answer_text
            manuscript["answer_tags"] = answer_tags

        sentence_frequencies: dict[str, int] = {}
        question_frequencies: dict[str, int] = {}

        def count_sentences(value: str, local: str) -> None:
            for sentence in shared.sentence_parts(value):
                normalized = shared.normalize_for_frequency(sentence, local)
                sentence_frequencies[normalized] = sentence_frequencies.get(normalized, 0) + 1

        for local, manuscript in values.items():
            for paragraph in manuscript.get("intro", []):
                count_sentences(str(paragraph), local)
            for _, paragraphs in manuscript.get("sections", []):
                for paragraph in paragraphs:
                    count_sentences(str(paragraph), local)
            for faq in manuscript.get("faqs", []):
                normalized = shared.normalize_for_frequency(str(faq["question"]), local)
                question_frequencies[normalized] = question_frequencies.get(normalized, 0) + 1
                count_sentences(str(faq["answer"]), local)
            for review in manuscript.get("reviews", []):
                count_sentences(str(review["content"]), local)
            count_sentences(str(manuscript.get("summary", "")), local)

        rank_by_local = {local: rank for rank, local in enumerate(sorted(values))}
        for local, manuscript in values.items():
            rank = rank_by_local[local]
            manuscript["sections"] = [
                (
                    heading,
                    [
                        professional_diversify_text(
                            str(paragraph), local, rank,
                            100 + section_index * 10 + paragraph_index,
                            sentence_frequencies, config,
                        )
                        for paragraph_index, paragraph in enumerate(paragraphs)
                    ],
                )
                for section_index, (heading, paragraphs) in enumerate(manuscript.get("sections", []))
            ]
            for faq_index, faq in enumerate(manuscript.get("faqs", [])):
                normalized = shared.normalize_for_frequency(str(faq["question"]), local)
                faq["question"] = professional_diversify_question(
                    str(faq["question"]), local, rank, faq_index,
                    question_frequencies.get(normalized, 0), config,
                )
                faq["answer"] = professional_diversify_text(
                    str(faq["answer"]), local, rank, 300 + faq_index,
                    sentence_frequencies, config,
                )
            for review_index, review in enumerate(manuscript.get("reviews", [])):
                review["content"] = professional_diversify_text(
                    str(review["content"]), local, rank, 400 + review_index,
                    sentence_frequencies, config,
                )
            manuscript["summary"] = professional_diversify_text(
                str(manuscript.get("summary", "")), local, rank, 500,
                sentence_frequencies, config,
            )

            center = center_data(local)
            verified_grades = [str(item) for item in center.get("verified_grades", [])]
            schools = [str(item) for item in center.get("schools", [])]
            title = str(manuscript["title"])
            manuscript["intro"] = [
                replace_title_repetition(
                    final_polish(str(paragraph), local, config, verified_grades, schools),
                    title, local, config, 600 + index, keep_first=index == 0,
                )
                for index, paragraph in enumerate(manuscript.get("intro", []))
            ]
            final_sections: list[tuple[str, list[str]]] = []
            for section_index, (heading, paragraphs) in enumerate(manuscript.get("sections", [])):
                final_heading = final_polish(str(heading), local, config, verified_grades, schools)
                final_heading = replace_title_repetition(
                    final_heading, title, local, config, 700 + section_index,
                    keep_first=section_index == 0,
                )
                final_paragraphs = [
                    replace_title_repetition(
                        final_polish(str(paragraph), local, config, verified_grades, schools),
                        title, local, config, 800 + section_index * 10 + paragraph_index,
                    )
                    for paragraph_index, paragraph in enumerate(paragraphs)
                ]
                final_sections.append((final_heading, final_paragraphs))
            manuscript["sections"] = final_sections
            manuscript["faqs"] = [
                {
                    "question": final_polish(str(item["question"]), local, config, verified_grades, schools),
                    "answer": final_polish(str(item["answer"]), local, config, verified_grades, schools),
                }
                for item in build_faqs(local, center, config, rank)
            ]
            for review_index, review in enumerate(manuscript.get("reviews", [])):
                review["label"] = replace_title_repetition(
                    final_polish(str(review.get("label", "")), local, config, verified_grades, schools),
                    title, local, config, 900 + review_index,
                )
                review["content"] = replace_title_repetition(
                    final_polish(str(review["content"]), local, config, verified_grades, schools),
                    title, local, config, 920 + review_index,
                    keep_first=review_index == 0,
                )
            manuscript["summary"] = final_polish(
                build_summary(local, center, config, rank), local, config, verified_grades, schools,
            )
            manuscript["meta"] = final_polish(
                build_meta(local, center, config, rank), local, config, verified_grades, schools,
            )
            answer_heading, answer_text, answer_tags = build_answer(local, center, config, rank)
            manuscript["answer_heading"] = final_polish(answer_heading, local, config, verified_grades, schools)
            manuscript["answer_text"] = final_polish(answer_text, local, config, verified_grades, schools)
            manuscript["answer_tags"] = [
                final_polish(str(tag), local, config, verified_grades, schools) for tag in answer_tags
            ]
        return values

    def links(local: str, index: int, order: list[str], center_url: str) -> list[dict[str, str]]:
        previous_local = order[index - 1] if index else order[-1]
        next_local = order[index + 1] if index + 1 < len(order) else order[0]
        sibling_slugs = [item["slug"] for item in CATEGORIES if item["slug"] != config["slug"]]
        items = [{"name": f"{config['label']} 전체 지역", "url": encoded_url("과목별학원", config["slug"])}]
        items.extend(
            {"name": f"{local} {next(item['label'] for item in CATEGORIES if item['slug'] == slug)}", "url": encoded_url("과목별학원", slug, local)}
            for slug in sibling_slugs
        )
        base_slug = "영어학원" if config["focus"] == "english" else "수학학원"
        items.append({"name": f"{local} {base_slug}", "url": encoded_url("과목별학원", base_slug, local)})
        if center_url:
            items.append({"name": f"{local} 전국센터 안내", "url": center_url})
        items.extend(
            [
                {"name": str(config["study_name"]), "url": encoded_url("교육정보", config["study_path"])},
                {"name": f"이전 지역 · {previous_local}", "url": encoded_url("과목별학원", config["slug"], previous_local)},
                {"name": f"다음 지역 · {next_local}", "url": encoded_url("과목별학원", config["slug"], next_local)},
            ]
        )
        return items

    def schema(local: str, manuscript: dict[str, object], center: dict[str, object], representative: str, related: list[dict[str, str]]) -> dict[str, object]:
        data = parent_schema(local, manuscript, center, representative, related)
        graph = data.get("@graph", [])
        by_type = {item.get("@type"): item for item in graph if isinstance(item, dict)}
        about = [{"@type": "Thing", "name": str(config["label"])}]
        about.extend({"@type": "Thing", "name": str(topic)} for topic in config["topics"])
        mentions = subject_mentions(center, local, config)
        headings = [str(heading) for heading, _ in manuscript.get("sections", [])]
        keywords = [str(manuscript["title"]), str(config["label"]), local, *[str(subject) for subject in config["subjects"]], *headings[:4]]

        webpage = by_type.get("WebPage", {})
        webpage["about"] = about
        webpage["mentions"] = mentions
        webpage["keywords"] = keywords
        webpage["significantLink"] = [str(item["url"]) for item in related[:6]]

        organization = by_type.get("EducationalOrganization", {})
        for key in ("alternateName", "description", "educationalLevel", "teaches", "knowsAbout", "makesOffer"):
            organization.pop(key, None)

        local_business = by_type.get("LocalBusiness", {})
        for key in ("alternateName", "description", "educationalLevel", "teaches", "knowsAbout", "makesOffer"):
            local_business.pop(key, None)

        article = by_type.get("Article", {})
        article["articleSection"] = [str(config["label"]), str(center.get("region", "")), str(center.get("city", "")), local, *headings]
        article["about"] = about
        article["mentions"] = mentions
        article["keywords"] = keywords
        verified_grades = [str(item) for item in center.get("verified_grades", [])]
        if verified_grades:
            article["audience"] = {
                "@type": "EducationalAudience",
                "educationalRole": "student",
                "audienceType": " · ".join(verified_grades),
            }
        else:
            article.pop("audience", None)

        service = by_type.get("Service", {})
        service["serviceType"] = str(config["label"])
        service["about"] = about[1:]
        service["mentions"] = mentions
        service["category"] = list(config["topics"][:3])
        if verified_grades:
            service["audience"] = {
                "@type": "EducationalAudience",
                "educationalRole": "student",
                "audienceType": " · ".join(verified_grades),
            }
        else:
            service.pop("audience", None)
        return data

    def render_page(local: str, index: int, order: list[str], manuscript: dict[str, object], center: dict[str, object], representative: str) -> str:
        output = parent_render_page(local, index, order, manuscript, center, representative)
        output = output.replace("<dt>제공 주소</dt>", "<dt>센터 주소</dt>")
        output = output.replace("<dt>제공 학교 참고</dt>", "<dt>수업 가능 학교</dt>")
        output = output.replace(
            "페이지의 학교·센터 정보는 제공된 자료를 기준으로 안내하며",
            "센터·학교 정보는 확인된 등록 자료를 기준으로 안내하며",
        )
        output = re.sub(
            r"<dt>[^<]*수업 가능 학년</dt>",
            f"<dt>{html.escape(str(config['label']))} 수업 가능 학년</dt>",
            output,
            count=1,
        )
        output = re.sub(
            rf"<h2>{re.escape(local)} .*? 상담 참고 사례</h2>",
            f"<h2>{html.escape(local)} {html.escape(str(config['label']))} 상담 참고 사례</h2>",
            output,
            count=1,
        )
        return output

    namespace["naturalize_text"] = naturalize
    namespace["extract_center_data"] = center_data
    namespace["parse_reviews"] = parse_professional_reviews
    namespace["load_manuscripts"] = manuscripts
    namespace["internal_links"] = links
    namespace["page_schema"] = schema
    namespace["render_page"] = render_page
    namespace["render_hub"] = lambda order, directory: render_hub(namespace, config, order, directory)


def hub_faq(config: dict[str, object]) -> list[dict[str, object]]:
    subject_text = "·".join(str(value) for value in config["subjects"])
    return [
        {
            "@type": "Question",
            "name": f"동네별 {config['label']} 페이지에서는 무엇을 확인할 수 있나요?",
            "acceptedAnswer": {"@type": "Answer", "text": f"제공된 지역별 안내와 센터 정보를 바탕으로 학생의 {subject_text} 학습 상태, 학교 자료 활용, 복습 순서와 상담 준비사항을 확인할 수 있습니다."},
        },
        {
            "@type": "Question",
            "name": f"{config['label']} 상담에는 어떤 자료를 준비하면 좋나요?",
            "acceptedAnswer": {"@type": "Answer", "text": "최근 시험지와 교재, 학교 시험 범위표, 틀린 문제의 답안·풀이 기록과 일주일 학습 시간표를 준비하면 현재 상태와 다음 계획을 구체적으로 살펴볼 수 있습니다."},
        },
        {
            "@type": "Question",
            "name": f"{config['label']}을 비교할 때 가장 먼저 볼 기준은 무엇인가요?",
            "acceptedAnswer": {"@type": "Answer", "text": "선행 진도나 문제 수보다 학생이 막힌 지점을 어떻게 진단하고, 수업 뒤 어떤 기록을 남기며, 일정 기간 후 오답을 다시 확인하는지부터 비교하는 편이 좋습니다."},
        },
    ]


def render_hub(namespace: dict[str, object], config: dict[str, object], order: list[str], directory: str) -> str:
    encoded_url = namespace["encoded_url"]
    esc = namespace["esc"]
    page_url = encoded_url("과목별학원", config["slug"])
    description = f"371개 동네별 {config['label']} 안내와 검증 가능한 센터 정보를 바탕으로 현재 학습 상태, 학교 자료, 오답 복습과 상담 준비 기준을 안내합니다."
    faqs = hub_faq(config)
    list_items = [
        {"@type": "ListItem", "position": index, "item": {"@type": "WebPage", "name": f"{local} {config['label']}", "url": encoded_url("과목별학원", config["slug"], local)}}
        for index, local in enumerate(order, start=1)
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "@id": page_url + "#webpage", "url": page_url, "name": f"{config['label']} 지역 안내 | {SITE_NAME}", "description": description, "inLanguage": "ko-KR", "isPartOf": {"@id": SITE_URL + "/#website"}, "publisher": {"@id": SITE_URL + "/#organization"}, "breadcrumb": {"@id": page_url + "#breadcrumb"}, "about": [{"@type": "Thing", "name": config["label"]}, *[{"@type": "Thing", "name": topic} for topic in config["topics"]]], "datePublished": TODAY, "dateModified": TODAY},
            {"@type": "BreadcrumbList", "@id": page_url + "#breadcrumb", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_URL + "/"}, {"@type": "ListItem", "position": 2, "name": "과목별학원", "item": encoded_url("과목별학원")}, {"@type": "ListItem", "position": 3, "name": f"{config['label']} 지역 안내", "item": page_url}]},
            {"@type": "ItemList", "@id": page_url + "#directory", "name": f"동네별 {config['label']} 안내", "numberOfItems": len(order), "itemListElement": list_items},
            {"@type": "FAQPage", "@id": page_url + "#faq", "mainEntity": faqs},
        ],
    }
    faq_markup = "".join(
        f'<details class="math-faq-item"{" open" if index == 0 else ""}><summary>{esc(item["name"])}</summary><p>{esc(item["acceptedAnswer"]["text"])}</p></details>'
        for index, item in enumerate(faqs)
    )
    search_id = f"{config['card_id']}-local-search"
    count_id = f"{config['card_id']}-search-count"
    tags = "".join(f"<span>{html.escape(tag)}</span>" for tag in config["hero_tags"][0])
    return f'''<!doctype html>
<html lang="ko"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(config['label'])} 지역 안내 | 371개 동네별 학습관리 | {SITE_NAME}</title>
  <meta name="description" content="{esc(description)}"><meta name="robots" content="index,follow"><link rel="canonical" href="{page_url}">
  <meta property="og:type" content="website"><meta property="og:title" content="{esc(config['label'])} 지역 안내 | {SITE_NAME}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{page_url}"><meta property="og:image" content="{SITE_URL}/assets/title.png">
  <link rel="icon" href="/assets/favicon.png"><link rel="stylesheet" href="/assets/fab.css"><link rel="stylesheet" href="/assets/header.css"><link rel="stylesheet" href="/assets/math-academy.css"><link rel="stylesheet" href="/assets/english-academy.css">
  <script type="application/ld+json">{compact_json(schema)}</script>
</head><body class="math-academy-page english-academy-page">
  <header class="site-header"><nav class="nav" aria-label="주요 메뉴"><a class="logo" href="/"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a><div class="nav-links" aria-label="페이지 이동"><a href="/">홈</a><a href="/overview/">학원소개</a><a href="/guide/">학습가이드</a><a href="/교육정보/">교육정보</a><a href="/학부모후기/">학부모후기</a><a class="active" href="/과목별학원/">과목별학원</a><a href="/center/">전국센터</a></div></nav></header>
  <main>
    <section class="math-hero"><div class="math-container"><nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/과목별학원/">과목별학원</a><span>›</span><span aria-current="page">{esc(config['label'])} 지역 안내</span></nav><div class="math-hero-grid"><div><p class="math-eyebrow">{esc(config['directory'])}</p><h1>동네별 {esc(config['label'])} 안내</h1><p class="math-hero-lead">{esc(config['hub_lead'])}</p></div><aside class="math-hero-panel"><strong>현재 학습 자료에서 출발합니다</strong><p>{esc(config['hero_copy'])}</p><div class="math-step-row">{tags}</div></aside></div></div></section>
    <section class="math-section paper"><div class="math-container math-quick-grid"><article class="math-summary-card"><strong>371 LOCAL GUIDES</strong><h2>지역과 학생 상황을 함께 보는 {esc(config['label'])} 안내</h2><p>각 페이지는 제공된 동네별 안내 내용과 센터·학교 자료를 사용합니다. 특정 결과를 약속하기보다 현재 학습 기록과 수업 후 복습 과정을 상담에서 구체적으로 확인하도록 구성했습니다.</p></article><aside class="math-info-card"><h2>상담 전 확인 기준</h2><dl><div><dt>현재 상태</dt><dd>최근 시험지·교재와 답안 또는 풀이 기록</dd></div><div><dt>학교 일정</dt><dd>제공 학교 자료와 시험 범위의 활용 방식</dd></div><div><dt>수업 과정</dt><dd>진단 결과가 과제와 다음 계획에 반영되는 절차</dd></div><div><dt>복습</dt><dd>오답 원인 기록과 일정 기간 뒤 재확인</dd></div></dl></aside></div></section>
    <section class="math-section"><div class="math-container"><p class="math-eyebrow">FIND YOUR LOCAL PAGE</p><h2 style="margin:0;font-family:'Noto Serif KR',serif;font-size:clamp(28px,4vw,44px);">동네명으로 {esc(config['label'])} 찾기</h2><div class="math-directory-tools"><input class="math-search" id="{search_id}" type="search" placeholder="예: 명일동, 불당동, 가경동" aria-label="동네명 검색"><div class="math-count" id="{count_id}">전체 371개 지역</div></div>{directory}</div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card"><p class="math-eyebrow">FAQ</p><h2>{esc(config['label'])} 안내 이용 전 확인사항</h2><div class="math-faq-list">{faq_markup}</div></div></section>
    <section class="math-section"><div class="math-narrow math-links-card"><p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>상담 전 함께 보면 좋은 안내</h2><div class="math-links"><a href="/교육정보/수학-공부법/">수학 공부법</a><a href="/교육정보/영어-공부법/">영어 공부법</a><a href="/교육정보/오답노트-작성법/">오답노트 작성</a><a href="/center/">전국센터 찾기</a></div></div></section>
  </main>
  <div class="wawa-fixed-fab-container"><a href="tel:010-3957-8283" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a><a href="https://blogsms.net/01039578283" target="_blank" rel="noopener" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a><a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" rel="noopener" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a></div>
  <footer class="math-footer"><strong>{SITE_NAME}</strong><br>동네별 {esc(config['label'])} 페이지는 제공된 센터·학교·안내 자료를 기준으로 구성했습니다.</footer>
  <script>(()=>{{const input=document.getElementById('{search_id}');const count=document.getElementById('{count_id}');const links=[...document.querySelectorAll('.math-local-grid a')];input.addEventListener('input',()=>{{const query=input.value.trim().toLowerCase();let visible=0;links.forEach(link=>{{const show=!query||link.dataset.local.toLowerCase().includes(query);link.hidden=!show;if(show)visible+=1;}});document.querySelectorAll('.math-city').forEach(city=>{{city.hidden=![...city.querySelectorAll('a')].some(link=>!link.hidden);}});document.querySelectorAll('.math-region').forEach(region=>{{const show=[...region.querySelectorAll('.math-city')].some(city=>!city.hidden);region.hidden=!show;if(query&&show)region.open=true;}});count.textContent=query?`${{visible}}개 지역 검색됨`:'전체 371개 지역';}});}})();</script>
</body></html>'''


def update_master_subject_hub(namespaces: dict[str, dict[str, object]]) -> None:
    path = ROOT / "과목별학원" / "index.html"
    source = path.read_text(encoding="utf-8")
    cards: list[str] = []
    for config in CATEGORIES:
        card = (
            f'<a class="subject-category-card" id="{config["card_id"]}" data-number="{config["card_number"]}" '
            f'href="./{config["slug"]}/"><small>{config["card_small"]}</small><h3>{config["label"]}</h3>'
            f'<p>{config["card_copy"]}</p><span class="subject-status">371개 지역 안내 보기 →</span></a>'
        )
        pattern = rf'<a class="subject-category-card" id="{re.escape(str(config["card_id"]))}".*?</a>'
        if re.search(pattern, source, re.DOTALL):
            source = re.sub(pattern, card, source, count=1, flags=re.DOTALL)
        else:
            cards.append(card)
    if cards:
        matches = list(re.finditer(r'<a class="subject-category-card".*?</a>', source, re.DOTALL))
        if not matches:
            raise ValueError("subject category cards not found")
        position = matches[-1].end()
        source = source[:position] + "\n          " + "\n          ".join(cards) + source[position:]

    description = "수학·영어 단과, 학년별 영수학원과 수학·영어·영수 전문학원까지 10개 지역별 안내를 학생의 현재 학습 상황에 맞춰 확인할 수 있습니다."
    source = re.sub(r'(<meta name="description" content=")[^"]*(">)', rf'\g<1>{description}\g<2>', source, count=1)
    source = re.sub(r'(<meta property="og:description" content=")[^"]*(">)', rf'\g<1>{description}\g<2>', source, count=1)
    source = re.sub(r"실제 지역 페이지가 준비된 [^<.]+ 분류만 표시합니다\.", "실제 지역 페이지가 준비된 열 가지 분류만 표시합니다.", source)

    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL)
    if not match:
        raise ValueError("master subject hub JSON-LD not found")
    data = json.loads(match.group(1))
    encoded_url = next(iter(namespaces.values()))["encoded_url"]
    for item in data.get("@graph", []):
        if item.get("@type") == "EducationalOrganization":
            current = list(item.get("knowsAbout", []))
            for name, _ in ALL_TOPICS:
                if name not in current:
                    current.append(name)
            item["knowsAbout"] = current
        elif item.get("@type") == "CollectionPage":
            item["description"] = description
            item["about"] = [{"@type": "Thing", "name": name} for name, _ in ALL_TOPICS]
            item["dateModified"] = TODAY
        elif item.get("@type") == "ItemList" and str(item.get("@id", "")).endswith("#topics"):
            item["numberOfItems"] = len(ALL_TOPICS)
            item["itemListElement"] = [
                {"@type": "ListItem", "position": index, "item": {"@type": "Thing", "name": name, "url": encoded_url("과목별학원", slug)}}
                for index, (name, slug) in enumerate(ALL_TOPICS, start=1)
            ]
    source = source[:match.start(1)] + compact_json(data) + source[match.end(1):]
    path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    namespaces: dict[str, dict[str, object]] = {}
    for config in CATEGORIES:
        namespace = shared.transformed_namespace(config)
        configure_namespace(namespace, config)
        namespace["main"]()
        namespaces[str(config["slug"])] = namespace
        print(f'{config["slug"]}: generated 371 detail pages and one hub')
    update_master_subject_hub(namespaces)
    print("updated master subject hub with ten live categories")


if __name__ == "__main__":
    main()
