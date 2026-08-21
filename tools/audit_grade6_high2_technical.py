#!/usr/bin/env python3
"""Read-only technical/release gate for the grade-6 and high-2 English batch.

The three attached workbooks are treated only as data.  The auditor parses
their OOXML containers without evaluating formulas, links, macros, or embedded
instructions.  It imports the generator only to obtain an in-memory plan and
never calls its apply path.  Projection, repeat, idempotent second-pass, and
reverse-input runs must be byte-identical before a release can pass.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import html
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, unquote, urljoin, urlsplit
from zipfile import ZipFile


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://wawa-center.kr"
HOSTS = {"wawa-center.kr", "www.wawa-center.kr"}
BASELINE_COMMIT = "b6a680b724db91246364e012597f92f385f2f0bd"
BASELINE_TREE = "9653f522cdc66f993e1f47dbf4e9f4d75e80df70"
BASELINE_HTML_COUNT = 17_229
BASELINE_TRACKED_COUNT = 20_656
IMMUTABLE_HTML_COUNT = 17_228
EXISTING_HIGH2_MATH_HTML_COUNT = 372
NEW_CATEGORY_COUNT = 3
DETAILS_PER_CATEGORY = 371
NEW_DETAIL_COUNT = 1_113
NEW_HTML_COUNT = 1_116
PLAN_DOCUMENT_COUNT = 1_119
FINAL_HTML_COUNT = 18_345
RELEASE_CHANGE_COUNT = 1_122
FINAL_TRACKED_COUNT = 21_775
GRADE_ACTIVE_COUNT = 3_721
RELEASE_DATE = "2026-08-21"

PARENT_REL = "학년별학원/index.html"
PARENT_ROUTE = "/" + quote("학년별학원", safe="") + "/"
GENERATOR_REL = "tools/generate_grade6_high2_pages.py"
CONTENT_AUDITOR_REL = "tools/audit_grade6_high2_content.py"
TECHNICAL_AUDITOR_REL = "tools/audit_grade6_high2_technical.py"
SITEMAP_REL = "sitemap.xml"
LLMS_REL = "llms.txt"
ROBOTS_REL = "robots.txt"
VERCEL_REL = "vercel.json"
HEADER_CSS_REL = "assets/header.css"

EXPECTED_CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
EXPECTED_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"
EXPECTED_COMMON_SNAPSHOT = (
    "18f93e215247e5089b4a7e20677e3e860165f1104007965b6d89e6980e5a6e21",
    640,
    119_418_807,
)
EXPECTED_LOCALITY_SEQUENCE_SHA256 = "c800e886954b8198cc6425e6907632a62d69e4cf195abeaeaafd1b54094b9767"
BASE_IMMUTABLE_HTML_MANIFEST = "b5eeb32768bc8403acf484d90cfd3dad52de7aa5df3a60e355e6abceca3fb0da"
BASE_HIGH2_MATH_MANIFEST = "d074db4c9e7defa99fc2ee6232c2279c9b6f767e253ceca0797f988878656429"
BASE_SITEMAP_BLOB_SHA256 = "1492469aa7865f9d97b06fadeae9202cc513c8ceaa8edb52d071f39a501ee857"
BASE_LLMS_BLOB_SHA256 = "935cec8925614ac155b1325a5e75b360c9c552e86a427bed124ca407b27f1db3"
BASELINE_JSONLD_BLOCK_COUNT = 23_275
FINAL_JSONLD_BLOCK_COUNT = 24_391

# Independently frozen after generator repetition/reversal and content review.
APPROVED_GENERATOR_SHA256 = "a2e8b21628ecc28d8e225c798ae615bef1b04c4c21bc52a9af89bebc3baa12d5"
APPROVED_CONTENT_AUDITOR_SHA256 = "959e534db259f51c030705c18b6afe8441e72e9c93ed68cbb6a963b5563f6ee8"
APPROVED_PLAN_CANDIDATE_SHA256 = "bc06615e55c11275b53f112f706a798968442da6550d634a6cd7e5053487a929"
APPROVED_PROJECTED_MANIFEST = "f5dd43576ef1d082b78d7af209bb729b690c072b894e638e9d8e8e827e6f1019"


@dataclass(frozen=True)
class Category:
    key: str
    grade: str
    subject: str
    slug: str
    hook: str
    workbook_name: str
    workbook_sha256: str
    workbook_bytes: int
    supported: int
    unconfirmed: int
    school_field: str
    school_hook: str
    school_provided: int
    school_missing: int
    exact_titles: int

    @property
    def label(self) -> str:
        return f"{self.grade} {self.subject}학원"

    @property
    def category_rel(self) -> str:
        return f"학년별학원/{self.slug}/index.html"

    @property
    def category_route(self) -> str:
        return PARENT_ROUTE + quote(self.slug, safe="") + "/"


CATEGORIES: tuple[Category, ...] = (
    Category(
        "elementary6_math", "초6", "수학", "초6수학학원", "elementary6-math",
        "초6 수학학원.xlsx", "7820827f61a9b91c80d9cc3b0a68b018b2e8eed1154d1eebe659f3df4e8fe6a3",
        1_228_435, 358, 13, "타깃학교(초)", "elementary-schools", 297, 74, 247,
    ),
    Category(
        "elementary6_english", "초6", "영어", "초6영어학원", "elementary6-english",
        "초6 영어학원.xlsx", "f507fab48c0e18303574eb78cdc5133c0ab2b1c72351fb40e31db5bc8f147148",
        1_255_108, 363, 8, "타깃학교(초)", "elementary-schools", 297, 74, 254,
    ),
    Category(
        "high2_english", "고2", "영어", "고2영어학원", "high2-english",
        "고2 영어학원.xlsx", "828bea4e58bc9d8192d0e1b0ce8d8be1c8749bdcdf5eb418aabf0ddcb622df26",
        1_248_002, 332, 39, "타깃학교(고)", "high-schools", 308, 63, 285,
    ),
)
CATEGORY_BY_KEY = {item.key: item for item in CATEGORIES}
CATEGORY_BY_SLUG = {item.slug: item for item in CATEGORIES}

PARENT_CATEGORY_SLUGS = (
    "초6수학학원", "초6영어학원",
    "중1수학학원", "중1영어학원", "중2수학학원", "중2영어학원",
    "중3수학학원", "중3영어학원", "고2수학학원", "고2영어학원",
)
PARENT_CATEGORY_ROUTES = tuple(PARENT_ROUTE + quote(item, safe="") + "/" for item in PARENT_CATEGORY_SLUGS)
EXPECTED_NAV_TARGETS = (
    "/", "/overview/", "/guide/", "/" + quote("교육정보", safe="") + "/",
    "/" + quote("학부모후기", safe="") + "/",
    "/" + quote("과목별학원", safe="") + "/", PARENT_ROUTE, "/center/",
)

KNOWN_BROKEN_ROUTE = "/" + "/".join(quote(value, safe="") for value in ("교육정보", "수학-단어-암기법")) + "/"
KNOWN_BROKEN_OCCURRENCES = 1
KNOWN_EXTERNAL_IMAGE = "https://wawa-center.com/wp-content/uploads/2026/06/M370.jpg"
KNOWN_EXTERNAL_IMAGE_OCCURRENCES = 1
KNOWN_BULK_HIDDEN_IMAGES = 6_307
KNOWN_MISSING_DIMENSION_IMAGES = 43_407
KNOWN_LEGACY_RAW_CANONICALS = 28

BROWSER_WIDTHS = (320, 390, 900, 901, 1024, 1120, 1121, 1440)
BROWSER_ROUTE_COUNT = 10
BROWSER_TEST_COUNT = 80
BROWSER_HUB_TEST_COUNT = 24
PRUNED_DIRS = {".git", ".vercel", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
IGNORED_SCHEMES = ("tel:", "sms:", "mailto:", "javascript:", "data:", "blob:")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DANGEROUS_RE = re.compile(
    r"<(?:script|style|iframe|object|embed|form|base|link|meta|template)\b|"
    r"\b(?:on[a-z]+|style)\s*=|(?:href|src|action)\s*=\s*[\"']?\s*javascript:", re.I,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.I),
)
ALLOWED_BASELINE_RESIDUE = {
    "tmp/__pycache__/generate_topic_child_pages.cpython-313.pyc":
        "3902772278900f03b38fab62e8a638152716069e466472b8ad50c700dfd5d1b5",
}
TRANSACTION_PREFIXES = (
    ".grade3-math-transaction-", ".middle-grade-transaction-",
    ".high2-math-transaction-", ".grade6-high2-transaction-",
)
RESIDUE_SUFFIXES = (".pyc", ".pyo", ".txn", ".journal", ".rollback", ".partial", ".bak", ".tmp")

PROTECTED_PINS = {
    "index.html": "a53e0cbc0b5db103dfa5f80b99819a53647ef17f02463946528d20ffdf9e29f5",
    HEADER_CSS_REL: "2a4bf6dc5520ef8c194087a6530deca17eedf744933286a3c220249308ab00c7",
    ROBOTS_REL: "8885ec5209a9731d33a7c774d489fe59de13182ee277bcb130f2987ce12e1794",
    VERCEL_REL: "64cc7a45a72a46477323ebfb2d4cac71d2a67e3012078d79093c18c60e51e53d",
    "tools/generate_grade3_math_pages.py": "3f16b2834ef503c239ea01bd5300599976692c4d933ba72382d931924acf1d33",
    "tools/audit_grade3_math_content.py": "895370c5a46ba9374123d0d9f6a644b7ab0d9cc009f40ea2d0696bf3b71f4865",
    "tools/audit_grade3_math_technical.py": "d3f098505622127dfda5ca594b3f4251385ef99b8f5e691f31abe3222e0d68b5",
    "tools/generate_middle_grade_pages.py": "46874729b875197b7b4c5dfc6f302aa720bf5388d2ba4d32593008346a1b36cf",
    "tools/audit_middle_grade_content.py": "086273c5529ebf406624a987a7e8a231233380b912b5df6b5f2aaba528de57c6",
    "tools/audit_middle_grade_technical.py": "16c74311e7e9edb34b66b1624ada303da53d097c40cc662368e2831a92bbf91c",
    "tools/generate_high2_math_pages.py": "834141ca0fb02218bbee64c095e3053a72cc80d1cdf326fd137c51976240bbe3",
    "tools/audit_high2_math_content.py": "17b9c926baa0c4fc5a7e382fc8dbc4792de457d31b36e0ca74350ce111ddd4e9",
    "tools/audit_high2_math_technical.py": "9877241cb7f1d418b1c6755f59d04ac5def772589accb32f1edb8fd7c87d3aa0",
}


def _load_base() -> ModuleType:
    path = ROOT / "tools" / "audit_middle_grade_technical.py"
    name = "_grade6_high2_technical_base_" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import technical base: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    for key, value in {
        "ROOT": ROOT, "DOMAIN": DOMAIN, "HOSTS": HOSTS,
        "BASELINE_COMMIT": BASELINE_COMMIT, "BASELINE_TREE": BASELINE_TREE,
        "BASELINE_HTML_COUNT": BASELINE_HTML_COUNT, "BASELINE_TRACKED_COUNT": BASELINE_TRACKED_COUNT,
        "FINAL_HTML_COUNT": FINAL_HTML_COUNT, "FINAL_TRACKED_COUNT": FINAL_TRACKED_COUNT,
        "BROWSER_WIDTHS": BROWSER_WIDTHS, "BROWSER_TEST_COUNT": BROWSER_TEST_COUNT,
        "BROWSER_HUB_TEST_COUNT": BROWSER_HUB_TEST_COUNT,
    }.items():
        setattr(module, key, value)
    return module


BASE = _load_base()
Audit = BASE.Audit
Projection = BASE.Projection
sha256 = BASE.sha256
normalized_text = BASE.normalized_text
run_git = BASE.run_git
baseline_paths = BASE.baseline_paths
git_blobs_batch = BASE.git_blobs_batch
fs_bytes = BASE.fs_bytes
manifest = BASE.manifest
tree_snapshot = BASE.tree_snapshot
directory_snapshot = BASE.directory_snapshot
route_for_relative = BASE.route_for_relative
normalize_route = BASE.normalize_route
parse_document = BASE.parse_document
nav_fragment = BASE.nav_fragment
nav_entries = BASE.nav_entries
data_nodes = BASE.data_nodes
schema_nodes = BASE.schema_nodes
type_has = BASE.type_has
visible_faq = BASE.visible_faq
schema_faq = BASE.schema_faq
parse_sitemap = BASE.parse_sitemap
normalize_relative = BASE.normalize_relative
normalize_documents = BASE.normalize_documents
normalize_changed = BASE.normalize_changed
normalize_hashes = BASE.normalize_hashes
compare_plan_streaming = BASE.compare_plan_streaming


@dataclass(frozen=True)
class SourceSet:
    workbook_paths: Mapping[str, Path]
    workbook_hashes: Mapping[str, str]
    localities: tuple[str, ...]
    manuscripts: Mapping[str, tuple[str, ...]]

    @property
    def locality_set(self) -> frozenset[str]:
        return frozenset(self.localities)


@dataclass(frozen=True)
class Authority:
    english: Mapping[str, tuple[str, ...]]
    math: Mapping[str, tuple[str, ...]]
    elementary_schools: Mapping[str, str]
    high_schools: Mapping[str, str]

    def levels(self, category: Category, locality: str) -> tuple[str, ...] | None:
        values = self.english if category.subject == "영어" else self.math
        return values.get(locality)

    def school(self, category: Category, locality: str) -> str:
        values = self.elementary_schools if category.grade.startswith("초") else self.high_schools
        return values.get(locality, "")


@dataclass(frozen=True)
class DetailReport:
    relative: str
    route: str
    category: Category
    locality: str
    status: str
    school_missing: bool


def _csv_header(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r", "").replace("\n", "").strip()


def _csv_tokens(value: str) -> tuple[str, ...]:
    values = (unicodedata.normalize("NFC", item.strip()) for item in value.split(","))
    return tuple(dict.fromkeys(item for item in values if item))


def discover_common_dir(root: Path, supplied: Path | None) -> Path:
    candidates = (
        supplied, root.parent / "참고자료" / "공통자료",
        root.parent.parent / "참고자료" / "공통자료",
        Path.home() / "Desktop" / "홈페이지 정리" / "참고자료" / "공통자료",
    )
    for path in candidates:
        if path is not None and path.is_dir():
            return path.resolve()
    raise RuntimeError("common data directory not found; pass --common-dir")


def _read_csv(path: Path, expected_sha: str, audit: Audit, code: str) -> tuple[list[str], list[dict[str, str]]]:
    audit.hard(path.is_file(), code + "_missing", str(path))
    if not path.is_file():
        return [], []
    raw = path.read_bytes()
    audit.hard(sha256(raw) == expected_sha, code + "_sha256", {"expected": expected_sha, "actual": sha256(raw)})
    try:
        source = raw.decode("utf-8-sig")
        controls = CONTROL_RE.findall(source)
        audit.hard(controls in ([], ["\x08"]), code + "_control_baseline", controls)
        source = source.replace("\x08", "")
        reader = csv.DictReader(io.StringIO(source, newline=""))
        originals = reader.fieldnames or []
        headers = [_csv_header(item) for item in originals]
        audit.hard(len(headers) == len(set(headers)), code + "_unique_headers", headers)
        rows: list[dict[str, str]] = []
        malformed: list[Any] = []
        for number, raw_row in enumerate(reader, 2):
            if None in raw_row:
                malformed.append({"row": number, "reason": "excess-fields"})
                continue
            rows.append({
                normalized: unicodedata.normalize("NFC", (raw_row[original] or "").strip())
                for original, normalized in zip(originals, headers)
            })
        audit.extend(code + "_malformed", malformed)
        return headers, rows
    except (UnicodeError, csv.Error) as exc:
        audit.hard(False, code + "_parse", f"{type(exc).__name__}: {exc}")
        return [], []


def load_authority(common_dir: Path, audit: Audit) -> tuple[tuple[str, ...], Authority]:
    center_headers, center_rows = _read_csv(
        common_dir / "센터정보 정리.csv", EXPECTED_CENTER_CSV_SHA256, audit, "center_csv"
    )
    school_headers, school_rows = _read_csv(
        common_dir / "타깃학교.csv", EXPECTED_SCHOOL_CSV_SHA256, audit, "school_csv"
    )
    locality_field = "근처 수업가능 동네"
    center_required = {locality_field, "가능학년(영어)", "가능학년(수학)"}
    school_required = {locality_field, "타깃학교(초)", "타깃학교(고)"}
    audit.hard(center_required <= set(center_headers), "center_csv_headers", center_headers)
    audit.hard(school_required <= set(school_headers), "school_csv_headers", school_headers)
    audit.hard(len(center_rows) == DETAILS_PER_CATEGORY, "center_csv_rows", len(center_rows))
    audit.hard(len(school_rows) == DETAILS_PER_CATEGORY, "school_csv_rows", len(school_rows))
    localities = tuple(row.get(locality_field, "") for row in center_rows)
    audit.hard(len(localities) == DETAILS_PER_CATEGORY and len(set(localities)) == DETAILS_PER_CATEGORY and all(localities), "authority_localities")
    locality_sequence = sha256("\n".join(localities).encode("utf-8"))
    audit.hard(locality_sequence == EXPECTED_LOCALITY_SEQUENCE_SHA256, "authority_locality_sequence", {"expected": EXPECTED_LOCALITY_SEQUENCE_SHA256, "actual": locality_sequence})
    english = {row[locality_field]: _csv_tokens(row.get("가능학년(영어)", "")) for row in center_rows if row.get(locality_field)}
    math_values = {row[locality_field]: _csv_tokens(row.get("가능학년(수학)", "")) for row in center_rows if row.get(locality_field)}
    elementary = {row.get(locality_field, ""): row.get("타깃학교(초)", "") for row in school_rows if row.get(locality_field)}
    high = {row.get(locality_field, ""): row.get("타깃학교(고)", "") for row in school_rows if row.get(locality_field)}
    audit.hard(set(english) == set(math_values) == set(elementary) == set(high) == set(localities), "authority_locality_parity")
    status: dict[str, dict[str, int]] = {}
    schools: dict[str, dict[str, int]] = {}
    for category in CATEGORIES:
        levels = english if category.subject == "영어" else math_values
        supported = sum(category.grade in values for values in levels.values())
        school_values = elementary if category.grade.startswith("초") else high
        provided = sum(bool(value) for value in school_values.values())
        audit.hard(supported == category.supported and DETAILS_PER_CATEGORY - supported == category.unconfirmed, "authority_supported", {"category": category.key, "actual": supported})
        audit.hard(provided == category.school_provided and DETAILS_PER_CATEGORY - provided == category.school_missing, "authority_school", {"category": category.key, "actual": provided})
        status[category.key] = {"supported": supported, "unconfirmed": DETAILS_PER_CATEGORY - supported}
        schools[category.key] = {"provided": provided, "missing": DETAILS_PER_CATEGORY - provided}
    audit.hard(any(english[item] != math_values[item] for item in localities), "authority_subject_distinction")
    audit.observations["authority"] = {"localities": len(localities), "locality_sequence_sha256": locality_sequence, "status": status, "schools": schools}
    return localities, Authority(english, math_values, elementary, high)


def parse_workbook_args(values: Sequence[str]) -> dict[str, Path]:
    result = {item.key: Path.home() / "Desktop" / item.workbook_name for item in CATEGORIES}
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"--workbook requires KEY=PATH: {value}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if key not in CATEGORY_BY_KEY or key in seen:
            raise ValueError(f"unknown or duplicate workbook key: {key}")
        seen.add(key)
        result[key] = Path(raw.strip()).expanduser()
    return {key: path.resolve() for key, path in result.items()}


def _shared_text(node: ET.Element, namespace: str) -> str:
    return "".join(item.text or "" for item in node.iter(f"{{{namespace}}}t"))


def inspect_workbooks(paths: Mapping[str, Path], localities: Sequence[str], audit: Audit) -> SourceSet:
    hashes: dict[str, str] = {}
    manuscripts: dict[str, tuple[str, ...]] = {}
    ns_uri = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns = {"m": ns_uri, "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    rel_ns = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    for category in CATEGORIES:
        path = paths.get(category.key, Path("MISSING"))
        code = "workbook_" + category.key
        audit.hard(path.is_file(), code + "_missing", str(path))
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = sha256(raw)
        hashes[category.key] = digest
        audit.hard(digest == category.workbook_sha256, code + "_sha256", {"expected": category.workbook_sha256, "actual": digest})
        audit.hard(len(raw) == category.workbook_bytes, code + "_bytes", len(raw))
        try:
            with ZipFile(path) as archive:
                infos = archive.infolist()
                names = [item.filename for item in infos]
                unsafe = [
                    name for name in names if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name)
                    or any(part == ".." for part in re.split(r"[\\/]", name)) or "\x00" in name
                ]
                suspicious = [
                    item.filename for item in infos if item.file_size > 20_000_000
                    or (item.compress_size and item.file_size / item.compress_size > 100)
                    or ((item.external_attr >> 16) & 0o170000) == 0o120000
                ]
                audit.hard(len(names) == 10 and len(names) == len(set(names)), code + "_zip_entries", len(names))
                audit.extend(code + "_unsafe", unsafe)
                audit.extend(code + "_suspicious", suspicious)
                audit.extend(code + "_macros", [name for name in names if "vba" in name.lower() or name.lower().endswith(".bin")])
                audit.extend(code + "_external", [name for name in names if name.startswith("xl/externalLinks/") or "connections" in name.lower()])
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
                rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                rels = {item.attrib["Id"]: item.attrib["Target"] for item in rel_root.findall("p:Relationship", rel_ns)}
                external_rels = [item.attrib for item in rel_root.findall("p:Relationship", rel_ns) if item.attrib.get("TargetMode") == "External"]
                audit.hard(not external_rels, code + "_external_relationships", external_rels)
                sheets_node = workbook.find("m:sheets", ns)
                sheets = [] if sheets_node is None else list(sheets_node)
                audit.hard(len(sheets) == 1, code + "_sheet_count", len(sheets))
                if len(sheets) != 1:
                    continue
                sheet = sheets[0]
                audit.hard(sheet.attrib.get("name") == "Sheet1" and sheet.attrib.get("state", "visible") == "visible", code + "_sheet_contract", sheet.attrib)
                rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
                target = rels[rid].lstrip("/")
                if not target.startswith("xl/"):
                    target = "xl/" + target
                xml = ET.fromstring(archive.read(target))
                dimension = xml.find("m:dimension", ns)
                rows = xml.findall(".//m:sheetData/m:row", ns)
                cells = xml.findall(".//m:sheetData/m:row/m:c", ns)
                refs = [cell.attrib.get("r", "") for cell in cells]
                expected_refs = [f"A{number}" for number in range(1, DETAILS_PER_CATEGORY + 1)]
                audit.hard(dimension is not None and dimension.attrib.get("ref") == "A1:A371", code + "_dimension", None if dimension is None else dimension.attrib)
                audit.hard(len(rows) == DETAILS_PER_CATEGORY and len(cells) == DETAILS_PER_CATEGORY and refs == expected_refs, code + "_row_cell_order", {"rows": len(rows), "cells": len(cells), "refs": refs[:5]})
                audit.hard(not xml.findall(".//m:f", ns), code + "_formula_free")
                audit.hard(not xml.findall(".//m:hyperlinks/m:hyperlink", ns), code + "_hyperlink_free")
                audit.hard(not xml.findall(".//m:mergeCells/m:mergeCell", ns), code + "_merge_free")
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [_shared_text(item, ns_uri) for item in shared_root.findall("m:si", ns)]
                indices = [int((cell.findtext("m:v", default="", namespaces=ns) or "-1")) for cell in cells]
                values = tuple(unicodedata.normalize("NFC", shared[index]) for index in indices if 0 <= index < len(shared))
                audit.hard(len(shared) == DETAILS_PER_CATEGORY and len(values) == DETAILS_PER_CATEGORY, code + "_shared_strings", {"shared": len(shared), "values": len(values)})
                audit.hard(len(set(values)) == DETAILS_PER_CATEGORY, code + "_unique_manuscripts", len(set(values)))
                def workbook_title(value: str) -> str:
                    lines = [line.strip() for line in value.splitlines()]
                    try:
                        marker = lines.index("[페이지타이틀]")
                    except ValueError:
                        marker = -1
                    candidates = lines[marker + 1:] if marker >= 0 else lines
                    return next((line for line in candidates if line), "")

                titles = tuple(workbook_title(value) for value in values)
                expected_titles = tuple(f"{locality} {category.label}" for locality in localities)
                title_mismatches = [
                    {"row": number, "actual": actual, "expected": expected}
                    for number, (actual, expected) in enumerate(zip(titles, expected_titles), 1)
                    if not actual.startswith(expected)
                ]
                audit.hard(not title_mismatches, code + "_title_order", {"count": len(title_mismatches), "samples": title_mismatches[:12]})
                exact_titles = sum(actual == expected for actual, expected in zip(titles, expected_titles))
                audit.hard(exact_titles == category.exact_titles, code + "_exact_extended_titles", {"exact": exact_titles, "extended": DETAILS_PER_CATEGORY - exact_titles})
                audit.hard(not any(CONTROL_RE.search(value) for value in values), code + "_control_text")
                manuscripts[category.key] = values
                audit.observations[code] = {
                    "path": str(path), "sha256": digest, "bytes": len(raw), "zip_entries": len(names),
                    "rows": len(rows), "shared_strings": len(shared), "unique": len(set(values)),
                    "exact_titles": exact_titles, "extended_titles": DETAILS_PER_CATEGORY - exact_titles,
                }
        except Exception as exc:
            audit.hard(False, code + "_ooxml", f"{type(exc).__name__}: {exc}")
    audit.hard(set(hashes) == set(CATEGORY_BY_KEY) and set(manuscripts) == set(CATEGORY_BY_KEY), "workbook_category_scope", {"hashes": sorted(hashes), "manuscripts": sorted(manuscripts)})
    return SourceSet(dict(paths), hashes, tuple(localities), manuscripts)


def expected_new_html(source: SourceSet) -> set[str]:
    result: set[str] = set()
    for category in CATEGORIES:
        result.add(category.category_rel)
        result.update(f"학년별학원/{category.slug}/{locality}/index.html" for locality in source.localities)
    return result


def expected_plan_paths(source: SourceSet) -> set[str]:
    return {PARENT_REL, SITEMAP_REL, LLMS_REL, *expected_new_html(source)}


def load_module(path: Path) -> Any:
    name = "_grade6_high2_generator_" + sha256(path.read_bytes())[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plan_value(plan: Any, name: str, default: Any = None) -> Any:
    return plan.get(name, default) if isinstance(plan, Mapping) else getattr(plan, name, default)


def call_build_plan(
    function: Any, *, root: Path, workbook_paths: Mapping[str, Path],
    common_dir: Path, overrides: Mapping[str, bytes] | None,
) -> Any:
    signature = inspect.signature(function)
    required = {"root", "workbook_paths", "common_dir", "current_overrides"}
    if not required <= set(signature.parameters):
        raise TypeError(f"build_plan signature must contain {sorted(required)}: {signature}")
    payload = None if overrides is None else {Path(path): value for path, value in overrides.items()}
    return function(root=root, workbook_paths=workbook_paths, common_dir=common_dir, current_overrides=payload)


def run_projection(
    root: Path, generator_path: Path, source: SourceSet, common_dir: Path,
    expected: set[str], audit: Audit,
) -> Projection | None:
    generator_sha = sha256(generator_path.read_bytes())
    strong_paths = {*expected, GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL, *PROTECTED_PINS}
    tree_before = tree_snapshot(root, strong_paths)
    common_before = directory_snapshot(common_dir)
    source_before = {key: sha256(path.read_bytes()) for key, path in source.workbook_paths.items()}
    status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
    try:
        module = load_module(generator_path)
        function = getattr(module, "build_plan", None)
        audit.hard(callable(function), "generator_build_plan")
        if not callable(function):
            return None
        first = call_build_plan(function, root=root, workbook_paths=source.workbook_paths, common_dir=common_dir, overrides=None)
        documents = normalize_documents(root, first, audit, "projection_first")
        audit.hard(set(documents) == expected and len(documents) == PLAN_DOCUMENT_COUNT, "projection_exact_scope", {"expected": len(expected), "actual": len(documents), "missing": sorted(expected - set(documents))[:20], "extra": sorted(set(documents) - expected)[:20]})
        projected_manifest = manifest(documents) if documents else ""
        before_manifest = normalize_hashes(root, plan_value(first, "before_manifest"), audit, "projection_before")
        after_manifest = normalize_hashes(root, plan_value(first, "after_manifest"), audit, "projection_after")
        expected_after = {path: sha256(value) for path, value in documents.items()}
        audit.hard(set(before_manifest) == expected, "projection_before_scope")
        audit.hard(after_manifest == expected_after, "projection_after_values")
        before_exists_raw = plan_value(first, "before_exists")
        audit.hard(isinstance(before_exists_raw, Mapping), "projection_before_exists_type")
        before_exists: dict[str, bool] = {}
        if isinstance(before_exists_raw, Mapping):
            for key, value in before_exists_raw.items():
                try:
                    before_exists[normalize_relative(root, key)] = bool(value)
                except Exception as exc:
                    audit.hard(False, "projection_before_exists_path", {"key": str(key), "error": str(exc)})
        audit.hard(set(before_exists) == expected, "projection_before_exists_scope")
        mismatches: list[Any] = []
        for relative in expected:
            current = fs_bytes(root, relative)
            if before_exists.get(relative) != (current is not None):
                mismatches.append({"path": relative, "reason": "existence"})
            elif current is not None and before_manifest.get(relative) != sha256(current):
                mismatches.append({"path": relative, "reason": "hash"})
        audit.extend("projection_before_values", mismatches)
        declared = normalize_changed(root, plan_value(first, "changed_paths", ()), audit, "projection_changed")
        actual = {path for path, value in documents.items() if fs_bytes(root, path) != value}
        audit.hard(declared == actual, "projection_declared_changed", {"declared_only": sorted(declared - actual)[:20], "actual_only": sorted(actual - declared)[:20]})
        audit.hard(len(actual) in {0, PLAN_DOCUMENT_COUNT}, "projection_partial_materialization", len(actual))
        second_declared = normalize_changed(root, plan_value(first, "second_pass_changes", ()), audit, "projection_declared_second")
        audit.hard(not second_declared, "projection_declared_second_zero", sorted(second_declared)[:20])
        candidate = str(plan_value(first, "candidate_sha256", "")).lower()
        audit.hard(bool(re.fullmatch(r"[0-9a-f]{64}", candidate)), "projection_candidate_contract", candidate)
        immutable = str(plan_value(first, "immutable_html_manifest_sha256", "")).lower()
        high2_math = str(plan_value(first, "high2_math_manifest_sha256", "")).lower()
        audit.hard(immutable == BASE_IMMUTABLE_HTML_MANIFEST, "projection_immutable_manifest", immutable)
        audit.hard(high2_math == BASE_HIGH2_MATH_MANIFEST, "projection_high2_math_manifest", high2_math)
        source_manifest = plan_value(first, "source_manifest", {})
        audit.hard(isinstance(source_manifest, Mapping), "projection_source_manifest_type")
        if isinstance(source_manifest, Mapping):
            values = {str(value).lower() for value in source_manifest.values()}
            expected_sources = {*(item.workbook_sha256 for item in CATEGORIES), EXPECTED_CENTER_CSV_SHA256, EXPECTED_SCHOOL_CSV_SHA256}
            audit.hard(expected_sources <= values, "projection_source_manifest_pins", {"missing": sorted(expected_sources - values)})
        del first
        gc.collect()
        repeat = call_build_plan(function, root=root, workbook_paths=source.workbook_paths, common_dir=common_dir, overrides=None)
        repeat_manifest = compare_plan_streaming(root, repeat, documents, audit, "projection_repeat")
        audit.hard(repeat_manifest == projected_manifest and str(plan_value(repeat, "candidate_sha256", "")).lower() == candidate, "projection_repeat_identity")
        del repeat
        gc.collect()
        second = call_build_plan(function, root=root, workbook_paths=source.workbook_paths, common_dir=common_dir, overrides=documents)
        second_manifest = compare_plan_streaming(root, second, documents, audit, "projection_second")
        second_changed = normalize_changed(root, plan_value(second, "changed_paths", ()), audit, "projection_second_changed")
        audit.hard(second_manifest == projected_manifest and not second_changed and str(plan_value(second, "candidate_sha256", "")).lower() == candidate, "projection_second_identity")
        del second
        gc.collect()
        reverse_paths = dict(reversed(list(source.workbook_paths.items())))
        reverse_documents = dict(reversed(list(documents.items())))
        reverse = call_build_plan(function, root=root, workbook_paths=reverse_paths, common_dir=common_dir, overrides=reverse_documents)
        reverse_manifest = compare_plan_streaming(root, reverse, documents, audit, "projection_reverse")
        reverse_changed = normalize_changed(root, plan_value(reverse, "changed_paths", ()), audit, "projection_reverse_changed")
        audit.hard(reverse_manifest == projected_manifest and not reverse_changed and str(plan_value(reverse, "candidate_sha256", "")).lower() == candidate, "projection_reverse_identity")
        del reverse
        gc.collect()
        audit.observations["projection"] = {
            "documents": len(documents), "changed": len(actual), "candidate_sha256": candidate,
            "projected_manifest": projected_manifest, "generator_sha256": generator_sha,
            "repeat": repeat_manifest, "second": second_manifest, "reverse": reverse_manifest,
            "immutable_manifest": immutable, "high2_math_manifest": high2_math,
        }
        return Projection(documents, frozenset(actual), candidate, projected_manifest, generator_sha)
    finally:
        audit.hard(tree_before == tree_snapshot(root, strong_paths), "projection_repository_read_only")
        audit.hard(common_before == directory_snapshot(common_dir), "projection_common_read_only")
        audit.hard(source_before == {key: sha256(path.read_bytes()) for key, path in source.workbook_paths.items()}, "projection_workbooks_read_only")
        audit.hard(status_before == run_git(root, ["status", "--porcelain=v1", "-z"]), "projection_git_status_read_only")


def git_blob(root: Path, relative: str) -> bytes:
    return run_git(root, ["show", f"{BASELINE_COMMIT}:{relative}"])


def files_manifest(root: Path, relatives: Iterable[str]) -> str:
    """Physical-byte boundary manifest: path, NUL, file SHA-256, LF."""

    digest = hashlib.sha256()
    for relative in sorted(relatives):
        value = fs_bytes(root, relative)
        if value is None:
            raise FileNotFoundError(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(value).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_repository(root: Path, audit: Audit) -> None:
    try:
        top = Path(run_git(root, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()).resolve()
    except Exception as exc:
        audit.hard(False, "repository_root", str(exc))
        return
    audit.hard(top == root.resolve(), "repository_root", {"expected": str(root.resolve()), "actual": str(top)})
    tree = run_git(root, ["show", "--no-patch", "--format=%T", BASELINE_COMMIT]).decode().strip()
    audit.hard(tree == BASELINE_TREE, "repository_baseline_tree", {"expected": BASELINE_TREE, "actual": tree})
    baseline_files = baseline_paths(root)
    baseline_html = [item for item in baseline_files if item.endswith("index.html")]
    audit.hard(len(baseline_files) == BASELINE_TRACKED_COUNT, "repository_baseline_tracked", len(baseline_files))
    audit.hard(len(baseline_html) == BASELINE_HTML_COUNT, "repository_baseline_html", len(baseline_html))
    immutable = [item for item in baseline_html if item != PARENT_REL]
    high2_math = [item for item in immutable if item.startswith("학년별학원/고2수학학원/")]
    audit.hard(files_manifest(root, immutable) == BASE_IMMUTABLE_HTML_MANIFEST, "repository_immutable_manifest")
    audit.hard(len(high2_math) == EXISTING_HIGH2_MATH_HTML_COUNT and files_manifest(root, high2_math) == BASE_HIGH2_MATH_MANIFEST, "repository_high2_math_manifest")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    audit.hard(ancestor.returncode == 0, "repository_baseline_ancestor", ancestor.stderr.decode("utf-8", "replace"))
    remote = run_git(root, ["remote", "get-url", "origin"], check=False).decode("utf-8", "replace").strip()
    audit.hard(remote.rstrip("/") in {
        "https://github.com/01039578283-hub/my-homepage.git",
        "git@github.com:01039578283-hub/my-homepage.git",
    }, "repository_origin", remote)
    disk_html = sum(
        1 for path in root.rglob("index.html")
        if not any(part in PRUNED_DIRS for part in path.relative_to(root).parts)
    )
    audit.hard(disk_html in {BASELINE_HTML_COUNT, FINAL_HTML_COUNT}, "repository_disk_html_phase", disk_html)
    branch = run_git(root, ["branch", "--show-current"], check=False).decode("utf-8", "replace").strip()
    audit.observations["repository"] = {
        "root": str(root), "baseline": BASELINE_COMMIT, "tree": tree,
        "baseline_tracked": len(baseline_files), "baseline_html": len(baseline_html),
        "disk_html": disk_html, "branch": branch, "origin": remote,
    }


def validate_projected_security(root: Path, projection: Projection, audit: Audit) -> None:
    errors: list[Any] = []
    for relative, value in projection.documents.items():
        try:
            normalized = normalize_relative(root, relative)
        except Exception as exc:
            errors.append({"path": str(relative), "reason": "unsafe-path", "error": str(exc)})
            continue
        if normalized != relative:
            errors.append({"path": relative, "reason": "noncanonical-path", "normalized": normalized})
        if len(value) > 50_000_000:
            errors.append({"path": relative, "reason": "oversize", "bytes": len(value)})
        try:
            source = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append({"path": relative, "reason": "not-utf8", "error": str(exc)})
            continue
        if value.startswith(b"\xef\xbb\xbf"):
            errors.append({"path": relative, "reason": "bom"})
        if CONTROL_RE.search(source):
            errors.append({"path": relative, "reason": "control-character"})
        for pattern in SECRET_PATTERNS:
            if pattern.search(source):
                errors.append({"path": relative, "reason": "secret-pattern", "pattern": pattern.pattern[:80]})
    audit.extend("projected_security", errors)
    audit.observations["projected_security"] = {"documents": len(projection.documents), "errors": len(errors)}


def validate_preservation(
    root: Path, projection: Projection, all_html: Sequence[str], new_html: set[str], audit: Audit,
) -> None:
    head = run_git(root, ["rev-parse", BASELINE_COMMIT]).decode().strip()
    tree = run_git(root, ["rev-parse", f"{BASELINE_COMMIT}^{{tree}}"]).decode().strip()
    audit.hard(head == BASELINE_COMMIT, "baseline_commit", head)
    audit.hard(tree == BASELINE_TREE, "baseline_tree", {"expected": BASELINE_TREE, "actual": tree})
    baseline_html = baseline_paths(root, "index.html")
    audit.hard(len(baseline_html) == BASELINE_HTML_COUNT, "baseline_html_count", len(baseline_html))
    audit.hard(len(new_html) == NEW_HTML_COUNT and not (set(baseline_html) & new_html), "new_html_disjoint", {"new": len(new_html), "collisions": sorted(set(baseline_html) & new_html)[:20]})
    audit.hard(set(all_html) == set(baseline_html) | new_html, "final_html_scope")
    existing_authorized = set(projection.documents) & set(baseline_html)
    audit.hard(existing_authorized == {PARENT_REL}, "existing_html_authorization", sorted(existing_authorized))
    changed = {
        item.decode("utf-8") for item in run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"]).split(b"\0") if item
    }
    immutable = set(baseline_html) - {PARENT_REL}
    high2_math = {item for item in baseline_html if item.startswith("학년별학원/고2수학학원/")}
    audit.hard(len(immutable) == IMMUTABLE_HTML_COUNT, "immutable_html_count", len(immutable))
    audit.hard(not (changed & immutable), "immutable_html_git_preservation", sorted(changed & immutable)[:20])
    audit.hard(len(high2_math) == EXISTING_HIGH2_MATH_HTML_COUNT, "high2_math_count", len(high2_math))
    audit.hard(not (changed & high2_math), "high2_math_git_preservation", sorted(changed & high2_math)[:20])
    protected_errors: list[Any] = []
    for relative, expected in PROTECTED_PINS.items():
        try:
            baseline_value = git_blob(root, relative)
            current = fs_bytes(root, relative)
            unchanged = subprocess.run(
                ["git", "diff", "--quiet", BASELINE_COMMIT, "--", relative], cwd=root,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            if sha256(baseline_value) != expected or current is None or unchanged.returncode != 0:
                protected_errors.append({
                    "path": relative, "expected_blob": expected,
                    "baseline_blob": sha256(baseline_value), "current_missing": current is None,
                    "git_diff_returncode": unchanged.returncode,
                })
        except Exception as exc:
            protected_errors.append({"path": relative, "error": str(exc)})
    audit.extend("protected_file_sha256", protected_errors)
    current_parent = projection.documents.get(PARENT_REL, fs_bytes(root, PARENT_REL) or b"")
    try:
        current_nav = nav_fragment(current_parent.decode("utf-8"))
        baseline_nav = nav_fragment(git_blob(root, PARENT_REL).decode("utf-8"))
        audit.hard(current_nav is not None and baseline_nav is not None and normalized_text(current_nav) == normalized_text(baseline_nav), "parent_nav_preservation")
    except Exception as exc:
        audit.hard(False, "parent_nav_preservation", str(exc))
    audit.observations["preservation"] = {
        "baseline_html": len(baseline_html), "immutable_html": len(immutable),
        "high2_math": len(high2_math), "existing_authorized": sorted(existing_authorized),
        "tracked_changed": len(changed), "protected_files": len(PROTECTED_PINS),
        "immutable_manifest": BASE_IMMUTABLE_HTML_MANIFEST,
        "high2_math_manifest": BASE_HIGH2_MATH_MANIFEST,
    }


def validate_sitemap(
    root: Path, value: bytes, all_html: Sequence[str], new_html: set[str], source: SourceSet, audit: Audit,
) -> None:
    rows, blocks = parse_sitemap(value, audit, "sitemap")
    locations = [location for location, _ in rows]
    expected_urls = {DOMAIN + route_for_relative(relative) for relative in all_html}
    audit.hard(len(rows) == FINAL_HTML_COUNT, "sitemap_count", len(rows))
    audit.hard(len(set(locations)) == FINAL_HTML_COUNT, "sitemap_unique", len(set(locations)))
    audit.hard(set(locations) == expected_urls, "sitemap_html_parity", {"missing": sorted(expected_urls - set(locations))[:20], "extra": sorted(set(locations) - expected_urls)[:20]})
    audit.hard(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) for _, date in rows), "sitemap_lastmod_contract")
    baseline_value = git_blob(root, SITEMAP_REL)
    audit.hard(sha256(baseline_value) == BASE_SITEMAP_BLOB_SHA256, "sitemap_baseline_pin")
    baseline_rows, baseline_blocks = parse_sitemap(baseline_value, audit, "sitemap_baseline")
    audit.hard(len(baseline_rows) == BASELINE_HTML_COUNT, "sitemap_baseline_count", len(baseline_rows))
    audit.hard(blocks[:BASELINE_HTML_COUNT] == baseline_blocks, "sitemap_append_only")
    appended = rows[BASELINE_HTML_COUNT:]
    expected_order: list[str] = []
    for category in CATEGORIES:
        expected_order.append(DOMAIN + category.category_route)
        expected_order.extend(DOMAIN + category.category_route + quote(locality, safe="") + "/" for locality in source.localities)
    audit.hard(len(appended) == NEW_HTML_COUNT, "sitemap_appended_count", len(appended))
    audit.hard([location for location, _ in appended] == expected_order, "sitemap_appended_order")
    audit.hard({location for location, _ in appended} == {DOMAIN + route_for_relative(path) for path in new_html}, "sitemap_appended_scope")
    audit.hard(all(date == RELEASE_DATE for _, date in appended), "sitemap_new_lastmod")
    audit.observations["sitemap"] = {"rows": len(rows), "unique": len(set(locations)), "appended": len(appended)}


def validate_llms(root: Path, value: bytes, audit: Audit) -> None:
    try:
        source = normalized_text(value.decode("utf-8"))
        baseline_value = git_blob(root, LLMS_REL)
        baseline = normalized_text(baseline_value.decode("utf-8"))
    except Exception as exc:
        audit.hard(False, "llms_utf8", str(exc))
        return
    audit.hard(sha256(baseline_value) == BASE_LLMS_BLOB_SHA256, "llms_baseline_pin")
    marker = "## 학년별학원 핵심 허브"
    audit.hard(source.count(marker) == 1 and baseline.count(marker) == 1, "llms_marker")
    if marker not in source or marker not in baseline:
        return
    audit.hard(source[:source.index(marker)] == baseline[:baseline.index(marker)], "llms_prefix_preservation")
    block = source[source.index(marker):]
    raw_parent = DOMAIN + "/학년별학원/"
    labels = (
        ("초6", "수학", "초6수학학원"), ("초6", "영어", "초6영어학원"),
        ("중1", "수학", "중1수학학원"), ("중1", "영어", "중1영어학원"),
        ("중2", "수학", "중2수학학원"), ("중2", "영어", "중2영어학원"),
        ("중3", "수학", "중3수학학원"), ("중3", "영어", "중3영어학원"),
        ("고2", "수학", "고2수학학원"), ("고2", "영어", "고2영어학원"),
    )
    expected_lines = [f"- {grade} {subject}학원: {raw_parent}{slug}/" for grade, subject, slug in labels]
    actual_lines = [line for line in block.splitlines() if re.match(r"^- (?:초6|중[123]|고2) (?:수학|영어)학원: ", line)]
    audit.hard(actual_lines == expected_lines, "llms_category_order", actual_lines)
    audit.hard(block.splitlines().count(f"- 학년별학원: {raw_parent}") == 1, "llms_parent_url")
    urls = [raw_parent + slug + "/" for _, _, slug in labels]
    audit.hard(all(source.count(url) == 1 for url in urls), "llms_category_url_unique", {url: source.count(url) for url in urls})
    lines = block.splitlines()
    audit.hard(len(lines) == 24, "llms_block_line_count", len(lines))
    audit.hard(any(all(grade in line for grade in ("초6", "중1", "중2", "중3", "고2")) for line in lines), "llms_grade_summary")
    for expected in expected_lines:
        index = lines.index(expected) if expected in lines else -1
        audit.hard(index >= 0 and index + 1 < len(lines) and lines[index + 1].startswith("  - ") and "371개" in lines[index + 1], "llms_description_contract", expected)


def validate_pins(
    root: Path, projection: Projection, generator: Path, content_auditor: Path, audit: Audit,
) -> None:
    values = {
        GENERATOR_REL: (generator, projection.generator_sha256, APPROVED_GENERATOR_SHA256),
        CONTENT_AUDITOR_REL: (
            content_auditor,
            sha256(content_auditor.read_bytes()) if content_auditor.is_file() else "MISSING",
            APPROVED_CONTENT_AUDITOR_SHA256,
        ),
    }
    pending: list[str] = []
    actual: dict[str, str] = {}
    for relative, (path, digest, approved) in values.items():
        canonical = root / PurePosixPath(relative)
        audit.hard(path.resolve() == canonical.resolve(), "pin_override_path", {"path": relative, "actual": str(path)})
        audit.hard(canonical.is_file(), "pin_file_missing", relative)
        if canonical.is_file():
            canonical_digest = sha256(canonical.read_bytes())
            actual[relative] = canonical_digest
            audit.hard(canonical_digest == digest, "pin_digest_parity", relative)
        if approved == "PENDING":
            pending.append(relative)
        else:
            audit.hard(digest == approved, "pin_sha256", {"path": relative, "expected": approved, "actual": digest})
    for label, actual_value, approved in (
        ("candidate_sha256", projection.candidate_sha256, APPROVED_PLAN_CANDIDATE_SHA256),
        ("projected_manifest", projection.projected_manifest, APPROVED_PROJECTED_MANIFEST),
    ):
        if approved == "PENDING":
            pending.append(label)
        else:
            audit.hard(actual_value == approved, "pin_" + label, {"expected": approved, "actual": actual_value})
    audit.hold(not pending, "freeze_pins_pending", pending)
    audit.observations["pins"] = {
        "actual": actual, "candidate_sha256": projection.candidate_sha256,
        "projected_manifest": projection.projected_manifest, "pending": pending,
    }


def detail_identity(relative: str) -> tuple[Category, str] | None:
    parts = PurePosixPath(relative).parts
    if len(parts) != 4 or parts[0] != "학년별학원" or parts[3] != "index.html":
        return None
    category = CATEGORY_BY_SLUG.get(parts[1])
    return (category, parts[2]) if category is not None else None


def semantic_detail_faq(source: str) -> tuple[int, list[tuple[str, str]]]:
    """Return visible FAQ text without the frozen manuscript Q/A labels."""

    count, values = visible_faq(source)
    normalized = [
        (
            re.sub(r"^Q(?:\d+)?[.)]\s*", "", question),
            # The inherited parser consumes only the leading ``A`` from
            # ``A1.`` and leaves ``1.`` behind; accept that exact residual
            # form as well as an intact answer prefix.
            re.sub(r"^(?:A(?:\d+)?[.)]|\d+[.)])\s*", "", answer),
        )
        for question, answer in values
    ]
    return count, normalized


def audit_documents(
    root: Path, projection: Projection, source: SourceSet, authority: Authority,
    all_html: list[str], new_html: set[str], audit: Audit,
) -> list[DetailReport]:
    audit.hard(len(all_html) == FINAL_HTML_COUNT, "final_html_count", len(all_html))
    route_to_relative = {route_for_relative(relative): relative for relative in all_html}
    audit.hard(len(route_to_relative) == FINAL_HTML_COUNT, "final_route_unique", len(route_to_relative))
    filesystem_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_file() and not any(part in PRUNED_DIRS for part in path.relative_to(root).parts)
    }

    def read(relative: str) -> bytes | None:
        return projection.documents.get(relative, fs_bytes(root, relative))

    failures: defaultdict[str, list[Any]] = defaultdict(list)
    canonicals: list[str] = []
    graph: defaultdict[str, set[str]] = defaultdict(set)
    broken: Counter[str] = Counter()
    broken_samples: dict[str, Any] = {}
    resources: Counter[str] = Counter()
    resource_samples: dict[str, Any] = {}
    details: list[DetailReport] = []
    status_counts: Counter[str] = Counter()
    category_status: defaultdict[str, Counter[str]] = defaultdict(Counter)
    school_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    nav_links = nav_active = jsonld_blocks = 0
    missing_dimensions = bulk_hidden = known_external = new_external = 0
    body_map = authoritative_levels = english_distinct = legacy_raw = 0

    for relative in all_html:
        value = read(relative)
        if value is None:
            failures["document_missing"].append(relative)
            continue
        parsed = parse_document(value, relative, audit)
        if parsed is None:
            continue
        source_text, parser = parsed
        route = route_for_relative(relative)
        if CONTROL_RE.search(source_text):
            failures["control_character"].append(relative)
        if len(parser.titles) != 1 or not parser.titles[0]:
            failures["title_count"].append({"path": relative, "values": parser.titles})
        if len(parser.h1s) != 1 or not parser.h1s[0]:
            failures["h1_count"].append({"path": relative, "values": parser.h1s})

        canonical_values = [item.get("href", "") for item in parser.links if "canonical" in item.get("rel", "").lower().split()]
        og_values = [item.get("content", "") for item in parser.metas if item.get("property", "").lower() == "og:url"]
        expected_canonical = DOMAIN + route
        strict = relative in new_html or relative == PARENT_REL
        canonical_ok = len(canonical_values) == 1 and canonical_values[0] == expected_canonical
        if not canonical_ok and not strict and len(canonical_values) == 1:
            baseline_parsed = parse_document(git_blob(root, relative), relative + "@baseline", audit)
            baseline_canonical = [] if baseline_parsed is None else [
                item.get("href", "") for item in baseline_parsed[1].links
                if "canonical" in item.get("rel", "").lower().split()
            ]
            canonical_ok = (
                canonical_values == baseline_canonical
                and normalize_route(canonical_values[0], base_route=route) == route
                and urlsplit(canonical_values[0]).scheme == "https"
                and urlsplit(canonical_values[0]).netloc.lower() in HOSTS
            )
            legacy_raw += int(canonical_ok)
        if canonical_ok:
            canonicals.append(expected_canonical)
        else:
            failures["canonical"].append({"path": relative, "expected": expected_canonical, "actual": canonical_values})
        if len(og_values) != 1 or og_values != canonical_values:
            failures["og_url"].append({"path": relative, "canonical": canonical_values, "og": og_values})
        robots = [
            item.get("content", "") for item in parser.metas
            if item.get("name", "").lower() in {"robots", "googlebot", "naverbot", "yeti"}
        ]
        if any("noindex" in item.lower() for item in robots):
            failures["noindex"].append(relative)

        fragment = nav_fragment(source_text)
        entries = nav_entries(fragment, route) if fragment else []
        if fragment is None:
            failures["nav_missing"].append(relative)
        if len(entries) != 9 or tuple(item["route"] for item in entries[1:]) != EXPECTED_NAV_TARGETS:
            failures["nav_contract"].append({"path": relative, "entries": entries})
        grade_links = [item for item in entries if item["text"] == "학년별학원"]
        nav_links += len(grade_links)
        active = len(grade_links) == 1 and "active" in grade_links[0]["class"].split()
        nav_active += int(active)
        should_active = relative == PARENT_REL or relative.startswith("학년별학원/")
        if len(grade_links) != 1 or grade_links[0]["route"] != PARENT_ROUTE or active != should_active:
            failures["grade_nav"].append({"path": relative, "expected_active": should_active, "actual": grade_links})

        nodes: list[Mapping[str, Any]] = []
        for block in parser.ld_scripts:
            jsonld_blocks += 1
            try:
                payload = json.loads(block)
                if isinstance(payload, Mapping):
                    graph_value = payload.get("@graph")
                    nodes.extend(item for item in graph_value if isinstance(item, Mapping)) if isinstance(graph_value, list) else nodes.append(payload)
            except Exception as exc:
                failures["jsonld_syntax"].append({"path": relative, "error": str(exc)})
        if strict and len(parser.ld_scripts) != 1:
            failures["jsonld_block_count"].append({"path": relative, "count": len(parser.ld_scripts)})

        for anchor in parser.anchors:
            href = anchor.get("href", "")
            target = normalize_route(href, base_route=route)
            if target is None:
                continue
            split = urlsplit(urljoin(DOMAIN + route, html.unescape(href)))
            if split.netloc.lower() not in HOSTS:
                continue
            if target in route_to_relative:
                graph[route].add(target)
            else:
                broken[target] += 1
                broken_samples.setdefault(target, {"path": relative, "href": href})

        for tag, attrs in parser.starts:
            if tag == "img":
                if not attrs.get("width", "").isdigit() or not attrs.get("height", "").isdigit():
                    missing_dimensions += 1
                if "bulk-hidden-image" in attrs.get("class", "").split():
                    bulk_hidden += 1
                if attrs.get("src") == KNOWN_EXTERNAL_IMAGE:
                    known_external += 1
                host = urlsplit(urljoin(DOMAIN + route, attrs.get("src", ""))).netloc.lower()
                if relative in new_html and host not in HOSTS:
                    new_external += 1
            if tag not in {"img", "script", "link"}:
                continue
            if tag == "link" and not ({"stylesheet", "icon", "shortcut", "apple-touch-icon", "preload", "modulepreload"} & set(attrs.get("rel", "").lower().split())):
                continue
            raw = attrs.get("src" if tag in {"img", "script"} else "href", "").strip()
            if not raw or raw.startswith(IGNORED_SCHEMES):
                continue
            split = urlsplit(urljoin(DOMAIN + route, html.unescape(raw)))
            if split.netloc.lower() not in HOSTS:
                continue
            resource = unquote(split.path).lstrip("/")
            if resource:
                resources[resource] += 1
                resource_samples.setdefault(resource, {"page": relative, "tag": tag, "value": raw})

        if relative == PARENT_REL:
            if len(data_nodes(parser, "data-grade-directory", "parent")) != 1:
                failures["parent_main_hook"].append(relative)
            cards = [attrs for attrs in parser.anchors if "subject-category-card" in attrs.get("class", "").split()]
            routes = [normalize_route(attrs.get("href", ""), base_route=route) for attrs in cards]
            if tuple(routes) != PARENT_CATEGORY_ROUTES:
                failures["parent_category_cards"].append(routes)
            faq_count, visible = visible_faq(source_text)
            if faq_count != 1 or len(visible) != 2 or visible != schema_faq(nodes):
                failures["parent_faq_parity"].append({"visible": visible, "schema": schema_faq(nodes)})
            types = ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage")
            counts = Counter(kind for kind in types for node in nodes if type_has(node, kind))
            if any(counts[kind] != 1 for kind in types):
                failures["parent_schema_cardinality"].append(counts)
            collections = [node for node in nodes if type_has(node, "CollectionPage")]
            item_lists = [node for node in nodes if type_has(node, "ItemList")]
            if len(collections) == 1:
                about, parts = collections[0].get("about"), collections[0].get("hasPart")
                if not isinstance(about, list) or len(about) < 2 or not isinstance(parts, list) or len(parts) != len(PARENT_CATEGORY_SLUGS):
                    failures["parent_schema_semantics"].append({"about": about, "hasPart": parts})
            if len(item_lists) == 1:
                elements = item_lists[0].get("itemListElement")
                if item_lists[0].get("numberOfItems") != len(PARENT_CATEGORY_SLUGS) or not isinstance(elements, list) or len(elements) != len(PARENT_CATEGORY_SLUGS):
                    failures["parent_itemlist"].append(item_lists[0])

        hub = next((item for item in CATEGORIES if relative == item.category_rel), None)
        if hub is not None:
            if len(data_nodes(parser, "data-grade-directory", hub.hook)) != 1:
                failures["hub_main_hook"].append(relative)
            for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
                if len(data_nodes(parser, hook)) != 1:
                    failures["hub_search_hook"].append({"path": relative, "hook": hook})
            cards = data_nodes(parser, "data-grade-locality")
            names = [attrs.get("data-grade-locality", "") for _, attrs in cards]
            if len(cards) != DETAILS_PER_CATEGORY or len(set(names)) != DETAILS_PER_CATEGORY or names != list(source.localities):
                failures["hub_card_contract"].append({"path": relative, "total": len(cards), "unique": len(set(names)), "ordered": names == list(source.localities)})
            expected_routes = {hub.category_route + quote(locality, safe="") + "/" for locality in source.localities}
            link_counts = Counter(normalize_route(attrs.get("href", ""), base_route=route) for attrs in parser.anchors)
            bad = [target for target in expected_routes if link_counts[target] != 1]
            if bad:
                failures["hub_detail_links"].append({"path": relative, "bad": bad[:20]})
            faq_count, visible = visible_faq(source_text)
            if faq_count != 1 or len(visible) != 2 or visible != schema_faq(nodes):
                failures["hub_faq_parity"].append({"path": relative, "visible": visible, "schema": schema_faq(nodes)})
            types = ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage")
            counts = Counter(kind for kind in types for node in nodes if type_has(node, kind))
            if any(counts[kind] != 1 for kind in types):
                failures["hub_schema_cardinality"].append({"path": relative, "actual": counts})
            item_lists = [node for node in nodes if type_has(node, "ItemList")]
            breadcrumbs = [node for node in nodes if type_has(node, "BreadcrumbList")]
            if len(item_lists) == 1:
                elements = item_lists[0].get("itemListElement")
                if item_lists[0].get("numberOfItems") != DETAILS_PER_CATEGORY or not isinstance(elements, list) or len(elements) != DETAILS_PER_CATEGORY:
                    failures["hub_itemlist"].append(relative)
            if len(breadcrumbs) == 1:
                elements = breadcrumbs[0].get("itemListElement")
                if not isinstance(elements, list) or len(elements) != 3:
                    failures["hub_breadcrumb"].append(relative)
            if len(parser.titles) == 1 and not all(item in parser.titles[0] for item in (hub.grade, hub.subject + "학원")):
                failures["hub_title_structure"].append({"path": relative, "title": parser.titles[0]})
            if len(parser.h1s) == 1 and not all(item in parser.h1s[0] for item in (hub.grade, hub.subject + "학원")):
                failures["hub_h1_structure"].append({"path": relative, "h1": parser.h1s[0]})

        identity = detail_identity(relative)
        if identity is None:
            continue
        category, locality = identity
        mains = [attrs for tag, attrs in parser.starts if tag == "main" and attrs.get("data-grade-page") == category.hook]
        status = mains[0].get("data-source-status", "") if len(mains) == 1 else ""
        if len(mains) != 1 or status not in {"supported", "unconfirmed-grade"}:
            failures["detail_main_hook"].append({"path": relative, "mains": mains})
        status_counts[status] += 1
        category_status[category.key][status] += 1
        expected_levels = authority.levels(category, locality)
        expected_status = "supported" if expected_levels is not None and category.grade in expected_levels else "unconfirmed-grade"
        if status != expected_status:
            failures["detail_authoritative_status"].append({"path": relative, "expected": expected_status, "actual": status})

        source_fields = Counter(attrs.get("data-source-field", "") for _, attrs in data_nodes(parser, "data-source-field"))
        expected_fields = Counter({"grade": 1, category.school_hook: 1, "address": 1, "registration": 1, "fee": 1})
        if source_fields != expected_fields:
            failures["detail_source_fields"].append({"path": relative, "expected": expected_fields, "actual": source_fields})
        school_nodes = [attrs for _, attrs in data_nodes(parser, "data-source-field", category.school_hook)]
        expected_school = "provided" if authority.school(category, locality) else "missing"
        actual_school = school_nodes[0].get("data-source-status", "") if len(school_nodes) == 1 else ""
        if actual_school != expected_school:
            failures["detail_school_status"].append({"path": relative, "expected": expected_school, "actual": actual_school})
        school_counts[category.key][actual_school] += 1
        if data_nodes(parser, "data-source-field", "middle-schools"):
            failures["detail_middle_school_leak"].append(relative)

        manuscript_sections = data_nodes(parser, "data-manuscript-section")
        if len(data_nodes(parser, "data-manuscript")) != 1 or not manuscript_sections:
            failures["detail_manuscript"].append(relative)
        if len(data_nodes(parser, "data-faq")) != 1 or len(data_nodes(parser, "data-review")) != 1:
            failures["detail_faq_review"].append(relative)
        article_match = re.search(r"<article\b(?=[^>]*\bdata-manuscript(?:\s*=|\s|>))[^>]*>.*?</article\s*>", source_text, re.I | re.S)
        if article_match is None or DANGEROUS_RE.search(article_match.group(0)):
            failures["detail_manuscript_safety"].append(relative)

        roles = [attrs.get("data-image-role", "") for attrs in parser.images]
        role_images = {role: [attrs for attrs in parser.images if attrs.get("data-image-role") == role] for role in ("body", "map")}
        if len(parser.images) != 2 or roles != ["body", "map"]:
            failures["detail_image_dom"].append({"path": relative, "roles": roles})
        body_map += sum(len(items) for items in role_images.values())
        for role, items in role_images.items():
            if len(items) != 1:
                continue
            attrs = items[0]
            valid_size = all(attrs.get(key, "").isdigit() and int(attrs[key]) > 0 for key in ("width", "height"))
            if not valid_size or attrs.get("loading") != ("eager" if role == "body" else "lazy") or attrs.get("decoding") != "async" or not attrs.get("alt", "").strip():
                failures["detail_image_attributes"].append({"path": relative, "role": role, "attrs": attrs})
            if role == "body" and attrs.get("fetchpriority") != "high":
                failures["detail_body_priority"].append(relative)

        checked = ("WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject", "Service", "Offer")
        required = {"WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject"}
        if status == "supported":
            required |= {"Service", "Offer"}
        schema_counts = Counter(kind for kind in checked for node in nodes if type_has(node, kind))
        if {kind for kind in checked if schema_counts[kind]} != required or any(schema_counts[kind] != (1 if kind in required else 0) for kind in checked):
            failures["detail_schema_cardinality"].append({"path": relative, "expected": sorted(required), "actual": schema_counts})
        organizations = [node for node in nodes if type_has(node, "EducationalOrganization")]
        businesses = [node for node in nodes if type_has(node, "LocalBusiness")]
        articles = [node for node in nodes if type_has(node, "Article")]
        webpages = [node for node in nodes if type_has(node, "WebPage")]
        actual_levels = organizations[0].get("educationalLevel") if len(organizations) == 1 else None
        if actual_levels != list(expected_levels or ()):
            failures["detail_educational_level"].append({"path": relative, "expected": expected_levels, "actual": actual_levels})
        else:
            authoritative_levels += 1
        if category.subject == "영어" and expected_levels != authority.math.get(locality):
            english_distinct += 1
            if actual_levels == list(authority.math.get(locality, ())):
                failures["detail_english_math_grade_leak"].append(relative)

        services = [node for node in nodes if type_has(node, "Service")]
        offers = [node for node in nodes if type_has(node, "Offer")]
        if len(organizations) == 1 and len(businesses) == 1:
            if status == "supported":
                offer_id = offers[0].get("@id") if len(offers) == 1 else None
                service_id = services[0].get("@id") if len(services) == 1 else None
                expected_offer = [{"@id": offer_id}] if offer_id else None
                if organizations[0].get("makesOffer") != expected_offer or businesses[0].get("makesOffer") != expected_offer or len(services) != 1 or services[0].get("offers") != ({"@id": offer_id} if offer_id else None) or len(offers) != 1 or offers[0].get("itemOffered") != ({"@id": service_id} if service_id else None):
                    failures["detail_makesoffer"].append(relative)
            elif "makesOffer" in organizations[0] or "makesOffer" in businesses[0]:
                failures["detail_unconfirmed_offer"].append(relative)

        if len(webpages) == 1 and len(articles) == 1:
            page_about, page_mentions, page_parts = webpages[0].get("about"), webpages[0].get("mentions"), webpages[0].get("hasPart")
            article_about, article_mentions = articles[0].get("about"), articles[0].get("mentions")
            article_parts, article_sections = articles[0].get("hasPart"), articles[0].get("articleSection")
            semantic = (
                isinstance(page_about, list) and len(page_about) >= 2
                and isinstance(page_mentions, list) and len(page_mentions) >= 6
                and isinstance(page_parts, list) and len(page_parts) == len(manuscript_sections) + 3
                and isinstance(article_about, list) and len(article_about) >= 2
                and isinstance(article_mentions, list) and article_mentions == page_mentions
                and isinstance(article_parts, list) and len(article_parts) == len(manuscript_sections)
                and isinstance(article_sections, list) and len(article_sections) == len(manuscript_sections)
                and all(isinstance(item, str) and item in parser.h2s for item in article_sections)
            )
            if not semantic:
                failures["detail_semantic_fields"].append(relative)

        breadcrumbs = [node for node in nodes if type_has(node, "BreadcrumbList")]
        if len(breadcrumbs) == 1:
            elements = breadcrumbs[0].get("itemListElement")
            positions = [item.get("position") for item in elements if isinstance(item, Mapping)] if isinstance(elements, list) else []
            final_item = elements[-1].get("item") if isinstance(elements, list) and elements and isinstance(elements[-1], Mapping) else None
            if not isinstance(elements, list) or len(elements) != 4 or positions != [1, 2, 3, 4] or final_item != expected_canonical:
                failures["detail_breadcrumb"].append(relative)
        item_lists = [node for node in nodes if type_has(node, "ItemList")]
        if len(item_lists) == 1:
            elements = item_lists[0].get("itemListElement")
            if item_lists[0].get("numberOfItems") != 7 or not isinstance(elements, list) or len(elements) != 7:
                failures["detail_itemlist"].append(relative)

        og_images = [item.get("content", "") for item in parser.metas if item.get("property", "").lower() == "og:image"]
        twitter_images = [item.get("content", "") for item in parser.metas if item.get("name", item.get("property", "")).lower() == "twitter:image"]
        image_objects = [node for node in nodes if type_has(node, "ImageObject")]
        if len(og_images) != 1 or twitter_images != og_images or len(articles) != 1 or len(image_objects) != 1:
            failures["detail_representative_cardinality"].append(relative)
        elif articles[0].get("image") != og_images[0] or image_objects[0].get("url") != og_images[0] or image_objects[0].get("contentUrl") != og_images[0]:
            failures["detail_representative_parity"].append(relative)
        if og_images:
            split = urlsplit(og_images[0])
            image_relative = unquote(split.path).lstrip("/")
            dom_paths = {unquote(urlsplit(urljoin(DOMAIN + route, attrs.get("src", ""))).path).lstrip("/") for attrs in parser.images}
            if split.scheme != "https" or split.netloc.lower() not in HOSTS or image_relative not in filesystem_files or image_relative in dom_paths:
                failures["detail_representative_local_hidden"].append(relative)
        faq_count, faq_values = semantic_detail_faq(source_text)
        if faq_count != 1 or not faq_values or faq_values != schema_faq(nodes):
            failures["detail_faq_schema_parity"].append(relative)
        if len(parser.titles) == 1 and not all(item in parser.titles[0] for item in (locality, category.grade, category.subject + "학원")):
            failures["detail_title_structure"].append({"path": relative, "title": parser.titles[0]})
        if len(parser.h1s) == 1 and not all(item in parser.h1s[0] for item in (locality, category.grade, category.subject + "학원")):
            failures["detail_h1_structure"].append({"path": relative, "h1": parser.h1s[0]})
        details.append(DetailReport(relative, route, category, locality, status, expected_school == "missing"))

    for code, values in failures.items():
        audit.extend(code, values)
    audit.hard(len(canonicals) == FINAL_HTML_COUNT and len(set(canonicals)) == FINAL_HTML_COUNT, "canonical_cardinality", {"total": len(canonicals), "unique": len(set(canonicals))})
    audit.hard(legacy_raw == KNOWN_LEGACY_RAW_CANONICALS, "legacy_raw_canonical_baseline", legacy_raw)
    audit.hard(nav_links == FINAL_HTML_COUNT, "grade_nav_link_total", nav_links)
    audit.hard(nav_active == GRADE_ACTIVE_COUNT, "grade_nav_active_total", nav_active)
    audit.hard(
        jsonld_blocks == FINAL_JSONLD_BLOCK_COUNT,
        "jsonld_block_total",
        {"expected": FINAL_JSONLD_BLOCK_COUNT, "actual": jsonld_blocks, "baseline": BASELINE_JSONLD_BLOCK_COUNT},
    )
    audit.hard(len(details) == NEW_DETAIL_COUNT, "detail_count", len(details))
    audit.hard(status_counts == Counter({"supported": 1_053, "unconfirmed-grade": 60}), "detail_status_total", status_counts)
    for category in CATEGORIES:
        audit.hard(category_status[category.key] == Counter({"supported": category.supported, "unconfirmed-grade": category.unconfirmed}), "detail_category_status", {"category": category.key, "actual": category_status[category.key]})
        audit.hard(school_counts[category.key] == Counter({"provided": category.school_provided, "missing": category.school_missing}), "detail_category_school", {"category": category.key, "actual": school_counts[category.key]})
    audit.hard(body_map == NEW_DETAIL_COUNT * 2, "detail_body_map_total", body_map)
    audit.hard(authoritative_levels == NEW_DETAIL_COUNT, "detail_authoritative_level_total", authoritative_levels)
    audit.hard(english_distinct > 0, "detail_english_distinct_level_coverage", english_distinct)
    missing_resources = [
        {"resource": item, "count": count, "sample": resource_samples[item]}
        for item, count in resources.items() if item not in projection.documents and item not in filesystem_files
    ]
    audit.extend("missing_local_resource", missing_resources)
    audit.hard(broken == Counter({KNOWN_BROKEN_ROUTE: KNOWN_BROKEN_OCCURRENCES}), "internal_link_regression", {"actual": broken, "samples": broken_samples})
    audit.hard(bulk_hidden == KNOWN_BULK_HIDDEN_IMAGES, "baseline_bulk_hidden_images", bulk_hidden)
    audit.hard(missing_dimensions == KNOWN_MISSING_DIMENSION_IMAGES, "baseline_missing_dimensions", missing_dimensions)
    audit.hard(known_external == KNOWN_EXTERNAL_IMAGE_OCCURRENCES, "baseline_known_external_404", known_external)
    audit.hard(new_external == 0, "new_external_images", new_external)

    distances: dict[str, int] = {"/": 0}
    queue: deque[str] = deque(["/"])
    while queue:
        current = queue.popleft()
        for target in graph[current]:
            if target not in distances:
                distances[target] = distances[current] + 1
                queue.append(target)
    orphans = sorted(set(route_to_relative) - set(distances))
    audit.hard(not orphans, "orphan_routes", [route_to_relative[item] for item in orphans[:20]])
    audit.hard(max(distances.values(), default=0) <= 4, "internal_link_max_depth", max(distances.values(), default=0))
    audit.hard(distances.get(PARENT_ROUTE) == 1, "parent_link_depth", distances.get(PARENT_ROUTE))
    for category in CATEGORIES:
        audit.hard(distances.get(category.category_route) == 2, "category_link_depth", {"category": category.key, "depth": distances.get(category.category_route)})
    audit.extend("detail_link_depth", [(item.route, distances.get(item.route)) for item in details if distances.get(item.route) != 3])
    audit.observations["documents"] = {
        "html": len(all_html), "canonical": len(canonicals), "nav_links": nav_links,
        "nav_active": nav_active, "jsonld_blocks": jsonld_blocks, "details": len(details),
        "status": status_counts, "schools": school_counts, "body_map_images": body_map,
        "legacy_raw_canonicals": legacy_raw,
    }
    audit.observations["links"] = {
        "edges": sum(len(items) for items in graph.values()), "broken": broken,
        "reachable": len(distances), "orphans": len(orphans), "max_depth": max(distances.values(), default=0),
    }
    audit.observations["resources"] = {
        "references": sum(resources.values()), "unique": len(resources), "missing": len(missing_resources),
        "bulk_hidden": bulk_hidden, "missing_dimensions": missing_dimensions,
        "known_external": known_external, "new_external": new_external,
    }
    return details


def validate_git_scope(root: Path, expected_plan: set[str], audit: Audit, *, release_gate: bool) -> None:
    expected = expected_plan | {GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL}
    changed = {
        item.decode("utf-8") for item in run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"]).split(b"\0") if item
    }
    changed |= {
        item.decode("utf-8") for item in run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).split(b"\0") if item
    }
    audit.hard(changed <= expected, "git_authorized_scope", {
        "authorized": len(expected), "actual": len(changed), "extra": sorted(changed - expected)[:30],
    })
    deleted = [
        item.decode("utf-8") for item in run_git(root, ["diff", "--name-only", "--diff-filter=D", "-z", BASELINE_COMMIT, "--"]).split(b"\0") if item
    ]
    audit.hard(not deleted, "git_no_deletions", deleted[:30])
    check = subprocess.run(
        ["git", "diff", "--check", BASELINE_COMMIT, "--"], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    audit.hard(check.returncode == 0, "git_diff_check", (check.stdout + check.stderr).decode("utf-8", "replace")[-3000:])
    security: list[Any] = []
    for relative in sorted(changed):
        path = root / PurePosixPath(relative)
        if path.is_symlink() or not path.is_file():
            security.append({"path": relative, "reason": "symlink-or-nonfile"})
            continue
        value = path.read_bytes()
        if len(value) > 50_000_000:
            security.append({"path": relative, "reason": "oversize", "bytes": len(value)})
        if path.suffix.lower() in {".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi"}:
            security.append({"path": relative, "reason": "executable"})
        if path.suffix.lower() in {".html", ".xml", ".txt", ".py", ".json", ".css", ".js", ".csv"}:
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                security.append({"path": relative, "reason": "not-utf8", "error": str(exc)})
                text = ""
            if value.startswith(b"\xef\xbb\xbf"):
                security.append({"path": relative, "reason": "bom"})
            if CONTROL_RE.search(text):
                security.append({"path": relative, "reason": "control-character"})
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    security.append({"path": relative, "reason": "secret-pattern", "pattern": pattern.pattern[:80]})
    audit.extend("release_security", security)

    residue: list[str] = []
    allowed_dirs = {str(PurePosixPath(item).parent) for item in ALLOWED_BASELINE_RESIDUE}
    for relative, expected_hash in ALLOWED_BASELINE_RESIDUE.items():
        path = root / PurePosixPath(relative)
        actual = sha256(path.read_bytes()) if path.is_file() else "MISSING"
        audit.hard(actual == expected_hash and sha256(git_blob(root, relative)) == expected_hash, "baseline_residue_pin", {"path": relative, "actual": actual})
    for path in root.rglob("*"):
        relative_path = path.relative_to(root)
        if any(part in {".git", ".vercel", "node_modules"} for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        name = path.name.lower()
        if path.is_dir() and (name == "__pycache__" or name.startswith(TRANSACTION_PREFIXES)):
            if relative not in allowed_dirs:
                residue.append(relative + "/")
        elif path.is_file() and (name.endswith(RESIDUE_SUFFIXES) or re.search(r"grade6.high2.*lock", name)):
            if relative not in ALLOWED_BASELINE_RESIDUE:
                residue.append(relative)
    audit.hard(not residue, "release_residue", sorted(residue)[:50])

    head = run_git(root, ["rev-parse", "HEAD"]).decode().strip()
    origin_main = run_git(root, ["rev-parse", "--verify", "refs/remotes/origin/main"], check=False).decode().strip()
    status = run_git(root, ["status", "--porcelain=v1", "-z"])
    tracked = [item for item in run_git(root, ["ls-files", "-z"]).split(b"\0") if item]
    if release_gate:
        audit.hard(changed == expected, "git_exact_release_scope", {
            "expected": len(expected), "actual": len(changed),
            "missing": sorted(expected - changed)[:30], "extra": sorted(changed - expected)[:30],
        })
        audit.hard(len(changed) == RELEASE_CHANGE_COUNT, "git_release_change_count", len(changed))
        audit.hard(not status, "git_release_commit_required")
        audit.hard(head != BASELINE_COMMIT, "git_release_head_advanced", head)
        audit.hard(bool(origin_main) and origin_main == head, "git_origin_main_release_parity", {"head": head, "origin_main": origin_main or "MISSING"})
        audit.hard(len(tracked) == FINAL_TRACKED_COUNT, "git_final_tracked_count", len(tracked))
    else:
        audit.hard(len(tracked) in {BASELINE_TRACKED_COUNT, FINAL_TRACKED_COUNT}, "git_tracked_count_phase", len(tracked))
    audit.observations["git_scope"] = {
        "expected": len(expected), "actual": len(changed), "tracked": len(tracked),
        "head": head, "origin_main": origin_main or "MISSING", "worktree_clean": not status,
        "release_gate": release_gate, "security_errors": len(security), "residue": sorted(residue),
    }


def select_browser_cases(details: Sequence[DetailReport], audit: Audit) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = [
        {"kind": "parent", "route": PARENT_ROUTE, "relative": PARENT_REL, "hook": "parent"}
    ]
    for category in CATEGORIES:
        cases.append({
            "kind": "hub", "route": category.category_route,
            "relative": category.category_rel, "hook": category.hook, "category": category.key,
        })
        values = sorted((item for item in details if item.category == category), key=lambda item: item.locality)
        for status, kind in (("supported", "supported"), ("unconfirmed-grade", "unconfirmed")):
            matches = [item for item in values if item.status == status]
            audit.hard(bool(matches), "browser_case_boundary", {"category": category.key, "status": status})
            if matches:
                item = matches[0]
                cases.append({
                    "kind": kind, "route": item.route, "relative": item.relative,
                    "hook": category.hook, "status": status, "category": category.key,
                    "locality": item.locality,
                })
    audit.hard(len(cases) == BROWSER_ROUTE_COUNT and len({item["route"] for item in cases}) == BROWSER_ROUTE_COUNT, "browser_route_contract", cases)
    audit.observations["browser_cases"] = cases
    return cases


def parse_browser_targets(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    allowed = {"local", "preview", "live"}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--browser-target requires NAME=URL: {value}")
        name, base = value.split("=", 1)
        name, base = name.strip().lower(), base.strip().rstrip("/")
        split = urlsplit(base)
        if name not in allowed or name in result:
            raise ValueError(f"browser target must be one unique value from {sorted(allowed)}: {name}")
        if split.scheme not in {"http", "https"} or not split.netloc or split.path not in {"", "/"} or split.query or split.fragment:
            raise ValueError(f"browser target must be an origin URL: {base}")
        hostname = (split.hostname or "").lower()
        if name == "local" and hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("local target must use loopback")
        if name == "preview" and (split.scheme != "https" or not hostname.endswith(".vercel.app")):
            raise ValueError("preview target must be an HTTPS vercel.app origin")
        if name == "live" and (split.scheme != "https" or hostname not in HOSTS):
            raise ValueError(f"live target must use {DOMAIN}")
        result[name] = base
    return result


def run_browser_matrix(
    targets: Mapping[str, str], cases: Sequence[Mapping[str, str]], timeout: int,
    bypass_secret: str | None, audit: Audit, *, release_gate: bool,
) -> None:
    expected_names = {"local", "preview", "live"}
    if release_gate:
        audit.hard(set(targets) == expected_names, "browser_release_matrix", {"expected": sorted(expected_names), "actual": sorted(targets)})
    results: dict[str, Any] = {}
    for name in ("local", "preview", "live"):
        base = targets.get(name)
        if not base:
            continue
        if name == "preview":
            audit.hard(bool(bypass_secret), "preview_bypass_secret_missing")
            if not bypass_secret:
                continue
        result = BASE.run_browser(base, cases, timeout, bypass_secret=bypass_secret if name == "preview" else None)
        results[name] = result
        audit.hard(result.get("tests") == BROWSER_TEST_COUNT, "browser_test_count", {"target": name, "actual": result.get("tests")})
        audit.hard(result.get("hub_tests") == BROWSER_HUB_TEST_COUNT, "browser_hub_test_count", {"target": name, "actual": result.get("hub_tests")})
        audit.hard(result.get("failures") == 0, "browser_failures", {"target": name, "result": result})
    audit.observations["browser"] = results or {
        "status": "not-run", "required_after_materialization": ["local", "preview", "live"],
        "routes": BROWSER_ROUTE_COUNT, "widths": list(BROWSER_WIDTHS), "tests_per_target": BROWSER_TEST_COUNT,
    }


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def inspect_vercel(url: str) -> dict[str, Any]:
    executable = shutil.which("vercel.cmd") or shutil.which("vercel")
    if executable is None:
        return {"ok": False, "error": "vercel CLI not found"}
    result = subprocess.run(
        [executable, "inspect", url], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120, check=False,
    )
    output = ANSI_RE.sub("", (result.stdout + result.stderr).decode("utf-8", "replace"))
    deployment = re.search(r"\bid\s+(dpl_[A-Za-z0-9]+)", output)
    return {
        "ok": result.returncode == 0, "id": deployment.group(1) if deployment else "",
        "ready": bool(re.search(r"\bstatus\s+[^\r\n]*\bReady\b", output, re.I)),
        "production": bool(re.search(r"\btarget\s+production\b", output, re.I)),
        "wawa_alias": "https://wawa-center.kr" in output, "output_tail": output[-2500:],
    }


def validate_deployments(
    targets: Mapping[str, str], expected_preview_id: str | None,
    expected_production_id: str | None, audit: Audit, *, release_gate: bool,
) -> None:
    results: dict[str, Any] = {}
    preview = targets.get("preview")
    if preview and expected_preview_id:
        report = inspect_vercel(preview)
        results["preview"] = report
        audit.hard(report.get("ok") and report.get("ready"), "vercel_preview_ready", report)
        audit.hard(report.get("id") == expected_preview_id, "vercel_preview_id", {"expected": expected_preview_id, "actual": report.get("id")})
        audit.hard(not report.get("production"), "vercel_preview_target", report)
    if expected_production_id:
        report = inspect_vercel(DOMAIN)
        results["production"] = report
        audit.hard(report.get("ok") and report.get("ready") and report.get("production"), "vercel_production_ready", report)
        audit.hard(report.get("id") == expected_production_id, "vercel_production_id", {"expected": expected_production_id, "actual": report.get("id")})
        audit.hard(report.get("wawa_alias"), "vercel_production_alias", report)
    if release_gate:
        audit.hard(bool(expected_preview_id), "vercel_expected_preview_id_required")
        audit.hard(bool(expected_production_id), "vercel_expected_production_id_required")
    audit.observations["vercel"] = results


def run_self_test() -> dict[str, Any]:
    audit = Audit()
    audit.hard(route_for_relative("index.html") == "/", "self_route_root")
    audit.hard(route_for_relative("학년별학원/초6영어학원/명일동/index.html") == CATEGORIES[1].category_route + quote("명일동", safe="") + "/", "self_route_encoding")
    audit.hard(normalize_route("/index.html") == "/", "self_route_normalize")
    audit.hard(normalize_route("https://wawa-center.kr/학년별학원/") == PARENT_ROUTE, "self_unicode_route")
    audit.hard(normalized_text("prefix\r\n") == "prefix\n", "self_crlf")
    fragment = '<header class="site-header"><a href="/">와와</a><a class="active" href="/학년별학원/">학년별학원</a></header>'
    entries = nav_entries(fragment, PARENT_ROUTE)
    audit.hard(len(entries) == 2 and entries[1]["route"] == PARENT_ROUTE, "self_nav")
    faq = '<div data-faq><details><summary><span>Q1.</span> 질문</summary><p><strong>A.</strong> 답변</p></details></div>'
    audit.hard(visible_faq(faq) == (1, [("질문", "답변")]), "self_faq")
    numbered_answer = '<div data-faq><details><summary><span>Q.</span> 질문</summary><p><strong>A1.</strong> 답변</p></details></div>'
    audit.hard(semantic_detail_faq(numbered_answer) == (1, [("질문", "답변")]), "self_source_faq_prefixes")
    try:
        normalize_relative(ROOT, "../escape")
    except ValueError:
        pass
    else:
        audit.hard(False, "self_relative_escape")
    audit.hard(
        NEW_CATEGORY_COUNT * (DETAILS_PER_CATEGORY + 1) == NEW_HTML_COUNT
        and BASELINE_HTML_COUNT + NEW_HTML_COUNT == FINAL_HTML_COUNT
        and PLAN_DOCUMENT_COUNT + 3 == RELEASE_CHANGE_COUNT
        and BASELINE_TRACKED_COUNT + NEW_HTML_COUNT + 3 == FINAL_TRACKED_COUNT,
        "self_cardinality",
    )
    audit.hard(sum(item.supported for item in CATEGORIES) == 1_053 and sum(item.unconfirmed for item in CATEGORIES) == 60, "self_status_totals")
    audit.hard(BROWSER_ROUTE_COUNT * len(BROWSER_WIDTHS) == BROWSER_TEST_COUNT and NEW_CATEGORY_COUNT * len(BROWSER_WIDTHS) == BROWSER_HUB_TEST_COUNT, "self_browser_cardinality")
    return {"status": "FAIL" if audit.errors else "PASS", "errors": audit.errors, "holds": audit.holds, "observations": {"tests": 12}}


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--common-dir", type=Path)
    parser.add_argument("--workbook", action="append", default=[], metavar="KEY=PATH")
    parser.add_argument("--generator", type=Path)
    parser.add_argument("--content-auditor", type=Path)
    parser.add_argument("--browser-target", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--browser-timeout", type=int, default=1_800)
    parser.add_argument("--preview-bypass-env", default="VERCEL_AUTOMATION_BYPASS_SECRET")
    parser.add_argument("--expected-preview-id")
    parser.add_argument("--expected-production-id")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--release-gate", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = build_argument_parser().parse_args(argv)
    if args.self_test:
        report = run_self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report["status"] == "PASS" else 1
    started = time.monotonic()
    audit = Audit()
    root = args.root.expanduser().resolve()
    status_before = b""
    common_dir: Path | None = None
    common_before: tuple[str, int, int] | None = None
    workbook_paths: dict[str, Path] = {}
    workbook_before: dict[str, str] = {}
    try:
        audit.hard(root.is_dir(), "root_missing", str(root))
        if not root.is_dir():
            raise RuntimeError(f"root directory does not exist: {root}")
        status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
        validate_repository(root, audit)
        common_dir = discover_common_dir(root, args.common_dir)
        common_before = directory_snapshot(common_dir)
        audit.hard(common_before == EXPECTED_COMMON_SNAPSHOT, "common_snapshot", {"expected": EXPECTED_COMMON_SNAPSHOT, "actual": common_before})
        localities, authority = load_authority(common_dir, audit)
        workbook_paths = parse_workbook_args(args.workbook)
        workbook_before = {key: sha256(path.read_bytes()) for key, path in workbook_paths.items() if path.is_file()}
        source = inspect_workbooks(workbook_paths, localities, audit)
        expected_plan = expected_plan_paths(source)
        audit.hard(len(expected_plan) == PLAN_DOCUMENT_COUNT, "expected_plan_count", len(expected_plan))
        audit.observations["release_contract"] = {
            "baseline_html": BASELINE_HTML_COUNT, "new_html": NEW_HTML_COUNT,
            "final_html": FINAL_HTML_COUNT, "plan_documents": PLAN_DOCUMENT_COUNT,
            "release_changes": RELEASE_CHANGE_COUNT, "immutable_html": IMMUTABLE_HTML_COUNT,
            "final_sitemap": FINAL_HTML_COUNT, "final_tracked": FINAL_TRACKED_COUNT,
        }
        if args.baseline_only:
            audit.observations["phase"] = "baseline-only"
        else:
            generator = (args.generator or root / PurePosixPath(GENERATOR_REL)).expanduser().resolve()
            content_auditor = (args.content_auditor or root / PurePosixPath(CONTENT_AUDITOR_REL)).expanduser().resolve()
            audit.hard(generator.is_file(), "generator_missing", str(generator))
            audit.hard(content_auditor.is_file(), "content_auditor_missing", str(content_auditor))
            if not generator.is_file():
                raise RuntimeError(f"generator not found: {generator}")
            projection = run_projection(root, generator, source, common_dir, expected_plan, audit)
            if projection is None:
                raise RuntimeError("generator projection unavailable")
            phase = "actual" if not projection.changed else "projected"
            audit.observations["phase"] = phase
            validate_projected_security(root, projection, audit)
            new_html = expected_new_html(source)
            all_html = sorted(set(baseline_paths(root, "index.html")) | new_html)
            sitemap = projection.documents.get(SITEMAP_REL)
            llms = projection.documents.get(LLMS_REL)
            audit.hard(sitemap is not None, "projected_sitemap_missing")
            audit.hard(llms is not None, "projected_llms_missing")
            if sitemap is not None:
                validate_sitemap(root, sitemap, all_html, new_html, source, audit)
            if llms is not None:
                validate_llms(root, llms, audit)
            details = audit_documents(root, projection, source, authority, all_html, new_html, audit)
            validate_preservation(root, projection, all_html, new_html, audit)
            validate_pins(root, projection, generator, content_auditor, audit)
            validate_git_scope(root, expected_plan, audit, release_gate=args.release_gate)
            targets = parse_browser_targets(args.browser_target)
            cases = select_browser_cases(details, audit)
            if phase == "projected":
                audit.hard(not targets, "projected_browser_targets_not_allowed", sorted(targets))
                if args.release_gate:
                    audit.hard(False, "release_requires_materialized_projection")
            else:
                secret = os.environ.get(args.preview_bypass_env, "") if args.preview_bypass_env else ""
                run_browser_matrix(targets, cases, args.browser_timeout, secret or None, audit, release_gate=args.release_gate)
            validate_deployments(targets, args.expected_preview_id, args.expected_production_id, audit, release_gate=args.release_gate)
    except Exception as exc:
        audit.hard(False, "auditor_exception", f"{type(exc).__name__}: {exc}")
    finally:
        if root.is_dir() and status_before:
            try:
                audit.hard(status_before == run_git(root, ["status", "--porcelain=v1", "-z"]), "auditor_git_status_read_only")
            except Exception as exc:
                audit.hard(False, "auditor_status_recheck", str(exc))
        if common_dir is not None and common_before is not None:
            try:
                audit.hard(common_before == directory_snapshot(common_dir), "auditor_common_read_only")
            except Exception as exc:
                audit.hard(False, "auditor_common_recheck", str(exc))
        if workbook_paths:
            try:
                after = {key: sha256(path.read_bytes()) for key, path in workbook_paths.items() if path.is_file()}
                audit.hard(workbook_before == after, "auditor_workbooks_read_only")
            except Exception as exc:
                audit.hard(False, "auditor_workbook_recheck", str(exc))
    status = "FAIL" if audit.errors else "HOLD" if audit.holds else "PASS"
    report = {
        "status": status, "errors": audit.errors, "holds": audit.holds,
        "observations": audit.observations, "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if status == "FAIL" else 2 if status == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
