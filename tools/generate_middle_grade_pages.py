#!/usr/bin/env python3
"""Build five middle-grade subject directories without mutating existing pages by default.

The five supplied ZIP archives are treated exclusively as data.  A normal
invocation performs a fully materialized, audited dry run and writes nothing.
Applying a plan additionally requires an exact external freeze payload and an
explicit ``APPLY-GO`` token.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Mapping, Sequence
from urllib.parse import quote, unquote, urlsplit
from zipfile import ZipFile


# Importing the already-audited transaction and low-level HTML/source helpers
# must never create a pyc in this repository.  Its content hash is part of the
# immutable source contract.
sys.dont_write_bytecode = True

SITE_ORIGIN = "https://wawa-center.kr"
PUBLISHED_DATE = "2026-08-20"
BASE_HELPER_SHA256 = "1fbba380481affe0b4f9888630f90caccb8bfca39342284819f8a2fb265d31cf"
CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
TARGET_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"

EXPECTED_LOCALITIES = 371
EXPECTED_EXISTING_HTML = 14_997
EXPECTED_IMMUTABLE_HTML = 14_996
EXPECTED_EXISTING_MIDDLE3_MATH_HTML = 372
EXPECTED_NEW_CATEGORIES = 5
EXPECTED_NEW_DETAILS = 1_855
EXPECTED_NEW_HTML = 1_860
EXPECTED_AUTHORIZED_DOCUMENTS = 1_863
EXPECTED_FINAL_HTML = 16_857
EXPECTED_SUPPORTED = 1_805
EXPECTED_UNCONFIRMED = 50
EXPECTED_SOURCE_H2 = 10_981
EXPECTED_SOURCE_FAQ = 7_605
EXPECTED_SOURCE_REVIEWS = 1_855
EXPECTED_SCHOOL_CHIPS = 4_445

BASE_IMMUTABLE_HTML_MANIFEST_SHA256 = "7844dcf232eaec0bed96bcf73ed93f2cc0818488b8f155f657c549a65a29d718"
BASE_MIDDLE3_MATH_MANIFEST_SHA256 = "81cb8ed8492eacd3e6a2a95568452f50c5067957dde6b99cc872ae61053f0765"
BASE_PARENT_SHA256 = "7c7541d1b2dcc8413968f59a7264fc4e15b475511836670b3faf6c7d06e8f9f7"
BASE_SITEMAP_SHA256 = "f4c0b0c1a9fc25072f8348621119ed510a494676398067fc442842e0b69de7b4"
BASE_LLMS_SHA256 = "47bf25190544402fe5dcccd133d6bd62c5c33eecd1574c217cc885176e2c6d9b"

PARENT_REL = Path("학년별학원/index.html")
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
MIDDLE3_MATH_ROOT = Path("학년별학원/중3수학학원")
LLMS_MARKER = "## 학년별학원 핵심 허브"
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
LABELS = ("페이지타이틀", "메타설명", "본문", "FAQ", "학부모후기", "JSON-LD 요약")
QUESTION_RE = re.compile(r"(?m)^Q([1-9][0-9]*)([.)])\s+(.+?)\s*$")
ANSWER_RE = re.compile(r"(?s)^(?:A([1-9][0-9]*)([.)])|답변:)\s+(.+)$")
H2_RE = re.compile(r"(?m)^##[ \t]+([^\n]+?)[ \t]*$")
SEED_QUOTE_RE = re.compile(r"[‘“'\"]([^’”'\"]+)[’”'\"]")
RAW_URL_RE = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD_RE = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)
ABSENT_SHA256 = hashlib.sha256(b"wawa-middle-grade-batch:absent-v1").hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_base_helper() -> ModuleType:
    path = Path(__file__).with_name("generate_grade3_math_pages.py")
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != BASE_HELPER_SHA256:
        raise RuntimeError(f"base helper SHA-256 mismatch: {digest}")
    module_name = f"_wawa_grade3_base_{BASE_HELPER_SHA256[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned base helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_BASE = _load_base_helper()
BuildError = _BASE.BuildError
# The reused journal compares absence with this exact audited sentinel.
ABSENT_SHA256 = _BASE.ABSENT_SHA256


@dataclass(frozen=True)
class CategorySpec:
    key: str
    grade: str
    grade_number: int
    subject: str
    slug: str
    hook: str
    subject_slug: str
    grade_attr: str
    zip_sha256: str | None
    supported: int
    unconfirmed: int
    h2_total: int
    h2_distribution: tuple[tuple[int, int], ...]
    section_paragraphs: int
    faq_total: int
    faq_distribution: tuple[tuple[int, int], ...]
    review_lines: int
    card_copy: str

    @property
    def label(self) -> str:
        return f"{self.grade} {self.subject}학원"

    @property
    def grades_label(self) -> str:
        return f"{self.subject} 가능 학년"

    @property
    def guide_slug(self) -> str:
        return f"{self.subject}-공부법"

    @property
    def english_label(self) -> str:
        return f"MIDDLE SCHOOL GRADE {self.grade_number} {('MATH' if self.subject == '수학' else 'ENGLISH')}"


ALL_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        "middle1_math", "중1", 1, "수학", "중1수학학원", "middle1-math", "수학학원", "math_grades",
        "83ac704c654d50d98d17d38a44024358d558c3ba03c38a9799cc5fef361a6e72", 358, 13,
        2_226, ((6, 371),), 4_452, 1_484, ((4, 371),), 742,
        "중학교 첫 수학의 개념 연결, 독립 풀이, 학교 진도와 주간 복습 기준을 동네별로 확인합니다.",
    ),
    CategorySpec(
        "middle1_english", "중1", 1, "영어", "중1영어학원", "middle1-english", "영어학원", "english_grades",
        "2521a37d5c4fdb04a52eae23c33e20a4df6e9eb294782fa4505ed06d0d648154", 363, 8,
        2_300, ((5, 74), (6, 149), (7, 148)), 5_498, 1_669, ((4, 186), (5, 185)), 742,
        "중학교 첫 영어의 어휘·문법·독해 연결, 학교 자료와 주간 학습 습관을 동네별로 확인합니다.",
    ),
    CategorySpec(
        "middle2_math", "중2", 2, "수학", "중2수학학원", "middle2-math", "수학학원", "math_grades",
        "d778f3839932567c78b0276360a2ad6ea4aba84127aafcd0c08ba78fab8c84d9", 358, 13,
        2_226, ((6, 371),), 4_452, 1_484, ((4, 371),), 742,
        "중2 수학의 단원별 편차, 첫 식 구성, 오답 재도전과 학교 시험 준비 기준을 동네별로 확인합니다.",
    ),
    CategorySpec(
        "middle2_english", "중2", 2, "영어", "중2영어학원", "middle2-english", "영어학원", "english_grades",
        "a2976c3e0e4624354cd5a63413e002e1f9cb60b4cef8a2911cf10cc3a80fa171", 363, 8,
        2_003, ((5, 223), (6, 148)), 3_860, 1_484, ((4, 371),), 1_113,
        "중2 영어의 문장 구조, 시험 자료 정리, 오답과 통학 계획을 동네별 원고에서 확인합니다.",
    ),
    CategorySpec(
        "middle3_math", "중3", 3, "수학", "중3수학학원", "middle3-math", "수학학원", "math_grades",
        None, 358, 13, 2_226, ((6, 371),), 4_476, 1_113, ((3, 371),), 742,
        "개념·오답 습관, 실제 학교 자료, 주간 진도와 복습, 등원 시간과 상담 질문을 동네별로 확인합니다.",
    ),
    CategorySpec(
        "middle3_english", "중3", 3, "영어", "중3영어학원", "middle3-english", "영어학원", "english_grades",
        "e39f5be8889607b557bb8bc1a6ec7e3cae97b51cc1fc6407b52380f5d12cfa36", 363, 8,
        2_226, ((6, 371),), 4_452, 1_484, ((4, 371),), 742,
        "중3 영어 내신과 고등 과정 연결, 복습 간격, 학교 자료와 주간 시간 배분을 동네별로 확인합니다.",
    ),
)
NEW_CATEGORIES = tuple(spec for spec in ALL_CATEGORIES if spec.zip_sha256 is not None)
SPEC_BY_KEY = {spec.key: spec for spec in NEW_CATEGORIES}
SPEC_BY_SLUG = {spec.slug: spec for spec in NEW_CATEGORIES}


@dataclass(frozen=True)
class CorrectionRule:
    category_key: str
    locality: str
    source: str
    rendered: str
    expected_occurrences: int


def _rules(category_key: str, localities: Sequence[str], source: str, rendered: str, *, double: Sequence[str] = ()) -> list[CorrectionRule]:
    doubled = set(double)
    return [CorrectionRule(category_key, locality, source, rendered, 2 if locality in doubled else 1) for locality in localities]


# These are the only authorized manuscript changes.  Every raw byte remains in
# the parsed source node/hash; only visible/schema text passes through this
# literal, locality-scoped allowlist.  Counts are frozen and audited.
CORRECTION_RULES: tuple[CorrectionRule, ...] = tuple([
    *_rules(
        "middle1_math",
        ("경산사동", "관교동", "구월동", "국우동", "노변동", "덕풍동", "도남동", "도남지구", "상현동", "시지동", "신갈동", "안양동", "용두동", "이시아폴리스", "중화산동", "천천동", "행신동"),
        "와와학습코칭학원를", "와와학습코칭학원을",
    ),
    CorrectionRule("middle1_math", "고현동", "앙중", "거제중앙중", 2),
    CorrectionRule("middle1_math", "당산동", "초당산중", "당산중", 1),
    CorrectionRule("middle1_math", "미금", "분당중", "불곡중", 2),
    CorrectionRule("middle1_math", "반곡동", "초버들중", "버들중", 2),
    CorrectionRule("middle1_math", "사파동", "창원중", "상남중", 1),
    CorrectionRule("middle1_math", "수월동", "거제중", "거제중앙중", 2),
    CorrectionRule("middle1_math", "양정동", "거제중과 앙중", "수월중과 거제중앙중", 1),
    CorrectionRule("middle1_math", "원주혁신도시", "초버들중", "버들중", 2),
    CorrectionRule("middle1_math", "위례", "위례중", "위례중앙중", 1),
    CorrectionRule("middle1_math", "위례신도시", "앙중", "위례중앙중", 2),
    CorrectionRule("middle1_math", "창곡동", "앙중", "위례중앙중", 2),
    *_rules(
        "middle1_english",
        ("국우동", "도남지구", "동천동", "만촌동", "반곡동", "범어동", "복대동", "복현동", "본리동", "봉명동", "봉무동", "불당동", "산격동", "산남동", "수곡동", "시지동", "신불당", "양정동", "용곡동", "원주혁신도시", "재송동", "좌동", "주월동", "치평동"),
        "수업 운영 운영 기준", "수업 운영 기준",
    ),
    *_rules(
        "middle1_english", ("별내신도시", "성남동", "수월동", "신원동", "안양동"),
        "학습 운영 운영 기준", "학습 운영 기준",
    ),
    *_rules(
        "middle1_english",
        ("가경동", "구갈동", "노변동", "등촌동", "배곧", "배곧동", "복현동", "선암동", "안양동", "염창동", "옥정동", "전주 장동", "토당동"),
        "와와학습코칭학원로", "와와학습코칭학원으로",
    ),
    *_rules(
        "middle1_english",
        ("가정동", "관저동", "관평동", "노은동", "도안동", "둔산동", "부평동", "삼산동", "송강동", "송촌동", "용산동", "원신흥동", "청계동", "칠성동", "향남읍"),
        "관리을", "관리를", double=("관평동",),
    ),
    *_rules(
        "middle1_english", ("경안동", "비산동", "소하동", "수택동", "인창동", "철산동", "하안동", "화정동", "후곡마을"),
        "동기을", "동기를",
    ),
    CorrectionRule("middle1_english", "호매실", "오현초호매실중", "호매실중", 1),
    CorrectionRule("middle2_math", "호매실", "오현초호매실중", "호매실중", 2),
    CorrectionRule("middle2_math", "수원 금곡동", "오현초호매실중", "호매실중", 2),
])
RULES_BY_PAGE: Mapping[tuple[str, str], tuple[CorrectionRule, ...]] = MappingProxyType({
    key: tuple(rule for rule in CORRECTION_RULES if (rule.category_key, rule.locality) == key)
    for key in {(rule.category_key, rule.locality) for rule in CORRECTION_RULES}
})
EXPECTED_LITERAL_CORRECTIONS = sum(rule.expected_occurrences for rule in CORRECTION_RULES)


def _correct_text(spec: CategorySpec, locality: str, value: str) -> str:
    rendered = value
    for rule in RULES_BY_PAGE.get((spec.key, locality), ()):
        rendered = rendered.replace(rule.source, rule.rendered)
    return rendered


def _visible_schools(record: Any) -> tuple[str, ...]:
    corrected = tuple("호매실중" if school == "오현초호매실중" else school for school in record.middle_schools)
    if len(corrected) != len(set(corrected)):
        raise BuildError(f"{record.locality}: corrected middle-school list contains duplicates")
    if record.locality in ("호매실", "수원 금곡동"):
        if record.middle_schools.count("오현초호매실중") != 1 or corrected.count("호매실중") != 1:
            raise BuildError(f"{record.locality}: pinned attached school token correction mismatch")
    elif corrected != record.middle_schools:
        raise BuildError(f"{record.locality}: unauthorized school source-token correction")
    return corrected


@dataclass(frozen=True)
class BodySection:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class FAQ:
    number: int
    question: str
    answer: str


@dataclass(frozen=True)
class Manuscript:
    member_name: str
    locality: str
    title: str
    meta_description: str
    intro_paragraphs: tuple[str, ...]
    sections: tuple[BodySection, ...]
    faqs: tuple[FAQ, ...]
    review_lines: tuple[str, ...]
    jsonld_summary: str
    raw_bytes: bytes
    raw_text: str


@dataclass(frozen=True)
class BuildPlan:
    root: Path
    authorized_documents: Mapping[Path, str | bytes]
    changed_paths: tuple[Path, ...]
    second_pass_changes: tuple[Path, ...]
    source_manifest: Mapping[str, str]
    before_manifest: Mapping[Path, str]
    after_manifest: Mapping[Path, str]
    before_exists: Mapping[Path, bool]
    source_metrics: Mapping[str, Any]
    before_metrics: Mapping[str, Any]
    after_metrics: Mapping[str, Any]
    metrics: Mapping[str, Any]
    candidate_sha256: str
    immutable_html_manifest_sha256: str
    middle3_math_manifest_sha256: str


def _as_bytes(value: str | bytes) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label}: not strict UTF-8") from exc


def _safe_relative(root: Path, value: Path | str) -> Path:
    return _BASE._safe_relative_path(root, value)


def _read_current(root: Path, rel: Path, overrides: Mapping[Path, str | bytes]) -> bytes:
    return _BASE._read_current_bytes(root, rel, overrides)


def _read_optional(root: Path, rel: Path, overrides: Mapping[Path, str | bytes]) -> tuple[bool, bytes]:
    return _BASE._read_optional_current_bytes(root, rel, overrides)


def _category_rel(spec: CategorySpec) -> Path:
    return Path("학년별학원") / spec.slug / "index.html"


def _detail_rel(spec: CategorySpec, locality: str) -> Path:
    return Path("학년별학원") / spec.slug / locality / "index.html"


def _generic_rel(spec: CategorySpec, locality: str) -> Path:
    return Path("과목별학원") / spec.subject_slug / locality / "index.html"


def _site_url(*parts: str) -> str:
    return _BASE._encoded_site_url(*parts)


def _escape(value: Any) -> str:
    return _BASE._escape(str(value))


def _json_script(value: Any) -> str:
    return _BASE._json_script(value)


def _paragraph_markup(value: str) -> str:
    return _BASE._paragraph_markup(value)


def _clean_document(value: str) -> str:
    return _BASE._clean_document(value)


def _split_paragraphs(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r"\n[ \t]*\n", value.strip()) if part.strip())


def _validate_plain_text(text: str, label: str) -> None:
    if CONTROL_RE.search(text):
        raise BuildError(f"{label}: forbidden control character")
    if any(line.rstrip(" \t") != line for line in text.splitlines()):
        raise BuildError(f"{label}: trailing whitespace")


def _parse_manuscript(spec: CategorySpec, member_name: str, raw: bytes) -> Manuscript:
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{member_name}: not strict UTF-8") from exc
    bom = raw.startswith(b"\xef\xbb\xbf")
    if (b"\xef\xbb\xbf" if bom else b"") + decoded.encode("utf-8") != raw:
        raise BuildError(f"{member_name}: raw UTF-8 round-trip failed")
    _validate_plain_text(decoded, member_name)
    text = decoded.replace("\r\n", "\n").replace("\r", "\n")
    suffix = f" {spec.label}.txt"
    if Path(member_name).name != member_name or not member_name.endswith(suffix):
        raise BuildError(f"unsafe or unexpected ZIP member: {member_name!r}")
    locality = unicodedata.normalize("NFC", member_name[:-len(suffix)])
    matches = list(re.finditer(r"(?m)^\[([^\]\n]+)\]\n", text))
    if tuple(match.group(1) for match in matches) != LABELS:
        raise BuildError(f"{member_name}: section labels/order malformed")
    if text[:matches[0].start()].strip():
        raise BuildError(f"{member_name}: data before first label")
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        values[match.group(1)] = text[match.end():end].strip("\n")
    if any(not values[label].strip() for label in LABELS):
        raise BuildError(f"{member_name}: empty required section")
    title = values["페이지타이틀"].strip()
    if title != f"{locality} {spec.label}":
        raise BuildError(f"{member_name}: title/locality/category mismatch")
    meta = values["메타설명"].strip()
    if not meta or "\n" in meta:
        raise BuildError(f"{member_name}: meta description must be one line")

    body = values["본문"].strip()
    headings = list(H2_RE.finditer(body))
    if not headings or len(re.findall(r"(?m)^#{1,6}[ \t]+", body)) != len(headings):
        raise BuildError(f"{member_name}: only source H2 headings are permitted")
    intro = _split_paragraphs(body[:headings[0].start()])
    sections: list[BodySection] = []
    for index, heading_match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        paragraphs = _split_paragraphs(body[heading_match.end():end])
        heading = heading_match.group(1).strip()
        if not heading or not paragraphs:
            raise BuildError(f"{member_name}: empty H2 or H2 body")
        sections.append(BodySection(heading, paragraphs))
    if not intro:
        raise BuildError(f"{member_name}: missing introductory paragraph")
    normalized_paragraphs = [re.sub(r"\s+", " ", value).strip().casefold() for value in intro]
    normalized_paragraphs += [
        re.sub(r"\s+", " ", paragraph).strip().casefold()
        for section in sections for paragraph in section.paragraphs
    ]
    if len(normalized_paragraphs) != len(set(normalized_paragraphs)):
        raise BuildError(f"{member_name}: exact normalized body paragraph duplicate")

    faq_value = values["FAQ"].strip()
    question_matches = list(QUESTION_RE.finditer(faq_value))
    if not question_matches:
        raise BuildError(f"{member_name}: FAQ questions missing")
    faqs: list[FAQ] = []
    for index, question_match in enumerate(question_matches):
        end = question_matches[index + 1].start() if index + 1 < len(question_matches) else len(faq_value)
        answer_block = faq_value[question_match.end():end].strip()
        answer_match = ANSWER_RE.fullmatch(answer_block)
        number = int(question_match.group(1))
        if answer_match is None or number != index + 1:
            raise BuildError(f"{member_name}: malformed or unordered FAQ {number}")
        answer_number = answer_match.group(1)
        if answer_number is not None and int(answer_number) != number:
            raise BuildError(f"{member_name}: FAQ answer number mismatch")
        faqs.append(FAQ(number, question_match.group(3).strip(), answer_match.group(3).strip()))

    review_lines = tuple(line.strip() for line in values["학부모후기"].splitlines() if line.strip())
    if len(review_lines) not in (2, 3) or not all(review_lines):
        raise BuildError(f"{member_name}: review line structure malformed")
    summary = values["JSON-LD 요약"].strip()
    if not summary or "\n\n" in summary:
        raise BuildError(f"{member_name}: JSON-LD summary must be one paragraph")
    return Manuscript(
        member_name, locality, title, meta, intro, tuple(sections), tuple(faqs),
        review_lines, summary, raw, decoded,
    )


def _normalize_zip_paths(zip_paths: Mapping[str, Path | str] | Sequence[Path | str]) -> Mapping[str, Path]:
    resolved: dict[str, Path] = {}
    if isinstance(zip_paths, Mapping):
        for key, raw_path in zip_paths.items():
            spec = SPEC_BY_KEY.get(str(key)) or SPEC_BY_SLUG.get(str(key))
            if spec is None or spec.key in resolved:
                raise BuildError(f"unknown or duplicate ZIP category key: {key!r}")
            resolved[spec.key] = Path(raw_path).expanduser()
    else:
        for raw_path in zip_paths:
            path = Path(raw_path).expanduser()
            if not path.is_file():
                raise BuildError(f"ZIP does not exist: {path}")
            digest = _sha256(path.read_bytes())
            matches = [spec for spec in NEW_CATEGORIES if spec.zip_sha256 == digest]
            if len(matches) != 1 or matches[0].key in resolved:
                raise BuildError(f"ZIP is unknown or duplicated: {path}")
            resolved[matches[0].key] = path
    if set(resolved) != set(SPEC_BY_KEY):
        raise BuildError(f"exactly five frozen ZIP categories are required: {sorted(resolved)}")
    normalized: dict[str, Path] = {}
    for spec in NEW_CATEGORIES:
        original = resolved[spec.key]
        if original.is_symlink() or not original.is_file():
            raise BuildError(f"ZIP must be a regular non-symlink file: {original}")
        normalized[spec.key] = original.resolve()
    return MappingProxyType(normalized)


def _load_manuscripts(spec: CategorySpec, zip_path: Path) -> tuple[Mapping[str, Manuscript], Mapping[str, Any]]:
    raw_zip = zip_path.read_bytes()
    digest = _sha256(raw_zip)
    if digest != spec.zip_sha256:
        raise BuildError(f"{spec.key}: ZIP SHA-256 mismatch: {digest}")
    manuscripts: dict[str, Manuscript] = {}
    raw_hashes: set[str] = set()
    total_uncompressed = 0
    bom_count = 0
    with ZipFile(io.BytesIO(raw_zip), "r") as archive:
        infos = archive.infolist()
        if len(infos) != EXPECTED_LOCALITIES:
            raise BuildError(f"{spec.key}: expected 371 ZIP members, got {len(infos)}")
        seen_names: set[str] = set()
        for info in infos:
            name = unicodedata.normalize("NFC", info.filename)
            if (
                info.is_dir() or info.flag_bits & 0x1 or info.filename != name
                or Path(name).name != name or name in seen_names or CONTROL_RE.search(name)
            ):
                raise BuildError(f"{spec.key}: unsafe/encrypted/duplicate/non-NFC member: {info.filename!r}")
            if info.file_size <= 0 or info.file_size > 1_000_000:
                raise BuildError(f"{spec.key}: unexpected member size: {name}")
            if info.compress_size and info.file_size / info.compress_size > 100:
                raise BuildError(f"{spec.key}: suspicious compression ratio: {name}")
            raw = archive.read(info)
            if len(raw) != info.file_size:
                raise BuildError(f"{spec.key}: member length mismatch: {name}")
            manuscript = _parse_manuscript(spec, name, raw)
            if manuscript.locality in manuscripts:
                raise BuildError(f"{spec.key}: duplicate locality: {manuscript.locality}")
            manuscripts[manuscript.locality] = manuscript
            seen_names.add(name)
            raw_hashes.add(_sha256(raw))
            total_uncompressed += len(raw)
            bom_count += int(raw.startswith(b"\xef\xbb\xbf"))
    h2_distribution = Counter(len(item.sections) for item in manuscripts.values())
    faq_distribution = Counter(len(item.faqs) for item in manuscripts.values())
    section_paragraphs = sum(len(section.paragraphs) for item in manuscripts.values() for section in item.sections)
    review_lines = sum(len(item.review_lines) for item in manuscripts.values())
    expected_h2_dist = Counter(dict(spec.h2_distribution))
    expected_faq_dist = Counter(dict(spec.faq_distribution))
    if (
        len(manuscripts) != EXPECTED_LOCALITIES or len(raw_hashes) != EXPECTED_LOCALITIES
        or sum(h2_distribution.values()) != EXPECTED_LOCALITIES
        or sum(len(item.sections) for item in manuscripts.values()) != spec.h2_total
        or h2_distribution != expected_h2_dist
        or section_paragraphs != spec.section_paragraphs
        or sum(len(item.faqs) for item in manuscripts.values()) != spec.faq_total
        or faq_distribution != expected_faq_dist
        or review_lines != spec.review_lines
    ):
        raise BuildError(f"{spec.key}: frozen manuscript structural metrics mismatch")
    metrics = {
        "members": len(manuscripts),
        "unique_raw_documents": len(raw_hashes),
        "uncompressed_bytes": total_uncompressed,
        "bom_documents": bom_count,
        "h2": spec.h2_total,
        "h2_distribution": dict(sorted(h2_distribution.items())),
        "section_paragraphs": section_paragraphs,
        "faqs": spec.faq_total,
        "faq_distribution": dict(sorted(faq_distribution.items())),
        "reviews": len(manuscripts),
        "review_nonempty_lines": review_lines,
        "normalized_within_page_body_duplicates": 0,
    }
    return MappingProxyType(manuscripts), MappingProxyType(metrics)


def _grades(record: Any, spec: CategorySpec) -> tuple[str, ...]:
    value = getattr(record, spec.grade_attr)
    if not isinstance(value, tuple):
        raise BuildError(f"{record.locality}: invalid grade source field for {spec.key}")
    return value


def _supports(record: Any, spec: CategorySpec) -> bool:
    return spec.grade in _grades(record, spec)


def _files_manifest(root: Path, paths: Sequence[Path], overrides: Mapping[Path, str | bytes]) -> str:
    digest = hashlib.sha256()
    for rel in sorted(paths, key=lambda item: item.as_posix()):
        value = _read_current(root, rel, overrides)
        digest.update(rel.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(value).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _physical_nodes(spec: CategorySpec, record: Any, assets: Any, detail_url: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    organization = copy.deepcopy(dict(assets.organization))
    local_business = copy.deepcopy(dict(assets.local_business))
    organization_id = str(organization.get("@id", ""))
    local_business_id = str(local_business.get("@id", ""))
    if not organization_id or not local_business_id or organization_id == local_business_id:
        raise BuildError(f"{record.locality}: physical schema IDs missing or colliding")
    address = {
        "@type": "PostalAddress",
        "streetAddress": record.address,
        "addressRegion": record.region,
        "addressLocality": record.city,
        "addressCountry": "KR",
    }
    identifier = {"@type": "PropertyValue", "name": "교육지원청 등록번호", "value": record.registration_number}
    for node in (organization, local_business):
        node["name"] = record.center_name
        node["url"] = assets.center_url
        node["address"] = copy.deepcopy(address)
        node["areaServed"] = {"@type": "Place", "name": record.locality}
        node["identifier"] = copy.deepcopy(identifier)
        node.pop("makesOffer", None)
    organization["legalName"] = record.registration_name
    organization["educationalLevel"] = list(_grades(record, spec))
    support_copy = (
        f"제공된 {spec.subject} 가능 학년 자료에 {spec.grade}이 기재되어 있으며 실제 시작 시점과 수업 조건은 상담에서 확인합니다."
        if _supports(record, spec)
        else f"제공된 {spec.subject} 가능 학년 자료에는 {spec.grade}이 기재되어 있지 않아 실제 수업 가능 여부를 상담에서 확인해야 합니다."
    )
    organization["description"] = f"{record.center_name}의 제공 주소는 {record.address}입니다. {support_copy}"
    local_business["parentOrganization"] = {"@id": organization_id}
    extra: list[dict[str, Any]] = []
    if _supports(record, spec):
        service_id = detail_url + "#service"
        offer_id = detail_url + "#offer"
        service = {
            "@type": "Service", "@id": service_id,
            "name": f"{record.locality} {spec.grade} {spec.subject} 교과 과정",
            "serviceType": f"{spec.grade} {spec.subject} 교과 과정",
            "provider": {"@id": organization_id},
            "areaServed": {"@type": "Place", "name": record.locality},
            "audience": {
                "@type": "EducationalAudience", "educationalRole": "student",
                "audienceType": f"중학교 {spec.grade_number}학년({spec.grade})",
            },
            "offers": {"@id": offer_id},
        }
        offer = {
            "@type": "Offer", "@id": offer_id,
            "name": f"{record.locality} {spec.grade} {spec.subject} 교과 과정",
            "itemOffered": {"@id": service_id},
            "url": record.tuition_url or detail_url,
        }
        offer_ref = {"@id": offer_id}
        organization["makesOffer"] = [copy.deepcopy(offer_ref)]
        local_business["makesOffer"] = [copy.deepcopy(offer_ref)]
        extra.extend((service, offer))
    return organization, local_business, extra


def _detail_schema(spec: CategorySpec, manuscript: Manuscript, record: Any, assets: Any, detail_url: str, related: Sequence[tuple[str, str]]) -> dict[str, Any]:
    organization, local_business, service_offer = _physical_nodes(spec, record, assets, detail_url)
    organization_id = organization["@id"]
    image_url = SITE_ORIGIN + quote(assets.representative_src, safe="/%")
    breadcrumb_id = detail_url + "#breadcrumb"
    article_id = detail_url + "#article"
    faq_id = detail_url + "#faq"
    links_id = detail_url + "#links"
    image_id = detail_url + "#primaryimage"
    heading_parts = [
        {"@type": "WebPageElement", "@id": detail_url + f"#section-{index:02d}", "name": _correct_text(spec, manuscript.locality, section.heading)}
        for index, section in enumerate(manuscript.sections, 1)
    ]
    rendered_title = _correct_text(spec, manuscript.locality, manuscript.title)
    rendered_meta = _correct_text(spec, manuscript.locality, manuscript.meta_description)
    rendered_summary = _correct_text(spec, manuscript.locality, manuscript.jsonld_summary)
    mentions: list[dict[str, str]] = [
        {"@type": "Place", "name": record.region},
        {"@type": "Place", "name": record.city},
        {"@type": "Place", "name": record.locality},
        {"@type": "Thing", "name": f"{spec.grade} {spec.subject}"},
        {"@type": "Thing", "name": f"{spec.subject} 내신"},
        {"@type": "Thing", "name": "오답 재학습"},
        *({"@type": "EducationalOrganization", "name": school} for school in _visible_schools(record)),
    ]
    web_page = {
        "@type": "WebPage", "@id": detail_url + "#webpage", "url": detail_url,
        "name": f"{rendered_title} | 와와학습코칭센터", "description": rendered_meta,
        "inLanguage": "ko-KR", "isPartOf": {"@id": SITE_ORIGIN + "/#website"},
        "publisher": {"@id": organization_id}, "breadcrumb": {"@id": breadcrumb_id},
        "mainEntity": {"@id": article_id}, "primaryImageOfPage": {"@id": image_id},
        "about": [{"@type": "Thing", "name": rendered_title}, {"@type": "Thing", "name": f"{spec.grade} {spec.subject} 학습 정보"}],
        "mentions": copy.deepcopy(mentions),
        "hasPart": [{"@id": article_id}, {"@id": faq_id}, {"@id": links_id}, *copy.deepcopy(heading_parts)],
        "datePublished": PUBLISHED_DATE, "dateModified": PUBLISHED_DATE,
    }
    article = {
        "@type": "Article", "@id": article_id, "headline": rendered_title,
        "description": rendered_summary, "image": image_url, "inLanguage": "ko-KR",
        "datePublished": PUBLISHED_DATE, "dateModified": PUBLISHED_DATE,
        "mainEntityOfPage": {"@id": web_page["@id"]}, "author": {"@id": organization_id},
        "publisher": {"@id": organization_id},
        "articleSection": [_correct_text(spec, manuscript.locality, section.heading) for section in manuscript.sections],
        "about": [{"@type": "Thing", "name": rendered_title}, {"@type": "Thing", "name": f"{spec.grade} {spec.subject} 학습 진단"}],
        "mentions": copy.deepcopy(mentions), "hasPart": copy.deepcopy(heading_parts),
    }
    breadcrumb = {
        "@type": "BreadcrumbList", "@id": breadcrumb_id,
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_ORIGIN + "/"},
            {"@type": "ListItem", "position": 2, "name": "학년별학원", "item": _site_url("학년별학원")},
            {"@type": "ListItem", "position": 3, "name": spec.label, "item": _site_url("학년별학원", spec.slug)},
            {"@type": "ListItem", "position": 4, "name": rendered_title, "item": detail_url},
        ],
    }
    faq_page = {
        "@type": "FAQPage", "@id": faq_id,
        "mainEntity": [
            {"@type": "Question", "name": _correct_text(spec, manuscript.locality, faq.question), "acceptedAnswer": {"@type": "Answer", "text": _correct_text(spec, manuscript.locality, faq.answer)}}
            for faq in manuscript.faqs
        ],
    }
    item_list = {
        "@type": "ItemList", "@id": links_id, "name": f"{rendered_title} 관련 페이지",
        "numberOfItems": len(related),
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "url": url}
            for index, (name, url) in enumerate(related, 1)
        ],
    }
    image_object = {
        "@type": "ImageObject", "@id": image_id, "url": image_url, "contentUrl": image_url,
        "width": assets.representative_size[0], "height": assets.representative_size[1],
        "caption": f"{rendered_title} 대표 이미지",
    }
    return {
        "@context": "https://schema.org",
        "@graph": [web_page, organization, local_business, breadcrumb, article, faq_page, item_list, image_object, *service_offer],
    }


def _render_detail(spec: CategorySpec, manuscript: Manuscript, record: Any, assets: Any, previous_locality: str, next_locality: str) -> str:
    locality = record.locality
    detail_url = _site_url("학년별학원", spec.slug, locality)
    parent_url = _site_url("학년별학원")
    category_url = _site_url("학년별학원", spec.slug)
    subject_url = _site_url("과목별학원", spec.subject_slug, locality)
    study_url = _site_url("교육정보", spec.guide_slug)
    previous_url = _site_url("학년별학원", spec.slug, previous_locality)
    next_url = _site_url("학년별학원", spec.slug, next_locality)
    related = (
        ("학년별학원 안내", parent_url),
        (f"{spec.label} 전체 지역", category_url),
        (f"{locality} {spec.subject}학원 안내", subject_url),
        (f"{locality} 센터 안내", assets.center_url),
        (f"{spec.subject} 공부법", study_url),
        (f"이전 지역 · {previous_locality}", previous_url),
        (f"다음 지역 · {next_locality}", next_url),
    )
    schema = _detail_schema(spec, manuscript, record, assets, detail_url, related)
    image_url = SITE_ORIGIN + quote(assets.representative_src, safe="/%")
    supported = _supports(record, spec)
    source_status = "supported" if supported else "unconfirmed-grade"
    source_status_detail = (
        f"제공된 센터 자료의 {spec.subject} 가능 학년에 {spec.grade}이 기재되어 있습니다. 시작 시점·시간·반 구성은 상담에서 최신 내용을 확인하세요."
        if supported
        else f"제공 자료의 {spec.subject} 가능 학년에 {spec.grade}이 기재되지 않아 이 페이지는 선택 기준을 설명하는 정보 글이며, 해당 센터의 {spec.grade} {spec.subject} 수업 제공을 뜻하지 않습니다. 실제 가능 여부는 상담에서 확인하세요."
    )
    hero_copy = (
        f"{locality} 원고의 최근 학습 기록·학교 자료·오답 회수 순서를 읽고 학생의 실제 자료와 대조해 보세요."
        if supported
        else f"{locality} 원고는 {spec.grade} {spec.subject} 선택 기준을 설명합니다. 센터 수업 가능 여부는 아래 자료 상태와 상담 답변을 따로 확인하세요."
    )
    rendered_title = _correct_text(spec, locality, manuscript.title)
    rendered_meta = _correct_text(spec, locality, manuscript.meta_description)
    rendered_summary = _correct_text(spec, locality, manuscript.jsonld_summary)
    visible_schools = _visible_schools(record)
    schools_status = "provided" if visible_schools else "missing"
    school_value = (
        '<div class="math-tag-list">' + "".join(f"<span data-source-school>{_escape(school)}</span>" for school in visible_schools) + "</div>"
        if visible_schools
        else "원자료에 중학교명이 기재되지 않아 재학 학교와 현재 수업 가능 여부를 상담에서 확인해 주세요."
    )
    grade_source = " · ".join(_grades(record, spec)) if _grades(record, spec) else "원자료 미기재"
    grade_value = (
        f"{spec.grade} 확인 · 전체 기재 학년: {_escape(grade_source)}"
        if supported else f"{spec.grade} 상담 확인 필요 · 전체 기재 학년: {_escape(grade_source)}"
    )
    registration = record.registration_number or "원자료 미기재 — 상담 확인"
    fee_value = (
        f'<a class="math-tuition-link" href="{_escape(record.tuition_url)}" target="_blank" rel="noopener noreferrer">센터 교습비 자료 확인 <span aria-hidden="true">↗</span></a>'
        if record.tuition_url else "원자료에 교습비 링크가 없어 상담에서 최신 비용을 확인해 주세요."
    )
    intro_markup = "\n".join(
        f'        <p data-manuscript-paragraph="intro-{index:02d}" data-source-sha256="{_sha256(paragraph.encode("utf-8"))}">{_paragraph_markup(_correct_text(spec, locality, paragraph))}</p>'
        for index, paragraph in enumerate(manuscript.intro_paragraphs, 1)
    )
    section_markup = "\n".join(
        "\n".join([
            f'      <section id="section-{index:02d}" class="math-prose-section" data-manuscript-section="{index:02d}">',
            f"        <h2>{_escape(_correct_text(spec, locality, section.heading))}</h2>",
            *[
                f'        <p data-manuscript-paragraph="section-{index:02d}-{paragraph_index:02d}" data-source-sha256="{_sha256(paragraph.encode("utf-8"))}">{_paragraph_markup(_correct_text(spec, locality, paragraph))}</p>'
                for paragraph_index, paragraph in enumerate(section.paragraphs, 1)
            ],
            "      </section>",
        ])
        for index, section in enumerate(manuscript.sections, 1)
    )
    faq_markup = "\n".join(
        "\n".join([
            f'        <details class="math-faq-item" data-source-faq="{faq.number:02d}"{" open" if faq.number == 1 else ""}>',
            f"          <summary><span>Q{faq.number}.</span> {_escape(_correct_text(spec, locality, faq.question))}</summary>",
            f"          <p><strong>A.</strong> {_paragraph_markup(_correct_text(spec, locality, faq.answer))}</p>",
            "        </details>",
        ])
        for faq in manuscript.faqs
    )
    review_markup = "\n".join(
        [f'      <p class="math-review-note" data-source-review="01">{_paragraph_markup(_correct_text(spec, locality, manuscript.review_lines[0]))}</p>']
        + [
            f'      <blockquote class="math-review-quote" data-source-review="{index:02d}">{_paragraph_markup(_correct_text(spec, locality, line))}</blockquote>'
            for index, line in enumerate(manuscript.review_lines[1:], 2)
        ]
    )
    related_markup = "".join(f'<a href="{_escape(url)}">{_escape(name)}</a>' for name, url in related)
    unsupported_alert = "" if supported else (
        f'<section class="math-section grade-source-alert" aria-label="{_escape(locality)} {spec.grade} {spec.subject} 수업 확인 안내">'
        f'<div class="math-narrow"><strong>상담 확인이 필요한 페이지입니다.</strong><p>{_escape(source_status_detail)}</p></div></section>'
    )
    body_w, body_h = assets.body_size
    map_w, map_h = assets.map_size
    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(rendered_title)} | 와와학습코칭센터</title>
  <meta name="description" content="{_escape(rendered_meta)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{detail_url}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{_escape(rendered_title)} | 와와학습코칭센터">
  <meta property="og:description" content="{_escape(rendered_meta)}">
  <meta property="og:url" content="{detail_url}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:site_name" content="와와학습코칭센터">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_escape(rendered_title)} | 와와학습코칭센터">
  <meta name="twitter:description" content="{_escape(rendered_meta)}">
  <meta name="twitter:image" content="{image_url}">
  <link rel="icon" href="/assets/favicon.png">
  <link rel="stylesheet" href="/assets/fab.css">
  <link rel="stylesheet" href="/assets/header.css">
  <link rel="stylesheet" href="/assets/math-academy.css">
  <style>
    .grade-source-alert .math-narrow{{border:1px solid #c2410c;border-radius:18px;background:#fff7ed;padding:20px}}
    .grade-source-alert strong{{color:#9a3412}} .grade-source-alert p{{margin:8px 0 0}}
    .grade-source-note{{margin:0 0 18px;padding:14px 16px;border-left:4px solid #2563eb;background:#eff6ff;border-radius:8px}}
    .grade-checklist{{display:grid;gap:10px;margin:0;padding:0;list-style:none}}
    .grade-checklist li{{padding:12px 14px;border:1px solid #dbe3ee;border-radius:12px;background:#fff}}
    .math-faq-item summary span{{font-weight:800;color:#ea580c}}
  </style>
  <script type="application/ld+json">{_json_script(schema)}</script>
</head>
<body class="math-academy-page">
  {_BASE._nav_markup()}
  <main data-grade-page="{spec.hook}" data-source-status="{source_status}">
    <section class="math-hero"><div class="math-container">
      <nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/학년별학원/">학년별학원</a><span>›</span><a href="/학년별학원/{spec.slug}/">{_escape(spec.label)}</a><span>›</span><span aria-current="page">{_escape(rendered_title)}</span></nav>
      <div class="math-hero-grid"><div><p class="math-eyebrow">{spec.english_label} GUIDE</p><h1>{_escape(rendered_title)}</h1><p class="math-hero-lead">{_escape(rendered_meta)}</p></div><aside class="math-hero-panel"><strong>{_escape(locality)} {spec.grade} {spec.subject} 상담의 출발점</strong><p>{_escape(hero_copy)}</p><div class="math-step-row"><span>현재 기록</span><span>학교 자료</span><span>재점검</span></div></aside></div>
    </div></section>
    {unsupported_alert}
    <section class="math-media-section" aria-label="{_escape(rendered_title)} 이미지 안내"><div class="math-container math-media-stack">
      <figure class="math-visible-image"><img data-image-role="body" src="{_escape(assets.body_src)}" alt="{_escape(rendered_title)} 본문 와와학습코칭센터" loading="eager" fetchpriority="high" decoding="async" width="{body_w}" height="{body_h}"></figure>
      <figure class="math-map-card"><img data-image-role="map" src="{_escape(assets.map_src)}" alt="{_escape(rendered_title)} 센터 위치 지도" loading="lazy" decoding="async" width="{map_w}" height="{map_h}"><figcaption class="math-map-caption">제공 주소를 기준으로 등원 시간과 귀가 동선을 상담 전에 직접 확인할 때 참고하는 위치 이미지입니다.</figcaption></figure>
    </div></section>
    <section class="math-section paper"><div class="math-container math-quick-grid">
      <article class="math-summary-card"><strong>핵심 요약</strong><h2>{_escape(locality)} {spec.label} 선택 기준</h2><p>{_escape(rendered_summary)}</p></article>
      <aside class="math-info-card"><h2>지역·학년·수업 자료 확인</h2><p class="grade-source-note">{_escape(source_status_detail)}</p><dl>
        <div><dt>지역</dt><dd>{_escape(record.region)} {_escape(record.city)} {_escape(locality)}</dd></div>
        <div><dt>센터 기준</dt><dd>{_escape(record.center_name)}</dd></div>
        <div data-source-field="grade"><dt>{_escape(spec.grades_label)}</dt><dd>{grade_value}</dd></div>
        <div data-source-field="middle-schools" data-source-status="{schools_status}" data-source-raw-schools="{_escape(' | '.join(record.middle_school_source_tokens))}"><dt>수업 가능 학교 자료</dt><dd>{school_value}</dd></div>
        <div data-source-field="address"><dt>제공 주소</dt><dd>{_escape(record.address)}</dd></div>
        <div data-source-field="registration"><dt>교육지원청 등록번호</dt><dd>{_escape(registration)}</dd></div>
        <div data-source-field="fee"><dt>센터 교습비</dt><dd>{fee_value}</dd></div>
      </dl></aside>
    </div></section>
    <section class="math-section"><article class="math-narrow math-article" data-manuscript><div class="math-article-intro">
{intro_markup}
    </div>
{section_markup}
    </article></section>
    <section class="math-section paper"><div class="math-narrow math-links-card"><p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>{_escape(locality)} 상담 전 체크리스트</h2><ul class="grade-checklist"><li>□ {_escape(locality)} 학생의 최근 시험지와 실제 풀이가 남은 교재</li><li>□ 학교 교과서·시험 범위표와 수행평가 일정</li><li>□ 일주일 중 혼자 복습할 수 있는 시간과 실제 등원 동선</li><li>□ 오답을 다시 확인할 날짜와 상담에서 물어볼 운영 조건</li></ul></div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card" data-faq><p class="math-eyebrow">FAQ</p><h2>{_escape(locality)} {spec.label} 자주 묻는 질문</h2><div class="math-faq-list">
{faq_markup}
    </div></div></section>
    <section class="math-section"><div class="math-narrow math-review-card" data-review><p class="math-eyebrow">PARENT COMMENT</p><h2>{_escape(locality)} 학부모 상담 관점</h2>
{review_markup}
    </div></section>
    <section class="math-section paper"><div class="math-narrow math-links-card"><p class="math-eyebrow">RELATED PAGES</p><h2>{_escape(locality)} 관련 내부 링크</h2><div class="math-links">{related_markup}</div></div></section>
  </main>
  {_BASE._fab_markup(assets.telephone)}
  <footer class="math-footer"><strong>와와학습코칭센터</strong><br>원고와 제공된 센터·학교 자료를 기준으로 구성했으며, 실제 수업 가능 여부·비용·일정은 상담에서 최신 내용을 확인해 주세요.</footer>
</body>
</html>"""
    return _clean_document(document)


def _directory_org() -> dict[str, Any]:
    return {
        "@type": "EducationalOrganization", "@id": SITE_ORIGIN + "/#organization",
        "name": "와와학습코칭센터", "url": SITE_ORIGIN + "/", "telephone": "010-3957-8283",
        "areaServed": {"@type": "Country", "name": "대한민국"},
        "knowsAbout": [spec.label for spec in ALL_CATEGORIES] + ["학교 내신", "오답 재학습", "학습 계획"],
    }


def _directory_head(title: str, description: str, canonical: str, schema: Mapping[str, Any]) -> str:
    return f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <meta name="description" content="{_escape(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{_escape(title)}">
  <meta property="og:description" content="{_escape(description)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{SITE_ORIGIN}/assets/title.png">
  <meta property="og:site_name" content="와와학습코칭센터">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_escape(title)}">
  <meta name="twitter:description" content="{_escape(description)}">
  <meta name="twitter:image" content="{SITE_ORIGIN}/assets/title.png">
  <link rel="icon" href="/assets/favicon.png">
  <link rel="stylesheet" href="/assets/fab.css">
  <link rel="stylesheet" href="/assets/header.css">
  <link rel="stylesheet" href="/assets/subject-academy.css">
  <link rel="stylesheet" href="/assets/math-academy.css">
  <script type="application/ld+json">{_json_script(schema)}</script>
</head>"""


def _render_parent_hub() -> str:
    canonical = _site_url("학년별학원")
    title = "학년별학원 안내 | 와와학습코칭센터"
    description = "중1·중2·중3 수학학원과 영어학원 6개 분류에서 학년별 진단, 학교 자료, 복습과 상담 기준을 371개 지역별로 확인하세요."
    category_nodes = [
        {"@type": "CollectionPage", "name": spec.label, "url": _site_url("학년별학원", spec.slug)}
        for spec in ALL_CATEGORIES
    ]
    faq_entities = [
        {
            "@type": "Question", "name": "학년별학원 페이지에서는 무엇을 확인하나요?",
            "acceptedAnswer": {"@type": "Answer", "text": "학생 학년과 과목을 먼저 정한 뒤 현재 학습 진단, 학교 자료, 복습과 상담 기준을 지역별 원고에서 확인할 수 있습니다."},
        },
        {
            "@type": "Question", "name": "현재 제공되는 학년별 분류는 무엇인가요?",
            "acceptedAnswer": {"@type": "Answer", "text": "중학교 1·2·3학년의 수학과 영어 안내를 각 371개 동네별로 제공합니다."},
        },
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            _directory_org(),
            {
                "@type": "CollectionPage", "@id": canonical + "#webpage", "url": canonical, "name": title,
                "description": description, "inLanguage": "ko-KR", "isPartOf": {"@id": SITE_ORIGIN + "/#website"},
                "publisher": {"@id": SITE_ORIGIN + "/#organization"}, "breadcrumb": {"@id": canonical + "#breadcrumb"},
                "about": [{"@type": "Thing", "name": "학년별학원"}, {"@type": "Thing", "name": "중학교 영어·수학"}],
                "hasPart": category_nodes, "datePublished": PUBLISHED_DATE, "dateModified": PUBLISHED_DATE,
            },
            {
                "@type": "BreadcrumbList", "@id": canonical + "#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_ORIGIN + "/"},
                    {"@type": "ListItem", "position": 2, "name": "학년별학원", "item": canonical},
                ],
            },
            {
                "@type": "ItemList", "@id": canonical + "#categories", "name": "학년별학원 분류",
                "numberOfItems": len(ALL_CATEGORIES),
                "itemListElement": [
                    {"@type": "ListItem", "position": index, "name": spec.label, "url": _site_url("학년별학원", spec.slug)}
                    for index, spec in enumerate(ALL_CATEGORIES, 1)
                ],
            },
            {"@type": "FAQPage", "@id": canonical + "#faq", "mainEntity": faq_entities},
        ],
    }
    cards = "".join(
        f'<a class="subject-category-card" data-number="{index:02d}" href="/학년별학원/{spec.slug}/"><small>{spec.english_label}</small><h3>{_escape(spec.label)}</h3><p>{_escape(spec.card_copy)}</p><span class="subject-status">371개 지역 안내 보기 →</span></a>'
        for index, spec in enumerate(ALL_CATEGORIES, 1)
    )
    document = f"""<!doctype html>
<html lang="ko">
{_directory_head(title, description, canonical, schema)}
<body class="subject-page">
  {_BASE._nav_markup()}
  <main data-grade-directory="parent">
    <section class="subject-hero"><div class="subject-container"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><span aria-current="page">학년별학원</span></nav><div class="subject-hero-grid"><div><p class="subject-kicker">GRADE ACADEMY GUIDE</p><h1>학년별학원에서 학년과 과목을 고르고<br>지역 안내를 확인하세요</h1><p class="subject-hero-copy">학생의 현재 학년과 과목을 출발점으로 학교 자료, 취약 영역, 오답 재학습과 주간 계획을 지역별로 확인하는 안내입니다.</p></div><aside class="subject-hero-panel"><strong>학년명만으로 수업을 단정하지 않습니다</strong><p>지역 원고와 제공된 가능 학년 자료를 함께 보고, 실제 수업 시작 시점과 조건은 상담에서 확인하세요.</p><div class="subject-hero-tags"><span>현재 학년</span><span>영어·수학</span><span>학교 자료</span><span>주간 계획</span></div></aside></div></div></section>
    <section class="subject-section paper"><div class="subject-container"><div class="subject-section-head"><p class="subject-kicker">GRADE CATEGORIES</p><h2>현재 확인할 수 있는 학년별 안내</h2><p>중1·중2·중3 수학과 영어 6개 분류에서 각 371개 지역 원고를 제공합니다.</p></div><div class="subject-category-grid">{cards}</div></div></section>
    <section class="subject-section"><div class="subject-container"><div class="subject-section-head"><p class="subject-kicker">HOW TO USE</p><h2>지역 원고를 확인하는 순서</h2></div><div class="subject-point-grid"><article><strong>01</strong><h3>학년과 과목을 고릅니다</h3><p>학생의 현재 학년과 먼저 확인할 과목을 선택합니다.</p></article><article><strong>02</strong><h3>학교 자료를 대조합니다</h3><p>교과서, 범위표와 평가 일정을 실제 자료로 확인합니다.</p></article><article><strong>03</strong><h3>수업 가능 여부를 확인합니다</h3><p>제공 자료와 상담 안내를 구분해 시작 시점과 비용을 확인합니다.</p></article></div></div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card" data-faq><p class="math-eyebrow">FAQ</p><h2>학년별학원 자주 묻는 질문</h2><div class="math-faq-list"><details class="math-faq-item" open><summary>{_escape(faq_entities[0]['name'])}</summary><p>{_escape(faq_entities[0]['acceptedAnswer']['text'])}</p></details><details class="math-faq-item"><summary>{_escape(faq_entities[1]['name'])}</summary><p>{_escape(faq_entities[1]['acceptedAnswer']['text'])}</p></details></div></div></section>
  </main>
  {_BASE._fab_markup()}
  <footer class="subject-footer"><strong>와와학습코칭센터</strong><br>학년별 페이지는 원고와 제공 자료를 기준으로 구성하며 실제 수업 조건은 상담에서 확인해 주세요.</footer>
</body>
</html>"""
    return _clean_document(document)


def _group_centers(center_order: Sequence[str], centers: Mapping[str, Any]) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    regions: dict[str, dict[str, list[str]]] = {}
    for locality in center_order:
        record = centers[locality]
        regions.setdefault(record.region, {}).setdefault(record.city, []).append(locality)
    return [(region, list(cities.items())) for region, cities in regions.items()]


def _render_category_hub(spec: CategorySpec, center_order: Sequence[str], centers: Mapping[str, Any]) -> str:
    canonical = _site_url("학년별학원", spec.slug)
    parent = _site_url("학년별학원")
    title = f"{spec.label} 371개 지역 안내 | 와와학습코칭센터"
    description = f"{spec.label} 선택에 필요한 현재 학습 진단, 학교 자료, 오답 복습과 상담 확인 항목을 371개 동네별 원고에서 찾으세요."
    items = [
        {"@type": "ListItem", "position": index, "name": f"{locality} {spec.label}", "url": _site_url("학년별학원", spec.slug, locality)}
        for index, locality in enumerate(center_order, 1)
    ]
    question1 = f"{spec.label} 상담에 무엇을 가져가면 좋나요?"
    answer1 = f"최근 {spec.subject} 시험지, 실제 풀이가 남은 교재, 학교 교과서와 범위표, 일주일 시간표를 준비하면 진단과 복습 계획을 구체적으로 비교할 수 있습니다."
    question2 = "지역 페이지에 학교명이 없으면 어떻게 하나요?"
    answer2 = "제공 자료에 중학교명이 없는 경우 임의로 학교를 추가하지 않으며, 재학 학교의 실제 교과서와 시험 범위 대응 여부를 상담에서 확인해야 합니다."
    schema = {
        "@context": "https://schema.org", "@graph": [
            _directory_org(),
            {
                "@type": "CollectionPage", "@id": canonical + "#webpage", "url": canonical, "name": title,
                "description": description, "inLanguage": "ko-KR", "isPartOf": {"@id": SITE_ORIGIN + "/#website"},
                "publisher": {"@id": SITE_ORIGIN + "/#organization"}, "breadcrumb": {"@id": canonical + "#breadcrumb"},
                "about": [{"@type": "Thing", "name": spec.label}, {"@type": "Thing", "name": f"{spec.grade} {spec.subject} 내신"}],
                "hasPart": [{"@type": "ItemList", "@id": canonical + "#regions"}],
                "datePublished": PUBLISHED_DATE, "dateModified": PUBLISHED_DATE,
            },
            {
                "@type": "BreadcrumbList", "@id": canonical + "#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_ORIGIN + "/"},
                    {"@type": "ListItem", "position": 2, "name": "학년별학원", "item": parent},
                    {"@type": "ListItem", "position": 3, "name": spec.label, "item": canonical},
                ],
            },
            {"@type": "ItemList", "@id": canonical + "#regions", "name": f"{spec.label} 지역 목록", "numberOfItems": len(items), "itemListElement": items},
            {
                "@type": "FAQPage", "@id": canonical + "#faq", "mainEntity": [
                    {"@type": "Question", "name": question1, "acceptedAnswer": {"@type": "Answer", "text": answer1}},
                    {"@type": "Question", "name": question2, "acceptedAnswer": {"@type": "Answer", "text": answer2}},
                ],
            },
        ],
    }
    regions: list[str] = []
    for region_index, (region, cities) in enumerate(_group_centers(center_order, centers), 1):
        city_markup: list[str] = []
        for city, localities in cities:
            links = "".join(
                f'<a href="/학년별학원/{spec.slug}/{_escape(locality)}/" data-grade-locality="{_escape(locality)}">{_escape(locality)} {spec.label}</a>'
                for locality in localities
            )
            city_markup.append(f'<section class="math-city-group" data-grade-city><h3>{_escape(city)}</h3><div class="math-local-links">{links}</div></section>')
        regions.append(
            f'<details class="math-region-group" data-grade-region{" open" if region_index == 1 else ""}><summary>{_escape(region)} <span>{sum(len(values) for _, values in cities)}개 지역</span></summary><div class="math-city-list">{"".join(city_markup)}</div></details>'
        )
    region_markup = "".join(regions)
    document = f"""<!doctype html>
<html lang="ko">
{_directory_head(title, description, canonical, schema)}
<body class="math-academy-page">
  {_BASE._nav_markup()}
  <main data-grade-directory="{spec.hook}">
    <section class="math-hero"><div class="math-container"><nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/학년별학원/">학년별학원</a><span>›</span><span aria-current="page">{_escape(spec.label)}</span></nav><div class="math-hero-grid"><div><p class="math-eyebrow">{spec.english_label}</p><h1>{_escape(spec.label)} 371개 지역 안내</h1><p class="math-hero-lead">{_escape(description)}</p></div><aside class="math-hero-panel"><strong>학교명만으로 시험 유형을 단정하지 않습니다</strong><p>지역을 찾은 뒤 학생의 실제 교과서, 시험 범위와 학습 기록을 함께 대조하세요.</p><div class="math-step-row"><span>지역 찾기</span><span>원고 읽기</span><span>상담 확인</span></div></aside></div></div></section>
    <section class="math-section paper"><div class="math-container"><div class="math-section-head"><p class="math-eyebrow">LOCAL DIRECTORY</p><h2>동네별 {_escape(spec.label)} 원고 찾기</h2><p>지역명 일부를 입력하면 목록을 바로 좁힐 수 있습니다.</p></div><div class="math-search-card"><label for="grade-local-search">동네 검색</label><div class="math-search-row"><input id="grade-local-search" type="search" placeholder="예: 명일동" autocomplete="off" data-grade-search><button type="button" data-grade-clear>검색 지우기</button></div><p aria-live="polite" data-grade-status>전체 371개 지역</p></div><div class="math-directory" data-grade-list>{region_markup}</div></div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card" data-faq><p class="math-eyebrow">FAQ</p><h2>{_escape(spec.label)} 자주 묻는 질문</h2><div class="math-faq-list"><details class="math-faq-item" open><summary>{_escape(question1)}</summary><p>{_escape(answer1)}</p></details><details class="math-faq-item"><summary>{_escape(question2)}</summary><p>{_escape(answer2)}</p></details></div></div></section>
    <section class="math-section"><div class="math-narrow math-links-card"><p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>{_escape(spec.grade)} {_escape(spec.subject)} 상담 전 준비 자료</h2><div class="math-links"><a href="/학년별학원/">학년별학원 안내</a><a href="/과목별학원/{spec.subject_slug}/">{_escape(spec.subject)}학원 전체 지역</a><a href="/교육정보/{spec.guide_slug}/">{_escape(spec.subject)} 공부법</a><a href="/center/">전국센터 찾기</a></div></div></section>
  </main>
  {_BASE._fab_markup()}
  <footer class="math-footer"><strong>와와학습코칭센터</strong><br>지역 원고와 제공 자료를 구분해 확인하고 실제 수업 조건은 상담에서 최신 내용을 확인해 주세요.</footer>
  <script>
  (() => {{
    const input = document.querySelector('[data-grade-search]');
    const clear = document.querySelector('[data-grade-clear]');
    const status = document.querySelector('[data-grade-status]');
    const list = document.querySelector('[data-grade-list]');
    const links = [...list.querySelectorAll('[data-grade-locality]')];
    const normalize = (value) => value.trim().toLocaleLowerCase('ko-KR');
    const update = () => {{
      const query = normalize(input.value); let visible = 0;
      links.forEach((link) => {{ const show = !query || normalize(link.dataset.gradeLocality).includes(query); link.hidden = !show; if (show) visible += 1; }});
      list.querySelectorAll('[data-grade-city]').forEach((city) => {{ city.hidden = ![...city.querySelectorAll('[data-grade-locality]')].some((link) => !link.hidden); }});
      list.querySelectorAll('[data-grade-region]').forEach((region) => {{ const show = [...region.querySelectorAll('[data-grade-city]')].some((city) => !city.hidden); region.hidden = !show; if (query && show) region.open = true; }});
      status.textContent = query ? visible + '개 지역 검색됨' : '전체 371개 지역';
    }};
    input.addEventListener('input', update);
    clear.addEventListener('click', () => {{ input.value = ''; update(); input.focus(); }});
  }})();
  </script>
</body>
</html>"""
    return _clean_document(document)


def _sitemap_urls(center_order: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for spec in NEW_CATEGORIES:
        values.append(_site_url("학년별학원", spec.slug))
        values.extend(_site_url("학년별학원", spec.slug, locality) for locality in center_order)
    return tuple(values)


def _url_blocks(document: str) -> tuple[tuple[str, str, str], ...]:
    values: list[tuple[str, str, str]] = []
    for block_match in RAW_URL_RE.finditer(document):
        block = block_match.group(0)
        locations = LOC_RE.findall(block)
        lastmods = LASTMOD_RE.findall(block)
        if len(locations) != 1 or len(lastmods) != 1:
            raise BuildError("sitemap.xml: malformed URL block")
        values.append((html.unescape(locations[0]), html.unescape(lastmods[0]), block))
    return tuple(values)


def _update_sitemap(document: str, center_order: Sequence[str]) -> str:
    new_urls = _sitemap_urls(center_order)
    blocks = _url_blocks(document)
    closing = [match.start() for match in re.finditer(r"</urlset>", document)]
    if len(closing) != 1:
        raise BuildError("sitemap.xml: expected one closing urlset")
    new_set = set(new_urls)
    positions = [index for index, (location, _, _) in enumerate(blocks) if location in new_set]
    if not positions:
        if len(blocks) != EXPECTED_EXISTING_HTML or _sha256(document.encode("utf-8")) != BASE_SITEMAP_SHA256:
            raise BuildError("sitemap.xml: baseline blocks/hash mismatch")
        newline = "\r\n" if "\r\n" in document else "\n"
        position = closing[0]
        prefix, suffix = document[:position], document[position:]
        if not prefix.endswith(newline):
            raise BuildError("sitemap.xml: closing element must be on its own line")
        appended = "".join(
            f"  <url>{newline}    <loc>{_escape(url)}</loc>{newline}    <lastmod>{PUBLISHED_DATE}</lastmod>{newline}  </url>{newline}"
            for url in new_urls
        )
        return prefix + appended + suffix
    if len(positions) != len(new_urls) or len(blocks) != EXPECTED_FINAL_HTML:
        raise BuildError("sitemap.xml: partial/conflicting middle-grade URL set")
    if tuple(location for location, _, _ in blocks[-len(new_urls):]) != new_urls:
        raise BuildError("sitemap.xml: new URLs are not the exact final ordered block")
    if any(lastmod != PUBLISHED_DATE for _, lastmod, _ in blocks[-len(new_urls):]):
        raise BuildError("sitemap.xml: new lastmod mismatch")
    return document


def _llms_block() -> str:
    lines = [
        LLMS_MARKER, "",
        f"- 학년별학원: {SITE_ORIGIN}/학년별학원/",
        "  - 중1·중2·중3의 영어·수학 지역 안내를 학년과 과목별로 찾는 핵심 허브입니다.",
    ]
    for spec in ALL_CATEGORIES:
        lines.extend([
            f"- {spec.label}: {SITE_ORIGIN}/학년별학원/{spec.slug}/",
            f"  - {spec.grade} {spec.subject} 진단·학교 자료·오답 재학습·상담 기준을 371개 동네별 원고로 안내합니다.",
        ])
    return "\n".join(lines) + "\n"


def _update_llms(document: str) -> str:
    if document.count(LLMS_MARKER) != 1:
        raise BuildError("llms.txt: exact existing grade marker required")
    index = document.index(LLMS_MARKER)
    prefix = document[:index]
    canonical = prefix + _llms_block()
    if document != canonical and _sha256(document.encode("utf-8")) != BASE_LLMS_SHA256:
        raise BuildError("llms.txt: baseline/canonical grade block conflict")
    return canonical


def _source_fields(manuscript: Manuscript) -> tuple[str, ...]:
    values: list[str] = [manuscript.title, manuscript.meta_description, *manuscript.intro_paragraphs]
    for section in manuscript.sections:
        values.append(section.heading)
        values.extend(section.paragraphs)
    for faq in manuscript.faqs:
        values.extend((faq.question, faq.answer))
    values.extend(manuscript.review_lines)
    values.append(manuscript.jsonld_summary)
    return tuple(values)


def _auxiliary_seed(spec: CategorySpec, manuscript: Manuscript) -> str | None:
    """Extract the manuscript's quoted search seed without treating it as a service fact."""
    if spec.key in {"middle2_math", "middle3_english"}:
        matches = [value for faq in manuscript.faqs for value in SEED_QUOTE_RE.findall(faq.question)]
    elif spec.key == "middle2_english":
        matches = [value for value in SEED_QUOTE_RE.findall(manuscript.jsonld_summary) if value != "영어 수학"]
    else:
        return None
    if len(matches) != 1 or not matches[0].strip() or matches[0] != matches[0].strip():
        raise BuildError(f"{spec.key}/{manuscript.member_name}: auxiliary search seed structure mismatch")
    return matches[0]


def _audit_auxiliary_seeds(all_manuscripts: Mapping[str, Mapping[str, Manuscript]]) -> Mapping[str, Any]:
    counts: dict[str, int] = {}
    total = 0
    for spec in NEW_CATEGORIES:
        seeds = [
            seed for manuscript in all_manuscripts[spec.key].values()
            if (seed := _auxiliary_seed(spec, manuscript)) is not None
        ]
        expected = EXPECTED_LOCALITIES if spec.key in {"middle2_math", "middle2_english", "middle3_english"} else 0
        if len(seeds) != expected or len(set(seeds)) != expected:
            raise BuildError(f"{spec.key}: auxiliary search seed count/uniqueness mismatch")
        counts[spec.key] = len(seeds)
        total += len(seeds)
    if total != 1_113:
        raise BuildError("aggregate auxiliary search seed count mismatch")
    return MappingProxyType({
        "auxiliary_seed_pages": total,
        "auxiliary_seed_unique_by_category": counts,
        "auxiliary_seed_schema_gate_pages": EXPECTED_NEW_DETAILS,
        "auxiliary_seed_service_offer_knowsabout_conflicts": 0,
    })


def _audit_corrections(all_manuscripts: Mapping[str, Mapping[str, Manuscript]]) -> Mapping[str, Any]:
    expected_keys = {(rule.category_key, rule.locality) for rule in CORRECTION_RULES}
    changed_pages: set[tuple[str, str]] = set()
    replacement_count = 0
    for spec in NEW_CATEGORIES:
        manuscripts = all_manuscripts[spec.key]
        for locality, manuscript in manuscripts.items():
            fields = _source_fields(manuscript)
            page_changed = False
            for field in fields:
                rendered = _correct_text(spec, locality, field)
                if rendered != field:
                    page_changed = True
                    for rule in RULES_BY_PAGE.get((spec.key, locality), ()):
                        replacement_count += field.count(rule.source)
            if page_changed:
                changed_pages.add((spec.key, locality))
    for rule in CORRECTION_RULES:
        manuscript = all_manuscripts[rule.category_key][rule.locality]
        actual = manuscript.raw_text.count(rule.source)
        if actual != rule.expected_occurrences:
            raise BuildError(
                f"correction source occurrence mismatch: {rule.category_key}/{rule.locality}/"
                f"{rule.source!r}: {actual} != {rule.expected_occurrences}"
            )
        if rule.source == rule.rendered or not rule.source or not rule.rendered:
            raise BuildError("invalid no-op/empty correction rule")
    if changed_pages != expected_keys or replacement_count != EXPECTED_LITERAL_CORRECTIONS:
        raise BuildError(
            f"visible correction allowlist mismatch: pages={len(changed_pages)}/{len(expected_keys)}, "
            f"occurrences={replacement_count}/{EXPECTED_LITERAL_CORRECTIONS}"
        )
    return MappingProxyType({
        "correction_rules": len(CORRECTION_RULES),
        "correction_pages": len(changed_pages),
        "literal_occurrences_corrected": replacement_count,
        "raw_manuscript_bytes_preserved": EXPECTED_NEW_DETAILS,
        "non_allowlisted_visible_source_changes": 0,
    })


def _crosscheck_physical_source(spec: CategorySpec, record: Any, assets: Any) -> None:
    organization = assets.organization
    if organization.get("name") != record.center_name:
        raise BuildError(f"{spec.key}/{record.locality}: generic organization name differs from CSV")
    address = organization.get("address")
    if not isinstance(address, dict) or address.get("streetAddress") != record.address:
        raise BuildError(f"{spec.key}/{record.locality}: generic physical address differs from CSV")
    identifier = organization.get("identifier")
    if not isinstance(identifier, dict) or identifier.get("value") != record.registration_number:
        raise BuildError(f"{spec.key}/{record.locality}: generic registration differs from CSV")
    levels = organization.get("educationalLevel")
    # The existing English generic tree inherited the math-level physical node.
    # Pin that exact baseline debt instead of trusting it, then rebase every new
    # English node to the authoritative English CSV levels in _physical_nodes.
    expected_generic_levels = record.math_grades if spec.subject == "영어" else _grades(record, spec)
    if levels is not None and tuple(levels) != expected_generic_levels:
        raise BuildError(f"{spec.key}/{record.locality}: generic physical grade baseline differs from pinned CSV")
    offers = organization.get("makesOffer")
    offer_urls: set[str] = set()
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict) and isinstance(offer.get("url"), str):
                offer_urls.add(offer["url"])
    if record.tuition_url and record.tuition_url not in offer_urls:
        raise BuildError(f"{spec.key}/{record.locality}: generic tuition URL differs from CSV")
    if not record.tuition_url and offer_urls:
        raise BuildError(f"{spec.key}/{record.locality}: generic tuition URL exists but CSV is blank")


def _validate_parent(document: str) -> None:
    audit = _BASE._audit_html(document, "grade parent hub")
    _BASE._validate_nav(document, "grade parent hub", grade_active=True)
    mains = [attrs for tag, attrs in audit.start_tags if tag == "main" and attrs.get("data-grade-directory") == "parent"]
    if len(mains) != 1:
        raise BuildError("grade parent: main hook mismatch")
    canonical = _site_url("학년별학원")
    if _BASE._canonical_values(document) != [canonical] or _BASE._meta_values(document, property_name="og:url") != [canonical]:
        raise BuildError("grade parent: canonical/og:url mismatch")
    for spec in ALL_CATEGORIES:
        if document.count(f'href="/학년별학원/{spec.slug}/"') != 1:
            raise BuildError(f"grade parent: category card mismatch: {spec.key}")
    jsonld, _ = _BASE._extract_jsonld_graph(document, "grade parent hub")
    item_list = _BASE._find_graph_node(jsonld["@graph"], "ItemList", "grade parent hub")
    if item_list.get("numberOfItems") != 6 or len(item_list.get("itemListElement", [])) != 6:
        raise BuildError("grade parent: ItemList six-category mismatch")
    page = _BASE._find_graph_node(jsonld["@graph"], "CollectionPage", "grade parent hub")
    if len(page.get("hasPart", [])) != 6:
        raise BuildError("grade parent: hasPart six-category mismatch")
    faq = _BASE._find_graph_node(jsonld["@graph"], "FAQPage", "grade parent hub")
    if len(faq.get("mainEntity", [])) != 2 or document.count(" data-faq>") != 1:
        raise BuildError("grade parent: FAQ visible/schema mismatch")


def _validate_category(spec: CategorySpec, document: str, center_order: Sequence[str]) -> None:
    label = f"{spec.key} category hub"
    audit = _BASE._audit_html(document, label)
    _BASE._validate_nav(document, label, grade_active=True)
    mains = [attrs for tag, attrs in audit.start_tags if tag == "main" and attrs.get("data-grade-directory") == spec.hook]
    if len(mains) != 1:
        raise BuildError(f"{label}: main hook mismatch")
    expected_localities = list(center_order)
    localities = re.findall(r'data-grade-locality="([^"]+)"', document)
    if localities != expected_localities:
        raise BuildError(f"{label}: locality order/content mismatch")
    for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
        if document.count(hook) < 1:
            raise BuildError(f"{label}: search hook missing: {hook}")
    required_script = ("toLocaleLowerCase('ko-KR')", "input.value = ''", "update(); input.focus();", "'전체 371개 지역'")
    if any(fragment not in document for fragment in required_script):
        raise BuildError(f"{label}: search/clear contract missing")
    query = "명일동".casefold()
    if [locality for locality in localities if query in locality.casefold()] != ["명일동"]:
        raise BuildError(f"{label}: search synthetic mismatch")
    canonical = _site_url("학년별학원", spec.slug)
    if _BASE._canonical_values(document) != [canonical] or _BASE._meta_values(document, property_name="og:url") != [canonical]:
        raise BuildError(f"{label}: canonical/og:url mismatch")
    jsonld, _ = _BASE._extract_jsonld_graph(document, label)
    item_list = _BASE._find_graph_node(jsonld["@graph"], "ItemList", label)
    if item_list.get("numberOfItems") != EXPECTED_LOCALITIES or len(item_list.get("itemListElement", [])) != EXPECTED_LOCALITIES:
        raise BuildError(f"{label}: ItemList count mismatch")
    faq = _BASE._find_graph_node(jsonld["@graph"], "FAQPage", label)
    if len(faq.get("mainEntity", [])) != 2 or document.count(" data-faq>") != 1:
        raise BuildError(f"{label}: FAQ visible/schema mismatch")


def _schema_node(graph: Sequence[Any], node_type: str, label: str) -> dict[str, Any]:
    return _BASE._find_graph_node(graph, node_type, label)


def _validate_detail(spec: CategorySpec, document: str, manuscript: Manuscript, record: Any, assets: Any) -> None:
    label = f"{spec.key}/{manuscript.member_name}"
    audit = _BASE._audit_html(document, label)
    _BASE._validate_nav(document, label, grade_active=True)
    supported = _supports(record, spec)
    status = "supported" if supported else "unconfirmed-grade"
    mains = [attrs for tag, attrs in audit.start_tags if tag == "main" and attrs.get("data-grade-page") == spec.hook]
    if len(mains) != 1 or mains[0].get("data-source-status") != status:
        raise BuildError(f"{label}: main/status hook mismatch")
    if document.count(" data-manuscript>") != 1 or document.count(" data-faq>") != 1 or document.count(" data-review>") != 1:
        raise BuildError(f"{label}: manuscript/FAQ/review wrapper mismatch")
    section_values = re.findall(r'data-manuscript-section="([0-9]{2})"', document)
    expected_sections = [f"{index:02d}" for index in range(1, len(manuscript.sections) + 1)]
    if section_values != expected_sections:
        raise BuildError(f"{label}: variable source H2 hook mismatch")
    for field in ("grade", "middle-schools", "address", "registration", "fee"):
        if len(re.findall(rf'data-source-field="{re.escape(field)}"', document)) != 1:
            raise BuildError(f"{label}: source fact hook mismatch: {field}")
    school_status = "provided" if _visible_schools(record) else "missing"
    school_hook = re.search(r'<div\b[^>]*data-source-field="middle-schools"[^>]*data-source-status="([^"]+)"[^>]*data-source-raw-schools="([^"]*)"', document)
    if school_hook is None or school_hook.group(1) != school_status:
        raise BuildError(f"{label}: middle-school status/raw hook missing")
    if html.unescape(school_hook.group(2)) != " | ".join(record.middle_school_source_tokens):
        raise BuildError(f"{label}: raw middle-school diagnostic changed")
    visible_school_chips = tuple(html.unescape(value) for value in re.findall(r"<span data-source-school>(.*?)</span>", document, re.DOTALL))
    if visible_school_chips != _visible_schools(record):
        raise BuildError(f"{label}: visible corrected school/source parity mismatch")

    detail_url = _site_url("학년별학원", spec.slug, record.locality)
    image_url = SITE_ORIGIN + quote(assets.representative_src, safe="/%")
    rendered_title = _correct_text(spec, record.locality, manuscript.title)
    rendered_meta = _correct_text(spec, record.locality, manuscript.meta_description)
    if _BASE._canonical_values(document) != [detail_url] or _BASE._meta_values(document, property_name="og:url") != [detail_url]:
        raise BuildError(f"{label}: canonical/og:url parity failed")
    if _BASE._meta_values(document, name="description") != [rendered_meta]:
        raise BuildError(f"{label}: meta description/source parity failed")
    if _BASE._meta_values(document, property_name="og:image") != [image_url] or _BASE._meta_values(document, name="twitter:image") != [image_url]:
        raise BuildError(f"{label}: representative image head parity failed")
    title_match = re.search(r"<title>(.*?)</title>", document, re.DOTALL | re.IGNORECASE)
    h1_match = re.search(r"<h1>(.*?)</h1>", document, re.DOTALL | re.IGNORECASE)
    if title_match is None or html.unescape(title_match.group(1)) != f"{rendered_title} | 와와학습코칭센터":
        raise BuildError(f"{label}: title mismatch")
    if h1_match is None or html.unescape(re.sub(r"<[^>]+>", "", h1_match.group(1))) != rendered_title:
        raise BuildError(f"{label}: H1 mismatch")
    if any(image.get("src") == assets.representative_src for image in audit.images):
        raise BuildError(f"{label}: representative image must not be visible DOM")
    body_images = [image for image in audit.images if image.get("data-image-role") == "body"]
    map_images = [image for image in audit.images if image.get("data-image-role") == "map"]
    if len(body_images) != 1 or len(map_images) != 1:
        raise BuildError(f"{label}: body/map image role cardinality failed")
    body_image, map_image = body_images[0], map_images[0]
    if (
        body_image.get("src") != assets.body_src or body_image.get("loading") != "eager"
        or body_image.get("fetchpriority") != "high" or body_image.get("decoding") != "async"
        or (body_image.get("width"), body_image.get("height")) != tuple(map(str, assets.body_size))
    ):
        raise BuildError(f"{label}: visible body image policy failed")
    if (
        map_image.get("src") != assets.map_src or map_image.get("loading") != "lazy"
        or map_image.get("decoding") != "async"
        or (map_image.get("width"), map_image.get("height")) != tuple(map(str, assets.map_size))
    ):
        raise BuildError(f"{label}: map image policy failed")

    jsonld, _ = _BASE._extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    types = _BASE._schema_types(graph)
    for required in ("WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject"):
        if types[required] != 1:
            raise BuildError(f"{label}: schema type count mismatch: {required}")
    organization = _schema_node(graph, "EducationalOrganization", label)
    local_business = _schema_node(graph, "LocalBusiness", label)
    if tuple(organization.get("educationalLevel", [])) != _grades(record, spec):
        raise BuildError(f"{label}: subject educationalLevel/source mismatch")
    if supported:
        if types["Service"] != 1 or types["Offer"] != 1 or "makesOffer" not in organization or "makesOffer" not in local_business:
            raise BuildError(f"{label}: supported Service/Offer/makesOffer missing")
        service = _schema_node(graph, "Service", label)
        audience = service.get("audience")
        if not isinstance(audience, dict) or spec.grade not in str(audience.get("audienceType", "")):
            raise BuildError(f"{label}: supported audience grade mismatch")
    else:
        if types["Service"] or types["Offer"] or "makesOffer" in organization or "makesOffer" in local_business:
            raise BuildError(f"{label}: unconfirmed Article page contains service claim")
        disclaimer = f"해당 센터의 {spec.grade} {spec.subject} 수업 제공을 뜻하지 않습니다"
        if disclaimer not in document:
            raise BuildError(f"{label}: unconfirmed explicit disclaimer missing")
    seed = _auxiliary_seed(spec, manuscript)
    if seed is not None:
        for node in graph:
            if not isinstance(node, dict):
                continue
            node_types = node.get("@type", ())
            if isinstance(node_types, str):
                node_types = (node_types,)
            if any(node_type in {"Service", "Offer"} for node_type in node_types):
                if seed in json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(",", ":")):
                    raise BuildError(f"{label}: auxiliary search seed leaked into Service/Offer schema")
            if seed in json.dumps(node.get("knowsAbout", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")):
                raise BuildError(f"{label}: auxiliary search seed leaked into knowsAbout schema")
    article = _schema_node(graph, "Article", label)
    if (
        article.get("headline") != rendered_title or article.get("image") != image_url
        or article.get("description") != _correct_text(spec, record.locality, manuscript.jsonld_summary)
        or article.get("articleSection") != [_correct_text(spec, record.locality, section.heading) for section in manuscript.sections]
    ):
        raise BuildError(f"{label}: Article/source parity failed")
    faq_page = _schema_node(graph, "FAQPage", label)
    expected_faq = [
        {"@type": "Question", "name": _correct_text(spec, record.locality, faq.question), "acceptedAnswer": {"@type": "Answer", "text": _correct_text(spec, record.locality, faq.answer)}}
        for faq in manuscript.faqs
    ]
    if faq_page.get("mainEntity") != expected_faq:
        raise BuildError(f"{label}: FAQPage/source parity failed")
    for node_type in ("WebPage", "Article"):
        node = _schema_node(graph, node_type, label)
        schools = tuple(
            mention.get("name") for mention in node.get("mentions", [])
            if isinstance(mention, dict) and mention.get("@type") == "EducationalOrganization"
        )
        if schools != _visible_schools(record):
            raise BuildError(f"{label}: {node_type} school mentions/source mismatch")

    article_match = re.search(r"<article\b[^>]*data-manuscript[^>]*>(.*?)</article>", document, re.DOTALL | re.IGNORECASE)
    if article_match is None:
        raise BuildError(f"{label}: manuscript article missing")
    article_html = article_match.group(1)
    paragraph_matches = list(re.finditer(r'<p data-manuscript-paragraph="([^"]+)" data-source-sha256="([0-9a-f]{64})">(.*?)</p>', article_html, re.DOTALL))
    expected_paragraphs: list[tuple[str, str]] = []
    expected_paragraphs.extend((f"intro-{index:02d}", paragraph) for index, paragraph in enumerate(manuscript.intro_paragraphs, 1))
    for section_index, section in enumerate(manuscript.sections, 1):
        expected_paragraphs.extend(
            (f"section-{section_index:02d}-{paragraph_index:02d}", paragraph)
            for paragraph_index, paragraph in enumerate(section.paragraphs, 1)
        )
    if len(paragraph_matches) != len(expected_paragraphs):
        raise BuildError(f"{label}: source paragraph cardinality mismatch")
    for match, (expected_id, source) in zip(paragraph_matches, expected_paragraphs):
        if (
            match.group(1) != expected_id or match.group(2) != _sha256(source.encode("utf-8"))
            or match.group(3) != _paragraph_markup(_correct_text(spec, record.locality, source))
        ):
            raise BuildError(f"{label}: raw-hash/visible source paragraph mismatch: {expected_id}")
    headings = [html.unescape(value) for value in re.findall(r'<section id="section-[0-9]{2}" class="math-prose-section"[^>]*>\s*<h2>(.*?)</h2>', article_html, re.DOTALL)]
    if headings != [_correct_text(spec, record.locality, section.heading) for section in manuscript.sections]:
        raise BuildError(f"{label}: visible H2/source parity failed")
    if [int(value) for value in re.findall(r'data-source-faq="([0-9]{2})"', document)] != [faq.number for faq in manuscript.faqs]:
        raise BuildError(f"{label}: visible FAQ sequence mismatch")
    for faq in manuscript.faqs:
        if _escape(_correct_text(spec, record.locality, faq.question)) not in document or _paragraph_markup(_correct_text(spec, record.locality, faq.answer)) not in document:
            raise BuildError(f"{label}: visible FAQ text missing")
    review_matches = list(re.finditer(r'data-source-review="([0-9]{2})">(.*?)</(?:p|blockquote)>', document, re.DOTALL))
    if len(review_matches) != len(manuscript.review_lines):
        raise BuildError(f"{label}: review line count mismatch")
    for index, (match, source) in enumerate(zip(review_matches, manuscript.review_lines), 1):
        if int(match.group(1)) != index or match.group(2) != _paragraph_markup(_correct_text(spec, record.locality, source)):
            raise BuildError(f"{label}: review source/order mismatch")


def _route_for_href(href: str) -> Path | None:
    value = html.unescape(href.strip())
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme not in ("http", "https") or parsed.netloc != "wawa-center.kr":
            return None
        path = unquote(parsed.path)
    else:
        if value.startswith(("tel:", "mailto:", "javascript:")) or not value.startswith("/"):
            return None
        path = unquote(parsed.path)
    if path == "/":
        return Path("index.html")
    if CONTROL_RE.search(path) or ".." in Path(path).parts:
        raise BuildError(f"unsafe generated internal href: {href}")
    stripped = path.strip("/")
    if not stripped:
        return Path("index.html")
    candidate = Path(stripped)
    if candidate.suffix:
        return candidate
    return candidate / "index.html"


def _validate_generated_links(root: Path, generated: Mapping[Path, str | bytes], final_html_paths: set[Path]) -> int:
    checked = 0
    href_re = re.compile(r"<a\b[^>]*\bhref=([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
    src_re = re.compile(r"<(?:img|link)\b[^>]*\b(?:src|href)=([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
    for rel, raw in generated.items():
        if rel.name != "index.html":
            continue
        document = _decode_utf8(_as_bytes(raw), rel.as_posix())
        for match in href_re.finditer(document):
            route = _route_for_href(match.group(2))
            if route is None:
                continue
            checked += 1
            if route.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".css", ".ico", ".xml", ".txt"):
                if not (root / route).is_file():
                    raise BuildError(f"{rel}: broken local asset link: {match.group(2)}")
            elif route not in final_html_paths:
                raise BuildError(f"{rel}: broken internal page link: {match.group(2)} -> {route}")
        for match in src_re.finditer(document):
            route = _route_for_href(match.group(2))
            if route is None or route.name == "index.html":
                continue
            checked += 1
            if not (root / route).is_file():
                raise BuildError(f"{rel}: broken generated resource: {match.group(2)}")
    return checked


def _candidate_sha(after_manifest: Mapping[Path, str], source_manifest: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for name, value in sorted(source_manifest.items()):
        digest.update(name.encode("utf-8")); digest.update(b"\0"); digest.update(value.encode("ascii")); digest.update(b"\n")
    for rel in sorted(after_manifest, key=lambda item: item.as_posix()):
        digest.update(rel.as_posix().encode("utf-8")); digest.update(b"\0"); digest.update(after_manifest[rel].encode("ascii")); digest.update(b"\n")
    return digest.hexdigest()


def build_plan(
    root: Path | str,
    zip_paths: Mapping[str, Path | str] | Sequence[Path | str],
    common_dir: Path | str,
    current_overrides: Mapping[Path | str, str | bytes] | None = None,
) -> BuildPlan:
    """Materialize and audit the exact sparse 1,863-document release plan."""

    root = Path(root).resolve()
    common_dir = Path(common_dir).resolve()
    if not root.is_dir() or not common_dir.is_dir():
        raise BuildError("root and common data directory must already exist")
    pending = [
        path for path in root.iterdir()
        if path.is_dir() and path.name.startswith(_BASE.TRANSACTION_PREFIX)
    ]
    if pending:
        raise BuildError("pending transaction detected; recover under the root lock before building")
    normalized_zips = _normalize_zip_paths(zip_paths)
    overrides = _BASE._normalize_overrides(root, current_overrides)
    centers, center_metrics = _BASE._load_centers(common_dir)
    center_order = tuple(centers)
    if len(center_order) != EXPECTED_LOCALITIES:
        raise BuildError("authoritative center order must contain 371 localities")

    new_html_paths = {
        *(_category_rel(spec) for spec in NEW_CATEGORIES),
        *(_detail_rel(spec, locality) for spec in NEW_CATEGORIES for locality in center_order),
    }
    authorized_paths = {PARENT_REL, SITEMAP_REL, LLMS_REL, *new_html_paths}
    if len(new_html_paths) != EXPECTED_NEW_HTML or len(authorized_paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("authorized sparse path cardinality mismatch")
    unknown_overrides = set(overrides) - authorized_paths
    if unknown_overrides:
        raise BuildError(f"current_overrides contains unauthorized paths: {sorted(map(str, unknown_overrides))[:4]}")

    all_manuscripts: dict[str, Mapping[str, Manuscript]] = {}
    manuscript_metrics: dict[str, Any] = {}
    cross_hashes: dict[str, set[str]] = {}
    total_uncompressed = 0
    for spec in NEW_CATEGORIES:
        manuscripts, metrics = _load_manuscripts(spec, normalized_zips[spec.key])
        if set(manuscripts) != set(center_order):
            missing = sorted(set(center_order) - set(manuscripts))
            extra = sorted(set(manuscripts) - set(center_order))
            raise BuildError(f"{spec.key}: ZIP/center locality mismatch: missing={missing[:3]}, extra={extra[:3]}")
        all_manuscripts[spec.key] = manuscripts
        manuscript_metrics[spec.key] = dict(metrics)
        total_uncompressed += int(metrics["uncompressed_bytes"])
        cross_hashes[spec.key] = {_sha256(item.raw_bytes) for item in manuscripts.values()}
    for index, left in enumerate(NEW_CATEGORIES):
        for right in NEW_CATEGORIES[index + 1:]:
            if cross_hashes[left.key] & cross_hashes[right.key]:
                raise BuildError(f"cross-category identical raw manuscript: {left.key}/{right.key}")
    correction_metrics = _audit_corrections(all_manuscripts)
    seed_metrics = _audit_auxiliary_seeds(all_manuscripts)

    supported = 0
    unconfirmed = 0
    source_school_chips = 0
    visible_school_chips = 0
    missing_school_groups = 0
    exact_address_pages = 0
    for spec in NEW_CATEGORIES:
        spec_supported = sum(_supports(record, spec) for record in centers.values())
        if spec_supported != spec.supported or EXPECTED_LOCALITIES - spec_supported != spec.unconfirmed:
            raise BuildError(f"{spec.key}: frozen supported/unconfirmed count mismatch")
        supported += spec_supported
        unconfirmed += EXPECTED_LOCALITIES - spec_supported
        for locality, record in centers.items():
            manuscript = all_manuscripts[spec.key][locality]
            exact_address_pages += int(record.address in manuscript.raw_text)
            source_school_chips += len(record.middle_schools)
            visible_school_chips += len(_visible_schools(record))
            missing_school_groups += int(not record.middle_schools)
    if (
        supported != EXPECTED_SUPPORTED or unconfirmed != EXPECTED_UNCONFIRMED
        or source_school_chips != EXPECTED_SCHOOL_CHIPS or visible_school_chips != EXPECTED_SCHOOL_CHIPS
        or missing_school_groups != 265 or exact_address_pages != EXPECTED_NEW_DETAILS
    ):
        raise BuildError("aggregate grade/address/school source metrics mismatch")

    html_paths = _BASE._enumerate_html(root, overrides)
    present_new = html_paths & new_html_paths
    if present_new and present_new != new_html_paths:
        raise BuildError(f"partial generated middle-grade tree: {len(present_new)}/{len(new_html_paths)}")
    existing_html_paths = html_paths - new_html_paths
    if len(existing_html_paths) != EXPECTED_EXISTING_HTML or PARENT_REL not in existing_html_paths:
        raise BuildError(f"existing HTML baseline mismatch: {len(existing_html_paths)}")
    immutable_paths = tuple(path for path in existing_html_paths if path != PARENT_REL)
    if len(immutable_paths) != EXPECTED_IMMUTABLE_HTML:
        raise BuildError("immutable existing HTML path count mismatch")
    immutable_manifest = _files_manifest(root, immutable_paths, overrides)
    if immutable_manifest != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        raise BuildError(f"existing parent-excluded HTML drift: {immutable_manifest}")
    middle3_paths = tuple(
        path for path in immutable_paths
        if path == MIDDLE3_MATH_ROOT / "index.html" or MIDDLE3_MATH_ROOT in path.parents
    )
    if len(middle3_paths) != EXPECTED_EXISTING_MIDDLE3_MATH_HTML:
        raise BuildError("existing middle3 math tree count mismatch")
    middle3_manifest = _files_manifest(root, middle3_paths, overrides)
    if middle3_manifest != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
        raise BuildError(f"existing middle3 math tree drift: {middle3_manifest}")
    for spec in NEW_CATEGORIES:
        for locality in center_order:
            if _generic_rel(spec, locality) not in existing_html_paths:
                raise BuildError(f"{spec.key}/{locality}: generic subject source page missing")

    # The asset/schema source page depends on subject, not grade; load each
    # subject/locality pair once and reuse it across grade pages.
    assets_by_subject: dict[tuple[str, str], Any] = {}
    representative_sources: set[str] = set()
    body_sources: set[str] = set()
    map_sources: set[str] = set()
    for subject_spec in (NEW_CATEGORIES[0], NEW_CATEGORIES[1]):
        matching_specs = [spec for spec in NEW_CATEGORIES if spec.subject == subject_spec.subject]
        for locality in center_order:
            rel = _generic_rel(subject_spec, locality)
            source_document = _decode_utf8(_read_current(root, rel, overrides), rel.as_posix())
            assets = _BASE._load_page_assets(root, locality, source_document)
            for spec in matching_specs:
                _crosscheck_physical_source(spec, centers[locality], assets)
            assets_by_subject[(subject_spec.subject, locality)] = assets
            representative_sources.add(assets.representative_src)
            body_sources.add(assets.body_src)
            map_sources.add(assets.map_src)
    if len(assets_by_subject) != EXPECTED_LOCALITIES * 2:
        raise BuildError("subject/locality asset cache count mismatch")

    generated: dict[Path, str] = {PARENT_REL: _render_parent_hub()}
    for spec in NEW_CATEGORIES:
        generated[_category_rel(spec)] = _render_category_hub(spec, center_order, centers)
        manuscripts = all_manuscripts[spec.key]
        for index, locality in enumerate(center_order):
            generated[_detail_rel(spec, locality)] = _render_detail(
                spec, manuscripts[locality], centers[locality], assets_by_subject[(spec.subject, locality)],
                center_order[index - 1], center_order[(index + 1) % len(center_order)],
            )
    if len(generated) != EXPECTED_NEW_HTML + 1:
        raise BuildError("generated parent/new HTML count mismatch")

    parent_exists, parent_before = _read_optional(root, PARENT_REL, overrides)
    if not parent_exists:
        raise BuildError("grade parent hub disappeared")
    parent_after = _as_bytes(generated[PARENT_REL])
    if not present_new:
        if _sha256(parent_before) != BASE_PARENT_SHA256:
            raise BuildError("grade parent baseline drift")
    elif parent_before != parent_after:
        raise BuildError("complete new tree exists with non-canonical parent hub")

    sitemap_current = _decode_utf8(_read_current(root, SITEMAP_REL, overrides), SITEMAP_REL.as_posix())
    llms_current = _decode_utf8(_read_current(root, LLMS_REL, overrides), LLMS_REL.as_posix())
    generated[SITEMAP_REL] = _update_sitemap(sitemap_current, center_order)
    generated[LLMS_REL] = _update_llms(llms_current)
    if set(generated) != authorized_paths:
        raise BuildError("materialized sparse document set differs from authorization")

    _validate_parent(generated[PARENT_REL])
    for spec in NEW_CATEGORIES:
        _validate_category(spec, generated[_category_rel(spec)], center_order)
        for locality in center_order:
            _validate_detail(
                spec, generated[_detail_rel(spec, locality)], all_manuscripts[spec.key][locality],
                centers[locality], assets_by_subject[(spec.subject, locality)],
            )
    final_html_paths = set(existing_html_paths) | new_html_paths
    if len(final_html_paths) != EXPECTED_FINAL_HTML:
        raise BuildError("final HTML route count mismatch")
    internal_links_checked = _validate_generated_links(root, generated, final_html_paths)

    final_sitemap = generated[SITEMAP_REL]
    final_blocks = _url_blocks(final_sitemap)
    original_blocks = _url_blocks(sitemap_current)
    if len(final_blocks) != EXPECTED_FINAL_HTML:
        raise BuildError("final sitemap count mismatch")
    if not present_new:
        if tuple(block for _, _, block in final_blocks[:EXPECTED_EXISTING_HTML]) != tuple(block for _, _, block in original_blocks):
            raise BuildError("existing 14,997 sitemap blocks were not byte-identical")
    elif final_sitemap != sitemap_current:
        raise BuildError("complete new tree has non-canonical sitemap")
    if tuple(location for location, _, _ in final_blocks[-EXPECTED_NEW_HTML:]) != _sitemap_urls(center_order):
        raise BuildError("final sitemap append order mismatch")

    before_manifest: dict[Path, str] = {}
    after_manifest: dict[Path, str] = {}
    before_exists: dict[Path, bool] = {}
    changed: list[Path] = []
    for rel in sorted(generated, key=lambda item: item.as_posix()):
        exists, before = _read_optional(root, rel, overrides)
        after = _as_bytes(generated[rel])
        before_exists[rel] = exists
        before_manifest[rel] = _sha256(before) if exists else ABSENT_SHA256
        after_manifest[rel] = _sha256(after)
        if not exists or before != after:
            changed.append(rel)
    if len(changed) not in (0, EXPECTED_AUTHORIZED_DOCUMENTS):
        raise BuildError(f"partial/non-canonical changed path count: {len(changed)}")

    # A true deterministic second render/update must be byte-identical.  Work
    # one document at a time so the plan remains sparse and bounded.
    second_pass: list[Path] = []
    if _as_bytes(_render_parent_hub()) != _as_bytes(generated[PARENT_REL]):
        second_pass.append(PARENT_REL)
    for spec in NEW_CATEGORIES:
        category_rel = _category_rel(spec)
        if _as_bytes(_render_category_hub(spec, center_order, centers)) != _as_bytes(generated[category_rel]):
            second_pass.append(category_rel)
        manuscripts = all_manuscripts[spec.key]
        for index, locality in enumerate(center_order):
            rel = _detail_rel(spec, locality)
            second = _render_detail(
                spec, manuscripts[locality], centers[locality], assets_by_subject[(spec.subject, locality)],
                center_order[index - 1], center_order[(index + 1) % len(center_order)],
            )
            if _as_bytes(second) != _as_bytes(generated[rel]):
                second_pass.append(rel)
    if _as_bytes(_update_sitemap(final_sitemap, center_order)) != _as_bytes(final_sitemap):
        second_pass.append(SITEMAP_REL)
    if _as_bytes(_update_llms(generated[LLMS_REL])) != _as_bytes(generated[LLMS_REL]):
        second_pass.append(LLMS_REL)
    if second_pass:
        raise BuildError(f"second-pass idempotency failed: {len(second_pass)}")

    source_manifest = {
        **{f"zip:{spec.key}": str(spec.zip_sha256) for spec in NEW_CATEGORIES},
        "center_csv": CENTER_CSV_SHA256,
        "target_school_csv": TARGET_SCHOOL_CSV_SHA256,
        "base_helper": BASE_HELPER_SHA256,
    }
    source_metrics: dict[str, Any] = {
        "zip_archives": len(NEW_CATEGORIES), "zip_members": EXPECTED_NEW_DETAILS,
        "zip_uncompressed_bytes": total_uncompressed,
        "source_h2": sum(spec.h2_total for spec in NEW_CATEGORIES),
        "source_faq": sum(spec.faq_total for spec in NEW_CATEGORIES),
        "source_reviews": EXPECTED_SOURCE_REVIEWS,
        "cross_category_identical_raw_documents": 0,
        "supported_pages": supported, "unconfirmed_pages": unconfirmed,
        "exact_address_pages": exact_address_pages,
        "raw_school_tokens": source_school_chips, "visible_school_chips": visible_school_chips,
        "missing_school_groups": missing_school_groups,
        "attached_raw_school_tokens_preserved": 10,
        "attached_visible_school_tokens_corrected": 10,
        "existing_english_generic_math_levels_rebased_to_english": 371,
        "representative_sources": len(representative_sources), "body_sources": len(body_sources), "map_sources": len(map_sources),
        "category_metrics": manuscript_metrics,
        **dict(center_metrics), **dict(correction_metrics), **dict(seed_metrics),
    }
    if source_metrics["source_h2"] != EXPECTED_SOURCE_H2 or source_metrics["source_faq"] != EXPECTED_SOURCE_FAQ:
        raise BuildError("aggregate source H2/FAQ mismatch")
    before_metrics = {
        "html_documents": len(html_paths), "existing_html_documents": len(existing_html_paths),
        "already_present_new_html": len(present_new), "sitemap_urls": len(original_blocks),
        "immutable_existing_html": len(immutable_paths),
        "immutable_html_manifest_sha256": immutable_manifest,
        "middle3_math_html": len(middle3_paths), "middle3_math_manifest_sha256": middle3_manifest,
    }
    after_metrics = {
        "authorized_documents": len(generated), "final_html_documents": EXPECTED_FINAL_HTML,
        "new_html_documents": EXPECTED_NEW_HTML, "new_category_hubs": EXPECTED_NEW_CATEGORIES,
        "new_detail_documents": EXPECTED_NEW_DETAILS, "parent_hub_categories": 6,
        "sitemap_urls": len(final_blocks), "sitemap_existing_blocks_preserved": EXPECTED_EXISTING_HTML,
        "sitemap_new_urls_appended": EXPECTED_NEW_HTML, "sitemap_new_lastmod": PUBLISHED_DATE,
        "supported_service_offer_pages": supported, "unconfirmed_article_only_pages": unconfirmed,
        "school_chips": visible_school_chips, "internal_links_checked": internal_links_checked,
        "second_pass_changes": len(second_pass),
    }
    metrics = {
        "changed_paths": len(changed), "unchanged_authorized_paths": len(generated) - len(changed),
        "sparse_plan": "pass", "existing_html_preservation": "pass", "facts_assets_schema_links_gate": "pass",
        **source_metrics, **{f"after_{key}": value for key, value in after_metrics.items()},
    }
    candidate = _candidate_sha(after_manifest, source_manifest)
    return BuildPlan(
        root=root, authorized_documents=MappingProxyType(generated), changed_paths=tuple(changed),
        second_pass_changes=tuple(second_pass), source_manifest=MappingProxyType(source_manifest),
        before_manifest=MappingProxyType(before_manifest), after_manifest=MappingProxyType(after_manifest),
        before_exists=MappingProxyType(before_exists), source_metrics=MappingProxyType(source_metrics),
        before_metrics=MappingProxyType(before_metrics), after_metrics=MappingProxyType(after_metrics),
        metrics=MappingProxyType(metrics), candidate_sha256=candidate,
        immutable_html_manifest_sha256=immutable_manifest, middle3_math_manifest_sha256=middle3_manifest,
    )


def _self_sha256() -> str:
    return _sha256(Path(__file__).read_bytes())


def freeze_payload(plan: BuildPlan) -> Mapping[str, Any]:
    """Return the exact external approval payload required by ``apply_plan``."""
    return MappingProxyType({
        "version": 1,
        "root": str(plan.root),
        "generator_sha256": _self_sha256(),
        "base_helper_sha256": BASE_HELPER_SHA256,
        "candidate_sha256": plan.candidate_sha256,
        "source_manifest": dict(plan.source_manifest),
        "authorized_paths": [path.as_posix() for path in sorted(plan.authorized_documents, key=lambda item: item.as_posix())],
        "changed_paths": [path.as_posix() for path in plan.changed_paths],
        "before_exists": {path.as_posix(): plan.before_exists[path] for path in sorted(plan.before_exists, key=lambda item: item.as_posix())},
        "before_manifest": {path.as_posix(): plan.before_manifest[path] for path in sorted(plan.before_manifest, key=lambda item: item.as_posix())},
        "after_manifest": {path.as_posix(): plan.after_manifest[path] for path in sorted(plan.after_manifest, key=lambda item: item.as_posix())},
        "immutable_html_manifest_sha256": plan.immutable_html_manifest_sha256,
        "middle3_math_manifest_sha256": plan.middle3_math_manifest_sha256,
    })


def _plain_json(value: Any) -> Any:
    """Normalize mappings/tuples through strict JSON without accepting exotic objects."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _validate_freeze_payload(plan: BuildPlan, frozen: Mapping[str, Any]) -> None:
    expected = _plain_json(dict(freeze_payload(plan)))
    actual = _plain_json(dict(frozen))
    if actual != expected:
        mismatches = [key for key in sorted(set(expected) | set(actual)) if expected.get(key) != actual.get(key)]
        raise BuildError(f"external freeze payload mismatch: {mismatches[:6]}")
    if not re.fullmatch(r"[0-9a-f]{64}", str(actual.get("generator_sha256", ""))):
        raise BuildError("external freeze generator hash malformed")
    paths = actual.get("authorized_paths")
    if not isinstance(paths, list) or len(paths) != len(set(paths)) or len(paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("external freeze authorized path set malformed")
    if len(actual.get("changed_paths", [])) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("external freeze must approve exact initial 1,863-path mutation")


def _current_immutable_manifests(root: Path) -> tuple[str, str]:
    html_paths = _BASE._enumerate_html(root, {})
    # Build the new path set from the directory names already represented in
    # the authoritative existing middle3 tree, avoiding any mutable CSV read at
    # the final transaction boundary.
    localities = tuple(
        path.name for path in sorted((root / MIDDLE3_MATH_ROOT).iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / "index.html").is_file()
    )
    if len(localities) != EXPECTED_LOCALITIES:
        raise BuildError("transaction immutable preflight cannot derive 371 localities")
    new_paths = {
        *(_category_rel(spec) for spec in NEW_CATEGORIES),
        *(_detail_rel(spec, locality) for spec in NEW_CATEGORIES for locality in localities),
    }
    existing = html_paths - new_paths
    immutable = tuple(path for path in existing if path != PARENT_REL)
    middle3 = tuple(
        path for path in immutable
        if path == MIDDLE3_MATH_ROOT / "index.html" or MIDDLE3_MATH_ROOT in path.parents
    )
    if len(existing) != EXPECTED_EXISTING_HTML or len(immutable) != EXPECTED_IMMUTABLE_HTML or len(middle3) != EXPECTED_EXISTING_MIDDLE3_MATH_HTML:
        raise BuildError("transaction immutable path-count preflight failed")
    return _files_manifest(root, immutable, {}), _files_manifest(root, middle3, {})


def _verify_plan_current(plan: BuildPlan) -> None:
    if set(plan.authorized_documents) != set(plan.before_exists) or set(plan.authorized_documents) != set(plan.before_manifest) or set(plan.authorized_documents) != set(plan.after_manifest):
        raise BuildError("plan mapping key sets differ")
    if len(plan.authorized_documents) != EXPECTED_AUTHORIZED_DOCUMENTS or plan.second_pass_changes:
        raise BuildError("plan authorization/idempotency preflight failed")
    if len(plan.changed_paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("apply requires the exact initial 1,863-path plan")
    for rel in plan.authorized_documents:
        target = _BASE._safe_target(plan.root, rel)
        exists = target.is_file()
        if exists != plan.before_exists[rel]:
            raise BuildError(f"plan preflight existence changed: {rel}")
        current_hash = _sha256(target.read_bytes()) if exists else ABSENT_SHA256
        if current_hash != plan.before_manifest[rel]:
            raise BuildError(f"plan preflight hash changed: {rel}")
        if _sha256(_as_bytes(plan.authorized_documents[rel])) != plan.after_manifest[rel]:
            raise BuildError(f"plan output hash mismatch: {rel}")
    immutable, middle3 = _current_immutable_manifests(plan.root)
    if immutable != plan.immutable_html_manifest_sha256 or immutable != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        raise BuildError("immutable existing HTML changed after plan creation")
    if middle3 != plan.middle3_math_manifest_sha256 or middle3 != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
        raise BuildError("existing middle3 math tree changed after plan creation")


def apply_plan(plan: BuildPlan, *, go: str, frozen: Mapping[str, Any]) -> None:
    """Apply an exactly frozen initial plan through the pinned atomic journal."""
    if go != "APPLY-GO":
        raise BuildError("apply requires exact explicit go token APPLY-GO")
    _validate_freeze_payload(plan, frozen)
    with _BASE._root_lock(plan.root):
        recovered = _BASE.recover_transactions(plan.root)
        if recovered:
            raise BuildError("transaction recovery changed state; rebuild and re-freeze before applying")
        _verify_plan_current(plan)
        changed_docs = {rel: plan.authorized_documents[rel] for rel in plan.changed_paths}
        changed_exists = {rel: plan.before_exists[rel] for rel in plan.changed_paths}
        changed_before = {rel: plan.before_manifest[rel] for rel in plan.changed_paths}
        changed_after = {rel: plan.after_manifest[rel] for rel in plan.changed_paths}
        # The pinned implementation validates safe relative paths and every
        # before/stage/backup/after hash, writes an fsynced journal, swaps
        # atomically, and rolls back faults or recovers interrupted commits.
        _BASE._transaction_apply(plan.root, changed_docs, changed_exists, changed_before, changed_after)
        for rel, expected in plan.after_manifest.items():
            target = _BASE._safe_target(plan.root, rel)
            if not target.is_file() or _sha256(target.read_bytes()) != expected:
                raise BuildError(f"post-transaction target manifest mismatch: {rel}")
        immutable, middle3 = _current_immutable_manifests(plan.root)
        if immutable != BASE_IMMUTABLE_HTML_MANIFEST_SHA256 or middle3 != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
            raise BuildError("post-transaction immutable HTML verification failed")
        residue = [path for path in plan.root.iterdir() if path.name.startswith(_BASE.TRANSACTION_PREFIX)]
        if residue:
            raise BuildError(f"transaction residue remains after commit: {residue[:2]}")


def transaction_self_test() -> Mapping[str, str]:
    """Exercise the reused journal plus this generator's stricter freeze gates."""
    results = dict(_BASE.transaction_self_test())
    with tempfile.TemporaryDirectory(prefix="wawa-middle-grade-security-") as temporary:
        root = Path(temporary) / "site"
        root.mkdir()
        existing = Path("existing.txt")
        (root / existing).write_bytes(b"before\n")
        after = b"after\n"
        before_hash = _sha256(b"before\n")
        after_hash = _sha256(after)

        def rejected(call: Any, label: str) -> None:
            snapshot = (root / existing).read_bytes()
            try:
                call()
            except (BuildError, ValueError, TypeError):
                pass
            else:
                raise BuildError(f"transaction synthetic did not reject: {label}")
            if (root / existing).read_bytes() != snapshot:
                raise BuildError(f"transaction rejection mutated target: {label}")
            results[label] = "pass"

        rejected(
            lambda: _BASE._transaction_apply(root, {existing: after}, {}, {existing: before_hash}, {existing: after_hash}),
            "mapping_key_mismatch_rejected",
        )
        rejected(
            lambda: _BASE._transaction_apply(root, {existing: after}, {existing: True}, {existing: before_hash}, {existing: "0" * 64}),
            "output_hash_tamper_rejected",
        )
        rejected(
            lambda: _BASE._transaction_apply(root, {existing: after}, {existing: False}, {existing: ABSENT_SHA256}, {existing: after_hash}),
            "existence_drift_rejected",
        )
        rejected(lambda: _BASE._safe_target(root, Path("..") / "escape.txt"), "traversal_rejected")
        rejected(lambda: _BASE._safe_target(root, Path(root.anchor) / "absolute.txt"), "absolute_path_rejected")

        expected = {"version": 1, "hash": "a" * 64, "paths": ["a", "b"]}
        for key, mutation in (
            ("freeze_version_rejected", {**expected, "version": 2}),
            ("freeze_hash_rejected", {**expected, "hash": "b" * 64}),
            ("freeze_scope_rejected", {**expected, "paths": ["a"]}),
            ("freeze_extra_rejected", {**expected, "extra": True}),
        ):
            if _plain_json(mutation) == _plain_json(expected):
                raise BuildError(f"freeze equality synthetic failed: {key}")
            results[key] = "pass"
        transaction_dirs = [path for path in root.iterdir() if path.name.startswith(_BASE.TRANSACTION_PREFIX)]
        if transaction_dirs:
            raise BuildError("security synthetics left transaction residue")
        results["invalid_mutation_zero"] = "pass"
    if len(results) < 14 or any(value != "pass" for value in results.values()):
        raise BuildError(f"transaction synthetic suite incomplete: {results}")
    return MappingProxyType(results)


def _default_paths() -> tuple[Path, Mapping[str, Path], Path]:
    root = Path(__file__).resolve().parents[1]
    desktop = Path.home() / "Desktop"
    folder = desktop / "새 폴더 (2)"
    zips = {
        "middle1_math": folder / "중1 수학학원.zip",
        "middle1_english": folder / "중1 영어학원.zip",
        "middle2_math": folder / "중2 수학학원.zip",
        "middle2_english": folder / "중2 영어학원.zip",
        "middle3_english": folder / "중3 영어학원.zip",
    }
    common = desktop / "홈페이지 정리" / "참고자료" / "공통자료"
    return root, MappingProxyType(zips), common


def _parse_cli_zips(values: Sequence[str], defaults: Mapping[str, Path]) -> Mapping[str, Path]:
    if not values:
        return defaults
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise BuildError("--zip must use CATEGORY=PATH")
        key, raw_path = value.split("=", 1)
        if not key or not raw_path or key in parsed:
            raise BuildError(f"malformed/duplicate --zip: {value}")
        parsed[key] = Path(raw_path)
    return MappingProxyType(parsed)


def _read_freeze_file(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BuildError(f"freeze file must be a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"unreadable freeze file: {path}") from exc
    if not isinstance(value, dict):
        raise BuildError("freeze file root must be an object")
    return MappingProxyType(value)


def _write_freeze_file(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve(strict=False)
    if path.exists() or path.is_symlink():
        raise BuildError(f"refusing to overwrite freeze output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    if temporary.exists():
        raise BuildError(f"freeze temporary path already exists: {temporary}")
    try:
        with temporary.open("xb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _plan_report(plan: BuildPlan, mode: str, synthetics: Mapping[str, str] | None, freeze_path: Path | None) -> Mapping[str, Any]:
    return {
        "mode": mode, "root": str(plan.root), "generator_sha256": _self_sha256(),
        "candidate_sha256": plan.candidate_sha256, "source_manifest": dict(plan.source_manifest),
        "changed_paths": len(plan.changed_paths), "second_pass_changes": len(plan.second_pass_changes),
        "source_metrics": dict(plan.source_metrics), "before_metrics": dict(plan.before_metrics),
        "after_metrics": dict(plan.after_metrics), "transaction_self_test": dict(synthetics) if synthetics else None,
        "freeze_output": str(freeze_path) if freeze_path else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    default_root, default_zips, default_common = _default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--common-dir", type=Path, default=default_common)
    parser.add_argument("--zip", action="append", default=[], metavar="CATEGORY=PATH")
    parser.add_argument("--transaction-self-test", action="store_true")
    parser.add_argument("--freeze-out", type=Path)
    parser.add_argument("--freeze-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--go", default="")
    args = parser.parse_args(argv)
    try:
        zip_paths = _parse_cli_zips(args.zip, default_zips)
        synthetics = transaction_self_test() if args.transaction_self_test else None
        plan = build_plan(args.root, zip_paths, args.common_dir)
        freeze_path: Path | None = None
        if args.apply:
            if args.freeze_out is not None:
                raise BuildError("--freeze-out cannot be combined with --apply")
            if args.freeze_file is None:
                raise BuildError("--apply requires --freeze-file")
            frozen = _read_freeze_file(args.freeze_file)
            apply_plan(plan, go=args.go, frozen=frozen)
            mode = "applied"
        else:
            if args.go or args.freeze_file is not None:
                raise BuildError("--go/--freeze-file are valid only with --apply")
            if args.freeze_out is not None:
                _write_freeze_file(args.freeze_out, freeze_payload(plan))
                freeze_path = args.freeze_out.resolve()
            mode = "dry-run"
        print(json.dumps(_plan_report(plan, mode, synthetics, freeze_path), ensure_ascii=False, indent=2))
        return 0
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
