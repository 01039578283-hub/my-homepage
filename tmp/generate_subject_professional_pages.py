from __future__ import annotations

import csv
import hashlib
import html
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_subject_combined_pages as shared


ROOT = Path(__file__).resolve().parents[1]
SITE_URL = "https://wawa-center.kr"
SITE_NAME = "와와학습코칭센터"
TODAY = "2026-08-03"
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
    {
        "slug": "고등전문학원",
        "label": "고등 전문학원",
        "zip": "고등 전문학원.zip",
        "focus": "combined",
        "level": "고등",
        "grade_prefix": "고",
        "school_marker": "",
        "eyebrow": "HIGH SCHOOL SPECIALIST ACADEMY GUIDE",
        "directory": "HIGH SCHOOL SPECIALIST ACADEMY DIRECTORY",
        "card_id": "high-specialist",
        "card_number": "11",
        "card_small": "HIGH SCHOOL SPECIALIST",
        "representative_seed": "wawa-high-specialist-v1",
        "card_copy": "고등 영어·수학의 내신 범위, 모의고사 학습, 시험 시간 배분과 오답 재확인 기준을 함께 살펴봅니다.",
        "study_path": "고등학생-공부법",
        "study_name": "고등학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("고등 영어 내신", "고등 수학 내신", "내신·모의고사 균형", "시험 시간 관리", "고등 오답 재학습"),
        "focus_terms": ("고등 영어·수학", "학교 내신 범위·모의고사 학습·과목별 시간 배분", "시험 일정과 주간 실행 기록"),
        "title_references": ("{local} 고등 학습 설계", "{local} 고등 과정 상담", "이 고등 학습 과정", "해당 고등 단계 관리 방식", "고등 내신·시간 관리 안내", "지역별 고등 학습 기준"),
        "related_pages": (("고등영수학원", "고등 영수학원"), ("중등전문학원", "중등 전문학원"), ("초등전문학원", "초등 전문학원"), ("영수전문학원", "영수 전문학원")),
        "base_page": ("고등영수학원", "고등 영수학원"),
        "hero_copy": "최근 고등 영어·수학 시험지와 교재를 바탕으로 학교 내신 범위, 모의고사 학습, 과목별 시간 배분과 오답 재확인 순서를 점검합니다.",
        "hero_tags": (("고등 내신", "모의고사", "시간 배분"), ("영어 답안", "수학 풀이", "오답 재확인"), ("학교 범위", "과목별 우선순위", "주간 계획"), ("현재 상태", "시험 일정", "다음 점검")),
        "hub_lead": "고등학생의 영어·수학을 같은 진도표로 묶지 않고 학교 내신 범위, 모의고사 학습, 과목별 시간 배분과 오답 재확인 기준을 나누어 볼 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "중등전문학원",
        "label": "중등 전문학원",
        "zip": "중등 전문학원.zip",
        "focus": "combined",
        "level": "중등",
        "grade_prefix": "중",
        "school_marker": "",
        "eyebrow": "MIDDLE SCHOOL SPECIALIST ACADEMY GUIDE",
        "directory": "MIDDLE SCHOOL SPECIALIST ACADEMY DIRECTORY",
        "card_id": "middle-specialist",
        "card_number": "12",
        "card_small": "MIDDLE SCHOOL SPECIALIST",
        "representative_seed": "wawa-middle-specialist-v1",
        "card_copy": "중등 영어·수학의 학교 진도, 지필·수행평가 준비, 과제 루틴과 오답 복습 기준을 확인합니다.",
        "study_path": "중학생-공부법",
        "study_name": "중학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("중등 영어 문법·독해", "중등 수학 개념·유형", "중등 내신 준비", "과제·복습 습관", "중등 오답 재학습"),
        "focus_terms": ("중등 영어·수학", "학교 진도·지필평가·수행평가 준비", "과제 실행과 주간 복습 기록"),
        "title_references": ("{local} 중등 학습 설계", "{local} 중등 과정 상담", "이 중등 학습 과정", "해당 중등 단계 관리 방식", "중등 내신·습관 관리 안내", "지역별 중등 학습 기준"),
        "related_pages": (("중등영수학원", "중등 영수학원"), ("고등전문학원", "고등 전문학원"), ("초등전문학원", "초등 전문학원"), ("영수전문학원", "영수 전문학원")),
        "base_page": ("중등영수학원", "중등 영수학원"),
        "hero_copy": "최근 중등 영어·수학 학습 자료를 바탕으로 학교 진도, 지필·수행평가 준비, 과제 실행과 오답 복습 순서를 확인합니다.",
        "hero_tags": (("중등 내신", "과제 루틴", "오답 복습"), ("영어 문법", "수학 개념", "학교 진도"), ("지필 평가", "수행평가", "주간 계획"), ("현재 단원", "취약 영역", "다음 확인")),
        "hub_lead": "중학생의 영어·수학을 단순 선행 진도로 비교하지 않고 학교 진도, 지필·수행평가 준비, 과제 실행과 오답 복습의 연결 과정을 살펴볼 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "초등전문학원",
        "label": "초등 전문학원",
        "zip": "초등 전문학원.zip",
        "focus": "combined",
        "level": "초등",
        "grade_prefix": "초",
        "school_marker": "",
        "eyebrow": "ELEMENTARY SPECIALIST ACADEMY GUIDE",
        "directory": "ELEMENTARY SPECIALIST ACADEMY DIRECTORY",
        "card_id": "elementary-specialist",
        "card_number": "13",
        "card_small": "ELEMENTARY SPECIALIST",
        "representative_seed": "wawa-elementary-specialist-v1",
        "card_copy": "초등 영어 읽기·어휘와 수학 개념·연산을 과제 습관, 설명 과정과 짧은 복습 기준으로 살펴봅니다.",
        "study_path": "초등학생-공부법",
        "study_name": "초등학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("초등 영어 읽기·어휘", "초등 수학 개념·연산", "초등 학습 습관", "과제·질문 기록", "초등 오답 재학습"),
        "focus_terms": ("초등 영어·수학", "읽기·어휘·개념·연산", "과제·질문·짧은 복습 기록"),
        "title_references": ("{local} 초등 학습 설계", "{local} 초등 과정 상담", "이 초등 학습 과정", "해당 초등 단계 관리 방식", "초등 기초·습관 관리 안내", "지역별 초등 학습 기준"),
        "related_pages": (("초등영수학원", "초등 영수학원"), ("중등전문학원", "중등 전문학원"), ("고등전문학원", "고등 전문학원"), ("영수전문학원", "영수 전문학원")),
        "base_page": ("초등영수학원", "초등 영수학원"),
        "hero_copy": "최근 초등 영어·수학 교재와 과제 기록을 바탕으로 읽기·어휘, 개념·연산, 질문 습관과 짧은 복습 순서를 확인합니다.",
        "hero_tags": (("읽기·어휘", "개념·연산", "학습 습관"), ("과제 기록", "질문 과정", "짧은 복습"), ("현재 교재", "설명하기", "오답 재확인"), ("기초 확인", "학습 리듬", "다음 계획")),
        "hub_lead": "초등학생의 영어·수학을 문제 수로만 비교하지 않고 읽기·어휘, 개념·연산, 질문 습관과 짧은 복습이 이어지는 과정을 살펴볼 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "고등내신학원",
        "label": "고등 내신학원",
        "zip": "고등 내신학원.zip",
        "focus": "combined",
        "level": "고등",
        "grade_prefix": "고",
        "school_marker": "",
        "eyebrow": "HIGH SCHOOL ACADEMIC RECORD GUIDE",
        "directory": "HIGH SCHOOL ACADEMIC RECORD DIRECTORY",
        "card_id": "high-school-record",
        "card_number": "14",
        "card_small": "HIGH SCHOOL ACADEMIC RECORD",
        "representative_seed": "wawa-high-school-record-v1",
        "card_copy": "학교별 시험 범위와 일정, 영어·수학 취약 단원, 오답 재풀이 기록을 기준으로 고등 내신 준비 과정을 살펴봅니다.",
        "study_path": "고등학생-공부법",
        "study_name": "고등학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("고등 내신 범위", "고등 영어 내신", "고등 수학 내신", "시험 일정 관리", "고등 내신 오답 복습"),
        "focus_terms": ("고등 내신 준비", "학교별 시험 범위·영어·수학 취약 단원·시험 일정", "최근 시험지·범위표·오답 재풀이 기록"),
        "title_references": ("{local} 고등 내신 준비", "{local} 고등 시험 대비 상담", "이 고등 내신 과정", "해당 학교 시험 대비 방식", "고등 내신 범위·오답 관리 안내", "지역별 고등 내신 기준"),
        "related_pages": (("고등전문학원", "고등 전문학원"), ("고등영수학원", "고등 영수학원"), ("중등내신학원", "중등 내신학원"), ("영수전문학원", "영수 전문학원")),
        "base_page": ("고등전문학원", "고등 전문학원"),
        "hero_copy": "최근 고등 영어·수학 시험지와 학교 범위표를 바탕으로 과목별 취약 단원, 남은 시험 기간, 오답 재풀이와 다음 점검 순서를 확인합니다.",
        "hero_tags": (("학교 시험 범위", "과목별 취약 단원", "오답 재풀이"), ("영어 내신", "수학 내신", "시험 일정"), ("학교 자료", "최근 시험지", "주간 계획"), ("현재 상태", "남은 기간", "다음 점검")),
        "hub_lead": "고등 내신을 단순 문제량이나 선행 진도로 비교하지 않고 학교별 시험 범위와 일정, 영어·수학의 서로 다른 취약 단원, 오답 재풀이 기록을 함께 확인할 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "중등내신학원",
        "label": "중등 내신학원",
        "zip": "중등 내신학원.zip",
        "focus": "combined",
        "level": "중등",
        "grade_prefix": "중",
        "school_marker": "",
        "eyebrow": "MIDDLE SCHOOL ACADEMIC RECORD GUIDE",
        "directory": "MIDDLE SCHOOL ACADEMIC RECORD DIRECTORY",
        "card_id": "middle-school-record",
        "card_number": "15",
        "card_small": "MIDDLE SCHOOL ACADEMIC RECORD",
        "representative_seed": "wawa-middle-school-record-v1",
        "card_copy": "학교 진도와 지필·수행평가 일정, 영어·수학 취약 단원, 과제와 오답 복습 흐름을 기준으로 중등 내신을 살펴봅니다.",
        "study_path": "중학생-공부법",
        "study_name": "중학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("중등 내신 범위", "중등 영어 내신", "중등 수학 내신", "지필·수행평가 준비", "중등 내신 오답 복습"),
        "focus_terms": ("중등 내신 준비", "학교 진도·지필평가·수행평가·영어·수학 취약 단원", "최근 시험지·학교 자료·과제·오답 복습 기록"),
        "title_references": ("{local} 중등 내신 준비", "{local} 중등 시험 대비 상담", "이 중등 내신 과정", "해당 학교 시험 대비 방식", "중등 내신 범위·과제 관리 안내", "지역별 중등 내신 기준"),
        "related_pages": (("중등전문학원", "중등 전문학원"), ("중등영수학원", "중등 영수학원"), ("고등내신학원", "고등 내신학원"), ("영수전문학원", "영수 전문학원")),
        "base_page": ("중등전문학원", "중등 전문학원"),
        "hero_copy": "최근 중등 영어·수학 학습 자료와 학교 시험 범위를 바탕으로 지필·수행평가 일정, 과목별 취약 단원, 과제 실행과 오답 복습 순서를 확인합니다.",
        "hero_tags": (("학교 시험 범위", "지필·수행평가", "오답 복습"), ("영어 내신", "수학 내신", "과제 실행"), ("학교 진도", "최근 시험지", "주간 계획"), ("현재 단원", "취약 영역", "다음 확인")),
        "hub_lead": "중등 내신을 시험 직전 문제풀이만으로 비교하지 않고 학교 진도와 지필·수행평가 일정, 영어·수학 취약 단원, 과제 실행과 오답 복습의 연결 과정을 확인할 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "영어내신학원",
        "label": "영어 내신학원",
        "zip": "영어 내신학원.zip",
        "focus": "english",
        "level": "초·중·고",
        "grade_prefix": "",
        "school_marker": "",
        "eyebrow": "LOCAL ENGLISH SCHOOL-RECORD GUIDE",
        "directory": "ENGLISH SCHOOL-RECORD DIRECTORY",
        "card_id": "english-school-record",
        "card_number": "16",
        "card_small": "ENGLISH SCHOOL RECORD",
        "representative_seed": "wawa-english-school-record-v1",
        "card_copy": "학교 시험 범위와 교과서 자료, 어휘·문법·독해·서술형 오답 기록을 기준으로 영어 내신 준비 과정을 살펴봅니다.",
        "study_path": "영어-공부법",
        "study_name": "영어 공부법",
        "subjects": ("영어",),
        "topics": ("영어 내신 범위", "교과서·학교 자료", "어휘·문법 적용", "독해 근거·서술형 표현", "영어 내신 오답 복습"),
        "focus_terms": ("영어 내신 준비", "학교별 시험 범위·교과서 본문·어휘·문법·독해·서술형", "최근 영어 시험지·범위표·오답 기록"),
        "title_references": ("{local} 영어 내신 준비", "{local} 영어 시험 대비 상담", "이 영어 내신 과정", "해당 학교 영어 대비 방식", "영어 내신 범위·답안 관리 안내", "지역별 영어 내신 기준"),
        "related_pages": (("영어학원", "영어학원"), ("영어전문학원", "영어 전문학원"), ("고등내신학원", "고등 내신학원"), ("중등내신학원", "중등 내신학원")),
        "base_page": ("영어학원", "영어학원"),
        "hero_copy": "최근 영어 시험지와 학교 범위표를 바탕으로 어휘 누적, 문법 적용, 독해 답의 근거, 서술형 표현과 오답 재확인 순서를 살펴봅니다.",
        "hero_tags": (("학교 영어 범위", "교과서 자료", "오답 재확인"), ("어휘 누적", "문법 적용", "독해 근거"), ("서술형 표현", "최근 시험지", "주간 계획"), ("현재 상태", "남은 기간", "다음 점검")),
        "hub_lead": "영어 내신을 단어 시험이나 문제 수로만 비교하지 않고 학교별 시험 범위와 교과서 자료, 어휘·문법 적용, 독해 근거와 서술형 오답 기록을 함께 확인할 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "수학내신학원",
        "label": "수학 내신학원",
        "zip": "수학 내신학원.zip",
        "focus": "math",
        "level": "초·중·고",
        "grade_prefix": "",
        "school_marker": "",
        "eyebrow": "LOCAL MATH SCHOOL-RECORD GUIDE",
        "directory": "MATH SCHOOL-RECORD DIRECTORY",
        "card_id": "math-school-record",
        "card_number": "17",
        "card_small": "MATH SCHOOL RECORD",
        "representative_seed": "wawa-math-school-record-v1",
        "card_copy": "학교 시험 범위와 교과서 진도, 개념·계산·조건 해석·서술형 풀이의 오답 기록을 기준으로 수학 내신을 살펴봅니다.",
        "study_path": "수학-공부법",
        "study_name": "수학 공부법",
        "subjects": ("수학",),
        "topics": ("수학 내신 범위", "교과서·학교 진도", "수학 개념·계산", "조건 해석·서술형 풀이", "수학 내신 오답 재풀이"),
        "focus_terms": ("수학 내신 준비", "학교별 시험 범위·교과서 진도·개념·계산·조건 해석·서술형", "최근 수학 시험지·범위표·풀이·오답 기록"),
        "title_references": ("{local} 수학 내신 준비", "{local} 수학 시험 대비 상담", "이 수학 내신 과정", "해당 학교 수학 대비 방식", "수학 내신 범위·풀이 관리 안내", "지역별 수학 내신 기준"),
        "related_pages": (("수학학원", "수학학원"), ("수학전문학원", "수학 전문학원"), ("고등내신학원", "고등 내신학원"), ("중등내신학원", "중등 내신학원")),
        "base_page": ("수학학원", "수학학원"),
        "hero_copy": "최근 수학 시험지와 학교 범위표를 바탕으로 개념 이해, 계산 정확도, 조건 해석, 서술형 풀이와 오답 재풀이 순서를 살펴봅니다.",
        "hero_tags": (("학교 수학 범위", "교과서 진도", "오답 재풀이"), ("개념 이해", "계산 정확도", "조건 해석"), ("서술형 풀이", "최근 시험지", "주간 계획"), ("현재 단원", "남은 기간", "다음 점검")),
        "hub_lead": "수학 내신을 선행 진도나 문제 수로만 비교하지 않고 학교별 시험 범위와 교과서 진도, 개념·계산·조건 해석·서술형 풀이의 오답 기록을 함께 확인할 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "고등영어수학학원",
        "label": "고등 영어수학학원",
        "zip": "고등 영어수학학원.zip",
        "focus": "combined",
        "level": "고등",
        "grade_prefix": "고",
        "school_marker": "",
        "eyebrow": "HIGH SCHOOL ENGLISH & MATH PATHWAY GUIDE",
        "directory": "HIGH SCHOOL ENGLISH & MATH PATHWAY DIRECTORY",
        "card_id": "high-english-math-pathway",
        "card_number": "18",
        "card_small": "HIGH ENGLISH & MATH PATHWAY",
        "representative_seed": "wawa-high-english-math-pathway-v1",
        "expected_reviews": 1,
        "role": "고등 영어와 수학을 분리 진단해 과목별 보완 순서와 다음 단원을 연결하는 학습경로 안내",
        "card_copy": "고등 영어의 독해·문법·서술형과 수학의 개념·풀이·서술형을 따로 진단해 과목별 보완 순서를 정합니다.",
        "study_path": "고등학생-공부법",
        "study_name": "고등학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("고등 영어 세부영역 진단", "고등 수학 풀이단계 진단", "영어·수학 과목별 학습경로", "과목별 보완 우선순위", "진단 결과 기반 다음 단원 연결"),
        "focus_terms": ("고등 영어·수학 분리 진단", "영어 독해·문법·서술형과 수학 개념·풀이·서술형의 과목별 출발점", "과목별 진단 결과·보완 순서·다음 단원 연결 기록"),
        "title_references": ("{local} 고등 영어·수학 진단", "{local} 고등 과목별 학습경로", "이 고등 영어·수학 진단 과정", "해당 고등 과목별 출발점 안내", "고등 영어·수학 보완 순서", "지역별 고등 과목 진단 기준"),
        "section_roles": ("과목별 성취자료에서 출발점 찾기", "학교 자료를 영어·수학에 다르게 적용하기", "영어 세부영역과 수학 풀이단계 구분", "과목별 보완 우선순위 정하기", "다음 단원으로 연결할 증거 확인", "상담 전에 준비할 과목별 기록"),
        "related_pages": (("고등영수학원", "고등 영수 통합 수업 운영"), ("고등내신학원", "고등 학교시험 대비"), ("고등영어학원", "고등 영어 단과 안내"), ("고등수학학원", "고등 수학 단과 안내")),
        "base_page": ("고등영수학원", "고등 영수 통합 수업 운영"),
        "hero_copy": "최근 영어 답안과 수학 풀이를 서로 다른 기준으로 살펴보고, 과목별 출발점과 보완 순서가 다음 단원으로 어떻게 이어지는지 확인합니다.",
        "hero_tags": (("영어 세부영역", "수학 풀이단계", "보완 순서"), ("과목별 출발점", "진단 증거", "다음 단원"), ("영어 답안", "수학 풀이", "학습경로"), ("현재 기록", "우선순위", "다음 점검")),
        "hub_lead": "두 과목을 한 시간표에 묶는 방식보다 고등 영어의 독해·문법·서술형과 수학의 개념·풀이·서술형을 따로 진단하고, 과목별 출발점과 다음 단원을 연결하는 기준을 확인하도록 371개 지역 안내를 정리했습니다.",
        "hub_description": "371개 동네별 고등 영어수학학원 안내에서 영어 세부영역과 수학 풀이단계를 따로 진단하고, 과목별 보완 순서와 다음 단원 연결 기준을 확인합니다.",
    },
    {
        "slug": "중등영어수학학원",
        "label": "중등 영어수학학원",
        "zip": "중등 영어수학학원.zip",
        "focus": "combined",
        "level": "중등",
        "grade_prefix": "중",
        "school_marker": "",
        "eyebrow": "MIDDLE SCHOOL ENGLISH & MATH PATHWAY GUIDE",
        "directory": "MIDDLE SCHOOL ENGLISH & MATH PATHWAY DIRECTORY",
        "card_id": "middle-english-math-pathway",
        "card_number": "19",
        "card_small": "MIDDLE ENGLISH & MATH PATHWAY",
        "representative_seed": "wawa-middle-english-math-pathway-v1",
        "expected_reviews": 2,
        "role": "중등 영어 문법·독해와 수학 개념·유형의 누적 공백을 각각 찾아 과목별 출발점을 정하는 안내",
        "card_copy": "중등 영어 문법·독해와 수학 개념·유형의 누적 공백을 따로 확인해 과목별 시작 단원과 다음 진도를 정합니다.",
        "study_path": "중학생-공부법",
        "study_name": "중학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("중등 영어 문법·독해 진단", "중등 수학 개념·유형 진단", "두 과목 누적 공백 확인", "과목별 보완 단원", "다음 진도 연결 기준"),
        "focus_terms": ("중등 영어·수학 분리 진단", "영어 문법·독해와 수학 개념·유형의 과목별 누적 공백", "과목별 출발점·보완 단원·다음 진도 연결 기록"),
        "title_references": ("{local} 중등 영어·수학 진단", "{local} 중등 과목별 출발점", "이 중등 영어·수학 진단 과정", "해당 중등 누적 공백 안내", "중등 과목별 보완 단원", "지역별 중등 학습경로 기준"),
        "section_roles": ("학교 자료에서 과목별 출발점 찾기", "영어 문법·독해의 누적 공백 확인", "수학 개념·유형의 누적 공백 확인", "학생 기록으로 보완 단원 정하기", "영어와 수학의 다른 학습경로 설계", "가정에서 확인할 과목별 점검 기록", "다음 진도 전 상담 기준"),
        "related_pages": (("중등영수학원", "중등 영수 통합 수업 운영"), ("중등내신학원", "중등 지필·수행평가 대비"), ("영어학원", "영어 단과 안내"), ("수학학원", "수학 단과 안내")),
        "base_page": ("중등영수학원", "중등 영수 통합 수업 운영"),
        "hero_copy": "중등 영어의 문법·독해와 수학의 개념·유형에서 누적된 공백을 따로 찾아 과목별 시작 단원과 다음 진도를 구분합니다.",
        "hero_tags": (("문법·독해 공백", "개념·유형 공백", "출발 단원"), ("영어 진단", "수학 진단", "보완 단원"), ("학교 자료", "누적 공백", "다음 진도"), ("현재 기록", "학습경로", "다음 확인")),
        "hub_lead": "중등 영어와 수학을 같은 진도로 묶기보다 문법·독해와 개념·유형의 누적 공백을 각각 확인하고, 과목별 출발 단원과 다음 진도를 정할 수 있도록 371개 지역 안내를 정리했습니다.",
    },
    {
        "slug": "초등영어수학학원",
        "label": "초등 영어수학학원",
        "zip": "초등 영어수학학원.zip",
        "focus": "combined",
        "level": "초등",
        "grade_prefix": "초",
        "school_marker": "",
        "eyebrow": "ELEMENTARY ENGLISH & MATH PATHWAY GUIDE",
        "directory": "ELEMENTARY ENGLISH & MATH PATHWAY DIRECTORY",
        "card_id": "elementary-english-math-pathway",
        "card_number": "20",
        "card_small": "ELEMENTARY ENGLISH & MATH PATHWAY",
        "representative_seed": "wawa-elementary-english-math-pathway-v1",
        "expected_reviews": 3,
        "role": "초등 영어 읽기·어휘와 수학 개념·연산의 서로 다른 준비도를 확인해 기초 경로를 정하는 안내",
        "card_copy": "초등 영어 읽기·어휘와 수학 개념·연산의 준비도를 따로 확인해 설명·재현·짧은 반복의 다음 단계를 정합니다.",
        "study_path": "초등학생-공부법",
        "study_name": "초등학생 공부법",
        "subjects": ("영어", "수학"),
        "topics": ("초등 영어 읽기·어휘 준비도", "초등 수학 개념·연산 준비도", "영어·수학 기초 격차 확인", "과목별 설명하기", "짧은 반복과 다음 단계 연결"),
        "focus_terms": ("초등 영어·수학 기초 준비도 진단", "영어 읽기·어휘와 수학 개념·연산의 서로 다른 출발점", "과목별 설명·재현·짧은 반복 기록"),
        "title_references": ("{local} 초등 영어·수학 준비도", "{local} 초등 과목별 기초 경로", "이 초등 영어·수학 확인 과정", "해당 초등 기초 출발점 안내", "초등 과목별 다음 단계", "지역별 초등 준비도 기준"),
        "section_roles": ("영어 읽기·어휘 준비도 확인", "수학 개념·연산 준비도 확인", "서로 다른 기초 출발점 구분", "학생이 설명하고 다시 해보는 과정", "짧은 반복 뒤 다음 단계 연결", "상담 전에 준비할 초등 학습 기록"),
        "related_pages": (("초등영수학원", "초등 영수 통합 수업 운영"), ("초등전문학원", "초등 기초·습관 관리"), ("영어학원", "영어 단과 안내"), ("수학학원", "수학 단과 안내")),
        "base_page": ("초등영수학원", "초등 영수 통합 수업 운영"),
        "hero_copy": "초등 영어의 읽기·어휘와 수학의 개념·연산 준비도를 따로 확인하고, 설명·재현·짧은 반복이 다음 기초 단계로 이어지는지 살펴봅니다.",
        "hero_tags": (("읽기·어휘", "개념·연산", "기초 준비도"), ("영어 출발점", "수학 출발점", "다음 단계"), ("설명하기", "다시 해보기", "짧은 반복"), ("현재 교재", "과목별 준비도", "다음 확인")),
        "hub_lead": "초등 영어와 수학을 같은 문제량으로 묶기보다 읽기·어휘와 개념·연산의 서로 다른 준비도를 확인하고, 과목별 설명·재현·짧은 반복을 다음 기초 단계로 연결할 수 있도록 371개 지역 안내를 정리했습니다.",
    },
)


# These three pathway categories answer a different question from the older
# integrated English-math and school-record categories.  A 8 x 8 x 8 evidence
# cube gives every one of the 371 local pages a deterministic, reader-facing
# combination without inventing a school, score, address, or student result.
PATHWAY_EVIDENCE_BANKS = {
    "고등영어수학학원": {
        "english": ("독해 근거", "문법 적용", "서술형 표현", "어휘 누적", "긴 문장 해석", "답안 근거", "문장 구조", "교재 지문 이해"),
        "math": ("개념 설명", "조건 해석", "풀이 전개", "서술형 근거", "계산 검산", "오답 원인", "유형 적용", "재풀이 과정"),
        "record": ("최근 답안", "학생 설명", "첫 풀이", "다시 푼 기록", "질문 메모", "교재 표시", "진단 기록", "다음 단원 점검"),
    },
    "중등영어수학학원": {
        "english": ("문법 적용 공백", "독해 근거 찾기", "어휘 누적", "문장 구조 해석", "서술형 표현", "교과서 문장 이해", "답안 근거 설명", "긴 지문 읽기"),
        "math": ("개념 연결 공백", "유형 적용", "조건 해석", "계산 정확도", "풀이 순서", "서술형 전개", "이전 단원 연결", "오답 재도전"),
        "record": ("최근 학습지", "학생 설명", "단원별 오답", "처음 푼 흔적", "다시 푼 결과", "질문 기록", "현재 교재", "다음 진도 점검"),
    },
    "초등영어수학학원": {
        "english": ("소리 내어 읽기", "기초 어휘 재현", "짧은 문장 이해", "철자와 뜻 연결", "문장 따라 말하기", "읽은 내용 설명", "기초 문장 쓰기", "반복 읽기"),
        "math": ("수 개념 설명", "기초 연산 재현", "문제 뜻 이해", "계산 과정 말하기", "단위와 조건 찾기", "짧은 서술형", "연산 검산", "기초 유형 다시 풀기"),
        "record": ("현재 교재", "학생 설명", "혼자 해본 결과", "짧은 반복 기록", "질문한 내용", "다시 시도한 흔적", "가정 복습 기록", "다음 기초 단계 점검"),
    },
}

PATHWAY_ACTIONS = (
    "다음 단원 선택 기준으로 연결합니다",
    "과목별 보완 순서에 반영합니다",
    "첫 달 점검 항목으로 정리합니다",
    "서로 다른 출발 단원을 정하는 근거로 씁니다",
    "영어와 수학의 다음 진도를 따로 결정합니다",
    "학생이 혼자 다시 해볼 순서를 정합니다",
    "과목별 피드백 질문으로 구체화합니다",
    "다음 상담에서 재확인할 항목으로 남깁니다",
    "교재 단계보다 먼저 볼 판단 기준으로 삼습니다",
    "과목별 설명 방식과 반복 간격을 나눕니다",
    "현재 공백과 다음 학습을 잇는 기록으로 활용합니다",
    "수업 뒤 재확인할 과정을 과목별로 정합니다",
    "진단 뒤 가장 먼저 보완할 내용을 결정합니다",
    "학생의 설명과 실제 수행을 비교하는 기준으로 둡니다",
    "두 과목의 준비도 차이를 다음 계획에 반영합니다",
    "다음 단계로 넘어갈 시점을 판단하는 자료로 씁니다",
)

PATHWAY_HEADING_LENSES = (
    "최근 답안과 대조", "현재 교재에서 확인", "학생 설명으로 점검", "첫 풀이와 다시 풀이 비교",
    "질문 기록과 연결", "과목별 출발점 비교", "다음 단원 전 확인", "보완 순서에 반영",
    "혼자 해낸 범위 확인", "진단 근거와 대조", "오답 원인으로 구분", "재확인 기록 활용",
    "영어·수학을 따로 점검", "수업 전 자료 확인", "가정 복습 기록과 비교", "다음 상담 질문으로 정리",
    "교재 표시에서 찾기", "설명·재현 과정 확인", "누적 공백과 현재 단원 구분", "학습경로 선택에 활용",
    "과목별 피드백 확인", "다음 진도 기준 세우기", "첫 달 변화와 비교", "학년 자료에 맞춰 점검",
    "최근 질문에서 출발", "다시 시도한 결과 확인", "현재 준비도 나누기", "과목별 반복 간격 정하기",
    "학습 흔적으로 판단", "진단 뒤 행동으로 연결", "학생 언어로 다시 확인", "다음 단계 전 재점검",
)


def pathway_components(config: dict[str, object], rank: int, slot: int = 0) -> tuple[str, str, str]:
    bank = PATHWAY_EVIDENCE_BANKS.get(str(config["slug"]))
    if not bank:
        return "현재 답안", "현재 풀이", "최근 학습 기록"
    serial = (rank + slot * 53) % 512
    english = bank["english"][serial % 8]
    math = bank["math"][(serial // 8) % 8]
    record = bank["record"][(serial // 64) % 8]
    return english, math, record


def pathway_action(config: dict[str, object], rank: int, slot: int = 0) -> str:
    code = shared.stable_number(str(config["slug"]), rank, slot, "pathway-action")
    return PATHWAY_ACTIONS[code % len(PATHWAY_ACTIONS)]


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


def split_school_values(value: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"[,，.;；/|]+", value or "")
        if item.strip()
    ]


SCHOOL_FIELDS = {
    "초": "타깃학교\n(초)",
    "중": "타깃학교\n(중)",
    "고": "타깃학교\n(고)",
}

SCHOOL_SCOPE_VALUES = {
    "지역내 모든 고등학교 가능",
    "지역 내 모든 고등학교 가능",
}


def schools_for_level(row: dict[str, str], prefix: str) -> list[str]:
    return unique_values(
        [
            school
            for school in split_school_values(row.get(SCHOOL_FIELDS.get(prefix, ""), ""))
            if school not in SCHOOL_SCOPE_VALUES
        ]
    )


def all_row_schools(row: dict[str, str]) -> list[str]:
    return unique_values(
        [school for field in SCHOOL_FIELDS.values() for school in split_school_values(row.get(field, ""))]
    )


def representative_mapping(order: list[str], config: dict[str, object]) -> dict[str, str]:
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
    seed = str(config.get("representative_seed") or f'wawa-{config["slug"]}-{TODAY}')
    random.Random(seed).shuffle(candidates)
    return {
        local: "/" + path.relative_to(ROOT).as_posix()
        for local, (_, path) in zip(order, candidates)
    }


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
    # Do not rewrite the syllables inside school names such as 상원고 or
    # 중원고.  Only production-language uses where 원고 is a standalone noun
    # are converted to reader-facing wording.
    text = re.sub(r"(?<![가-힣])원고처럼", "일반적인 안내처럼", text)
    text = re.sub(r"(?<![가-힣])원고라면", "안내라면", text)
    text = re.sub(r"(?<![가-힣])원고입니다", "안내입니다", text)
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
    text = text.replace("제공된 학교 정보", "확인된 학교 정보")
    text = text.replace("제공된 학교명", "확인된 학교명")
    text = text.replace("실제 제공된", "실제 확인된")
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
    text = text.replace("시험시간관리", "시험 시간 관리")
    text = text.replace("성적관리", "학습 성과 점검")
    text = text.replace("수업을 정보성으로 살펴보면", "수업 과정을 살펴보면")
    text = text.replace("상담 오답 관리", "상담에서 오답 관리")
    text = text.replace("원인 분류가 먼저 확인할 필요가 있습니다", "오답 원인부터 분류할 필요가 있습니다")
    text = text.replace("를 점검하는 과정이 ", "를 점검하면 ")
    text = re.sub(
        r"수업 가능 학교 정보는 “([^”]+)”로 한정해 쓰는 것이 좋습니다\.",
        r"확인된 수업 가능 학교는 “\1”이며, 자녀 학교 자료의 실제 적용 범위는 상담에서 확인하는 것이 좋습니다.",
        text,
    )
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

    grade_token = r"(?:초등학교|초등|초|중학교|중등|중|고등학교|고등|고)\s*[1-6]\s*(?:학년)?"

    def dedupe_sequence(match: re.Match[str]) -> str:
        values: list[tuple[str, str]] = []
        seen: set[str] = set()
        for token in GRADE_PATTERN.finditer(match.group(0)):
            code = canonical_grade(token.group("level"), token.group("number"))
            if code not in seen:
                seen.add(code)
                values.append((code, token.group(0)))
        return "·".join(display_grade(code, original) for code, original in values)

    text = re.sub(rf"{grade_token}(?:\s*[·,/]\s*{grade_token})+", dedupe_sequence, text)
    text = re.sub(
        r"(?<![가-힣])([초중고][1-6])(?:\s*[·,/]?\s*\1)+(?![가-힣])",
        r"\1",
        text,
    )
    text = text.replace("해당 학년 학년", "해당 학년")
    text = re.sub(r"해당 학년(?:\s*[·,]\s*해당 학년)+", "해당 학년", text)
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


def sanitize_school_claims(
    value: str,
    local: str,
    allowed_schools: list[str],
    config: dict[str, object],
) -> str:
    """Remove school names outside the requested grade level without inventing replacements."""
    prefix = str(config.get("grade_prefix", ""))
    if not prefix:
        return value
    row = CENTER_ROWS.get(local, {})
    all_schools = all_row_schools(row)
    allowed = set(allowed_schools)
    blocked = [school for school in all_schools if school not in allowed]
    if not blocked:
        return value

    generic_frames = (
        f"확인된 {config['level']} 학교 정보가 없는 경우에는 자녀 학교의 최근 시험 범위표와 학습 자료를 상담에 준비해야 합니다.",
        f"{local} {config['label']} 상담에서는 자녀 학교의 실제 시험 범위와 교재를 가져와 학교 자료 활용 범위를 확인하는 편이 좋습니다.",
        f"이 지역의 {config['level']} 학교 정보가 따로 확인되지 않았다면 학교명을 추정하지 말고 자녀가 받은 최근 자료를 기준으로 상담해야 합니다.",
        f"수업 가능 {config['level']} 학교는 상담에서 자녀 학교 자료와 함께 확인하고, 확인되지 않은 학교명은 적용 범위로 단정하지 않습니다.",
    )
    sentence_pattern = re.compile(r"[^.!?]+(?:[.!?]|$)")

    suffixes = (
        "입니다", "에서는", "에서", "으로는", "으로", "이라는", "이라고", "이라면",
        "라는", "이며", "이고", "에는", "부터", "까지", "보다", "처럼",
        "은", "는", "이", "가", "을", "를", "과", "와", "의", "도", "만", "에", "등",
    )
    suffix_pattern = "|".join(re.escape(item) for item in sorted(suffixes, key=len, reverse=True))

    def school_pattern(school: str) -> str:
        return (
            rf"(?<![가-힣A-Za-z0-9]){re.escape(school)}"
            rf"(?=$|[^가-힣A-Za-z0-9]|(?:{suffix_pattern})(?:$|[^가-힣A-Za-z0-9]))"
        )

    def removable_school_pattern(school: str) -> str:
        return (
            rf"(?<![가-힣A-Za-z0-9]){re.escape(school)}"
            rf"(?:(?:{suffix_pattern})(?=$|[^가-힣A-Za-z0-9])|(?=$|[^가-힣A-Za-z0-9]))"
        )

    def clean_sentence(match: re.Match[str]) -> str:
        sentence = match.group(0)
        hits = [school for school in blocked if school and re.search(school_pattern(school), sentence)]
        if not hits:
            return sentence
        if not any(re.search(school_pattern(school), sentence) for school in allowed):
            code = shared.stable_number(str(config["slug"]), local, "school-filter", sentence)
            leading_match = re.match(r"^\s*", sentence)
            leading = leading_match.group(0) if leading_match else ""
            return leading + generic_frames[code % len(generic_frames)]
        cleaned = sentence
        for school in sorted(hits, key=len, reverse=True):
            cleaned = re.sub(removable_school_pattern(school), "", cleaned)
        cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned)
        cleaned = re.sub(r"([:：]|에는)\s*,", r"\1 ", cleaned)
        cleaned = re.sub(r",\s*(?=[.!?]|$)", "", cleaned)
        cleaned = re.sub(r"\s+,", ",", cleaned)
        cleaned = re.sub(r"\s+([.!?])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned

    return sentence_pattern.sub(clean_sentence, value)


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
    text = sanitize_school_claims(text, local, schools, config)
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
        "교재을": "교재를",
        "영어 수학를": "영어와 수학을",
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
        "학원로": "학원으로",
        "수행평가 준비을": "수행평가 준비를",
        "수행평가 준비과": "수행평가 준비와",
        "수행평가 준비으로": "수행평가 준비로",
        "고등 내신 준비은": "고등 내신 준비는",
        "중등 내신 준비은": "중등 내신 준비는",
        "영어 내신 준비을": "영어 내신 준비를",
        "영어 내신 준비은": "영어 내신 준비는",
        "수학 내신 준비을": "수학 내신 준비를",
        "수학 내신 준비은": "수학 내신 준비는",
        "준비을": "준비를",
        "준비은": "준비는",
        "날짜을": "날짜를",
        "학년학생": "학년 학생",
        "기준 기준으로": "기준으로",
        "확인이 확인할 필요가 있습니다": "확인할 필요가 있습니다",
        "예시을": "예시를",
        "학습성과표을": "학습성과표를",
        "수학과 영어가라는": "수학과 영어라는",
        "처음 첫 상담": "첫 상담",
        "안내 안내": "안내",
        "관리 안내은": "관리 안내는",
        "안내은": "안내는",
        "안내을": "안내를",
        "기준을 기준으로": "기준으로",
        "적용해야 합니다면": "적용해야 한다면",
        "필요합니다면": "필요하다면",
        "평가 대비가라는": "평가 대비라는",
        "시기가라면": "시기라면",
        "제공 값": "확인된 정보",
        "검색에 노출될 수 있지만": "지역 안내에서 확인할 수 있지만",
        "검색에 노출되지만": "지역 안내에서 확인되지만",
        "시간이 먼저 확인할 필요가 있습니다": "시간을 먼저 마련해야 합니다",
        "진단 진단": "진단",
        "분리 진단 학습을 진단할 때": "분리 진단에서",
        "준비도 진단 학습을 진단할 때": "준비도 진단에서",
        "초등 학생의 학생이": "초등 과정에서 학생이",
        "중등 학생의 학생이": "중등 과정에서 학생이",
        "고등 학생의 학생이": "고등 과정에서 학생이",
        "수학·영어가라도": "수학·영어라도",
        "영어·수학가라도": "영어·수학이라도",
        "보완 순서이": "보완 순서가",
        " 이며": "이며",
        "먼저 먼저": "먼저",
        "상담에서 상담에서": "상담에서",
        "방향가": "방향이",
        "··": "·",
    }
    for old, new in grammar.items():
        text = text.replace(old, new)
    text = text.replace("두 과목 과목", "두 과목")
    text = re.sub(
        r"(?<![가-힣])학원\s+(?=(?:오답 점검|영어 답안 점검|수학 풀이 기록|과제 피드백|주간 시간 배분))",
        "",
        text,
    )
    if config["focus"] == "math":
        text = text.replace("두 과목의 학습 흐름", "수학 풀이와 복습 흐름")
        text = text.replace("영어·수학 복습 간격", "수학 오답 재확인 간격")
        text = text.replace("과목별 취약", "수학 영역별 취약")
    elif config["focus"] == "english":
        text = text.replace("두 과목의 학습 흐름", "영어 학습과 복습 흐름")
        text = text.replace("영어·수학 복습 간격", "영어 어휘·독해 복습 간격")
        text = text.replace("과목별 취약", "영어 영역별 취약")
    text = re.sub(r"^\s*[·,]\s*", "", text)
    text = collapse_repeated_terms(text)
    text = re.sub(
        r"(초등|중등|고등)\s*([1-6])학년\s*[~～-]\s*\2학년",
        r"\1 \2학년",
        text,
    )
    text = re.sub(r"(초|중|고)([1-6])\s*[~～-]\s*\1\2", r"\1\2", text)
    text = re.sub(r"(?<=[초중고][1-6])(?=[가-힣])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = reader_facing_text(text, local, config).strip()
    for old, new in grammar.items():
        text = text.replace(old, new)
    text = collapse_repeated_terms(text)
    text = re.sub(r"(?<=[초중고][1-6])(?=[가-힣])", " ", text)
    text = re.sub(r"((?:초[1-6]|중[1-3]|고[1-3])(?:·(?:초[1-6]|중[1-3]|고[1-3]))*)\s+이(?=\s|[가-힣])", r"\1이", text)
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
        if re.match(r"^[^,.!?]{5,90}(?:하면|보면|살펴볼 때|포함하면|세울 때),", varied):
            result.append(varied)
            continue
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
        suffixes = (
            " 상담 전 최근 답안과 복습 계획도 함께 확인하세요.",
            " 학교 자료와 과목별 학습 순서를 함께 살펴보세요.",
            " 최근 교재와 오답 기록을 상담 전에 준비해 보세요.",
            " 현재 학습 기록과 다음 점검 순서도 함께 확인하세요.",
        )
        start = shared.stable_number(str(config["slug"]), title, "meta-suffix") % len(suffixes)
        base = text.rstrip(".") + "."
        for offset in range(len(suffixes)):
            candidate = base + suffixes[(start + offset) % len(suffixes)]
            if len(candidate) <= 110:
                text = candidate
                break
    if len(text) < 70:
        text += " 학교 자료와 복습 가능 시간도 함께 점검합니다."
    if len(text) > 110:
        window = text[:110]
        endings = [window.rfind(mark) for mark in ".!?" ]
        sentence_end = max(endings)
        if sentence_end >= 69:
            text = window[: sentence_end + 1].strip()
        else:
            cropped = text[:107].rsplit(" ", 1)[0].rstrip(" ,·.")
            text = (cropped or text[:107].rstrip(" ,·.")) + "."
    return text


def concise_summary(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= 320:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*selected, sentence]).strip()
        if len(candidate) > 320:
            break
        selected.append(sentence)
    compact = " ".join(selected).strip()
    if len(compact) >= 160:
        return compact
    cropped = text[:317].rsplit(" ", 1)[0].rstrip(" ,·")
    return cropped + "."


def focus_terms(config: dict[str, object]) -> tuple[str, str, str]:
    configured = config.get("focus_terms")
    if configured:
        return tuple(str(value) for value in configured)  # type: ignore[return-value]
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
    configured = config.get("title_references")
    if configured:
        return tuple(str(value).format(local=local) for value in configured)
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
    text = (
        text.replace("관리을", "관리를")
        .replace("관리이", "관리가")
        .replace("안내을", "안내를")
        .replace("안내은", "안내는")
        .replace("고등 내신 준비은", "고등 내신 준비는")
        .replace("중등 내신 준비은", "중등 내신 준비는")
        .replace("기준을 기준으로", "기준으로")
    )
    text = re.sub(r"상담\s+상담(?=(?:자는|자에게|자가|자는지|에서|으로|은|는|이|가|을|를|과|와|의|에|도|만|부터|까지))", "상담", text)
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
    if str(config["slug"]) in PATHWAY_EVIDENCE_BANKS:
        english, math, record = pathway_components(config, rank)
        action = pathway_action(config, rank)
        answer_sentence = (
            f"{title} 상담은 영어 ‘{english}’, 수학 ‘{math}’, ‘{record}’ 세 기준을 "
            f"따로 확인해 과목별 출발점을 찾고, 진단 결과를 바탕으로 {action}."
        )
    else:
        answer_sentence = answer_frames[code % len(answer_frames)]
    if center.get("verified_grades"):
        grade_frames = (
            f"센터 등록 자료에서 확인된 {config['label']} 수업 가능 학년은 {grade_text}입니다.",
            f"제공된 센터 자료에는 {grade_text}이 {config['label']} 상담 가능 학년으로 확인됩니다.",
            f"{config['label']} 수업 범위는 확인 자료상 {grade_text}이며, 세부 진도는 현재 교재를 보고 정합니다.",
            f"상담 가능한 학년으로 확인된 범위는 {grade_text}입니다. 학년 안에서도 이전 단원 공백은 따로 살펴봅니다.",
            f"등록 자료 기준 {grade_text} 학생이 {config['label']} 상담 대상에 포함됩니다.",
            f"현재 확인 가능한 {config['label']} 학년 범위는 {grade_text}입니다. 실제 시작점은 최근 답안으로 나눕니다.",
            f"센터 정보에서 {grade_text} 수업 가능 여부가 확인되며, 학기 일정과 교재 단계는 상담에서 맞춥니다.",
            f"{grade_text}이 확인된 수업 가능 학년입니다. 같은 학년이라도 과목별 준비 순서는 달라질 수 있습니다.",
        )
    else:
        grade_frames = (
            f"이 센터의 {config['label']} 수업 가능 학년은 상담에서 먼저 확인해야 합니다.",
            f"등록 자료에 구체적인 {config['label']} 학년 범위가 없어 자녀 학년의 수업 가능 여부를 우선 확인해야 합니다.",
            f"{config['label']} 상담 전에는 현재 학년이 수업 범위에 포함되는지 먼저 문의하는 편이 안전합니다.",
            f"확인 자료만으로 학년 범위를 단정하기 어려워 상담에서 자녀 학년과 교재 단계를 함께 확인합니다.",
        )
    fact_sentence = grade_frames[(code // 5) % len(grade_frames)]
    if school_text:
        school_frames = (
            f"확인된 학교 정보에는 {school_text} 등이 있으며, 실제 시험 범위와 자료 활용 방식은 자녀 학교를 기준으로 상담에서 맞춥니다.",
            f"센터 자료에 나온 학교는 {school_text} 등입니다. 학교별 적용 여부는 최근 범위표와 교재를 가져와 다시 확인합니다.",
            f"수업 가능 학교 참고 자료에는 {school_text} 등이 포함되지만, 실제 내신 준비는 자녀 학교의 현재 자료를 기준으로 정합니다.",
            f"{school_text} 등의 학교 정보가 확인됩니다. 학교명만으로 수업을 단정하지 않고 시험 범위와 답안을 함께 살펴봅니다.",
            f"학교 참고 범위로 {school_text} 등이 확인되며, 학기별 범위 변화는 상담 시 최신 자료로 대조합니다.",
            f"제공 자료에서는 {school_text} 등을 확인할 수 있습니다. 자녀 학교의 프린트와 시험 계획표도 함께 준비하세요.",
            f"{school_text} 등이 수업 가능 학교 정보에 들어 있습니다. 실제 적용 범위는 학생이 받은 학교 자료로 다시 맞춥니다.",
            f"확인된 학교 예시는 {school_text} 등이며, 과목별 내신 일정은 최근 공지와 교재를 기준으로 상담합니다.",
        )
    else:
        school_frames = (
            "수업 가능 학교 정보가 따로 확인되지 않은 경우에는 자녀 학교의 최근 시험 범위표와 학습 자료를 준비해 적용 범위를 상담에서 확인해야 합니다.",
            "제공 자료에 학교명이 없으므로 자녀 학교의 교재와 범위표를 가져와 실제 적용 가능 여부를 먼저 확인합니다.",
            "학교 참고 정보가 확인되지 않을 때는 학교명을 추정하지 않고 학생이 받은 최신 자료로 상담 범위를 정합니다.",
            "등록된 학교 정보가 없는 경우에는 최근 학교 공지와 교재를 준비해 내신 자료 활용 여부부터 문의하세요.",
        )
    school_sentence = school_frames[(code // 11) % len(school_frames)]
    preparation_frames = (
        f"{fact_sentence} {school_sentence}",
        f"{school_sentence} {fact_sentence}",
        f"상담에는 최근 시험지·교재·일주일 학습표를 준비하는 것이 좋습니다. {fact_sentence} {school_sentence}",
        f"{fact_sentence} 현재 학습 상태를 정확히 나누기 위해 최근 교재와 오답 기록을 함께 준비하세요. {school_sentence}",
    )
    return [answer_sentence, preparation_frames[(code // 7) % len(preparation_frames)]]


def build_summary(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> str:
    title = f"{local} {config['label']}"
    subject, diagnostic, evidence = focus_terms(config)
    location = " ".join(unique_values([str(center.get("region", "")), str(center.get("city", "")), local]))
    grades = [str(item) for item in center.get("verified_grades", [])]
    schools = verified_school_text(center, 2)
    grade_clause = f"확인된 수업 가능 학년은 {'·'.join(grades)}이며" if grades else "수업 가능 학년은 상담 확인이 필요하며"
    school_clause = f"수업 가능 학교 정보에는 {schools} 등이 포함됩니다" if schools else "자녀 학교의 시험 자료를 준비해 수업 적용 범위를 확인해야 합니다"
    if str(config["slug"]) in PATHWAY_EVIDENCE_BANKS:
        english, math, record = pathway_components(config, rank, 1)
        action = pathway_action(config, rank, 1)
        role = str(config.get("role", "영어와 수학의 출발점을 따로 확인하는 학습경로 안내"))
        summary = (
            f"{title}은 {location}에서 {role}입니다. 영어 확인 항목은 ‘{english}’, 수학 확인 항목은 ‘{math}’이며, "
            f"{grade_clause} {school_clause}. ‘{record}’에서 확인한 내용을 근거로 {action}."
        )
        return concise_summary(summary)
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
    evidence_left = evidence_bank[rank % len(evidence_bank)]
    evidence_right = evidence_bank[(rank // len(evidence_bank)) % len(evidence_bank)]
    evidence_text = evidence_left if evidence_left == evidence_right else f"{evidence_left}, {evidence_right}"
    action = action_bank[(rank // (len(evidence_bank) * len(evidence_bank))) % len(action_bank)]
    detail = f"추가 확인 자료: {evidence_text}. 이 기록으로 {action}."
    base = frames[rank % len(frames)]
    summary = f"{base} {detail}"
    if len(summary) <= 320:
        return summary
    # Do not drop the per-page evidence pair when a long school/grade clause
    # pushes the original summary over the limit.  The evidence pair and
    # action form a stable 371-way sequence and keep summaries meaningfully
    # distinct even after the local name is normalized for similarity tests.
    compact = (
        f"{title}은 {location}에서 {subject} 수업의 현재 상태와 내신 준비 흐름을 "
        f"확인하는 안내입니다. 학년·학교별 적용 범위는 등록 자료와 자녀의 실제 "
        f"학교 자료를 함께 확인합니다. {detail}"
    )
    if len(compact) <= 320:
        return compact
    cropped = compact[:317].rsplit(" ", 1)[0].rstrip(" ,·")
    return cropped + "."


def build_meta(local: str, center: dict[str, object], config: dict[str, object], rank: int) -> str:
    title = f"{local} {config['label']}"
    subject, diagnostic, evidence = focus_terms(config)
    if str(config["slug"]) in PATHWAY_EVIDENCE_BANKS:
        english, math, record = pathway_components(config, rank, 2)
        if str(config["slug"]) == "고등영어수학학원":
            frame = (
                f"{title}의 진단 항목은 영어 ‘{english}’, 수학 ‘{math}’, 확인 기록 ‘{record}’입니다. "
                "이 세 기준으로 과목별 출발점과 다음 단원 연결 순서를 안내합니다."
            )
        elif str(config["slug"]) == "중등영어수학학원":
            frame = (
                f"{title}의 점검 항목은 영어 ‘{english}’, 수학 ‘{math}’, 확인 기록 ‘{record}’입니다. "
                "누적 공백을 나누어 과목별 출발 단원과 다음 진도를 안내합니다."
            )
        else:
            frame = (
                f"{title}의 준비도 항목은 영어 ‘{english}’, 수학 ‘{math}’, 확인 기록 ‘{record}’입니다. "
                "설명·재현·짧은 반복을 다음 기초 단계로 연결하는 기준을 안내합니다."
            )
        return concise_meta(frame, title, config)
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
    if str(config["slug"]) in PATHWAY_EVIDENCE_BANKS:
        english, math, record = pathway_components(config, rank, 3)
        action = pathway_action(config, rank, 3)
        heading = f"{local} {config['level']} 진단 · 영어 {english} / 수학 {math}"
        text = (
            f"‘{record}’에서 영어 항목 ‘{english}’, 수학 항목 ‘{math}’의 현재 단계를 각각 확인하고, "
            f"이 차이를 바탕으로 {action}."
        )
        tags = list(config["hero_tags"][rank % len(config["hero_tags"])])
        return heading, text, tags
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
    grade_text = "·".join(grades)
    school_text = "·".join(schools[:3])
    if grades:
        grade_answers = (
            f"확인 자료에 나온 수업 가능 학년은 {grade_text}입니다. 최근 교재와 시험 범위를 함께 보면 학년 범위 안에서 시작 단원을 구체적으로 정할 수 있습니다.",
            f"센터 등록 정보에서는 {grade_text} 수업이 가능합니다. 같은 학년이라도 이전 단원 공백과 과목별 진도가 달라 현재 자료를 먼저 확인합니다.",
            f"상담 대상 학년으로 확인된 범위는 {grade_text}입니다. 학년만 맞추지 않고 학생이 혼자 해결할 수 있는 단원까지 함께 살펴봅니다.",
            f"수업 가능 여부가 확인된 학년은 {grade_text}입니다. 학교 일정과 현재 교재를 준비하면 실제 적용할 학습 순서를 정하기 쉽습니다.",
            f"등록 자료 기준으로 {grade_text} 학생이 상담할 수 있습니다. 세부 수업 범위는 최근 답안과 과제 기록을 보고 조정합니다.",
            f"{grade_text}이 확인된 수업 가능 학년입니다. 진도보다 누적된 빈틈과 가정에서 가능한 복습 시간을 먼저 나눕니다.",
            f"현재 센터 자료에서 확인되는 학년 범위는 {grade_text}입니다. 자녀의 학기 일정과 교재 단계를 대조해 시작점을 정합니다.",
            f"{grade_text} 수업 가능 정보가 확인됩니다. 상담에서는 학년 범위와 별도로 최근 시험지에서 반복된 어려움을 살펴봅니다.",
        )
    else:
        grade_answers = (
            "구체적인 수업 가능 학년이 등록 자료에 없어 자녀 학년의 가능 여부를 상담에서 먼저 확인해야 합니다. 확인되지 않은 학년을 미리 단정하지 않습니다.",
            "제공 정보만으로 학년 범위를 정하기 어려우므로 현재 학년과 교재 단계를 알려 주고 수업 가능 여부부터 문의하세요.",
            "학년 정보가 확인되지 않은 센터는 자녀 학년의 수업 가능 범위와 시작 단원을 첫 상담에서 함께 확인해야 합니다.",
            "등록된 학년 범위가 없을 때는 임의로 적용하지 않고 최근 교재와 학교 일정을 준비해 상담 가능 여부를 확인합니다.",
        )
    if schools:
        school_answers = (
            f"확인된 수업 가능 학교 정보에는 {school_text} 등이 있습니다. 실제 내신 범위는 자녀 학교의 최신 범위표와 교재로 다시 확인합니다.",
            f"센터 자료에서 {school_text} 등을 학교 참고 범위로 확인할 수 있습니다. 학교별 프린트와 평가 일정은 상담 시 최신 자료로 대조합니다.",
            f"수업 가능 학교 예시로 {school_text} 등이 확인됩니다. 학교명만 보고 판단하지 않고 학생이 받은 시험 계획표와 답안을 함께 봅니다.",
            f"제공된 학교 정보는 {school_text} 등입니다. 실제 적용 여부는 자녀 학교의 현재 교과서·프린트·시험 범위를 기준으로 확인합니다.",
            f"{school_text} 등이 확인된 학교 자료에 포함됩니다. 학기마다 범위가 달라질 수 있어 최근 공지와 교재를 상담에 준비하는 편이 좋습니다.",
            f"학교 참고 정보에는 {school_text} 등이 있습니다. 자녀 학교의 내신 자료를 어떻게 수업 계획에 반영하는지 상담에서 질문하세요.",
            f"등록 자료상 {school_text} 등을 확인할 수 있습니다. 실제 수업 범위는 학생이 가져온 학교 자료와 현재 진도를 놓고 정합니다.",
            f"{school_text} 등이 수업 가능 학교 정보로 확인됩니다. 학교별 평가 방식은 최신 범위표와 최근 답안으로 다시 살펴봅니다.",
        )
    else:
        school_answers = (
            "확인된 수업 가능 학교 정보가 없어 자녀 학교의 최근 범위표와 교재를 준비해 적용 범위를 먼저 확인해야 합니다. 학교명을 임의로 추정하지 않습니다.",
            "등록 자료에 학교명이 없는 경우에는 학생이 받은 교과서·프린트·시험 계획표를 가져와 학교 자료 활용 여부를 확인합니다.",
            "학교 참고 정보가 확인되지 않으므로 자녀 학교명을 알려 주고 최근 내신 자료를 바탕으로 수업 가능 범위를 상담해야 합니다.",
            "제공된 학교 목록이 없을 때는 특정 학교를 적용 대상으로 단정하지 않고 최신 학교 자료로 가능 여부를 확인합니다.",
        )
    question_banks = (
        (
            "{subject} 상담 전에 어떤 자료를 준비하면 좋나요?",
            "{subject} 상담에서 최근 시험지는 어떻게 활용하나요?",
            "{subject}의 첫 진단에 필요한 학습 기록은 무엇인가요?",
            "{subject} 상담을 구체적으로 받으려면 무엇을 가져가야 하나요?",
            "{subject}의 현재 상태를 보여 줄 자료는 어떤 것인가요?",
            "{subject} 상담 전 교재와 오답 기록을 준비해야 하나요?",
            "{subject} 수업 문의 때 일주일 학습표도 필요한가요?",
            "{subject}의 시작점을 확인할 때 어떤 자료부터 보나요?",
        ),
        (
            "{subject}에서 학생의 현재 수준은 어떤 기준으로 진단하나요?",
            "{subject}의 학습 공백은 어떻게 구분하나요?",
            "{subject} 상담에서 정답 수 외에 무엇을 확인하나요?",
            "{subject}의 막힌 단원을 찾는 과정은 어떻게 진행되나요?",
            "{subject}에서 개념 부족과 실수는 어떻게 나누어 보나요?",
            "{subject} 수업 전 학생의 설명 과정도 확인하나요?",
            "{subject}의 현재 진도와 누적 빈틈은 어떻게 구분하나요?",
            "{subject} 상담에서 오답을 다시 풀어 보게 하나요?",
        ),
        (
            "{subject}의 수업 가능 학교와 내신 자료는 어떻게 확인하나요?",
            "{subject}에서 학교별 시험 범위는 어떻게 반영하나요?",
            "{subject} 상담 전 자녀 학교 자료를 준비해야 하나요?",
            "{subject}의 학교 프린트 활용 여부는 어디서 확인하나요?",
            "{subject}에서 수업 가능한 학교 정보는 어떤 기준인가요?",
            "{subject} 상담에서는 학교별 자료를 어떻게 대조하나요?",
            "{subject}의 내신 준비에 최근 범위표가 필요한가요?",
            "{subject}에서 학교 정보는 상담 중 어떻게 확인하나요?",
        ),
        (
            "{subject}은 어떤 학년이 상담할 수 있나요?",
            "{subject}의 수업 가능 학년은 어디서 확인하나요?",
            "{subject} 상담은 현재 학년부터 확인하나요?",
            "{subject}에서 학년별 시작점은 어떻게 정하나요?",
            "{subject}의 학년 범위와 교재 단계는 함께 보나요?",
            "{subject}은 학년이 같아도 진단 내용이 달라지나요?",
            "{subject} 상담 전에 수업 가능 학년을 문의해야 하나요?",
            "{subject}에서 확인된 학년 범위는 어떻게 적용하나요?",
        ),
        (
            "{subject}을 비교할 때 점수보다 먼저 볼 기준은 무엇인가요?",
            "{subject} 선택에서 수업 횟수보다 중요한 것은 무엇인가요?",
            "{subject}의 관리 방식을 비교할 때 무엇을 질문해야 하나요?",
            "{subject}에서 과제량보다 먼저 확인할 과정은 무엇인가요?",
            "{subject} 상담 후 어떤 기록이 남아야 하나요?",
            "{subject}을 고를 때 오답 재확인도 비교해야 하나요?",
            "{subject}의 피드백이 다음 계획으로 이어지는지 어떻게 보나요?",
            "{subject} 선택 전 학생이 혼자 다시 푸는 과정도 확인하나요?",
        ),
    )
    preparation_answers = (
        f"최근 시험지와 현재 교재, 틀린 답안·풀이, 일주일 학습표를 함께 준비하세요. 이 자료로 {diagnostic}과 {evidence}을 나누면 우선 보완할 내용을 정하기 쉽습니다.",
        f"최근 학교 자료와 교재 진도, 오답 흔적, 실제 공부 시간을 가져가면 좋습니다. {diagnostic}을 확인한 뒤 {evidence}이 다음 계획으로 이어지는지 상담할 수 있습니다.",
        f"현재 풀고 있는 교재와 최근 평가 자료, 스스로 다시 푼 기록을 준비하세요. 정답률보다 {diagnostic}의 차이를 구체적으로 설명하는 데 도움이 됩니다.",
        f"시험 범위표·답안·풀이 과정·주간 시간표를 한꺼번에 보면 좋습니다. 수업 전 상태를 확인하고 {evidence}을 연결해 현실적인 복습량을 정할 수 있습니다.",
        f"최근 틀린 문제와 교재의 표시, 학교 일정, 가정 복습 기록을 챙기세요. 이 자료는 {diagnostic} 중 우선 확인할 지점을 나누는 근거가 됩니다.",
        f"교재 이름만 알려 주기보다 실제로 푼 페이지와 오답, 일주일 실행 기록을 준비하세요. {evidence}이 남는 수업인지 비교하기 쉬워집니다.",
        f"학교 시험지나 단원 평가, 현재 교재, 질문 메모를 가져가면 상담이 구체적입니다. {diagnostic}을 학생의 설명과 함께 살펴볼 수 있습니다.",
        f"최근 답안·풀이와 과제 완료 기록, 시험까지 남은 기간을 정리해 오세요. 이를 통해 {evidence}을 어느 간격으로 확인할지 정할 수 있습니다.",
    )
    diagnosis_answers = (
        f"정답 수만 세지 않고 {diagnostic} 중 어디에서 멈추는지 봅니다. 설명 과정과 일정 뒤 다시 푼 결과를 함께 확인해 필요한 복습 방식을 정합니다.",
        f"최근 답안에서 반복된 어려움을 {diagnostic}으로 나누어 살펴봅니다. 학생이 도움 없이 다시 설명하고 해결하는지도 중요한 진단 기준입니다.",
        f"교재 진도보다 실제 풀이·답안에서 {diagnostic}이 어떻게 나타나는지 먼저 확인합니다. 같은 유형의 재도전 결과까지 봐야 공백을 구분할 수 있습니다.",
        f"틀린 문제를 바로 고치게 하기보다 학생이 막힌 이유를 말하게 합니다. 이후 {diagnostic}과 {evidence}을 대조해 시작 단원을 정합니다.",
        f"최근 시험지와 과제에서 실수, 개념 공백, 시간 부족을 분리합니다. {diagnostic}을 확인한 뒤 학생이 혼자 할 수 있는 범위를 함께 표시합니다.",
        f"현재 교재의 첫 풀이와 다시 푼 결과를 비교합니다. {diagnostic} 중 반복되는 지점을 찾으면 과제와 피드백 순서를 구체화할 수 있습니다.",
        f"점수 한 줄보다 답을 고른 근거와 풀이 흐름을 확인합니다. {evidence}이 실제로 남아 있는지 보면 이해와 일시적 암기를 나누기 쉽습니다.",
        f"학교 범위와 누적 단원을 따로 놓고 {diagnostic}을 점검합니다. 학생의 설명과 오답 재확인 결과를 함께 보아 다음 학습 순서를 정합니다.",
    )
    comparison_answers = (
        "점수 상승을 단정하기보다 진단 결과가 수업 계획, 과제 피드백, 오답 재확인 날짜로 이어지는지 확인하세요. 학생이 혼자 다시 해낸 기록도 비교 기준입니다.",
        "문제 수보다 틀린 원인이 기록되고 다음 수업에서 다시 확인되는지 살펴보세요. 피드백이 학생의 다음 행동으로 연결되어야 합니다.",
        "선행 범위만 비교하지 말고 현재 공백을 어떻게 설명하며 주간 계획을 어떻게 조정하는지 질문하세요. 재풀이 결과가 남는지도 중요합니다.",
        "수업 횟수보다 진단·실행·재확인의 절차를 확인하는 편이 좋습니다. 가정에서 가능한 복습량까지 반영하는지도 함께 비교하세요.",
        "과제량이 많다는 설명보다 완료 후 어떤 피드백을 받고 언제 다시 푸는지 확인하세요. 특정 결과보다 실제 실행 기록이 판단 근거가 됩니다.",
        "상담에서 정한 우선순위가 교재·과제·오답 일정에 구체적으로 반영되는지 보세요. 학생의 설명 과정도 정기적으로 확인하는 편이 좋습니다.",
        "학교 대비와 누적 복습을 구분해 계획하는지, 결석이나 일정 변화 때 어떻게 조정하는지 질문하세요. 관리 방식은 기록으로 확인해야 합니다.",
        "현재 상태를 과장하지 않고 부족한 부분과 가능한 복습량을 함께 설명하는지 살펴보세요. 다음 점검 시점이 분명한지도 중요한 기준입니다.",
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
    keep = {rank % len(question_banks), (rank + 2) % len(question_banks)}
    short_phrase = f"{local} {subject} 수업"
    answer_banks = (
        preparation_answers,
        diagnosis_answers,
        school_answers,
        grade_answers,
        comparison_answers,
    )
    result: list[dict[str, str]] = []
    for index, templates in enumerate(question_banks):
        phrase = title if index in keep else short_phrase
        question_code = shared.stable_number(config["slug"], local, "faq-question", index)
        template = templates[question_code % len(templates)]
        question = template.format(subject=phrase)
        answer_code = shared.stable_number(config["slug"], local, "faq", index)
        answers = answer_banks[index]
        answer = (
            f"{answers[answer_code % len(answers)]} "
            f"{closers[(answer_code // len(answers)) % len(closers)]}"
        )
        result.append({"question": question, "answer": answer})
    return result


def parse_professional_reviews(value: str) -> list[dict[str, str]]:
    marker = re.compile(
        r"^\s*(?:-\s*)?((?:후기\s*예시|예시\s*후기|상담\s*후\s*기록|보호자\s*추가\s*메모|후기)\s*\d*)\s*(?:[｜|:.)\-])\s*",
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
    if not reviews:
        # New manuscript sets use descriptive labels such as
        # "복습 습관을 잡고 싶었던 학부모 후기 예시:" and
        # "페이지 후기 문안 1.".  Keep the supplied label and parse the
        # text after the colon/full stop instead of falling back to a shared
        # review template.
        descriptive = re.compile(
            r"^\s*(?:-\s*)?(?P<label>[^\n]{1,100}?(?:후기|문안)[^\n]{0,50}?)"
            r"\s*(?:[:：]|\.)\s*(?P<content>.+?)\s*$"
        )
        for line in value.splitlines():
            match = descriptive.match(line)
            if not match:
                continue
            label = re.sub(r"\s+", " ", match.group("label")).strip()
            raw = re.sub(r"\s+", " ", match.group("content")).strip().strip('“”"')
            if raw:
                reviews.append({"label": label, "content": raw})
    if not reviews:
        # Elementary English-math manuscripts supply one short production
        # note followed by three standalone curly-quoted parent comments.
        # Parse only the quoted comments so the note never reaches the page.
        quoted = re.compile(r'^\s*[“"](?P<content>.+?)[”"]\s*$')
        for index, line in enumerate(value.splitlines(), start=1):
            match = quoted.match(line)
            if not match:
                continue
            raw = re.sub(r"\s+", " ", match.group("content")).strip()
            if raw:
                reviews.append({"label": f"학부모 상담 기록 {index}", "content": raw})
    if not reviews:
        for index, line in enumerate(value.splitlines(), start=1):
            match = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if not match:
                continue
            raw = re.sub(r"\s+", " ", match.group(1)).strip().strip('“”"')
            if raw:
                reviews.append({"label": f"학부모 상담 후기 {index}", "content": raw})
    return reviews


def review_label(local: str, config: dict[str, object], rank: int, index: int) -> str:
    """Return a reader-facing, deterministic label without production terms."""
    level = str(config["level"])
    banks = (
        "과목별 출발점을 확인한 학부모 기록",
        "영어·수학 보완 순서를 정한 상담 기록",
        "학습 자료를 함께 살펴본 보호자 기록",
        "다음 단원 기준을 확인한 학부모 기록",
        "과목별 학습경로를 점검한 상담 기록",
        "첫 진단 뒤 남긴 보호자 기록",
    )
    # Use a stable page-specific starting point and advance by index.  This
    # keeps labels varied across pages while guaranteeing that two or three
    # reviews on the same page never receive the same heading.
    code = shared.stable_number(str(config["slug"]), local, "review-label", rank)
    phrase = banks[(code + index) % len(banks)]
    return f"{local} {level} {phrase}"


def section_heading(
    original: str,
    local: str,
    config: dict[str, object],
    rank: int,
    index: int,
) -> str:
    """Keep the manuscript's specific H2 and use a safe role/lens fallback."""
    roles = tuple(str(item) for item in config.get("section_roles", ()))
    if not roles:
        return original
    source_heading = re.sub(r"\s+", " ", original).strip(" ·|-")
    if source_heading and len(source_heading) <= 100:
        return source_heading
    role = roles[index % len(roles)]
    lens_code = shared.stable_number(str(config["slug"]), local, "heading-lens", rank, index)
    lens = PATHWAY_HEADING_LENSES[lens_code % len(PATHWAY_HEADING_LENSES)]
    templates = (
        "{role} · {lens}",
        "{role}: {lens}",
        "{lens}로 확인하는 {role}",
        "{role} — {lens}",
        "{role} | {lens}",
        "{local} {role} · {lens}",
    )
    code = shared.stable_number(str(config["slug"]), local, "section-heading", rank, index)
    return templates[code % len(templates)].format(role=role, local=local, lens=lens)


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
        grade_prefix = str(config.get("grade_prefix", ""))
        if grade_prefix:
            grades = [grade for grade in grades if grade.startswith(grade_prefix)]
            fallback = f"{config['level']} 영어·수학 공통 수업 가능 학년 상담 확인 필요"
        center["verified_grades"] = grades
        center["grade_status"] = "" if grades else fallback
        center["grades"] = grades or [fallback]
        if grade_prefix:
            center["schools"] = schools_for_level(row, grade_prefix)
        else:
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
            reviews = list(manuscript.get("reviews", []))
            expected_reviews = config.get("expected_reviews")
            if expected_reviews is not None and len(reviews) != int(expected_reviews):
                raise ValueError(
                    f"{config['slug']}/{local}: parsed reviews={len(reviews)}, "
                    f"expected={expected_reviews}"
                )
            for review_index, review in enumerate(reviews):
                review["label"] = review_label(local, config, rank, review_index)
                review["content"] = final_polish(str(review["content"]), local, config, verified_grades, schools)
            manuscript["reviews"] = reviews
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
            manuscript["intro"] = [
                professional_diversify_text(
                    str(paragraph), local, rank, 50 + intro_index,
                    sentence_frequencies, config,
                )
                for intro_index, paragraph in enumerate(manuscript.get("intro", []))
            ]
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
            def title_variant(value: str, code: int, keep_first: bool = False) -> str:
                replaced = replace_title_repetition(
                    final_polish(value, local, config, verified_grades, schools),
                    title, local, config, code, keep_first=keep_first,
                )
                # Title-reference variants can introduce a new 받침-dependent
                # particle combination (for example "준비을").  Run the
                # deterministic grammar pass once more after substitution.
                return final_polish(replaced, local, config, verified_grades, schools)

            manuscript["intro"] = [
                title_variant(str(paragraph), 600 + index, keep_first=index == 0)
                for index, paragraph in enumerate(manuscript.get("intro", []))
            ]
            final_sections: list[tuple[str, list[str]]] = []
            for section_index, (heading, paragraphs) in enumerate(manuscript.get("sections", [])):
                if config.get("section_roles"):
                    final_heading = final_polish(
                        section_heading(str(heading), local, config, rank, section_index),
                        local, config, verified_grades, schools,
                    )
                else:
                    final_heading = title_variant(
                        str(heading), 700 + section_index, keep_first=section_index == 0,
                    )
                final_paragraphs = [
                    title_variant(
                        str(paragraph), 800 + section_index * 10 + paragraph_index,
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
                for item in manuscript.get("faqs", [])
            ]
            for review_index, review in enumerate(manuscript.get("reviews", [])):
                review["label"] = title_variant(
                    str(review.get("label", "")), 900 + review_index,
                )
                review["content"] = title_variant(
                    str(review["content"]), 920 + review_index,
                    keep_first=review_index == 0,
                )
            manuscript["summary"] = concise_summary(
                final_polish(
                    str(manuscript.get("summary", "")), local, config, verified_grades, schools,
                )
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
        items = [{"name": f"{config['label']} 전체 지역", "url": encoded_url("과목별학원", config["slug"])}]
        configured_related = config.get("related_pages")
        if configured_related:
            related_pages = [(str(slug), str(label)) for slug, label in configured_related]
        else:
            related_pages = [
                (str(item["slug"]), str(item["label"]))
                for item in CATEGORIES
                if item["slug"] != config["slug"]
            ]
        items.extend(
            {"name": f"{local} {label}", "url": encoded_url("과목별학원", slug, local)}
            for slug, label in related_pages
        )
        configured_base = config.get("base_page")
        if configured_base:
            base_slug, base_label = (str(value) for value in configured_base)
        else:
            base_slug = "영어학원" if config["focus"] == "english" else "수학학원"
            base_label = base_slug
        if all(item["url"] != encoded_url("과목별학원", base_slug, local) for item in items):
            items.append({"name": f"{local} {base_label}", "url": encoded_url("과목별학원", base_slug, local)})
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
        if config.get("role"):
            about.append({"@type": "Thing", "name": str(config["role"])})
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
    namespace["select_representatives"] = lambda order: representative_mapping(order, config)
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
    description = str(
        config.get("hub_description")
        or f"371개 동네별 {config['label']} 안내와 검증 가능한 센터 정보를 바탕으로 현재 학습 상태, 학교 자료, 오답 복습과 상담 준비 기준을 안내합니다."
    )
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

    description = f"수학·영어 단과와 학년별 영수·영어수학·전문·내신학원까지 {len(ALL_TOPICS)}개 지역별 안내를 학생의 현재 학습 상황에 맞춰 확인할 수 있습니다."
    source = re.sub(r'(<meta name="description" content=")[^"]*(">)', rf'\g<1>{description}\g<2>', source, count=1)
    source = re.sub(r'(<meta property="og:description" content=")[^"]*(">)', rf'\g<1>{description}\g<2>', source, count=1)
    source = re.sub(
        r"실제 지역 페이지가 준비된 [^<.]+ 분류만 표시합니다\.",
        f"실제 지역 페이지가 준비된 {len(ALL_TOPICS)}개 분류만 표시합니다.",
        source,
    )
    source = source.replace(
        "수학·영어 단과와 고등·중등·초등 영수 안내",
        "수학·영어 단과와 학년별 영수·영어수학·전문·내신학원 안내",
    )
    source = source.replace(
        "수학·영어 단과와 학년별 영수·전문학원 안내",
        "수학·영어 단과와 학년별 영수·영어수학·전문·내신학원 안내",
    )
    source = source.replace("필요한 과목 정하기", "필요한 과목·학년 분류 정하기")
    source = source.replace(
        "수학·영어 단과 또는 학년별 영수학원을 먼저 선택한 뒤",
        "단과·학년별 영수·영어수학·전문·내신학원 분류를 먼저 선택한 뒤",
    )

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
        elif item.get("@type") == "FAQPage":
            for faq in item.get("mainEntity", []):
                if faq.get("name") == "과목별학원 페이지는 전국센터 페이지와 무엇이 다른가요?":
                    faq["acceptedAnswer"]["text"] = (
                        "전국센터는 지역과 센터를 기준으로 찾는 구조이고, 과목별학원은 "
                        "단과·학년별 영수·영어수학·전문·내신학원 분류를 먼저 선택한 뒤 해당 동네의 "
                        "학습 안내를 확인하는 구조입니다."
                    )
    source = source[:match.start(1)] + compact_json(data) + source[match.end(1):]
    path.write_text(source, encoding="utf-8", newline="\n")


def refresh_sitemap_lastmod(slugs: list[str]) -> None:
    """Refresh dates for the categories regenerated in this invocation."""
    path = ROOT / "sitemap.xml"
    source = path.read_text(encoding="utf-8")
    for slug in slugs:
        prefix = SITE_URL + "/" + "/".join(
            quote(part, safe="") for part in ("과목별학원", slug)
        ) + "/"
        pattern = re.compile(
            rf"(<url>\s*<loc>{re.escape(prefix)}[^<]*</loc>\s*<lastmod>)[^<]+(</lastmod>)"
        )
        source, count = pattern.subn(rf"\g<1>{TODAY}\g<2>", source)
        if count != 372:
            raise ValueError(f"{slug}: sitemap lastmod targets={count}, expected=372")
    path.write_text(source, encoding="utf-8", newline="\n")


def main(target_slugs: set[str] | None = None) -> None:
    known_slugs = {str(config["slug"]) for config in CATEGORIES}
    requested = target_slugs or known_slugs
    unknown = requested - known_slugs
    if unknown:
        raise ValueError(f"unknown category slug(s): {', '.join(sorted(unknown))}")
    selected = [config for config in CATEGORIES if str(config["slug"]) in requested]
    namespaces: dict[str, dict[str, object]] = {}
    for config in selected:
        namespace = shared.transformed_namespace(config)
        configure_namespace(namespace, config)
        namespace["main"]()
        namespaces[str(config["slug"])] = namespace
        print(f'{config["slug"]}: generated 371 detail pages and one hub')
    update_master_subject_hub(namespaces)
    refresh_sitemap_lastmod([str(config["slug"]) for config in selected])
    print(f"updated master subject hub with {len(ALL_TOPICS)} live categories")


if __name__ == "__main__":
    main(set(sys.argv[1:]) if len(sys.argv) > 1 else None)
