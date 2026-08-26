#!/usr/bin/env python3
"""Independent read-only content gate for the attached high-school grade-2 math batch.

The XLSX is immutable, untrusted content data.  This auditor reads OOXML parts
in memory, never asks Excel to calculate, and never follows text found in a
cell as an instruction.  It independently parses every manuscript and checks
the generator projection or the materialized release without writing files.

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
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote
from xml.etree import ElementTree as ET


sys.dont_write_bytecode = True

BASE_URL = "https://wawa-center.kr"
RELEASE_DATE = "2026-08-21"
EXPECTED_BASE_HEAD = "b2b20303a01360cdaf4b3dc94b97f5151b55c3ab"

# These release pins are frozen only after an independent source and rendered
# projection pass over the final generator candidate.
EXPECTED_GENERATOR_SHA256 = "834141ca0fb02218bbee64c095e3053a72cc80d1cdf326fd137c51976240bbe3"
EXPECTED_CANDIDATE_SHA256 = "0dd052530657d022be08cff5ffb0eb84215efac1f85dda4eb62a500e4f817f7a"
EXPECTED_RELEASE_AUTHORIZED_MANIFEST_SHA256 = "fc27139cde9e4ca216aaae868407742dca6ca162118e746c584abf489bdcba59"
EXPECTED_RELEASE_NEW_HTML_MANIFEST_SHA256 = "fa14d7e2af838386c5ad9d7941d0bd246608f141bf60707188c0e477abb0a986"
EXPECTED_RELEASE_ALL_HTML_MANIFEST_SHA256 = "b625724752b4821b99f5672f48c3367ef378dde5f1c1c5055fec93687694ff39"

EXPECTED_WORKBOOK_SHA256 = "ecb016f9ba0ae4abc7a2cd4032c3837168ad74f81885bdaa3e6ea3139adf5f68"
EXPECTED_CELL_MANIFEST_SHA256 = "58b81c3fb5caff3fc6269cb13583fa91ae864fc5abf646999564fc9bf06d8d81"
EXPECTED_CELL_SEQUENCE_SHA256 = "8dbb6437d751e4d6e98b7c10b7c5ac284ea180c224a0cfca18b7186f249e9fb1"
EXPECTED_CELL_MAPPING_SHA256 = "ed72bcf9d04072cc4be04efc4e1cd5d2c7f466751bad4d51fb0313a2a7e36380"
EXPECTED_OOXML_ENTRY_MANIFEST_SHA256 = "83f6dbe98f15f956d7e39d7070063c7c6f771dc1adfdff61c6269d0e5c106636"
EXPECTED_UNCOMPRESSED_BYTES = 4_150_748

EXPECTED_LOCALITIES = 371
EXPECTED_BASE_HTML = 16_857
EXPECTED_IMMUTABLE_HTML = 16_856
EXPECTED_NEW_HUBS = 1
EXPECTED_NEW_DETAILS = 371
EXPECTED_NEW_HTML = 372
EXPECTED_AUTHORIZED = 375
EXPECTED_FINAL_HTML = 17_229
EXPECTED_SUPPORTED = 325
EXPECTED_UNCONFIRMED = 46
EXPECTED_SCHOOL_GROUPS_PROVIDED = 308
EXPECTED_SCHOOL_GROUPS_MISSING = 63
EXPECTED_SCHOOL_CHIPS = 909
EXPECTED_SCHOOL_UNIQUE = 378
EXPECTED_H2 = 2_441
EXPECTED_BODY_PARAGRAPHS = 7_064
EXPECTED_FAQ = 1_996
EXPECTED_REVIEW_LINES = 895
EXPECTED_SUMMARY_PARAGRAPHS = 373

EXPECTED_H2_DISTRIBUTION = {6: 157, 7: 213, 8: 1}
EXPECTED_INTRO_DISTRIBUTION = {0: 27, 1: 313, 2: 31}
EXPECTED_FAQ_DISTRIBUTION = {5: 230, 6: 141}
EXPECTED_REVIEW_DISTRIBUTION = {1: 45, 2: 141, 3: 172, 4: 13}
EXPECTED_SUMMARY_DISTRIBUTION = {1: 369, 2: 2}
EXPECTED_FORMAT_DISTRIBUTION = {
    "markdown": 367,
    "plain_allowlist": 1,
    "html_h2": 2,
    "h2_dot": 1,
}

EXPECTED_H2_MAX_DF = 70
EXPECTED_H2_UNIQUE_TEMPLATES = 1_513
EXPECTED_PARAGRAPH_MAX_DF = 2
EXPECTED_PARAGRAPH_UNIQUE_TEMPLATES = 7_060
EXPECTED_SENTENCE_MAX_DF = 67
EXPECTED_SENTENCE_UNIQUE_TEMPLATES = 16_502

COMMON_HASHES = {
    "센터정보 정리.csv": "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a",
    "타깃학교.csv": "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f",
    "EducationalOrganization.csv": "e44c9a78c8b272781d5c078e38b466f9d438127a76219661ff43ee2604766c22",
    "이미지링크.csv": "c1b4f87b2b62f659107dbf0a79a1d566e213e008fc4b7f30cfa656ffae814100",
}

BASE_IMMUTABLE_HTML_MANIFEST_SHA256 = "5584c365f755b711a4f01e6faaa32e2878d25fc4ef1112b2dbe2752f5b0726b7"
BASE_PARENT_SHA256 = "c8ed1f93cca3dfbdc32a8da514adffea19a54b63214b6ea081f113a306b6219a"
BASE_SITEMAP_SHA256 = "eca96c125207b09e4d5f3c8f8c6d3bb004546fee9a62bb6b2af28bc644874de7"
BASE_LLMS_SHA256 = "4963fb2ce46260f30232e518df78aa09a206011b42f7ec8d85b7ef9a7c5d7111"

PARENT_REL = Path("학년별학원/index.html")
CATEGORY_ROOT = Path("학년별학원/고2수학학원")
CATEGORY_REL = CATEGORY_ROOT / "index.html"
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
GENERATOR_REL = Path("tools/generate_high2_math_pages.py")
LLMS_MARKER = "## 학년별학원 핵심 허브"

GRADE_CATEGORIES = (
    ("중1 수학학원", "중1수학학원", "중1", "수학"),
    ("중1 영어학원", "중1영어학원", "중1", "영어"),
    ("중2 수학학원", "중2수학학원", "중2", "수학"),
    ("중2 영어학원", "중2영어학원", "중2", "영어"),
    ("중3 수학학원", "중3수학학원", "중3", "수학"),
    ("중3 영어학원", "중3영어학원", "중3", "영어"),
    ("고2 수학학원", "고2수학학원", "고2", "수학"),
)

MARKERS = (
    "[페이지타이틀]",
    "[메타설명]",
    "[본문]",
    "[FAQ]",
    "[학부모후기]",
    "[JSON-LD 요약]",
)

PLAIN_SANBON_HEADINGS = (
    "고2 수학에서 먼저 점검해야 할 부분",
    "산본 생활권 학생에게 필요한 학교별 내신 준비",
    "개념 이해와 응용력의 간격 줄이기",
    "내신과 수능을 따로 보지 않는 학습 설계",
    "학습결과를 확인하는 관리 방식",
    "산본동에서 상담을 받을 때 확인할 내용",
)

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROMPT_OR_CODE = re.compile(
    r"(?:ignore\s+(?:all\s+)?previous|system\s+prompt|assistant\s*:|developer\s*:|"
    r"instructions?\s*:|이전\s*지시|지시를\s*무시|시스템\s*프롬프트|"
    r"명령을\s*실행|파일을\s*삭제|powershell|cmd\.exe|javascript\s*:|<script)",
    re.IGNORECASE,
)
MOJIBAKE = re.compile(r"(?:\ufffd|Ã.|Â.|â€|ì[\x80-\xff])")
GUARANTEE = re.compile(r"(?:100\s*%|무조건\s*(?:상승|향상|합격)|성적\s*보장|합격\s*보장)")
INLINE_REPEAT = re.compile(r"(?<![가-힣A-Za-z0-9])([가-힣]{2,})[ \t]+\1(?![가-힣A-Za-z0-9])")
QUESTION = re.compile(r"^Q(?:([1-9][0-9]*))?([.)])\s*(.+)$")
ANSWER = re.compile(r"^A(?:([1-9][0-9]*))?([.)])\s*(.+)$")
RAW_URL_BLOCK = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
INVISIBLE_TAGS = {"script", "style", "template", "noscript", "head"}

OOXML_ALLOWED = {
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/worksheets/sheet1.xml",
    "xl/theme/theme1.xml",
    "xl/styles.xml",
    "xl/sharedStrings.xml",
    "docProps/core.xml",
    "docProps/app.xml",
}

SHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


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


def split_paragraphs(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r"\n[ \t]*\n", value.strip()) if part.strip())


def normalized_header(value: str) -> str:
    return nfc(value).replace("\r", "").replace("\n", "").strip()


def find_column(columns: Iterable[str], compact_name: str) -> str | None:
    wanted = re.sub(r"[\s()]", "", compact_name)
    for column in columns:
        if re.sub(r"[\s()]", "", normalized_header(column)) == wanted:
            return column
    return None


def row_value(row: Mapping[str, str], compact_name: str) -> str:
    column = find_column(row.keys(), compact_name)
    return norm(row.get(column, "")) if column else ""


def split_csv_tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


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
    answer_prefixed: bool


@dataclass(frozen=True)
class Manuscript:
    row_number: int
    locality: str
    title: str
    meta: str
    intro: tuple[str, ...]
    sections: tuple[Section, ...]
    faqs: tuple[FAQ, ...]
    review_lines: tuple[str, ...]
    summary_paragraphs: tuple[str, ...]
    body_format: str
    raw_text: str
    raw_sha256: str

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(section.heading for section in self.sections)

    @property
    def paragraphs(self) -> tuple[str, ...]:
        return self.intro + tuple(paragraph for section in self.sections for paragraph in section.paragraphs)

    @property
    def summary(self) -> str:
        return "\n\n".join(self.summary_paragraphs)


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
    elementary_raw: str
    middle_raw: str
    high_raw: str
    high_schools: tuple[str, ...]
    math_grades: tuple[str, ...]
    telephone: str
    opening_hours: str
    official_site: str
    image_body: str
    image_map: str

    @property
    def supported(self) -> bool:
        return "고2" in self.math_grades


def read_csv_rows(path: Path, audit: Audit, code: str) -> list[dict[str, str]]:
    if path.is_symlink() or not path.is_file():
        audit.error(code + "_missing", path, "authoritative CSV must be a regular file")
        return []
    actual = sha256_file(path)
    expected = COMMON_HASHES[path.name]
    if actual != expected:
        audit.error(code + "_hash", path, f"actual={actual}, expected={expected}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                audit.error(code + "_header", path, "missing")
                return []
            rows = [{normalized_header(key): nfc(value or "") for key, value in row.items()} for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        audit.error(code + "_read", path, repr(exc))
        return []
    if len(rows) != EXPECTED_LOCALITIES:
        audit.error(code + "_count", path, f"actual={len(rows)}, expected={EXPECTED_LOCALITIES}")
    return rows


def load_common(common: Path, audit: Audit) -> tuple[SourceRow, ...]:
    center = read_csv_rows(common / "센터정보 정리.csv", audit, "center")
    target = read_csv_rows(common / "타깃학교.csv", audit, "target")
    eo = read_csv_rows(common / "EducationalOrganization.csv", audit, "eo")
    images = read_csv_rows(common / "이미지링크.csv", audit, "images")
    if not all((center, target, eo, images)):
        return ()

    orders = {
        "center": [row_value(row, "근처 수업가능 동네") for row in center],
        "target": [row_value(row, "근처 수업가능 동네") for row in target],
        "eo": [row_value(row, "서비스 제공 지역") for row in eo],
        "images": [row_value(row, "제목") for row in images],
    }
    for label, order in orders.items():
        if len(order) != len(set(order)):
            audit.error("common_duplicate_locality", label, "duplicate locality")
        if order != orders["center"]:
            audit.error("common_order", label, "locality order differs from center CSV")

    result: list[SourceRow] = []
    parity_fields = (
        "근처 수업가능 동네", "지역", "시or구", "센터명",
        "타깃학교(초)", "타깃학교(중)", "타깃학교(고)",
    )
    for center_row, target_row, eo_row, image_row in zip(center, target, eo, images, strict=False):
        locality = row_value(center_row, "근처 수업가능 동네")
        location = "common:" + locality
        for key in parity_fields:
            if row_value(center_row, key) != row_value(target_row, key):
                audit.error("common_target_parity", location, repr(key))
        center_name = row_value(center_row, "센터명")
        address = row_value(center_row, "센터 주소")
        if row_value(eo_row, "실제 센터명") != center_name:
            audit.error("common_eo_name", location, "center/EO differs")
        if row_value(eo_row, "도로명 주소") != address:
            audit.error("common_eo_address", location, "center/EO differs")
        if row_value(eo_row, "서비스 제공 지역") != locality:
            audit.error("common_eo_locality", location, repr(row_value(eo_row, "서비스 제공 지역")))
        if row_value(image_row, "제목") != locality:
            audit.error("common_image_locality", location, repr(row_value(image_row, "제목")))
        result.append(SourceRow(
            locality=locality,
            region=row_value(center_row, "지역"),
            city=row_value(center_row, "시or구"),
            center_name=center_name,
            fee_url=row_value(center_row, "센터 교습비"),
            education_office=row_value(center_row, "교육지원청명칭"),
            registration=row_value(center_row, "교육지원청 등록번호"),
            address=address,
            elementary_raw=row_value(center_row, "타깃학교(초)"),
            middle_raw=row_value(center_row, "타깃학교(중)"),
            high_raw=row_value(center_row, "타깃학교(고)"),
            high_schools=split_csv_tokens(row_value(center_row, "타깃학교(고)")),
            math_grades=split_csv_tokens(row_value(center_row, "가능학년(수학)")),
            telephone=row_value(eo_row, "전화번호"),
            opening_hours=row_value(eo_row, "운영 시간"),
            official_site=row_value(eo_row, "공식 홈페이지"),
            image_body=row_value(image_row, "본문"),
            image_map=row_value(image_row, "지도"),
        ))

    rows = tuple(result)
    supported = sum(row.supported for row in rows)
    provided = sum(bool(row.high_schools) for row in rows)
    chips = sum(len(row.high_schools) for row in rows)
    unique = len({school for row in rows for school in row.high_schools})
    if (supported, len(rows) - supported) != (EXPECTED_SUPPORTED, EXPECTED_UNCONFIRMED):
        audit.error("common_grade_support", common, f"supported={supported}, unconfirmed={len(rows)-supported}")
    if (provided, len(rows) - provided, chips, unique) != (
        EXPECTED_SCHOOL_GROUPS_PROVIDED,
        EXPECTED_SCHOOL_GROUPS_MISSING,
        EXPECTED_SCHOOL_CHIPS,
        EXPECTED_SCHOOL_UNIQUE,
    ):
        audit.error(
            "common_high_schools",
            common,
            f"provided={provided}, missing={len(rows)-provided}, chips={chips}, unique={unique}",
        )
    if any(not row.address or not row.telephone or not row.opening_hours for row in rows):
        audit.error("common_required_fact", common, "blank address/telephone/opening hours")
    audit.observations["common"] = {
        "rows": len(rows),
        "hashes": COMMON_HASHES,
        "supported": supported,
        "unconfirmed": len(rows) - supported,
        "unconfirmed_localities": [row.locality for row in rows if not row.supported],
        "high_school_groups_provided": provided,
        "high_school_groups_missing": len(rows) - provided,
        "high_school_chips": chips,
        "high_school_unique": unique,
    }
    return rows


def safe_archive_name(name: str) -> bool:
    posix = PurePosixPath(name.replace("\\", "/"))
    windows = PureWindowsPath(name)
    return not (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or ".." in windows.parts
    )


def load_workbook_cells(path: Path, audit: Audit) -> tuple[str, ...]:
    if path.is_symlink() or not path.is_file():
        audit.error("workbook_missing", path, "must be a regular non-symlink file")
        return ()
    actual_hash = sha256_file(path)
    if actual_hash != EXPECTED_WORKBOOK_SHA256:
        audit.error("workbook_hash", path, f"actual={actual_hash}, expected={EXPECTED_WORKBOOK_SHA256}")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != OOXML_ALLOWED:
                audit.error("workbook_entries", path, f"actual={names!r}")
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if not safe_archive_name(info.filename) or mode == 0o120000:
                    audit.error("workbook_unsafe_entry", path, info.filename)
                if info.flag_bits & 1:
                    audit.error("workbook_encrypted_entry", path, info.filename)
                if info.file_size > 8_000_000 or info.file_size / max(info.compress_size, 1) > 50:
                    audit.error("workbook_archive_limit", path, info.filename)
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed != EXPECTED_UNCOMPRESSED_BYTES:
                audit.error("workbook_uncompressed", path, f"actual={total_uncompressed}")
            bad_crc = archive.testzip()
            if bad_crc is not None:
                audit.error("workbook_crc", path, bad_crc)
            entry_manifest = sha256_bytes("".join(
                f"{info.filename}\t{info.file_size}\t{info.CRC:08x}\n" for info in infos
            ).encode("utf-8"))
            if entry_manifest != EXPECTED_OOXML_ENTRY_MANIFEST_SHA256:
                audit.error("workbook_entry_manifest", path, entry_manifest)

            content_types = archive.read("[Content_Types].xml")
            relationships = archive.read("xl/_rels/workbook.xml.rels")
            forbidden = re.compile(rb"(?:vbaProject|macroEnabled|externalLink|oleObject|activeX|connections)", re.I)
            if forbidden.search(content_types) or forbidden.search(relationships):
                audit.error("workbook_active_part", path, "forbidden OOXML part relationship")

            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook.findall(".//x:sheets/x:sheet", SHEET_NS)
            if len(sheets) != 1 or sheets[0].get("name") != "Sheet1":
                audit.error("workbook_sheets", path, f"count={len(sheets)}")

            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_nodes = shared_root.findall("x:si", SHEET_NS)
            strings: list[str] = []
            for index, node in enumerate(shared_nodes):
                text_nodes = node.findall(".//x:t", SHEET_NS)
                if len(text_nodes) != 1 or node.findall("x:r", SHEET_NS) or node.findall("x:rPh", SHEET_NS):
                    audit.error("workbook_rich_string", f"shared:{index}", "only one plain t node is allowed")
                value = "".join(item.text or "" for item in text_nodes)
                strings.append(value)
            if (
                shared_root.get("count") != str(EXPECTED_LOCALITIES)
                or shared_root.get("uniqueCount") != str(EXPECTED_LOCALITIES)
                or len(strings) != EXPECTED_LOCALITIES
                or len(set(strings)) != EXPECTED_LOCALITIES
            ):
                audit.error("workbook_shared_strings", path, f"count={len(strings)}, unique={len(set(strings))}")

            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            dimension = sheet.find("x:dimension", SHEET_NS)
            if dimension is None or dimension.get("ref") != "A1:A371":
                audit.error("workbook_dimension", path, repr(dimension.get("ref") if dimension is not None else None))
            if sheet.findall(".//x:f", SHEET_NS):
                audit.error("workbook_formula", path, "formula cells are forbidden")
            if sheet.find("x:mergeCells", SHEET_NS) is not None or sheet.find("x:hyperlinks", SHEET_NS) is not None:
                audit.error("workbook_sheet_active", path, "merged cells/hyperlinks are forbidden")
            cells = sheet.findall(".//x:sheetData/x:row/x:c", SHEET_NS)
            values: list[str] = []
            mapping: list[tuple[str, int]] = []
            for expected_row, cell in enumerate(cells, 1):
                ref = cell.get("r", "")
                value_node = cell.find("x:v", SHEET_NS)
                if ref != f"A{expected_row}" or cell.get("t") != "s" or value_node is None:
                    audit.error("workbook_cell", path, f"row={expected_row}, ref={ref}, type={cell.get('t')}")
                    continue
                try:
                    shared_index = int(value_node.text or "")
                    value = strings[shared_index]
                except (ValueError, IndexError) as exc:
                    audit.error("workbook_cell_index", ref, repr(exc))
                    continue
                mapping.append((ref, shared_index))
                values.append(value)
            if len(cells) != EXPECTED_LOCALITIES or [index for _, index in mapping] != list(range(EXPECTED_LOCALITIES)):
                audit.error("workbook_cell_mapping", path, f"cells={len(cells)}")

    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        audit.error("workbook_read", path, repr(exc))
        return ()

    cell_manifest = sha256_bytes("".join(
        f"{index}\t{sha256_bytes(value.encode('utf-8'))}\n"
        for index, value in enumerate(values, 1)
    ).encode("utf-8"))
    sequence_hash = sha256_bytes("\0".join(values).encode("utf-8"))
    mapping_hash = sha256_bytes("".join(f"{ref}\t{index}\n" for ref, index in mapping).encode("utf-8"))
    if cell_manifest != EXPECTED_CELL_MANIFEST_SHA256:
        audit.error("workbook_cell_manifest", path, cell_manifest)
    if sequence_hash != EXPECTED_CELL_SEQUENCE_SHA256:
        audit.error("workbook_cell_sequence", path, sequence_hash)
    if mapping_hash != EXPECTED_CELL_MAPPING_SHA256:
        audit.error("workbook_mapping_manifest", path, mapping_hash)
    audit.observations["workbook"] = {
        "sha256": actual_hash,
        "entries": len(OOXML_ALLOWED),
        "uncompressed_bytes": EXPECTED_UNCOMPRESSED_BYTES,
        "sheet": "Sheet1",
        "dimension": "A1:A371",
        "cells": len(values),
        "unique_cells": len(set(values)),
        "formulas": 0,
        "hyperlinks": 0,
        "merged_ranges": 0,
        "cell_manifest_sha256": cell_manifest,
        "cell_sequence_sha256": sequence_hash,
        "cell_mapping_sha256": mapping_hash,
    }
    return tuple(values)


def parse_body(body: str, row_number: int, locality: str, audit: Audit) -> tuple[str, tuple[str, ...], tuple[Section, ...]]:
    blocks = list(split_paragraphs(body))
    parsed: list[tuple[str, str]] = []
    formats: set[str] = set()
    for block in blocks:
        markdown = re.fullmatch(r"##[ \t]+(.+?)[ \t]*", block, re.DOTALL)
        html_heading = re.fullmatch(r"<h2>([^\n<>]+)</h2>", block, re.IGNORECASE)
        h2_dot = re.fullmatch(r"H2\.\s*(.+)", block, re.DOTALL)
        if markdown is not None and "\n" not in block:
            formats.add("markdown")
            parsed.append(("h", markdown.group(1).strip()))
        elif html_heading is not None:
            formats.add("html_h2")
            parsed.append(("h", html_heading.group(1).strip()))
        elif h2_dot is not None and "\n" not in block:
            formats.add("h2_dot")
            parsed.append(("h", h2_dot.group(1).strip()))
        else:
            parsed.append(("p", block))

    if not formats:
        if row_number != 78 or locality != "산본동":
            audit.error("source_body_format", f"row:{row_number}:{locality}", "heading syntax absent")
            return "invalid", (), ()
        headings = set(PLAIN_SANBON_HEADINGS)
        parsed = [("h", value) if value in headings else (kind, value) for kind, value in parsed]
        formats.add("plain_allowlist")
    if len(formats) != 1:
        audit.error("source_body_mixed_format", f"row:{row_number}:{locality}", repr(sorted(formats)))
    body_format = next(iter(formats))

    expected_special = {
        78: ("산본동", "plain_allowlist"),
        300: ("수창동", "html_h2"),
        304: ("달동", "h2_dot"),
        360: ("단구동", "html_h2"),
    }
    if row_number in expected_special:
        if (locality, body_format) != expected_special[row_number]:
            audit.error("source_body_special", row_number, f"actual={(locality, body_format)!r}")
    elif body_format != "markdown":
        audit.error("source_body_unexpected_variant", f"row:{row_number}:{locality}", body_format)

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
    if not result or any(not section.heading or not section.paragraphs for section in result):
        audit.error("source_body_sections", f"row:{row_number}:{locality}", f"sections={len(result)}")
    if body_format == "plain_allowlist" and tuple(section.heading for section in result) != PLAIN_SANBON_HEADINGS:
        audit.error("source_plain_heading_allowlist", locality, repr(tuple(section.heading for section in result)))
    return body_format, tuple(intro), result


def parse_faq(value: str, row_number: int, locality: str, audit: Audit) -> tuple[FAQ, ...]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    result: list[FAQ] = []
    if len(lines) % 2:
        audit.error("source_faq_lines", f"row:{row_number}:{locality}", f"count={len(lines)}")
        return ()
    for index in range(0, len(lines), 2):
        question = QUESTION.fullmatch(lines[index])
        if question is None:
            audit.error("source_faq_question", f"row:{row_number}:{locality}", repr(lines[index]))
            continue
        answer = ANSWER.fullmatch(lines[index + 1])
        if answer is None:
            if row_number != 87 or locality != "다산신도시":
                audit.error("source_faq_answer", f"row:{row_number}:{locality}", repr(lines[index + 1]))
                continue
            result.append(FAQ(
                "Q" + (question.group(1) or "") + question.group(2),
                question.group(3).strip(),
                "",
                lines[index + 1],
                False,
            ))
        else:
            result.append(FAQ(
                "Q" + (question.group(1) or "") + question.group(2),
                question.group(3).strip(),
                "A" + (answer.group(1) or "") + answer.group(2),
                answer.group(3).strip(),
                True,
            ))
    return tuple(result)


def parse_manuscript(raw_text: str, row: SourceRow, row_number: int, audit: Audit) -> Manuscript | None:
    location = f"row:{row_number}:{row.locality}"
    if raw_text.encode("utf-8").decode("utf-8") != raw_text:
        audit.error("source_utf8_roundtrip", location, "failed")
    if CONTROL.search(raw_text) or MOJIBAKE.search(raw_text) or GUARANTEE.search(raw_text):
        audit.error("source_quality", location, "control/mojibake/guarantee pattern")
    if PROMPT_OR_CODE.search(raw_text):
        audit.error("source_instruction", location, PROMPT_OR_CODE.search(raw_text).group(0))
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

    def segment(start: int, end: int | None) -> str:
        right = positions[end] if end is not None else len(lines)
        return "\n".join(lines[positions[start] + 1:right]).strip("\n")

    title_values = split_paragraphs(segment(0, 1))
    meta_values = split_paragraphs(segment(1, 2))
    body = segment(2, 3).strip()
    faq_text = segment(3, 4).strip()
    review_lines = tuple(line.strip() for line in segment(4, 5).splitlines() if line.strip())
    summary_values = split_paragraphs(segment(5, None))
    if len(title_values) != 1 or len(meta_values) != 1 or not summary_values:
        audit.error(
            "source_singletons",
            location,
            f"title={len(title_values)}, meta={len(meta_values)}, summary={len(summary_values)}",
        )
        return None
    expected_prefix = row.locality + " 고2 수학학원"
    if not title_values[0].startswith(expected_prefix):
        audit.error("source_title_locality", location, repr(title_values[0]))
    body_format, intro, sections = parse_body(body, row_number, row.locality, audit)
    faqs = parse_faq(faq_text, row_number, row.locality, audit)
    return Manuscript(
        row_number=row_number,
        locality=row.locality,
        title=title_values[0],
        meta=meta_values[0],
        intro=intro,
        sections=sections,
        faqs=faqs,
        review_lines=review_lines,
        summary_paragraphs=summary_values,
        body_format=body_format,
        raw_text=raw_text,
        raw_sha256=sha256_bytes(raw_text.encode("utf-8")),
    )


def normalized_template(value: str, manuscript: Manuscript, row: SourceRow) -> str:
    text = norm(unicodedata.normalize("NFKC", value)).casefold()
    replacements = {
        manuscript.title,
        manuscript.locality + " 고2 수학학원",
        manuscript.locality,
        row.locality,
        row.region,
        row.city,
        row.center_name,
        row.address,
        row.education_office,
        row.registration,
        row.fee_url,
        *split_csv_tokens(row.elementary_raw),
        *split_csv_tokens(row.middle_raw),
        *split_csv_tokens(row.high_raw),
    }
    for replacement in sorted((norm(item).casefold() for item in replacements if item), key=len, reverse=True):
        text = text.replace(replacement, " {fact} ")
    return re.sub(r"\d+", "{n}", norm(text))


def validate_source_contract(cells: Sequence[str], rows: Sequence[SourceRow], audit: Audit) -> tuple[Manuscript, ...]:
    if len(cells) != EXPECTED_LOCALITIES or len(rows) != EXPECTED_LOCALITIES:
        audit.error("source_alignment", "source", f"cells={len(cells)}, rows={len(rows)}")
        return ()
    manuscripts = tuple(
        item
        for item in (
            parse_manuscript(text, row, index, audit)
            for index, (text, row) in enumerate(zip(cells, rows, strict=True), 1)
        )
        if item is not None
    )
    if len(manuscripts) != EXPECTED_LOCALITIES:
        audit.error("source_parse_count", "source", f"actual={len(manuscripts)}")
        return manuscripts

    h2_distribution = Counter(len(item.sections) for item in manuscripts)
    intro_distribution = Counter(len(item.intro) for item in manuscripts)
    faq_distribution = Counter(len(item.faqs) for item in manuscripts)
    review_distribution = Counter(len(item.review_lines) for item in manuscripts)
    summary_distribution = Counter(len(item.summary_paragraphs) for item in manuscripts)
    format_distribution = Counter(item.body_format for item in manuscripts)
    aggregates = (
        sum(len(item.sections) for item in manuscripts),
        sum(len(item.paragraphs) for item in manuscripts),
        sum(len(item.faqs) for item in manuscripts),
        sum(len(item.review_lines) for item in manuscripts),
        sum(len(item.summary_paragraphs) for item in manuscripts),
    )
    if aggregates != (
        EXPECTED_H2,
        EXPECTED_BODY_PARAGRAPHS,
        EXPECTED_FAQ,
        EXPECTED_REVIEW_LINES,
        EXPECTED_SUMMARY_PARAGRAPHS,
    ):
        audit.error("source_aggregate", "source", repr(aggregates))
    distributions = {
        "h2": dict(h2_distribution),
        "intro": dict(intro_distribution),
        "faq": dict(faq_distribution),
        "review": dict(review_distribution),
        "summary": dict(summary_distribution),
        "format": dict(format_distribution),
    }
    expected_distributions = {
        "h2": EXPECTED_H2_DISTRIBUTION,
        "intro": EXPECTED_INTRO_DISTRIBUTION,
        "faq": EXPECTED_FAQ_DISTRIBUTION,
        "review": EXPECTED_REVIEW_DISTRIBUTION,
        "summary": EXPECTED_SUMMARY_DISTRIBUTION,
        "format": EXPECTED_FORMAT_DISTRIBUTION,
    }
    if distributions != expected_distributions:
        audit.error("source_distribution", "source", f"actual={distributions!r}")

    exact_titles = sum(item.title == item.locality + " 고2 수학학원" for item in manuscripts)
    extended_titles = len(manuscripts) - exact_titles
    bare_answers = [(item.row_number, item.locality, faq.answer) for item in manuscripts for faq in item.faqs if not faq.answer_prefixed]
    if (exact_titles, extended_titles) != (274, 97):
        audit.error("source_title_distribution", "source", f"exact={exact_titles}, extended={extended_titles}")
    if len(bare_answers) != 5 or {(row, locality) for row, locality, _ in bare_answers} != {(87, "다산신도시")}:
        audit.error("source_bare_faq", "source", repr(bare_answers[:10]))

    within_paragraph_duplicates: list[str] = []
    within_heading_duplicates: list[str] = []
    h2_df: Counter[str] = Counter()
    paragraph_df: Counter[str] = Counter()
    sentence_df: Counter[str] = Counter()
    normalized_documents: set[str] = set()
    for manuscript, row in zip(manuscripts, rows, strict=True):
        paragraphs = [normalized_template(value, manuscript, row) for value in manuscript.paragraphs]
        headings = [normalized_template(value, manuscript, row) for value in manuscript.headings]
        if len(paragraphs) != len(set(paragraphs)):
            within_paragraph_duplicates.append(manuscript.locality)
        if len(headings) != len(set(headings)):
            within_heading_duplicates.append(manuscript.locality)
        h2_df.update(set(headings))
        paragraph_df.update(set(paragraphs))
        sentence_df.update({
            normalized_template(sentence, manuscript, row)
            for paragraph in manuscript.paragraphs
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if norm(sentence)
        })
        visible_values = (
            manuscript.title,
            manuscript.meta,
            *manuscript.intro,
            *(value for section in manuscript.sections for value in (section.heading, *section.paragraphs)),
            *(value for faq in manuscript.faqs for value in (faq.question, faq.answer)),
            *manuscript.review_lines,
            *manuscript.summary_paragraphs,
        )
        normalized_documents.add(sha256_bytes("\0".join(
            normalized_template(value, manuscript, row) for value in visible_values
        ).encode("utf-8")))
    if within_paragraph_duplicates or within_heading_duplicates:
        audit.error(
            "source_within_page_duplicate",
            "source",
            f"paragraphs={within_paragraph_duplicates[:10]}, headings={within_heading_duplicates[:10]}",
        )
    diversity = {
        "h2_max_df": max(h2_df.values(), default=0),
        "h2_unique_templates": len(h2_df),
        "paragraph_max_df": max(paragraph_df.values(), default=0),
        "paragraph_unique_templates": len(paragraph_df),
        "sentence_max_df": max(sentence_df.values(), default=0),
        "sentence_unique_templates": len(sentence_df),
        "fact_normalized_document_unique": len(normalized_documents),
    }
    expected_diversity = {
        "h2_max_df": EXPECTED_H2_MAX_DF,
        "h2_unique_templates": EXPECTED_H2_UNIQUE_TEMPLATES,
        "paragraph_max_df": EXPECTED_PARAGRAPH_MAX_DF,
        "paragraph_unique_templates": EXPECTED_PARAGRAPH_UNIQUE_TEMPLATES,
        "sentence_max_df": EXPECTED_SENTENCE_MAX_DF,
        "sentence_unique_templates": EXPECTED_SENTENCE_UNIQUE_TEMPLATES,
        "fact_normalized_document_unique": EXPECTED_LOCALITIES,
    }
    if diversity != expected_diversity:
        audit.error("source_diversity", "source", f"actual={diversity!r}")

    repeated = [
        (item.row_number, item.locality, match.group(0))
        for item in manuscripts
        for match in INLINE_REPEAT.finditer(item.raw_text)
    ]
    if repeated != [(108, "성남 금곡동", "금곡동 금곡동")]:
        audit.error("source_inline_repeat_baseline", "source", repr(repeated))
    html_tags = [(item.row_number, item.locality, len(re.findall(r"</?h2>", item.raw_text, re.I))) for item in manuscripts if "<" in item.raw_text]
    if html_tags != [(300, "수창동", 12), (360, "단구동", 12)]:
        audit.error("source_html_allowlist", "source", repr(html_tags))
    if any(re.search(r"<(?!/?h2>)[^>]+>", item.raw_text, re.I) for item in manuscripts):
        audit.error("source_html_unallowlisted", "source", "tag outside exact h2 structural variants")
    anomaly_item = manuscripts[103]
    anomaly_row = rows[103]
    if (
        anomaly_item.locality != "부천 중동"
        or anomaly_item.raw_text.count("중흥고") != 4
        or anomaly_item.raw_text.count("증흥고") != 0
        or anomaly_row.high_raw.count("증흥고") != 1
    ):
        audit.error("source_school_spelling_baseline", "부천 중동", "raw workbook/common source anomaly changed")

    audit.observations["source"] = {
        "manuscripts": len(manuscripts),
        "unique_raw_cells": len({item.raw_sha256 for item in manuscripts}),
        "title_exact": exact_titles,
        "title_extended": extended_titles,
        "h2": aggregates[0],
        "body_paragraphs": aggregates[1],
        "faq": aggregates[2],
        "review_lines": aggregates[3],
        "summary_paragraphs": aggregates[4],
        "distributions": distributions,
        "bare_faq_answers": len(bare_answers),
        "no_visible_corrections_authorized": True,
        "preserved_anomalies": {
            "inline_repeat": repeated,
            "부천_중동_workbook": "중흥고",
            "부천_중동_common": "증흥고",
        },
        "diversity": diversity,
        "h2_top": h2_df.most_common(5),
        "paragraph_top": paragraph_df.most_common(5),
        "sentence_top": sentence_df.most_common(5),
    }
    return manuscripts


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    parent: "Element | None" = None
    children: list["Element | str"] = field(default_factory=list)

    def text(self, *, visible: bool = True) -> str:
        if visible and self.tag in INVISIBLE_TAGS:
            return ""
        return norm(" ".join(
            child.text(visible=visible) if isinstance(child, Element) else child
            for child in self.children
        ))

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
    except Exception as exc:  # noqa: BLE001 - malformed HTML is an audit finding
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
            matched = actual is not None if expected is None else actual == expected
            if not matched:
                break
        if matched:
            result.append(node)
    return result


def nodes_with_attr(root: Element, name: str, value: str | None = None) -> list[Element]:
    return [
        node for node in root.descendants()
        if name in node.attrs and (value is None or node.attrs[name] == value)
    ]


def has_class(node: Element, name: str) -> bool:
    return name in node.attrs.get("class", "").split()


def canonical_values(dom: Element) -> list[str]:
    return [
        node.attrs.get("href", "")
        for node in find_elements(dom, "link")
        if "canonical" in node.attrs.get("rel", "").split()
    ]


def meta_values(dom: Element, *, name: str | None = None, prop: str | None = None) -> list[str]:
    result: list[str] = []
    for node in find_elements(dom, "meta"):
        if name is not None and node.attrs.get("name", "").casefold() != name.casefold():
            continue
        if prop is not None and node.attrs.get("property", "").casefold() != prop.casefold():
            continue
        result.append(node.attrs.get("content", ""))
    return result


def json_graph(dom: Element, audit: Audit, location: str) -> list[dict[str, Any]]:
    scripts = find_elements(dom, "script", type="application/ld+json")
    if len(scripts) != 1:
        audit.error("jsonld_script_count", location, f"count={len(scripts)}")
    result: list[dict[str, Any]] = []
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


def graph_nodes(graph: Sequence[Mapping[str, Any]], wanted: str) -> list[Mapping[str, Any]]:
    return [node for node in graph if wanted in node_types(node)]


def walk_json(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def faq_schema_pairs(node: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    entities = node.get("mainEntity")
    if not isinstance(entities, list):
        return ()
    result: list[tuple[str, str]] = []
    for question in entities:
        if not isinstance(question, Mapping):
            continue
        answer = question.get("acceptedAnswer")
        if isinstance(answer, Mapping):
            result.append((norm(question.get("name")), norm(answer.get("text"))))
    return tuple(result)


@dataclass
class View:
    root: Path
    overrides: Mapping[str, str | bytes] = field(default_factory=dict)

    def exists(self, rel: str | Path) -> bool:
        key = Path(rel).as_posix()
        return key in self.overrides or self.root.joinpath(*PurePosixPath(key).parts).is_file()

    def bytes(self, rel: str | Path) -> bytes:
        key = Path(rel).as_posix()
        if key in self.overrides:
            value = self.overrides[key]
            return value if isinstance(value, bytes) else value.encode("utf-8")
        return self.root.joinpath(*PurePosixPath(key).parts).read_bytes()

    def text(self, rel: str | Path) -> str:
        return self.bytes(rel).decode("utf-8")


def detail_rel(locality: str) -> Path:
    return CATEGORY_ROOT / locality / "index.html"


def expected_new_paths(rows: Sequence[SourceRow]) -> set[str]:
    return {
        CATEGORY_REL.as_posix(),
        *(detail_rel(row.locality).as_posix() for row in rows),
    }


def expected_authorized_paths(rows: Sequence[SourceRow]) -> set[str]:
    return {
        PARENT_REL.as_posix(),
        SITEMAP_REL.as_posix(),
        LLMS_REL.as_posix(),
        *expected_new_paths(rows),
    }


def enumerate_html(root: Path) -> set[str]:
    result: set[str] = set()
    for path in root.rglob("*.html"):
        rel = path.relative_to(root)
        if any(part in {".git", ".vercel", "node_modules", "__pycache__"} for part in rel.parts):
            continue
        if path.is_file():
            result.add(rel.as_posix())
    return result


def files_manifest(root: Path, paths: Iterable[str]) -> str:
    return sha256_bytes("".join(
        rel + "\0" + sha256_file(root.joinpath(*PurePosixPath(rel).parts)) + "\n"
        for rel in sorted(paths)
    ).encode("utf-8"))


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


def source_snapshot(root: Path, workbook: Path, common: Path) -> dict[str, str]:
    paths = [
        workbook,
        *(common / name for name in COMMON_HASHES),
        root / GENERATOR_REL,
        root / "tools/generate_middle_grade_pages.py",
        root / "tools/generate_grade3_math_pages.py",
    ]
    return {str(path.resolve()): sha256_file(path) for path in paths if path.is_file()}


def validate_baseline(root: Path, rows: Sequence[SourceRow], audit: Audit) -> str:
    all_html = enumerate_html(root)
    new_paths = expected_new_paths(rows)
    present = all_html & new_paths
    if not present:
        state = "baseline"
    elif present == new_paths:
        state = "release"
    else:
        state = "partial"
        audit.error("materialization_partial", CATEGORY_ROOT, f"actual={len(present)}/{len(new_paths)}")
    existing = all_html - new_paths
    immutable = existing - {PARENT_REL.as_posix()}
    if len(existing) != EXPECTED_BASE_HTML or len(immutable) != EXPECTED_IMMUTABLE_HTML:
        audit.error("baseline_html_count", root, f"existing={len(existing)}, immutable={len(immutable)}")
    else:
        manifest = files_manifest(root, immutable)
        if manifest != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
            audit.error("baseline_immutable_manifest", root, f"actual={manifest}")
    if state == "baseline":
        for rel, expected in (
            (PARENT_REL, BASE_PARENT_SHA256),
            (SITEMAP_REL, BASE_SITEMAP_SHA256),
            (LLMS_REL, BASE_LLMS_SHA256),
        ):
            path = root / rel
            if not path.is_file() or sha256_file(path) != expected:
                audit.error("baseline_mutable_hash", rel, f"actual={sha256_file(path) if path.is_file() else 'missing'}")
    expected_total = EXPECTED_BASE_HTML if state == "baseline" else EXPECTED_FINAL_HTML if state == "release" else -1
    if expected_total >= 0 and len(all_html) != expected_total:
        audit.error("baseline_total_html", root, f"actual={len(all_html)}, expected={expected_total}")
    audit.observations["materialization"] = {
        "state": state,
        "all_html": len(all_html),
        "existing_html": len(existing),
        "immutable_html": len(immutable),
        "new_html": len(present),
    }
    return state


def import_pinned_generator(root: Path, audit: Audit) -> ModuleType | None:
    path = root / GENERATOR_REL
    if not path.is_file():
        audit.hold("generator_pending", path, "generator file is not present")
        return None
    actual = sha256_file(path)
    if EXPECTED_GENERATOR_SHA256 == "PENDING":
        audit.hold("generator_pin_pending", path, f"actual={actual}")
        return None
    if actual != EXPECTED_GENERATOR_SHA256:
        audit.error("generator_hash", path, f"actual={actual}, expected={EXPECTED_GENERATOR_SHA256}")
        return None
    name = "_pinned_high2_math_generator_" + actual[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        audit.error("generator_import_spec", path, "loader unavailable")
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - a pinned import failure is an audit finding
        sys.modules.pop(name, None)
        audit.error("generator_import", path, repr(exc))
        return None
    build_plan = getattr(module, "build_plan", None)
    if not callable(build_plan):
        audit.error("generator_api", path, "build_plan missing")
        return None
    parameters = tuple(inspect.signature(build_plan).parameters)
    if parameters != ("root", "workbook_path", "common_dir", "current_overrides"):
        audit.error("generator_api_signature", path, repr(parameters))
        return None
    return module


def normalize_plan_documents(plan: Any, root: Path, audit: Audit) -> dict[str, str | bytes]:
    source = getattr(plan, "authorized_documents", None)
    if not isinstance(source, Mapping):
        audit.error("plan_documents", GENERATOR_REL, "authorized_documents is not a mapping")
        return {}
    result: dict[str, str | bytes] = {}
    for key, value in source.items():
        path = Path(key)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(root)
            except ValueError:
                audit.error("plan_path_outside", key, "outside root")
                continue
        rel = path.as_posix()
        if rel.startswith("../") or rel in result or not isinstance(value, (str, bytes)):
            audit.error("plan_document", rel, "unsafe/duplicate/non-text value")
            continue
        result[rel] = value
    return result


def build_projected_view(
    root: Path,
    workbook: Path,
    common: Path,
    rows: Sequence[SourceRow],
    audit: Audit,
) -> View | None:
    module = import_pinned_generator(root, audit)
    if module is None:
        return None
    before_repo = repository_snapshot(root)
    before_source = source_snapshot(root, workbook, common)
    try:
        plan = module.build_plan(root, workbook, common)
    except Exception as exc:  # noqa: BLE001 - plan failures are audit findings
        audit.error("plan_build", GENERATOR_REL, repr(exc))
        return None
    if repository_snapshot(root) != before_repo:
        audit.error("plan_repository_write", GENERATOR_REL, "build_plan changed repository state")
    if source_snapshot(root, workbook, common) != before_source:
        audit.error("plan_source_write", GENERATOR_REL, "build_plan changed an immutable source")

    documents = normalize_plan_documents(plan, root, audit)
    expected_paths = expected_authorized_paths(rows)
    if set(documents) != expected_paths or len(documents) != EXPECTED_AUTHORIZED:
        audit.error(
            "plan_authorized_paths",
            GENERATOR_REL,
            f"actual={len(documents)}, missing={sorted(expected_paths-set(documents))[:5]}, extra={sorted(set(documents)-expected_paths)[:5]}",
        )
    changed = {Path(item).as_posix() for item in getattr(plan, "changed_paths", ())}
    if changed not in (set(), expected_paths):
        audit.error("plan_changed_paths", GENERATOR_REL, f"actual={len(changed)}")
    second = tuple(getattr(plan, "second_pass_changes", ()))
    if second:
        audit.error("plan_second_pass", GENERATOR_REL, repr(second[:10]))
    after_manifest = getattr(plan, "after_manifest", None)
    if not isinstance(after_manifest, Mapping) or len(after_manifest) != EXPECTED_AUTHORIZED:
        audit.error("plan_after_manifest", GENERATOR_REL, f"actual={len(after_manifest) if isinstance(after_manifest, Mapping) else 'invalid'}")
    else:
        for rel, value in documents.items():
            actual_hash = sha256_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
            if after_manifest.get(Path(rel)) != actual_hash:
                audit.error("plan_after_hash", rel, f"actual={actual_hash}, plan={after_manifest.get(Path(rel))}")

    expected_source_manifest = {
        "workbook": EXPECTED_WORKBOOK_SHA256,
        "workbook_cells": EXPECTED_CELL_MANIFEST_SHA256,
        "center_csv": COMMON_HASHES["센터정보 정리.csv"],
        "target_school_csv": COMMON_HASHES["타깃학교.csv"],
        "middle_helper": "8953f73fde05e6b6ffef4be605c8e25cc34e888b7edbb9021cda622d4ed9d773",
        "base_helper": "1fbba380481affe0b4f9888630f90caccb8bfca39342284819f8a2fb265d31cf",
    }
    source_manifest = dict(getattr(plan, "source_manifest", {}))
    if source_manifest != expected_source_manifest:
        audit.error("plan_source_manifest", GENERATOR_REL, repr(source_manifest))

    source_metrics = dict(getattr(plan, "source_metrics", {}))
    expected_source_metrics: dict[str, Any] = {
        "xlsx_bytes": 1_246_025,
        "sheets": 1,
        "cells": EXPECTED_LOCALITIES,
        "unique_cells": EXPECTED_LOCALITIES,
        "formula_cells": 0,
        "hyperlinks": 0,
        "merged_ranges": 0,
        "cell_manifest_sha256": EXPECTED_CELL_MANIFEST_SHA256,
        "sequence_sha256": EXPECTED_CELL_SEQUENCE_SHA256,
        "mapping_sha256": EXPECTED_CELL_MAPPING_SHA256,
        "manuscripts": EXPECTED_LOCALITIES,
        "title_exact": 274,
        "title_extended": 97,
        "source_h2": EXPECTED_H2,
        "h2_distribution": EXPECTED_H2_DISTRIBUTION,
        "source_body_paragraphs": EXPECTED_BODY_PARAGRAPHS,
        "intro_distribution": EXPECTED_INTRO_DISTRIBUTION,
        "source_faq": EXPECTED_FAQ,
        "faq_distribution": EXPECTED_FAQ_DISTRIBUTION,
        "source_review_blocks": EXPECTED_REVIEW_LINES,
        "source_summary_paragraphs": EXPECTED_SUMMARY_PARAGRAPHS,
        "unprefixed_faq_answers": 5,
        "visible_manuscript_corrections": 0,
        "supported_pages": EXPECTED_SUPPORTED,
        "unconfirmed_pages": EXPECTED_UNCONFIRMED,
        "high_school_chips": EXPECTED_SCHOOL_CHIPS,
        "missing_high_school_rows": EXPECTED_SCHOOL_GROUPS_MISSING,
        "exact_address_in_manuscript_pages": 282,
        "manuscript_visible_high_school_pairs": 882,
        "representative_sources": 371,
        "body_sources": 2,
        "map_sources": 371,
    }
    differences = {
        key: {"actual": source_metrics.get(key), "expected": expected}
        for key, expected in expected_source_metrics.items()
        if source_metrics.get(key) != expected
    }
    if differences:
        audit.error("plan_source_metrics", GENERATOR_REL, repr(differences))

    after_metrics = dict(getattr(plan, "after_metrics", {}))
    expected_after_metrics: dict[str, Any] = {
        "authorized_documents": EXPECTED_AUTHORIZED,
        "final_html_documents": EXPECTED_FINAL_HTML,
        "new_html_documents": EXPECTED_NEW_HTML,
        "new_category_hubs": EXPECTED_NEW_HUBS,
        "new_detail_documents": EXPECTED_NEW_DETAILS,
        "parent_hub_categories": 7,
        "sitemap_urls": EXPECTED_FINAL_HTML,
        "sitemap_existing_blocks_preserved": EXPECTED_BASE_HTML,
        "sitemap_new_urls_appended": EXPECTED_NEW_HTML,
        "sitemap_new_lastmod": RELEASE_DATE,
        "supported_service_offer_pages": EXPECTED_SUPPORTED,
        "unconfirmed_article_only_pages": EXPECTED_UNCONFIRMED,
        "high_school_chips": EXPECTED_SCHOOL_CHIPS,
        "internal_links_checked": 9_688,
        "second_pass_changes": 0,
    }
    after_differences = {
        key: {"actual": after_metrics.get(key), "expected": expected}
        for key, expected in expected_after_metrics.items()
        if after_metrics.get(key) != expected
    }
    if after_differences:
        audit.error("plan_after_metrics", GENERATOR_REL, repr(after_differences))
    if getattr(plan, "immutable_html_manifest_sha256", None) != BASE_IMMUTABLE_HTML_MANIFEST_SHA256:
        audit.error("plan_immutable_manifest", GENERATOR_REL, repr(getattr(plan, "immutable_html_manifest_sha256", None)))
    candidate = str(getattr(plan, "candidate_sha256", ""))
    if EXPECTED_CANDIDATE_SHA256 == "PENDING":
        audit.hold("candidate_pin_pending", GENERATOR_REL, f"actual={candidate}")
    elif candidate != EXPECTED_CANDIDATE_SHA256:
        audit.error("candidate_hash", GENERATOR_REL, f"actual={candidate}, expected={EXPECTED_CANDIDATE_SHA256}")
    audit.observations["plan"] = {
        "generator_sha256": sha256_file(root / GENERATOR_REL),
        "candidate_sha256": candidate,
        "authorized_documents": len(documents),
        "changed_paths": len(changed),
        "second_pass_changes": len(second),
        "source_manifest": source_manifest,
        "source_metrics": source_metrics,
        "after_metrics": after_metrics,
    }
    return View(root, documents)


def one_graph_node(
    graph: Sequence[Mapping[str, Any]],
    wanted: str,
    audit: Audit,
    location: str,
) -> Mapping[str, Any]:
    nodes = graph_nodes(graph, wanted)
    if len(nodes) != 1:
        audit.error("schema_type_count", location, f"type={wanted}, count={len(nodes)}")
        return {}
    return nodes[0]


def mapping_names(value: Any, wanted_type: str | None = None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        if wanted_type is not None and wanted_type not in node_types(item):
            continue
        result.append(norm(item.get("name")))
    return tuple(result)


def validate_document_head(
    dom: Element,
    expected_url: str,
    expected_title: str | None,
    expected_h1: str | None,
    audit: Audit,
    location: str,
) -> None:
    if canonical_values(dom) != [expected_url]:
        audit.error("canonical", location, repr(canonical_values(dom)))
    if meta_values(dom, prop="og:url") != [expected_url]:
        audit.error("og_url", location, repr(meta_values(dom, prop="og:url")))
    titles = find_elements(dom, "title")
    title_values = [node.text(visible=False) for node in titles]
    if expected_title is not None and title_values != [expected_title]:
        audit.error("html_title", location, repr(title_values))
    h1_values = [node.text() for node in find_elements(dom, "h1")]
    if len(h1_values) != 1:
        audit.error("h1_count", location, repr(h1_values))
    elif expected_h1 is not None and h1_values[0] != norm(expected_h1):
        audit.error("h1_exact", location, f"actual={h1_values[0]!r}, expected={expected_h1!r}")


def validate_parent_document(view: View, audit: Audit) -> None:
    location = PARENT_REL.as_posix()
    if not view.exists(PARENT_REL):
        audit.error("parent_missing", location, "missing")
        return
    document = view.text(PARENT_REL)
    dom = parse_dom(document, audit, location)
    if dom is None:
        return
    expected_url = encoded_url("학년별학원")
    validate_document_head(
        dom,
        expected_url,
        "학년별학원 안내 | 와와학습코칭센터 영어수학 전문학원",
        None,
        audit,
        location,
    )
    high2_href = "/학년별학원/고2수학학원/"
    if sum(node.attrs.get("href") == high2_href for node in find_elements(dom, "a")) != 1:
        audit.error("parent_high2_card", location, "expected one high2 category card")
    graph = json_graph(dom, audit, location)
    organization = one_graph_node(graph, "EducationalOrganization", audit, location)
    page = one_graph_node(graph, "CollectionPage", audit, location)
    one_graph_node(graph, "BreadcrumbList", audit, location)
    item_list = one_graph_node(graph, "ItemList", audit, location)
    one_graph_node(graph, "FAQPage", audit, location)
    if "고2 수학학원" not in organization.get("knowsAbout", []):
        audit.error("parent_knows_about", location, "고2 수학학원 missing")
    if page.get("url") != expected_url or page.get("dateModified") != RELEASE_DATE:
        audit.error("parent_page_identity", location, repr({"url": page.get("url"), "dateModified": page.get("dateModified")}))
    high2_url = encoded_url("학년별학원", "고2수학학원")
    has_part = page.get("hasPart")
    if not isinstance(has_part, list) or len(has_part) != 7:
        audit.error("parent_has_part", location, f"count={len(has_part) if isinstance(has_part, list) else 'invalid'}")
    elif sum(isinstance(item, Mapping) and item.get("name") == "고2 수학학원" and item.get("url") == high2_url for item in has_part) != 1:
        audit.error("parent_has_part_high2", location, "missing/excess")
    items = item_list.get("itemListElement")
    if item_list.get("numberOfItems") != 7 or not isinstance(items, list) or len(items) != 7:
        audit.error("parent_item_list", location, repr(item_list.get("numberOfItems")))
    elif (
        items[-1].get("position"), items[-1].get("name"), items[-1].get("url")
    ) != (7, "고2 수학학원", high2_url):
        audit.error("parent_item_list_high2", location, repr(items[-1]))


def validate_category_document(view: View, rows: Sequence[SourceRow], audit: Audit) -> None:
    location = CATEGORY_REL.as_posix()
    if not view.exists(CATEGORY_REL):
        audit.error("category_missing", location, "missing")
        return
    document = view.text(CATEGORY_REL)
    dom = parse_dom(document, audit, location)
    if dom is None:
        return
    expected_url = encoded_url("학년별학원", "고2수학학원")
    validate_document_head(
        dom,
        expected_url,
        "고2 수학학원 371개 지역 안내 | 와와학습코칭센터 영어수학 전문학원",
        None,
        audit,
        location,
    )
    h1_values = [node.text() for node in find_elements(dom, "h1")]
    if len(h1_values) == 1 and "고2 수학학원" not in h1_values[0]:
        audit.error("category_h1_topic", location, repr(h1_values[0]))
    graph = json_graph(dom, audit, location)
    organization = one_graph_node(graph, "EducationalOrganization", audit, location)
    page = one_graph_node(graph, "CollectionPage", audit, location)
    one_graph_node(graph, "BreadcrumbList", audit, location)
    item_list = one_graph_node(graph, "ItemList", audit, location)
    if "고2 수학학원" not in organization.get("knowsAbout", []):
        audit.error("category_knows_about", location, "고2 수학학원 missing")
    if page.get("url") != expected_url or page.get("datePublished") != RELEASE_DATE or page.get("dateModified") != RELEASE_DATE:
        audit.error("category_page_identity", location, repr({
            "url": page.get("url"), "datePublished": page.get("datePublished"), "dateModified": page.get("dateModified"),
        }))
    expected_items = tuple(
        (index, row.locality + " 고2 수학학원", encoded_url("학년별학원", "고2수학학원", row.locality))
        for index, row in enumerate(rows, 1)
    )
    raw_items = item_list.get("itemListElement")
    actual_items = tuple(
        (item.get("position"), item.get("name"), item.get("url"))
        for item in raw_items
        if isinstance(item, Mapping)
    ) if isinstance(raw_items, list) else ()
    if item_list.get("numberOfItems") != EXPECTED_LOCALITIES or actual_items != expected_items:
        audit.error("category_item_list", location, f"count={len(actual_items)}, order_match={actual_items == expected_items}")
    hrefs = Counter(node.attrs.get("href", "") for node in find_elements(dom, "a"))
    bad_links = [
        row.locality
        for row in rows
        if hrefs[f"/학년별학원/고2수학학원/{row.locality}/"] != 1
    ]
    if bad_links:
        audit.error("category_visible_links", location, repr(bad_links[:20]))


def source_node_texts(dom: Element, attribute: str) -> tuple[str, ...]:
    return tuple(node.text() for node in nodes_with_attr(dom, attribute))


def validate_detail_document(
    view: View,
    manuscript: Manuscript,
    row: SourceRow,
    audit: Audit,
) -> dict[str, int]:
    rel = detail_rel(row.locality)
    location = rel.as_posix()
    empty = {"h2": 0, "paragraphs": 0, "faq": 0, "reviews": 0, "schools": 0, "supported": 0, "unconfirmed": 0}
    if not view.exists(rel):
        audit.error("detail_missing", location, "missing")
        return empty
    try:
        document = view.text(rel)
    except (OSError, UnicodeError) as exc:
        audit.error("detail_utf8", location, repr(exc))
        return empty
    dom = parse_dom(document, audit, location)
    if dom is None:
        return empty
    expected_url = encoded_url("학년별학원", "고2수학학원", row.locality)
    validate_document_head(
        dom,
        expected_url,
        manuscript.title + " | 와와학습코칭센터 영어수학 전문학원",
        manuscript.title,
        audit,
        location,
    )
    if meta_values(dom, name="description") != [manuscript.meta]:
        audit.error("meta_description_exact", location, repr(meta_values(dom, name="description")))

    articles = nodes_with_attr(dom, "data-manuscript")
    if len(articles) != 1:
        audit.error("manuscript_article", location, f"count={len(articles)}")
    else:
        article = articles[0]
        expected_attrs = {
            "data-source-workbook-row": str(manuscript.row_number),
            "data-source-cell-sha256": manuscript.raw_sha256,
            "data-manuscript-sha256": manuscript.raw_sha256,
        }
        differences = {key: article.attrs.get(key) for key, expected in expected_attrs.items() if article.attrs.get(key) != expected}
        if differences:
            audit.error("manuscript_identity", location, repr(differences))

    headings = source_node_texts(dom, "data-source-heading")
    paragraphs = source_node_texts(dom, "data-source-paragraph")
    questions = source_node_texts(dom, "data-source-question")
    answers = source_node_texts(dom, "data-source-answer")
    reviews = source_node_texts(dom, "data-source-review")
    schools = source_node_texts(dom, "data-source-school")
    expected_questions = tuple(norm(faq.question_prefix + " " + faq.question) for faq in manuscript.faqs)
    expected_answers = tuple(norm((faq.answer_prefix + " " if faq.answer_prefix else "") + faq.answer) for faq in manuscript.faqs)
    exact_sequences = (
        ("heading", headings, tuple(norm(value) for value in manuscript.headings)),
        ("paragraph", paragraphs, tuple(norm(value) for value in manuscript.paragraphs)),
        ("faq_question", questions, expected_questions),
        ("faq_answer", answers, expected_answers),
        ("review", reviews, tuple(norm(value) for value in manuscript.review_lines)),
        ("school", schools, tuple(norm(value) for value in row.high_schools)),
    )
    for label, actual, expected in exact_sequences:
        if actual != expected:
            audit.error("source_visible_" + label, location, f"actual_count={len(actual)}, expected_count={len(expected)}")
    if len(nodes_with_attr(dom, "data-manuscript-faq")) != 1 or len(nodes_with_attr(dom, "data-manuscript-review")) != 1:
        audit.error("source_section_hooks", location, "FAQ/review outer hook mismatch")
    if len(nodes_with_attr(dom, "data-source-field", "high-schools")) != 1 or nodes_with_attr(dom, "data-source-field", "middle-schools"):
        audit.error("source_school_field", location, "high-school identity hook mismatch")
    visible = dom.text()
    leaking_markers = [marker for marker in MARKERS if marker in visible]
    if leaking_markers:
        audit.error("source_marker_visible", location, repr(leaking_markers))
    if manuscript.row_number == 108 and visible.count("금곡동 금곡동") != 1:
        audit.error("source_repeat_not_preserved", location, f"count={visible.count('금곡동 금곡동')}")

    graph = json_graph(dom, audit, location)
    ids = [node.get("@id") for node in graph if isinstance(node.get("@id"), str)]
    if len(ids) != len(set(ids)):
        audit.error("schema_duplicate_id", location, "duplicate top-level @id")
    webpage = one_graph_node(graph, "WebPage", audit, location)
    organization = one_graph_node(graph, "EducationalOrganization", audit, location)
    business = one_graph_node(graph, "LocalBusiness", audit, location)
    breadcrumb = one_graph_node(graph, "BreadcrumbList", audit, location)
    article_schema = one_graph_node(graph, "Article", audit, location)
    faq_schema = one_graph_node(graph, "FAQPage", audit, location)
    one_graph_node(graph, "ItemList", audit, location)
    one_graph_node(graph, "ImageObject", audit, location)

    if webpage.get("url") != expected_url:
        audit.error("webpage_url", location, repr(webpage.get("url")))
    for key in ("about", "mentions", "hasPart"):
        if not isinstance(webpage.get(key), list) or not webpage.get(key):
            audit.error("webpage_" + key, location, "missing/empty")
    if article_schema.get("headline") != manuscript.title:
        audit.error("article_headline", location, repr(article_schema.get("headline")))
    if article_schema.get("description") != manuscript.summary:
        audit.error("article_description_exact", location, "JSON-LD summary differs from workbook")
    if article_schema.get("articleSection") != list(manuscript.headings):
        audit.error("article_section", location, repr(article_schema.get("articleSection")))
    for key in ("about", "mentions", "hasPart"):
        if not isinstance(article_schema.get(key), list) or not article_schema.get(key):
            audit.error("article_" + key, location, "missing/empty")
    article_parts = mapping_names(article_schema.get("hasPart"), "WebPageElement")
    if article_parts != manuscript.headings:
        audit.error("article_has_part", location, f"actual={article_parts!r}")
    mentioned_schools = mapping_names(article_schema.get("mentions"), "EducationalOrganization")
    if mentioned_schools != row.high_schools:
        audit.error("article_school_mentions", location, f"actual={mentioned_schools!r}, expected={row.high_schools!r}")
    expected_faq = tuple((norm(faq.question), norm(faq.answer)) for faq in manuscript.faqs)
    if faq_schema_pairs(faq_schema) != expected_faq:
        audit.error("faq_schema_exact", location, "schema FAQ differs from workbook")
    if article_schema.get("datePublished") != RELEASE_DATE or article_schema.get("dateModified") != RELEASE_DATE:
        audit.error("article_dates", location, repr((article_schema.get("datePublished"), article_schema.get("dateModified"))))

    for label, node in (("organization", organization), ("business", business)):
        address = node.get("address")
        actual_address = address.get("streetAddress") if isinstance(address, Mapping) else None
        identifier = node.get("identifier")
        actual_registration = identifier.get("value") if isinstance(identifier, Mapping) else None
        facts = (node.get("name"), node.get("telephone"), actual_address, actual_registration)
        expected_facts = (row.center_name, row.telephone, row.address, row.registration)
        if facts != expected_facts:
            audit.error("schema_common_" + label, location, f"actual={facts!r}, expected={expected_facts!r}")
    breadcrumb_items = breadcrumb.get("itemListElement")
    actual_breadcrumb = tuple(
        (item.get("position"), item.get("name"), item.get("item"))
        for item in breadcrumb_items
        if isinstance(item, Mapping)
    ) if isinstance(breadcrumb_items, list) else ()
    expected_breadcrumb = (
        (1, "홈", BASE_URL + "/"),
        (2, "학년별학원", encoded_url("학년별학원")),
        (3, "고2 수학학원", encoded_url("학년별학원", "고2수학학원")),
        (4, manuscript.title, expected_url),
    )
    if actual_breadcrumb != expected_breadcrumb:
        audit.error("breadcrumb_exact", location, repr(actual_breadcrumb))

    services = graph_nodes(graph, "Service")
    offers = graph_nodes(graph, "Offer")
    if row.supported:
        if len(services) != 1 or len(offers) != 1:
            audit.error("supported_service_offer", location, f"service={len(services)}, offer={len(offers)}")
        else:
            audience = services[0].get("audience")
            if not isinstance(audience, Mapping) or audience.get("audienceType") != "고등학교 2학년(고2)":
                audit.error("service_audience", location, repr(audience))
            if services[0].get("areaServed", {}).get("name") != row.locality:
                audit.error("service_area", location, repr(services[0].get("areaServed")))
            if offers[0].get("url") != row.fee_url:
                audit.error("offer_url", location, repr(offers[0].get("url")))
        for label, node in (("organization", organization), ("business", business)):
            makes_offer = node.get("makesOffer")
            if not isinstance(makes_offer, list) or len(makes_offer) != 1:
                audit.error("makes_offer_" + label, location, repr(makes_offer))
    else:
        if services or offers:
            audit.error("unconfirmed_service_offer", location, f"service={len(services)}, offer={len(offers)}")
        forbidden = [
            (node.get("@id"), key)
            for node in walk_json(graph)
            for key in ("makesOffer", "offers")
            if key in node
        ]
        if forbidden:
            audit.error("unconfirmed_offer_claim", location, repr(forbidden))

    return {
        "h2": len(headings),
        "paragraphs": len(paragraphs),
        "faq": len(questions),
        "reviews": len(reviews),
        "schools": len(schools),
        "supported": int(row.supported),
        "unconfirmed": int(not row.supported),
    }


def git_blob(root: Path, ref: str, rel: Path, audit: Audit) -> bytes | None:
    try:
        process = subprocess.run(
            ["git", "show", f"{ref}:{rel.as_posix()}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        audit.error("git_blob", rel, repr(exc))
        return None
    if process.returncode:
        audit.error("git_blob", rel, process.stderr.decode("utf-8", "replace").strip())
        return None
    return process.stdout


def sitemap_blocks(document: str, audit: Audit, location: str) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    for raw in RAW_URL_BLOCK.findall(document):
        locations = LOC.findall(raw)
        lastmods = LASTMOD.findall(raw)
        if len(locations) != 1 or len(lastmods) != 1:
            audit.error("sitemap_block", location, "malformed URL block")
            continue
        result.append((html.unescape(locations[0]), html.unescape(lastmods[0]), raw))
    return tuple(result)


def expected_llms_block() -> str:
    lines = [
        LLMS_MARKER,
        "",
        f"- 학년별학원: {BASE_URL}/학년별학원/",
        "  - 중1·중2·중3 영어·수학과 고2 수학 지역 안내를 학년과 과목별로 찾는 핵심 허브입니다.",
    ]
    for label, slug, grade, subject in GRADE_CATEGORIES:
        lines.extend((
            f"- {label}: {BASE_URL}/학년별학원/{slug}/",
            f"  - {grade} {subject} 진단·학교 자료·오답 재학습·상담 기준을 371개 동네별 원고로 안내합니다.",
        ))
    return "\n".join(lines) + "\n"


def validate_sitemap_and_llms(view: View, root: Path, rows: Sequence[SourceRow], audit: Audit) -> None:
    base_sitemap_bytes = git_blob(root, EXPECTED_BASE_HEAD, SITEMAP_REL, audit)
    base_llms_bytes = git_blob(root, EXPECTED_BASE_HEAD, LLMS_REL, audit)
    if base_sitemap_bytes is None or base_llms_bytes is None:
        return
    def checkout_bytes(value: bytes, expected: str, location: Path) -> bytes:
        candidates = (value, value.replace(b"\n", b"\r\n"))
        for candidate in candidates:
            if sha256_bytes(candidate) == expected:
                return candidate
        audit.error("base_checkout_pin", location, repr([sha256_bytes(item) for item in candidates]))
        return value

    base_sitemap_bytes = checkout_bytes(base_sitemap_bytes, BASE_SITEMAP_SHA256, SITEMAP_REL)
    base_llms_bytes = checkout_bytes(base_llms_bytes, BASE_LLMS_SHA256, LLMS_REL)
    try:
        base_sitemap = base_sitemap_bytes.decode("utf-8")
        final_sitemap = view.text(SITEMAP_REL)
        base_llms = base_llms_bytes.decode("utf-8")
        final_llms = view.text(LLMS_REL)
    except (OSError, UnicodeError) as exc:
        audit.error("discovery_utf8", "sitemap/llms", repr(exc))
        return
    base_blocks = sitemap_blocks(base_sitemap, audit, "base sitemap")
    final_blocks = sitemap_blocks(final_sitemap, audit, "final sitemap")
    new_urls = (
        encoded_url("학년별학원", "고2수학학원"),
        *(encoded_url("학년별학원", "고2수학학원", row.locality) for row in rows),
    )
    if len(base_blocks) != EXPECTED_BASE_HTML or len(final_blocks) != EXPECTED_FINAL_HTML:
        audit.error("sitemap_count", SITEMAP_REL, f"base={len(base_blocks)}, final={len(final_blocks)}")
    if tuple(item[2] for item in final_blocks[:len(base_blocks)]) != tuple(item[2] for item in base_blocks):
        audit.error("sitemap_existing_blocks", SITEMAP_REL, "base blocks changed/reordered")
    appended = final_blocks[len(base_blocks):]
    if tuple(item[0] for item in appended) != new_urls:
        audit.error("sitemap_new_order", SITEMAP_REL, f"count={len(appended)}")
    if any(item[1] != RELEASE_DATE for item in appended):
        audit.error("sitemap_new_lastmod", SITEMAP_REL, "new lastmod mismatch")
    locations = [item[0] for item in final_blocks]
    if len(locations) != len(set(locations)):
        audit.error("sitemap_duplicates", SITEMAP_REL, "duplicate loc")

    if base_llms.count(LLMS_MARKER) != 1:
        audit.error("base_llms_marker", LLMS_REL, f"count={base_llms.count(LLMS_MARKER)}")
    else:
        prefix = base_llms[:base_llms.index(LLMS_MARKER)]
        expected_llms = prefix + expected_llms_block()
        if final_llms != expected_llms:
            audit.error("llms_exact", LLMS_REL, "prefix or canonical grade block differs")


def view_manifest(view: View, paths: Iterable[str]) -> str:
    return sha256_bytes("".join(
        rel + "\0" + sha256_bytes(view.bytes(rel)) + "\n"
        for rel in sorted(paths)
    ).encode("utf-8"))


def validate_release_manifests(view: View, rows: Sequence[SourceRow], audit: Audit) -> None:
    authorized = expected_authorized_paths(rows)
    new_html = expected_new_paths(rows)
    all_html = enumerate_html(view.root) | {
        rel for rel in view.overrides if rel.endswith(".html")
    }
    values = {
        "authorized": (view_manifest(view, authorized), EXPECTED_RELEASE_AUTHORIZED_MANIFEST_SHA256),
        "new_html": (view_manifest(view, new_html), EXPECTED_RELEASE_NEW_HTML_MANIFEST_SHA256),
        "all_html": (view_manifest(view, all_html), EXPECTED_RELEASE_ALL_HTML_MANIFEST_SHA256),
    }
    if len(all_html) != EXPECTED_FINAL_HTML:
        audit.error("release_html_count", view.root, f"actual={len(all_html)}, expected={EXPECTED_FINAL_HTML}")
    for label, (actual, expected) in values.items():
        if expected == "PENDING":
            audit.hold("release_manifest_pin_pending", label, f"actual={actual}")
        elif actual != expected:
            audit.error("release_manifest", label, f"actual={actual}, expected={expected}")
    audit.observations["release_manifests"] = {label: actual for label, (actual, _) in values.items()}


def validate_rendered_tree(
    view: View,
    root: Path,
    rows: Sequence[SourceRow],
    manuscripts: Sequence[Manuscript],
    audit: Audit,
) -> None:
    expected = expected_authorized_paths(rows)
    missing = [rel for rel in sorted(expected) if not view.exists(rel)]
    if missing:
        audit.error("authorized_missing", root, repr(missing[:20]))
        return
    validate_parent_document(view, audit)
    validate_category_document(view, rows, audit)
    totals: Counter[str] = Counter()
    for manuscript, row in zip(manuscripts, rows, strict=True):
        totals.update(validate_detail_document(view, manuscript, row, audit))
    expected_totals = {
        "h2": EXPECTED_H2,
        "paragraphs": EXPECTED_BODY_PARAGRAPHS,
        "faq": EXPECTED_FAQ,
        "reviews": EXPECTED_REVIEW_LINES,
        "schools": EXPECTED_SCHOOL_CHIPS,
        "supported": EXPECTED_SUPPORTED,
        "unconfirmed": EXPECTED_UNCONFIRMED,
    }
    if dict(totals) != expected_totals:
        audit.error("rendered_aggregate", CATEGORY_ROOT, f"actual={dict(totals)!r}, expected={expected_totals!r}")
    validate_sitemap_and_llms(view, root, rows, audit)
    validate_release_manifests(view, rows, audit)
    audit.observations["rendered"] = dict(totals)


def run_self_test(audit: Audit) -> None:
    try:
        assert encoded_url("학년별학원", "고2수학학원", "명일동") == (
            "https://wawa-center.kr/%ED%95%99%EB%85%84%EB%B3%84%ED%95%99%EC%9B%90/"
            "%EA%B3%A02%EC%88%98%ED%95%99%ED%95%99%EC%9B%90/%EB%AA%85%EC%9D%BC%EB%8F%99/"
        )
        parser = DOMParser()
        parser.feed('<html><head><title>A &amp; B</title></head><body><h1>X <em>Y</em></h1><p data-x="1">A<br>B</p></body></html>')
        assert [node.text(visible=False) for node in find_elements(parser.root, "title")] == ["A & B"]
        assert [node.text() for node in find_elements(parser.root, "h1")] == ["X Y"]
        assert source_node_texts(parser.root, "data-x") == ("A B",)
        assert split_csv_tokens("A, B,A") == ("A", "B")
    except AssertionError as exc:
        audit.error("self_test", "auditor", repr(exc))


def default_inputs() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    desktop = Path.home() / "Desktop"
    workbook = desktop / "고2 수학학원.xlsx"
    common = desktop / "홈페이지 정리" / "참고자료" / "공통자료"
    return root, workbook, common


def run_audit(root: Path, workbook: Path, common: Path, mode: str, *, self_test: bool = False) -> Audit:
    audit = Audit()
    if self_test:
        run_self_test(audit)
    root = root.resolve()
    if root.is_symlink() or not root.is_dir():
        audit.error("root", root, "root must be a regular directory")
        return audit
    rows = load_common(common.resolve(), audit)
    cells = load_workbook_cells(workbook, audit)
    manuscripts = validate_source_contract(cells, rows, audit) if rows and cells else ()
    if mode == "source" or not rows or not manuscripts:
        return audit
    state = validate_baseline(root, rows, audit)
    if mode == "actual":
        if state != "release":
            audit.hold("materialization_pending", CATEGORY_ROOT, f"state={state}")
            return audit
        validate_rendered_tree(View(root), root, rows, manuscripts, audit)
        return audit
    if mode == "actual-release":
        if state != "release":
            audit.error("release_not_materialized", CATEGORY_ROOT, f"state={state}")
            return audit
        validate_rendered_tree(View(root), root, rows, manuscripts, audit)
        projected = build_projected_view(root, workbook, common, rows, audit)
        if projected is not None:
            validate_rendered_tree(projected, root, rows, manuscripts, audit)
        return audit
    if mode == "projected":
        projected = build_projected_view(root, workbook, common, rows, audit)
        if projected is not None:
            validate_rendered_tree(projected, root, rows, manuscripts, audit)
        return audit
    audit.error("mode", mode, "unsupported")
    return audit


def payload(audit: Audit) -> dict[str, Any]:
    return {
        "status": audit.status,
        "errors": audit.errors,
        "holds": audit.holds,
        "observations": audit.observations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    default_root, default_workbook, default_common = default_inputs()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--workbook", type=Path, default=default_workbook)
    parser.add_argument("--common-dir", type=Path, default=default_common)
    parser.add_argument("--mode", choices=("source", "actual", "projected", "actual-release"), default="actual")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    audit = run_audit(args.root, args.workbook, args.common_dir, args.mode, self_test=args.self_test)
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
