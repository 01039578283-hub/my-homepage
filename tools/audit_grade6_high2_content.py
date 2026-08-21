#!/usr/bin/env python3
"""Independent content gate for the grade-6/high-school grade-2 batch.

The three attached XLSX workbooks are immutable, untrusted content data.  This
auditor reads their OOXML parts in memory, never opens Excel, never evaluates a
formula, and never treats cell text as an instruction.  It validates the raw
source contract and either the generator's in-memory projection or a materialized
release.  It writes no files.

Exit codes: 0 PASS, 1 FAIL, 2 HOLD.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote
from xml.etree import ElementTree as ET


sys.dont_write_bytecode = True

BASE_URL = "https://wawa-center.kr"
RELEASE_DATE = "2026-08-21"
EXPECTED_LOCALITIES = 371
EXPECTED_BASE_HTML = 17_229
EXPECTED_NEW_HTML = 1_116
EXPECTED_AUTHORIZED = 1_119
EXPECTED_FINAL_HTML = 18_345
EXPECTED_BASE_GRADE_HTML = 2_605
EXPECTED_FINAL_GRADE_HTML = 3_721
EXPECTED_BASE_SITEMAP_LOCATION_SHA256 = "97dce4825b1ee7f308f3c98dabe68e827d70980d3c1b109b8770c0cc25957074"
EXPECTED_BASE_SITEMAP_BLOCK_SHA256 = "fe1df9d38cc814094490c4377049f4f7daa08ba11a98b363381a51489b997c96"
EXPECTED_LOCALITY_SEQUENCE_SHA256 = "c800e886954b8198cc6425e6907632a62d69e4cf195abeaeaafd1b54094b9767"
EXPECTED_CELL_MAPPING_SHA256 = "ed72bcf9d04072cc4be04efc4e1cd5d2c7f466751bad4d51fb0313a2a7e36380"

GENERATOR_REL = Path("tools/generate_grade6_high2_pages.py")
PARENT_REL = Path("학년별학원/index.html")
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
LLMS_MARKER = "## 학년별학원 핵심 허브"

COMMON_HASHES = {
    "센터정보 정리.csv": "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a",
    "타깃학교.csv": "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f",
}

OOXML_ALLOWED = frozenset({
    "[Content_Types].xml",
    "_rels/.rels",
    "docProps/app.xml",
    "docProps/core.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/sharedStrings.xml",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
    "xl/workbook.xml",
    "xl/worksheets/sheet1.xml",
})
SHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

MARKERS = (
    "[페이지타이틀]",
    "[메타설명]",
    "[본문]",
    "[FAQ]",
    "[학부모후기]",
    "[JSON-LD 요약]",
)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MOJIBAKE = re.compile(r"(?:\ufffd|Ã.|Â.|â€|ì[\x80-\xff])")
PROMPT_OR_CODE = re.compile(
    r"(?:ignore\s+(?:all\s+)?previous|system\s+prompt|assistant\s*:|developer\s*:|"
    r"instructions?\s*:|이전\s*지시|지시를\s*무시|시스템\s*프롬프트|"
    r"명령을\s*실행|파일을\s*삭제|powershell|cmd\.exe|javascript\s*:|<script)",
    re.IGNORECASE,
)
GUARANTEE = re.compile(r"(?:100\s*%|무조건\s*(?:상승|향상|합격)|성적\s*보장|합격\s*보장)")
QUESTION = re.compile(r"^Q(?:([1-9][0-9]*))?([.)])\s*(.+)$")
ANSWER = re.compile(r"^A(?:([1-9][0-9]*))?([.)])\s*(.+)$")
RAW_URL_BLOCK = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    grade: str
    subject: str
    slug: str
    hook: str
    grade_column: str
    school_column: str
    school_hook: str
    workbook_name: str
    workbook_bytes: int
    workbook_sha256: str
    uncompressed_bytes: int
    entry_manifest_sha256: str
    cell_manifest_sha256: str
    cell_sequence_sha256: str
    total_chars: int
    min_chars: int
    max_chars: int
    title_exact: int
    h2_distribution: Mapping[int, int]
    format_distribution: Mapping[str, int]
    intro_distribution: Mapping[int, int]
    section_paragraph_distribution: Mapping[int, int]
    body_paragraphs: int
    faq_distribution: Mapping[int, int]
    review_distribution: Mapping[int, int]
    summary_distribution: Mapping[int, int]
    supported: int
    school_groups_provided: int
    school_chips: int
    school_unique: int
    manuscript_school_mentions: int
    manuscript_address_mentions: int

    @property
    def subject_slug(self) -> str:
        return self.subject + "학원"

    @property
    def category_root(self) -> Path:
        return Path("학년별학원") / self.slug

    @property
    def category_rel(self) -> Path:
        return self.category_root / "index.html"

    @property
    def unconfirmed(self) -> int:
        return EXPECTED_LOCALITIES - self.supported


CATEGORIES: tuple[Category, ...] = (
    Category(
        "elementary6_math", "초6 수학학원", "초6", "수학", "초6수학학원", "elementary6-math",
        "가능학년(수학)", "타깃학교(초)", "elementary-schools", "초6 수학학원.xlsx",
        1_228_435, "7820827f61a9b91c80d9cc3b0a68b018b2e8eed1154d1eebe659f3df4e8fe6a3",
        4_143_778, "5281eb79de40d50e92a7ebe104005703de85053d6476897ab2f25ad991697430",
        "48966ddc64d3e838e068546cbca21d9d20dc9f420079eafaead2d443bbce572d",
        "5792c0066078574c68eff514efb073402d8eaf477ece9eed81bdf4173dc06eb1",
        1_686_475, 3_556, 5_752, 247, {6: 164, 7: 207},
        {"markdown_h2": 368, "html_h2": 2, "plain": 1}, {0: 23, 1: 293, 2: 55},
        {2: 1_173, 3: 917, 4: 298, 5: 37, 6: 6, 7: 2}, 6_927,
        {5: 217, 6: 153, 7: 1}, {1: 41, 2: 144, 3: 171, 4: 15}, {1: 370, 2: 1},
        358, 297, 638, 305, 623, 276,
    ),
    Category(
        "elementary6_english", "초6 영어학원", "초6", "영어", "초6영어학원", "elementary6-english",
        "가능학년(영어)", "타깃학교(초)", "elementary-schools", "초6 영어학원.xlsx",
        1_255_108, "f507fab48c0e18303574eb78cdc5133c0ab2b1c72351fb40e31db5bc8f147148",
        4_164_631, "77a100995d9e38d1b59bbbb2cac40aff46f78e1c8e29bbde64d8d18bc088f3f4",
        "b13f9532e3d25f4f1c3d150499b5b72649fdc0b06295e69ae113d30531a776df",
        "7fb97a23bd7dae670cbf4d8229b48c992b486795d7153a8743357a7f5ec24044",
        1_696_011, 3_657, 5_884, 254, {6: 189, 7: 181, 9: 1},
        {"markdown_h2": 364, "html_h2": 2, "markdown_h3": 3, "numbered": 1, "plain": 1},
        {0: 18, 1: 312, 2: 41}, {1: 4, 2: 1_003, 3: 1_025, 4: 312, 5: 49, 6: 10, 7: 1, 8: 4, 9: 1, 10: 1},
        7_090, {5: 235, 6: 136}, {1: 38, 2: 131, 3: 181, 4: 21}, {1: 370, 2: 1},
        363, 297, 638, 305, 625, 279,
    ),
    Category(
        "high2_english", "고2 영어학원", "고2", "영어", "고2영어학원", "high2-english",
        "가능학년(영어)", "타깃학교(고)", "high-schools", "고2 영어학원.xlsx",
        1_248_002, "828bea4e58bc9d8192d0e1b0ce8d8be1c8749bdcdf5eb418aabf0ddcb622df26",
        4_122_594, "8bb7636db53f7f49442887e9a9a98ba7a5c761b32dfc6cae529fae64a3a51d95",
        "6897b65600df26b49d7648422c7b9ca5eb233fd85b9612c8df47f71d8b38c7dd",
        "732aa8030179f159b74862eade4a0717faca4c5105814e93e6a6dd4c0451a5c1",
        1_679_889, 3_725, 5_421, 285, {6: 203, 7: 168},
        {"markdown_h2": 366, "html_h2": 4, "markdown_h3": 1}, {0: 14, 1: 324, 2: 33},
        {2: 1_033, 3: 1_065, 4: 248, 5: 37, 6: 8, 7: 2, 9: 1}, 6_899,
        {5: 281, 6: 89, 7: 1}, {1: 53, 2: 126, 3: 179, 4: 13}, {1: 370, 2: 1},
        332, 308, 909, 378, 886, 273,
    ),
)
CATEGORY_BY_KEY = {item.key: item for item in CATEGORIES}

ALL_CATEGORY_LINKS = (
    ("중1 수학학원", "중1수학학원"), ("중1 영어학원", "중1영어학원"),
    ("중2 수학학원", "중2수학학원"), ("중2 영어학원", "중2영어학원"),
    ("중3 수학학원", "중3수학학원"), ("중3 영어학원", "중3영어학원"),
    ("고2 수학학원", "고2수학학원"),
    *((item.label, item.slug) for item in CATEGORIES),
)


def _heading_tuple(*values: str) -> tuple[str, ...]:
    return values


SPECIAL_HEADINGS: Mapping[tuple[str, int], tuple[str, str, tuple[str, ...]]] = {
    ("high2_english", 30): ("길음동", "html_h2", _heading_tuple(
        "고2 영어에서 먼저 점검해야 할 부분", "학교 시험에 맞춘 영어 내신 준비", "독해와 어법을 연결하는 수업",
        "오답을 성적 관리로 연결하는 방법", "수능형 영어를 내신과 함께 준비하기", "학생별 학습 계획과 학부모 확인 사항",
        "상담 전 준비하면 좋은 질문",
    )),
    ("high2_english", 135): ("은행동", "markdown_h3", _heading_tuple(
        "고2 영어에서 성적이 쉽게 오르지 않는 이유", "은행동 고2 학생에게 필요한 영어 학습훈련", "은행고 내신을 준비하는 방법",
        "학생 유형별 수업 방향", "은행동 생활권에서 꾸준히 다니는 학습 환경", "상담 전 확인하면 좋은 내용",
    )),
    ("high2_english", 286): ("복현동", "html_h2", _heading_tuple(
        "복현동 고2 영어, 지금 점검해야 할 부분", "학교별 내신 준비는 어떻게 달라질까", "장기관리반에서 진행하는 영어 학습",
        "고2 수능 영어를 함께 준비하는 방법", "영어와 수학을 함께 관리할 때의 기준", "복현동 학원 선택 전 확인할 사항",
    )),
    ("high2_english", 309): ("복산동", "html_h2", _heading_tuple(
        "고2 영어에서 먼저 확인해야 할 학습 문제", "복산동 학생에게 필요한 내신 영어 준비", "수능 독해와 어휘를 함께 다루는 방법",
        "문법과 서술형에서 실수를 줄이는 학습", "학생별 진도와 오답 관리", "상담 시 확인할 학원 선택 기준",
    )),
    ("high2_english", 344): ("월계동", "html_h2", _heading_tuple(
        "월계동 고2 영어, 지금 점검해야 할 학습 요소", "학교별 내신 대비는 무엇이 달라야 할까",
        "개념은 아는데 응용이 약한 학생을 위한 수업 방향", "내신과 모의고사를 함께 준비하는 학습 일정",
        "영어 수학을 함께 관리할 때의 기준", "월계동 학부모가 상담에서 확인할 내용", "학생에게 맞는 영어 공부 습관 만들기",
    )),
    ("elementary6_math", 95): ("호평동", "plain", _heading_tuple(
        "초6 수학에서 확인해야 할 핵심 영역", "학생 유형에 맞춘 수업 방향", "숙제관리로 학습 리듬 만들기",
        "학교별 진도와 중학교 준비", "수업에서 오답을 활용하는 방법", "호평동에서 상담할 때 확인할 내용",
    )),
    ("elementary6_math", 130): ("조남동", "html_h2", _heading_tuple(
        "초6 수학에서 먼저 확인해야 할 학습 상태", "조남동 초6 수학 수업의 핵심은 ‘이해 후 적용’",
        "조남초·목감초 학생에게 필요한 학교 진도 관리", "중학교 수학을 앞둔 학생의 준비 방향",
        "수학과 영어 학습을 함께 관리할 때의 기준", "학부모가 상담 전에 확인할 내용",
    )),
    ("elementary6_math", 219): ("동춘동", "html_h2", _heading_tuple(
        "동춘동 초6 수학, 지금 확인해야 할 학습 상태", "초6 교과 수학에서 자주 어려워하는 부분", "개념 이해 후 응용까지 이어지는 수업",
        "오답을 남기는 방식이 수학 실력을 좌우합니다", "대건고·연수여고·연수고와 연결되는 학습 준비",
        "영어와 수학을 함께 관리할 때의 기준", "상담 전 학부모가 확인할 질문",
    )),
    ("elementary6_english", 6): ("화곡동", "numbered", _heading_tuple(
        "화곡동 초6 영어학원이 필요한 시기", "초6 학생의 영어 실력은 무엇부터 확인할까", "화곡동 초6 영어 수업의 학습 구성",
        "독해가 느린 학생을 위한 지도 방법", "중학교 영어를 대비하는 초6 학습 계획", "학부모가 상담 전 확인하면 좋은 내용",
    )),
    ("elementary6_english", 18): ("용두동", "html_h2", _heading_tuple(
        "초6 영어에서 먼저 확인해야 할 학습 상태", "용두동 초6 학생에게 필요한 영어 학습 방향", "학교 수업과 중학교 영어를 연결하는 방법",
        "영어 오답을 실력으로 바꾸는 학습코칭", "숙제와 학원결제관리까지 이어지는 학부모 확인", "서울 동대문구 용두동에서 학원을 선택할 때",
    )),
    ("elementary6_english", 26): ("북가좌동", "markdown_h3", _heading_tuple(
        "북가좌동 초6 영어, 지금 확인해야 할 학습 요소", "가재울초·연가초 학생의 학교 영어 학습",
        "개념은 알지만 응용이 어려운 학생을 위한 수업", "초6 영어에서 문법과 독해를 연결하는 방법",
        "수업 전후 학습 관리와 학원결제시스템", "중학교 영어를 앞둔 6학년의 준비 방향", "북가좌동에서 상담할 때 확인할 내용",
    )),
    ("elementary6_english", 32): ("목동", "plain", _heading_tuple(
        "목동 초6 학생에게 필요한 영어 학습 점검", "신목초·서정초 학생의 중등 영어 준비", "어휘·문법·독해를 연결하는 학습 방식",
        "학생 유형별로 달라야 하는 지도", "목동 초6 영어학원 상담 시 확인할 내용", "중학교 영어를 위한 6학년 학습 계획",
    )),
    ("elementary6_english", 53): ("삼송동", "markdown_h3", _heading_tuple(
        "삼송동 초6 학생에게 필요한 영어 학습 방향", "원흥초·삼송초 학생의 초6 영어 점검", "어휘를 오래 기억하는 학습전략",
        "문법을 문제 풀이와 연결하는 방법", "중학교 진학 전 독해와 서술형 준비", "삼송동에서 학원 선택 시 확인할 사항",
    )),
    ("elementary6_english", 123): ("권선동", "markdown_h3", _heading_tuple(
        "초6 영어, 지금 확인해야 할 학습 상태", "매탄초·매현초 학생에게 필요한 중등 전환 준비", "영어와 수학을 함께 살피는 학습점검",
        "초등 영어에서 중학교 내신 영어로 연결하기", "오답이 반복되는 학생을 위한 보완 방식", "수업 위치와 상담 시 확인할 내용",
    )),
    ("elementary6_english", 222): ("송도동", "html_h2", _heading_tuple(
        "초6 영어, 지금 시험대비가 필요한 이유", "해송초등학교 학습 흐름에 맞춘 영어 관리", "개념 이해 후 응용까지 이어지는 수업",
        "영어와 수학을 함께 관리해야 하는 초6 시기", "송도동 초6 학생에게 필요한 학습 점검",
        "시험 직전보다 평소 관리가 중요한 이유", "상담 시 확인할 학원 선택 기준",
    )),
}


@dataclass
class Audit:
    errors: list[dict[str, str]] = field(default_factory=list)
    holds: list[dict[str, str]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    max_findings: int = 250

    def error(self, code: str, location: Any, message: str) -> None:
        if len(self.errors) < self.max_findings:
            self.errors.append({"code": code, "location": str(location), "message": message})

    def hold(self, code: str, location: Any, message: str) -> None:
        if len(self.holds) < self.max_findings:
            self.holds.append({"code": code, "location": str(location), "message": message})

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else "HOLD" if self.holds else "PASS"


@dataclass(frozen=True)
class CommonRow:
    locality: str
    region: str
    city: str
    center_name: str
    address: str
    fee_url: str
    grades: Mapping[str, tuple[str, ...]]
    schools: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class Section:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class FAQ:
    question_prefix: str
    question: str
    answer_prefix: str
    answer: str


@dataclass(frozen=True)
class Manuscript:
    row_number: int
    locality: str
    title: str
    meta: str
    intro: tuple[str, ...]
    sections: tuple[Section, ...]
    faqs: tuple[FAQ, ...]
    reviews: tuple[str, ...]
    summaries: tuple[str, ...]
    body_format: str
    raw_text: str
    raw_sha256: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def encoded_url(*parts: str) -> str:
    return BASE_URL + "/" + "/".join(quote(part, safe="") for part in parts) + ("/" if parts else "")


def split_paragraphs(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r"\n[ \t]*\n", value.strip()) if part.strip())


def normalized_header(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r", "").replace("\n", "").strip()


def split_csv_tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def read_csv(path: Path, expected_sha: str, audit: Audit) -> list[dict[str, str]]:
    if path.is_symlink() or not path.is_file():
        audit.error("common_missing", path, "must be a regular non-symlink file")
        return []
    raw = path.read_bytes()
    actual = sha256_bytes(raw)
    if actual != expected_sha:
        audit.error("common_hash", path, f"actual={actual}, expected={expected_sha}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        audit.error("common_utf8", path, repr(exc))
        return []
    controls = CONTROL.findall(text)
    if controls:
        if path.name != "센터정보 정리.csv" or controls != ["\x08"]:
            audit.error("common_control", path, repr(controls))
            return []
        text = text.replace("\x08", "")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        audit.error("common_header", path, "missing")
        return []
    names = [normalized_header(item) for item in reader.fieldnames]
    result: list[dict[str, str]] = []
    for raw_row in reader:
        if None in raw_row:
            audit.error("common_excess_field", path, repr(raw_row[None]))
            continue
        result.append({
            name: unicodedata.normalize("NFC", (raw_row[original] or "").strip())
            for original, name in zip(reader.fieldnames, names, strict=True)
        })
    return result


def load_common(common: Path, audit: Audit) -> tuple[CommonRow, ...]:
    center = read_csv(common / "센터정보 정리.csv", COMMON_HASHES["센터정보 정리.csv"], audit)
    target = read_csv(common / "타깃학교.csv", COMMON_HASHES["타깃학교.csv"], audit)
    required = {
        "근처 수업가능 동네", "지역", "시or구", "센터명", "센터 주소", "센터 교습비",
        "타깃학교(초)", "타깃학교(중)", "타깃학교(고)", "가능학년(영어)", "가능학년(수학)",
    }
    if len(center) != EXPECTED_LOCALITIES or not center or not required.issubset(center[0]):
        audit.error("common_center_contract", common, f"rows={len(center)}")
        return ()
    if len(target) != EXPECTED_LOCALITIES:
        audit.error("common_target_count", common, f"rows={len(target)}")
        return ()
    target_by_locality = {item.get("근처 수업가능 동네", ""): item for item in target}
    if len(target_by_locality) != EXPECTED_LOCALITIES:
        audit.error("common_target_unique", common, f"unique={len(target_by_locality)}")
    result: list[CommonRow] = []
    seen: set[str] = set()
    parity = ("근처 수업가능 동네", "지역", "시or구", "센터명", "타깃학교(초)", "타깃학교(중)", "타깃학교(고)")
    for source in center:
        locality = source["근처 수업가능 동네"]
        if not locality or locality in seen:
            audit.error("common_locality", common, repr(locality))
            continue
        seen.add(locality)
        companion = target_by_locality.get(locality)
        if companion is None or any(source.get(key, "") != companion.get(key, "") for key in parity):
            audit.error("common_target_parity", locality, "seven source fields differ")
        result.append(CommonRow(
            locality=locality,
            region=source["지역"],
            city=source["시or구"],
            center_name=source["센터명"],
            address=source["센터 주소"],
            fee_url=source["센터 교습비"],
            grades={
                "가능학년(영어)": split_csv_tokens(source["가능학년(영어)"]),
                "가능학년(수학)": split_csv_tokens(source["가능학년(수학)"]),
            },
            schools={
                "타깃학교(초)": split_csv_tokens(source["타깃학교(초)"]),
                "타깃학교(고)": split_csv_tokens(source["타깃학교(고)"]),
            },
        ))
    sequence = sha256_bytes("\n".join(item.locality for item in result).encode("utf-8"))
    if sequence != EXPECTED_LOCALITY_SEQUENCE_SHA256:
        audit.error("common_locality_sequence", common, sequence)
    for category in CATEGORIES:
        supported = sum(category.grade in item.grades[category.grade_column] for item in result)
        schools = [school for item in result for school in item.schools[category.school_column]]
        provided = sum(bool(item.schools[category.school_column]) for item in result)
        actual = (supported, provided, len(schools), len(set(schools)))
        expected = (category.supported, category.school_groups_provided, category.school_chips, category.school_unique)
        if actual != expected:
            audit.error("common_category_metrics", category.key, f"actual={actual}, expected={expected}")
    audit.observations["common"] = {
        "localities": len(result), "locality_sequence_sha256": sequence,
        "categories": {
            item.key: {
                "supported": item.supported, "unconfirmed": item.unconfirmed,
                "school_groups_provided": item.school_groups_provided,
                "school_groups_missing": EXPECTED_LOCALITIES - item.school_groups_provided,
                "school_chips": item.school_chips, "school_unique": item.school_unique,
                "school_hook": item.school_hook,
            }
            for item in CATEGORIES
        },
    }
    return tuple(result)


def safe_archive_name(name: str) -> bool:
    posix = PurePosixPath(name.replace("\\", "/"))
    windows = PureWindowsPath(name)
    return not (
        posix.is_absolute() or windows.is_absolute() or windows.drive
        or ".." in posix.parts or ".." in windows.parts or CONTROL.search(name)
    )


def load_workbook_cells(category: Category, path: Path, audit: Audit) -> tuple[str, ...]:
    location = f"{category.key}:{path}"
    if path.is_symlink() or not path.is_file():
        audit.error("workbook_missing", location, "must be a regular non-symlink file")
        return ()
    raw = path.read_bytes()
    actual_hash = sha256_bytes(raw)
    if len(raw) != category.workbook_bytes or actual_hash != category.workbook_sha256:
        audit.error(
            "workbook_identity", location,
            f"bytes={len(raw)}, sha256={actual_hash}, expected={category.workbook_bytes}/{category.workbook_sha256}",
        )
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or set(names) != OOXML_ALLOWED:
                audit.error("workbook_entries", location, repr(names))
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                ratio = info.file_size / max(info.compress_size, 1)
                if (
                    not safe_archive_name(info.filename) or mode == 0o120000 or info.is_dir()
                    or info.flag_bits & 1 or info.file_size > 8_000_000 or ratio > 50
                ):
                    audit.error("workbook_unsafe_entry", location, info.filename)
            uncompressed = sum(item.file_size for item in infos)
            entry_manifest = sha256_bytes("".join(
                f"{item.filename}\t{item.file_size}\t{item.CRC:08x}\n" for item in infos
            ).encode("utf-8"))
            if uncompressed != category.uncompressed_bytes or entry_manifest != category.entry_manifest_sha256:
                audit.error(
                    "workbook_entry_manifest", location,
                    f"bytes={uncompressed}, manifest={entry_manifest}",
                )
            bad_crc = archive.testzip()
            if bad_crc is not None:
                audit.error("workbook_crc", location, bad_crc)
            content_types = archive.read("[Content_Types].xml")
            relationships = archive.read("xl/_rels/workbook.xml.rels")
            forbidden = re.compile(rb"(?:vbaProject|macroEnabled|externalLink|oleObject|activeX|connections)", re.I)
            if forbidden.search(content_types) or forbidden.search(relationships) or b'TargetMode="External"' in relationships:
                audit.error("workbook_active_part", location, "executable or external relationship")

            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook.findall(".//x:sheets/x:sheet", SHEET_NS)
            if (
                len(sheets) != 1 or sheets[0].get("name") != "Sheet1"
                or sheets[0].get("state", "visible") != "visible"
                or not sheets[0].get(f"{{{OFFICE_REL_NS}}}id")
            ):
                audit.error("workbook_sheets", location, repr([(x.get("name"), x.get("state")) for x in sheets]))

            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_nodes = shared_root.findall("x:si", SHEET_NS)
            shared: list[str] = []
            for index, node in enumerate(shared_nodes):
                text_nodes = node.findall(".//x:t", SHEET_NS)
                if len(text_nodes) != 1 or node.findall("x:r", SHEET_NS) or node.findall("x:rPh", SHEET_NS):
                    audit.error("workbook_rich_string", f"{category.key}:shared:{index}", "plain t only")
                shared.append("".join(item.text or "" for item in text_nodes))
            if (
                shared_root.get("count") != str(EXPECTED_LOCALITIES)
                or shared_root.get("uniqueCount") != str(EXPECTED_LOCALITIES)
                or len(shared) != EXPECTED_LOCALITIES or len(set(shared)) != EXPECTED_LOCALITIES
            ):
                audit.error("workbook_shared_strings", location, f"cells={len(shared)}, unique={len(set(shared))}")

            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            dimension = sheet.find("x:dimension", SHEET_NS)
            rows = sheet.findall(".//x:sheetData/x:row", SHEET_NS)
            if dimension is None or dimension.get("ref") != "A1:A371" or len(rows) != EXPECTED_LOCALITIES:
                audit.error("workbook_dimension", location, f"dimension={dimension.get('ref') if dimension is not None else None}, rows={len(rows)}")
            if (
                sheet.findall(".//x:f", SHEET_NS)
                or sheet.findall(".//x:hyperlink", SHEET_NS)
                or sheet.findall(".//x:mergeCell", SHEET_NS)
            ):
                audit.error("workbook_active_cells", location, "formula/hyperlink/merge present")
            values: list[str] = []
            mapping: list[tuple[str, int]] = []
            for row_number, row in enumerate(rows, 1):
                cells = row.findall("x:c", SHEET_NS)
                if row.get("r") != str(row_number) or len(cells) != 1:
                    audit.error("workbook_row", location, f"row={row_number}, cells={len(cells)}")
                    continue
                cell = cells[0]
                value_node = cell.find("x:v", SHEET_NS)
                ref = f"A{row_number}"
                if cell.get("r") != ref or cell.get("t") != "s" or value_node is None:
                    audit.error("workbook_cell", location, f"row={row_number}")
                    continue
                try:
                    shared_index = int(value_node.text or "")
                    value = shared[shared_index]
                except (ValueError, IndexError) as exc:
                    audit.error("workbook_cell_index", f"{category.key}:{ref}", repr(exc))
                    continue
                mapping.append((ref, shared_index))
                values.append(value)
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        audit.error("workbook_read", location, repr(exc))
        return ()

    cell_manifest = sha256_bytes("".join(
        f"{index}\t{sha256_bytes(value.encode('utf-8'))}\n"
        for index, value in enumerate(values, 1)
    ).encode("utf-8"))
    sequence = sha256_bytes("\0".join(values).encode("utf-8"))
    mapping_hash = sha256_bytes("".join(f"{ref}\t{index}\n" for ref, index in mapping).encode("ascii"))
    actual_metrics = (len(values), len(set(values)), sum(map(len, values)), min(map(len, values), default=0), max(map(len, values), default=0))
    expected_metrics = (EXPECTED_LOCALITIES, EXPECTED_LOCALITIES, category.total_chars, category.min_chars, category.max_chars)
    if actual_metrics != expected_metrics:
        audit.error("workbook_cell_metrics", location, f"actual={actual_metrics}, expected={expected_metrics}")
    if (
        cell_manifest != category.cell_manifest_sha256 or sequence != category.cell_sequence_sha256
        or mapping_hash != EXPECTED_CELL_MAPPING_SHA256
    ):
        audit.error(
            "workbook_cell_hashes", location,
            f"manifest={cell_manifest}, sequence={sequence}, mapping={mapping_hash}",
        )
    audit.observations.setdefault("workbooks", {})[category.key] = {
        "path": str(path), "bytes": len(raw), "sha256": actual_hash,
        "entries": len(OOXML_ALLOWED), "uncompressed_bytes": category.uncompressed_bytes,
        "sheet": "Sheet1", "range": "A1:A371", "cells": len(values), "unique_cells": len(set(values)),
        "formulas": 0, "hyperlinks": 0, "merged_ranges": 0,
        "cell_manifest_sha256": cell_manifest, "cell_sequence_sha256": sequence,
        "cell_mapping_sha256": mapping_hash,
    }
    return tuple(values)


def parse_body(
    category: Category,
    body: str,
    row_number: int,
    locality: str,
    audit: Audit,
) -> tuple[str, tuple[str, ...], tuple[Section, ...]]:
    blocks = list(split_paragraphs(body))
    parsed: list[tuple[str, str]] = []
    special = SPECIAL_HEADINGS.get((category.key, row_number))
    plain_allowlist = set(special[2]) if special is not None and special[1] == "plain" else set()
    selected_format = special[1] if special is not None else "markdown_h2"
    heading_count = 0
    for block in blocks:
        markdown_h2 = re.fullmatch(r"##[ \t]+(.+?)[ \t]*", block, re.DOTALL)
        html_h2 = re.fullmatch(r"<h2>([^\n<>]+)</h2>[ \t]*", block, re.IGNORECASE)
        markdown_h3 = re.fullmatch(r"###[ \t]+(.+?)[ \t]*", block, re.DOTALL)
        numbered = re.fullmatch(r"[1-9][0-9]*\.[ \t]+(.+?)[ \t]*", block, re.DOTALL)
        matches = {
            "markdown_h2": markdown_h2 if "\n" not in block else None,
            "html_h2": html_h2,
            "markdown_h3": markdown_h3 if "\n" not in block else None,
            "numbered": numbered if "\n" not in block else None,
            "plain": block if block in plain_allowlist else None,
        }
        chosen = matches[selected_format]
        if chosen is None:
            parsed.append(("p", block))
            continue
        heading_count += 1
        heading = block if selected_format == "plain" else chosen.group(1).strip()
        parsed.append(("h", heading))
    body_format = selected_format
    if not heading_count:
        audit.error("source_body_format", f"{category.key}:row:{row_number}:{locality}", f"missing {selected_format}")
    if special is None:
        if body_format != "markdown_h2":
            audit.error("source_body_unexpected_variant", f"{category.key}:row:{row_number}:{locality}", body_format)
    else:
        expected_locality, expected_format, expected_headings = special
        if (locality, body_format) != (expected_locality, expected_format):
            audit.error(
                "source_body_special", f"{category.key}:row:{row_number}",
                f"actual={(locality, body_format)}, expected={(expected_locality, expected_format)}",
            )
    intro: list[str] = []
    sections: list[list[Any]] = []
    current: list[Any] | None = None
    for kind, value in parsed:
        if kind == "h":
            current = [value, []]
            sections.append(current)
        elif current is None:
            intro.append(value)
        else:
            current[1].append(value)
    result = tuple(Section(str(heading), tuple(paragraphs)) for heading, paragraphs in sections)
    if not result or any(not item.heading or not item.paragraphs for item in result):
        audit.error("source_body_sections", f"{category.key}:row:{row_number}:{locality}", f"sections={len(result)}")
    if special is not None and tuple(item.heading for item in result) != special[2]:
        audit.error("source_special_headings", f"{category.key}:row:{row_number}:{locality}", repr(tuple(item.heading for item in result)))
    return body_format, tuple(intro), result


def parse_faq(category: Category, value: str, row_number: int, locality: str, audit: Audit) -> tuple[FAQ, ...]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) % 2:
        audit.error("source_faq_lines", f"{category.key}:row:{row_number}:{locality}", f"count={len(lines)}")
        return ()
    result: list[FAQ] = []
    for offset in range(0, len(lines), 2):
        question = QUESTION.fullmatch(lines[offset])
        answer = ANSWER.fullmatch(lines[offset + 1])
        if question is None or answer is None:
            audit.error("source_faq_pair", f"{category.key}:row:{row_number}:{locality}", repr(lines[offset:offset + 2]))
            continue
        question_number = question.group(1)
        answer_number = answer.group(1)
        expected_number = offset // 2 + 1
        if question_number is not None and int(question_number) != expected_number:
            audit.error("source_faq_question_order", f"{category.key}:row:{row_number}:{locality}", question_number)
        if answer_number is not None and int(answer_number) != expected_number:
            audit.error("source_faq_answer_order", f"{category.key}:row:{row_number}:{locality}", answer_number)
        if question_number is not None and answer_number is not None and question_number != answer_number:
            audit.error("source_faq_number_pair", f"{category.key}:row:{row_number}:{locality}", f"{question_number}/{answer_number}")
        result.append(FAQ(
            "Q" + (question_number or "") + question.group(2), question.group(3).strip(),
            "A" + (answer_number or "") + answer.group(2), answer.group(3).strip(),
        ))
    return tuple(result)


def parse_manuscript(
    category: Category,
    raw_text: str,
    row: CommonRow,
    row_number: int,
    audit: Audit,
) -> Manuscript | None:
    location = f"{category.key}:row:{row_number}:{row.locality}"
    if unicodedata.normalize("NFC", raw_text) != raw_text:
        audit.error("source_nfc", location, "not NFC")
    if CONTROL.search(raw_text) or MOJIBAKE.search(raw_text) or GUARANTEE.search(raw_text):
        audit.error("source_quality", location, "control/mojibake/guarantee pattern")
    instruction = PROMPT_OR_CODE.search(raw_text)
    if instruction:
        audit.error("source_instruction_like_data", location, instruction.group(0))
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    positions: list[int] = []
    for marker in MARKERS:
        hits = [index for index, line in enumerate(lines) if line.strip() == marker]
        if len(hits) != 1:
            audit.error("source_marker", location, f"{marker} count={len(hits)}")
            return None
        positions.append(hits[0])
    if positions != sorted(positions) or any(line.strip() for line in lines[:positions[0]]):
        audit.error("source_marker_order", location, repr(positions))
        return None

    def segment(index: int) -> str:
        end = positions[index + 1] if index + 1 < len(positions) else len(lines)
        return "\n".join(lines[positions[index] + 1:end]).strip("\n")

    titles = split_paragraphs(segment(0))
    metas = split_paragraphs(segment(1))
    body = segment(2).strip()
    faq_value = segment(3).strip()
    reviews = split_paragraphs(segment(4))
    summaries = split_paragraphs(segment(5))
    if len(titles) != 1 or len(metas) != 1 or not body or not reviews or not summaries:
        audit.error(
            "source_required_sections", location,
            f"title={len(titles)}, meta={len(metas)}, body={bool(body)}, reviews={len(reviews)}, summaries={len(summaries)}",
        )
        return None
    expected_prefix = f"{row.locality} {category.label}"
    if not titles[0].startswith(expected_prefix):
        audit.error("source_title_locality", location, repr(titles[0]))
    if "\n" in metas[0]:
        audit.error("source_meta_multiline", location, repr(metas[0]))
    body_format, intro, sections = parse_body(category, body, row_number, row.locality, audit)
    faqs = parse_faq(category, faq_value, row_number, row.locality, audit)
    return Manuscript(
        row_number, row.locality, titles[0], metas[0], intro, sections, faqs, reviews, summaries,
        body_format, raw_text, sha256_bytes(raw_text.encode("utf-8")),
    )


def validate_source_contract(
    category: Category,
    cells: Sequence[str],
    rows: Sequence[CommonRow],
    audit: Audit,
) -> tuple[Manuscript, ...]:
    if len(cells) != EXPECTED_LOCALITIES or len(rows) != EXPECTED_LOCALITIES:
        return ()
    manuscripts: list[Manuscript] = []
    for row_number, (raw_text, row) in enumerate(zip(cells, rows, strict=True), 1):
        manuscript = parse_manuscript(category, raw_text, row, row_number, audit)
        if manuscript is not None:
            manuscripts.append(manuscript)
    if len(manuscripts) != EXPECTED_LOCALITIES:
        audit.error("source_manuscript_count", category.key, f"actual={len(manuscripts)}")
        return tuple(manuscripts)
    h2_distribution = Counter(len(item.sections) for item in manuscripts)
    format_distribution = Counter(item.body_format for item in manuscripts)
    intro_distribution = Counter(len(item.intro) for item in manuscripts)
    section_distribution = Counter(len(section.paragraphs) for item in manuscripts for section in item.sections)
    body_paragraphs = sum(len(item.intro) + sum(len(section.paragraphs) for section in item.sections) for item in manuscripts)
    faq_distribution = Counter(len(item.faqs) for item in manuscripts)
    review_distribution = Counter(len(item.reviews) for item in manuscripts)
    summary_distribution = Counter(len(item.summaries) for item in manuscripts)
    title_exact = sum(item.title == f"{item.locality} {category.label}" for item in manuscripts)
    common_by_locality = {item.locality: item for item in rows}
    school_mentions = sum(
        school in item.raw_text
        for item in manuscripts
        for school in common_by_locality[item.locality].schools[category.school_column]
    )
    address_mentions = sum(common_by_locality[item.locality].address in item.raw_text for item in manuscripts)
    actual = {
        "title_exact": title_exact,
        "h2_distribution": dict(sorted(h2_distribution.items())),
        "format_distribution": dict(sorted(format_distribution.items())),
        "intro_distribution": dict(sorted(intro_distribution.items())),
        "section_paragraph_distribution": dict(sorted(section_distribution.items())),
        "body_paragraphs": body_paragraphs,
        "faq_distribution": dict(sorted(faq_distribution.items())),
        "review_distribution": dict(sorted(review_distribution.items())),
        "summary_distribution": dict(sorted(summary_distribution.items())),
        "manuscript_school_mentions": school_mentions,
        "manuscript_address_mentions": address_mentions,
    }
    expected = {
        "title_exact": category.title_exact,
        "h2_distribution": dict(category.h2_distribution),
        "format_distribution": dict(category.format_distribution),
        "intro_distribution": dict(category.intro_distribution),
        "section_paragraph_distribution": dict(category.section_paragraph_distribution),
        "body_paragraphs": category.body_paragraphs,
        "faq_distribution": dict(category.faq_distribution),
        "review_distribution": dict(category.review_distribution),
        "summary_distribution": dict(category.summary_distribution),
        "manuscript_school_mentions": category.manuscript_school_mentions,
        "manuscript_address_mentions": category.manuscript_address_mentions,
    }
    if actual != expected:
        differences = {key: {"actual": actual[key], "expected": expected[key]} for key in expected if actual[key] != expected[key]}
        audit.error("source_aggregate", category.key, repr(differences))
    audit.observations.setdefault("source", {})[category.key] = {
        **actual,
        "title_extended": EXPECTED_LOCALITIES - title_exact,
        "source_h2": sum(key * value for key, value in h2_distribution.items()),
        "source_faq": sum(key * value for key, value in faq_distribution.items()),
        "source_review_blocks": sum(key * value for key, value in review_distribution.items()),
        "source_summary_paragraphs": sum(key * value for key, value in summary_distribution.items()),
        "visible_manuscript_corrections": 0,
    }
    return tuple(manuscripts)


@dataclass(frozen=True)
class View:
    root: Path
    overrides: Mapping[str, str | bytes] = field(default_factory=dict)

    def exists(self, relative: str | Path) -> bool:
        rel = Path(relative).as_posix()
        return rel in self.overrides or (self.root / Path(rel)).is_file()

    def bytes(self, relative: str | Path) -> bytes:
        rel = Path(relative).as_posix()
        if rel in self.overrides:
            value = self.overrides[rel]
            return value if isinstance(value, bytes) else value.encode("utf-8")
        return self.root.joinpath(*PurePosixPath(rel).parts).read_bytes()

    def text(self, relative: str | Path) -> str:
        return self.bytes(relative).decode("utf-8")


def detail_rel(category: Category, locality: str) -> Path:
    return category.category_root / locality / "index.html"


def expected_new_html_paths(rows: Sequence[CommonRow]) -> set[str]:
    return {
        path.as_posix()
        for category in CATEGORIES
        for path in (category.category_rel, *(detail_rel(category, row.locality) for row in rows))
    }


def expected_authorized_paths(rows: Sequence[CommonRow]) -> set[str]:
    return expected_new_html_paths(rows) | {PARENT_REL.as_posix(), SITEMAP_REL.as_posix(), LLMS_REL.as_posix()}


def enumerate_html(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*.html") if path.is_file()}


def materialization_state(root: Path, rows: Sequence[CommonRow], audit: Audit) -> str:
    expected = expected_new_html_paths(rows)
    present = {rel for rel in expected if root.joinpath(*PurePosixPath(rel).parts).is_file()}
    if not present:
        if len(enumerate_html(root)) != EXPECTED_BASE_HTML:
            audit.error("baseline_html_count", root, f"actual={len(enumerate_html(root))}, expected={EXPECTED_BASE_HTML}")
        grade_count = sum(1 for path in (root / "학년별학원").rglob("*.html") if path.is_file())
        if grade_count != EXPECTED_BASE_GRADE_HTML:
            audit.error("baseline_grade_count", root, f"actual={grade_count}, expected={EXPECTED_BASE_GRADE_HTML}")
        return "base"
    if present == expected:
        return "release"
    audit.error("partial_materialization", root, f"present={len(present)}, expected={len(expected)}")
    return "partial"


def source_snapshot(
    root: Path,
    workbook_paths: Mapping[str, Path],
    common: Path,
    rows: Sequence[CommonRow],
) -> Mapping[str, str]:
    paths = [root / GENERATOR_REL, *(workbook_paths[key] for key in sorted(workbook_paths))]
    paths += [common / name for name in sorted(COMMON_HASHES)]
    paths += [root.joinpath(*PurePosixPath(rel).parts) for rel in sorted(expected_authorized_paths(rows))]
    result: dict[str, str] = {}
    for path in paths:
        key = str(path.resolve(strict=False))
        result[key] = sha256_file(path) if path.is_file() else "ABSENT"
    return result


def load_generator(root: Path, audit: Audit) -> ModuleType | None:
    path = root / GENERATOR_REL
    if path.is_symlink() or not path.is_file():
        audit.error("generator_missing", path, "must be a regular non-symlink file")
        return None
    try:
        name = f"_grade6_high2_generator_{sha256_file(path)[:12]}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError("spec loader unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - converted to an audit finding
        audit.error("generator_import", path, repr(exc))
        return None
    if not callable(getattr(module, "build_plan", None)):
        audit.error("generator_api", path, "build_plan missing")
        return None
    audit.observations["generator"] = {"path": str(path), "sha256": sha256_file(path)}
    return module


def normalize_plan_documents(plan: Any, root: Path, audit: Audit) -> Mapping[str, str | bytes]:
    source = getattr(plan, "authorized_documents", None)
    if not isinstance(source, Mapping):
        audit.error("plan_documents", GENERATOR_REL, "authorized_documents is not a mapping")
        return {}
    result: dict[str, str | bytes] = {}
    for raw_path, value in source.items():
        path = Path(raw_path)
        if path.is_absolute() or ".." in path.parts or not isinstance(value, (str, bytes)):
            audit.error("plan_document_entry", raw_path, type(value).__name__)
            continue
        rel = path.as_posix()
        if rel in result:
            audit.error("plan_document_duplicate", rel, "duplicate")
            continue
        result[rel] = value
    return result


def build_projected_view(
    root: Path,
    workbook_paths: Mapping[str, Path],
    common: Path,
    rows: Sequence[CommonRow],
    audit: Audit,
) -> View | None:
    module = load_generator(root, audit)
    if module is None:
        return None
    before = source_snapshot(root, workbook_paths, common, rows)
    try:
        plan = module.build_plan(root, workbook_paths, common)
    except Exception as exc:  # noqa: BLE001 - plan failures are audit findings
        audit.error("plan_build", GENERATOR_REL, repr(exc))
        return None
    after = source_snapshot(root, workbook_paths, common, rows)
    if before != after:
        changed = [key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]
        audit.error("plan_write", GENERATOR_REL, repr(changed[:20]))
    documents = normalize_plan_documents(plan, root, audit)
    expected = expected_authorized_paths(rows)
    if set(documents) != expected or len(documents) != EXPECTED_AUTHORIZED:
        audit.error(
            "plan_authorized_paths", GENERATOR_REL,
            f"actual={len(documents)}, missing={sorted(expected-set(documents))[:10]}, extra={sorted(set(documents)-expected)[:10]}",
        )
    second = tuple(getattr(plan, "second_pass_changes", ()))
    if second:
        audit.error("plan_second_pass", GENERATOR_REL, repr(second[:10]))
    after_manifest = getattr(plan, "after_manifest", None)
    if not isinstance(after_manifest, Mapping) or len(after_manifest) != EXPECTED_AUTHORIZED:
        audit.error("plan_after_manifest", GENERATOR_REL, f"actual={len(after_manifest) if isinstance(after_manifest, Mapping) else 'invalid'}")
    else:
        normalized_manifest = {Path(key).as_posix(): value for key, value in after_manifest.items()}
        for rel, value in documents.items():
            data = value if isinstance(value, bytes) else value.encode("utf-8")
            if normalized_manifest.get(rel) != sha256_bytes(data):
                audit.error("plan_after_hash", rel, repr(normalized_manifest.get(rel)))
    source_manifest = dict(getattr(plan, "source_manifest", {}))
    frozen_hashes = {item.workbook_sha256 for item in CATEGORIES} | set(COMMON_HASHES.values())
    manifest_values = {str(value) for value in source_manifest.values()}
    missing_source_hashes = sorted(frozen_hashes - manifest_values)
    if missing_source_hashes:
        audit.error("plan_source_manifest", GENERATOR_REL, repr(missing_source_hashes))
    metrics = dict(getattr(plan, "metrics", {}))
    source_metrics = dict(getattr(plan, "source_metrics", {}))
    after_metrics = dict(getattr(plan, "after_metrics", {}))
    audit.observations["plan"] = {
        "candidate_sha256": str(getattr(plan, "candidate_sha256", "")),
        "authorized_documents": len(documents), "second_pass_changes": len(second),
        "source_manifest": source_manifest, "source_metrics": source_metrics,
        "after_metrics": after_metrics, "metrics": metrics,
    }
    return View(root, documents)


class FragmentText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_data(self, data: str) -> None:
        self.values.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "br":
            self.values.append(" ")


def fragment_text(value: str) -> str:
    parser = FragmentText()
    parser.feed(value)
    parser.close()
    return norm("".join(parser.values))


def tag_attr(tag: str, name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(2)) if match else None


def meta_values(document: str, *, name: str | None = None, prop: str | None = None) -> list[str]:
    result: list[str] = []
    for tag in re.findall(r"<meta\b[^>]*>", document, re.IGNORECASE):
        key = tag_attr(tag, "name" if name is not None else "property")
        wanted = name if name is not None else prop
        if key is not None and wanted is not None and key.casefold() == wanted.casefold():
            result.append(tag_attr(tag, "content") or "")
    return result


def canonical_values(document: str) -> list[str]:
    result: list[str] = []
    for tag in re.findall(r"<link\b[^>]*>", document, re.IGNORECASE):
        rel = (tag_attr(tag, "rel") or "").casefold().split()
        if "canonical" in rel:
            result.append(tag_attr(tag, "href") or "")
    return result


def one_text(document: str, tag_name: str) -> list[str]:
    return [fragment_text(value) for value in re.findall(
        rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>", document, re.IGNORECASE | re.DOTALL,
    )]


def json_graph(document: str, audit: Audit, location: str) -> tuple[Mapping[str, Any], ...]:
    graphs: list[tuple[Mapping[str, Any], ...]] = []
    for opening, value in re.findall(
        r"(<script\b[^>]*\btype=[\"']application/ld\+json[\"'][^>]*>)(.*?)</script>",
        document, re.IGNORECASE | re.DOTALL,
    ):
        try:
            parsed = json.loads(value.replace("<\\/", "</"))
        except json.JSONDecodeError as exc:
            audit.error("jsonld_parse", location, repr(exc))
            continue
        if isinstance(parsed, Mapping) and isinstance(parsed.get("@graph"), list):
            graph = tuple(item for item in parsed["@graph"] if isinstance(item, Mapping))
            graphs.append(graph)
    if len(graphs) != 1:
        audit.error("jsonld_graph_count", location, f"actual={len(graphs)}")
        return ()
    return graphs[0]


def node_types(node: Mapping[str, Any]) -> tuple[str, ...]:
    value = node.get("@type")
    return (value,) if isinstance(value, str) else tuple(item for item in value or () if isinstance(item, str))


def graph_nodes(graph: Sequence[Mapping[str, Any]], wanted: str) -> list[Mapping[str, Any]]:
    return [item for item in graph if wanted in node_types(item)]


def one_node(graph: Sequence[Mapping[str, Any]], wanted: str, audit: Audit, location: str) -> Mapping[str, Any]:
    values = graph_nodes(graph, wanted)
    if len(values) != 1:
        audit.error("schema_type_count", location, f"type={wanted}, count={len(values)}")
        return {}
    return values[0]


def walk_json(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from walk_json(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk_json(item)


def validate_head(
    document: str,
    expected_url: str,
    expected_title: str,
    expected_h1: str,
    expected_meta: str | None,
    audit: Audit,
    location: str,
) -> None:
    if canonical_values(document) != [expected_url]:
        audit.error("canonical", location, repr(canonical_values(document)))
    if meta_values(document, prop="og:url") != [expected_url]:
        audit.error("og_url", location, repr(meta_values(document, prop="og:url")))
    titles = one_text(document, "title")
    if titles != [expected_title]:
        audit.error("html_title", location, repr(titles))
    h1s = one_text(document, "h1")
    if h1s != [norm(expected_h1)]:
        audit.error("h1", location, repr(h1s))
    if expected_meta is not None and meta_values(document, name="description") != [expected_meta]:
        audit.error("meta_description", location, repr(meta_values(document, name="description")))


def attr_hook_texts(document: str, tag_name: str, hook: str) -> tuple[str, ...]:
    pattern = re.compile(
        rf"<{tag_name}\b(?=[^>]*\b{re.escape(hook)}(?:\s|=|>))[^>]*>(.*?)</{tag_name}>",
        re.IGNORECASE | re.DOTALL,
    )
    return tuple(fragment_text(match.group(1)) for match in pattern.finditer(document))


def source_review_texts(document: str) -> tuple[str, ...]:
    matches = re.finditer(
        r"<(p|blockquote)\b(?=[^>]*\bdata-source-review=[\"'][^\"']+[\"'])[^>]*>(.*?)</\1>",
        document, re.IGNORECASE | re.DOTALL,
    )
    return tuple(fragment_text(match.group(2)) for match in matches)


def source_assets(root: Path, category: Category, locality: str, audit: Audit) -> tuple[str, str, str]:
    rel = Path("과목별학원") / category.subject_slug / locality / "index.html"
    path = root / rel
    if not path.is_file():
        audit.error("generic_source_missing", rel, "missing")
        return "", "", ""
    try:
        document = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        audit.error("generic_source_read", rel, repr(exc))
        return "", "", ""
    representative = meta_values(document, prop="og:image")
    body = re.findall(
        r'<figure\b[^>]*\bclass=["\'][^"\']*\bmath-visible-image\b[^"\']*["\'][^>]*>\s*<img\b[^>]*\bsrc=["\']([^"\']+)',
        document, re.IGNORECASE | re.DOTALL,
    )
    map_values = re.findall(
        r'<figure\b[^>]*\bclass=["\'][^"\']*\bmath-map-card\b[^"\']*["\'][^>]*>\s*<img\b[^>]*\bsrc=["\']([^"\']+)',
        document, re.IGNORECASE | re.DOTALL,
    )
    if len(representative) != 1 or len(body) != 1 or len(map_values) != 1:
        audit.error("generic_asset_hooks", rel, f"rep={len(representative)}, body={len(body)}, map={len(map_values)}")
        return "", "", ""
    return representative[0], html.unescape(body[0]), html.unescape(map_values[0])


def item_list_rows(node: Mapping[str, Any]) -> tuple[tuple[Any, str, str], ...]:
    result: list[tuple[Any, str, str]] = []
    value = node.get("itemListElement")
    if not isinstance(value, list):
        return ()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        result.append((item.get("position"), str(item.get("name", "")), str(item.get("url", item.get("item", "")))))
    return tuple(result)


def validate_parent(view: View, audit: Audit) -> None:
    location = PARENT_REL.as_posix()
    if not view.exists(PARENT_REL):
        audit.error("parent_missing", location, "missing")
        return
    document = view.text(PARENT_REL)
    validate_head(
        document, encoded_url("학년별학원"), "학년별학원 안내 | 와와학습코칭센터",
        one_text(document, "h1")[0] if len(one_text(document, "h1")) == 1 else "", None, audit, location,
    )
    hrefs = [html.unescape(item) for item in re.findall(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", document, re.IGNORECASE)]
    for label, slug in ALL_CATEGORY_LINKS:
        href = f"/학년별학원/{slug}/"
        if hrefs.count(href) != 1:
            audit.error("parent_category_link", location, f"{label}: count={hrefs.count(href)}")
    graph = json_graph(document, audit, location)
    item_list = one_node(graph, "ItemList", audit, location)
    page = one_node(graph, "CollectionPage", audit, location)
    organization = one_node(graph, "EducationalOrganization", audit, location)
    one_node(graph, "BreadcrumbList", audit, location)
    one_node(graph, "FAQPage", audit, location)
    rows = item_list_rows(item_list)
    if item_list.get("numberOfItems") != len(ALL_CATEGORY_LINKS) or len(rows) != len(ALL_CATEGORY_LINKS):
        audit.error("parent_item_list", location, f"number={item_list.get('numberOfItems')}, rows={len(rows)}")
    row_pairs = {(name, url) for _, name, url in rows}
    expected_pairs = {(label, encoded_url("학년별학원", slug)) for label, slug in ALL_CATEGORY_LINKS}
    if row_pairs != expected_pairs:
        audit.error("parent_item_list_values", location, f"missing={sorted(expected_pairs-row_pairs)}")
    has_part = page.get("hasPart")
    if not isinstance(has_part, list) or len(has_part) != len(ALL_CATEGORY_LINKS):
        audit.error("parent_has_part", location, f"actual={len(has_part) if isinstance(has_part, list) else 'invalid'}")
    knows = organization.get("knowsAbout")
    if not isinstance(knows, list) or any(category.label not in knows for category in CATEGORIES):
        audit.error("parent_knows_about", location, repr(knows))


def validate_category(view: View, category: Category, rows: Sequence[CommonRow], audit: Audit) -> None:
    location = category.category_rel.as_posix()
    if not view.exists(category.category_rel):
        audit.error("category_missing", location, "missing")
        return
    document = view.text(category.category_rel)
    expected_url = encoded_url("학년별학원", category.slug)
    validate_head(
        document, expected_url, f"{category.label} 371개 지역 안내 | 와와학습코칭센터",
        f"{category.label} 371개 지역 안내", None, audit, location,
    )
    main_tags = [tag for tag in re.findall(r"<main\b[^>]*>", document, re.IGNORECASE) if tag_attr(tag, "data-grade-directory") == category.hook]
    if len(main_tags) != 1:
        audit.error("category_main_hook", location, f"actual={len(main_tags)}")
    locality_values = tuple(html.unescape(value) for value in re.findall(
        r"<a\b(?=[^>]*\bdata-grade-locality=[\"']([^\"']+)[\"'])[^>]*>", document, re.IGNORECASE,
    ))
    expected_localities = tuple(row.locality for row in rows)
    if locality_values != expected_localities:
        audit.error("category_locality_order", location, f"actual={len(locality_values)}")
    for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
        if len(re.findall(rf"\b{hook}(?:\s|=|>)", document)) != 1:
            audit.error("category_search_hook", location, hook)
    graph = json_graph(document, audit, location)
    item_list = one_node(graph, "ItemList", audit, location)
    one_node(graph, "CollectionPage", audit, location)
    one_node(graph, "BreadcrumbList", audit, location)
    one_node(graph, "FAQPage", audit, location)
    item_rows = item_list_rows(item_list)
    expected_items = tuple(
        (index, f"{row.locality} {category.label}", encoded_url("학년별학원", category.slug, row.locality))
        for index, row in enumerate(rows, 1)
    )
    if item_list.get("numberOfItems") != EXPECTED_LOCALITIES or item_rows != expected_items:
        audit.error("category_item_list", location, f"number={item_list.get('numberOfItems')}, rows={len(item_rows)}")


def expected_audience(category: Category) -> str:
    return "초등학교 6학년(초6)" if category.grade == "초6" else "고등학교 2학년(고2)"


def validate_detail(
    view: View,
    root: Path,
    category: Category,
    manuscript: Manuscript,
    row: CommonRow,
    audit: Audit,
) -> Counter[str]:
    rel = detail_rel(category, row.locality)
    location = rel.as_posix()
    result: Counter[str] = Counter()
    if not view.exists(rel):
        audit.error("detail_missing", location, "missing")
        return result
    document = view.text(rel)
    expected_url = encoded_url("학년별학원", category.slug, row.locality)
    validate_head(
        document, expected_url, f"{manuscript.title} | 와와학습코칭센터",
        manuscript.title, manuscript.meta, audit, location,
    )
    main_tags = [tag for tag in re.findall(r"<main\b[^>]*>", document, re.IGNORECASE) if tag_attr(tag, "data-grade-page") == category.hook]
    supported = category.grade in row.grades[category.grade_column]
    expected_status = "supported" if supported else "unconfirmed-grade"
    if len(main_tags) != 1 or tag_attr(main_tags[0], "data-source-status") != expected_status:
        audit.error("detail_main_hook", location, f"count={len(main_tags)}, expected_status={expected_status}")
    article_tags = [tag for tag in re.findall(r"<article\b[^>]*>", document, re.IGNORECASE) if re.search(r"\bdata-manuscript(?:\s|=|>)", tag)]
    if len(article_tags) != 1:
        audit.error("detail_article_hook", location, f"actual={len(article_tags)}")
    else:
        tag = article_tags[0]
        expected_hash = manuscript.raw_sha256
        if (
            tag_attr(tag, "data-source-workbook-row") != str(manuscript.row_number)
            or tag_attr(tag, "data-source-cell-sha256") != expected_hash
            or tag_attr(tag, "data-manuscript-sha256") != expected_hash
        ):
            audit.error("detail_source_identity", location, tag)

    expected_headings = tuple(
        norm(f"{index}. {section.heading}" if manuscript.body_format == "numbered" else section.heading)
        for index, section in enumerate(manuscript.sections, 1)
    )
    rendered_headings = attr_hook_texts(document, "h2", "data-source-heading")
    if rendered_headings != expected_headings:
        audit.error("detail_source_headings", location, f"actual={len(rendered_headings)}, expected={len(expected_headings)}")
    expected_paragraphs = tuple(norm(value) for value in manuscript.intro) + tuple(
        norm(value) for section in manuscript.sections for value in section.paragraphs
    )
    rendered_paragraphs = attr_hook_texts(document, "p", "data-source-paragraph")
    if rendered_paragraphs != expected_paragraphs:
        audit.error("detail_source_paragraphs", location, f"actual={len(rendered_paragraphs)}, expected={len(expected_paragraphs)}")
    expected_questions = tuple(norm(f"{item.question_prefix} {item.question}") for item in manuscript.faqs)
    rendered_questions = attr_hook_texts(document, "summary", "data-source-question")
    if rendered_questions != expected_questions:
        audit.error("detail_source_questions", location, f"actual={len(rendered_questions)}, expected={len(expected_questions)}")
    expected_answers = tuple(norm(f"{item.answer_prefix} {item.answer}") for item in manuscript.faqs)
    rendered_answers = attr_hook_texts(document, "p", "data-source-answer")
    if rendered_answers != expected_answers:
        audit.error("detail_source_answers", location, f"actual={len(rendered_answers)}, expected={len(expected_answers)}")
    rendered_reviews = source_review_texts(document)
    expected_reviews = tuple(norm(value) for value in manuscript.reviews)
    if rendered_reviews != expected_reviews:
        audit.error("detail_source_reviews", location, f"actual={len(rendered_reviews)}, expected={len(expected_reviews)}")

    expected_schools = row.schools[category.school_column]
    rendered_schools = tuple(fragment_text(value) for value in re.findall(
        r"<span\b(?=[^>]*\bdata-source-school(?:\s|=|>))[^>]*>(.*?)</span>", document, re.IGNORECASE | re.DOTALL,
    ))
    if rendered_schools != expected_schools:
        audit.error("detail_school_chips", location, f"actual={rendered_schools!r}, expected={expected_schools!r}")
    school_tags = [tag for tag in re.findall(r"<div\b[^>]*>", document, re.IGNORECASE) if tag_attr(tag, "data-source-field") == category.school_hook]
    expected_school_status = "provided" if expected_schools else "missing"
    if (
        len(school_tags) != 1 or tag_attr(school_tags[0], "data-source-status") != expected_school_status
        or tag_attr(school_tags[0], "data-source-raw-schools") != " | ".join(expected_schools)
    ):
        audit.error("detail_school_hook", location, repr(school_tags))
    if re.search(r'data-source-field=["\'](?:middle-schools|high-schools|elementary-schools)["\']', document):
        school_hook_names = re.findall(r'data-source-field=["\']([^"\']+-schools)["\']', document)
        if school_hook_names != [category.school_hook]:
            audit.error("detail_school_hook_exclusive", location, repr(school_hook_names))

    grade_blocks = re.findall(
        r'<div\b(?=[^>]*\bdata-source-field=["\']grade["\'])[^>]*>.*?<dd>(.*?)</dd>.*?</div>',
        document, re.IGNORECASE | re.DOTALL,
    )
    grade_source = " · ".join(row.grades[category.grade_column]) if row.grades[category.grade_column] else "원자료 미기재"
    expected_grade_text = (
        f"{category.grade} 확인 · 전체 기재 학년: {grade_source}"
        if supported else f"{category.grade} 상담 확인 필요 · 전체 기재 학년: {grade_source}"
    )
    if len(grade_blocks) != 1 or fragment_text(grade_blocks[0]) != expected_grade_text:
        audit.error("detail_grade_source", location, repr([fragment_text(value) for value in grade_blocks]))

    representative, body_src, map_src = source_assets(root, category, row.locality, audit)
    if meta_values(document, prop="og:image") != [representative]:
        audit.error("detail_representative_image", location, repr(meta_values(document, prop="og:image")))
    body_images = [tag_attr(tag, "src") for tag in re.findall(r"<img\b[^>]*>", document, re.IGNORECASE) if tag_attr(tag, "data-image-role") == "body"]
    map_images = [tag_attr(tag, "src") for tag in re.findall(r"<img\b[^>]*>", document, re.IGNORECASE) if tag_attr(tag, "data-image-role") == "map"]
    if body_images != [body_src] or map_images != [map_src]:
        audit.error("detail_visible_images", location, f"body={body_images}, map={map_images}")

    graph = json_graph(document, audit, location)
    webpage = one_node(graph, "WebPage", audit, location)
    article = one_node(graph, "Article", audit, location)
    organization = one_node(graph, "EducationalOrganization", audit, location)
    one_node(graph, "LocalBusiness", audit, location)
    breadcrumb = one_node(graph, "BreadcrumbList", audit, location)
    faq_page = one_node(graph, "FAQPage", audit, location)
    if webpage.get("url") != expected_url or webpage.get("description") != manuscript.meta:
        audit.error("schema_webpage", location, repr((webpage.get("url"), webpage.get("description"))))
    expected_summary = "\n\n".join(manuscript.summaries)
    if article.get("headline") != manuscript.title or article.get("description") != expected_summary:
        audit.error("schema_article_source", location, repr((article.get("headline"), article.get("description"))))
    breadcrumb_rows = item_list_rows(breadcrumb)
    expected_breadcrumb = (
        (1, "홈", BASE_URL + "/"),
        (2, "학년별학원", encoded_url("학년별학원")),
        (3, category.label, encoded_url("학년별학원", category.slug)),
        (4, manuscript.title, expected_url),
    )
    if breadcrumb_rows != expected_breadcrumb:
        audit.error("schema_breadcrumb", location, repr(breadcrumb_rows))
    entities = faq_page.get("mainEntity")
    expected_faq_schema = tuple((item.question, item.answer) for item in manuscript.faqs)
    actual_faq_schema = tuple(
        (str(item.get("name", "")), str(item.get("acceptedAnswer", {}).get("text", "")))
        for item in entities or () if isinstance(item, Mapping) and isinstance(item.get("acceptedAnswer"), Mapping)
    )
    if actual_faq_schema != expected_faq_schema:
        audit.error("schema_faq_source", location, f"actual={len(actual_faq_schema)}, expected={len(expected_faq_schema)}")
    schema_names = [str(item.get("name", "")) for item in walk_json(graph)]
    if any(school not in schema_names for school in expected_schools):
        audit.error("schema_school_source", location, repr(expected_schools))
    services = graph_nodes(graph, "Service")
    offers = graph_nodes(graph, "Offer")
    if supported:
        if len(services) != 1 or len(offers) != 1:
            audit.error("supported_service_offer", location, f"service={len(services)}, offer={len(offers)}")
        else:
            audience = services[0].get("audience")
            if not isinstance(audience, Mapping) or audience.get("audienceType") != expected_audience(category):
                audit.error("service_audience", location, repr(audience))
            if offers[0].get("url") != row.fee_url:
                audit.error("offer_url", location, repr(offers[0].get("url")))
        makes_offer = organization.get("makesOffer")
        if not isinstance(makes_offer, list) or len(makes_offer) != 1:
            audit.error("organization_makes_offer", location, repr(makes_offer))
    else:
        if services or offers:
            audit.error("unconfirmed_service_offer", location, f"service={len(services)}, offer={len(offers)}")
        if any(key in node for node in walk_json(graph) for key in ("makesOffer", "offers")):
            audit.error("unconfirmed_offer_claim", location, "offer-bearing property present")

    result.update({
        "h2": len(rendered_headings), "paragraphs": len(rendered_paragraphs),
        "faq": len(rendered_questions), "reviews": len(rendered_reviews), "schools": len(rendered_schools),
        "supported": int(supported), "unconfirmed": int(not supported),
    })
    return result


def sitemap_blocks(document: str, audit: Audit, location: str) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    for block in RAW_URL_BLOCK.findall(document):
        locations = LOC.findall(block)
        lastmods = LASTMOD.findall(block)
        if len(locations) != 1 or len(lastmods) != 1:
            audit.error("sitemap_block", location, "malformed")
            continue
        result.append((html.unescape(locations[0]), html.unescape(lastmods[0]), block.replace("\r\n", "\n")))
    return tuple(result)


def validate_discovery(view: View, rows: Sequence[CommonRow], audit: Audit) -> None:
    if not view.exists(SITEMAP_REL) or not view.exists(LLMS_REL):
        audit.error("discovery_missing", "sitemap/llms", "missing")
        return
    sitemap = view.text(SITEMAP_REL)
    blocks = sitemap_blocks(sitemap, audit, SITEMAP_REL.as_posix())
    if len(blocks) != EXPECTED_FINAL_HTML:
        audit.error("sitemap_count", SITEMAP_REL, f"actual={len(blocks)}, expected={EXPECTED_FINAL_HTML}")
    prefix = blocks[:EXPECTED_BASE_HTML]
    location_hash = sha256_bytes("\n".join(item[0] for item in prefix).encode("utf-8"))
    block_hash = sha256_bytes("".join(item[2] for item in prefix).encode("utf-8"))
    if location_hash != EXPECTED_BASE_SITEMAP_LOCATION_SHA256 or block_hash != EXPECTED_BASE_SITEMAP_BLOCK_SHA256:
        audit.error("sitemap_base_prefix", SITEMAP_REL, f"locations={location_hash}, blocks={block_hash}")
    appended = blocks[EXPECTED_BASE_HTML:]
    expected_by_category = {
        category.key: (
            encoded_url("학년별학원", category.slug),
            *(encoded_url("학년별학원", category.slug, row.locality) for row in rows),
        )
        for category in CATEGORIES
    }
    appended_locations = tuple(item[0] for item in appended)
    expected_set = {url for values in expected_by_category.values() for url in values}
    if len(appended_locations) != EXPECTED_NEW_HTML or set(appended_locations) != expected_set:
        audit.error("sitemap_new_urls", SITEMAP_REL, f"actual={len(appended_locations)}, unique={len(set(appended_locations))}")
    for category in CATEGORIES:
        positions = [appended_locations.index(value) for value in expected_by_category[category.key] if value in appended_locations]
        if len(positions) != EXPECTED_LOCALITIES + 1 or positions != list(range(min(positions), min(positions) + EXPECTED_LOCALITIES + 1)):
            audit.error("sitemap_category_order", category.key, f"positions={positions[:3]}... count={len(positions)}")
    if any(lastmod != RELEASE_DATE for _, lastmod, _ in appended):
        audit.error("sitemap_new_lastmod", SITEMAP_REL, "new URL lastmod differs")
    all_locations = [item[0] for item in blocks]
    if len(all_locations) != len(set(all_locations)):
        audit.error("sitemap_duplicates", SITEMAP_REL, "duplicate loc")

    llms = view.text(LLMS_REL)
    if llms.count(LLMS_MARKER) != 1:
        audit.error("llms_marker", LLMS_REL, f"count={llms.count(LLMS_MARKER)}")
    parent_line = f"- 학년별학원: {BASE_URL}/학년별학원/"
    if llms.splitlines().count(parent_line) != 1:
        audit.error("llms_parent", LLMS_REL, f"count={llms.splitlines().count(parent_line)}")
    for label, slug in ALL_CATEGORY_LINKS:
        line = f"- {label}: {BASE_URL}/학년별학원/{slug}/"
        if llms.splitlines().count(line) != 1:
            audit.error("llms_category", LLMS_REL, f"{label}: count={llms.splitlines().count(line)}")
    audit.observations["discovery"] = {
        "sitemap_urls": len(blocks), "base_location_sha256": location_hash,
        "base_block_sha256": block_hash, "new_urls": len(appended),
        "new_lastmod": RELEASE_DATE,
    }


def manifest_hash(view: View, paths: Iterable[str]) -> str:
    return sha256_bytes("".join(
        rel + "\0" + sha256_bytes(view.bytes(rel)) + "\n" for rel in sorted(paths)
    ).encode("utf-8"))


def validate_rendered_tree(
    view: View,
    root: Path,
    rows: Sequence[CommonRow],
    manuscripts: Mapping[str, Sequence[Manuscript]],
    audit: Audit,
) -> None:
    expected_paths = expected_authorized_paths(rows)
    missing = [rel for rel in sorted(expected_paths) if not view.exists(rel)]
    if missing:
        audit.error("authorized_missing", root, repr(missing[:20]))
        return
    all_html = enumerate_html(root) | {rel for rel in view.overrides if rel.endswith(".html")}
    if len(all_html) != EXPECTED_FINAL_HTML:
        audit.error("final_html_count", root, f"actual={len(all_html)}, expected={EXPECTED_FINAL_HTML}")
    grade_html = {rel for rel in all_html if rel.startswith("학년별학원/")}
    if len(grade_html) != EXPECTED_FINAL_GRADE_HTML:
        audit.error("final_grade_html_count", root, f"actual={len(grade_html)}, expected={EXPECTED_FINAL_GRADE_HTML}")
    validate_parent(view, audit)
    row_by_locality = {item.locality: item for item in rows}
    rendered: dict[str, Mapping[str, int]] = {}
    for category in CATEGORIES:
        validate_category(view, category, rows, audit)
        totals: Counter[str] = Counter()
        for manuscript in manuscripts[category.key]:
            totals.update(validate_detail(view, root, category, manuscript, row_by_locality[manuscript.locality], audit))
        expected = {
            "h2": sum(key * value for key, value in category.h2_distribution.items()),
            "paragraphs": category.body_paragraphs,
            "faq": sum(key * value for key, value in category.faq_distribution.items()),
            "reviews": sum(key * value for key, value in category.review_distribution.items()),
            "schools": category.school_chips,
            "supported": category.supported,
            "unconfirmed": category.unconfirmed,
        }
        if dict(totals) != expected:
            audit.error("rendered_aggregate", category.key, f"actual={dict(totals)}, expected={expected}")
        rendered[category.key] = dict(totals)
    validate_discovery(view, rows, audit)
    new_html = expected_new_html_paths(rows)
    audit.observations["rendered"] = rendered
    audit.observations["release_manifests"] = {
        "authorized": manifest_hash(view, expected_paths),
        "new_html": manifest_hash(view, new_html),
        "all_html": manifest_hash(view, all_html),
    }


def compare_actual_and_projected(actual: View, projected: View, rows: Sequence[CommonRow], audit: Audit) -> None:
    different = [
        rel for rel in sorted(expected_authorized_paths(rows))
        if actual.exists(rel) and projected.exists(rel) and actual.bytes(rel) != projected.bytes(rel)
    ]
    if different:
        audit.error("actual_projection_parity", "authorized documents", repr(different[:20]))


def run_self_test(audit: Audit) -> None:
    try:
        assert encoded_url("학년별학원", "초6수학학원", "명일동") == (
            "https://wawa-center.kr/%ED%95%99%EB%85%84%EB%B3%84%ED%95%99%EC%9B%90/"
            "%EC%B4%886%EC%88%98%ED%95%99%ED%95%99%EC%9B%90/%EB%AA%85%EC%9D%BC%EB%8F%99/"
        )
        assert fragment_text("<span>Q1.</span> A &amp; B<br>C") == "Q1. A & B C"
        assert split_csv_tokens("A, B,A") == ("A", "B")
        assert len(SPECIAL_HEADINGS) == 15
        assert len(ALL_CATEGORY_LINKS) == 10
    except AssertionError as exc:
        audit.error("self_test", "auditor", repr(exc))


def default_inputs() -> tuple[Path, Mapping[str, Path], Path]:
    root = Path(__file__).resolve().parents[1]
    desktop = Path.home() / "Desktop"
    workbooks = {item.key: desktop / item.workbook_name for item in CATEGORIES}
    common = desktop / "홈페이지 정리" / "참고자료" / "공통자료"
    return root, workbooks, common


def run_audit(
    root: Path,
    workbook_paths: Mapping[str, Path],
    common: Path,
    mode: str,
    *,
    self_test: bool = False,
) -> Audit:
    audit = Audit()
    if self_test:
        run_self_test(audit)
    root = root.resolve()
    common = common.resolve()
    workbook_paths = {key: path.resolve() for key, path in workbook_paths.items()}
    if root.is_symlink() or not root.is_dir():
        audit.error("root", root, "must be a regular directory")
        return audit
    if set(workbook_paths) != set(CATEGORY_BY_KEY):
        audit.error("workbook_keys", "arguments", repr(sorted(workbook_paths)))
        return audit
    rows = load_common(common, audit)
    manuscripts: dict[str, tuple[Manuscript, ...]] = {}
    for category in CATEGORIES:
        cells = load_workbook_cells(category, workbook_paths[category.key], audit)
        manuscripts[category.key] = validate_source_contract(category, cells, rows, audit) if cells and rows else ()
    if any(len(manuscripts[key]) != EXPECTED_LOCALITIES for key in CATEGORY_BY_KEY):
        return audit
    if mode == "source":
        return audit
    state = materialization_state(root, rows, audit)
    audit.observations["materialization_state"] = state
    if mode == "actual":
        if state != "release":
            audit.hold("materialization_pending", "학년별학원", f"state={state}")
            return audit
        validate_rendered_tree(View(root), root, rows, manuscripts, audit)
        return audit
    if mode == "projected":
        projected = build_projected_view(root, workbook_paths, common, rows, audit)
        if projected is not None:
            validate_rendered_tree(projected, root, rows, manuscripts, audit)
        return audit
    if mode == "actual-release":
        if state != "release":
            audit.error("release_not_materialized", "학년별학원", f"state={state}")
            return audit
        actual = View(root)
        validate_rendered_tree(actual, root, rows, manuscripts, audit)
        projected = build_projected_view(root, workbook_paths, common, rows, audit)
        if projected is not None:
            validate_rendered_tree(projected, root, rows, manuscripts, audit)
            compare_actual_and_projected(actual, projected, rows, audit)
        return audit
    audit.error("mode", mode, "unsupported")
    return audit


def payload(audit: Audit) -> Mapping[str, Any]:
    return {
        "status": audit.status, "errors": audit.errors,
        "holds": audit.holds, "observations": audit.observations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    default_root, default_workbooks, default_common = default_inputs()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--workbook-elementary6-math", type=Path, default=default_workbooks["elementary6_math"])
    parser.add_argument("--workbook-elementary6-english", type=Path, default=default_workbooks["elementary6_english"])
    parser.add_argument("--workbook-high2-english", type=Path, default=default_workbooks["high2_english"])
    parser.add_argument("--common-dir", type=Path, default=default_common)
    parser.add_argument("--mode", choices=("source", "actual", "projected", "actual-release"), default="actual")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    workbooks = {
        "elementary6_math": args.workbook_elementary6_math,
        "elementary6_english": args.workbook_elementary6_english,
        "high2_english": args.workbook_high2_english,
    }
    audit = run_audit(args.root, workbooks, args.common_dir, args.mode, self_test=args.self_test)
    value = payload(audit)
    if args.json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{audit.status}: errors={len(audit.errors)}, holds={len(audit.holds)}")
        for finding in (*audit.errors, *audit.holds):
            print(f"- {finding['code']} [{finding['location']}]: {finding['message']}")
    return 1 if audit.errors else 2 if audit.holds else 0


if __name__ == "__main__":
    raise SystemExit(main())
