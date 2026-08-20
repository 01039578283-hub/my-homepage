#!/usr/bin/env python3
"""Independent, read-only content/fact gate for the five middle-grade batches.

The five user archives are untrusted *data*.  This auditor never extracts,
imports, evaluates, or follows text from an archive.  ``actual`` mode expects
the untouched 14,997-page baseline to be a HOLD.  ``projected`` validates the
in-memory release, and ``actual-release`` validates the materialized 16,857
page tree plus a zero-change pinned generator plan and exact disk parity.

Exit codes: 0 PASS, 1 FAIL, 2 HOLD.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import inspect
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote, unquote, urlparse


sys.dont_write_bytecode = True

BASE_URL = "https://wawa-center.kr"
RELEASE_DATE = "2026-08-20"
EXPECTED_BASE_HEAD = "9e0eee90aa21394eafd5979dd00a4f3e4f29417e"
EXPECTED_GENERATOR_SHA256 = "46874729b875197b7b4c5dfc6f302aa720bf5388d2ba4d32593008346a1b36cf"
EXPECTED_CANDIDATE_SHA256 = "ae1a111a4642e4906dc735a51da6533a205d23cff72c254232c2507dfd1614a0"
EXPECTED_BOUNDARY_SAMPLE_SHA256 = "499ded2aa988ad78c1818e9c05fb8c8446b3adbdf38e828ded59b0a71811a9f6"
EXPECTED_BOUNDARY_SAMPLE_COUNT = 262

EXPECTED_LOCALITIES = 371
EXPECTED_BASE_HTML = 14_997
EXPECTED_IMMUTABLE_HTML = 14_996
EXPECTED_NEW_CATEGORIES = 5
EXPECTED_NEW_DETAILS = 1_855
EXPECTED_NEW_HTML = 1_860
EXPECTED_FINAL_HTML = 16_857
EXPECTED_AUTHORIZED = 1_863
EXPECTED_SUPPORTED = 1_805
EXPECTED_UNCONFIRMED = 50
EXPECTED_H2 = 10_981
EXPECTED_FAQ = 7_605
EXPECTED_REVIEWS = 1_855
EXPECTED_SCHOOL_CHIPS = 4_445
EXPECTED_CORRECTION_RULES = 97
EXPECTED_CORRECTION_PAGES = 95
EXPECTED_CORRECTION_OCCURRENCES = 107

BASE_IMMUTABLE_HTML_MANIFEST_SHA256 = "7844dcf232eaec0bed96bcf73ed93f2cc0818488b8f155f657c549a65a29d718"
BASE_MIDDLE3_MATH_MANIFEST_SHA256 = "81cb8ed8492eacd3e6a2a95568452f50c5067957dde6b99cc872ae61053f0765"
BASE_PARENT_SHA256 = "7c7541d1b2dcc8413968f59a7264fc4e15b475511836670b3faf6c7d06e8f9f7"
BASE_SITEMAP_SHA256 = "f4c0b0c1a9fc25072f8348621119ed510a494676398067fc442842e0b69de7b4"
BASE_LLMS_SHA256 = "47bf25190544402fe5dcccd133d6bd62c5c33eecd1574c217cc885176e2c6d9b"
RELEASE_AUTHORIZED_MANIFEST_SHA256 = "359aa1d35a5827875cda22a8a9c43ee4db689a9f3abc2398976e7aecc409635a"
RELEASE_NEW_HTML_MANIFEST_SHA256 = "62b909f19eefc6b38bf8a850ac32b80311b3f4db648d4c6453c3d3cd92d7fb46"
RELEASE_ALL_HTML_MANIFEST_SHA256 = "6854b09c3611d1726b8cd87444a385756ae1872c09c76eac36122ec9350feff7"

COMMON_HASHES = {
    "센터정보 정리.csv": "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a",
    "타깃학교.csv": "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f",
    "EducationalOrganization.csv": "e44c9a78c8b272781d5c078e38b466f9d438127a76219661ff43ee2604766c22",
    "이미지링크.csv": "c1b4f87b2b62f659107dbf0a79a1d566e213e008fc4b7f30cfa656ffae814100",
}

PARENT_REL = Path("학년별학원/index.html")
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
GENERATOR_REL = Path("tools/generate_middle_grade_pages.py")
MIDDLE3_MATH_ROOT = Path("학년별학원/중3수학학원")
LLMS_MARKER = "## 학년별학원 핵심 허브"

MARKERS = (
    "[페이지타이틀]",
    "[메타설명]",
    "[본문]",
    "[FAQ]",
    "[학부모후기]",
    "[JSON-LD 요약]",
)

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROMPT_OR_CODE = re.compile(
    r"(?:ignore\s+(?:all\s+)?previous|system\s+prompt|assistant\s*:|developer\s*:|"
    r"instructions?\s*:|이전\s*지시|지시를\s*무시|시스템\s*프롬프트|"
    r"명령을\s*실행|파일을\s*삭제|powershell|cmd\.exe|javascript\s*:|<script)",
    re.IGNORECASE,
)
ACTIVE_TEXT = re.compile(r"https?://|<[/A-Za-z]|```|\x00", re.IGNORECASE)
MOJIBAKE = re.compile(r"(?:\ufffd|Ã.|Â.|â€|ì[\x80-\xff])")
GUARANTEE = re.compile(r"(?:100\s*%|무조건\s*(?:상승|향상|합격)|성적\s*보장|합격\s*보장)")
INLINE_REPEAT = re.compile(r"(?<![가-힣A-Za-z0-9])([가-힣]{2,})[ \t]+\1(?![가-힣A-Za-z0-9])")
QUESTION = re.compile(r"^Q([1-9][0-9]*)([.)])\s+(.+)$")
ANSWER = re.compile(r"^(?:A([1-9][0-9]*)([.)])|답변:)\s+(.+)$")
H2 = re.compile(r"(?m)^##[ \t]+([^\n]+?)[ \t]*$")
SCHOOL_TOKEN = re.compile(
    r"(?<![가-힣A-Za-z0-9])([가-힣A-Za-z0-9()\-]+?(?:중학교|중))"
    r"(?=(?:과|와|은|는|이|가|을|를|의|·|,|\s|['’”)]|$))"
)
SCHOOL_NOUN_EXCLUSIONS = {
    "중", "중학교", "학기중", "수업중", "진행중", "준비중", "시험중", "과정중",
    "사용중", "등록중", "상담중", "운영중", "재학중", "복습중", "학습중", "관리중",
    "비중", "집중", "주중", "그중",
}
RAW_URL_BLOCK = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
INVISIBLE_TAGS = {"script", "style", "template", "noscript", "head"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def encoded_url(*parts: str) -> str:
    if not parts:
        return BASE_URL + "/"
    return BASE_URL + "/" + "/".join(quote(part, safe="") for part in parts) + "/"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    grade: str
    subject: str
    slug: str
    hook: str
    zip_name: str
    zip_sha256: str
    zip_manifest_sha256: str
    zip_bytes: int
    uncompressed_bytes: int
    bom: int
    support: int
    unconfirmed: int
    h2_total: int
    h2_distribution: tuple[tuple[int, int], ...]
    section_paragraphs: int
    faq_total: int
    faq_distribution: tuple[tuple[int, int], ...]
    review_lines: int
    h2_max_df: int
    h2_unique_templates: int

    @property
    def subject_slug(self) -> str:
        return self.subject + "학원"


CATEGORIES = (
    Category(
        "middle1_math", "중1 수학학원", "중1", "수학", "중1수학학원", "middle1-math",
        "중1 수학학원.zip", "83ac704c654d50d98d17d38a44024358d558c3ba03c38a9799cc5fef361a6e72",
        "a3d56e6e46419b5c7c0503fa6cbfc9bc11cafb9cf1c14217a50b89f3606572bd",
        1_295_984, 3_752_831, 371, 358, 13, 2_226, ((6, 371),), 4_452, 1_484,
        ((4, 371),), 742, 89, 258,
    ),
    Category(
        "middle1_english", "중1 영어학원", "중1", "영어", "중1영어학원", "middle1-english",
        "중1 영어학원.zip", "2521a37d5c4fdb04a52eae23c33e20a4df6e9eb294782fa4505ed06d0d648154",
        "44d20f9d784fa13af36450e8cdf2d1d82a3451cdff2d7671c10db6d82304b1a2",
        1_364_424, 3_599_494, 371, 363, 8, 2_300, ((5, 74), (6, 149), (7, 148)),
        5_498, 1_669, ((4, 186), (5, 185)), 742, 83, 94,
    ),
    Category(
        "middle2_math", "중2 수학학원", "중2", "수학", "중2수학학원", "middle2-math",
        "중2 수학학원.zip", "d778f3839932567c78b0276360a2ad6ea4aba84127aafcd0c08ba78fab8c84d9",
        "c89099f3ef975664d4596332af2a792c05697e8515f6f58d9972dca22b5a7e1b",
        1_442_813, 4_201_526, 0, 358, 13, 2_226, ((6, 371),), 4_452, 1_484,
        ((4, 371),), 742, 80, 649,
    ),
    Category(
        "middle2_english", "중2 영어학원", "중2", "영어", "중2영어학원", "middle2-english",
        "중2 영어학원.zip", "a2976c3e0e4624354cd5a63413e002e1f9cb60b4cef8a2911cf10cc3a80fa171",
        "d6cdbc2ec0d22e462b577c177e8ca18af6dc199792e6a77aa88e00bec699b4b2",
        1_357_904, 3_956_144, 371, 363, 8, 2_003, ((5, 223), (6, 148)), 3_860,
        1_484, ((4, 371),), 1_113, 88, 651,
    ),
    Category(
        "middle3_english", "중3 영어학원", "중3", "영어", "중3영어학원", "middle3-english",
        "중3 영어학원.zip", "e39f5be8889607b557bb8bc1a6ec7e3cae97b51cc1fc6407b52380f5d12cfa36",
        "800df1b09d04ac12b84be6b9667d736ad3d4ebc04e8fcb5db2c091557e25a2fe",
        1_230_627, 3_756_594, 371, 363, 8, 2_226, ((6, 371),), 4_452, 1_484,
        ((4, 371),), 742, 87, 411,
    ),
)
CATEGORY_BY_KEY = {item.key: item for item in CATEGORIES}
ALL_CATEGORY_LABELS = (
    ("중1 수학학원", "중1수학학원"),
    ("중1 영어학원", "중1영어학원"),
    ("중2 수학학원", "중2수학학원"),
    ("중2 영어학원", "중2영어학원"),
    ("중3 수학학원", "중3수학학원"),
    ("중3 영어학원", "중3영어학원"),
)


@dataclass(frozen=True)
class Correction:
    category: str
    old: str
    new: str
    localities: tuple[str, ...]
    occurrences: int
    token: bool = False
    per_locality_counts: tuple[tuple[str, int], ...] = ()


# Raw ZIP bytes remain immutable.  Only these exact category/locality/literal
# transforms are allowed in visible copy and its schema parity.
CORRECTIONS = (
    Correction("middle1_math", "와와학습코칭학원를", "와와학습코칭학원을", (
        "경산사동", "관교동", "구월동", "국우동", "노변동", "덕풍동", "도남동", "도남지구",
        "상현동", "시지동", "신갈동", "안양동", "용두동", "이시아폴리스", "중화산동", "천천동", "행신동",
    ), 17),
    Correction("middle1_english", "와와학습코칭학원로", "와와학습코칭학원으로", (
        "가경동", "구갈동", "노변동", "등촌동", "배곧", "배곧동", "복현동", "선암동", "안양동",
        "염창동", "옥정동", "전주 장동", "토당동",
    ), 13),
    Correction("middle1_english", "관리을", "관리를", (
        "가정동", "관저동", "관평동", "노은동", "도안동", "둔산동", "부평동", "삼산동", "송강동",
        "송촌동", "용산동", "원신흥동", "청계동", "칠성동", "향남읍",
    ), 16, False, (("가정동", 1), ("관저동", 1), ("관평동", 2), ("노은동", 1), ("도안동", 1),
        ("둔산동", 1), ("부평동", 1), ("삼산동", 1), ("송강동", 1), ("송촌동", 1),
        ("용산동", 1), ("원신흥동", 1), ("청계동", 1), ("칠성동", 1), ("향남읍", 1))),
    Correction("middle1_english", "동기을", "동기를", (
        "경안동", "비산동", "소하동", "수택동", "인창동", "철산동", "하안동", "화정동", "후곡마을",
    ), 9),
    Correction("middle1_english", "수업 운영 운영 기준", "수업 운영 기준", (
        "국우동", "도남지구", "동천동", "만촌동", "반곡동", "범어동", "복대동", "복현동", "본리동",
        "봉명동", "봉무동", "불당동", "산격동", "산남동", "수곡동", "시지동", "신불당", "양정동",
        "용곡동", "원주혁신도시", "재송동", "좌동", "주월동", "치평동",
    ), 24),
    Correction("middle1_english", "학습 운영 운영 기준", "학습 운영 기준", (
        "별내신도시", "성남동", "수월동", "신원동", "안양동",
    ), 5),
    Correction("middle1_math", "앙중", "거제중앙중", ("고현동",), 2, True),
    Correction("middle1_math", "초당산중", "당산중", ("당산동",), 1, True),
    Correction("middle1_math", "분당중", "불곡중", ("미금",), 2, True),
    Correction("middle1_math", "초버들중", "버들중", ("반곡동", "원주혁신도시"), 4, True),
    Correction("middle1_math", "창원중", "상남중", ("사파동",), 1, True),
    Correction("middle1_math", "거제중", "거제중앙중", ("수월동",), 2, True),
    Correction("middle1_math", "거제중과 앙중", "수월중과 거제중앙중", ("양정동",), 1),
    Correction("middle1_math", "위례중", "위례중앙중", ("위례",), 1, True),
    Correction("middle1_math", "앙중", "위례중앙중", ("위례신도시", "창곡동"), 4, True),
    Correction("middle1_english", "오현초호매실중", "호매실중", ("호매실",), 1, True),
    Correction("middle2_math", "오현초호매실중", "호매실중", ("호매실", "수원 금곡동"), 4, True),
)


@dataclass(frozen=True)
class FAQ:
    number: int
    question: str
    answer: str


@dataclass(frozen=True)
class Section:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Manuscript:
    category: str
    filename: str
    locality: str
    title: str
    meta: str
    intro: tuple[str, ...]
    sections: tuple[Section, ...]
    faqs: tuple[FAQ, ...]
    review: tuple[str, ...]
    summary: str
    raw_text: str
    raw_bytes: bytes
    raw_sha256: str

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(item.heading for item in self.sections)

    @property
    def paragraphs(self) -> tuple[str, ...]:
        return self.intro + tuple(value for item in self.sections for value in item.paragraphs)


@dataclass(frozen=True)
class SourceRow:
    locality: str
    region: str
    city: str
    center_name: str
    fee_url: str
    education_office: str
    registration: str
    address: str
    middle_school_raw: str
    middle_schools: tuple[str, ...]
    english_grades: tuple[str, ...]
    math_grades: tuple[str, ...]
    telephone: str
    opening_hours: str
    official_site: str
    image_body: str
    image_map: str

    def grades(self, category: Category) -> tuple[str, ...]:
        return self.math_grades if category.subject == "수학" else self.english_grades

    def supports(self, category: Category) -> bool:
        return category.grade in self.grades(category)

    @property
    def middle_school_source_tokens(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(part for part in re.split(r"[,/.\s]+", self.middle_school_raw.strip()) if part))


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
        if self.errors:
            return "FAIL"
        if self.holds:
            return "HOLD"
        return "PASS"


def split_paragraphs(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r"\n[ \t]*\n", value.strip()) if part.strip())


def normalized_header(value: str) -> str:
    return nfc(value).replace("\r", "").replace("\n", "").strip()


def split_tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def split_schools(value: str, locality: str, audit: Audit | None = None) -> tuple[str, ...]:
    raw = tuple(dict.fromkeys(part for part in re.split(r"[,/\.\s]+", value.strip()) if part))
    values: list[str] = []
    for token in raw:
        if token == "오현초호매실중" and locality in {"호매실", "수원 금곡동"}:
            token = "호매실중"
        values.append(token)
    result = tuple(dict.fromkeys(values))
    if audit is not None:
        malformed = [item for item in result if not re.fullmatch(r"[0-9A-Za-z가-힣·()\-]+", item) or not item.endswith(("중", "중학교"))]
        if malformed:
            audit.error("source_school_token", locality, repr(malformed))
    return result


def correction_pattern(rule: Correction) -> re.Pattern[str]:
    if not rule.token:
        return re.compile(re.escape(rule.old))
    return re.compile(
        rf"(?<![가-힣A-Za-z0-9]){re.escape(rule.old)}"
        rf"(?=(?:과|와|은|는|이|가|을|를|의|·|,|\s|['’”)]|$))"
    )


def apply_corrections(value: str, category: str, locality: str) -> str:
    result = value
    for rule in CORRECTIONS:
        if rule.category == category and locality in rule.localities:
            result = correction_pattern(rule).sub(rule.new, result)
    return result


def corrected_manuscript(item: Manuscript) -> Manuscript:
    fix = lambda value: apply_corrections(value, item.category, item.locality)
    return replace(
        item,
        title=fix(item.title),
        meta=fix(item.meta),
        intro=tuple(fix(value) for value in item.intro),
        sections=tuple(Section(fix(section.heading), tuple(fix(value) for value in section.paragraphs)) for section in item.sections),
        faqs=tuple(FAQ(faq.number, fix(faq.question), fix(faq.answer)) for faq in item.faqs),
        review=tuple(fix(value) for value in item.review),
        summary=fix(item.summary),
    )


def parse_manuscript(category: Category, filename: str, raw: bytes, audit: Audit) -> Manuscript | None:
    location = f"{category.zip_name}:{filename}"
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        audit.error("zip_encoding", location, repr(exc))
        return None
    bom = raw.startswith(b"\xef\xbb\xbf")
    if (b"\xef\xbb\xbf" if bom else b"") + decoded.encode("utf-8") != raw:
        audit.error("zip_roundtrip", location, "strict UTF-8 byte round-trip differs")
    if CONTROL.search(decoded):
        audit.error("zip_control", location, repr(CONTROL.search(decoded).group(0)))
    if any(line.rstrip(" \t") != line for line in decoded.splitlines()):
        audit.error("zip_trailing_space", location, "trailing spaces found")
    if PROMPT_OR_CODE.search(decoded):
        audit.error("zip_instruction", location, PROMPT_OR_CODE.search(decoded).group(0))
    if ACTIVE_TEXT.search(decoded):
        audit.error("zip_active_text", location, ACTIVE_TEXT.search(decoded).group(0))
    if MOJIBAKE.search(decoded):
        audit.error("zip_mojibake", location, MOJIBAKE.search(decoded).group(0))
    if GUARANTEE.search(decoded):
        audit.error("source_guarantee", location, GUARANTEE.search(decoded).group(0))

    text = decoded.replace("\r\n", "\n").replace("\r", "\n")
    suffix = f" {category.label}.txt"
    if not filename.endswith(suffix) or Path(filename).name != filename:
        audit.error("zip_filename", location, f"expected suffix={suffix!r}")
        return None
    locality = nfc(filename[:-len(suffix)])
    lines = text.splitlines()
    positions: dict[str, int] = {}
    for marker in MARKERS:
        hits = [index for index, line in enumerate(lines) if line.strip() == marker]
        if len(hits) != 1:
            audit.error("source_marker", location, f"{marker} count={len(hits)}")
            return None
        positions[marker] = hits[0]
    if [positions[item] for item in MARKERS] != sorted(positions.values()):
        audit.error("source_marker_order", location, "marker order differs")
        return None

    def segment(start: str, end: str | None) -> str:
        left = positions[start] + 1
        right = positions[end] if end else len(lines)
        return "\n".join(lines[left:right]).strip("\n")

    title_values = split_paragraphs(segment(MARKERS[0], MARKERS[1]))
    meta_values = split_paragraphs(segment(MARKERS[1], MARKERS[2]))
    body = segment(MARKERS[2], MARKERS[3]).strip()
    faq_text = segment(MARKERS[3], MARKERS[4]).strip()
    review_lines = tuple(line.strip() for line in segment(MARKERS[4], MARKERS[5]).splitlines() if line.strip())
    summary_values = split_paragraphs(segment(MARKERS[5], None))
    if len(title_values) != 1 or len(meta_values) != 1 or len(summary_values) != 1:
        audit.error("source_singletons", location, f"title={len(title_values)}, meta={len(meta_values)}, summary={len(summary_values)}")
        return None
    if title_values[0] != f"{locality} {category.label}":
        audit.error("source_title", location, repr(title_values[0]))

    heading_matches = list(H2.finditer(body))
    if not heading_matches or len(re.findall(r"(?m)^#{1,6}[ \t]+", body)) != len(heading_matches):
        audit.error("source_heading_syntax", location, f"h2={len(heading_matches)}")
        return None
    intro = split_paragraphs(body[:heading_matches[0].start()])
    sections: list[Section] = []
    for index, match in enumerate(heading_matches):
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(body)
        paragraphs = split_paragraphs(body[match.end():end])
        if not match.group(1).strip() or not paragraphs:
            audit.error("source_section", location, f"section={index + 1}, paragraphs={len(paragraphs)}")
        sections.append(Section(match.group(1).strip(), paragraphs))
    if len(intro) != 1:
        audit.error("source_intro", location, f"count={len(intro)}")

    faq_lines = [line.strip() for line in faq_text.splitlines() if line.strip()]
    faqs: list[FAQ] = []
    cursor = 0
    while cursor < len(faq_lines):
        question = QUESTION.fullmatch(faq_lines[cursor])
        if question is None:
            break
        cursor += 1
        if cursor >= len(faq_lines):
            break
        answer = ANSWER.fullmatch(faq_lines[cursor])
        if answer is None:
            break
        number = int(question.group(1))
        answer_number = int(answer.group(1)) if answer.group(1) else number
        if number != len(faqs) + 1 or answer_number != number:
            break
        faqs.append(FAQ(number, question.group(3).strip(), answer.group(3).strip()))
        cursor += 1
    if cursor != len(faq_lines):
        audit.error("source_faq_format", location, f"parsed={cursor}, lines={len(faq_lines)}")
    if len(review_lines) not in (2, 3):
        audit.error("source_review_lines", location, f"count={len(review_lines)}")
    elif not re.search(r"(?:실제|가상|예시|아니|뜻하지)", review_lines[0]):
        audit.error("source_review_disclaimer", location, review_lines[0])

    paragraphs = intro + tuple(value for section in sections for value in section.paragraphs)
    normalized = [norm(value).casefold() for value in paragraphs]
    if len(normalized) != len(set(normalized)):
        audit.error("source_within_page_duplicate", location, "normalized paragraph duplicate")

    return Manuscript(
        category.key, filename, locality, title_values[0], meta_values[0], intro, tuple(sections),
        tuple(faqs), review_lines, summary_values[0], decoded, raw, sha256_bytes(raw),
    )


def find_column(columns: Iterable[str], compact_name: str) -> str | None:
    wanted = re.sub(r"[\s()]", "", compact_name)
    for column in columns:
        if re.sub(r"[\s()]", "", normalized_header(column)) == wanted:
            return column
    return None


def archive_manifest(lines: Iterable[str]) -> str:
    return sha256_bytes("".join(sorted(lines)).encode("utf-8"))


def manuscript_values(item: Manuscript) -> tuple[str, ...]:
    return (
        item.title,
        item.meta,
        *item.intro,
        *(section.heading for section in item.sections),
        *(value for section in item.sections for value in section.paragraphs),
        *(value for faq in item.faqs for value in (faq.question, faq.answer)),
        *item.review,
        item.summary,
    )


def load_archives(
    zip_dir: Path,
    audit: Audit,
) -> tuple[dict[str, tuple[Manuscript, ...]], dict[str, tuple[Manuscript, ...]]]:
    """Load ZIP members in memory only and return raw-parsed/corrected models."""
    parsed_by_category: dict[str, tuple[Manuscript, ...]] = {}
    corrected_by_category: dict[str, tuple[Manuscript, ...]] = {}
    global_raw_hashes: list[str] = []
    locality_sets: dict[str, set[str]] = {}
    observations: dict[str, Any] = {}
    correction_rules = sum(len(rule.localities) for rule in CORRECTIONS)
    correction_pages = len({(rule.category, locality) for rule in CORRECTIONS for locality in rule.localities})
    correction_occurrences = sum(rule.occurrences for rule in CORRECTIONS)
    if (correction_rules, correction_pages, correction_occurrences) != (
        EXPECTED_CORRECTION_RULES, EXPECTED_CORRECTION_PAGES, EXPECTED_CORRECTION_OCCURRENCES,
    ):
        audit.error(
            "correction_contract_cardinality", "CORRECTIONS",
            f"rules={correction_rules}, pages={correction_pages}, occurrences={correction_occurrences}",
        )

    for category in CATEGORIES:
        path = zip_dir / category.zip_name
        if not path.is_file():
            audit.error("zip_missing", path, "authoritative manuscript archive missing")
            continue
        actual_sha = sha256_file(path)
        if actual_sha != category.zip_sha256:
            audit.error("zip_hash", path, f"actual={actual_sha}, expected={category.zip_sha256}")
        if path.stat().st_size != category.zip_bytes:
            audit.error("zip_size", path, f"actual={path.stat().st_size}, expected={category.zip_bytes}")

        parsed: list[Manuscript] = []
        names: list[str] = []
        manifest_lines: list[str] = []
        total_uncompressed = 0
        total_compressed = 0
        ratios: list[float] = []
        bom_count = 0
        try:
            with zipfile.ZipFile(path, "r") as archive:
                if archive.comment:
                    audit.error("zip_comment", path, f"bytes={len(archive.comment)}")
                infos = archive.infolist()
                if len(infos) != EXPECTED_LOCALITIES:
                    audit.error("zip_count", path, f"actual={len(infos)}, expected={EXPECTED_LOCALITIES}")
                bad_crc = archive.testzip()
                if bad_crc is not None:
                    audit.error("zip_crc", path, bad_crc)
                for info in infos:
                    name = nfc(info.filename)
                    names.append(name)
                    posix = PurePosixPath(name)
                    windows = PureWindowsPath(name)
                    mode = (info.external_attr >> 16) & 0o170000
                    unsafe = (
                        name != info.filename
                        or info.is_dir()
                        or posix.is_absolute()
                        or windows.is_absolute()
                        or len(posix.parts) != 1
                        or len(windows.parts) != 1
                        or ".." in posix.parts
                        or ".." in windows.parts
                        or windows.drive != ""
                        or bool(info.flag_bits & 0x1)
                        or mode == 0o120000
                        or not name.endswith(".txt")
                    )
                    if unsafe:
                        audit.error("zip_member_safety", f"{category.zip_name}:{name}", "unsafe/non-text member")
                        continue
                    if info.compress_type != zipfile.ZIP_DEFLATED:
                        audit.error("zip_compression", f"{category.zip_name}:{name}", str(info.compress_type))
                    if not info.flag_bits & 0x800:
                        audit.error("zip_filename_encoding", f"{category.zip_name}:{name}", "UTF-8 flag missing")
                    if info.extra:
                        audit.error("zip_extra_field", f"{category.zip_name}:{name}", f"bytes={len(info.extra)}")
                    if info.comment:
                        audit.error("zip_member_comment", f"{category.zip_name}:{name}", f"bytes={len(info.comment)}")
                    raw = archive.read(info)
                    total_uncompressed += info.file_size
                    total_compressed += info.compress_size
                    ratios.append(info.file_size / max(1, info.compress_size))
                    bom_count += int(raw.startswith(b"\xef\xbb\xbf"))
                    if b"\r" in raw or b"\x00" in raw:
                        audit.error("zip_line_encoding", f"{category.zip_name}:{name}", "expected LF-only text without NUL")
                    file_sha = sha256_bytes(raw)
                    manifest_lines.append(f"{name}\0{len(raw)}\0{file_sha}\n")
                    item = parse_manuscript(category, name, raw, audit)
                    if item is not None:
                        parsed.append(item)
        except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            audit.error("zip_read", path, repr(exc))
            continue

        manifest_sha = archive_manifest(manifest_lines)
        if manifest_sha != category.zip_manifest_sha256:
            audit.error("zip_manifest_hash", path, f"actual={manifest_sha}, expected={category.zip_manifest_sha256}")
        if total_uncompressed != category.uncompressed_bytes:
            audit.error("zip_uncompressed_bytes", path, f"actual={total_uncompressed}, expected={category.uncompressed_bytes}")
        if bom_count != category.bom:
            audit.error("zip_bom_count", path, f"actual={bom_count}, expected={category.bom}")
        if ratios and max(ratios) >= 10:
            audit.error("zip_ratio", path, f"max={max(ratios):.3f}")
        if len(names) != len(set(names)):
            audit.error("zip_duplicate_name", path, "duplicate member filename")
        if len({item.locality for item in parsed}) != len(parsed):
            audit.error("zip_duplicate_locality", path, "duplicate locality")
        if len({item.raw_sha256 for item in parsed}) != len(parsed):
            audit.error("zip_duplicate_content", path, "duplicate raw manuscript")

        parsed_tuple = tuple(parsed)
        corrected_tuple = tuple(corrected_manuscript(item) for item in parsed)
        parsed_by_category[category.key] = parsed_tuple
        corrected_by_category[category.key] = corrected_tuple
        global_raw_hashes.extend(item.raw_sha256 for item in parsed)
        locality_sets[category.key] = {item.locality for item in parsed}

        # The exact correction contract is category + locality + literal.  No
        # broad replacement is accepted, and immutable raw bytes remain attached.
        for rule in (value for value in CORRECTIONS if value.category == category.key):
            total = 0
            per_locality: dict[str, int] = {}
            pattern = correction_pattern(rule)
            for item in parsed:
                if item.locality not in rule.localities:
                    continue
                count = len(pattern.findall(item.raw_text))
                per_locality[item.locality] = count
                total += count
            missing_paths = sorted(set(rule.localities) - set(per_locality))
            if rule.per_locality_counts:
                expected_per_locality = dict(rule.per_locality_counts)
            elif rule.occurrences % len(rule.localities) == 0:
                expected_per_locality = {
                    locality: rule.occurrences // len(rule.localities) for locality in rule.localities
                }
            else:
                expected_per_locality = {}
            distribution_differs = bool(expected_per_locality) and per_locality != expected_per_locality
            if missing_paths or any(value == 0 for value in per_locality.values()) or total != rule.occurrences or distribution_differs:
                audit.error(
                    "correction_allowlist_raw",
                    f"{category.key}:{rule.old}->{rule.new}",
                    f"total={total}/{rule.occurrences}, missing={missing_paths}, "
                    f"per_locality={per_locality}, expected_per_locality={expected_per_locality}",
                )
            for raw_item, fixed_item in zip(parsed_tuple, corrected_tuple, strict=False):
                if raw_item.locality not in rule.localities:
                    continue
                if raw_item.raw_bytes != fixed_item.raw_bytes or raw_item.raw_sha256 != fixed_item.raw_sha256:
                    audit.error("correction_raw_mutation", raw_item.filename, "raw attachment changed")
                remaining = sum(len(pattern.findall(value)) for value in manuscript_values(fixed_item))
                if remaining:
                    audit.error("correction_visible_remaining", fixed_item.filename, f"literal={rule.old!r}, count={remaining}")

        h2_distribution = Counter(len(item.sections) for item in corrected_tuple)
        faq_distribution = Counter(len(item.faqs) for item in corrected_tuple)
        h2_total = sum(len(item.sections) for item in corrected_tuple)
        section_paragraphs = sum(len(section.paragraphs) for item in corrected_tuple for section in item.sections)
        faq_total = sum(len(item.faqs) for item in corrected_tuple)
        review_lines = sum(len(item.review) for item in corrected_tuple)
        expected_h2_distribution = dict(category.h2_distribution)
        expected_faq_distribution = dict(category.faq_distribution)
        metrics = {
            "zip_sha256": actual_sha,
            "manifest_sha256": manifest_sha,
            "entries": len(parsed),
            "zip_bytes": path.stat().st_size,
            "uncompressed_bytes": total_uncompressed,
            "compressed_bytes": total_compressed,
            "max_compression_ratio": round(max(ratios, default=0), 3),
            "bom": bom_count,
            "h2": h2_total,
            "h2_distribution": dict(sorted(h2_distribution.items())),
            "section_paragraphs": section_paragraphs,
            "faq": faq_total,
            "faq_distribution": dict(sorted(faq_distribution.items())),
            "review_nonempty_lines": review_lines,
        }
        observations[category.key] = metrics
        for code, actual, expected in (
            ("h2", h2_total, category.h2_total),
            ("section_paragraphs", section_paragraphs, category.section_paragraphs),
            ("faq", faq_total, category.faq_total),
            ("review_lines", review_lines, category.review_lines),
        ):
            if actual != expected:
                audit.error(f"source_{code}", category.zip_name, f"actual={actual}, expected={expected}")
        if dict(h2_distribution) != expected_h2_distribution:
            audit.error("source_h2_distribution", category.zip_name, f"actual={dict(h2_distribution)}")
        if dict(faq_distribution) != expected_faq_distribution:
            audit.error("source_faq_distribution", category.zip_name, f"actual={dict(faq_distribution)}")

    if locality_sets:
        first_key = CATEGORIES[0].key
        reference = locality_sets.get(first_key, set())
        for key, values in locality_sets.items():
            if values != reference:
                audit.error("zip_locality_parity", key, f"missing={sorted(reference-values)[:5]}, extra={sorted(values-reference)[:5]}")
    if len(global_raw_hashes) != EXPECTED_NEW_DETAILS or len(set(global_raw_hashes)) != len(global_raw_hashes):
        audit.error("zip_global_duplicate_content", zip_dir, f"count={len(global_raw_hashes)}, unique={len(set(global_raw_hashes))}")
    audit.observations["archives"] = observations
    audit.observations["corrections"] = {
        "rules": correction_rules,
        "pages": correction_pages,
        "occurrences": correction_occurrences,
    }
    return parsed_by_category, corrected_by_category


def read_csv_rows(path: Path, audit: Audit, code: str) -> list[dict[str, str]]:
    if not path.is_file():
        audit.error(f"{code}_missing", path, "authoritative CSV missing")
        return []
    expected = COMMON_HASHES[path.name]
    actual = sha256_file(path)
    if actual != expected:
        audit.error(f"{code}_hash", path, f"actual={actual}, expected={expected}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                audit.error(f"{code}_header", path, "header missing")
                return []
            rows = [{normalized_header(key): nfc(value or "") for key, value in row.items()} for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        audit.error(f"{code}_read", path, repr(exc))
        return []
    if len(rows) != EXPECTED_LOCALITIES:
        audit.error(f"{code}_count", path, f"actual={len(rows)}, expected={EXPECTED_LOCALITIES}")
    return rows


def row_value(row: Mapping[str, str], compact_name: str) -> str:
    column = find_column(row.keys(), compact_name)
    return norm(row.get(column, "")) if column else ""


def load_common(common: Path, audit: Audit) -> tuple[SourceRow, ...]:
    center = read_csv_rows(common / "센터정보 정리.csv", audit, "center")
    target = read_csv_rows(common / "타깃학교.csv", audit, "target")
    eo = read_csv_rows(common / "EducationalOrganization.csv", audit, "eo")
    images = read_csv_rows(common / "이미지링크.csv", audit, "images")
    if not all((center, target, eo, images)):
        return ()

    sequences = (
        ("center", center, "근처 수업가능 동네"),
        ("target", target, "근처 수업가능 동네"),
        ("eo", eo, "서비스 제공 지역"),
        ("images", images, "제목"),
    )
    orders: dict[str, list[str]] = {}
    for label, values, key in sequences:
        orders[label] = [row_value(row, key) for row in values]
        if len(orders[label]) != len(set(orders[label])):
            audit.error("common_duplicate_locality", label, "duplicate locality")
    for label, order in orders.items():
        if order != orders["center"]:
            audit.error("common_order", label, "locality order differs from center CSV")

    result: list[SourceRow] = []
    raw_normalized: list[str] = []
    for center_row, target_row, eo_row, image_row in zip(center, target, eo, images, strict=False):
        locality = row_value(center_row, "근처 수업가능 동네")
        location = f"common:{locality}"
        for key in (
            "근처 수업가능 동네", "지역", "시or구", "센터명",
            "타깃학교(초)", "타깃학교(중)", "타깃학교(고)",
        ):
            if row_value(center_row, key) != row_value(target_row, key):
                audit.error("common_target_parity", location, f"field={key!r}")
        center_name = row_value(center_row, "센터명")
        address = row_value(center_row, "센터 주소")
        if row_value(eo_row, "실제 센터명") != center_name:
            audit.error("common_eo_name", location, f"center={center_name!r}, eo={row_value(eo_row, '실제 센터명')!r}")
        if row_value(eo_row, "도로명 주소") != address:
            audit.error("common_eo_address", location, f"center={address!r}, eo={row_value(eo_row, '도로명 주소')!r}")
        if row_value(eo_row, "서비스 제공 지역") != locality:
            audit.error("common_eo_locality", location, repr(row_value(eo_row, "서비스 제공 지역")))
        if row_value(image_row, "제목") != locality:
            audit.error("common_image_locality", location, repr(row_value(image_row, "제목")))
        telephone = row_value(eo_row, "전화번호")
        opening = row_value(eo_row, "운영 시간")
        if not telephone or not opening:
            audit.error("common_required_contact", location, f"telephone={telephone!r}, opening={opening!r}")
        middle_raw = row_value(center_row, "타깃학교(중)")
        if "오현초호매실중" in re.split(r"[,/.\s]+", middle_raw):
            raw_normalized.append(locality)
        result.append(SourceRow(
            locality=locality,
            region=row_value(center_row, "지역"),
            city=row_value(center_row, "시or구"),
            center_name=center_name,
            fee_url=row_value(center_row, "센터 교습비"),
            education_office=row_value(center_row, "교육지원청명칭"),
            registration=row_value(center_row, "교육지원청 등록번호"),
            address=address,
            middle_school_raw=middle_raw,
            middle_schools=split_schools(middle_raw, locality, audit) if middle_raw else (),
            english_grades=split_tokens(row_value(center_row, "가능학년(영어)")),
            math_grades=split_tokens(row_value(center_row, "가능학년(수학)")),
            telephone=telephone,
            opening_hours=opening,
            official_site=row_value(eo_row, "공식 홈페이지"),
            image_body=row_value(image_row, "본문"),
            image_map=row_value(image_row, "지도"),
        ))

    rows = tuple(result)
    if set(raw_normalized) != {"호매실", "수원 금곡동"}:
        audit.error("common_raw_school_normalization", common, repr(raw_normalized))
    if sum(bool(row.middle_schools) for row in rows) != 318:
        audit.error("common_middle_school_provided", common, str(sum(bool(row.middle_schools) for row in rows)))
    if sum(len(row.middle_schools) for row in rows) != 889:
        audit.error("common_middle_school_occurrences", common, str(sum(len(row.middle_schools) for row in rows)))
    if len({school for row in rows for school in row.middle_schools}) != 405:
        audit.error("common_middle_school_unique", common, str(len({school for row in rows for school in row.middle_schools})))
    fee_missing = {row.locality for row in rows if not row.fee_url}
    if fee_missing != {"석사동", "퇴계동"}:
        audit.error("common_fee_missing", common, repr(sorted(fee_missing)))

    supported: dict[str, dict[str, Any]] = {}
    total_supported = 0
    for category in CATEGORIES:
        yes = [row.locality for row in rows if row.supports(category)]
        no = [row.locality for row in rows if not row.supports(category)]
        if len(yes) != category.support or len(no) != category.unconfirmed:
            audit.error("common_grade_support", category.key, f"supported={len(yes)}, unconfirmed={len(no)}")
        supported[category.key] = {"supported": len(yes), "unconfirmed": len(no), "unconfirmed_localities": no}
        total_supported += len(yes)
    if total_supported != EXPECTED_SUPPORTED or EXPECTED_NEW_DETAILS - total_supported != EXPECTED_UNCONFIRMED:
        audit.error("common_total_support", common, f"supported={total_supported}, unconfirmed={EXPECTED_NEW_DETAILS-total_supported}")
    audit.observations["common"] = {
        "rows": len(rows),
        "hashes": COMMON_HASHES,
        "middle_school_provided": sum(bool(row.middle_schools) for row in rows),
        "middle_school_missing": sum(not row.middle_schools for row in rows),
        "middle_school_occurrences_per_category": sum(len(row.middle_schools) for row in rows),
        "middle_school_unique": len({school for row in rows for school in row.middle_schools}),
        "raw_school_normalization": raw_normalized,
        "fee_missing": sorted(fee_missing),
        "categories": supported,
    }
    return rows


def normalized_template(value: str, item: Manuscript, row: SourceRow, category: Category) -> str:
    text = norm(unicodedata.normalize("NFKC", value)).casefold()
    replacements = {
        item.title,
        f"{item.locality} {category.label}",
        item.locality,
        category.label,
        row.address,
        row.center_name,
        row.registration,
        row.education_office,
        row.fee_url,
        row.locality,
        row.region,
        row.city,
        *row.middle_schools,
    }
    for replacement in sorted((norm(value).casefold() for value in replacements if value), key=len, reverse=True):
        text = text.replace(replacement, " {fact} ")
    text = re.sub(r"\d+", "{n}", text)
    return norm(text)


def extracted_school_names(value: str) -> set[str]:
    return {
        match.group(1)
        for match in SCHOOL_TOKEN.finditer(value)
        if match.group(1) not in SCHOOL_NOUN_EXCLUSIONS
    }


POSITIVE_AVAILABILITY = re.compile(
    r"(?:(?:중[123]\s*)?(?:영어|수학)\s*(?:수업|과정).{0,24}(?:가능|제공|운영|진행)|"
    r"(?:가능|제공|운영|진행).{0,24}(?:중[123]\s*)?(?:영어|수학)\s*(?:수업|과정))"
)
SAFE_QUALIFIER = re.compile(
    r"(?:확인|검증|문의|단정(?:하지|해서는\s*안)|뜻하지|아니|않(?:습니다|으며|고|는)|미확인|"
    r"제공된\s*정보|실제\s*(?:여부|운영)|상담\s*(?:답변|에서))"
)
SEED_QUOTE = re.compile(r"[‘“'\"]([^’”'\"]+)[’”'\"]")


def auxiliary_seed(item: Manuscript) -> str | None:
    if item.category in {"middle2_math", "middle3_english"}:
        matches = [value for faq in item.faqs for value in SEED_QUOTE.findall(faq.question)]
        return matches[0] if len(matches) == 1 else None
    if item.category == "middle2_english":
        matches = [value for value in SEED_QUOTE.findall(item.summary) if value != "영어 수학"]
        return matches[0] if len(matches) == 1 else None
    return None


def validate_source_contract(
    parsed_by_category: Mapping[str, Sequence[Manuscript]],
    corrected_by_category: Mapping[str, Sequence[Manuscript]],
    rows: Sequence[SourceRow],
    audit: Audit,
) -> None:
    if len(rows) != EXPECTED_LOCALITIES:
        audit.error("source_alignment", "common", f"rows={len(rows)}")
        return
    row_by_locality = {row.locality: row for row in rows}
    common_localities = set(row_by_locality)
    all_addresses: dict[str, set[str]] = defaultdict(set)
    all_centers: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        all_addresses[row.address].add(row.locality)
        all_centers[row.center_name].add(row.locality)

    overall_h2 = overall_faq = overall_reviews = overall_school_chips = 0
    all_corrected_fingerprints: set[str] = set()
    style_pages: set[str] = set()
    style_occurrences = 0
    seed_metrics: dict[str, Any] = {}
    naturalness: dict[str, Any] = {}

    for category in CATEGORIES:
        raw_items = tuple(parsed_by_category.get(category.key, ()))
        items = tuple(corrected_by_category.get(category.key, ()))
        localities = {item.locality for item in items}
        if localities != common_localities:
            audit.error(
                "source_locality_parity",
                category.key,
                f"missing={sorted(common_localities-localities)[:5]}, extra={sorted(localities-common_localities)[:5]}",
            )
        if len(items) != EXPECTED_LOCALITIES or len(raw_items) != EXPECTED_LOCALITIES:
            audit.error("source_category_count", category.key, f"raw={len(raw_items)}, corrected={len(items)}")
            continue
        item_by_locality = {item.locality: item for item in items}
        raw_by_locality = {item.locality: item for item in raw_items}
        h2_df: Counter[str] = Counter()
        paragraph_df: Counter[str] = Counter()
        sentence_df: Counter[str] = Counter()
        seeds: list[str] = []
        positive_seed_claims = 0

        for row in rows:
            item = item_by_locality.get(row.locality)
            raw_item = raw_by_locality.get(row.locality)
            if item is None or raw_item is None:
                continue
            if item.raw_bytes != raw_item.raw_bytes or item.raw_text != raw_item.raw_text:
                audit.error("source_raw_roundtrip", f"{category.key}:{row.locality}", "corrected model did not retain exact raw source")
            visible_values = manuscript_values(item)
            visible = "\n".join(visible_values)
            if any(marker in visible for marker in MARKERS):
                audit.error("source_marker_leak", item.filename, "source marker in parsed fields")
            if INLINE_REPEAT.search(visible):
                audit.error("source_inline_repeat", item.filename, INLINE_REPEAT.search(visible).group(0))
            if MOJIBAKE.search(visible) or GUARANTEE.search(visible):
                audit.error("source_quality_pattern", item.filename, "mojibake/guarantee pattern")

            normalized_paragraphs = [normalized_template(value, item, row, category) for value in item.paragraphs]
            duplicates = [value for value, count in Counter(normalized_paragraphs).items() if count > 1]
            if duplicates:
                audit.error("source_within_page_template_duplicate", item.filename, repr(duplicates[:3]))
            h2_df.update({normalized_template(value, item, row, category) for value in item.headings})
            paragraph_df.update(set(normalized_paragraphs))
            sentence_df.update({
                normalized_template(sentence, item, row, category)
                for paragraph in item.paragraphs
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
                if norm(sentence)
            })

            # Exact source schools only.  The 12 visible manuscript repairs are
            # applied above; source CSV's two glued raw tokens normalize here.
            mentioned_schools = extracted_school_names(visible)
            invented = mentioned_schools - set(row.middle_schools)
            if invented:
                audit.error("source_school_invention", item.filename, repr(sorted(invented)))
            for address, owner_localities in all_addresses.items():
                if address and address in visible and address != row.address:
                    audit.error("source_foreign_address", item.filename, f"address={address!r}, owners={sorted(owner_localities)}")
            for center, owner_localities in all_centers.items():
                if center and center in visible and center != row.center_name:
                    audit.error("source_foreign_center", item.filename, f"center={center!r}, owners={sorted(owner_localities)}")

            if not row.supports(category):
                for match in POSITIVE_AVAILABILITY.finditer(visible):
                    start = max(0, visible.rfind(".", 0, match.start()) + 1)
                    end_pos = visible.find(".", match.end())
                    end = len(visible) if end_pos < 0 else end_pos + 1
                    sentence = visible[start:end]
                    if not SAFE_QUALIFIER.search(sentence):
                        audit.error("source_unsupported_positive", item.filename, sentence[:300])

            raw_style_count = raw_item.raw_text.count("수업학교")
            if raw_style_count:
                style_pages.add(f"{category.key}:{row.locality}")
                style_occurrences += raw_style_count

            seed = auxiliary_seed(item)
            if category.key in {"middle2_math", "middle2_english", "middle3_english"}:
                if not seed:
                    audit.error("source_seed_extract", item.filename, "one auxiliary query seed was not found")
                else:
                    seeds.append(seed)
                    seed_context = " ".join(
                        [value for faq in item.faqs for value in (faq.question, faq.answer)] + [item.summary]
                    )
                    if seed_context.count(seed) < 2:
                        audit.error("source_seed_roundtrip", item.filename, f"seed={seed!r}, count={seed_context.count(seed)}")
                    if not SAFE_QUALIFIER.search(seed_context):
                        audit.error("source_seed_qualification", item.filename, seed)
                    for match in re.finditer(re.escape(seed), seed_context):
                        window = seed_context[max(0, match.start()-90):match.end()+160]
                        if re.search(r"(?:실제로|현재)\s*(?:제공|운영)|(?:제공|운영)합니다", window) and not SAFE_QUALIFIER.search(window):
                            positive_seed_claims += 1
                            audit.error("source_seed_positive_claim", item.filename, window)

            fingerprint = sha256_bytes("\0".join(visible_values).encode("utf-8"))
            if fingerprint in all_corrected_fingerprints:
                audit.error("source_corrected_duplicate", item.filename, fingerprint)
            all_corrected_fingerprints.add(fingerprint)

        h2_max = max(h2_df.values(), default=0)
        h2_unique = len(h2_df)
        if h2_max != category.h2_max_df or h2_unique != category.h2_unique_templates:
            audit.error(
                "source_h2_diversity",
                category.key,
                f"max_df={h2_max}/{category.h2_max_df}, unique={h2_unique}/{category.h2_unique_templates}",
            )
        naturalness[category.key] = {
            "h2_max_df": h2_max,
            "h2_unique_templates": h2_unique,
            "h2_top": h2_df.most_common(5),
            "paragraph_max_df": max(paragraph_df.values(), default=0),
            "sentence_max_df": max(sentence_df.values(), default=0),
        }
        if category.key in {"middle2_math", "middle2_english", "middle3_english"}:
            if len(seeds) != EXPECTED_LOCALITIES or len(set(seeds)) != EXPECTED_LOCALITIES:
                audit.error("source_seed_cardinality", category.key, f"count={len(seeds)}, unique={len(set(seeds))}")
            seed_metrics[category.key] = {
                "count": len(seeds),
                "unique": len(set(seeds)),
                "positive_service_claims": positive_seed_claims,
            }

        overall_h2 += sum(len(item.sections) for item in items)
        overall_faq += sum(len(item.faqs) for item in items)
        overall_reviews += len(items)
        overall_school_chips += sum(len(row.middle_schools) for row in rows)

    if (overall_h2, overall_faq, overall_reviews, overall_school_chips) != (
        EXPECTED_H2, EXPECTED_FAQ, EXPECTED_REVIEWS, EXPECTED_SCHOOL_CHIPS,
    ):
        audit.error(
            "source_aggregate_counts",
            "source",
            f"h2={overall_h2}, faq={overall_faq}, reviews={overall_reviews}, schools={overall_school_chips}",
        )
    if style_occurrences != 183 or len(style_pages) != 158 or any(not value.startswith("middle1_english:") for value in style_pages):
        audit.error("source_style_debt", "수업학교", f"occurrences={style_occurrences}, pages={len(style_pages)}")
    audit.observations["source_contract"] = {
        "details": sum(len(value) for value in corrected_by_category.values()),
        "h2": overall_h2,
        "faq": overall_faq,
        "review_sections": overall_reviews,
        "school_chips": overall_school_chips,
        "corrected_visible_fingerprints": len(all_corrected_fingerprints),
        "style_debt": {"literal": "수업학교", "occurrences": style_occurrences, "pages": len(style_pages)},
        "seeds": seed_metrics,
        "naturalness": naturalness,
    }


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    parent: "Element | None" = None
    children: list["Element | str"] = field(default_factory=list)

    def text(self, *, visible: bool = True) -> str:
        if visible and self.tag in INVISIBLE_TAGS:
            return ""
        return norm(" ".join(child.text(visible=visible) if isinstance(child, Element) else child for child in self.children))

    def descendants(self, *, include_self: bool = False) -> Iterator["Element"]:
        if include_self:
            yield self
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.descendants()


class DOMParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document", {})
        self.stack: list[Element] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        node = Element(name, {key.lower(): value or "" for key, value in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if name not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_dom(value: str, audit: Audit, location: str) -> Element | None:
    parser = DOMParser()
    try:
        parser.feed(value)
        parser.close()
    except Exception as exc:  # noqa: BLE001 - parser errors are audit findings
        audit.error("html_parse", location, repr(exc))
        return None
    return parser.root


def find_elements(root: Element, tag: str | None = None, **attrs: str | None) -> list[Element]:
    result: list[Element] = []
    for node in root.descendants():
        if tag is not None and node.tag != tag:
            continue
        matched = True
        for key, expected in attrs.items():
            actual = node.attrs.get(key.replace("_", "-"))
            if expected is None:
                matched = actual is not None
            else:
                matched = actual == expected
            if not matched:
                break
        if matched:
            result.append(node)
    return result


def has_class(node: Element, value: str) -> bool:
    return value in node.attrs.get("class", "").split()


def ancestor_has_class(node: Element, value: str) -> bool:
    current = node.parent
    while current is not None:
        if has_class(current, value):
            return True
        current = current.parent
    return False


def nodes_with_attr(root: Element, attr: str, value: str | None = None) -> list[Element]:
    return [
        node for node in root.descendants()
        if attr in node.attrs and (value is None or node.attrs[attr] == value)
    ]


def single_node(values: Sequence[Any], audit: Audit, code: str, location: str) -> Any | None:
    if len(values) != 1:
        audit.error(code, location, f"count={len(values)}")
        return None
    return values[0]


def meta_values(dom: Element, *, name: str | None = None, prop: str | None = None) -> list[str]:
    result: list[str] = []
    for node in find_elements(dom, "meta"):
        if name is not None and node.attrs.get("name", "").casefold() != name.casefold():
            continue
        if prop is not None and node.attrs.get("property", "").casefold() != prop.casefold():
            continue
        result.append(node.attrs.get("content", ""))
    return result


def canonical_values(dom: Element) -> list[str]:
    return [node.attrs.get("href", "") for node in find_elements(dom, "link") if "canonical" in node.attrs.get("rel", "").split()]


def json_graph(dom: Element, audit: Audit, location: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    scripts = find_elements(dom, "script", type="application/ld+json")
    if len(scripts) != 1:
        audit.error("jsonld_script_count", location, f"count={len(scripts)}")
    for script in scripts:
        try:
            payload = json.loads(script.text(visible=False))
        except json.JSONDecodeError as exc:
            audit.error("jsonld_parse", location, str(exc))
            continue
        values: Any
        if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
            values = payload["@graph"]
        elif isinstance(payload, list):
            values = payload
        else:
            values = [payload]
        result.extend(value for value in values if isinstance(value, dict))
    return result


def node_types(node: Mapping[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def graph_nodes(graph: Sequence[Mapping[str, Any]], node_type: str) -> list[Mapping[str, Any]]:
    return [node for node in graph if node_type in node_types(node)]


def walk_json(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def faq_schema_pairs(node: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    entities = node.get("mainEntity")
    if not isinstance(entities, list):
        return ()
    for question in entities:
        if not isinstance(question, Mapping):
            continue
        answer = question.get("acceptedAnswer")
        if isinstance(answer, Mapping):
            pairs.append((norm(question.get("name")), norm(answer.get("text"))))
    return tuple(pairs)


@dataclass(frozen=True)
class AssetSet:
    representative_src: str
    body_src: str
    map_src: str
    body_size: tuple[str, str]
    map_size: tuple[str, str]


@dataclass
class View:
    root: Path
    overrides: Mapping[str, str | bytes] = field(default_factory=dict)

    def exists(self, rel: str | Path) -> bool:
        key = Path(rel).as_posix()
        return key in self.overrides or (self.root / Path(key)).is_file()

    def bytes(self, rel: str | Path) -> bytes:
        key = Path(rel).as_posix()
        if key in self.overrides:
            value = self.overrides[key]
            return value if isinstance(value, bytes) else value.encode("utf-8")
        return self.root.joinpath(*PurePosixPath(key).parts).read_bytes()

    def text(self, rel: str | Path) -> str:
        return self.bytes(rel).decode("utf-8")


def detail_rel(category: Category, locality: str) -> str:
    return (Path("학년별학원") / category.slug / locality / "index.html").as_posix()


def category_rel(category: Category) -> str:
    return (Path("학년별학원") / category.slug / "index.html").as_posix()


def expected_new_paths(rows: Sequence[SourceRow]) -> set[str]:
    return {
        *(category_rel(category) for category in CATEGORIES),
        *(detail_rel(category, row.locality) for category in CATEGORIES for row in rows),
    }


def materialization_state(new_html_count: int) -> str:
    if new_html_count == 0:
        return "baseline"
    if new_html_count == EXPECTED_NEW_HTML:
        return "release"
    return "partial"


def local_path_from_site_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != "wawa-center.kr":
            return None
        path = parsed.path
    else:
        path = parsed.path
    decoded = unquote(path).lstrip("/")
    pure = PurePosixPath(decoded)
    if pure.is_absolute() or ".." in pure.parts:
        return None
    return pure.as_posix()


def image_dimensions(path: Path) -> tuple[int, int] | None:
    """Read GIF/PNG/JPEG/WebP dimensions without executing image content."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return (int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little"))
    if data.startswith(b"\xff\xd8"):
        position = 2
        sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while position + 4 <= len(data):
            if data[position] != 0xFF:
                position += 1
                continue
            while position < len(data) and data[position] == 0xFF:
                position += 1
            if position >= len(data):
                break
            marker = data[position]
            position += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if position + 2 > len(data):
                break
            length = int.from_bytes(data[position:position + 2], "big")
            if length < 2 or position + length > len(data):
                break
            if marker in sof and length >= 7:
                return (
                    int.from_bytes(data[position + 5:position + 7], "big"),
                    int.from_bytes(data[position + 3:position + 5], "big"),
                )
            position += length
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        kind = data[12:16]
        if kind == b"VP8X":
            return (1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little"))
        if kind == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            return (int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF)
        if kind == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    return None


def load_generic_assets(root: Path, rows: Sequence[SourceRow], audit: Audit) -> dict[tuple[str, str], AssetSet]:
    result: dict[tuple[str, str], AssetSet] = {}
    unique_files: set[str] = set()
    for subject in ("수학", "영어"):
        subject_slug = subject + "학원"
        for row in rows:
            rel = (Path("과목별학원") / subject_slug / row.locality / "index.html").as_posix()
            path = root.joinpath(*PurePosixPath(rel).parts)
            if not path.is_file():
                audit.error("asset_source_page_missing", rel, "generic subject page missing")
                continue
            try:
                document = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                audit.error("asset_source_page_read", rel, repr(exc))
                continue
            dom = parse_dom(document, audit, f"asset:{rel}")
            if dom is None:
                continue
            representative = meta_values(dom, prop="og:image")
            body = [node for node in find_elements(dom, "img") if ancestor_has_class(node, "math-visible-image")]
            maps = [node for node in find_elements(dom, "img") if ancestor_has_class(node, "math-map-card")]
            if len(representative) != 1 or len(body) != 1 or len(maps) != 1:
                audit.error("asset_source_roles", rel, f"representative={len(representative)}, body={len(body)}, map={len(maps)}")
                continue
            rep_src = local_path_from_site_url(representative[0])
            if rep_src is None:
                audit.error("asset_representative_url", rel, representative[0])
                continue
            body_src = body[0].attrs.get("src", "")
            map_src = maps[0].attrs.get("src", "")
            sources = (rep_src, body_src.lstrip("/"), map_src.lstrip("/"))
            for source in sources:
                source_path = root.joinpath(*PurePosixPath(unquote(source)).parts)
                if not source_path.is_file():
                    audit.error("asset_file_missing", rel, source)
                unique_files.add(source)
            body_dimensions = image_dimensions(root.joinpath(*PurePosixPath(unquote(body_src.lstrip("/"))).parts))
            map_dimensions = image_dimensions(root.joinpath(*PurePosixPath(unquote(map_src.lstrip("/"))).parts))
            if body_dimensions is None or map_dimensions is None:
                body_size = tuple(body[0].attrs.get(key, "") for key in ("width", "height"))
                map_size = tuple(maps[0].attrs.get(key, "") for key in ("width", "height"))
                audit.error("asset_dimensions", rel, f"body={body_size}, map={map_size}")
            else:
                body_size = tuple(map(str, body_dimensions))
                map_size = tuple(map(str, map_dimensions))
            result[(subject, row.locality)] = AssetSet("/" + rep_src, body_src, map_src, body_size, map_size)
    audit.observations["assets"] = {
        "generic_pages": len(result),
        "unique_local_files": len(unique_files),
        "representative_unique": len({value.representative_src for value in result.values()}),
        "body_unique": len({value.body_src for value in result.values()}),
        "map_unique": len({value.map_src for value in result.values()}),
    }
    if len(result) != 742:
        audit.error("asset_generic_count", root, f"actual={len(result)}, expected=742")
    return result


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def physical_address(node: Mapping[str, Any]) -> str:
    value = node.get("address")
    return norm(value.get("streetAddress")) if isinstance(value, Mapping) else ""


def expected_faq_pairs(item: Manuscript) -> tuple[tuple[str, str], ...]:
    return tuple((faq.question, faq.answer) for faq in item.faqs)


def validate_detail_page(
    document: str,
    category: Category,
    item: Manuscript,
    raw_item: Manuscript,
    row: SourceRow,
    assets: AssetSet,
    root: Path,
    audit: Audit,
) -> None:
    rel = detail_rel(category, row.locality)
    dom = parse_dom(document, audit, rel)
    if dom is None:
        return
    expected_url = encoded_url("학년별학원", category.slug, row.locality)
    expected_title = f"{item.title} | 와와학습코칭센터"
    titles = [node.text(visible=False) for node in find_elements(dom, "title")]
    h1 = [node.text() for node in find_elements(dom, "h1")]
    if titles != [expected_title]:
        audit.error("detail_title", rel, repr(titles))
    if h1 != [item.title]:
        audit.error("detail_h1", rel, repr(h1))
    if canonical_values(dom) != [expected_url] or meta_values(dom, prop="og:url") != [expected_url]:
        audit.error("detail_url_identity", rel, repr({"canonical": canonical_values(dom), "og:url": meta_values(dom, prop="og:url")}))
    if meta_values(dom, name="description") != [item.meta]:
        audit.error("detail_meta", rel, repr(meta_values(dom, name="description")))

    expected_status = "supported" if row.supports(category) else "unconfirmed-grade"
    main = single_node(nodes_with_attr(dom, "data-grade-page", category.hook), audit, "detail_main", rel)
    if main is None:
        return
    if main.attrs.get("data-source-status") != expected_status:
        audit.error("detail_status", rel, main.attrs.get("data-source-status", ""))
    article = single_node(nodes_with_attr(main, "data-manuscript"), audit, "detail_article", rel)
    faq_wrapper = single_node(nodes_with_attr(main, "data-faq"), audit, "detail_faq", rel)
    review_wrapper = single_node(nodes_with_attr(main, "data-review"), audit, "detail_review", rel)

    if article is not None:
        headings = [node.text() for node in article.descendants() if node.tag == "h2"]
        if tuple(headings) != item.headings:
            audit.error("detail_h2_roundtrip", rel, f"actual={headings!r}")
        paragraph_nodes = nodes_with_attr(article, "data-manuscript-paragraph")
        expected_paragraphs = item.paragraphs
        raw_paragraphs = raw_item.paragraphs
        if tuple(node.text() for node in paragraph_nodes) != expected_paragraphs:
            audit.error("detail_paragraph_roundtrip", rel, f"actual_count={len(paragraph_nodes)}, expected={len(expected_paragraphs)}")
        hashes = tuple(node.attrs.get("data-source-sha256") for node in paragraph_nodes)
        expected_hashes = tuple(sha256_bytes(value.encode("utf-8")) for value in raw_paragraphs)
        if hashes != expected_hashes:
            audit.error("detail_raw_paragraph_hash", rel, "raw source paragraph hashes differ")
        section_indexes = [node.attrs.get("data-manuscript-section") for node in nodes_with_attr(article, "data-manuscript-section")]
        if section_indexes != [f"{index:02d}" for index in range(1, len(item.sections) + 1)]:
            audit.error("detail_section_indexes", rel, repr(section_indexes))

    if faq_wrapper is not None:
        details = nodes_with_attr(faq_wrapper, "data-source-faq")
        if len(details) != len(item.faqs):
            audit.error("detail_faq_count", rel, f"actual={len(details)}, expected={len(item.faqs)}")
        for node, expected in zip(details, item.faqs, strict=False):
            summary = [value.text() for value in node.descendants() if value.tag == "summary"]
            answers = [value.text() for value in node.descendants() if value.tag == "p"]
            if len(summary) != 1 or expected.question not in summary[0] or len(answers) != 1 or expected.answer not in answers[0]:
                audit.error("detail_faq_roundtrip", rel, f"faq={expected.number}")
    if review_wrapper is not None:
        review_nodes = nodes_with_attr(review_wrapper, "data-source-review")
        if tuple(node.text() for node in review_nodes) != item.review:
            audit.error("detail_review_roundtrip", rel, f"actual={tuple(node.text() for node in review_nodes)!r}")

    source_fields = Counter(node.attrs.get("data-source-field") for node in nodes_with_attr(main, "data-source-field"))
    if source_fields != Counter({"grade": 1, "middle-schools": 1, "address": 1, "registration": 1, "fee": 1}):
        audit.error("detail_source_fields", rel, repr(source_fields))
    school_field = single_node(nodes_with_attr(main, "data-source-field", "middle-schools"), audit, "detail_school_field", rel)
    if school_field is not None:
        expected_school_status = "provided" if row.middle_schools else "missing"
        if school_field.attrs.get("data-source-status") != expected_school_status:
            audit.error("detail_school_status", rel, school_field.attrs.get("data-source-status", ""))
        expected_raw = " | ".join(row.middle_school_source_tokens)
        if school_field.attrs.get("data-source-raw-schools") != expected_raw:
            audit.error("detail_school_raw", rel, repr(school_field.attrs.get("data-source-raw-schools")))
        chips = tuple(node.text() for node in nodes_with_attr(school_field, "data-source-school"))
        if chips != row.middle_schools:
            audit.error("detail_school_chips", rel, f"actual={chips!r}, expected={row.middle_schools!r}")
    for field, fact in (("address", row.address), ("registration", row.registration)):
        node = single_node(nodes_with_attr(main, "data-source-field", field), audit, f"detail_{field}_field", rel)
        if node is not None and fact not in node.text():
            audit.error(f"detail_{field}_fact", rel, node.text())
    fee = single_node(nodes_with_attr(main, "data-source-field", "fee"), audit, "detail_fee_field", rel)
    if fee is not None:
        links = [node.attrs.get("href", "") for node in fee.descendants() if node.tag == "a"]
        if row.fee_url and links != [row.fee_url]:
            audit.error("detail_fee_url", rel, repr(links))
        if not row.fee_url and (links or "원자료에 교습비 링크가 없어" not in fee.text()):
            audit.error("detail_fee_missing_state", rel, fee.text())

    expected_image_url = BASE_URL + quote(assets.representative_src, safe="/%")
    if meta_values(dom, prop="og:image") != [expected_image_url] or meta_values(dom, name="twitter:image") != [expected_image_url]:
        audit.error("detail_representative_asset", rel, repr(meta_values(dom, prop="og:image")))
    images = find_elements(main, "img")
    body_images = [node for node in images if node.attrs.get("data-image-role") == "body"]
    map_images = [node for node in images if node.attrs.get("data-image-role") == "map"]
    if len(body_images) != 1 or len(map_images) != 1:
        audit.error("detail_visible_image_roles", rel, f"body={len(body_images)}, map={len(map_images)}")
    else:
        body, map_image = body_images[0], map_images[0]
        if (
            body.attrs.get("src") != assets.body_src or body.attrs.get("loading") != "eager"
            or body.attrs.get("fetchpriority") != "high" or body.attrs.get("decoding") != "async"
            or (body.attrs.get("width"), body.attrs.get("height")) != assets.body_size
        ):
            audit.error("detail_body_image_policy", rel, repr(body.attrs))
        if (
            map_image.attrs.get("src") != assets.map_src or map_image.attrs.get("loading") != "lazy"
            or map_image.attrs.get("decoding") != "async"
            or (map_image.attrs.get("width"), map_image.attrs.get("height")) != assets.map_size
        ):
            audit.error("detail_map_image_policy", rel, repr(map_image.attrs))
        if any(node.attrs.get("src") == assets.representative_src for node in images):
            audit.error("detail_representative_visible", rel, assets.representative_src)

    main_visible = main.text()
    if any(marker in main_visible for marker in MARKERS) or re.search(r"(?:\$\{|\{fact\}|undefined|\bNone\b)", main_visible):
        audit.error("detail_template_artifact", rel, "source marker/template artifact")
    if MOJIBAKE.search(main_visible) or GUARANTEE.search(main_visible):
        audit.error("detail_visible_quality", rel, "mojibake/guarantee")
    repeated_nodes = [
        (node.tag, INLINE_REPEAT.search(node.text()).group(0))
        for node in main.descendants()
        if node.tag in {"h1", "h2", "h3", "p", "li", "blockquote", "summary", "dt", "dd"}
        and INLINE_REPEAT.search(node.text())
    ]
    if repeated_nodes:
        audit.error("detail_visible_inline_repeat", rel, repr(repeated_nodes[:3]))
    for rule in (value for value in CORRECTIONS if value.category == category.key and row.locality in value.localities):
        if correction_pattern(rule).search(main_visible):
            audit.error("detail_correction_remaining", rel, rule.old)
    if not row.supports(category):
        phrase = f"해당 센터의 {category.grade} {category.subject} 수업 제공을 뜻하지 않습니다"
        alerts = [node for node in main.descendants() if has_class(node, "grade-source-alert")]
        if len(alerts) != 1 or phrase not in alerts[0].text():
            audit.error("detail_unconfirmed_disclaimer", rel, f"alerts={len(alerts)}")
    elif any(has_class(node, "grade-source-alert") for node in main.descendants()):
        audit.error("detail_supported_alert", rel, "supported page has unconfirmed alert")

    graph = json_graph(dom, audit, rel)
    required = ("WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject")
    for node_type in required:
        if len(graph_nodes(graph, node_type)) != 1:
            audit.error("detail_schema_type", rel, f"{node_type}={len(graph_nodes(graph, node_type))}")
    if any(len(graph_nodes(graph, value)) != (1 if row.supports(category) else 0) for value in ("Service", "Offer")):
        audit.error("detail_schema_service_count", rel, f"Service={len(graph_nodes(graph, 'Service'))}, Offer={len(graph_nodes(graph, 'Offer'))}")
    nodes = {node_type: single_node(graph_nodes(graph, node_type), audit, f"detail_schema_{node_type}", rel) for node_type in required}
    organization = nodes.get("EducationalOrganization")
    local_business = nodes.get("LocalBusiness")
    article_schema = nodes.get("Article")
    webpage = nodes.get("WebPage")
    faq_schema = nodes.get("FAQPage")
    breadcrumb = nodes.get("BreadcrumbList")
    item_list = nodes.get("ItemList")
    image_object = nodes.get("ImageObject")
    for label, node in (("organization", organization), ("local_business", local_business)):
        if node is None:
            continue
        if norm(node.get("name")) != row.center_name or physical_address(node) != row.address:
            audit.error("detail_schema_physical", rel, f"{label}: name/address mismatch")
        identifier = node.get("identifier")
        if not isinstance(identifier, Mapping) or norm(identifier.get("value")) != row.registration:
            audit.error("detail_schema_identifier", rel, label)
        area = node.get("areaServed")
        if not isinstance(area, Mapping) or norm(area.get("name")) != row.locality:
            audit.error("detail_schema_area", rel, label)
    if organization is not None and tuple(map(norm, organization.get("educationalLevel", []))) != row.grades(category):
        audit.error(
            "detail_schema_educational_level",
            rel,
            f"actual={organization.get('educationalLevel')!r}, expected={row.grades(category)!r}",
        )
    if article_schema is not None:
        if (
            norm(article_schema.get("headline")) != item.title
            or norm(article_schema.get("description")) != item.summary
            or tuple(map(norm, article_schema.get("articleSection", []))) != item.headings
            or article_schema.get("image") != expected_image_url
        ):
            audit.error("detail_schema_article_parity", rel, "headline/description/sections/image mismatch")
        for prop in ("about", "mentions", "hasPart"):
            if not isinstance(article_schema.get(prop), list) or not article_schema[prop]:
                audit.error("detail_schema_article_relation", rel, prop)
    if webpage is not None:
        if webpage.get("url") != expected_url or norm(webpage.get("description")) != item.meta:
            audit.error("detail_schema_webpage_parity", rel, "url/description mismatch")
        for prop in ("about", "mentions", "hasPart"):
            if not isinstance(webpage.get(prop), list) or not webpage[prop]:
                audit.error("detail_schema_webpage_relation", rel, prop)
    if faq_schema is not None and faq_schema_pairs(faq_schema) != expected_faq_pairs(item):
        audit.error("detail_schema_faq_parity", rel, repr(faq_schema_pairs(faq_schema)))
    expected_schools = row.middle_schools
    for label, node in (("WebPage", webpage), ("Article", article_schema)):
        if node is None:
            continue
        schools = tuple(
            norm(value.get("name")) for value in node.get("mentions", [])
            if isinstance(value, Mapping) and value.get("@type") == "EducationalOrganization"
        )
        if schools != expected_schools:
            audit.error("detail_schema_school_mentions", rel, f"{label}={schools!r}")
    if breadcrumb is not None:
        values = breadcrumb.get("itemListElement")
        expected_names = ["홈", "학년별학원", category.label, item.title]
        expected_urls = [BASE_URL + "/", encoded_url("학년별학원"), encoded_url("학년별학원", category.slug), expected_url]
        if not isinstance(values, list) or [norm(value.get("name")) for value in values if isinstance(value, Mapping)] != expected_names or [value.get("item") for value in values if isinstance(value, Mapping)] != expected_urls:
            audit.error("detail_schema_breadcrumb", rel, repr(values))
    if item_list is not None:
        values = item_list.get("itemListElement")
        if not isinstance(values, list) or len(values) != 7:
            audit.error("detail_schema_itemlist", rel, repr(values))
        else:
            positions = [value.get("position") for value in values if isinstance(value, Mapping)]
            urls = [value.get("url") for value in values if isinstance(value, Mapping)]
            if positions != list(range(1, 8)) or any(not isinstance(url, str) or not url.startswith(BASE_URL + "/") for url in urls):
                audit.error("detail_schema_itemlist", rel, repr({"positions": positions, "urls": urls}))
    if image_object is not None:
        image_size = image_dimensions(root.joinpath(*PurePosixPath(unquote(assets.representative_src.lstrip("/"))).parts))
        if image_object.get("url") != expected_image_url or image_object.get("contentUrl") != expected_image_url or image_size is None or (image_object.get("width"), image_object.get("height")) != image_size:
            audit.error("detail_schema_image", rel, repr(image_object))

    if row.supports(category):
        service = single_node(graph_nodes(graph, "Service"), audit, "detail_schema_service", rel)
        offer = single_node(graph_nodes(graph, "Offer"), audit, "detail_schema_offer", rel)
        if service is not None:
            audience = service.get("audience")
            if (
                category.grade not in norm(service.get("serviceType"))
                or category.subject not in norm(service.get("serviceType"))
                or not isinstance(audience, Mapping)
                or category.grade not in norm(audience.get("audienceType"))
            ):
                audit.error("detail_schema_service_parity", rel, repr(service))
        if offer is not None and offer.get("url") != (row.fee_url or expected_url):
            audit.error("detail_schema_offer_url", rel, repr(offer.get("url")))
        for label, node in (("organization", organization), ("local_business", local_business)):
            if node is not None and not isinstance(node.get("makesOffer"), list):
                audit.error("detail_schema_makes_offer", rel, label)
    else:
        for label, node in (("organization", organization), ("local_business", local_business)):
            if node is not None and "makesOffer" in node:
                audit.error("detail_schema_unconfirmed_offer", rel, label)

    seed = auxiliary_seed(item)
    if seed:
        forbidden_nodes = [*graph_nodes(graph, "Service"), *graph_nodes(graph, "Offer")]
        if any(seed in json_text(node) for node in forbidden_nodes):
            audit.error("detail_schema_seed_service", rel, seed)
        if organization is not None and seed in json_text(organization.get("knowsAbout", [])):
            audit.error("detail_schema_seed_knowsabout", rel, seed)


def validate_details(
    view: View,
    corrected_by_category: Mapping[str, Sequence[Manuscript]],
    parsed_by_category: Mapping[str, Sequence[Manuscript]],
    rows: Sequence[SourceRow],
    assets: Mapping[tuple[str, str], AssetSet],
    audit: Audit,
    mode: str,
) -> None:
    missing: list[str] = []
    validated = 0
    for category in CATEGORIES:
        fixed = {item.locality: item for item in corrected_by_category.get(category.key, ())}
        raw = {item.locality: item for item in parsed_by_category.get(category.key, ())}
        for row in rows:
            rel = detail_rel(category, row.locality)
            if not view.exists(rel):
                missing.append(rel)
                continue
            if row.locality not in fixed or row.locality not in raw or (category.subject, row.locality) not in assets:
                audit.error("detail_input_alignment", rel, "manuscript/source asset missing")
                continue
            try:
                document = view.text(rel)
            except (OSError, UnicodeError) as exc:
                audit.error("detail_read", rel, repr(exc))
                continue
            validate_detail_page(document, category, fixed[row.locality], raw[row.locality], row, assets[(category.subject, row.locality)], view.root, audit)
            validated += 1
    if missing:
        message = f"missing={len(missing)}, sample={missing[:5]}"
        if mode == "actual" and len(missing) == EXPECTED_NEW_DETAILS:
            audit.hold("detail_pages_missing", "학년별학원", message)
        else:
            audit.error("detail_pages_missing", "학년별학원", message)
    audit.observations["rendered_details"] = {"validated": validated, "missing": len(missing)}


def validate_hub_document(
    document: str,
    rel: str,
    canonical: str,
    expected_h1: str,
    expected_items: Sequence[tuple[str, str]],
    audit: Audit,
    *,
    directory_hook: str,
    localities: Sequence[str] | None = None,
) -> None:
    dom = parse_dom(document, audit, rel)
    if dom is None:
        return
    if canonical_values(dom) != [canonical] or meta_values(dom, prop="og:url") != [canonical]:
        audit.error("hub_url_identity", rel, repr({"canonical": canonical_values(dom), "og:url": meta_values(dom, prop="og:url")}))
    h1_values = [node.text() for node in find_elements(dom, "h1")]
    if h1_values != [expected_h1]:
        audit.error("hub_h1", rel, repr(h1_values))
    main = single_node(nodes_with_attr(dom, "data-grade-directory", directory_hook), audit, "hub_main", rel)
    if main is None:
        return
    graph = json_graph(dom, audit, rel)
    for node_type in ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage"):
        if len(graph_nodes(graph, node_type)) != 1:
            audit.error("hub_schema_type", rel, f"{node_type}={len(graph_nodes(graph, node_type))}")
    item_list = single_node(graph_nodes(graph, "ItemList"), audit, "hub_itemlist", rel)
    if item_list is not None:
        items = item_list.get("itemListElement")
        actual: list[tuple[str, str]] = []
        positions: list[Any] = []
        if isinstance(items, list):
            for value in items:
                if isinstance(value, Mapping):
                    actual.append((norm(value.get("name")), str(value.get("url", ""))))
                    positions.append(value.get("position"))
        if actual != list(expected_items) or positions != list(range(1, len(expected_items) + 1)) or item_list.get("numberOfItems") != len(expected_items):
            audit.error("hub_itemlist_parity", rel, f"count={len(actual)}, positions={positions[:5]}")
    faq_schema = single_node(graph_nodes(graph, "FAQPage"), audit, "hub_faq_schema", rel)
    visible_faq = single_node(nodes_with_attr(main, "data-faq"), audit, "hub_faq_visible", rel)
    if faq_schema is not None and len(faq_schema_pairs(faq_schema)) != 2:
        audit.error("hub_faq_count", rel, f"schema={len(faq_schema_pairs(faq_schema))}")
    if visible_faq is not None and len([node for node in visible_faq.descendants() if node.tag == "details"]) != 2:
        audit.error("hub_faq_visible_count", rel, "expected two details")
    collection = single_node(graph_nodes(graph, "CollectionPage"), audit, "hub_collection", rel)
    if collection is not None:
        if collection.get("url") != canonical or not collection.get("about") or not collection.get("hasPart"):
            audit.error("hub_collection_relations", rel, "url/about/hasPart")
    if localities is not None:
        visible_localities = [node.attrs.get("data-grade-locality", "") for node in nodes_with_attr(main, "data-grade-locality")]
        if visible_localities != list(localities):
            audit.error("hub_visible_localities", rel, f"actual={len(visible_localities)}, expected={len(localities)}")
        for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
            if len(nodes_with_attr(main, hook)) != 1:
                audit.error("hub_search_hook", rel, hook)
        if "toLocaleLowerCase('ko-KR')" not in document or "input.value = ''" not in document or "전체 371개 지역" not in document:
            audit.error("hub_search_script", rel, "search/clear/status behavior missing")


def validate_hubs(view: View, rows: Sequence[SourceRow], audit: Audit, mode: str) -> None:
    missing = [category_rel(category) for category in CATEGORIES if not view.exists(category_rel(category))]
    if missing:
        message = f"missing={len(missing)}, paths={missing}"
        if mode == "actual" and len(missing) == EXPECTED_NEW_CATEGORIES:
            audit.hold("category_hubs_missing", "학년별학원", message)
        else:
            audit.error("category_hubs_missing", "학년별학원", message)
    else:
        for category in CATEGORIES:
            rel = category_rel(category)
            items = [(f"{row.locality} {category.label}", encoded_url("학년별학원", category.slug, row.locality)) for row in rows]
            validate_hub_document(
                view.text(rel), rel, encoded_url("학년별학원", category.slug),
                f"{category.label} 371개 지역 안내", items, audit,
                directory_hook=category.hook, localities=[row.locality for row in rows],
            )

    parent_rel = PARENT_REL.as_posix()
    if not view.exists(parent_rel):
        audit.error("parent_hub_missing", parent_rel, "existing parent hub missing")
        return
    if mode == "actual":
        if sha256_bytes(view.bytes(parent_rel)) != BASE_PARENT_SHA256:
            audit.error("parent_hub_baseline", parent_rel, sha256_bytes(view.bytes(parent_rel)))
        audit.hold("parent_hub_update", parent_rel, "baseline has only the existing 중3 수학 category; six-category update not generated")
        return
    parent_items = [(label, encoded_url("학년별학원", slug)) for label, slug in ALL_CATEGORY_LABELS]
    validate_hub_document(
        view.text(parent_rel), parent_rel, encoded_url("학년별학원"),
        "학년별학원에서 학년과 과목을 고르고 지역 안내를 확인하세요",
        parent_items, audit, directory_hook="parent",
    )
    dom = parse_dom(view.text(parent_rel), audit, parent_rel + ":cards")
    if dom is not None:
        links = [
            (node.text(), node.attrs.get("href", ""))
            for node in find_elements(dom, "a") if has_class(node, "subject-category-card")
        ]
        expected_hrefs = [f"/학년별학원/{slug}/" for _, slug in ALL_CATEGORY_LABELS]
        if [href for _, href in links] != expected_hrefs or any(label not in text for (text, _), (label, _) in zip(links, ALL_CATEGORY_LABELS, strict=False)):
            audit.error("parent_hub_cards", parent_rel, repr(links))


def parse_sitemap(document: str, audit: Audit, location: str) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    for match in RAW_URL_BLOCK.finditer(document):
        block = match.group(0)
        locations = LOC.findall(block)
        lastmods = LASTMOD.findall(block)
        if len(locations) != 1 or len(lastmods) != 1:
            audit.error("sitemap_block", location, f"loc={len(locations)}, lastmod={len(lastmods)}")
            continue
        result.append((html.unescape(locations[0]), html.unescape(lastmods[0]), block))
    return tuple(result)


def validate_sitemap(view: View, root: Path, rows: Sequence[SourceRow], audit: Audit, mode: str) -> None:
    rel = SITEMAP_REL.as_posix()
    if not view.exists(rel):
        audit.error("sitemap_missing", rel, "missing")
        return
    document = view.text(rel)
    blocks = parse_sitemap(document, audit, rel)
    expected_new = tuple(
        url
        for category in CATEGORIES
        for url in (
            encoded_url("학년별학원", category.slug),
            *(encoded_url("학년별학원", category.slug, row.locality) for row in rows),
        )
    )
    if mode == "actual":
        if sha256_bytes(view.bytes(rel)) != BASE_SITEMAP_SHA256 or len(blocks) != EXPECTED_BASE_HTML:
            audit.error("sitemap_baseline", rel, f"hash={sha256_bytes(view.bytes(rel))}, blocks={len(blocks)}")
        if any(location in set(expected_new) for location, _, _ in blocks):
            audit.error("sitemap_baseline_new_url", rel, "partial new URL set")
        audit.hold("sitemap_update", rel, f"new URL blocks pending={len(expected_new)}")
        return
    try:
        # Path.read_text() performs universal-newline translation.  Compare the
        # decoded bytes so preserved CRLF URL blocks remain byte-significant.
        base_document = (root / SITEMAP_REL).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        audit.error("sitemap_base_read", rel, repr(exc))
        return
    base_blocks = parse_sitemap(base_document, audit, "baseline:sitemap")
    if len(blocks) != EXPECTED_FINAL_HTML or len({value[0] for value in blocks}) != EXPECTED_FINAL_HTML:
        audit.error("sitemap_final_count", rel, f"blocks={len(blocks)}, unique={len({value[0] for value in blocks})}")
    if blocks[:EXPECTED_BASE_HTML] != base_blocks or len(base_blocks) != EXPECTED_BASE_HTML:
        audit.error("sitemap_existing_preservation", rel, f"base={len(base_blocks)}, prefix={len(blocks[:EXPECTED_BASE_HTML])}")
    actual_new = tuple(value[0] for value in blocks[EXPECTED_BASE_HTML:])
    if actual_new != expected_new:
        audit.error("sitemap_new_order", rel, f"actual={len(actual_new)}, expected={len(expected_new)}")
    if any(value[1] != RELEASE_DATE for value in blocks[EXPECTED_BASE_HTML:]):
        audit.error("sitemap_new_lastmod", rel, "new lastmod differs")
    audit.observations["sitemap"] = {"blocks": len(blocks), "new": len(actual_new), "unique": len({value[0] for value in blocks})}


def validate_llms(view: View, root: Path, audit: Audit, mode: str) -> None:
    rel = LLMS_REL.as_posix()
    if not view.exists(rel):
        audit.error("llms_missing", rel, "missing")
        return
    document = view.text(rel)
    if mode == "actual":
        if sha256_bytes(view.bytes(rel)) != BASE_LLMS_SHA256:
            audit.error("llms_baseline", rel, sha256_bytes(view.bytes(rel)))
        audit.hold("llms_update", rel, "five category references pending")
        return
    # The preserved prefix is CRLF in the baseline while the replacement block
    # is LF.  Decode bytes directly rather than normalizing newlines on read.
    base = (root / LLMS_REL).read_bytes().decode("utf-8")
    if LLMS_MARKER not in base or document[:document.index(LLMS_MARKER)] != base[:base.index(LLMS_MARKER)]:
        audit.error("llms_prefix_preservation", rel, "pre-grade block differs")
    if document.count(LLMS_MARKER) != 1:
        audit.error("llms_marker", rel, f"count={document.count(LLMS_MARKER)}")
    # llms.txt intentionally publishes readable Unicode URLs; HTML/schema and
    # sitemap use the percent-encoded canonical form checked elsewhere.
    expected_urls = [
        BASE_URL + "/학년별학원/",
        *(BASE_URL + f"/학년별학원/{slug}/" for _, slug in ALL_CATEGORY_LABELS),
    ]
    url_tokens = Counter(re.findall(r"https://wawa-center\.kr/[^\s]+", document))
    for url in expected_urls:
        if url_tokens[url] != 1:
            audit.error("llms_url", rel, f"url={url}, count={url_tokens[url]}")
    audit.observations["llms"] = {"marker": document.count(LLMS_MARKER), "grade_urls": len(expected_urls)}


def files_manifest(root: Path, relative_paths: Iterable[str | Path], overrides: Mapping[str, str | bytes] | None = None) -> str:
    overrides = overrides or {}
    digest = hashlib.sha256()
    for value in sorted((Path(item).as_posix() for item in relative_paths)):
        if value in overrides:
            source = overrides[value]
            data = source if isinstance(source, bytes) else source.encode("utf-8")
        else:
            data = root.joinpath(*PurePosixPath(value).parts).read_bytes()
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_bytes(data).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def baseline_html_paths(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*.html") if ".git" not in path.relative_to(root).parts}


def validate_baseline(root: Path, audit: Audit) -> set[str]:
    html_paths = baseline_html_paths(root)
    new_roots = {f"학년별학원/{category.slug}" for category in CATEGORIES}
    existing_new = {
        value for value in html_paths
        if any(value == f"{prefix}/index.html" or value.startswith(prefix + "/") for prefix in new_roots)
    }
    if existing_new and len(existing_new) != EXPECTED_NEW_HTML:
        audit.error("baseline_partial_new_tree", root, f"actual={len(existing_new)}, expected=0 or {EXPECTED_NEW_HTML}")
    expected_count = EXPECTED_BASE_HTML + (EXPECTED_NEW_HTML if existing_new else 0)
    if len(html_paths) != expected_count:
        audit.error("baseline_html_count", root, f"actual={len(html_paths)}, expected={expected_count}")
    immutable = {value for value in html_paths if value != PARENT_REL.as_posix() and value not in existing_new}
    if len(immutable) != EXPECTED_IMMUTABLE_HTML:
        audit.error("baseline_immutable_count", root, f"actual={len(immutable)}, expected={EXPECTED_IMMUTABLE_HTML}")
    elif files_manifest(root, immutable) != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        audit.error("baseline_immutable_manifest", root, f"actual={files_manifest(root, immutable)}")
    middle3 = {
        value for value in immutable
        if value == (MIDDLE3_MATH_ROOT / "index.html").as_posix()
        or value.startswith(MIDDLE3_MATH_ROOT.as_posix() + "/")
    }
    if len(middle3) != 372 or files_manifest(root, middle3) != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
        audit.error("baseline_middle3_math_freeze", MIDDLE3_MATH_ROOT, f"count={len(middle3)}, manifest={files_manifest(root, middle3) if middle3 else ''}")
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True,
            text=True, encoding="utf-8", timeout=20,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        audit.error("git_head", root, repr(exc))
        head = ""
    if head != EXPECTED_BASE_HEAD:
        audit.error("git_head", root, f"actual={head}, expected={EXPECTED_BASE_HEAD}")
    audit.observations["baseline"] = {
        "head": head,
        "html": len(html_paths),
        "new_html_present": len(existing_new),
        "immutable_html": len(immutable),
        "immutable_manifest_sha256": files_manifest(root, immutable) if immutable else "",
        "middle3_math_html": len(middle3),
    }
    return html_paths


RESIDUE_SUFFIXES = (".pyc", ".pyo", ".txn", ".journal", ".rollback", ".partial", ".bak", ".tmp")
TRACKED_BASELINE_RESIDUE = {
    "tmp/__pycache__/generate_topic_child_pages.cpython-313.pyc":
        "3902772278900f03b38fab62e8a638152716069e466472b8ad50c700dfd5d1b5",
}


def validate_residue(root: Path, audit: Audit) -> None:
    residue: list[str] = []
    transaction_prefixes = (".grade3-math-transaction-", ".middle-grade-transaction-")
    allowed_dirs = {PurePosixPath(value).parent.as_posix() for value in TRACKED_BASELINE_RESIDUE}
    for rel, expected_sha in TRACKED_BASELINE_RESIDUE.items():
        path = root.joinpath(*PurePosixPath(rel).parts)
        actual_sha = sha256_file(path) if path.is_file() else "missing"
        try:
            head_bytes = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{rel}"], check=True,
                capture_output=True, timeout=20,
            ).stdout
            head_sha = sha256_bytes(head_bytes)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            audit.error("tracked_residue_head", rel, repr(exc))
            head_sha = "unavailable"
        if actual_sha != expected_sha or head_sha != expected_sha:
            audit.error("tracked_residue_drift", rel, f"actual={actual_sha}, head={head_sha}, expected={expected_sha}")
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        rel_posix = rel.as_posix()
        if ".git" in rel.parts or ".vercel" in rel.parts or "node_modules" in rel.parts:
            continue
        if rel_posix in TRACKED_BASELINE_RESIDUE or rel_posix in allowed_dirs:
            continue
        if path.is_dir() and (path.name == "__pycache__" or path.name.startswith(transaction_prefixes)):
            residue.append(rel_posix + "/")
        elif path.is_file() and path.suffix.casefold() in RESIDUE_SUFFIXES:
            residue.append(rel_posix)
    if residue:
        audit.error("release_residue", root, repr(sorted(residue)[:50]))
    audit.observations["residue"] = {
        "count": len(residue), "paths": sorted(residue)[:50],
        "tracked_baseline_allowlist": TRACKED_BASELINE_RESIDUE,
    }


def repository_snapshot(root: Path) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in {".git", ".vercel", "node_modules", "__pycache__"} for part in rel.parts):
            continue
        result[rel.as_posix()] = (path.stat().st_size, sha256_file(path))
    return result


def source_snapshot(zip_dir: Path, common: Path, root: Path) -> dict[str, str]:
    paths = [
        *(zip_dir / category.zip_name for category in CATEGORIES),
        *(common / name for name in COMMON_HASHES),
        root / GENERATOR_REL,
        root / "tools/generate_grade3_math_pages.py",
    ]
    return {str(path.resolve()): sha256_file(path) for path in paths if path.is_file()}


def import_pinned_generator(root: Path, audit: Audit) -> ModuleType | None:
    path = root / GENERATOR_REL
    if not path.is_file():
        audit.error("generator_missing", path, "missing")
        return None
    actual = sha256_file(path)
    if EXPECTED_GENERATOR_SHA256 == "PENDING":
        audit.hold("generator_pin_pending", path, f"actual={actual}")
        return None
    if actual != EXPECTED_GENERATOR_SHA256:
        audit.error("generator_hash", path, f"actual={actual}, expected={EXPECTED_GENERATOR_SHA256}")
        return None
    name = f"_pinned_middle_grade_generator_{actual[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        audit.error("generator_import_spec", path, "loader unavailable")
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - pinned module failures are audit findings
        sys.modules.pop(name, None)
        audit.error("generator_import", path, repr(exc))
        return None
    build_plan = getattr(module, "build_plan", None)
    if not callable(build_plan):
        audit.error("generator_api", path, "build_plan missing")
        return None
    parameters = tuple(inspect.signature(build_plan).parameters)
    if parameters != ("root", "zip_paths", "common_dir", "current_overrides"):
        audit.error("generator_api_signature", path, repr(parameters))
        return None
    return module


def normalized_plan_documents(plan: Any, root: Path, audit: Audit) -> dict[str, str | bytes]:
    source = getattr(plan, "authorized_documents", None)
    if not isinstance(source, Mapping):
        audit.error("plan_documents", "build_plan", "authorized_documents is not a mapping")
        return {}
    result: dict[str, str | bytes] = {}
    for key, value in source.items():
        path = Path(key)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(root)
            except ValueError:
                audit.error("plan_document_path", key, "outside repository")
                continue
        rel = path.as_posix()
        if rel.startswith("../") or rel in result or not isinstance(value, (str, bytes)):
            audit.error("plan_document", rel, "unsafe/duplicate/non-text value")
            continue
        result[rel] = value
    return result


def build_projected_view(
    root: Path,
    zip_dir: Path,
    common: Path,
    rows: Sequence[SourceRow],
    audit: Audit,
) -> View | None:
    module = import_pinned_generator(root, audit)
    if module is None:
        return None
    before_repo = repository_snapshot(root)
    before_source = source_snapshot(zip_dir, common, root)
    zip_paths = {category.key: zip_dir / category.zip_name for category in CATEGORIES}
    try:
        plan = module.build_plan(root, zip_paths, common)
    except Exception as exc:  # noqa: BLE001 - generator exceptions are findings
        audit.error("plan_build", GENERATOR_REL, repr(exc))
        return None
    after_source = source_snapshot(zip_dir, common, root)
    after_repo = repository_snapshot(root)
    if before_source != after_source:
        audit.error("plan_source_write", GENERATOR_REL, "source/generator snapshot changed during build_plan")
    if before_repo != after_repo:
        changed = sorted(set(before_repo) ^ set(after_repo) | {key for key in before_repo.keys() & after_repo.keys() if before_repo[key] != after_repo[key]})
        audit.error("plan_repository_write", GENERATOR_REL, repr(changed[:50]))

    documents = normalized_plan_documents(plan, root, audit)
    expected_authorized = {
        PARENT_REL.as_posix(), SITEMAP_REL.as_posix(), LLMS_REL.as_posix(), *expected_new_paths(rows),
    }
    if set(documents) != expected_authorized or len(documents) != EXPECTED_AUTHORIZED:
        audit.error(
            "plan_authorized_paths", GENERATOR_REL,
            f"actual={len(documents)}, missing={sorted(expected_authorized-set(documents))[:5]}, extra={sorted(set(documents)-expected_authorized)[:5]}",
        )
    changed_paths = {Path(value).as_posix() for value in getattr(plan, "changed_paths", ())}
    if changed_paths not in (set(), expected_authorized):
        audit.error("plan_changed_paths", GENERATOR_REL, f"actual={len(changed_paths)}")
    second = tuple(getattr(plan, "second_pass_changes", ()))
    if second:
        audit.error("plan_second_pass", GENERATOR_REL, repr(second[:10]))
    after_manifest = getattr(plan, "after_manifest", {})
    if not isinstance(after_manifest, Mapping) or len(after_manifest) != EXPECTED_AUTHORIZED:
        audit.error("plan_after_manifest", GENERATOR_REL, f"count={len(after_manifest) if isinstance(after_manifest, Mapping) else 'invalid'}")
    else:
        for key, value in documents.items():
            expected_hash = after_manifest.get(Path(key))
            actual_hash = sha256_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
            if expected_hash != actual_hash:
                audit.error("plan_after_hash", key, f"actual={actual_hash}, plan={expected_hash}")
    source_manifest = dict(getattr(plan, "source_manifest", {}))
    expected_source_manifest = {
        **{f"zip:{category.key}": category.zip_sha256 for category in CATEGORIES},
        "center_csv": COMMON_HASHES["센터정보 정리.csv"],
        "target_school_csv": COMMON_HASHES["타깃학교.csv"],
        "base_helper": "1fbba380481affe0b4f9888630f90caccb8bfca39342284819f8a2fb265d31cf",
    }
    if source_manifest != expected_source_manifest:
        audit.error("plan_source_manifest", GENERATOR_REL, repr(source_manifest))
    source_metrics = dict(getattr(plan, "source_metrics", {}))
    expected_source_metrics = {
        "zip_archives": 5,
        "zip_members": EXPECTED_NEW_DETAILS,
        "zip_uncompressed_bytes": sum(category.uncompressed_bytes for category in CATEGORIES),
        "source_h2": EXPECTED_H2,
        "source_faq": EXPECTED_FAQ,
        "source_reviews": EXPECTED_REVIEWS,
        "supported_pages": EXPECTED_SUPPORTED,
        "unconfirmed_pages": EXPECTED_UNCONFIRMED,
        "exact_address_pages": EXPECTED_NEW_DETAILS,
        "raw_school_tokens": EXPECTED_SCHOOL_CHIPS,
        "visible_school_chips": EXPECTED_SCHOOL_CHIPS,
        "missing_school_groups": 265,
        "attached_raw_school_tokens_preserved": 10,
        "attached_visible_school_tokens_corrected": 10,
        "existing_english_generic_math_levels_rebased_to_english": 371,
        "representative_sources": 742,
        "body_sources": 2,
        "map_sources": 371,
        "correction_rules": EXPECTED_CORRECTION_RULES,
        "correction_pages": EXPECTED_CORRECTION_PAGES,
        "literal_occurrences_corrected": EXPECTED_CORRECTION_OCCURRENCES,
        "raw_manuscript_bytes_preserved": EXPECTED_NEW_DETAILS,
        "non_allowlisted_visible_source_changes": 0,
        "auxiliary_seed_pages": 1_113,
        "auxiliary_seed_schema_gate_pages": EXPECTED_NEW_DETAILS,
        "auxiliary_seed_service_offer_knowsabout_conflicts": 0,
    }
    metric_diffs = {
        key: {"actual": source_metrics.get(key), "expected": expected}
        for key, expected in expected_source_metrics.items()
        if source_metrics.get(key) != expected
    }
    expected_seed_counts = {
        "middle1_math": 0, "middle1_english": 0, "middle2_math": 371,
        "middle2_english": 371, "middle3_english": 371,
    }
    if source_metrics.get("auxiliary_seed_unique_by_category") != expected_seed_counts:
        metric_diffs["auxiliary_seed_unique_by_category"] = {
            "actual": source_metrics.get("auxiliary_seed_unique_by_category"), "expected": expected_seed_counts,
        }
    if metric_diffs:
        audit.error("plan_source_metrics", GENERATOR_REL, repr(metric_diffs))
    after_metrics = dict(getattr(plan, "after_metrics", {}))
    expected_after_metrics = {
        "authorized_documents": EXPECTED_AUTHORIZED,
        "final_html_documents": EXPECTED_FINAL_HTML,
        "new_html_documents": EXPECTED_NEW_HTML,
        "new_category_hubs": EXPECTED_NEW_CATEGORIES,
        "new_detail_documents": EXPECTED_NEW_DETAILS,
        "parent_hub_categories": 6,
        "sitemap_urls": EXPECTED_FINAL_HTML,
        "sitemap_existing_blocks_preserved": EXPECTED_BASE_HTML,
        "sitemap_new_urls_appended": EXPECTED_NEW_HTML,
        "sitemap_new_lastmod": RELEASE_DATE,
        "supported_service_offer_pages": EXPECTED_SUPPORTED,
        "unconfirmed_article_only_pages": EXPECTED_UNCONFIRMED,
        "school_chips": EXPECTED_SCHOOL_CHIPS,
        "second_pass_changes": 0,
    }
    after_diffs = {
        key: {"actual": after_metrics.get(key), "expected": expected}
        for key, expected in expected_after_metrics.items()
        if after_metrics.get(key) != expected
    }
    if after_diffs:
        audit.error("plan_after_metrics", GENERATOR_REL, repr(after_diffs))
    if (
        getattr(plan, "immutable_html_manifest_sha256", None) != BASE_IMMUTABLE_HTML_MANIFEST_SHA256
        or getattr(plan, "middle3_math_manifest_sha256", None) != BASE_MIDDLE3_MATH_MANIFEST_SHA256
    ):
        audit.error("plan_freeze_manifest", GENERATOR_REL, "immutable/middle3 plan manifest differs")
    candidate = str(getattr(plan, "candidate_sha256", ""))
    if EXPECTED_CANDIDATE_SHA256 == "PENDING":
        audit.hold("candidate_pin_pending", GENERATOR_REL, f"actual={candidate}")
    elif candidate != EXPECTED_CANDIDATE_SHA256:
        audit.error("candidate_hash", GENERATOR_REL, f"actual={candidate}, expected={EXPECTED_CANDIDATE_SHA256}")
    immutable = set(baseline_html_paths(root)) - {PARENT_REL.as_posix()} - expected_new_paths(rows)
    if len(immutable) != EXPECTED_IMMUTABLE_HTML or files_manifest(root, immutable) != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        audit.error("plan_immutable_freeze", root, f"count={len(immutable)}, manifest={files_manifest(root, immutable) if immutable else ''}")
    audit.observations["plan"] = {
        "generator_sha256": sha256_file(root / GENERATOR_REL),
        "candidate_sha256": candidate,
        "authorized_documents": len(documents),
        "changed_paths": len(changed_paths),
        "second_pass_changes": len(second),
        "source_manifest": source_manifest,
        "source_metrics_checked": len(expected_source_metrics) + 1,
        "after_metrics_checked": len(expected_after_metrics),
        "write_set": len(set(before_repo) ^ set(after_repo) | {key for key in before_repo.keys() & after_repo.keys() if before_repo[key] != after_repo[key]}),
    }
    return View(root, documents)


def git_head_bytes(root: Path, rel: str, audit: Audit) -> bytes | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{rel}"], check=True,
            capture_output=True, timeout=30,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        audit.error("release_head_blob", rel, repr(exc))
        return None


def normalized_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def validate_release_sitemap(view: View, root: Path, rows: Sequence[SourceRow], audit: Audit) -> None:
    rel = SITEMAP_REL.as_posix()
    try:
        document = view.text(rel)
    except (OSError, UnicodeError) as exc:
        audit.error("release_sitemap_read", rel, repr(exc))
        return
    head_raw = git_head_bytes(root, rel, audit)
    if head_raw is None:
        return
    try:
        head_document = head_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        audit.error("release_sitemap_head_encoding", rel, repr(exc))
        return
    blocks = parse_sitemap(document, audit, "release:sitemap")
    head_blocks = parse_sitemap(head_document, audit, "HEAD:sitemap")
    if len(head_blocks) != EXPECTED_BASE_HTML:
        audit.error("release_sitemap_head_count", rel, f"actual={len(head_blocks)}, expected={EXPECTED_BASE_HTML}")
    normalized_prefix = tuple(normalized_newlines(value[2]) for value in blocks[:EXPECTED_BASE_HTML])
    normalized_head = tuple(normalized_newlines(value[2]) for value in head_blocks)
    if normalized_prefix != normalized_head:
        audit.error("release_sitemap_prefix", rel, "HEAD URL blocks differ after newline normalization")
    expected_new = tuple(
        url
        for category in CATEGORIES
        for url in (
            encoded_url("학년별학원", category.slug),
            *(encoded_url("학년별학원", category.slug, row.locality) for row in rows),
        )
    )
    if len(blocks) != EXPECTED_FINAL_HTML or len({value[0] for value in blocks}) != EXPECTED_FINAL_HTML:
        audit.error("release_sitemap_count", rel, f"blocks={len(blocks)}, unique={len({value[0] for value in blocks})}")
    if tuple(value[0] for value in blocks[EXPECTED_BASE_HTML:]) != expected_new:
        audit.error("release_sitemap_new_order", rel, "new canonical URL block/order differs")
    if any(value[1] != RELEASE_DATE for value in blocks[EXPECTED_BASE_HTML:]):
        audit.error("release_sitemap_new_lastmod", rel, "new lastmod differs")
    audit.observations["sitemap"] = {
        "blocks": len(blocks), "head_blocks": len(head_blocks),
        "new": len(blocks) - len(head_blocks), "unique": len({value[0] for value in blocks}),
        "head_prefix_newline_normalized": normalized_prefix == normalized_head,
    }


def validate_release_llms(view: View, root: Path, audit: Audit) -> None:
    rel = LLMS_REL.as_posix()
    validate_llms(view, root, audit, "actual-release")
    head_raw = git_head_bytes(root, rel, audit)
    if head_raw is None:
        return
    try:
        head = head_raw.decode("utf-8")
        document = view.text(rel)
    except (OSError, UnicodeError) as exc:
        audit.error("release_llms_read", rel, repr(exc))
        return
    if LLMS_MARKER not in head or LLMS_MARKER not in document:
        audit.error("release_llms_marker", rel, "grade marker missing")
        return
    head_prefix = normalized_newlines(head[:head.index(LLMS_MARKER)])
    disk_prefix = normalized_newlines(document[:document.index(LLMS_MARKER)])
    if head_prefix != disk_prefix:
        audit.error("release_llms_head_prefix", rel, "HEAD pre-grade content differs")


def validate_release_disk(
    projected: View,
    root: Path,
    rows: Sequence[SourceRow],
    audit: Audit,
) -> View:
    expected_authorized = {
        PARENT_REL.as_posix(), SITEMAP_REL.as_posix(), LLMS_REL.as_posix(), *expected_new_paths(rows),
    }
    changed = int(audit.observations.get("plan", {}).get("changed_paths", -1))
    second = int(audit.observations.get("plan", {}).get("second_pass_changes", -1))
    write_set = int(audit.observations.get("plan", {}).get("write_set", -1))
    if changed != 0 or second != 0 or write_set != 0:
        audit.error("release_zero_change_plan", GENERATOR_REL, f"changed={changed}, second={second}, write_set={write_set}")
    if set(projected.overrides) != expected_authorized:
        audit.error(
            "release_authorized_paths", root,
            f"actual={len(projected.overrides)}, expected={len(expected_authorized)}",
        )
    mismatches: list[str] = []
    for rel, value in projected.overrides.items():
        expected = value if isinstance(value, bytes) else value.encode("utf-8")
        path = root.joinpath(*PurePosixPath(rel).parts)
        if not path.is_file() or path.read_bytes() != expected:
            mismatches.append(rel)
    if mismatches:
        audit.error("release_disk_projection_parity", root, repr(mismatches[:50]))
    new_paths = expected_new_paths(rows)
    all_html = baseline_html_paths(root)
    manifests = {
        "authorized_manifest_sha256": files_manifest(root, expected_authorized),
        "new_html_manifest_sha256": files_manifest(root, new_paths),
        "all_html_manifest_sha256": files_manifest(root, all_html),
    }
    expected_manifests = {
        "authorized_manifest_sha256": RELEASE_AUTHORIZED_MANIFEST_SHA256,
        "new_html_manifest_sha256": RELEASE_NEW_HTML_MANIFEST_SHA256,
        "all_html_manifest_sha256": RELEASE_ALL_HTML_MANIFEST_SHA256,
    }
    if manifests != expected_manifests:
        audit.error("release_target_manifest", root, f"actual={manifests}, expected={expected_manifests}")
    audit.observations["release"] = {
        "state": materialization_state(len(new_paths & all_html)),
        "authorized_documents": len(expected_authorized),
        "authorized_disk_exact": len(expected_authorized) - len(mismatches),
        "disk_mismatches": len(mismatches),
        "new_html": len(new_paths & all_html),
        "all_html": len(all_html),
        **manifests,
    }
    if audit.observations["release"]["state"] != "release":
        audit.error("release_materialization_state", root, repr(audit.observations["release"]))
    return View(root)


def boundary_sample_paths(
    corrected_by_category: Mapping[str, Sequence[Manuscript]],
    rows: Sequence[SourceRow],
) -> tuple[str, ...]:
    row_index = {row.locality: index for index, row in enumerate(rows)}
    selected: set[tuple[str, str]] = set()
    for category in CATEGORIES:
        items = {item.locality: item for item in corrected_by_category.get(category.key, ())}
        selected.update((category.key, row.locality) for row in rows if not row.supports(category))
        selected.update((category.key, row.locality) for row in rows if " " in row.locality)
        selected.update((category.key, row.locality) for row in rows if row.locality in {"호매실", "수원 금곡동"})
        missing = [row for row in rows if not row.middle_schools]
        if missing:
            selected.update((category.key, missing[(index * (len(missing) - 1) + 4) // 9].locality) for index in range(10))
        available = [item for item in items.values()]
        for metric in (
            lambda value: len(value.title),
            lambda value: len(value.meta),
            lambda value: sum(len(part) for part in manuscript_values(value)),
        ):
            if available:
                maximum = max(metric(value) for value in available)
                chosen = min((value for value in available if metric(value) == maximum), key=lambda value: row_index[value.locality])
                selected.add((category.key, chosen.locality))
    selected.update((rule.category, locality) for rule in CORRECTIONS for locality in rule.localities)
    category_index = {category.key: index for index, category in enumerate(CATEGORIES)}
    ordered = sorted(selected, key=lambda value: (category_index[value[0]], row_index.get(value[1], 10**9)))
    return tuple(detail_rel(CATEGORY_BY_KEY[key], locality) for key, locality in ordered)


def validate_boundary_sample(
    view: View | None,
    corrected_by_category: Mapping[str, Sequence[Manuscript]],
    rows: Sequence[SourceRow],
    audit: Audit,
) -> None:
    paths = boundary_sample_paths(corrected_by_category, rows)
    digest = sha256_bytes("".join(f"{value}\n" for value in paths).encode("utf-8"))
    if len(paths) != EXPECTED_BOUNDARY_SAMPLE_COUNT or digest != EXPECTED_BOUNDARY_SAMPLE_SHA256:
        audit.error("boundary_sample_hash", "source", f"count={len(paths)}, actual={digest}, expected={EXPECTED_BOUNDARY_SAMPLE_SHA256}")
    if view is not None:
        missing = [path for path in paths if not view.exists(path)]
        if missing and len(missing) != len(paths):
            audit.error("boundary_sample_partial", "rendered", repr(missing[:10]))
    audit.observations["boundary_sample"] = {"count": len(paths), "sha256": digest, "paths": list(paths)}


def validate_final_document_count(view: View, rows: Sequence[SourceRow], audit: Audit, mode: str) -> None:
    disk = baseline_html_paths(view.root)
    projected = disk | {path for path in view.overrides if path.endswith(".html")}
    expected = EXPECTED_BASE_HTML if mode == "actual" else EXPECTED_FINAL_HTML
    if len(projected) != expected:
        audit.error("final_html_count", view.root, f"actual={len(projected)}, expected={expected}")
    if mode in {"projected", "actual-release"}:
        grade_tree = {value for value in projected if value == PARENT_REL.as_posix() or value.startswith("학년별학원/")}
        if len(grade_tree) != 2_233:
            audit.error("final_grade_tree_count", "학년별학원", f"actual={len(grade_tree)}, expected=2233")
    audit.observations["documents"] = {"html": len(projected), "expected": expected}


def self_test() -> None:
    assert materialization_state(0) == "baseline"
    assert materialization_state(EXPECTED_NEW_HTML) == "release"
    assert materialization_state(1) == "partial"
    baseline_audit = Audit()
    baseline_audit.hold("synthetic_baseline", "selftest", "generation pending")
    assert baseline_audit.status == "HOLD"
    release_audit = Audit()
    assert release_audit.status == "PASS"
    assert sum(len(rule.localities) for rule in CORRECTIONS) == EXPECTED_CORRECTION_RULES
    assert len({(rule.category, locality) for rule in CORRECTIONS for locality in rule.localities}) == EXPECTED_CORRECTION_PAGES
    assert sum(rule.occurrences for rule in CORRECTIONS) == EXPECTED_CORRECTION_OCCURRENCES
    assert encoded_url("학년별학원", "중1수학학원", "부천 중동") == (
        BASE_URL + "/%ED%95%99%EB%85%84%EB%B3%84%ED%95%99%EC%9B%90/"
        "%EC%A4%911%EC%88%98%ED%95%99%ED%95%99%EC%9B%90/"
        "%EB%B6%80%EC%B2%9C%20%EC%A4%91%EB%8F%99/"
    )
    assert split_schools("오현초호매실중, 능실중", "호매실") == ("호매실중", "능실중")
    assert split_schools("오현초호매실중, 능실중", "다른동") == ("오현초호매실중", "능실중")
    rule = next(value for value in CORRECTIONS if value.old == "관리을")
    assert dict(rule.per_locality_counts)["관평동"] == 2
    assert dict(rule.per_locality_counts)["관저동"] == 1
    assert apply_corrections("관리을 관리을", "middle1_english", "관평동") == "관리를 관리를"
    assert apply_corrections("관리을", "middle1_english", "관저동") == "관리를"
    assert apply_corrections("관리을", "middle1_english", "비허용동") == "관리을"
    assert correction_pattern(Correction("x", "거제중", "x", ("x",), 1, True)).search("거제중과")
    assert not correction_pattern(Correction("x", "거제중", "x", ("x",), 1, True)).search("거제중앙중과")
    audit = Audit()
    dom = parse_dom('<main data-x="raw &amp; exact"><p>앞 <strong>중간</strong> 뒤</p></main>', audit, "selftest")
    assert dom is not None and not audit.errors
    assert nodes_with_attr(dom, "data-x")[0].attrs["data-x"] == "raw & exact"
    assert find_elements(dom, "p")[0].text() == "앞 중간 뒤"
    schema_dom = parse_dom(
        '<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"FAQPage","mainEntity":[]}]}</script>',
        audit, "selftest-schema",
    )
    assert schema_dom is not None and len(graph_nodes(json_graph(schema_dom, audit, "selftest-schema"), "FAQPage")) == 1
    sitemap_base = "<urlset>\r\n<url>\r\n<loc>https://wawa-center.kr/</loc>\r\n<lastmod>2026-01-01</lastmod>\r\n</url>\r\n"
    sitemap_candidate = sitemap_base + "<url>\r\n<loc>https://wawa-center.kr/%ED%95%99%EB%85%84/</loc>\r\n<lastmod>2026-08-20</lastmod>\r\n</url>\r\n</urlset>"
    assert parse_sitemap(sitemap_candidate, audit, "selftest-sitemap")[:1] == parse_sitemap(sitemap_base, audit, "selftest-sitemap-base")
    assert sitemap_base != sitemap_base.replace("\r\n", "\n")
    assert normalized_newlines(sitemap_base) == normalized_newlines(sitemap_base.replace("\r\n", "\n"))
    readable_parent = BASE_URL + "/학년별학원/"
    readable_child = BASE_URL + "/학년별학원/중1수학학원/"
    tokens = Counter(re.findall(r"https://wawa-center\.kr/[^\s]+", f"- parent: {readable_parent}\n- child: {readable_child}\n"))
    assert tokens[readable_parent] == 1 and tokens[readable_child] == 1
    assert encoded_url("학년별학원") not in f"- parent: {readable_parent}\n- child: {readable_child}\n"
    assert EXPECTED_GENERATOR_SHA256 != "PENDING" and EXPECTED_CANDIDATE_SHA256 != "PENDING"
    assert not audit.errors


def run(
    root: Path,
    zip_dir: Path,
    common: Path,
    mode: str,
    *,
    max_findings: int = 250,
) -> Audit:
    audit = Audit(max_findings=max_findings)
    root = root.resolve()
    zip_dir = zip_dir.resolve()
    common = common.resolve()
    parsed, corrected = load_archives(zip_dir, audit)
    rows = load_common(common, audit)
    validate_source_contract(parsed, corrected, rows, audit)
    assets = load_generic_assets(root, rows, audit) if rows else {}
    validate_boundary_sample(None, corrected, rows, audit)
    if mode == "source":
        return audit

    validate_baseline(root, audit)
    validate_residue(root, audit)
    if mode == "actual":
        view = View(root)
    elif mode == "projected":
        projected = build_projected_view(root, zip_dir, common, rows, audit)
        if projected is None:
            return audit
        view = projected
    else:
        projected = build_projected_view(root, zip_dir, common, rows, audit)
        if projected is None:
            return audit
        view = validate_release_disk(projected, root, rows, audit)
    rendered_mode = "actual" if mode == "actual" else "projected"
    validate_final_document_count(view, rows, audit, mode)
    validate_hubs(view, rows, audit, rendered_mode)
    validate_details(view, corrected, parsed, rows, assets, audit, rendered_mode)
    if mode == "actual-release":
        validate_release_sitemap(view, root, rows, audit)
        validate_release_llms(view, root, audit)
    else:
        validate_sitemap(view, root, rows, audit, mode)
        validate_llms(view, root, audit, mode)
    if mode in {"projected", "actual-release"}:
        validate_boundary_sample(view, corrected, rows, audit)
    return audit


def audit_payload(audit: Audit, max_findings: int) -> dict[str, Any]:
    return {
        "status": audit.status,
        "errors": len(audit.errors),
        "holds": len(audit.holds),
        "error_findings": audit.errors[:max_findings],
        "hold_findings": audit.holds[:max_findings],
        "observations": audit.observations,
    }


def default_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    return root, Path.home() / "Desktop" / "새 폴더 (2)", root.parent / "참고자료" / "공통자료"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    root, zip_dir, common = default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("source", "actual", "projected", "actual-release"), default="actual")
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--zip-dir", type=Path, default=zip_dir)
    parser.add_argument("--common", type=Path, default=common)
    parser.add_argument("--max-findings", type=int, default=250)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
    audit = run(args.root, args.zip_dir, args.common, args.mode, max_findings=args.max_findings)
    payload = audit_payload(audit, args.max_findings)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"content audit: {payload['status']} (errors={payload['errors']}, holds={payload['holds']})")
        for finding in payload["error_findings"]:
            print(f"ERROR {finding['code']} [{finding['location']}]: {finding['message']}")
        for finding in payload["hold_findings"]:
            print(f"HOLD {finding['code']} [{finding['location']}]: {finding['message']}")
        print(json.dumps(payload["observations"], ensure_ascii=False, sort_keys=True))
    return {"PASS": 0, "FAIL": 1, "HOLD": 2}[audit.status]


if __name__ == "__main__":
    raise SystemExit(main())
