#!/usr/bin/env python3
"""Build the grade-6 mathematics/English and grade-2 English directories.

The three attached XLSX workbooks are immutable content data.  Formulae,
macros, hyperlinks, embedded instructions, and external relationships are
never executed.  A normal invocation constructs and audits the complete
1,119-document sparse plan in memory and writes nothing.  Applying requires
an exact external freeze payload plus the literal ``APPLY-GO`` token and uses
the pinned recoverable transaction journal.
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
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Mapping, Sequence
from urllib.parse import quote
from zipfile import ZipFile


sys.dont_write_bytecode = True

SITE_ORIGIN = "https://wawa-center.kr"
PUBLISHED_DATE = "2026-08-21"
MIDDLE_HELPER_SHA256 = "8953f73fde05e6b6ffef4be605c8e25cc34e888b7edbb9021cda622d4ed9d773"
BASE_HELPER_SHA256 = "1fbba380481affe0b4f9888630f90caccb8bfca39342284819f8a2fb265d31cf"
HIGH2_MATH_HELPER_SHA256 = "2101024613021e74b598034fd43b24a62ee74d994177f8b7e109b2ae98de43e5"
CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
TARGET_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"

EXPECTED_LOCALITIES = 371
EXPECTED_NEW_CATEGORIES = 3
EXPECTED_NEW_HTML = 1_116
EXPECTED_AUTHORIZED_DOCUMENTS = 1_119
EXPECTED_EXISTING_HTML = 17_229
EXPECTED_IMMUTABLE_HTML = 17_228
EXPECTED_FINAL_HTML = 18_345
EXPECTED_HIGH2_MATH_HTML = 372
EXPECTED_ASSET_FILES = 1_878
EXPECTED_EXISTING_GENERATORS = 3
EXPECTED_PARENT_CATEGORIES = 10
EXPECTED_SPECIAL_HEADING_PAGES = 15
EXPECTED_SPECIAL_HEADINGS = 95

BASE_PARENT_SHA256 = "6543d753904d7ee4c9956a702073da3d62d15f3ad07522fc1b87de00c16bf58e"
BASE_SITEMAP_SHA256 = "c760bcaedaa2565c34c0312fb3022eb2e3e533d3e0b8444f4e02cb4924ad5c24"
BASE_LLMS_SHA256 = "1937e0726a3fdb651ba97cb89beab06a8d0da18de26dcea6db3cef25035c33ec"
BASE_IMMUTABLE_HTML_MANIFEST_SHA256 = "b5eeb32768bc8403acf484d90cfd3dad52de7aa5df3a60e355e6abceca3fb0da"
BASE_HIGH2_MATH_MANIFEST_SHA256 = "d074db4c9e7defa99fc2ee6232c2279c9b6f767e253ceca0797f988878656429"
BASE_ASSET_MANIFEST_SHA256 = "8115d36ee4c535856bc63cd2277eadc108de430e0ca0d0928d93000e1670b182"
BASE_GENERATOR_MANIFEST_SHA256 = "70d17d8d30f973cc24ac5521590905c97930581bfe1b55f999f96c53d8f6d15b"
HIGH2_HUB_STYLE_SHA256 = "9ce3034405dd35179c7212b862c6523c8163cae3000da114af9c55a030e09af5"

PARENT_REL = Path("학년별학원/index.html")
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
HIGH2_MATH_ROOT = Path("학년별학원/고2수학학원")
HIGH2_MATH_HUB_REL = HIGH2_MATH_ROOT / "index.html"
LLMS_MARKER = "## 학년별학원 핵심 허브"
ABSENT_SHA256 = hashlib.sha256(b"wawa-grade3-math:absent-v1").hexdigest()

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
LABELS = ("페이지타이틀", "메타설명", "본문", "FAQ", "학부모후기", "JSON-LD 요약")
LABEL_RE = re.compile(r"(?m)^\[([^\]\n]+)\][ \t]*\n")
MARKDOWN_H2_RE = re.compile(r"(?m)^##[ \t]+([^\n]+?)[ \t]*$")
QUESTION_RE = re.compile(r"(?m)^(Q(?:[1-9][0-9]*)?\.)[ \t]+(.+?)[ \t]*$")
ANSWER_RE = re.compile(r"^(A(?:[1-9][0-9]*)?\.)[ \t]+(.+)$", re.DOTALL)
RAW_URL_RE = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD_RE = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)
STYLE_RE = re.compile(r"<style>.*?</style>", re.DOTALL)

XLSX_PARTS = frozenset({
    "[Content_Types].xml", "_rels/.rels", "docProps/app.xml", "docProps/core.xml",
    "xl/_rels/workbook.xml.rels", "xl/sharedStrings.xml", "xl/styles.xml",
    "xl/theme/theme1.xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml",
})
XML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_middle_helper() -> ModuleType:
    path = Path(__file__).with_name("generate_middle_grade_pages.py")
    digest = _sha256(path.read_bytes())
    if digest != MIDDLE_HELPER_SHA256:
        raise RuntimeError(f"middle helper SHA-256 mismatch: {digest}")
    name = f"_wawa_middle_batch3_{MIDDLE_HELPER_SHA256[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned middle-grade helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if module.BASE_HELPER_SHA256 != BASE_HELPER_SHA256:
        raise RuntimeError("nested base-helper contract mismatch")
    high2_path = path.with_name("generate_high2_math_pages.py")
    if _sha256(high2_path.read_bytes()) != HIGH2_MATH_HELPER_SHA256:
        raise RuntimeError("high2 mathematics helper SHA-256 mismatch")
    return module


_MID = _load_middle_helper()
_BASE = _MID._BASE
BuildError = _MID.BuildError
ABSENT_SHA256 = _BASE.ABSENT_SHA256


@dataclass(frozen=True)
class GradeSpec:
    key: str
    tier: str
    grade: str
    grade_number: int
    subject: str
    slug: str
    hook: str
    grade_attr: str
    school_attr: str
    school_hook: str
    school_label: str
    workbook_sha256: str
    workbook_bytes: int
    cell_manifest_sha256: str
    sequence_sha256: str
    mapping_sha256: str
    h2_total: int
    h2_distribution: tuple[tuple[int, int], ...]
    intro_distribution: tuple[tuple[int, int], ...]
    paragraph_total: int
    section_paragraphs: int
    faq_total: int
    faq_distribution: tuple[tuple[int, int], ...]
    review_total: int
    review_distribution: tuple[tuple[int, int], ...]
    summary_paragraphs: int
    summary_distribution: tuple[tuple[int, int], ...]
    title_exact: int
    title_extended: int
    supported: int
    unconfirmed: int
    school_chips: int
    missing_school_rows: int
    card_copy: str

    @property
    def label(self) -> str:
        return f"{self.grade} {self.subject}학원"

    @property
    def grades_label(self) -> str:
        return f"{self.subject} 가능 학년"

    @property
    def subject_slug(self) -> str:
        return f"{self.subject}학원"

    @property
    def guide_slug(self) -> str:
        return f"{self.subject}-공부법"

    @property
    def english_label(self) -> str:
        tier = "ELEMENTARY SCHOOL" if self.tier == "elementary" else "HIGH SCHOOL"
        subject = "MATH" if self.subject == "수학" else "ENGLISH"
        return f"{tier} GRADE {self.grade_number} {subject}"

    @property
    def audience_type(self) -> str:
        tier = "초등학교" if self.tier == "elementary" else "고등학교"
        return f"{tier} {self.grade_number}학년({self.grade})"


ELEMENTARY6_MATH = GradeSpec(
    "elementary6_math", "elementary", "초6", 6, "수학", "초6수학학원", "elementary6-math",
    "math_grades", "elementary_schools", "elementary-schools", "초등학교",
    "7820827f61a9b91c80d9cc3b0a68b018b2e8eed1154d1eebe659f3df4e8fe6a3", 1_228_435,
    "48966ddc64d3e838e068546cbca21d9d20dc9f420079eafaead2d443bbce572d",
    "5792c0066078574c68eff514efb073402d8eaf477ece9eed81bdf4173dc06eb1",
    "ed72bcf9d04072cc4be04efc4e1cd5d2c7f466751bad4d51fb0313a2a7e36380",
    2_433, ((6, 164), (7, 207)), ((0, 23), (1, 293), (2, 55)),
    6_927, 6_524, 2_010, ((5, 217), (6, 153), (7, 1)),
    902, ((1, 41), (2, 144), (3, 171), (4, 15)), 372, ((1, 370), (2, 1)),
    247, 124, 358, 13, 638, 74,
    "초6 수학의 핵심 개념, 문장제·응용, 오답 복습과 중학교 전환 준비 기준을 동네별로 확인합니다.",
)
ELEMENTARY6_ENGLISH = GradeSpec(
    "elementary6_english", "elementary", "초6", 6, "영어", "초6영어학원", "elementary6-english",
    "english_grades", "elementary_schools", "elementary-schools", "초등학교",
    "f507fab48c0e18303574eb78cdc5133c0ab2b1c72351fb40e31db5bc8f147148", 1_255_108,
    "b13f9532e3d25f4f1c3d150499b5b72649fdc0b06295e69ae113d30531a776df",
    "7fb97a23bd7dae670cbf4d8229b48c992b486795d7153a8743357a7f5ec24044",
    "ed72bcf9d04072cc4be04efc4e1cd5d2c7f466751bad4d51fb0313a2a7e36380",
    2_410, ((6, 189), (7, 181), (9, 1)), ((0, 18), (1, 312), (2, 41)),
    7_090, 6_696, 1_991, ((5, 235), (6, 136)),
    927, ((1, 38), (2, 131), (3, 181), (4, 21)), 372, ((1, 370), (2, 1)),
    254, 117, 363, 8, 638, 74,
    "초6 영어의 어휘·문장 구조·독해·쓰기와 중학교 전환 학습 기준을 동네별로 확인합니다.",
)
HIGH2_ENGLISH = GradeSpec(
    "high2_english", "high", "고2", 2, "영어", "고2영어학원", "high2-english",
    "english_grades", "high_schools", "high-schools", "고등학교",
    "828bea4e58bc9d8192d0e1b0ce8d8be1c8749bdcdf5eb418aabf0ddcb622df26", 1_248_002,
    "6897b65600df26b49d7648422c7b9ca5eb233fd85b9612c8df47f71d8b38c7dd",
    "732aa8030179f159b74862eade4a0717faca4c5105814e93e6a6dd4c0451a5c1",
    "ed72bcf9d04072cc4be04efc4e1cd5d2c7f466751bad4d51fb0313a2a7e36380",
    2_394, ((6, 203), (7, 168)), ((0, 14), (1, 324), (2, 33)),
    6_899, 6_509, 1_946, ((5, 281), (6, 89), (7, 1)),
    894, ((1, 53), (2, 126), (3, 179), (4, 13)), 372, ((1, 370), (2, 1)),
    285, 86, 332, 39, 909, 63,
    "고2 영어의 학교별 내신, 모의고사 독해·어법·서술형과 오답 관리 기준을 동네별로 확인합니다.",
)
NEW_SPECS = (ELEMENTARY6_MATH, ELEMENTARY6_ENGLISH, HIGH2_ENGLISH)
SPEC_BY_KEY = MappingProxyType({spec.key: spec for spec in NEW_SPECS})


@dataclass(frozen=True)
class ParentSpec:
    key: str
    grade: str
    subject: str
    slug: str
    english_label: str
    card_copy: str

    @property
    def label(self) -> str:
        return f"{self.grade} {self.subject}학원"


HIGH2_MATH_PARENT = ParentSpec(
    "high2_math", "고2", "수학", "고2수학학원", "HIGH SCHOOL GRADE 2 MATH",
    "고2 수학의 학교별 내신 범위, 수능 기초, 취약 단원과 오답 관리 기준을 동네별 원고에서 확인합니다.",
)
PARENT_ORDER: tuple[Any, ...] = (
    ELEMENTARY6_MATH, ELEMENTARY6_ENGLISH,
    *_MID.ALL_CATEGORIES,
    HIGH2_MATH_PARENT, HIGH2_ENGLISH,
)


@dataclass(frozen=True)
class HeadingToken:
    start: int
    end: int
    text: str
    kind: str


@dataclass(frozen=True)
class BodySection:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class FAQ:
    number: int
    question: str
    answer: str
    question_prefix: str
    answer_prefix: str


@dataclass(frozen=True)
class Manuscript:
    member_name: str
    workbook_row: int
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
    cell_sha256: str
    heading_kind: str


@dataclass(frozen=True)
class BuildPlan:
    root: Path
    authorized_documents: Mapping[Path, str | bytes]
    changed_paths: tuple[Path, ...]
    second_pass_changes: tuple[Path, ...]
    source_manifest: Mapping[str, str]
    source_paths: Mapping[str, Path]
    before_manifest: Mapping[Path, str]
    after_manifest: Mapping[Path, str]
    before_exists: Mapping[Path, bool]
    source_metrics: Mapping[str, Any]
    before_metrics: Mapping[str, Any]
    after_metrics: Mapping[str, Any]
    metrics: Mapping[str, Any]
    candidate_sha256: str
    immutable_html_manifest_sha256: str
    high2_math_manifest_sha256: str
    asset_manifest_sha256: str
    generator_manifest_sha256: str


# Only these source rows may reinterpret a non-``##`` line as a heading.  The
# heading sequence digest freezes every stripped structural marker and every
# retained heading character.  No spelling or prose correction is allowed.
SPECIAL_HEADING_ALLOWLIST = MappingProxyType({
    ("high2_english", 30): ("literal-h2", 7, "d3769b2cb13791a04082250dd15c10dfb78b8ffa6114ecd9291ecf55060de9a3"),
    ("high2_english", 135): ("markdown-h3", 6, "82d3fd384e2496cb518c033a9a9a7bef160d209cdf59af7fb4381417a6caa424"),
    ("high2_english", 286): ("literal-h2", 6, "811e01df65a6b491ab65f39dbc010597fe24c29a0bc28b762d784ae3745b0f3b"),
    ("high2_english", 309): ("literal-h2", 6, "06085b75d09034cc1b01d1395ea8f75e91cf5f2659411bf78b0ea6a43e8d574c"),
    ("high2_english", 344): ("literal-h2", 7, "ae51a20c303104d2eacb2fdfaa125ca110007ec8d495a54f087340ad09be7b0b"),
    ("elementary6_math", 95): ("plain-block", 6, "b03edbc205eabd70935def82303d02a493134fa86d35b45c61e8d54dac9f1588"),
    ("elementary6_math", 130): ("literal-h2", 6, "93d948d37260bc2e2195f10e3abeee0a3f383241a1c352db5cb1cf22bc3dd2d6"),
    ("elementary6_math", 219): ("literal-h2", 7, "652192a13c76e55a4bbffb1b39826faeef9b784f0e5e1ea6a900411f17600fed"),
    ("elementary6_english", 6): ("numbered-plain", 6, "79b1d2d8169b33bc22de9142e2bae3177e1f95f22254843f07762d56271060ab"),
    ("elementary6_english", 18): ("literal-h2", 6, "263ba90ed9d19fbb011dcc6e71fb812da65e37ec333aec4fb1e7d36d40ea2508"),
    ("elementary6_english", 26): ("markdown-h3", 7, "a87662407c7d7f0f1a07a1c19ea225030098e2c16c39a5dd9c32280169009436"),
    ("elementary6_english", 32): ("plain-block", 6, "04a0845c4cb0c2ac14fb532b29e973d2da74bccd25d07abd0d5662207488f178"),
    ("elementary6_english", 53): ("markdown-h3", 6, "2667d530c2743986428d86f9ee05b6d4e5a0853bd38ca283bc711d09705f503b"),
    ("elementary6_english", 123): ("markdown-h3", 6, "b54d7d904d32edaf2af564ed13b7182cab2ea553045881db09c735da73543528"),
    ("elementary6_english", 222): ("literal-h2", 7, "0de47bafca3feae27bb096ce6745246b77c0a375d31387fd18f89d0fdc5e28d4"),
})

PLAIN_HEADINGS = MappingProxyType({
    ("elementary6_math", 95): (
        "초6 수학에서 확인해야 할 핵심 영역", "학생 유형에 맞춘 수업 방향", "숙제관리로 학습 리듬 만들기",
        "학교별 진도와 중학교 준비", "수업에서 오답을 활용하는 방법", "호평동에서 상담할 때 확인할 내용",
    ),
    ("elementary6_english", 32): (
        "목동 초6 학생에게 필요한 영어 학습 점검", "신목초·서정초 학생의 중등 영어 준비",
        "어휘·문법·독해를 연결하는 학습 방식", "학생 유형별로 달라야 하는 지도",
        "목동 초6 영어학원 상담 시 확인할 내용", "중학교 영어를 위한 6학년 학습 계획",
    ),
})


def _as_bytes(value: str | bytes) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")


def _decode_utf8(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label}: not strict UTF-8") from exc


def _escape(value: Any) -> str:
    return _BASE._escape(str(value))


def _site_url(*parts: str) -> str:
    return _BASE._encoded_site_url(*parts)


def _category_rel(spec: GradeSpec) -> Path:
    return Path("학년별학원") / spec.slug / "index.html"


def _detail_rel(spec: GradeSpec, locality: str) -> Path:
    return Path("학년별학원") / spec.slug / locality / "index.html"


def _generic_rel(spec: GradeSpec, locality: str) -> Path:
    return Path("과목별학원") / spec.subject_slug / locality / "index.html"


def _split_paragraphs(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(block.strip() for block in re.split(r"\n[ \t]*\n", value) if block.strip())


def _replace_once(value: str, old: str, new: str, label: str) -> str:
    if value.count(old) != 1:
        raise BuildError(f"{label}: expected one replacement target, got {value.count(old)}")
    return value.replace(old, new, 1)


def _xlsx_cells(spec: GradeSpec, path: Path) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise BuildError(f"{spec.key}: workbook must be a regular non-symlink file: {path}")
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != spec.workbook_sha256 or len(raw) != spec.workbook_bytes:
        raise BuildError(f"{spec.key}: workbook bytes/hash mismatch: {len(raw)}/{digest}")
    with ZipFile(io.BytesIO(raw), "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != XLSX_PARTS:
            raise BuildError(f"{spec.key}: workbook package part set differs from frozen data-only contract")
        for info in infos:
            parts = Path(info.filename).parts
            if (
                info.is_dir() or info.flag_bits & 0x1 or info.filename.startswith(("/", "\\"))
                or ".." in parts or CONTROL_RE.search(info.filename)
                or info.file_size < 0 or info.file_size > 8_000_000
                or (info.compress_size and info.file_size / info.compress_size > 150)
            ):
                raise BuildError(f"{spec.key}: unsafe/encrypted/suspicious workbook part: {info.filename!r}")
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        if "macroEnabled" in content_types or "vbaProject" in content_types or "externalLink" in content_types:
            raise BuildError(f"{spec.key}: executable/external-link content type is forbidden")

    sheets = workbook_root.findall(f".//{{{XML_NS}}}sheet")
    if len(sheets) != 1 or sheets[0].get("name") != "Sheet1" or sheets[0].get("state", "visible") != "visible":
        raise BuildError(f"{spec.key}: workbook must contain exactly one visible Sheet1")
    if workbook_root.findall(f".//{{{XML_NS}}}definedName"):
        raise BuildError(f"{spec.key}: defined names are outside the frozen data contract")
    relationship_id = sheets[0].get(f"{{{REL_NS}}}id")
    relationships = {
        node.get("Id"): (node.get("Type", ""), node.get("Target", ""), node.get("TargetMode", ""))
        for node in rels_root
    }
    if relationship_id not in relationships or relationships[relationship_id][1] != "worksheets/sheet1.xml":
        raise BuildError(f"{spec.key}: Sheet1 relationship target mismatch")
    if any(mode == "External" for _, _, mode in relationships.values()):
        raise BuildError(f"{spec.key}: external workbook relationship is forbidden")

    shared_nodes = shared_root.findall(f"{{{XML_NS}}}si")
    if shared_root.get("count") != "371" or shared_root.get("uniqueCount") != "371" or len(shared_nodes) != EXPECTED_LOCALITIES:
        raise BuildError(f"{spec.key}: shared-string count mismatch")
    shared: list[str] = []
    for index, node in enumerate(shared_nodes, 1):
        if node.find(f".//{{{XML_NS}}}f") is not None:
            raise BuildError(f"{spec.key}: shared string {index} contains a formula node")
        value = "".join(part.text or "" for part in node.findall(f".//{{{XML_NS}}}t"))
        if not value or CONTROL_RE.search(value) or unicodedata.normalize("NFC", value) != value:
            raise BuildError(f"{spec.key}: shared string {index} is empty/control/non-NFC")
        shared.append(value)

    if sheet_root.findall(f".//{{{XML_NS}}}f"):
        raise BuildError(f"{spec.key}: worksheet formula is forbidden")
    if sheet_root.findall(f".//{{{XML_NS}}}hyperlink") or sheet_root.findall(f".//{{{XML_NS}}}mergeCell"):
        raise BuildError(f"{spec.key}: hyperlink/merge is outside the frozen data contract")
    dimension = sheet_root.find(f"{{{XML_NS}}}dimension")
    if dimension is None or dimension.get("ref") != "A1:A371":
        raise BuildError(f"{spec.key}: worksheet dimension must be A1:A371")
    rows = sheet_root.findall(f".//{{{XML_NS}}}sheetData/{{{XML_NS}}}row")
    if len(rows) != EXPECTED_LOCALITIES:
        raise BuildError(f"{spec.key}: worksheet row count mismatch")
    cells: list[str] = []
    mapping = hashlib.sha256()
    for row_number, row in enumerate(rows, 1):
        nodes = row.findall(f"{{{XML_NS}}}c")
        if row.get("r") != str(row_number) or len(nodes) != 1:
            raise BuildError(f"{spec.key}/Sheet1 row {row_number}: exact one-cell contract failed")
        cell = nodes[0]
        ref = f"A{row_number}"
        value_node = cell.find(f"{{{XML_NS}}}v")
        if cell.get("r") != ref or cell.get("t") != "s" or value_node is None or value_node.text is None:
            raise BuildError(f"{spec.key}/Sheet1!{ref}: shared-string cell contract failed")
        try:
            shared_index = int(value_node.text)
        except ValueError as exc:
            raise BuildError(f"{spec.key}/Sheet1!{ref}: invalid shared-string index") from exc
        if not 0 <= shared_index < len(shared):
            raise BuildError(f"{spec.key}/Sheet1!{ref}: shared-string index out of range")
        cells.append(shared[shared_index])
        mapping.update(f"{ref}\t{shared_index}\n".encode("ascii"))
    if len(set(cells)) != EXPECTED_LOCALITIES:
        raise BuildError(f"{spec.key}: manuscript cells must be exactly unique")
    cell_manifest = hashlib.sha256()
    for index, value in enumerate(cells, 1):
        cell_manifest.update(f"{index}\t{_sha256(value.encode('utf-8'))}\n".encode("ascii"))
    sequence = _sha256(b"\0".join(value.encode("utf-8") for value in cells))
    if (
        cell_manifest.hexdigest() != spec.cell_manifest_sha256
        or sequence != spec.sequence_sha256
        or mapping.hexdigest() != spec.mapping_sha256
    ):
        raise BuildError(f"{spec.key}: workbook cell sequence/manifest/mapping mismatch")
    return tuple(cells), MappingProxyType({
        "xlsx_bytes": len(raw), "sheets": 1, "cells": len(cells), "unique_cells": len(set(cells)),
        "formula_cells": 0, "hyperlinks": 0, "merged_ranges": 0,
        "cell_manifest_sha256": cell_manifest.hexdigest(), "sequence_sha256": sequence,
        "mapping_sha256": mapping.hexdigest(),
    })


def _heading_sequence_sha(tokens: Sequence[HeadingToken]) -> str:
    return _sha256(b"\0".join(token.text.encode("utf-8") for token in tokens))


def _special_heading_tokens(spec: GradeSpec, row: int, body: str, kind: str) -> tuple[HeadingToken, ...]:
    if kind == "literal-h2":
        pattern = re.compile(r"(?m)^<h2>([^<\n]+)</h2>[ \t]*$")
        tokens = tuple(HeadingToken(match.start(), match.end(), match.group(1), kind) for match in pattern.finditer(body))
    elif kind == "markdown-h3":
        pattern = re.compile(r"(?m)^###[ \t]+([^\n]+?)[ \t]*$")
        tokens = tuple(HeadingToken(match.start(), match.end(), match.group(1).strip(), kind) for match in pattern.finditer(body))
    elif kind == "numbered-plain":
        pattern = re.compile(r"(?m)^([1-6]\.[ \t]+[^\n]+?)[ \t]*$")
        tokens = tuple(HeadingToken(match.start(), match.end(), match.group(1).strip(), kind) for match in pattern.finditer(body))
    elif kind == "plain-block":
        headings = PLAIN_HEADINGS.get((spec.key, row))
        if headings is None:
            raise BuildError(f"{spec.key}/Sheet1!A{row}: plain heading tuple missing")
        pattern = re.compile(r"(?m)^(" + "|".join(re.escape(value) for value in headings) + r")[ \t]*$")
        tokens = tuple(HeadingToken(match.start(), match.end(), match.group(1), kind) for match in pattern.finditer(body))
        if tuple(token.text for token in tokens) != headings:
            raise BuildError(f"{spec.key}/Sheet1!A{row}: exact plain heading order mismatch")
    else:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: unsupported structural heading kind: {kind}")
    return tokens


def _heading_tokens(spec: GradeSpec, row: int, body: str) -> tuple[HeadingToken, ...]:
    special = SPECIAL_HEADING_ALLOWLIST.get((spec.key, row))
    if special is None:
        matches = tuple(
            HeadingToken(item.start(), item.end(), item.group(1).strip(), "markdown-h2")
            for item in MARKDOWN_H2_RE.finditer(body)
        )
        if not matches:
            raise BuildError(f"{spec.key}/Sheet1!A{row}: source markdown H2 headings are required")
        if re.findall(r"(?m)^<h[1-6]>.*?</h[1-6]>[ \t]*$", body):
            raise BuildError(f"{spec.key}/Sheet1!A{row}: literal heading tag outside strict allowlist")
        return matches
    kind, expected_count, expected_sha = special
    tokens = _special_heading_tokens(spec, row, body, kind)
    if len(tokens) != expected_count or _heading_sequence_sha(tokens) != expected_sha:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: special heading count/sequence mismatch")
    markdown_count = len(re.findall(r"(?m)^#{1,6}[ \t]+", body))
    literal_count = len(re.findall(r"(?m)^<h[1-6]>.*?</h[1-6]>[ \t]*$", body))
    if kind == "markdown-h3" and markdown_count != expected_count:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: mixed markdown heading styles forbidden")
    if kind == "literal-h2" and literal_count != expected_count:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: mixed literal heading styles forbidden")
    if kind in {"numbered-plain", "plain-block"} and (markdown_count or literal_count):
        raise BuildError(f"{spec.key}/Sheet1!A{row}: marked headings mixed into plain allowlist")
    return tokens


def _parse_manuscript(spec: GradeSpec, row: int, source: str) -> Manuscript:
    if unicodedata.normalize("NFC", source) != source or CONTROL_RE.search(source):
        raise BuildError(f"{spec.key}/Sheet1!A{row}: non-NFC/control manuscript")
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(LABEL_RE.finditer(text))
    if tuple(match.group(1) for match in matches) != LABELS:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: section labels/order malformed")
    if text[:matches[0].start()].strip():
        raise BuildError(f"{spec.key}/Sheet1!A{row}: content before first marker")
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        values[match.group(1)] = text[match.end():end].strip("\n")
    if any(not values[label].strip() for label in LABELS):
        raise BuildError(f"{spec.key}/Sheet1!A{row}: empty required section")
    title = values["페이지타이틀"].strip()
    title_separator = f" {spec.label}"
    if title.count(title_separator) != 1 or title.startswith(title_separator):
        raise BuildError(f"{spec.key}/Sheet1!A{row}: title must begin with locality and {spec.label}")
    locality = title.split(title_separator, 1)[0].strip()
    if not locality:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: empty title locality")
    meta = values["메타설명"].strip()
    if not meta or "\n" in meta:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: meta description must remain one line")
    body = values["본문"].strip()
    headings = _heading_tokens(spec, row, body)
    intro = _split_paragraphs(body[:headings[0].start])
    sections: list[BodySection] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start if index + 1 < len(headings) else len(body)
        paragraphs = _split_paragraphs(body[heading.end:end])
        if not heading.text or not paragraphs:
            raise BuildError(f"{spec.key}/Sheet1!A{row}: empty source heading/body")
        sections.append(BodySection(heading.text, paragraphs))
    normalized = [re.sub(r"\s+", " ", value).strip().casefold() for value in intro]
    normalized.extend(
        re.sub(r"\s+", " ", paragraph).strip().casefold()
        for section in sections for paragraph in section.paragraphs
    )
    if len(normalized) != len(set(normalized)):
        raise BuildError(f"{spec.key}/Sheet1!A{row}: normalized body paragraph duplicate")

    faq_value = values["FAQ"].strip()
    question_matches = list(QUESTION_RE.finditer(faq_value))
    if len(question_matches) not in (5, 6, 7):
        raise BuildError(f"{spec.key}/Sheet1!A{row}: expected five to seven FAQ questions")
    faqs: list[FAQ] = []
    for index, question in enumerate(question_matches, 1):
        end = question_matches[index].start() if index < len(question_matches) else len(faq_value)
        answer_block = faq_value[question.end():end].strip()
        answer_match = ANSWER_RE.fullmatch(answer_block)
        if answer_match is None or not answer_match.group(2).strip():
            raise BuildError(f"{spec.key}/Sheet1!A{row}: malformed/empty FAQ answer {index}")
        faqs.append(FAQ(
            index, question.group(2).strip(), answer_match.group(2).strip(),
            question.group(1), answer_match.group(1),
        ))
    review_blocks = _split_paragraphs(values["학부모후기"].strip())
    if not 1 <= len(review_blocks) <= 4:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: review block count outside frozen range")
    summary = values["JSON-LD 요약"].strip()
    if not summary:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: empty JSON-LD summary")
    kinds = {heading.kind for heading in headings}
    if len(kinds) != 1:
        raise BuildError(f"{spec.key}/Sheet1!A{row}: mixed heading transform kinds")
    return Manuscript(
        member_name=f"Sheet1!A{row}", workbook_row=row, locality=locality,
        title=title, meta_description=meta, intro_paragraphs=intro, sections=tuple(sections),
        faqs=tuple(faqs), review_lines=review_blocks, jsonld_summary=summary,
        raw_bytes=source.encode("utf-8"), raw_text=source,
        cell_sha256=_sha256(source.encode("utf-8")), heading_kind=next(iter(kinds)),
    )


def _load_manuscripts(spec: GradeSpec, workbook_path: Path) -> tuple[Mapping[str, Manuscript], Mapping[str, Any]]:
    cells, workbook_metrics = _xlsx_cells(spec, workbook_path)
    manuscripts: dict[str, Manuscript] = {}
    for row, source in enumerate(cells, 1):
        manuscript = _parse_manuscript(spec, row, source)
        if manuscript.locality in manuscripts:
            raise BuildError(f"{spec.key}: duplicate workbook locality: {manuscript.locality}")
        manuscripts[manuscript.locality] = manuscript
    h2_distribution = Counter(len(value.sections) for value in manuscripts.values())
    intro_distribution = Counter(len(value.intro_paragraphs) for value in manuscripts.values())
    paragraph_total = sum(
        len(value.intro_paragraphs) + sum(len(section.paragraphs) for section in value.sections)
        for value in manuscripts.values()
    )
    section_paragraphs = sum(len(section.paragraphs) for value in manuscripts.values() for section in value.sections)
    faq_distribution = Counter(len(value.faqs) for value in manuscripts.values())
    review_distribution = Counter(len(value.review_lines) for value in manuscripts.values())
    summary_distribution = Counter(len(_split_paragraphs(value.jsonld_summary)) for value in manuscripts.values())
    special_pages = sum(value.heading_kind != "markdown-h2" for value in manuscripts.values())
    special_headings = sum(len(value.sections) for value in manuscripts.values() if value.heading_kind != "markdown-h2")
    if (
        len(manuscripts) != EXPECTED_LOCALITIES
        or h2_distribution != Counter(dict(spec.h2_distribution))
        or sum(key * count for key, count in h2_distribution.items()) != spec.h2_total
        or intro_distribution != Counter(dict(spec.intro_distribution))
        or paragraph_total != spec.paragraph_total or section_paragraphs != spec.section_paragraphs
        or faq_distribution != Counter(dict(spec.faq_distribution))
        or sum(key * count for key, count in faq_distribution.items()) != spec.faq_total
        or review_distribution != Counter(dict(spec.review_distribution))
        or sum(key * count for key, count in review_distribution.items()) != spec.review_total
        or summary_distribution != Counter(dict(spec.summary_distribution))
        or sum(key * count for key, count in summary_distribution.items()) != spec.summary_paragraphs
        or sum(value.title == f"{value.locality} {spec.label}" for value in manuscripts.values()) != spec.title_exact
        or sum(value.title != f"{value.locality} {spec.label}" for value in manuscripts.values()) != spec.title_extended
    ):
        raise BuildError(f"{spec.key}: frozen workbook manuscript structural metrics mismatch")
    metrics = {
        **dict(workbook_metrics), "manuscripts": len(manuscripts),
        "title_exact": spec.title_exact, "title_extended": spec.title_extended,
        "source_h2": spec.h2_total, "h2_distribution": dict(sorted(h2_distribution.items())),
        "intro_distribution": dict(sorted(intro_distribution.items())),
        "source_body_paragraphs": paragraph_total, "source_section_paragraphs": section_paragraphs,
        "source_faq": spec.faq_total, "faq_distribution": dict(sorted(faq_distribution.items())),
        "source_review_blocks": spec.review_total, "review_distribution": dict(sorted(review_distribution.items())),
        "source_summary_paragraphs": spec.summary_paragraphs,
        "summary_distribution": dict(sorted(summary_distribution.items())),
        "special_heading_pages": special_pages, "special_headings": special_headings,
        "visible_manuscript_corrections": 0, "non_allowlisted_structural_transforms": 0,
    }
    return MappingProxyType(manuscripts), MappingProxyType(metrics)


def _normalize_workbook_paths(paths: Mapping[str, Path | str]) -> Mapping[str, Path]:
    if set(paths) != set(SPEC_BY_KEY):
        raise BuildError(f"exact workbook keys required: {sorted(SPEC_BY_KEY)}")
    normalized: dict[str, Path] = {}
    for spec in NEW_SPECS:
        original = Path(paths[spec.key]).expanduser()
        if original.is_symlink() or not original.is_file():
            raise BuildError(f"{spec.key}: workbook must be a regular non-symlink file: {original}")
        normalized[spec.key] = original.resolve()
    return MappingProxyType(normalized)


def _load_all_manuscripts(
    workbook_paths: Mapping[str, Path],
) -> tuple[Mapping[str, Mapping[str, Manuscript]], Mapping[str, Mapping[str, Any]]]:
    all_manuscripts: dict[str, Mapping[str, Manuscript]] = {}
    all_metrics: dict[str, Mapping[str, Any]] = {}
    for spec in NEW_SPECS:
        manuscripts, metrics = _load_manuscripts(spec, workbook_paths[spec.key])
        all_manuscripts[spec.key] = manuscripts
        all_metrics[spec.key] = metrics
    special_pages = sum(int(metrics["special_heading_pages"]) for metrics in all_metrics.values())
    special_headings = sum(int(metrics["special_headings"]) for metrics in all_metrics.values())
    if special_pages != EXPECTED_SPECIAL_HEADING_PAGES or special_headings != EXPECTED_SPECIAL_HEADINGS:
        raise BuildError("combined strict structural heading allowlist metrics mismatch")
    return MappingProxyType(all_manuscripts), MappingProxyType(all_metrics)


def _proxy_schools(spec: GradeSpec, record: Any) -> Any:
    schools = tuple(getattr(record, spec.school_attr))
    if len(schools) != len(set(schools)):
        raise BuildError(f"{spec.key}/{record.locality}: duplicate authoritative school chip")
    return replace(record, middle_schools=schools, middle_school_source_tokens=schools)


def _call_middle_with_exact_schools(function: Any, *args: Any) -> Any:
    """Call an inherited renderer/validator with identity school semantics."""

    previous = _MID._visible_schools

    def exact(record: Any) -> tuple[str, ...]:
        values = tuple(record.middle_schools)
        if len(values) != len(set(values)):
            raise BuildError(f"{record.locality}: duplicate authoritative school chip")
        return values

    _MID._visible_schools = exact
    try:
        return function(*args)
    finally:
        _MID._visible_schools = previous


def _mutate_jsonld(document: str, label: str, mutator: Any) -> str:
    matches = list(_BASE.SCRIPT_JSON_RE.finditer(document))
    if len(matches) != 1:
        raise BuildError(f"{label}: expected exactly one JSON-LD script")
    match = matches[0]
    try:
        value = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        raise BuildError(f"{label}: invalid generated JSON-LD") from exc
    mutator(value)
    replacement = match.group(1) + _BASE._json_script(value) + match.group(3)
    return document[:match.start()] + replacement + document[match.end():]


def _find_node(graph: Sequence[Any], node_type: str, label: str) -> dict[str, Any]:
    return _BASE._find_graph_node(graph, node_type, label)


def _canonical_text(document: str, old: str, new: str, label: str) -> str:
    old_count, new_count = document.count(old), document.count(new)
    if old_count and new_count:
        raise BuildError(f"{label}: baseline/canonical text collision")
    if not old_count and not new_count:
        raise BuildError(f"{label}: baseline/canonical text missing")
    return document.replace(old, new) if old_count else document


def _parent_card(spec: Any, number: int) -> str:
    return (
        f'<a class="subject-category-card" data-number="{number:02d}" href="/학년별학원/{spec.slug}/">'
        f'<small>{_escape(spec.english_label)}</small><h3>{_escape(spec.label)}</h3>'
        f'<p>{_escape(spec.card_copy)}</p><span class="subject-status">371개 지역 안내 보기 →</span></a>'
    )


def _update_parent(document: str) -> str:
    document = document.replace("\r\n", "\n").replace("\r", "\n")
    baseline_description = "중1·중2·중3 영어·수학과 고2 수학 7개 분류에서 학년별 진단, 학교 자료, 복습과 상담 기준을 371개 지역별로 확인하세요."
    description = "초6·중1·중2·중3 영어·수학과 고2 영어·수학 10개 분류에서 학년별 진단, 학교 자료, 복습과 상담 기준을 371개 지역별로 확인하세요."
    baseline_section = "중1·중2·중3 수학·영어와 고2 수학 7개 분류에서 각 371개 지역 원고를 제공합니다."
    section = "초6·중1·중2·중3 수학·영어와 고2 수학·영어 10개 분류에서 각 371개 지역 원고를 제공합니다."
    baseline_answer = "중학교 1·2·3학년의 수학·영어와 고등학교 2학년 수학 안내를 각 371개 동네별로 제공합니다."
    answer = "초등학교 6학년, 중학교 1·2·3학년과 고등학교 2학년의 수학·영어 안내를 각 371개 동네별로 제공합니다."
    document = _canonical_text(document, baseline_description, description, "grade parent description")
    document = _canonical_text(document, baseline_section, section, "grade parent section copy")
    document = _canonical_text(document, baseline_answer, answer, "grade parent FAQ answer")

    grid_start = '<div class="subject-category-grid">'
    grid_end = '</div></div></section>\n    <section class="subject-section"><div class="subject-container"><div class="subject-section-head"><p class="subject-kicker">HOW TO USE</p>'
    start = document.find(grid_start)
    end = document.find(grid_end, start)
    if start < 0 or end < 0 or document.find(grid_start, start + 1) >= 0:
        raise BuildError("grade parent: category grid boundary mismatch")
    cards = "".join(_parent_card(spec, index) for index, spec in enumerate(PARENT_ORDER, 1))
    document = document[:start] + grid_start + cards + document[end:]

    def mutate(value: dict[str, Any]) -> None:
        graph = value.get("@graph")
        if not isinstance(graph, list):
            raise BuildError("grade parent: JSON-LD graph missing")
        organization = _find_node(graph, "EducationalOrganization", "grade parent")
        organization["knowsAbout"] = [spec.label for spec in PARENT_ORDER] + ["학교 내신", "오답 재학습", "학습 계획"]
        page = _find_node(graph, "CollectionPage", "grade parent")
        page["description"] = description
        page["about"] = [
            {"@type": "Thing", "name": "학년별학원"},
            {"@type": "Thing", "name": "초등학교 영어·수학"},
            {"@type": "Thing", "name": "중학교 영어·수학"},
            {"@type": "Thing", "name": "고등학교 영어·수학"},
        ]
        page["hasPart"] = [
            {"@type": "CollectionPage", "name": spec.label, "url": _site_url("학년별학원", spec.slug)}
            for spec in PARENT_ORDER
        ]
        page["dateModified"] = PUBLISHED_DATE
        item_list = _find_node(graph, "ItemList", "grade parent")
        item_list["numberOfItems"] = EXPECTED_PARENT_CATEGORIES
        item_list["itemListElement"] = [
            {
                "@type": "ListItem", "position": index, "name": spec.label,
                "url": _site_url("학년별학원", spec.slug),
            }
            for index, spec in enumerate(PARENT_ORDER, 1)
        ]
        faq = _find_node(graph, "FAQPage", "grade parent")
        entities = faq.get("mainEntity")
        if not isinstance(entities, list) or len(entities) != 2:
            raise BuildError("grade parent: FAQ schema baseline mismatch")
        entities[1]["acceptedAnswer"]["text"] = answer

    return _MID._clean_document(_mutate_jsonld(document, "grade parent", mutate))


def _hub_style(document: str) -> str:
    matches = STYLE_RE.findall(document)
    if len(matches) != 1:
        raise BuildError("high2 mathematics hub clean-style pin mismatch")
    canonical = matches[0].replace("\r\n", "\n").replace("\r", "\n")
    if _sha256(canonical.encode("utf-8")) != HIGH2_HUB_STYLE_SHA256:
        raise BuildError("high2 mathematics hub clean-style pin mismatch")
    return canonical


def _render_category_hub(
    spec: GradeSpec, center_order: Sequence[str], centers: Mapping[str, Any], clean_style: str,
) -> str:
    document = _MID._render_category_hub(spec, center_order, centers)
    school_phrase = f"{spec.school_label}명이 없는 경우"
    if document.count("중학교명이 없는 경우") != 2:
        raise BuildError(f"{spec.key}: inherited category school-label baseline mismatch")
    document = document.replace("중학교명이 없는 경우", school_phrase)
    scoped_style = clean_style.replace('data-grade-directory="high2-math"', f'data-grade-directory="{spec.hook}"')
    if scoped_style == clean_style or "high2-math" in scoped_style:
        raise BuildError(f"{spec.key}: clean style scoping failed")
    document = _replace_once(
        document, '  <link rel="stylesheet" href="/assets/math-academy.css">',
        '  <link rel="stylesheet" href="/assets/math-academy.css">\n  ' + scoped_style,
        f"{spec.key}: clean style insertion",
    )
    description = f"{spec.label} 선택에 필요한 현재 학습 진단, 학교 자료, 오답 복습과 상담 확인 항목을 371개 동네별 원고에서 찾으세요."
    document = _replace_once(
        document,
        f'<p class="math-eyebrow">{_escape(spec.english_label)}</p><h1>{_escape(spec.label)} 371개 지역 안내</h1><p class="math-hero-lead">{_escape(description)}</p>',
        f'<p class="math-eyebrow">{_escape(spec.grade)} {_escape(spec.subject)} 지역 안내</p><h1>{_escape(spec.label)} 371개 지역 안내</h1><p class="math-hero-lead">거주 지역을 검색해 {_escape(spec.grade)} {_escape(spec.subject)} 학습 안내를 확인하세요.</p>',
        f"{spec.key}: clean hero copy",
    )
    document = _replace_once(
        document,
        '<aside class="math-hero-panel"><strong>학교명만으로 시험 유형을 단정하지 않습니다</strong><p>지역을 찾은 뒤 학생의 실제 교과서, 시험 범위와 학습 기록을 함께 대조하세요.</p><div class="math-step-row"><span>지역 찾기</span><span>원고 읽기</span><span>상담 확인</span></div></aside>',
        '<aside class="math-hero-panel"><strong>상세 안내를 확인해 주세요</strong><p>학교별 교과서·시험 범위와 실제 수업 가능 여부는 상담에서 확인합니다.</p><div class="math-step-row"><span>지역 검색</span><span>상세 확인</span><span>상담 확인</span></div></aside>',
        f"{spec.key}: clean hero panel",
    )
    document = _replace_once(
        document,
        f'<div class="math-section-head"><p class="math-eyebrow">LOCAL DIRECTORY</p><h2>동네별 {_escape(spec.label)} 원고 찾기</h2><p>지역명 일부를 입력하면 목록을 바로 좁힐 수 있습니다.</p></div>',
        f'<div class="math-section-head"><p class="math-eyebrow">지역 검색</p><h2>지역별 {_escape(spec.label)} 안내</h2><p>동네 이름을 입력해 지역 페이지를 찾으세요.</p></div>',
        f"{spec.key}: clean directory heading",
    )
    document = _replace_once(
        document,
        f'<p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>{_escape(spec.grade)} {_escape(spec.subject)} 상담 전 준비 자료</h2>',
        '<p class="math-eyebrow">관련 안내</p><h2>함께 살펴볼 안내</h2>',
        f"{spec.key}: clean related heading",
    )
    document = _replace_once(
        document,
        '지역 원고와 제공 자료를 구분해 확인하고 실제 수업 조건은 상담에서 최신 내용을 확인해 주세요.',
        '학교별 수업 범위와 운영 조건은 상담 시 확인해 주세요.',
        f"{spec.key}: clean footer",
    )

    def mutate(value: dict[str, Any]) -> None:
        graph = value.get("@graph")
        if not isinstance(graph, list):
            raise BuildError(f"{spec.key}: category JSON-LD graph missing")
        organization = _find_node(graph, "EducationalOrganization", f"{spec.key} category")
        knows = organization.get("knowsAbout")
        if not isinstance(knows, list):
            raise BuildError(f"{spec.key}: category knowsAbout missing")
        if spec.label not in knows:
            knows.append(spec.label)
        for node in graph:
            if isinstance(node, dict):
                if "datePublished" in node:
                    node["datePublished"] = PUBLISHED_DATE
                if "dateModified" in node:
                    node["dateModified"] = PUBLISHED_DATE

    return _MID._clean_document(_mutate_jsonld(document, f"{spec.key} category", mutate))


def _render_detail(
    spec: GradeSpec, manuscript: Manuscript, record: Any, assets: Any,
    previous_locality: str, next_locality: str,
) -> str:
    proxy = _proxy_schools(spec, record)
    document = _call_middle_with_exact_schools(
        _MID._render_detail, spec, manuscript, proxy, assets, previous_locality, next_locality,
    )
    document = _replace_once(
        document, 'data-source-field="middle-schools"', f'data-source-field="{spec.school_hook}"',
        manuscript.member_name,
    )
    document = document.replace("원자료에 중학교명이 기재되지 않아", f"원자료에 {spec.school_label}명이 기재되지 않아")
    article_tag = '<article class="math-narrow math-article" data-manuscript>'
    enriched_tag = (
        f'<article class="math-narrow math-article" data-source-workbook-row="{manuscript.workbook_row}" '
        f'data-source-cell-sha256="{manuscript.cell_sha256}" data-manuscript-sha256="{manuscript.cell_sha256}" '
        f'data-source-heading-kind="{manuscript.heading_kind}" data-manuscript>'
    )
    document = _replace_once(document, article_tag, enriched_tag, manuscript.member_name)
    document = _replace_once(document, 'math-faq-card" data-faq>', 'math-faq-card" data-manuscript-faq data-faq>', manuscript.member_name)
    document = _replace_once(document, 'math-review-card" data-review>', 'math-review-card" data-manuscript-review data-review>', manuscript.member_name)
    document, heading_replacements = re.subn(
        r'(<section id="section-[0-9]{2}" class="math-prose-section" data-manuscript-section="[0-9]{2}">\n[ \t]*)<h2>',
        r'\1<h2 data-source-heading>', document,
    )
    if heading_replacements != len(manuscript.sections):
        raise BuildError(f"{spec.key}/{manuscript.member_name}: source heading hook cardinality mismatch")
    document, paragraph_replacements = re.subn(
        r'(<p data-manuscript-paragraph="[^"]+" data-source-sha256="[0-9a-f]{64}")>',
        r'\1 data-source-paragraph>', document,
    )
    expected_paragraphs = len(manuscript.intro_paragraphs) + sum(len(section.paragraphs) for section in manuscript.sections)
    if paragraph_replacements != expected_paragraphs:
        raise BuildError(f"{spec.key}/{manuscript.member_name}: source paragraph hook cardinality mismatch")
    for faq in manuscript.faqs:
        old_question = f"<summary><span>Q{faq.number}.</span> {_escape(faq.question)}</summary>"
        new_question = f"<summary data-source-question><span>{_escape(faq.question_prefix)}</span> {_escape(faq.question)}</summary>"
        document = _replace_once(document, old_question, new_question, f"{spec.key}/{manuscript.member_name} FAQ question {faq.number}")
        old_answer = f"<p><strong>A.</strong> {_MID._paragraph_markup(faq.answer)}</p>"
        prefix = f"<strong>{_escape(faq.answer_prefix)}</strong> "
        new_answer = f"<p data-source-answer>{prefix}{_MID._paragraph_markup(faq.answer)}</p>"
        document = _replace_once(document, old_answer, new_answer, f"{spec.key}/{manuscript.member_name} FAQ answer {faq.number}")

    inherited_audience = f"중학교 {spec.grade_number}학년({spec.grade})"

    def mutate(value: dict[str, Any]) -> None:
        graph = value.get("@graph")
        if not isinstance(graph, list):
            raise BuildError(f"{spec.key}/{manuscript.member_name}: JSON-LD graph missing")
        for node in graph:
            if not isinstance(node, dict):
                continue
            if "datePublished" in node:
                node["datePublished"] = PUBLISHED_DATE
            if "dateModified" in node:
                node["dateModified"] = PUBLISHED_DATE
            node_types = node.get("@type")
            types = (node_types,) if isinstance(node_types, str) else tuple(node_types or ())
            if "Service" in types:
                audience = node.get("audience")
                if not isinstance(audience, dict) or audience.get("audienceType") != inherited_audience:
                    raise BuildError(f"{spec.key}/{manuscript.member_name}: inherited audience baseline mismatch")
                audience["audienceType"] = spec.audience_type

    return _MID._clean_document(_mutate_jsonld(document, f"{spec.key}/{manuscript.member_name}", mutate))


def _validate_parent(document: str) -> None:
    label = "grade parent hub"
    audit = _BASE._audit_html(document, label)
    _BASE._validate_nav(document, label, grade_active=True)
    mains = [attrs for tag, attrs in audit.start_tags if tag == "main" and attrs.get("data-grade-directory") == "parent"]
    if len(mains) != 1:
        raise BuildError("grade parent: main hook mismatch")
    canonical = _site_url("학년별학원")
    if _BASE._canonical_values(document) != [canonical] or _BASE._meta_values(document, property_name="og:url") != [canonical]:
        raise BuildError("grade parent: canonical/og:url mismatch")
    for index, spec in enumerate(PARENT_ORDER, 1):
        if document.count(f'data-number="{index:02d}" href="/학년별학원/{spec.slug}/"') != 1:
            raise BuildError(f"grade parent: ordered category card mismatch: {spec.key}")
    if document.count('class="subject-category-card"') != EXPECTED_PARENT_CATEGORIES:
        raise BuildError("grade parent: category card count mismatch")
    jsonld, _ = _BASE._extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    item_list = _find_node(graph, "ItemList", label)
    page = _find_node(graph, "CollectionPage", label)
    items = item_list.get("itemListElement", [])
    parts = page.get("hasPart", [])
    if (
        item_list.get("numberOfItems") != EXPECTED_PARENT_CATEGORIES
        or len(items) != EXPECTED_PARENT_CATEGORIES or len(parts) != EXPECTED_PARENT_CATEGORIES
        or [item.get("name") for item in items] != [spec.label for spec in PARENT_ORDER]
        or [item.get("name") for item in parts] != [spec.label for spec in PARENT_ORDER]
    ):
        raise BuildError("grade parent: ten-category schema/order mismatch")
    faq = _find_node(graph, "FAQPage", label)
    if len(faq.get("mainEntity", [])) != 2 or document.count(" data-faq>") != 1:
        raise BuildError("grade parent: FAQ visible/schema mismatch")


def _validate_category(spec: GradeSpec, document: str, center_order: Sequence[str]) -> None:
    _MID._validate_category(spec, document, center_order)
    label = f"{spec.key} category"
    style_matches = STYLE_RE.findall(document)
    if len(style_matches) != 1:
        raise BuildError(f"{label}: clean style cardinality mismatch")
    normalized_style = style_matches[0].replace(
        f'data-grade-directory="{spec.hook}"', 'data-grade-directory="high2-math"'
    )
    if _sha256(normalized_style.encode("utf-8")) != HIGH2_HUB_STYLE_SHA256:
        raise BuildError(f"{label}: clean style parity mismatch")
    main = re.search(r"<main\b.*?</main>", document, re.DOTALL)
    if main is None or "원고" in main.group(0):
        raise BuildError(f"{label}: cleaned visible hub copy regressed")
    for fragment in (
        f"{spec.grade} {spec.subject} 지역 안내", "상세 안내를 확인해 주세요",
        "지역 검색", f"지역별 {spec.label} 안내", "함께 살펴볼 안내",
    ):
        if fragment not in main.group(0):
            raise BuildError(f"{label}: clean hub fragment missing: {fragment}")
    jsonld, _ = _BASE._extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    item_list = _find_node(graph, "ItemList", label)
    faq = _find_node(graph, "FAQPage", label)
    if item_list.get("numberOfItems") != EXPECTED_LOCALITIES or len(item_list.get("itemListElement", [])) != EXPECTED_LOCALITIES:
        raise BuildError(f"{label}: ItemList count mismatch")
    if len(faq.get("mainEntity", [])) != 2:
        raise BuildError(f"{label}: FAQ schema count mismatch")
    if f"{spec.school_label}명이 없는 경우" not in json.dumps(faq, ensure_ascii=False):
        raise BuildError(f"{label}: school-tier FAQ wording mismatch")


def _validate_detail(spec: GradeSpec, document: str, manuscript: Manuscript, record: Any, assets: Any) -> None:
    label = f"{spec.key}/{manuscript.member_name}"
    if document.count(f'data-source-field="{spec.school_hook}"') != 1 or 'data-source-field="middle-schools"' in document:
        raise BuildError(f"{label}: school-tier fact hook mismatch")
    for attribute, expected in (
        ("data-source-workbook-row", str(manuscript.workbook_row)),
        ("data-source-cell-sha256", manuscript.cell_sha256),
        ("data-manuscript-sha256", manuscript.cell_sha256),
        ("data-source-heading-kind", manuscript.heading_kind),
    ):
        if document.count(f'{attribute}="{expected}"') != 1:
            raise BuildError(f"{label}: workbook/source identity hook mismatch: {attribute}")
    proxy = _proxy_schools(spec, record)
    compatibility = document.replace(f'data-source-field="{spec.school_hook}"', 'data-source-field="middle-schools"')
    compatibility = compatibility.replace(" data-source-heading", "").replace(" data-source-paragraph", "")
    compatibility = compatibility.replace(" data-source-question", "").replace(" data-source-answer", "")
    _call_middle_with_exact_schools(_MID._validate_detail, spec, compatibility, manuscript, proxy, assets)

    jsonld, _ = _BASE._extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    types = _BASE._schema_types(graph)
    supported = spec.grade in getattr(record, spec.grade_attr)
    if supported:
        service = _find_node(graph, "Service", label)
        audience = service.get("audience")
        if not isinstance(audience, dict) or audience.get("audienceType") != spec.audience_type:
            raise BuildError(f"{label}: school-tier audience mismatch")
    elif types["Service"] or types["Offer"]:
        raise BuildError(f"{label}: unconfirmed page contains Service/Offer")
    schools = tuple(getattr(record, spec.school_attr))
    visible = tuple(html.unescape(value) for value in re.findall(r"<span data-source-school>(.*?)</span>", document, re.DOTALL))
    if visible != schools:
        raise BuildError(f"{label}: visible school/common-source mismatch")
    for faq in manuscript.faqs:
        block_match = re.search(
            rf'<details class="math-faq-item" data-source-faq="{faq.number:02d}"[^>]*>(.*?)</details>',
            document, re.DOTALL,
        )
        if block_match is None:
            raise BuildError(f"{label}: FAQ block missing {faq.number}")
        block = block_match.group(1)
        question_prefix = re.search(r"<summary data-source-question><span>(.*?)</span>", block, re.DOTALL)
        answer_prefix = re.search(r"<p data-source-answer><strong>(.*?)</strong> ", block, re.DOTALL)
        if question_prefix is None or html.unescape(question_prefix.group(1)) != faq.question_prefix:
            raise BuildError(f"{label}: exact FAQ question prefix changed")
        if answer_prefix is None or html.unescape(answer_prefix.group(1)) != faq.answer_prefix:
            raise BuildError(f"{label}: exact FAQ answer prefix changed")
    if _BASE._meta_values(document, name="description") != [manuscript.meta_description]:
        raise BuildError(f"{label}: exact manuscript meta changed")
    h1 = re.search(r"<h1>(.*?)</h1>", document, re.DOTALL)
    if h1 is None or html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))) != manuscript.title:
        raise BuildError(f"{label}: exact manuscript H1 changed")
    headings = tuple(html.unescape(value) for value in re.findall(r"<h2 data-source-heading>(.*?)</h2>", document, re.DOTALL))
    if headings != tuple(section.heading for section in manuscript.sections):
        raise BuildError(f"{label}: exact source heading text changed")


def _sitemap_urls(center_order: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for spec in NEW_SPECS:
        values.append(_site_url("학년별학원", spec.slug))
        values.extend(_site_url("학년별학원", spec.slug, locality) for locality in center_order)
    return tuple(values)


def _url_blocks(document: str) -> tuple[tuple[str, str, str], ...]:
    values: list[tuple[str, str, str]] = []
    for match in RAW_URL_RE.finditer(document):
        block = match.group(0)
        locations = LOC_RE.findall(block)
        lastmods = LASTMOD_RE.findall(block)
        if len(locations) != 1 or len(lastmods) != 1:
            raise BuildError("sitemap.xml: malformed URL block")
        values.append((html.unescape(locations[0]), html.unescape(lastmods[0]), block))
    return tuple(values)


def _update_sitemap(document: str, center_order: Sequence[str]) -> str:
    new_urls = _sitemap_urls(center_order)
    if len(new_urls) != EXPECTED_NEW_HTML or len(set(new_urls)) != EXPECTED_NEW_HTML:
        raise BuildError("sitemap.xml: generated URL cardinality/uniqueness mismatch")
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
            raise BuildError("sitemap.xml: closing tag line contract failed")
        appended = "".join(
            f"  <url>{newline}    <loc>{_escape(url)}</loc>{newline}    <lastmod>{PUBLISHED_DATE}</lastmod>{newline}  </url>{newline}"
            for url in new_urls
        )
        return prefix + appended + suffix
    if len(positions) != EXPECTED_NEW_HTML or len(blocks) != EXPECTED_FINAL_HTML:
        raise BuildError("sitemap.xml: partial/conflicting new URL set")
    if positions != list(range(EXPECTED_EXISTING_HTML, EXPECTED_FINAL_HTML)):
        raise BuildError("sitemap.xml: new URLs are not a contiguous final block")
    if tuple(location for location, _, _ in blocks[-EXPECTED_NEW_HTML:]) != new_urls:
        raise BuildError("sitemap.xml: new URL order mismatch")
    if any(lastmod != PUBLISHED_DATE for _, lastmod, _ in blocks[-EXPECTED_NEW_HTML:]):
        raise BuildError("sitemap.xml: new URL lastmod mismatch")
    return document


def _llms_block() -> str:
    lines = [
        LLMS_MARKER, "",
        f"- 학년별학원: {SITE_ORIGIN}/학년별학원/",
        "  - 초6·중1·중2·중3 영어·수학과 고2 영어·수학 지역 안내를 학년과 과목별로 찾는 핵심 허브입니다.",
    ]
    for spec in PARENT_ORDER:
        lines.extend([
            f"- {spec.label}: {SITE_ORIGIN}/학년별학원/{spec.slug}/",
            f"  - {spec.grade} {spec.subject} 진단·학교 자료·오답 재학습·상담 기준을 371개 동네별 원고로 안내합니다.",
        ])
    return "\n".join(lines) + "\n"


def _update_llms(document: str) -> str:
    if document.count(LLMS_MARKER) != 1:
        raise BuildError("llms.txt: exact grade marker required")
    prefix = document[:document.index(LLMS_MARKER)]
    canonical = prefix + _llms_block()
    if document != canonical and _sha256(document.encode("utf-8")) != BASE_LLMS_SHA256:
        raise BuildError("llms.txt: baseline/canonical conflict")
    return canonical


def _files_manifest(root: Path, paths: Sequence[Path], overrides: Mapping[Path, str | bytes]) -> str:
    return _MID._files_manifest(root, paths, overrides)


def _candidate_sha(after_manifest: Mapping[Path, str], source_manifest: Mapping[str, str]) -> str:
    return _MID._candidate_sha(after_manifest, source_manifest)


def _asset_paths(root: Path) -> tuple[Path, ...]:
    asset_root = root / "assets"
    if asset_root.is_symlink() or not asset_root.is_dir():
        raise BuildError("assets directory must be a regular non-symlink directory")
    paths: list[Path] = []
    for path in asset_root.rglob("*"):
        if path.is_symlink():
            raise BuildError(f"asset symlink is forbidden: {path.relative_to(root)}")
        if path.is_file():
            paths.append(path.relative_to(root))
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _existing_generator_paths(root: Path) -> tuple[Path, ...]:
    names = (
        "generate_grade3_math_pages.py", "generate_middle_grade_pages.py", "generate_high2_math_pages.py",
    )
    paths = tuple(Path("tools") / name for name in names)
    if any((root / path).is_symlink() or not (root / path).is_file() for path in paths):
        raise BuildError("existing generator file set is missing/symlinked")
    discovered = tuple(
        sorted(
            (
                path.relative_to(root) for path in (root / "tools").glob("generate_*.py")
                if path.name != Path(__file__).name
            ),
            key=lambda item: item.as_posix(),
        )
    )
    if discovered != tuple(sorted(paths, key=lambda item: item.as_posix())):
        raise BuildError(f"existing generator file set drift: {discovered}")
    return paths


def _boundary_manifests(
    root: Path, overrides: Mapping[Path, str | bytes], new_html_paths: set[Path],
) -> Mapping[str, Any]:
    html_paths = _BASE._enumerate_html(root, overrides)
    present_new = html_paths & new_html_paths
    if present_new and present_new != new_html_paths:
        raise BuildError(f"partial generated batch tree: {len(present_new)}/{len(new_html_paths)}")
    existing_html = html_paths - new_html_paths
    if len(existing_html) != EXPECTED_EXISTING_HTML or PARENT_REL not in existing_html:
        raise BuildError(f"existing HTML baseline mismatch: {len(existing_html)}")
    immutable = tuple(path for path in existing_html if path != PARENT_REL)
    high2_math = tuple(
        path for path in immutable if path == HIGH2_MATH_HUB_REL or HIGH2_MATH_ROOT in path.parents
    )
    assets = _asset_paths(root)
    generators = _existing_generator_paths(root)
    values = {
        "html_paths": html_paths, "present_new": present_new, "existing_html": existing_html,
        "immutable_count": len(immutable), "immutable_sha256": _files_manifest(root, immutable, overrides),
        "high2_math_count": len(high2_math), "high2_math_sha256": _files_manifest(root, high2_math, overrides),
        "asset_count": len(assets), "asset_sha256": _files_manifest(root, assets, {}),
        "generator_count": len(generators), "generator_sha256": _files_manifest(root, generators, {}),
    }
    if (
        values["immutable_count"] != EXPECTED_IMMUTABLE_HTML
        or values["immutable_sha256"] != BASE_IMMUTABLE_HTML_MANIFEST_SHA256
        or values["high2_math_count"] != EXPECTED_HIGH2_MATH_HTML
        or values["high2_math_sha256"] != BASE_HIGH2_MATH_MANIFEST_SHA256
        or values["asset_count"] != EXPECTED_ASSET_FILES
        or values["asset_sha256"] != BASE_ASSET_MANIFEST_SHA256
        or values["generator_count"] != EXPECTED_EXISTING_GENERATORS
        or values["generator_sha256"] != BASE_GENERATOR_MANIFEST_SHA256
    ):
        raise BuildError("immutable HTML/high2/assets/existing-generator boundary drift")
    return MappingProxyType(values)


def build_plan(
    root: Path | str,
    workbook_paths: Mapping[str, Path | str],
    common_dir: Path | str,
    current_overrides: Mapping[Path | str, str | bytes] | None = None,
) -> BuildPlan:
    """Materialize and audit the exact sparse 1,119-document release plan."""

    root = Path(root).resolve()
    common_dir = Path(common_dir).resolve()
    if not root.is_dir() or not common_dir.is_dir():
        raise BuildError("root and common data directory must already exist")
    pending = [path for path in root.iterdir() if path.is_dir() and path.name.startswith(_BASE.TRANSACTION_PREFIX)]
    if pending:
        raise BuildError("pending transaction detected")
    normalized_workbooks = _normalize_workbook_paths(workbook_paths)
    overrides = _BASE._normalize_overrides(root, current_overrides)
    centers, center_metrics = _BASE._load_centers(common_dir)
    center_order = tuple(centers)
    all_manuscripts, manuscript_metrics = _load_all_manuscripts(normalized_workbooks)
    for spec in NEW_SPECS:
        if center_order != tuple(all_manuscripts[spec.key]):
            raise BuildError(f"{spec.key}: workbook locality order must match authoritative center CSV")

    new_html_paths = {
        *(_category_rel(spec) for spec in NEW_SPECS),
        *(_detail_rel(spec, locality) for spec in NEW_SPECS for locality in center_order),
    }
    authorized_paths = {PARENT_REL, SITEMAP_REL, LLMS_REL, *new_html_paths}
    if len(new_html_paths) != EXPECTED_NEW_HTML or len(authorized_paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("authorized sparse path cardinality mismatch")
    unknown_overrides = set(overrides) - authorized_paths
    if unknown_overrides:
        raise BuildError(f"current_overrides contains unauthorized paths: {sorted(map(str, unknown_overrides))[:4]}")
    boundary = _boundary_manifests(root, overrides, new_html_paths)
    html_paths = set(boundary["html_paths"])
    present_new = set(boundary["present_new"])
    existing_html_paths = set(boundary["existing_html"])

    supported_metrics: dict[str, Mapping[str, int]] = {}
    for spec in NEW_SPECS:
        supported = sum(spec.grade in getattr(record, spec.grade_attr) for record in centers.values())
        unconfirmed = EXPECTED_LOCALITIES - supported
        school_chips = sum(len(getattr(record, spec.school_attr)) for record in centers.values())
        missing_school_rows = sum(not getattr(record, spec.school_attr) for record in centers.values())
        if (supported, unconfirmed, school_chips, missing_school_rows) != (
            spec.supported, spec.unconfirmed, spec.school_chips, spec.missing_school_rows,
        ):
            raise BuildError(f"{spec.key}: authoritative grade/school metrics mismatch")
        supported_metrics[spec.key] = MappingProxyType({
            "supported": supported, "unconfirmed": unconfirmed,
            "school_chips": school_chips, "missing_school_rows": missing_school_rows,
        })

    hub_document = _decode_utf8(_BASE._read_current_bytes(root, HIGH2_MATH_HUB_REL, overrides), HIGH2_MATH_HUB_REL.as_posix())
    clean_style = _hub_style(hub_document)
    assets_cache: dict[tuple[str, str], Any] = {}
    representative_sources: set[str] = set()
    body_sources: set[str] = set()
    map_sources: set[str] = set()
    for spec in NEW_SPECS:
        for locality, record in centers.items():
            cache_key = (spec.subject, locality)
            if cache_key not in assets_cache:
                rel = _generic_rel(spec, locality)
                if rel not in existing_html_paths:
                    raise BuildError(f"{spec.key}/{locality}: generic subject source page missing")
                source = _decode_utf8(_BASE._read_current_bytes(root, rel, overrides), rel.as_posix())
                assets_cache[cache_key] = _BASE._load_page_assets(root, locality, source)
            assets = assets_cache[cache_key]
            _MID._crosscheck_physical_source(spec, record, assets)
            representative_sources.add(assets.representative_src)
            body_sources.add(assets.body_src)
            map_sources.add(assets.map_src)

    parent_exists, parent_before = _BASE._read_optional_current_bytes(root, PARENT_REL, overrides)
    if not parent_exists:
        raise BuildError("grade parent hub disappeared")
    parent_current = _decode_utf8(parent_before, PARENT_REL.as_posix())
    generated: dict[Path, str] = {PARENT_REL: _update_parent(parent_current)}
    for spec in NEW_SPECS:
        generated[_category_rel(spec)] = _render_category_hub(spec, center_order, centers, clean_style)
        manuscripts = all_manuscripts[spec.key]
        for index, locality in enumerate(center_order):
            generated[_detail_rel(spec, locality)] = _render_detail(
                spec, manuscripts[locality], centers[locality], assets_cache[(spec.subject, locality)],
                center_order[index - 1], center_order[(index + 1) % len(center_order)],
            )
    if len(generated) != EXPECTED_NEW_HTML + 1:
        raise BuildError("generated parent/new HTML count mismatch")

    if not present_new:
        if _sha256(parent_before) != BASE_PARENT_SHA256:
            raise BuildError("grade parent baseline drift")
    elif parent_before != _as_bytes(generated[PARENT_REL]):
        raise BuildError("complete new tree exists with non-canonical parent")
    sitemap_current = _decode_utf8(_BASE._read_current_bytes(root, SITEMAP_REL, overrides), SITEMAP_REL.as_posix())
    llms_current = _decode_utf8(_BASE._read_current_bytes(root, LLMS_REL, overrides), LLMS_REL.as_posix())
    generated[SITEMAP_REL] = _update_sitemap(sitemap_current, center_order)
    generated[LLMS_REL] = _update_llms(llms_current)
    if set(generated) != authorized_paths:
        raise BuildError("materialized sparse set differs from authorization")

    _validate_parent(generated[PARENT_REL])
    for spec in NEW_SPECS:
        _validate_category(spec, generated[_category_rel(spec)], center_order)
        for locality in center_order:
            _validate_detail(
                spec, generated[_detail_rel(spec, locality)], all_manuscripts[spec.key][locality],
                centers[locality], assets_cache[(spec.subject, locality)],
            )
    final_html_paths = set(existing_html_paths) | new_html_paths
    if len(final_html_paths) != EXPECTED_FINAL_HTML:
        raise BuildError("final HTML route count mismatch")
    internal_links_checked = _MID._validate_generated_links(root, generated, final_html_paths)

    original_blocks = _url_blocks(sitemap_current)
    final_blocks = _url_blocks(generated[SITEMAP_REL])
    if len(final_blocks) != EXPECTED_FINAL_HTML:
        raise BuildError("final sitemap count mismatch")
    if not present_new:
        if tuple(block for _, _, block in final_blocks[:EXPECTED_EXISTING_HTML]) != tuple(block for _, _, block in original_blocks):
            raise BuildError("existing sitemap blocks changed")
    elif generated[SITEMAP_REL] != sitemap_current:
        raise BuildError("complete new tree has non-canonical sitemap")

    before_manifest: dict[Path, str] = {}
    after_manifest: dict[Path, str] = {}
    before_exists: dict[Path, bool] = {}
    changed: list[Path] = []
    for rel in sorted(generated, key=lambda path: path.as_posix()):
        exists, before = _BASE._read_optional_current_bytes(root, rel, overrides)
        after = _as_bytes(generated[rel])
        before_exists[rel] = exists
        before_manifest[rel] = _sha256(before) if exists else ABSENT_SHA256
        after_manifest[rel] = _sha256(after)
        if not exists or before != after:
            changed.append(rel)
    if len(changed) not in (0, EXPECTED_AUTHORIZED_DOCUMENTS):
        raise BuildError(f"partial/non-canonical changed path count: {len(changed)}")

    second_pass: list[Path] = []
    if _update_parent(generated[PARENT_REL]) != generated[PARENT_REL]:
        second_pass.append(PARENT_REL)
    for spec in NEW_SPECS:
        if _render_category_hub(spec, center_order, centers, clean_style) != generated[_category_rel(spec)]:
            second_pass.append(_category_rel(spec))
        manuscripts = all_manuscripts[spec.key]
        for index, locality in enumerate(center_order):
            rel = _detail_rel(spec, locality)
            second = _render_detail(
                spec, manuscripts[locality], centers[locality], assets_cache[(spec.subject, locality)],
                center_order[index - 1], center_order[(index + 1) % len(center_order)],
            )
            if second != generated[rel]:
                second_pass.append(rel)
    if _update_sitemap(generated[SITEMAP_REL], center_order) != generated[SITEMAP_REL]:
        second_pass.append(SITEMAP_REL)
    if _update_llms(generated[LLMS_REL]) != generated[LLMS_REL]:
        second_pass.append(LLMS_REL)
    if second_pass:
        raise BuildError(f"second-pass idempotency failed: {len(second_pass)}")

    self_path = Path(__file__).resolve()
    source_paths = {
        **{f"workbook_{spec.key}": normalized_workbooks[spec.key] for spec in NEW_SPECS},
        "center_csv": common_dir / "센터정보 정리.csv",
        "target_school_csv": common_dir / "타깃학교.csv",
        "middle_helper": Path(_MID.__file__).resolve(),
        "base_helper": Path(_BASE.__file__).resolve(),
        "high2_math_helper": self_path.with_name("generate_high2_math_pages.py"),
        "generator": self_path,
    }
    source_manifest = {
        **{f"workbook_{spec.key}": spec.workbook_sha256 for spec in NEW_SPECS},
        **{f"workbook_cells_{spec.key}": spec.cell_manifest_sha256 for spec in NEW_SPECS},
        "center_csv": CENTER_CSV_SHA256, "target_school_csv": TARGET_SCHOOL_CSV_SHA256,
        "middle_helper": MIDDLE_HELPER_SHA256, "base_helper": BASE_HELPER_SHA256,
        "high2_math_helper": HIGH2_MATH_HELPER_SHA256, "generator": _sha256(self_path.read_bytes()),
        "high2_hub_style": HIGH2_HUB_STYLE_SHA256,
    }
    source_metrics = {
        "workbooks": {spec.key: dict(manuscript_metrics[spec.key]) for spec in NEW_SPECS},
        "authoritative_centers": dict(center_metrics),
        "support": {key: dict(value) for key, value in supported_metrics.items()},
        "source_workbooks": EXPECTED_NEW_CATEGORIES, "source_cells": EXPECTED_NEW_CATEGORIES * EXPECTED_LOCALITIES,
        "special_heading_pages": EXPECTED_SPECIAL_HEADING_PAGES,
        "special_headings": EXPECTED_SPECIAL_HEADINGS,
        "visible_manuscript_corrections": 0, "non_allowlisted_structural_transforms": 0,
        "representative_sources": len(representative_sources), "body_sources": len(body_sources), "map_sources": len(map_sources),
    }
    before_metrics = {
        "html_documents": len(html_paths), "existing_html_documents": len(existing_html_paths),
        "already_present_new_html": len(present_new), "sitemap_urls": len(original_blocks),
        "immutable_existing_html": int(boundary["immutable_count"]),
        "immutable_html_manifest_sha256": str(boundary["immutable_sha256"]),
        "high2_math_html": int(boundary["high2_math_count"]),
        "high2_math_manifest_sha256": str(boundary["high2_math_sha256"]),
        "asset_files": int(boundary["asset_count"]), "asset_manifest_sha256": str(boundary["asset_sha256"]),
        "existing_generators": int(boundary["generator_count"]),
        "generator_manifest_sha256": str(boundary["generator_sha256"]),
    }
    after_metrics = {
        "authorized_documents": len(generated), "final_html_documents": EXPECTED_FINAL_HTML,
        "new_html_documents": EXPECTED_NEW_HTML, "new_category_hubs": EXPECTED_NEW_CATEGORIES,
        "new_detail_documents": EXPECTED_NEW_CATEGORIES * EXPECTED_LOCALITIES,
        "parent_hub_categories": EXPECTED_PARENT_CATEGORIES,
        "sitemap_urls": len(final_blocks), "sitemap_existing_blocks_preserved": EXPECTED_EXISTING_HTML,
        "sitemap_new_urls_appended": EXPECTED_NEW_HTML, "sitemap_new_lastmod": PUBLISHED_DATE,
        "supported_service_offer_pages": sum(spec.supported for spec in NEW_SPECS),
        "unconfirmed_article_only_pages": sum(spec.unconfirmed for spec in NEW_SPECS),
        "school_chips": sum(spec.school_chips for spec in NEW_SPECS),
        "internal_links_checked": internal_links_checked, "second_pass_changes": len(second_pass),
    }
    metrics = {
        "changed_paths": len(changed), "unchanged_authorized_paths": len(generated) - len(changed),
        "sparse_plan": "pass", "existing_html_assets_generators_preservation": "pass",
        "source_exact_rendering": "pass", "facts_assets_schema_links_gate": "pass",
        **{f"after_{key}": value for key, value in after_metrics.items()},
    }
    candidate = _candidate_sha(after_manifest, source_manifest)
    return BuildPlan(
        root=root, authorized_documents=MappingProxyType(generated), changed_paths=tuple(changed),
        second_pass_changes=tuple(second_pass), source_manifest=MappingProxyType(source_manifest),
        source_paths=MappingProxyType(source_paths), before_manifest=MappingProxyType(before_manifest),
        after_manifest=MappingProxyType(after_manifest), before_exists=MappingProxyType(before_exists),
        source_metrics=MappingProxyType(source_metrics), before_metrics=MappingProxyType(before_metrics),
        after_metrics=MappingProxyType(after_metrics), metrics=MappingProxyType(metrics),
        candidate_sha256=candidate,
        immutable_html_manifest_sha256=str(boundary["immutable_sha256"]),
        high2_math_manifest_sha256=str(boundary["high2_math_sha256"]),
        asset_manifest_sha256=str(boundary["asset_sha256"]),
        generator_manifest_sha256=str(boundary["generator_sha256"]),
    )


def _self_sha256() -> str:
    return _sha256(Path(__file__).read_bytes())


def freeze_payload(plan: BuildPlan) -> Mapping[str, Any]:
    return MappingProxyType({
        "version": 1, "root": str(plan.root), "generator_sha256": _self_sha256(),
        "middle_helper_sha256": MIDDLE_HELPER_SHA256, "base_helper_sha256": BASE_HELPER_SHA256,
        "high2_math_helper_sha256": HIGH2_MATH_HELPER_SHA256,
        "candidate_sha256": plan.candidate_sha256, "source_manifest": dict(plan.source_manifest),
        "authorized_paths": [path.as_posix() for path in sorted(plan.authorized_documents, key=lambda item: item.as_posix())],
        "changed_paths": [path.as_posix() for path in plan.changed_paths],
        "before_exists": {path.as_posix(): plan.before_exists[path] for path in sorted(plan.before_exists, key=lambda item: item.as_posix())},
        "before_manifest": {path.as_posix(): plan.before_manifest[path] for path in sorted(plan.before_manifest, key=lambda item: item.as_posix())},
        "after_manifest": {path.as_posix(): plan.after_manifest[path] for path in sorted(plan.after_manifest, key=lambda item: item.as_posix())},
        "immutable_html_manifest_sha256": plan.immutable_html_manifest_sha256,
        "high2_math_manifest_sha256": plan.high2_math_manifest_sha256,
        "asset_manifest_sha256": plan.asset_manifest_sha256,
        "generator_manifest_sha256": plan.generator_manifest_sha256,
    })


def _plain_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _validate_freeze_payload(plan: BuildPlan, frozen: Mapping[str, Any]) -> None:
    expected = _plain_json(dict(freeze_payload(plan)))
    actual = _plain_json(dict(frozen))
    if actual != expected:
        mismatches = [key for key in sorted(set(expected) | set(actual)) if expected.get(key) != actual.get(key)]
        raise BuildError(f"external freeze payload mismatch: {mismatches[:6]}")
    paths = actual.get("authorized_paths")
    if not isinstance(paths, list) or len(paths) != len(set(paths)) or len(paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("external freeze authorized path set malformed")
    if len(actual.get("changed_paths", [])) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("external freeze must approve the exact initial 1,119-path mutation")


def _new_html_paths_from_existing(root: Path) -> set[Path]:
    localities = tuple(
        path.name for path in sorted((root / HIGH2_MATH_ROOT).iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / "index.html").is_file()
    )
    if len(localities) != EXPECTED_LOCALITIES:
        raise BuildError("boundary preflight cannot derive 371 localities from pinned high2 tree")
    return {
        *(_category_rel(spec) for spec in NEW_SPECS),
        *(_detail_rel(spec, locality) for spec in NEW_SPECS for locality in localities),
    }


def _verify_source_boundaries(plan: BuildPlan) -> None:
    expected_file_hashes = {
        **{f"workbook_{spec.key}": spec.workbook_sha256 for spec in NEW_SPECS},
        "center_csv": CENTER_CSV_SHA256, "target_school_csv": TARGET_SCHOOL_CSV_SHA256,
        "middle_helper": MIDDLE_HELPER_SHA256, "base_helper": BASE_HELPER_SHA256,
        "high2_math_helper": HIGH2_MATH_HELPER_SHA256, "generator": _self_sha256(),
    }
    if set(plan.source_paths) != set(expected_file_hashes):
        raise BuildError("source boundary path key set mismatch")
    for key, path in plan.source_paths.items():
        if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != expected_file_hashes[key]:
            raise BuildError(f"source boundary hash changed: {key}")
    new_paths = _new_html_paths_from_existing(plan.root)
    boundary = _boundary_manifests(plan.root, {}, new_paths)
    if (
        boundary["immutable_sha256"] != plan.immutable_html_manifest_sha256
        or boundary["high2_math_sha256"] != plan.high2_math_manifest_sha256
        or boundary["asset_sha256"] != plan.asset_manifest_sha256
        or boundary["generator_sha256"] != plan.generator_manifest_sha256
    ):
        raise BuildError("boundary manifest differs from materialized plan")
    current_hub = _decode_utf8((plan.root / HIGH2_MATH_HUB_REL).read_bytes(), HIGH2_MATH_HUB_REL.as_posix())
    _hub_style(current_hub)


def _verify_plan_current(plan: BuildPlan) -> None:
    keys = set(plan.authorized_documents)
    if keys != set(plan.before_exists) or keys != set(plan.before_manifest) or keys != set(plan.after_manifest):
        raise BuildError("plan mapping key sets differ")
    if len(keys) != EXPECTED_AUTHORIZED_DOCUMENTS or plan.second_pass_changes:
        raise BuildError("plan authorization/idempotency preflight failed")
    if len(plan.changed_paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("apply/boundary red-read requires the exact initial 1,119-path plan")
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
    _verify_source_boundaries(plan)


def boundary_red_read(plan: BuildPlan) -> Mapping[str, Any]:
    """Re-read every mutable target and frozen source without writing."""

    _verify_plan_current(plan)
    return MappingProxyType({
        "status": "pass", "targets_re_read": len(plan.authorized_documents),
        "source_files_re_read": len(plan.source_paths),
        "immutable_html_manifest_sha256": plan.immutable_html_manifest_sha256,
        "high2_math_manifest_sha256": plan.high2_math_manifest_sha256,
        "asset_manifest_sha256": plan.asset_manifest_sha256,
        "generator_manifest_sha256": plan.generator_manifest_sha256,
    })


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
        _BASE._transaction_apply(plan.root, changed_docs, changed_exists, changed_before, changed_after)
        for rel, expected in plan.after_manifest.items():
            target = _BASE._safe_target(plan.root, rel)
            if not target.is_file() or _sha256(target.read_bytes()) != expected:
                raise BuildError(f"post-transaction target manifest mismatch: {rel}")
        _verify_source_boundaries(plan)
        if len(_BASE._enumerate_html(plan.root, {})) != EXPECTED_FINAL_HTML:
            raise BuildError("post-transaction final HTML count mismatch")
        residue = [path for path in plan.root.iterdir() if path.name.startswith(_BASE.TRANSACTION_PREFIX)]
        if residue:
            raise BuildError(f"transaction residue remains after commit: {residue[:2]}")


def transaction_self_test() -> Mapping[str, str]:
    """Exercise the pinned journal and strict external-freeze gates in temp."""

    results = dict(_BASE.transaction_self_test())
    with tempfile.TemporaryDirectory(prefix="wawa-grade6-high2-security-") as temporary:
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
        if any(path.name.startswith(_BASE.TRANSACTION_PREFIX) for path in root.iterdir()):
            raise BuildError("security synthetics left transaction residue")
        results["invalid_mutation_zero"] = "pass"
    if len(results) < 14 or any(value != "pass" for value in results.values()):
        raise BuildError(f"transaction synthetic suite incomplete: {results}")
    return MappingProxyType(results)


def _default_paths() -> tuple[Path, Mapping[str, Path], Path]:
    root = Path(__file__).resolve().parents[1]
    desktop = Path.home() / "Desktop"
    workbooks = {
        "elementary6_math": desktop / "초6 수학학원.xlsx",
        "elementary6_english": desktop / "초6 영어학원.xlsx",
        "high2_english": desktop / "고2 영어학원.xlsx",
    }
    common = desktop / "홈페이지 정리" / "참고자료" / "공통자료"
    return root, MappingProxyType(workbooks), common


def _parse_cli_workbooks(values: Sequence[str], defaults: Mapping[str, Path]) -> Mapping[str, Path]:
    if not values:
        return defaults
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise BuildError("--workbook must use CATEGORY=PATH")
        key, raw_path = value.split("=", 1)
        if not key or not raw_path or key in parsed:
            raise BuildError(f"malformed/duplicate --workbook: {value}")
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
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _plan_report(
    plan: BuildPlan, mode: str, synthetics: Mapping[str, str] | None,
    boundary: Mapping[str, Any] | None, freeze_path: Path | None,
) -> Mapping[str, Any]:
    return {
        "mode": mode, "write_performed": mode == "applied", "root": str(plan.root),
        "generator_sha256": _self_sha256(), "candidate_sha256": plan.candidate_sha256,
        "source_manifest": dict(plan.source_manifest), "changed_paths": len(plan.changed_paths),
        "second_pass_changes": len(plan.second_pass_changes), "source_metrics": dict(plan.source_metrics),
        "before_metrics": dict(plan.before_metrics), "after_metrics": dict(plan.after_metrics),
        "transaction_self_test": dict(synthetics) if synthetics else None,
        "boundary_red_read": dict(boundary) if boundary else None,
        "freeze_output": str(freeze_path) if freeze_path else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    default_root, default_workbooks, default_common = _default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--common-dir", type=Path, default=default_common)
    parser.add_argument("--workbook", action="append", default=[], metavar="CATEGORY=PATH")
    parser.add_argument("--transaction-self-test", action="store_true")
    parser.add_argument("--boundary-red-read", action="store_true")
    parser.add_argument("--freeze-out", type=Path)
    parser.add_argument("--freeze-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--go", default="")
    args = parser.parse_args(argv)
    try:
        workbooks = _parse_cli_workbooks(args.workbook, default_workbooks)
        synthetics = transaction_self_test() if args.transaction_self_test else None
        plan = build_plan(args.root, workbooks, args.common_dir)
        boundary = boundary_red_read(plan) if args.boundary_red_read else None
        freeze_path: Path | None = None
        if args.apply:
            if args.freeze_out is not None:
                raise BuildError("--freeze-out cannot be combined with --apply")
            if args.freeze_file is None:
                raise BuildError("--apply requires --freeze-file")
            apply_plan(plan, go=args.go, frozen=_read_freeze_file(args.freeze_file))
            mode = "applied"
        else:
            if args.go or args.freeze_file is not None:
                raise BuildError("--go/--freeze-file are valid only with --apply")
            if args.freeze_out is not None:
                _write_freeze_file(args.freeze_out, freeze_payload(plan))
                freeze_path = args.freeze_out.resolve()
            mode = "dry-run/no-edit"
        print(json.dumps(_plan_report(plan, mode, synthetics, boundary, freeze_path), ensure_ascii=False, indent=2))
        return 0
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
