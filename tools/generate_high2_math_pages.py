#!/usr/bin/env python3
"""Build the wawa-center.kr high-school grade 2 mathematics directory.

The attached XLSX is immutable content data.  Formulae, macros, hyperlinks and
embedded instructions are never executed.  A normal invocation materializes
and audits the complete 375-document plan in memory and writes nothing.  An
apply requires an exact external freeze file plus the literal ``APPLY-GO``
token and uses the already-audited recoverable transaction journal.
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
WORKBOOK_SHA256 = "ecb016f9ba0ae4abc7a2cd4032c3837168ad74f81885bdaa3e6ea3139adf5f68"
WORKBOOK_CELL_MANIFEST_SHA256 = "58b81c3fb5caff3fc6269cb13583fa91ae864fc5abf646999564fc9bf06d8d81"
WORKBOOK_SEQUENCE_SHA256 = "8dbb6437d751e4d6e98b7c10b7c5ac284ea180c224a0cfca18b7186f249e9fb1"
WORKBOOK_MAPPING_SHA256 = "ed72bcf9d04072cc4be04efc4e1cd5d2c7f466751bad4d51fb0313a2a7e36380"
CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
TARGET_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"

EXPECTED_LOCALITIES = 371
EXPECTED_EXISTING_HTML = 16_857
EXPECTED_IMMUTABLE_HTML = 16_856
EXPECTED_NEW_HTML = 372
EXPECTED_AUTHORIZED_DOCUMENTS = 375
EXPECTED_FINAL_HTML = 17_229
EXPECTED_SUPPORTED = 325
EXPECTED_UNCONFIRMED = 46
EXPECTED_HIGH_SCHOOL_CHIPS = 909
EXPECTED_MISSING_HIGH_SCHOOL_ROWS = 63
EXPECTED_SOURCE_H2 = 2_441
EXPECTED_SOURCE_PARAGRAPHS = 7_064
EXPECTED_SOURCE_FAQ = 1_996
EXPECTED_SOURCE_REVIEW_BLOCKS = 895
EXPECTED_SOURCE_SUMMARY_PARAGRAPHS = 373

BASE_IMMUTABLE_HTML_MANIFEST_SHA256 = "5584c365f755b711a4f01e6faaa32e2878d25fc4ef1112b2dbe2752f5b0726b7"
BASE_MIDDLE3_MATH_MANIFEST_SHA256 = "81cb8ed8492eacd3e6a2a95568452f50c5067957dde6b99cc872ae61053f0765"
BASE_PARENT_SHA256 = "c8ed1f93cca3dfbdc32a8da514adffea19a54b63214b6ea081f113a306b6219a"
BASE_SITEMAP_SHA256 = "eca96c125207b09e4d5f3c8f8c6d3bb004546fee9a62bb6b2af28bc644874de7"
BASE_LLMS_SHA256 = "4963fb2ce46260f30232e518df78aa09a206011b42f7ec8d85b7ef9a7c5d7111"

PARENT_REL = Path("학년별학원/index.html")
CATEGORY_REL = Path("학년별학원/고2수학학원/index.html")
CATEGORY_ROOT = Path("학년별학원/고2수학학원")
MIDDLE3_MATH_ROOT = Path("학년별학원/중3수학학원")
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
LLMS_MARKER = "## 학년별학원 핵심 허브"
ABSENT_SHA256 = hashlib.sha256(b"wawa-grade3-math:absent-v1").hexdigest()
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
LABELS = ("페이지타이틀", "메타설명", "본문", "FAQ", "학부모후기", "JSON-LD 요약")
LABEL_RE = re.compile(r"(?m)^\[([^\]\n]+)\][ \t]*\n")
MARKDOWN_H2_RE = re.compile(r"(?m)^##[ \t]+([^\n]+?)[ \t]*$")
QUESTION_RE = re.compile(r"(?m)^(Q(?:[1-9][0-9]*)?\.)[ \t]+(.+?)[ \t]*$")
ANSWER_RE = re.compile(r"^(A(?:[1-9][0-9]*)?\.)[ \t]+(.+)$", re.DOTALL)
SIMPLE_TITLE_RE = re.compile(r"^(.+?) 고2 수학학원")
RAW_URL_RE = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD_RE = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)

XLSX_PARTS = frozenset({
    "[Content_Types].xml", "_rels/.rels", "docProps/app.xml", "docProps/core.xml",
    "xl/_rels/workbook.xml.rels", "xl/sharedStrings.xml", "xl/styles.xml",
    "xl/theme/theme1.xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml",
})
XML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

SANBON_HEADINGS = (
    "고2 수학에서 먼저 점검해야 할 부분",
    "산본 생활권 학생에게 필요한 학교별 내신 준비",
    "개념 이해와 응용력의 간격 줄이기",
    "내신과 수능을 따로 보지 않는 학습 설계",
    "학습결과를 확인하는 관리 방식",
    "산본동에서 상담을 받을 때 확인할 내용",
)
SPECIAL_HEADING_ROWS = MappingProxyType({"산본동": 78, "수창동": 300, "달동": 304, "단구동": 360})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_middle_helper() -> ModuleType:
    path = Path(__file__).with_name("generate_middle_grade_pages.py")
    digest = _sha256(path.read_bytes())
    if digest != MIDDLE_HELPER_SHA256:
        raise RuntimeError(f"middle helper SHA-256 mismatch: {digest}")
    name = f"_wawa_middle_{MIDDLE_HELPER_SHA256[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned middle-grade helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if module.BASE_HELPER_SHA256 != BASE_HELPER_SHA256:
        raise RuntimeError("nested base-helper contract mismatch")
    return module


_MID = _load_middle_helper()
_BASE = _MID._BASE
BuildError = _MID.BuildError
ABSENT_SHA256 = _BASE.ABSENT_SHA256


@dataclass(frozen=True)
class HighSpec:
    key: str = "high2_math"
    grade: str = "고2"
    grade_number: int = 2
    subject: str = "수학"
    slug: str = "고2수학학원"
    hook: str = "high2-math"
    subject_slug: str = "수학학원"
    grade_attr: str = "math_grades"
    card_copy: str = "고2 수학의 학교별 내신 범위, 수능 기초, 취약 단원과 오답 관리 기준을 동네별 원고에서 확인합니다."

    @property
    def label(self) -> str:
        return "고2 수학학원"

    @property
    def grades_label(self) -> str:
        return "수학 가능 학년"

    @property
    def guide_slug(self) -> str:
        return "수학-공부법"

    @property
    def english_label(self) -> str:
        return "HIGH SCHOOL GRADE 2 MATH"


SPEC = HighSpec()
ALL_CATEGORIES = tuple(_MID.ALL_CATEGORIES) + (SPEC,)


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


def _decode_utf8(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label}: not strict UTF-8") from exc


def _escape(value: Any) -> str:
    return _BASE._escape(str(value))


def _site_url(*parts: str) -> str:
    return _BASE._encoded_site_url(*parts)


def _detail_rel(locality: str) -> Path:
    return CATEGORY_ROOT / locality / "index.html"


def _generic_math_rel(locality: str) -> Path:
    return Path("과목별학원/수학학원") / locality / "index.html"


def _split_paragraphs(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(block.strip() for block in re.split(r"\n[ \t]*\n", value) if block.strip())


def _replace_once(value: str, old: str, new: str, label: str) -> str:
    if value.count(old) != 1:
        raise BuildError(f"{label}: expected one replacement target, got {value.count(old)}")
    return value.replace(old, new, 1)


def _xlsx_cells(path: Path) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise BuildError(f"workbook must be a regular non-symlink file: {path}")
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != WORKBOOK_SHA256:
        raise BuildError(f"workbook SHA-256 mismatch: {digest}")
    with ZipFile(io.BytesIO(raw), "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != XLSX_PARTS:
            raise BuildError("workbook package part set differs from frozen data-only contract")
        for info in infos:
            path_parts = Path(info.filename).parts
            if (
                info.is_dir() or info.flag_bits & 0x1 or info.filename.startswith(("/", "\\"))
                or ".." in path_parts or CONTROL_RE.search(info.filename)
                or info.file_size < 0 or info.file_size > 8_000_000
                or (info.compress_size and info.file_size / info.compress_size > 150)
            ):
                raise BuildError(f"unsafe/encrypted/suspicious workbook part: {info.filename!r}")
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        if "macroEnabled" in content_types or "vbaProject" in content_types or "externalLink" in content_types:
            raise BuildError("workbook contains executable or external-link content type")

    sheets = workbook_root.findall(f".//{{{XML_NS}}}sheet")
    if len(sheets) != 1 or sheets[0].get("name") != "Sheet1" or sheets[0].get("state", "visible") != "visible":
        raise BuildError("workbook must contain exactly one visible Sheet1")
    relationship_id = sheets[0].get(f"{{{REL_NS}}}id")
    relationships = {
        node.get("Id"): (node.get("Type", ""), node.get("Target", ""), node.get("TargetMode", ""))
        for node in rels_root
    }
    if relationship_id not in relationships or relationships[relationship_id][1] != "worksheets/sheet1.xml":
        raise BuildError("Sheet1 relationship target mismatch")
    if any(mode == "External" for _, _, mode in relationships.values()):
        raise BuildError("external workbook relationship is forbidden")

    shared_nodes = shared_root.findall(f"{{{XML_NS}}}si")
    if shared_root.get("count") != "371" or shared_root.get("uniqueCount") != "371" or len(shared_nodes) != EXPECTED_LOCALITIES:
        raise BuildError("shared-string count mismatch")
    shared: list[str] = []
    for index, node in enumerate(shared_nodes, 1):
        if node.find(f".//{{{XML_NS}}}f") is not None:
            raise BuildError(f"shared string {index}: formula node forbidden")
        value = "".join(part.text or "" for part in node.findall(f".//{{{XML_NS}}}t"))
        if not value or CONTROL_RE.search(value):
            raise BuildError(f"shared string {index}: empty/control content")
        shared.append(value)

    if sheet_root.findall(f".//{{{XML_NS}}}f"):
        raise BuildError("worksheet formula is forbidden")
    if sheet_root.findall(f".//{{{XML_NS}}}hyperlink") or sheet_root.findall(f".//{{{XML_NS}}}mergeCell"):
        raise BuildError("worksheet hyperlink/merge is outside frozen data contract")
    dimension = sheet_root.find(f"{{{XML_NS}}}dimension")
    if dimension is None or dimension.get("ref") != "A1:A371":
        raise BuildError("worksheet dimension must be A1:A371")
    rows = sheet_root.findall(f".//{{{XML_NS}}}sheetData/{{{XML_NS}}}row")
    if len(rows) != EXPECTED_LOCALITIES:
        raise BuildError("worksheet row count mismatch")
    cells: list[str] = []
    mapping = hashlib.sha256()
    for row_number, row in enumerate(rows, 1):
        cell_nodes = row.findall(f"{{{XML_NS}}}c")
        if row.get("r") != str(row_number) or len(cell_nodes) != 1:
            raise BuildError(f"Sheet1 row {row_number}: exact one-cell contract failed")
        cell = cell_nodes[0]
        ref = f"A{row_number}"
        value_node = cell.find(f"{{{XML_NS}}}v")
        if cell.get("r") != ref or cell.get("t") != "s" or value_node is None or value_node.text is None:
            raise BuildError(f"{ref}: shared-string cell contract failed")
        try:
            shared_index = int(value_node.text)
        except ValueError as exc:
            raise BuildError(f"{ref}: invalid shared-string index") from exc
        if not 0 <= shared_index < len(shared):
            raise BuildError(f"{ref}: shared-string index out of range")
        cells.append(shared[shared_index])
        mapping.update(f"{ref}\t{shared_index}\n".encode("ascii"))
    if len(set(cells)) != EXPECTED_LOCALITIES:
        raise BuildError("workbook manuscript cells must be exactly unique")
    cell_manifest = hashlib.sha256()
    for index, value in enumerate(cells, 1):
        cell_manifest.update(f"{index}\t{_sha256(value.encode('utf-8'))}\n".encode("ascii"))
    sequence = _sha256(b"\0".join(value.encode("utf-8") for value in cells))
    if cell_manifest.hexdigest() != WORKBOOK_CELL_MANIFEST_SHA256 or sequence != WORKBOOK_SEQUENCE_SHA256 or mapping.hexdigest() != WORKBOOK_MAPPING_SHA256:
        raise BuildError("workbook cell sequence/manifest mapping mismatch")
    return tuple(cells), MappingProxyType({
        "xlsx_bytes": len(raw), "sheets": 1, "cells": len(cells), "unique_cells": len(set(cells)),
        "formula_cells": 0, "hyperlinks": 0, "merged_ranges": 0,
        "cell_manifest_sha256": cell_manifest.hexdigest(), "sequence_sha256": sequence,
        "mapping_sha256": mapping.hexdigest(),
    })


def _heading_tokens(body: str, locality: str, row: int) -> tuple[HeadingToken, ...]:
    expected_special = SPECIAL_HEADING_ROWS.get(locality)
    if expected_special is not None and expected_special != row:
        raise BuildError(f"{locality}: frozen special-heading row mismatch")
    if locality == "산본동":
        allow = set(SANBON_HEADINGS)
        pattern = re.compile(r"(?m)^(" + "|".join(re.escape(value) for value in SANBON_HEADINGS) + r")[ \t]*$")
        matches = tuple(HeadingToken(item.start(), item.end(), item.group(1), "plain-allowlist") for item in pattern.finditer(body))
        if tuple(item.text for item in matches) != SANBON_HEADINGS or set(item.text for item in matches) != allow:
            raise BuildError("산본동: exact plain-heading allowlist mismatch")
        return matches
    if locality in ("수창동", "단구동"):
        pattern = re.compile(r"(?m)^<h2>([^<\n]+)</h2>[ \t]*$")
        matches = tuple(HeadingToken(item.start(), item.end(), item.group(1), "literal-h2-tag") for item in pattern.finditer(body))
        if len(matches) != 6:
            raise BuildError(f"{locality}: exact literal <h2> count mismatch")
        return matches
    if locality == "달동":
        pattern = re.compile(r"(?m)^H2\.[ \t]+(.+?)[ \t]*$")
        matches = tuple(HeadingToken(item.start(), item.end(), item.group(1), "literal-h2-prefix") for item in pattern.finditer(body))
        if len(matches) != 7:
            raise BuildError("달동: exact H2. heading count mismatch")
        return matches
    if expected_special is not None:
        raise BuildError(f"{locality}: unsupported special heading contract")
    matches = tuple(HeadingToken(item.start(), item.end(), item.group(1).strip(), "markdown-h2") for item in MARKDOWN_H2_RE.finditer(body))
    if not matches or len(re.findall(r"(?m)^#{1,6}[ \t]+", body)) != len(matches):
        raise BuildError(f"{locality}: only source markdown H2 headings are permitted")
    return matches


def _parse_manuscript(row: int, source: str) -> Manuscript:
    if unicodedata.normalize("NFC", source) != source:
        raise BuildError(f"Sheet1!A{row}: non-NFC manuscript")
    if CONTROL_RE.search(source):
        raise BuildError(f"Sheet1!A{row}: forbidden control character")
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(LABEL_RE.finditer(text))
    if tuple(match.group(1) for match in matches) != LABELS:
        raise BuildError(f"Sheet1!A{row}: section labels/order malformed")
    if text[:matches[0].start()].strip():
        raise BuildError(f"Sheet1!A{row}: content before first marker")
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        values[match.group(1)] = text[match.end():end].strip("\n")
    if any(not values[label].strip() for label in LABELS):
        raise BuildError(f"Sheet1!A{row}: empty required section")
    title = values["페이지타이틀"].strip()
    title_match = SIMPLE_TITLE_RE.match(title)
    if title_match is None:
        raise BuildError(f"Sheet1!A{row}: title must begin with locality and 고2 수학학원")
    locality = title_match.group(1).strip()
    meta = values["메타설명"].strip()
    if "\n" in meta:
        raise BuildError(f"Sheet1!A{row}: meta description must remain one line")
    body = values["본문"].strip()
    headings = _heading_tokens(body, locality, row)
    intro = _split_paragraphs(body[:headings[0].start])
    sections: list[BodySection] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start if index + 1 < len(headings) else len(body)
        paragraphs = _split_paragraphs(body[heading.end:end])
        if not heading.text or not paragraphs:
            raise BuildError(f"Sheet1!A{row}: empty source H2/body")
        sections.append(BodySection(heading.text, paragraphs))

    faq_value = values["FAQ"].strip()
    question_matches = list(QUESTION_RE.finditer(faq_value))
    if len(question_matches) not in (5, 6):
        raise BuildError(f"Sheet1!A{row}: expected five or six FAQ questions")
    faqs: list[FAQ] = []
    for index, question in enumerate(question_matches, 1):
        end = question_matches[index].start() if index < len(question_matches) else len(faq_value)
        answer_block = faq_value[question.end():end].strip()
        answer_match = ANSWER_RE.fullmatch(answer_block)
        if answer_match is None:
            if locality != "다산신도시" or len(question_matches) != 5:
                raise BuildError(f"Sheet1!A{row}: unprefixed FAQ answer outside exact allowlist")
            answer_prefix, answer = "", answer_block
        else:
            answer_prefix, answer = answer_match.group(1), answer_match.group(2).strip()
        if not answer:
            raise BuildError(f"Sheet1!A{row}: empty FAQ answer")
        faqs.append(FAQ(index, question.group(2).strip(), answer, question.group(1), answer_prefix))
    review_blocks = _split_paragraphs(values["학부모후기"].strip())
    if not 1 <= len(review_blocks) <= 4:
        raise BuildError(f"Sheet1!A{row}: review block count outside frozen range")
    summary = values["JSON-LD 요약"].strip()
    return Manuscript(
        member_name=f"Sheet1!A{row}", workbook_row=row, locality=locality, title=title,
        meta_description=meta, intro_paragraphs=intro, sections=tuple(sections),
        faqs=tuple(faqs), review_lines=review_blocks, jsonld_summary=summary,
        raw_bytes=source.encode("utf-8"), raw_text=source, cell_sha256=_sha256(source.encode("utf-8")),
    )


def _load_manuscripts(workbook_path: Path) -> tuple[Mapping[str, Manuscript], Mapping[str, Any]]:
    cells, workbook_metrics = _xlsx_cells(workbook_path)
    manuscripts: dict[str, Manuscript] = {}
    for row, source in enumerate(cells, 1):
        manuscript = _parse_manuscript(row, source)
        if manuscript.locality in manuscripts:
            raise BuildError(f"duplicate workbook locality: {manuscript.locality}")
        manuscripts[manuscript.locality] = manuscript
    h2_distribution = Counter(len(value.sections) for value in manuscripts.values())
    faq_distribution = Counter(len(value.faqs) for value in manuscripts.values())
    intro_distribution = Counter(len(value.intro_paragraphs) for value in manuscripts.values())
    paragraph_total = sum(len(value.intro_paragraphs) + sum(len(section.paragraphs) for section in value.sections) for value in manuscripts.values())
    reviews = sum(len(value.review_lines) for value in manuscripts.values())
    summary_paragraphs = sum(len(_split_paragraphs(value.jsonld_summary)) for value in manuscripts.values())
    if (
        len(manuscripts) != EXPECTED_LOCALITIES
        or h2_distribution != Counter({6: 157, 7: 213, 8: 1})
        or sum(key * count for key, count in h2_distribution.items()) != EXPECTED_SOURCE_H2
        or intro_distribution != Counter({0: 27, 1: 313, 2: 31})
        or paragraph_total != EXPECTED_SOURCE_PARAGRAPHS
        or faq_distribution != Counter({5: 230, 6: 141})
        or sum(key * count for key, count in faq_distribution.items()) != EXPECTED_SOURCE_FAQ
        or reviews != EXPECTED_SOURCE_REVIEW_BLOCKS
        or summary_paragraphs != EXPECTED_SOURCE_SUMMARY_PARAGRAPHS
    ):
        raise BuildError("frozen workbook manuscript structural metrics mismatch")
    metrics = {
        **dict(workbook_metrics), "manuscripts": len(manuscripts),
        "title_exact": sum(value.title == f"{value.locality} 고2 수학학원" for value in manuscripts.values()),
        "title_extended": sum(value.title != f"{value.locality} 고2 수학학원" for value in manuscripts.values()),
        "source_h2": EXPECTED_SOURCE_H2, "h2_distribution": dict(sorted(h2_distribution.items())),
        "source_body_paragraphs": paragraph_total, "intro_distribution": dict(sorted(intro_distribution.items())),
        "source_faq": EXPECTED_SOURCE_FAQ, "faq_distribution": dict(sorted(faq_distribution.items())),
        "source_review_blocks": reviews, "source_summary_paragraphs": summary_paragraphs,
        "unprefixed_faq_answers": sum(not faq.answer_prefix for value in manuscripts.values() for faq in value.faqs),
        "visible_manuscript_corrections": 0,
    }
    return MappingProxyType(manuscripts), MappingProxyType(metrics)


def _proxy_high_schools(record: Any) -> Any:
    return replace(
        record, middle_schools=tuple(record.high_schools),
        middle_school_source_tokens=tuple(record.high_schools),
    )


def _call_middle_with_exact_high_schools(function: Any, *args: Any) -> Any:
    """Run one inherited renderer/validator with identity school semantics.

    The middle-grade helper contains one locality-scoped correction for a
    malformed middle-school token.  High-school source chips are a different
    authoritative field and must never pass through that correction.
    """
    previous = _MID._visible_schools

    def exact(record: Any) -> tuple[str, ...]:
        values = tuple(record.middle_schools)
        if len(values) != len(set(values)):
            raise BuildError(f"{record.locality}: duplicate authoritative high-school chip")
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


def _render_parent_hub() -> str:
    old_description = "중1·중2·중3 수학학원과 영어학원 6개 분류에서 학년별 진단, 학교 자료, 복습과 상담 기준을 371개 지역별로 확인하세요."
    description = "중1·중2·중3 영어·수학과 고2 수학 7개 분류에서 학년별 진단, 학교 자료, 복습과 상담 기준을 371개 지역별로 확인하세요."
    old_answer = "중학교 1·2·3학년의 수학과 영어 안내를 각 371개 동네별로 제공합니다."
    answer = "중학교 1·2·3학년의 수학·영어와 고등학교 2학년 수학 안내를 각 371개 동네별로 제공합니다."
    old_section = "중1·중2·중3 수학과 영어 6개 분류에서 각 371개 지역 원고를 제공합니다."
    section = "중1·중2·중3 수학·영어와 고2 수학 7개 분류에서 각 371개 지역 원고를 제공합니다."
    document = _MID._render_parent_hub()
    for old, new, label in ((old_description, description, "description"), (old_answer, answer, "FAQ answer"), (old_section, section, "category count")):
        if old not in document:
            raise BuildError(f"grade parent: baseline {label} text missing")
        document = document.replace(old, new)
    card = (
        f'<a class="subject-category-card" data-number="07" href="/학년별학원/{SPEC.slug}/">'
        f'<small>{SPEC.english_label}</small><h3>{_escape(SPEC.label)}</h3><p>{_escape(SPEC.card_copy)}</p>'
        '<span class="subject-status">371개 지역 안내 보기 →</span></a>'
    )
    grid_end = '</div></div></section>\n    <section class="subject-section"><div class="subject-container"><div class="subject-section-head"><p class="subject-kicker">HOW TO USE</p>'
    document = _replace_once(document, grid_end, card + grid_end, "grade parent category grid")

    def mutate(value: dict[str, Any]) -> None:
        graph = value.get("@graph")
        if not isinstance(graph, list):
            raise BuildError("grade parent: JSON-LD graph missing")
        organization = _find_node(graph, "EducationalOrganization", "grade parent")
        knows = organization.get("knowsAbout")
        if not isinstance(knows, list) or SPEC.label in knows:
            raise BuildError("grade parent: organization category baseline mismatch")
        knows.append(SPEC.label)
        page = _find_node(graph, "CollectionPage", "grade parent")
        page["description"] = description
        page["dateModified"] = PUBLISHED_DATE
        about = page.get("about")
        if not isinstance(about, list):
            raise BuildError("grade parent: about missing")
        about.append({"@type": "Thing", "name": "고등학교 수학"})
        has_part = page.get("hasPart")
        if not isinstance(has_part, list) or len(has_part) != 6:
            raise BuildError("grade parent: existing hasPart baseline mismatch")
        has_part.append({"@type": "CollectionPage", "name": SPEC.label, "url": _site_url("학년별학원", SPEC.slug)})
        item_list = _find_node(graph, "ItemList", "grade parent")
        items = item_list.get("itemListElement")
        if item_list.get("numberOfItems") != 6 or not isinstance(items, list) or len(items) != 6:
            raise BuildError("grade parent: existing ItemList baseline mismatch")
        item_list["numberOfItems"] = 7
        items.append({"@type": "ListItem", "position": 7, "name": SPEC.label, "url": _site_url("학년별학원", SPEC.slug)})
        faq = _find_node(graph, "FAQPage", "grade parent")
        entities = faq.get("mainEntity")
        if not isinstance(entities, list) or len(entities) != 2:
            raise BuildError("grade parent: FAQ baseline mismatch")
        entities[1]["acceptedAnswer"]["text"] = answer

    return _MID._clean_document(_mutate_jsonld(document, "grade parent", mutate))


def _render_category_hub(center_order: Sequence[str], centers: Mapping[str, Any]) -> str:
    document = _MID._render_category_hub(SPEC, center_order, centers)
    document = document.replace("중학교명이 없는 경우", "고등학교명이 없는 경우")

    def mutate(value: dict[str, Any]) -> None:
        graph = value.get("@graph")
        if not isinstance(graph, list):
            raise BuildError("high2 category: JSON-LD graph missing")
        organization = _find_node(graph, "EducationalOrganization", "high2 category")
        knows = organization.get("knowsAbout")
        if not isinstance(knows, list):
            raise BuildError("high2 category: knowsAbout missing")
        if SPEC.label not in knows:
            knows.append(SPEC.label)
        for node in graph:
            if isinstance(node, dict):
                if "datePublished" in node:
                    node["datePublished"] = PUBLISHED_DATE
                if "dateModified" in node:
                    node["dateModified"] = PUBLISHED_DATE

    return _MID._clean_document(_mutate_jsonld(document, "high2 category", mutate))


def _render_detail(manuscript: Manuscript, record: Any, assets: Any, previous_locality: str, next_locality: str) -> str:
    proxy = _proxy_high_schools(record)
    document = _call_middle_with_exact_high_schools(
        _MID._render_detail, SPEC, manuscript, proxy, assets, previous_locality, next_locality,
    )
    document = _replace_once(document, 'data-source-field="middle-schools"', 'data-source-field="high-schools"', manuscript.member_name)
    document = document.replace("원자료에 중학교명이 기재되지 않아", "원자료에 고등학교명이 기재되지 않아")
    article_tag = '<article class="math-narrow math-article" data-manuscript>'
    enriched_tag = (
        f'<article class="math-narrow math-article" data-source-workbook-row="{manuscript.workbook_row}" '
        f'data-source-cell-sha256="{manuscript.cell_sha256}" data-manuscript-sha256="{manuscript.cell_sha256}" data-manuscript>'
    )
    document = _replace_once(document, article_tag, enriched_tag, manuscript.member_name)
    document = _replace_once(document, 'math-faq-card" data-faq>', 'math-faq-card" data-manuscript-faq data-faq>', manuscript.member_name)
    document = _replace_once(document, 'math-review-card" data-review>', 'math-review-card" data-manuscript-review data-review>', manuscript.member_name)
    document, heading_replacements = re.subn(
        r'(<section id="section-[0-9]{2}" class="math-prose-section" data-manuscript-section="[0-9]{2}">\n[ \t]*)<h2>',
        r'\1<h2 data-source-heading>', document,
    )
    if heading_replacements != len(manuscript.sections):
        raise BuildError(f"{manuscript.member_name}: source heading hook cardinality mismatch")
    document = re.sub(
        r'(<p data-manuscript-paragraph="[^"]+" data-source-sha256="[0-9a-f]{64}")>',
        r'\1 data-source-paragraph>', document,
    )
    for faq in manuscript.faqs:
        old_question = f"<summary><span>Q{faq.number}.</span> {_escape(faq.question)}</summary>"
        new_question = f"<summary data-source-question><span>{_escape(faq.question_prefix)}</span> {_escape(faq.question)}</summary>"
        document = _replace_once(document, old_question, new_question, f"{manuscript.member_name} FAQ question {faq.number}")
        old_answer = f"<p><strong>A.</strong> {_MID._paragraph_markup(faq.answer)}</p>"
        prefix = f"<strong>{_escape(faq.answer_prefix)}</strong> " if faq.answer_prefix else ""
        new_answer = f"<p data-source-answer>{prefix}{_MID._paragraph_markup(faq.answer)}</p>"
        document = _replace_once(document, old_answer, new_answer, f"{manuscript.member_name} FAQ answer {faq.number}")

    def mutate(value: dict[str, Any]) -> None:
        graph = value.get("@graph")
        if not isinstance(graph, list):
            raise BuildError(f"{manuscript.member_name}: JSON-LD graph missing")
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
                if not isinstance(audience, dict) or audience.get("audienceType") != "중학교 2학년(고2)":
                    raise BuildError(f"{manuscript.member_name}: inherited audience baseline mismatch")
                audience["audienceType"] = "고등학교 2학년(고2)"

    return _MID._clean_document(_mutate_jsonld(document, manuscript.member_name, mutate))


def _validate_parent(document: str) -> None:
    audit = _BASE._audit_html(document, "grade parent hub")
    _BASE._validate_nav(document, "grade parent hub", grade_active=True)
    mains = [attrs for tag, attrs in audit.start_tags if tag == "main" and attrs.get("data-grade-directory") == "parent"]
    if len(mains) != 1:
        raise BuildError("grade parent: main hook mismatch")
    canonical = _site_url("학년별학원")
    if _BASE._canonical_values(document) != [canonical] or _BASE._meta_values(document, property_name="og:url") != [canonical]:
        raise BuildError("grade parent: canonical/og:url mismatch")
    for index, spec in enumerate(ALL_CATEGORIES, 1):
        if document.count(f'data-number="{index:02d}" href="/학년별학원/{spec.slug}/"') != 1:
            raise BuildError(f"grade parent: category card mismatch: {spec.key}")
    jsonld, _ = _BASE._extract_jsonld_graph(document, "grade parent hub")
    item_list = _find_node(jsonld["@graph"], "ItemList", "grade parent hub")
    page = _find_node(jsonld["@graph"], "CollectionPage", "grade parent hub")
    if item_list.get("numberOfItems") != 7 or len(item_list.get("itemListElement", [])) != 7 or len(page.get("hasPart", [])) != 7:
        raise BuildError("grade parent: seven-category schema mismatch")


def _validate_detail(document: str, manuscript: Manuscript, record: Any, assets: Any) -> None:
    label = f"high2_math/{manuscript.member_name}"
    if document.count('data-source-field="high-schools"') != 1 or 'data-source-field="middle-schools"' in document:
        raise BuildError(f"{label}: high-school fact hook mismatch")
    if document.count(f'data-source-workbook-row="{manuscript.workbook_row}"') != 1 or document.count(f'data-source-cell-sha256="{manuscript.cell_sha256}"') != 1:
        raise BuildError(f"{label}: workbook source identity hook mismatch")
    proxy = _proxy_high_schools(record)
    compatibility = document.replace('data-source-field="high-schools"', 'data-source-field="middle-schools"')
    compatibility = compatibility.replace(" data-source-heading", "").replace(" data-source-paragraph", "")
    compatibility = compatibility.replace(" data-source-question", "").replace(" data-source-answer", "")
    _call_middle_with_exact_high_schools(_MID._validate_detail, SPEC, compatibility, manuscript, proxy, assets)
    jsonld, _ = _BASE._extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    types = _BASE._schema_types(graph)
    if "고2" in record.math_grades:
        service = _find_node(graph, "Service", label)
        audience = service.get("audience")
        if not isinstance(audience, dict) or audience.get("audienceType") != "고등학교 2학년(고2)":
            raise BuildError(f"{label}: high-school audience mismatch")
    elif types["Service"] or types["Offer"]:
        raise BuildError(f"{label}: unconfirmed page contains Service/Offer")
    high_schools = tuple(record.high_schools)
    visible = tuple(html.unescape(value) for value in re.findall(r"<span data-source-school>(.*?)</span>", document, re.DOTALL))
    if visible != high_schools:
        raise BuildError(f"{label}: visible high-school/common-source mismatch")
    for faq in manuscript.faqs:
        block_match = re.search(
            rf'<details class="math-faq-item" data-source-faq="{faq.number:02d}"[^>]*>(.*?)</details>',
            document, re.DOTALL,
        )
        if block_match is None:
            raise BuildError(f"{label}: FAQ block missing {faq.number}")
        block = block_match.group(1)
        question_prefix = re.search(r"<summary data-source-question><span>(.*?)</span>", block, re.DOTALL)
        answer_prefix = re.search(r"<p data-source-answer>(?:<strong>(.*?)</strong> )?", block, re.DOTALL)
        if question_prefix is None or html.unescape(question_prefix.group(1)) != faq.question_prefix:
            raise BuildError(f"{label}: exact FAQ question prefix changed")
        rendered_answer_prefix = html.unescape(answer_prefix.group(1)) if answer_prefix and answer_prefix.group(1) is not None else ""
        if rendered_answer_prefix != faq.answer_prefix:
            raise BuildError(f"{label}: exact FAQ answer prefix changed")
    if _BASE._meta_values(document, name="description") != [manuscript.meta_description]:
        raise BuildError(f"{label}: exact manuscript meta changed")
    h1 = re.search(r"<h1>(.*?)</h1>", document, re.DOTALL)
    if h1 is None or html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))) != manuscript.title:
        raise BuildError(f"{label}: exact manuscript H1 changed")


def _sitemap_urls(center_order: Sequence[str]) -> tuple[str, ...]:
    return (_site_url("학년별학원", SPEC.slug), *(_site_url("학년별학원", SPEC.slug, locality) for locality in center_order))


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
        raise BuildError("sitemap.xml: partial/conflicting high2 URL set")
    if tuple(location for location, _, _ in blocks[-EXPECTED_NEW_HTML:]) != new_urls:
        raise BuildError("sitemap.xml: high2 URLs are not the exact final ordered block")
    if any(lastmod != PUBLISHED_DATE for _, lastmod, _ in blocks[-EXPECTED_NEW_HTML:]):
        raise BuildError("sitemap.xml: high2 lastmod mismatch")
    return document


def _llms_block() -> str:
    lines = [
        LLMS_MARKER, "",
        f"- 학년별학원: {SITE_ORIGIN}/학년별학원/",
        "  - 중1·중2·중3 영어·수학과 고2 수학 지역 안내를 학년과 과목별로 찾는 핵심 허브입니다.",
    ]
    for spec in ALL_CATEGORIES:
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


def build_plan(
    root: Path | str,
    workbook_path: Path | str,
    common_dir: Path | str,
    current_overrides: Mapping[Path | str, str | bytes] | None = None,
) -> BuildPlan:
    """Materialize and audit the exact sparse 375-document release plan."""

    root = Path(root).resolve()
    workbook_input = Path(workbook_path).expanduser()
    if workbook_input.is_symlink() or not workbook_input.is_file():
        raise BuildError(f"workbook must be a regular non-symlink file: {workbook_input}")
    workbook_path = workbook_input.resolve()
    common_dir = Path(common_dir).resolve()
    if not root.is_dir() or not common_dir.is_dir():
        raise BuildError("root and common data directory must already exist")
    pending = [path for path in root.iterdir() if path.is_dir() and path.name.startswith(_BASE.TRANSACTION_PREFIX)]
    if pending:
        raise BuildError("pending transaction detected")
    overrides = _BASE._normalize_overrides(root, current_overrides)
    centers, center_metrics = _BASE._load_centers(common_dir)
    center_order = tuple(centers)
    manuscripts, manuscript_metrics = _load_manuscripts(workbook_path)
    if center_order != tuple(manuscripts):
        raise BuildError("workbook row/locality order must exactly match authoritative center CSV")

    new_html_paths = {CATEGORY_REL, *(_detail_rel(locality) for locality in center_order)}
    authorized_paths = {PARENT_REL, SITEMAP_REL, LLMS_REL, *new_html_paths}
    if len(new_html_paths) != EXPECTED_NEW_HTML or len(authorized_paths) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("authorized sparse path cardinality mismatch")
    unknown_overrides = set(overrides) - authorized_paths
    if unknown_overrides:
        raise BuildError(f"current_overrides contains unauthorized paths: {sorted(map(str, unknown_overrides))[:4]}")

    html_paths = _BASE._enumerate_html(root, overrides)
    present_new = html_paths & new_html_paths
    if present_new and present_new != new_html_paths:
        raise BuildError(f"partial generated high2 tree: {len(present_new)}/{len(new_html_paths)}")
    existing_html_paths = html_paths - new_html_paths
    if len(existing_html_paths) != EXPECTED_EXISTING_HTML or PARENT_REL not in existing_html_paths:
        raise BuildError(f"existing HTML baseline mismatch: {len(existing_html_paths)}")
    immutable_paths = tuple(path for path in existing_html_paths if path != PARENT_REL)
    immutable_manifest = _files_manifest(root, immutable_paths, overrides)
    if len(immutable_paths) != EXPECTED_IMMUTABLE_HTML or immutable_manifest != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        raise BuildError(f"existing parent-excluded HTML drift: {len(immutable_paths)}/{immutable_manifest}")
    middle3_paths = tuple(path for path in immutable_paths if path == MIDDLE3_MATH_ROOT / "index.html" or MIDDLE3_MATH_ROOT in path.parents)
    middle3_manifest = _files_manifest(root, middle3_paths, overrides)
    if len(middle3_paths) != 372 or middle3_manifest != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
        raise BuildError("existing middle3 math tree drift")

    supported = sum("고2" in record.math_grades for record in centers.values())
    unconfirmed = EXPECTED_LOCALITIES - supported
    high_school_chips = sum(len(record.high_schools) for record in centers.values())
    missing_high_school_rows = sum(not record.high_schools for record in centers.values())
    if (supported, unconfirmed, high_school_chips, missing_high_school_rows) != (
        EXPECTED_SUPPORTED, EXPECTED_UNCONFIRMED, EXPECTED_HIGH_SCHOOL_CHIPS, EXPECTED_MISSING_HIGH_SCHOOL_ROWS,
    ):
        raise BuildError("high2 grade/high-school authoritative metrics mismatch")

    assets_by_locality: dict[str, Any] = {}
    representative_sources: set[str] = set()
    body_sources: set[str] = set()
    map_sources: set[str] = set()
    for locality, record in centers.items():
        rel = _generic_math_rel(locality)
        if rel not in existing_html_paths:
            raise BuildError(f"{locality}: generic math source page missing")
        source_document = _decode_utf8(_BASE._read_current_bytes(root, rel, overrides), rel.as_posix())
        assets = _BASE._load_page_assets(root, locality, source_document)
        _MID._crosscheck_physical_source(SPEC, record, assets)
        assets_by_locality[locality] = assets
        representative_sources.add(assets.representative_src)
        body_sources.add(assets.body_src)
        map_sources.add(assets.map_src)

    generated: dict[Path, str] = {PARENT_REL: _render_parent_hub(), CATEGORY_REL: _render_category_hub(center_order, centers)}
    for index, locality in enumerate(center_order):
        generated[_detail_rel(locality)] = _render_detail(
            manuscripts[locality], centers[locality], assets_by_locality[locality],
            center_order[index - 1], center_order[(index + 1) % len(center_order)],
        )
    if len(generated) != EXPECTED_NEW_HTML + 1:
        raise BuildError("generated parent/new HTML count mismatch")

    parent_exists, parent_before = _BASE._read_optional_current_bytes(root, PARENT_REL, overrides)
    if not parent_exists:
        raise BuildError("grade parent hub disappeared")
    if not present_new:
        if _sha256(parent_before) != BASE_PARENT_SHA256:
            raise BuildError("grade parent baseline drift")
    elif parent_before != _as_bytes(generated[PARENT_REL]):
        raise BuildError("complete high2 tree exists with non-canonical parent")
    sitemap_current = _decode_utf8(_BASE._read_current_bytes(root, SITEMAP_REL, overrides), SITEMAP_REL.as_posix())
    llms_current = _decode_utf8(_BASE._read_current_bytes(root, LLMS_REL, overrides), LLMS_REL.as_posix())
    generated[SITEMAP_REL] = _update_sitemap(sitemap_current, center_order)
    generated[LLMS_REL] = _update_llms(llms_current)
    if set(generated) != authorized_paths:
        raise BuildError("materialized sparse set differs from authorization")

    _validate_parent(generated[PARENT_REL])
    _MID._validate_category(SPEC, generated[CATEGORY_REL], center_order)
    for locality in center_order:
        _validate_detail(generated[_detail_rel(locality)], manuscripts[locality], centers[locality], assets_by_locality[locality])
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
        raise BuildError("complete high2 tree has non-canonical sitemap")

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
    if _render_parent_hub() != generated[PARENT_REL] or _render_category_hub(center_order, centers) != generated[CATEGORY_REL]:
        second_pass.append(PARENT_REL)
    for index, locality in enumerate(center_order):
        second = _render_detail(
            manuscripts[locality], centers[locality], assets_by_locality[locality],
            center_order[index - 1], center_order[(index + 1) % len(center_order)],
        )
        if second != generated[_detail_rel(locality)]:
            second_pass.append(_detail_rel(locality))
    if _update_sitemap(generated[SITEMAP_REL], center_order) != generated[SITEMAP_REL]:
        second_pass.append(SITEMAP_REL)
    if _update_llms(generated[LLMS_REL]) != generated[LLMS_REL]:
        second_pass.append(LLMS_REL)
    if second_pass:
        raise BuildError(f"second-pass idempotency failed: {len(second_pass)}")

    source_manifest = {
        "workbook": WORKBOOK_SHA256, "workbook_cells": WORKBOOK_CELL_MANIFEST_SHA256,
        "center_csv": CENTER_CSV_SHA256, "target_school_csv": TARGET_SCHOOL_CSV_SHA256,
        "middle_helper": MIDDLE_HELPER_SHA256, "base_helper": BASE_HELPER_SHA256,
    }
    source_metrics = {
        **dict(manuscript_metrics), **dict(center_metrics),
        "supported_pages": supported, "unconfirmed_pages": unconfirmed,
        "high_school_chips": high_school_chips, "missing_high_school_rows": missing_high_school_rows,
        "exact_address_in_manuscript_pages": sum(record.address in manuscripts[locality].raw_text for locality, record in centers.items()),
        "manuscript_visible_high_school_pairs": sum(
            school in manuscripts[locality].raw_text for locality, record in centers.items() for school in record.high_schools
        ),
        "representative_sources": len(representative_sources), "body_sources": len(body_sources), "map_sources": len(map_sources),
    }
    before_metrics = {
        "html_documents": len(html_paths), "existing_html_documents": len(existing_html_paths),
        "already_present_new_html": len(present_new), "sitemap_urls": len(original_blocks),
        "immutable_existing_html": len(immutable_paths), "immutable_html_manifest_sha256": immutable_manifest,
        "middle3_math_html": len(middle3_paths), "middle3_math_manifest_sha256": middle3_manifest,
    }
    after_metrics = {
        "authorized_documents": len(generated), "final_html_documents": EXPECTED_FINAL_HTML,
        "new_html_documents": EXPECTED_NEW_HTML, "new_category_hubs": 1,
        "new_detail_documents": EXPECTED_LOCALITIES, "parent_hub_categories": 7,
        "sitemap_urls": len(final_blocks), "sitemap_existing_blocks_preserved": EXPECTED_EXISTING_HTML,
        "sitemap_new_urls_appended": EXPECTED_NEW_HTML, "sitemap_new_lastmod": PUBLISHED_DATE,
        "supported_service_offer_pages": supported, "unconfirmed_article_only_pages": unconfirmed,
        "high_school_chips": high_school_chips, "internal_links_checked": internal_links_checked,
        "second_pass_changes": len(second_pass),
    }
    metrics = {
        "changed_paths": len(changed), "unchanged_authorized_paths": len(generated) - len(changed),
        "sparse_plan": "pass", "existing_html_preservation": "pass",
        "source_exact_rendering": "pass", "facts_assets_schema_links_gate": "pass",
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
    return MappingProxyType({
        "version": 1, "root": str(plan.root), "generator_sha256": _self_sha256(),
        "middle_helper_sha256": MIDDLE_HELPER_SHA256, "base_helper_sha256": BASE_HELPER_SHA256,
        "candidate_sha256": plan.candidate_sha256, "source_manifest": dict(plan.source_manifest),
        "authorized_paths": [path.as_posix() for path in sorted(plan.authorized_documents, key=lambda item: item.as_posix())],
        "changed_paths": [path.as_posix() for path in plan.changed_paths],
        "before_exists": {path.as_posix(): plan.before_exists[path] for path in sorted(plan.before_exists, key=lambda item: item.as_posix())},
        "before_manifest": {path.as_posix(): plan.before_manifest[path] for path in sorted(plan.before_manifest, key=lambda item: item.as_posix())},
        "after_manifest": {path.as_posix(): plan.after_manifest[path] for path in sorted(plan.after_manifest, key=lambda item: item.as_posix())},
        "immutable_html_manifest_sha256": plan.immutable_html_manifest_sha256,
        "middle3_math_manifest_sha256": plan.middle3_math_manifest_sha256,
    })


def _plain_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _validate_freeze_payload(plan: BuildPlan, frozen: Mapping[str, Any]) -> None:
    expected = _plain_json(dict(freeze_payload(plan)))
    actual = _plain_json(dict(frozen))
    if actual != expected:
        keys = [key for key in sorted(set(expected) | set(actual)) if expected.get(key) != actual.get(key)]
        raise BuildError(f"external freeze payload mismatch: {keys[:6]}")
    if len(actual.get("authorized_paths", [])) != EXPECTED_AUTHORIZED_DOCUMENTS or len(actual.get("changed_paths", [])) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("freeze must approve exact initial 375-path mutation")


def _current_immutable_manifests(root: Path) -> tuple[str, str]:
    html_paths = _BASE._enumerate_html(root, {})
    if not (root / MIDDLE3_MATH_ROOT).is_dir():
        raise BuildError("transaction preflight cannot derive locality baseline")
    localities = tuple(path.name for path in (root / MIDDLE3_MATH_ROOT).iterdir() if path.is_dir() and (path / "index.html").is_file())
    if len(localities) != EXPECTED_LOCALITIES:
        raise BuildError("transaction preflight locality count mismatch")
    new_paths = {CATEGORY_REL, *(_detail_rel(locality) for locality in localities)}
    existing = html_paths - new_paths
    immutable = tuple(path for path in existing if path != PARENT_REL)
    middle3 = tuple(path for path in immutable if path == MIDDLE3_MATH_ROOT / "index.html" or MIDDLE3_MATH_ROOT in path.parents)
    if len(existing) != EXPECTED_EXISTING_HTML or len(immutable) != EXPECTED_IMMUTABLE_HTML or len(middle3) != 372:
        raise BuildError("transaction immutable path-count preflight failed")
    return _files_manifest(root, immutable, {}), _files_manifest(root, middle3, {})


def _verify_plan_current(plan: BuildPlan) -> None:
    keys = set(plan.authorized_documents)
    if keys != set(plan.before_exists) or keys != set(plan.before_manifest) or keys != set(plan.after_manifest):
        raise BuildError("plan mapping key sets differ")
    if len(keys) != EXPECTED_AUTHORIZED_DOCUMENTS or len(plan.changed_paths) != EXPECTED_AUTHORIZED_DOCUMENTS or plan.second_pass_changes:
        raise BuildError("apply requires exact initial idempotent 375-path plan")
    for rel in keys:
        target = _BASE._safe_target(plan.root, rel)
        exists = target.is_file()
        if exists != plan.before_exists[rel]:
            raise BuildError(f"plan preflight existence changed: {rel}")
        current_hash = _sha256(target.read_bytes()) if exists else ABSENT_SHA256
        if current_hash != plan.before_manifest[rel] or _sha256(_as_bytes(plan.authorized_documents[rel])) != plan.after_manifest[rel]:
            raise BuildError(f"plan preflight hash mismatch: {rel}")
    immutable, middle3 = _current_immutable_manifests(plan.root)
    if immutable != plan.immutable_html_manifest_sha256 or immutable != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        raise BuildError("immutable HTML changed after plan creation")
    if middle3 != plan.middle3_math_manifest_sha256 or middle3 != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
        raise BuildError("middle3 math tree changed after plan creation")


def apply_plan(plan: BuildPlan, *, go: str, frozen: Mapping[str, Any]) -> None:
    if go != "APPLY-GO":
        raise BuildError("apply requires exact explicit go token APPLY-GO")
    _validate_freeze_payload(plan, frozen)
    with _BASE._root_lock(plan.root):
        if _BASE.recover_transactions(plan.root):
            raise BuildError("transaction recovery changed state; rebuild and re-freeze")
        _verify_plan_current(plan)
        changed_docs = {rel: plan.authorized_documents[rel] for rel in plan.changed_paths}
        changed_exists = {rel: plan.before_exists[rel] for rel in plan.changed_paths}
        changed_before = {rel: plan.before_manifest[rel] for rel in plan.changed_paths}
        changed_after = {rel: plan.after_manifest[rel] for rel in plan.changed_paths}
        _BASE._transaction_apply(plan.root, changed_docs, changed_exists, changed_before, changed_after)
        for rel, expected in plan.after_manifest.items():
            target = _BASE._safe_target(plan.root, rel)
            if not target.is_file() or _sha256(target.read_bytes()) != expected:
                raise BuildError(f"post-transaction manifest mismatch: {rel}")
        immutable, middle3 = _current_immutable_manifests(plan.root)
        if immutable != BASE_IMMUTABLE_HTML_MANIFEST_SHA256 or middle3 != BASE_MIDDLE3_MATH_MANIFEST_SHA256:
            raise BuildError("post-transaction immutable HTML verification failed")


def transaction_self_test() -> Mapping[str, str]:
    results = dict(_BASE.transaction_self_test())
    with tempfile.TemporaryDirectory(prefix="wawa-high2-math-security-") as temporary:
        root = Path(temporary) / "site"
        root.mkdir()
        target = Path("existing.txt")
        (root / target).write_bytes(b"before\n")
        before_hash = _sha256(b"before\n")
        after = b"after\n"
        after_hash = _sha256(after)

        def rejected(call: Any, label: str) -> None:
            snapshot = (root / target).read_bytes()
            try:
                call()
            except (BuildError, ValueError, TypeError):
                pass
            else:
                raise BuildError(f"security synthetic did not reject: {label}")
            if (root / target).read_bytes() != snapshot:
                raise BuildError(f"security rejection mutated target: {label}")
            results[label] = "pass"

        rejected(lambda: _BASE._transaction_apply(root, {target: after}, {}, {target: before_hash}, {target: after_hash}), "mapping_key_mismatch_rejected")
        rejected(lambda: _BASE._transaction_apply(root, {target: after}, {target: True}, {target: before_hash}, {target: "0" * 64}), "output_hash_tamper_rejected")
        rejected(lambda: _BASE._safe_target(root, Path("..") / "escape.txt"), "traversal_rejected")
        rejected(lambda: _BASE._safe_target(root, Path(root.anchor) / "absolute.txt"), "absolute_path_rejected")
        results["invalid_mutation_zero"] = "pass"
    return MappingProxyType(results)


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
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
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


def _default_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    desktop = Path.home() / "Desktop"
    workbook = desktop / "고2 수학학원.xlsx"
    common = desktop / "홈페이지 정리" / "참고자료" / "공통자료"
    return root, workbook, common


def main(argv: Sequence[str] | None = None) -> int:
    default_root, default_workbook, default_common = _default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--workbook", type=Path, default=default_workbook)
    parser.add_argument("--common-dir", type=Path, default=default_common)
    parser.add_argument("--transaction-self-test", action="store_true")
    parser.add_argument("--freeze-out", type=Path)
    parser.add_argument("--freeze-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--go", default="")
    args = parser.parse_args(argv)
    try:
        synthetics = transaction_self_test() if args.transaction_self_test else None
        plan = build_plan(args.root, args.workbook, args.common_dir)
        freeze_path: Path | None = None
        if args.apply:
            if args.freeze_out is not None or args.freeze_file is None:
                raise BuildError("--apply requires --freeze-file and forbids --freeze-out")
            apply_plan(plan, go=args.go, frozen=_read_freeze_file(args.freeze_file))
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
