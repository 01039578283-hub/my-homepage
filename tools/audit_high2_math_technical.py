#!/usr/bin/env python3
"""Read-only technical and release gate for the high-school grade-2 math directory.

The attached workbook is data only.  This auditor never executes formulas,
macros, links, or instructions from it.  It inspects the OOXML container,
imports the approved generator, obtains its in-memory plan, proves repeatable,
idempotent and reverse-order behavior, and validates projected or materialized
HTML.  It never calls the generator apply path and never writes project files.
"""

from __future__ import annotations

import argparse
import base64
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
BASELINE_COMMIT = "b2b20303a01360cdaf4b3dc94b97f5151b55c3ab"
BASELINE_TREE = "33c329f3d9ccd721d71e3257c33d836d8b37bda9"
BASELINE_HTML_COUNT = 16_857
BASELINE_TRACKED_COUNT = 20_281
IMMUTABLE_HTML_COUNT = 16_856
NEW_CATEGORY_COUNT = 1
DETAILS_PER_CATEGORY = 371
NEW_DETAIL_COUNT = 371
NEW_HTML_COUNT = 372
PLAN_DOCUMENT_COUNT = 375
FINAL_HTML_COUNT = 17_229
RELEASE_CHANGE_COUNT = 378
FINAL_TRACKED_COUNT = 20_656
GRADE_ACTIVE_COUNT = 2_605
RELEASE_DATE = "2026-08-21"

PARENT_REL = "학년별학원/index.html"
PARENT_ROUTE = "/" + quote("학년별학원", safe="") + "/"
CATEGORY_SLUG = "고2수학학원"
CATEGORY_LABEL = "고2 수학학원"
CATEGORY_HOOK = "high2-math"
CATEGORY_REL = f"학년별학원/{CATEGORY_SLUG}/index.html"
CATEGORY_ROUTE = PARENT_ROUTE + quote(CATEGORY_SLUG, safe="") + "/"

GENERATOR_REL = "tools/generate_high2_math_pages.py"
CONTENT_AUDITOR_REL = "tools/audit_high2_math_content.py"
TECHNICAL_AUDITOR_REL = "tools/audit_high2_math_technical.py"
HEADER_CSS_REL = "assets/header.css"
SITEMAP_REL = "sitemap.xml"
LLMS_REL = "llms.txt"
ROBOTS_REL = "robots.txt"
VERCEL_REL = "vercel.json"

WORKBOOK_SHA256 = "ecb016f9ba0ae4abc7a2cd4032c3837168ad74f81885bdaa3e6ea3139adf5f68"
WORKBOOK_BYTES = 1_246_025
EXPECTED_CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
EXPECTED_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"
EXPECTED_COMMON_SNAPSHOT = (
    "18f93e215247e5089b4a7e20677e3e860165f1104007965b6d89e6980e5a6e21",
    640,
    119_418_807,
)
EXPECTED_SUPPORTED = 325
EXPECTED_UNCONFIRMED = 46
EXPECTED_SCHOOL_PROVIDED = 308
EXPECTED_SCHOOL_MISSING = 63

BASE_IMMUTABLE_HTML_MANIFEST = "5584c365f755b711a4f01e6faaa32e2878d25fc4ef1112b2dbe2752f5b0726b7"
BASE_MIDDLE3_MATH_MANIFEST = "81cb8ed8492eacd3e6a2a95568452f50c5067957dde6b99cc872ae61053f0765"
BASE_SITEMAP_SHA256 = "a54380b03a57055fdb6d11b7917c1a80d5f158bac23f079900a0294eaf8ff0fb"
BASE_LLMS_SHA256 = "77960e5373ca5d64d49d870139c1a6bacbab30012596c32f32a9adbcf397d057"
BASE_PARENT_SHA256 = "8ab82cbcfaa03f351306732c3c50661c033da53e8193e65a719bbbf7cdcd7eb2"

# Filled only after the generator and content auditor have passed independent
# review.  Pending pins produce HOLD rather than a false release PASS.
APPROVED_GENERATOR_SHA256 = "834141ca0fb02218bbee64c095e3053a72cc80d1cdf326fd137c51976240bbe3"
APPROVED_CONTENT_AUDITOR_SHA256 = "17b9c926baa0c4fc5a7e382fc8dbc4792de457d31b36e0ca74350ce111ddd4e9"
APPROVED_PLAN_CANDIDATE_SHA256 = "0dd052530657d022be08cff5ffb0eb84215efac1f85dda4eb62a500e4f817f7a"
APPROVED_PROJECTED_MANIFEST = "88ee19efd9c237c9eddfc5903bc0adc97db805de29354684c5fad3f4ac4cc54d"

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
}

EXPECTED_NAV_TARGETS = (
    "/",
    "/overview/",
    "/guide/",
    "/" + quote("교육정보", safe="") + "/",
    "/" + quote("학부모후기", safe="") + "/",
    "/" + quote("과목별학원", safe="") + "/",
    PARENT_ROUTE,
    "/center/",
)
KNOWN_BROKEN_ROUTE = "/" + "/".join(
    quote(value, safe="") for value in ("교육정보", "수학-단어-암기법")
) + "/"
KNOWN_BROKEN_OCCURRENCES = 1
KNOWN_EXTERNAL_IMAGE = "https://wawa-center.com/wp-content/uploads/2026/06/M370.jpg"
KNOWN_EXTERNAL_IMAGE_OCCURRENCES = 1
KNOWN_BULK_HIDDEN_IMAGES = 6_307
KNOWN_MISSING_DIMENSION_IMAGES = 43_407

BROWSER_WIDTHS = (320, 390, 900, 901, 1024, 1120, 1121, 1440)
BROWSER_ROUTE_COUNT = 16
BROWSER_TEST_COUNT = 128
BROWSER_HUB_TEST_COUNT = 8
PRUNED_DIRS = {".git", ".vercel", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
IGNORED_SCHEMES = ("tel:", "sms:", "mailto:", "javascript:", "data:", "blob:")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DANGEROUS_RE = re.compile(
    r"<(?:script|style|iframe|object|embed|form|base|link|meta|template)\b|"
    r"\b(?:on[a-z]+|style)\s*=|(?:href|src|action)\s*=\s*[\"']?\s*javascript:",
    re.I,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.I),
)


def _load_base() -> ModuleType:
    path = ROOT / "tools" / "audit_middle_grade_technical.py"
    name = "_high2_technical_base_" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import technical base: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.BASELINE_COMMIT = BASELINE_COMMIT
    module.BASELINE_TREE = BASELINE_TREE
    module.DOMAIN = DOMAIN
    module.HOSTS = HOSTS
    module.PARENT_REL = PARENT_REL
    module.PARENT_ROUTE = PARENT_ROUTE
    return module


BASE = _load_base()
Audit = BASE.Audit
Projection = BASE.Projection
sha256 = BASE.sha256
normalized_text = BASE.normalized_text
run_git = BASE.run_git
baseline_paths = BASE.baseline_paths
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
    workbook_path: Path
    workbook_sha256: str
    localities: tuple[str, ...]

    @property
    def locality_set(self) -> frozenset[str]:
        return frozenset(self.localities)


@dataclass(frozen=True)
class Authority:
    grades: Mapping[str, tuple[str, ...]]
    high_schools: Mapping[str, str]


@dataclass(frozen=True)
class DetailReport:
    relative: str
    route: str
    locality: str
    status: str
    school_missing: bool


def git_blob(root: Path, relative: str) -> bytes:
    return run_git(root, ["show", f"{BASELINE_COMMIT}:{relative}"])


def _csv_header(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r", "").replace("\n", "").strip()


def _csv_tokens(value: str) -> tuple[str, ...]:
    values = (unicodedata.normalize("NFC", item.strip()) for item in value.split(","))
    return tuple(dict.fromkeys(item for item in values if item))


def discover_common_dir(root: Path, supplied: Path | None) -> Path:
    candidates = (
        supplied,
        root.parent / "참고자료" / "공통자료",
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
        text = raw.decode("utf-8-sig")
        controls = CONTROL_RE.findall(text)
        audit.hard(controls in ([], ["\x08"]), code + "_control_baseline", controls)
        if controls == ["\x08"]:
            text = text.replace("\x08", "")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        originals = reader.fieldnames or []
        headers = [_csv_header(item) for item in originals]
        audit.hard(len(headers) == len(set(headers)), code + "_unique_headers", headers)
        rows: list[dict[str, str]] = []
        malformed: list[Any] = []
        for number, raw_row in enumerate(reader, 2):
            if None in raw_row:
                malformed.append({"row": number, "reason": "excess-fields"})
                continue
            row = {
                normalized: unicodedata.normalize("NFC", (raw_row[original] or "").strip())
                for original, normalized in zip(originals, headers)
            }
            rows.append(row)
        audit.extend(code + "_malformed", malformed)
        return headers, rows
    except (UnicodeError, csv.Error) as exc:
        audit.hard(False, code + "_parse", f"{type(exc).__name__}: {exc}")
        return [], []


def load_authority(common_dir: Path, audit: Audit) -> tuple[SourceSet | None, Authority]:
    center_headers, center_rows = _read_csv(
        common_dir / "센터정보 정리.csv", EXPECTED_CENTER_CSV_SHA256, audit, "center_csv"
    )
    school_headers, school_rows = _read_csv(
        common_dir / "타깃학교.csv", EXPECTED_SCHOOL_CSV_SHA256, audit, "school_csv"
    )
    locality_field = "근처 수업가능 동네"
    required_center = {locality_field, "가능학년(수학)"}
    required_school = {locality_field, "타깃학교(고)"}
    audit.hard(required_center <= set(center_headers), "center_csv_headers", center_headers)
    audit.hard(required_school <= set(school_headers), "school_csv_headers", school_headers)
    audit.hard(len(center_rows) == DETAILS_PER_CATEGORY, "center_csv_rows", len(center_rows))
    audit.hard(len(school_rows) == DETAILS_PER_CATEGORY, "school_csv_rows", len(school_rows))
    localities = tuple(row.get(locality_field, "") for row in center_rows)
    audit.hard(len(set(localities)) == DETAILS_PER_CATEGORY and all(localities), "center_locality_unique")
    school_map = {row.get(locality_field, ""): row.get("타깃학교(고)", "") for row in school_rows}
    audit.hard(set(school_map) == set(localities), "school_locality_parity", {
        "center_only": sorted(set(localities) - set(school_map))[:20],
        "school_only": sorted(set(school_map) - set(localities))[:20],
    })
    grades = {row[locality_field]: _csv_tokens(row.get("가능학년(수학)", "")) for row in center_rows if row.get(locality_field)}
    supported = sum("고2" in values for values in grades.values())
    provided = sum(bool(value) for value in school_map.values())
    audit.hard(supported == EXPECTED_SUPPORTED, "authority_supported", supported)
    audit.hard(DETAILS_PER_CATEGORY - supported == EXPECTED_UNCONFIRMED, "authority_unconfirmed")
    audit.hard(provided == EXPECTED_SCHOOL_PROVIDED, "authority_school_provided", provided)
    audit.hard(DETAILS_PER_CATEGORY - provided == EXPECTED_SCHOOL_MISSING, "authority_school_missing")
    audit.observations["authority"] = {
        "localities": len(localities), "supported": supported,
        "unconfirmed": DETAILS_PER_CATEGORY - supported,
        "school_provided": provided, "school_missing": DETAILS_PER_CATEGORY - provided,
    }
    return None, Authority(grades, school_map)


def inspect_workbook(path: Path, localities: Sequence[str], audit: Audit) -> SourceSet:
    audit.hard(path.is_file(), "workbook_missing", str(path))
    if not path.is_file():
        return SourceSet(path, "", tuple(localities))
    raw = path.read_bytes()
    digest = sha256(raw)
    audit.hard(digest == WORKBOOK_SHA256, "workbook_sha256", {"expected": WORKBOOK_SHA256, "actual": digest})
    audit.hard(len(raw) == WORKBOOK_BYTES, "workbook_bytes", len(raw))
    errors: list[Any] = []
    metrics: dict[str, Any] = {}
    try:
        with ZipFile(path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            unsafe = [
                name for name in names
                if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name)
                or any(part == ".." for part in re.split(r"[\\/]", name)) or "\x00" in name
            ]
            suspicious = [
                item.filename for item in infos
                if item.file_size > 20_000_000
                or (item.compress_size and item.file_size / item.compress_size > 100)
                or ((item.external_attr >> 16) & 0o170000) == 0o120000
            ]
            macro = [name for name in names if "vba" in name.lower() or name.lower().endswith(".bin")]
            external = [name for name in names if name.startswith("xl/externalLinks/")]
            connections = [name for name in names if "connections" in name.lower()]
            audit.hard(len(names) == 10, "workbook_zip_entry_count", len(names))
            audit.hard(len(names) == len(set(names)), "workbook_unique_entries")
            audit.extend("workbook_unsafe_entries", unsafe)
            audit.extend("workbook_suspicious_entries", suspicious)
            audit.extend("workbook_macros", macro)
            audit.extend("workbook_external_links", external)
            audit.extend("workbook_connections", connections)
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
            rel_ns = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}
            rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rels = {item.attrib["Id"]: item.attrib["Target"] for item in rel_root.findall("p:Relationship", rel_ns)}
            sheets_node = workbook.find("m:sheets", ns)
            sheets = [] if sheets_node is None else list(sheets_node)
            audit.hard(len(sheets) == 1, "workbook_sheet_count", len(sheets))
            sheet = sheets[0]
            audit.hard(sheet.attrib.get("name") == "Sheet1" and sheet.attrib.get("state", "visible") == "visible", "workbook_sheet_contract", sheet.attrib)
            rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rels[rid].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            xml = ET.fromstring(archive.read(target))
            dimension = xml.find("m:dimension", ns)
            rows = xml.findall(".//m:sheetData/m:row", ns)
            cells = xml.findall(".//m:sheetData/m:row/m:c", ns)
            formulas = xml.findall(".//m:f", ns)
            hyperlinks = xml.findall(".//m:hyperlinks/m:hyperlink", ns)
            merges = xml.findall(".//m:mergeCells/m:mergeCell", ns)
            refs = [cell.attrib.get("r", "") for cell in cells]
            types = [cell.attrib.get("t", "") for cell in cells]
            expected_refs = [f"A{value}" for value in range(1, DETAILS_PER_CATEGORY + 1)]
            audit.hard(dimension is not None and dimension.attrib.get("ref") == "A1:A371", "workbook_dimension", None if dimension is None else dimension.attrib)
            audit.hard(len(rows) == DETAILS_PER_CATEGORY and len(cells) == DETAILS_PER_CATEGORY, "workbook_row_cell_count", {"rows": len(rows), "cells": len(cells)})
            audit.hard(refs == expected_refs, "workbook_cell_order", refs[:20])
            audit.hard(set(types) == {"s"}, "workbook_shared_string_cells", Counter(types))
            audit.hard(not formulas, "workbook_formula_free", len(formulas))
            audit.hard(not hyperlinks, "workbook_hyperlink_free", len(hyperlinks))
            audit.hard(not merges, "workbook_merge_free", len(merges))
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_items = shared.findall("m:si", ns)
            audit.hard(len(shared_items) == DETAILS_PER_CATEGORY, "workbook_shared_string_count", len(shared_items))
            metrics = {
                "bytes": len(raw), "sha256": digest, "zip_entries": len(names),
                "sheets": len(sheets), "rows": len(rows), "cells": len(cells),
                "shared_strings": len(shared_items), "formulas": len(formulas),
                "hyperlinks": len(hyperlinks), "merges": len(merges),
                "macros": len(macro), "external_links": len(external),
            }
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    audit.extend("workbook_ooxml", errors)
    audit.observations["workbook"] = metrics
    return SourceSet(path.resolve(), digest, tuple(localities))


def expected_new_html(source: SourceSet) -> set[str]:
    return {
        CATEGORY_REL,
        *(f"학년별학원/{CATEGORY_SLUG}/{locality}/index.html" for locality in source.localities),
    }


def expected_plan_paths(source: SourceSet) -> set[str]:
    return {PARENT_REL, SITEMAP_REL, LLMS_REL, *expected_new_html(source)}


def load_module(path: Path) -> Any:
    name = "_high2_generator_" + sha256(path.read_bytes())[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plan_value(plan: Any, name: str, default: Any = None) -> Any:
    return plan.get(name, default) if isinstance(plan, Mapping) else getattr(plan, name, default)


def call_build_plan(function: Any, *, root: Path, workbook: Path, common_dir: Path, overrides: Mapping[str, bytes] | None) -> Any:
    signature = inspect.signature(function)
    required = {"root", "workbook_path", "common_dir", "current_overrides"}
    if not required <= set(signature.parameters):
        raise TypeError(f"build_plan signature must contain {sorted(required)}: {signature}")
    payload = None if overrides is None else {Path(path): value for path, value in overrides.items()}
    return function(root=root, workbook_path=workbook, common_dir=common_dir, current_overrides=payload)


def run_projection(root: Path, generator_path: Path, source: SourceSet, common_dir: Path, expected: set[str], audit: Audit) -> Projection | None:
    generator_sha = sha256(generator_path.read_bytes())
    strong_paths = {*expected, GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL, *PROTECTED_PINS}
    repo_before = tree_snapshot(root, strong_paths)
    common_before = directory_snapshot(common_dir)
    workbook_before = sha256(source.workbook_path.read_bytes())
    status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
    try:
        module = load_module(generator_path)
        function = getattr(module, "build_plan", None)
        audit.hard(callable(function), "generator_build_plan")
        if not callable(function):
            return None
        first = call_build_plan(function, root=root, workbook=source.workbook_path, common_dir=common_dir, overrides=None)
        documents = normalize_documents(root, first, audit, "projection_first")
        audit.hard(set(documents) == expected, "projection_exact_scope", {
            "expected": len(expected), "actual": len(documents),
            "missing": sorted(expected - set(documents))[:30],
            "extra": sorted(set(documents) - expected)[:30],
        })
        audit.hard(len(documents) == PLAN_DOCUMENT_COUNT, "projection_document_count", len(documents))
        projected_manifest = manifest(documents) if documents else ""
        before_manifest = normalize_hashes(root, plan_value(first, "before_manifest"), audit, "projection_before")
        after_manifest = normalize_hashes(root, plan_value(first, "after_manifest"), audit, "projection_after")
        expected_after = {path: sha256(value) for path, value in documents.items()}
        audit.hard(set(before_manifest) == expected, "projection_before_scope")
        audit.hard(after_manifest == expected_after, "projection_after_values", {"declared": len(after_manifest), "expected": len(expected_after)})
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
        before_errors: list[Any] = []
        for relative in expected:
            current = fs_bytes(root, relative)
            if before_exists.get(relative) != (current is not None):
                before_errors.append({"path": relative, "reason": "existence"})
            elif current is not None and before_manifest.get(relative) != sha256(current):
                before_errors.append({"path": relative, "reason": "hash"})
        audit.extend("projection_before_values", before_errors)
        declared_changed = normalize_changed(root, plan_value(first, "changed_paths", ()), audit, "projection_changed")
        actual_changed = {path for path, value in documents.items() if fs_bytes(root, path) != value}
        audit.hard(declared_changed == actual_changed, "projection_declared_changed", {
            "declared_only": sorted(declared_changed - actual_changed)[:30],
            "actual_only": sorted(actual_changed - declared_changed)[:30],
        })
        audit.hard(len(actual_changed) in {0, PLAN_DOCUMENT_COUNT}, "projection_partial_materialization", len(actual_changed))
        second_pass = normalize_changed(root, plan_value(first, "second_pass_changes", ()), audit, "projection_declared_second_pass")
        audit.hard(not second_pass, "projection_declared_second_pass_zero", sorted(second_pass)[:30])
        candidate = str(plan_value(first, "candidate_sha256", "")).lower()
        audit.hard(bool(re.fullmatch(r"[0-9a-f]{64}", candidate)), "projection_candidate_contract", candidate)
        immutable = str(plan_value(first, "immutable_html_manifest_sha256", "")).lower()
        middle3 = str(plan_value(first, "middle3_math_manifest_sha256", "")).lower()
        audit.hard(immutable == BASE_IMMUTABLE_HTML_MANIFEST, "projection_immutable_manifest", immutable)
        audit.hard(middle3 == BASE_MIDDLE3_MATH_MANIFEST, "projection_middle3_manifest", middle3)
        source_manifest = plan_value(first, "source_manifest", {})
        audit.hard(isinstance(source_manifest, Mapping), "projection_source_manifest_type")
        if isinstance(source_manifest, Mapping):
            source_values = {str(key): str(value).lower() for key, value in source_manifest.items()}
            audit.hard(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in source_values.values()), "projection_source_manifest_hashes")
            for digest, code in (
                (WORKBOOK_SHA256, "workbook"),
                (EXPECTED_CENTER_CSV_SHA256, "center"),
                (EXPECTED_SCHOOL_CSV_SHA256, "school"),
            ):
                audit.hard(digest in source_values.values(), "projection_source_pin_" + code)
        del first
        gc.collect()
        repeat = call_build_plan(function, root=root, workbook=source.workbook_path, common_dir=common_dir, overrides=None)
        repeat_manifest = compare_plan_streaming(root, repeat, documents, audit, "projection_repeat")
        audit.hard(repeat_manifest == projected_manifest, "projection_repeat_manifest")
        audit.hard(str(plan_value(repeat, "candidate_sha256", "")).lower() == candidate, "projection_repeat_candidate")
        del repeat
        gc.collect()
        second = call_build_plan(function, root=root, workbook=source.workbook_path, common_dir=common_dir, overrides=documents)
        second_manifest = compare_plan_streaming(root, second, documents, audit, "projection_second")
        audit.hard(second_manifest == projected_manifest, "projection_second_manifest")
        second_changed = normalize_changed(root, plan_value(second, "changed_paths", ()), audit, "projection_second_changed")
        audit.hard(not second_changed, "projection_second_changed_zero", sorted(second_changed)[:30])
        audit.hard(str(plan_value(second, "candidate_sha256", "")).lower() == candidate, "projection_second_candidate")
        del second
        gc.collect()
        reversed_documents = dict(reversed(list(documents.items())))
        reverse = call_build_plan(function, root=root, workbook=source.workbook_path, common_dir=common_dir, overrides=reversed_documents)
        reverse_manifest = compare_plan_streaming(root, reverse, documents, audit, "projection_reverse")
        audit.hard(reverse_manifest == projected_manifest, "projection_reverse_manifest")
        reverse_changed = normalize_changed(root, plan_value(reverse, "changed_paths", ()), audit, "projection_reverse_changed")
        audit.hard(not reverse_changed, "projection_reverse_changed_zero", sorted(reverse_changed)[:30])
        audit.hard(str(plan_value(reverse, "candidate_sha256", "")).lower() == candidate, "projection_reverse_candidate")
        del reverse, reversed_documents
        gc.collect()
        transaction = getattr(module, "transaction_self_test", None)
        audit.hard(callable(transaction), "generator_transaction_self_test")
        transaction_result: Mapping[str, Any] = {}
        if callable(transaction):
            value = transaction()
            if isinstance(value, Mapping):
                transaction_result = value
            audit.hard(bool(transaction_result) and all(item == "pass" for item in transaction_result.values()), "generator_transaction_result", dict(transaction_result))
            required_transaction = {"success", "rollback", "crash_recovery", "path_escape_rejected", "hash_freeze_rejected", "invalid_mutation_zero"}
            audit.hard(required_transaction <= set(transaction_result), "generator_transaction_coverage", sorted(transaction_result))
        audit.observations["projection"] = {
            "documents": len(documents), "changed": len(actual_changed),
            "second_changed": len(second_changed), "reverse_changed": len(reverse_changed),
            "manifest": projected_manifest, "candidate_sha256": candidate,
            "generator_sha256": generator_sha, "transaction": dict(transaction_result),
        }
        return Projection(documents, frozenset(actual_changed), candidate, projected_manifest, generator_sha)
    finally:
        audit.hard(repo_before == tree_snapshot(root, strong_paths), "projection_repo_read_only")
        audit.hard(common_before == directory_snapshot(common_dir), "projection_common_read_only")
        audit.hard(workbook_before == sha256(source.workbook_path.read_bytes()), "projection_workbook_read_only")
        audit.hard(status_before == run_git(root, ["status", "--porcelain=v1", "-z"]), "projection_git_status_read_only")


def _paths_manifest(root: Path, paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        value = (root / PurePosixPath(relative)).read_bytes()
        digest.update(relative.encode("utf-8") + b"\0" + sha256(value).encode("ascii") + b"\n")
    return digest.hexdigest()


def validate_repository(root: Path, audit: Audit) -> None:
    try:
        top = Path(run_git(root, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()).resolve()
    except Exception as exc:
        audit.hard(False, "repository_root", str(exc))
        return
    audit.hard(top == root.resolve(), "repository_root", {"expected": str(root), "actual": str(top)})
    tree = run_git(root, ["show", "--no-patch", "--format=%T", BASELINE_COMMIT]).decode().strip()
    audit.hard(tree == BASELINE_TREE, "repository_baseline_tree", {"expected": BASELINE_TREE, "actual": tree})
    files = baseline_paths(root)
    html_paths = [item for item in files if item.endswith("index.html")]
    audit.hard(len(files) == BASELINE_TRACKED_COUNT, "repository_baseline_tracked", len(files))
    audit.hard(len(html_paths) == BASELINE_HTML_COUNT, "repository_baseline_html", len(html_paths))
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
    audit.observations["repository"] = {
        "root": str(root), "baseline": BASELINE_COMMIT, "tree": tree,
        "baseline_tracked": len(files), "baseline_html": len(html_paths),
        "disk_html": disk_html, "branch": run_git(root, ["branch", "--show-current"]).decode().strip(),
        "origin": remote,
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


def validate_preservation(root: Path, projection: Projection, source: SourceSet, audit: Audit) -> None:
    baseline_html = baseline_paths(root, "index.html")
    new_html = expected_new_html(source)
    audit.hard(len(baseline_html) == BASELINE_HTML_COUNT, "preservation_baseline_html", len(baseline_html))
    audit.hard(not (set(baseline_html) & new_html), "preservation_new_disjoint", sorted(set(baseline_html) & new_html)[:20])
    authorized_existing = set(projection.documents) & set(baseline_html)
    audit.hard(authorized_existing == {PARENT_REL}, "preservation_existing_authorized", sorted(authorized_existing))
    immutable = set(baseline_html) - {PARENT_REL}
    audit.hard(len(immutable) == IMMUTABLE_HTML_COUNT, "preservation_immutable_count", len(immutable))
    current_manifest = _paths_manifest(root, immutable)
    audit.hard(current_manifest == BASE_IMMUTABLE_HTML_MANIFEST, "preservation_immutable_manifest", current_manifest)
    middle3 = {item for item in baseline_html if item.startswith("학년별학원/중3수학학원/")}
    audit.hard(len(middle3) == 372, "preservation_middle3_count", len(middle3))
    audit.hard(_paths_manifest(root, middle3) == BASE_MIDDLE3_MATH_MANIFEST, "preservation_middle3_manifest")
    diff = run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"])
    changed = {item.decode("utf-8") for item in diff.split(b"\0") if item}
    audit.hard(not (changed & immutable), "preservation_immutable_git", sorted(changed & immutable)[:30])
    audit.hard(not (changed & set(PROTECTED_PINS)), "preservation_protected_git", sorted(changed & set(PROTECTED_PINS)))
    protected_errors: list[Any] = []
    for relative, expected in PROTECTED_PINS.items():
        baseline = git_blob(root, relative)
        current = fs_bytes(root, relative)
        current_digest = "MISSING"
        if current is not None:
            try:
                current_digest = sha256(normalized_text(current.decode("utf-8")).encode("utf-8"))
            except UnicodeDecodeError:
                current_digest = sha256(current)
        if sha256(baseline) != expected or current_digest != expected:
            protected_errors.append({
                "path": relative, "expected": expected, "baseline": sha256(baseline),
                "current": current_digest,
            })
    audit.extend("preservation_protected_sha256", protected_errors)
    audit.hard(sha256(git_blob(root, PARENT_REL)) == BASE_PARENT_SHA256, "preservation_parent_baseline_pin")
    audit.hard(sha256(git_blob(root, SITEMAP_REL)) == BASE_SITEMAP_SHA256, "preservation_sitemap_baseline_pin")
    audit.hard(sha256(git_blob(root, LLMS_REL)) == BASE_LLMS_SHA256, "preservation_llms_baseline_pin")
    projected_parent = projection.documents.get(PARENT_REL, fs_bytes(root, PARENT_REL) or b"")
    try:
        current_nav = nav_fragment(projected_parent.decode("utf-8"))
        baseline_nav = nav_fragment(git_blob(root, PARENT_REL).decode("utf-8"))
        audit.hard(
            current_nav is not None and baseline_nav is not None
            and normalized_text(current_nav) == normalized_text(baseline_nav),
            "preservation_parent_nav",
        )
    except Exception as exc:
        audit.hard(False, "preservation_parent_nav", str(exc))
    audit.observations["preservation"] = {
        "baseline_html": len(baseline_html), "immutable_html": len(immutable),
        "immutable_manifest": current_manifest, "changed": len(changed),
        "protected": len(PROTECTED_PINS),
    }


def validate_sitemap(root: Path, value: bytes, all_html: Sequence[str], new_html: set[str], source: SourceSet, audit: Audit) -> None:
    rows, blocks = parse_sitemap(value, audit, "sitemap")
    locations = [location for location, _ in rows]
    expected_urls = {DOMAIN + route_for_relative(relative) for relative in all_html}
    audit.hard(len(rows) == FINAL_HTML_COUNT, "sitemap_count", len(rows))
    audit.hard(len(set(locations)) == FINAL_HTML_COUNT, "sitemap_unique", len(set(locations)))
    audit.hard(set(locations) == expected_urls, "sitemap_html_parity", {
        "missing": sorted(expected_urls - set(locations))[:30],
        "extra": sorted(set(locations) - expected_urls)[:30],
    })
    audit.hard(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", lastmod) for _, lastmod in rows), "sitemap_lastmod_contract")
    baseline_rows, baseline_blocks = parse_sitemap(git_blob(root, SITEMAP_REL), audit, "sitemap_baseline")
    audit.hard(len(baseline_rows) == BASELINE_HTML_COUNT, "sitemap_baseline_count", len(baseline_rows))
    audit.hard(blocks[:BASELINE_HTML_COUNT] == baseline_blocks, "sitemap_append_only")
    appended = rows[BASELINE_HTML_COUNT:]
    expected_order = [DOMAIN + CATEGORY_ROUTE] + [
        DOMAIN + CATEGORY_ROUTE + quote(locality, safe="") + "/" for locality in source.localities
    ]
    audit.hard(len(appended) == NEW_HTML_COUNT, "sitemap_appended_count", len(appended))
    audit.hard([location for location, _ in appended] == expected_order, "sitemap_appended_order")
    audit.hard({location for location, _ in appended} == {DOMAIN + route_for_relative(path) for path in new_html}, "sitemap_appended_scope")
    audit.hard(all(lastmod == RELEASE_DATE for _, lastmod in appended), "sitemap_new_lastmod")
    audit.observations["sitemap"] = {"rows": len(rows), "unique": len(set(locations)), "appended": len(appended)}


def validate_llms(root: Path, value: bytes, audit: Audit) -> None:
    try:
        source = normalized_text(value.decode("utf-8"))
        baseline = normalized_text(git_blob(root, LLMS_REL).decode("utf-8"))
    except Exception as exc:
        audit.hard(False, "llms_utf8", str(exc))
        return
    marker = "## 학년별학원 핵심 허브"
    audit.hard(source.count(marker) == 1 and baseline.count(marker) == 1, "llms_marker", {
        "source": source.count(marker), "baseline": baseline.count(marker),
    })
    if marker not in source or marker not in baseline:
        return
    audit.hard(source[:source.index(marker)] == baseline[:baseline.index(marker)], "llms_prefix_preservation")
    block = source[source.index(marker):]
    raw_parent = DOMAIN + "/학년별학원/"
    categories = (
        ("중1", "수학", "중1수학학원"), ("중1", "영어", "중1영어학원"),
        ("중2", "수학", "중2수학학원"), ("중2", "영어", "중2영어학원"),
        ("중3", "수학", "중3수학학원"), ("중3", "영어", "중3영어학원"),
        ("고2", "수학", CATEGORY_SLUG),
    )
    expected_lines = [f"- {grade} {subject}학원: {raw_parent}{slug}/" for grade, subject, slug in categories]
    actual_lines = [line for line in block.splitlines() if re.match(r"^- (?:중[123]|고2) (?:수학|영어)학원: ", line)]
    audit.hard(actual_lines == expected_lines, "llms_category_order", actual_lines)
    audit.hard(block.splitlines().count(f"- 학년별학원: {raw_parent}") == 1, "llms_parent_url")
    all_urls = [raw_parent + slug + "/" for _, _, slug in categories]
    audit.hard(all(source.count(url) == 1 for url in all_urls), "llms_category_url_unique", {url: source.count(url) for url in all_urls})
    lines = block.splitlines()
    audit.hard(len(lines) == 18, "llms_block_line_count", len(lines))
    audit.hard(any(all(grade in line for grade in ("중1", "중2", "중3", "고2")) for line in lines), "llms_grade_summary")
    for expected in expected_lines:
        index = lines.index(expected) if expected in lines else -1
        audit.hard(index >= 0 and index + 1 < len(lines) and lines[index + 1].startswith("  - ") and "371개" in lines[index + 1], "llms_description_contract", expected)


def manuscript_faq(source: str) -> tuple[int, list[tuple[str, str]]]:
    """Read manuscript FAQ semantics while keeping visible source labels intact.

    The workbook deliberately contains several exact label styles (for example
    ``Q.``, ``Q1.``, and unprefixed answers).  Labels remain visible in HTML,
    while FAQPage stores the semantic question/answer text without those UI
    labels.  Data hooks make that distinction unambiguous.
    """

    container_count = len(re.findall(
        r'<[^>]+\bdata-manuscript-faq(?:\s*=|\s|>)[^>]*\bdata-faq(?:\s*=|\s|>)',
        source, re.I,
    ))
    blocks = re.findall(
        r'<details\b(?=[^>]*\bdata-source-faq=["\'][^"\']+["\'])[^>]*>(.*?)</details\s*>',
        source, re.I | re.S,
    )
    values: list[tuple[str, str]] = []
    for block in blocks:
        question_match = re.search(
            r'<summary\b(?=[^>]*\bdata-source-question(?:\s*=|\s|>))[^>]*>(.*?)</summary\s*>',
            block, re.I | re.S,
        )
        answer_match = re.search(
            r'<p\b(?=[^>]*\bdata-source-answer(?:\s*=|\s|>))[^>]*>(.*?)</p\s*>',
            block, re.I | re.S,
        )
        if question_match is None or answer_match is None:
            continue
        question_markup = re.sub(r"^\s*<span\b[^>]*>.*?</span\s*>\s*", "", question_match.group(1), count=1, flags=re.I | re.S)
        answer_markup = re.sub(r"^\s*<strong\b[^>]*>.*?</strong\s*>\s*", "", answer_match.group(1), count=1, flags=re.I | re.S)
        values.append((BASE.strip_tags(question_markup), BASE.strip_tags(answer_markup)))
    return container_count, values


def audit_documents(
    root: Path,
    projection: Projection,
    source: SourceSet,
    authority: Authority,
    all_html: list[str],
    new_html: set[str],
    audit: Audit,
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
    school_counts: Counter[str] = Counter()
    nav_links = nav_active = legacy_raw = 0
    missing_dimensions = bulk_hidden = known_external = new_external = body_map = 0

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
            baseline_values = [] if baseline_parsed is None else [
                item.get("href", "") for item in baseline_parsed[1].links
                if "canonical" in item.get("rel", "").lower().split()
            ]
            canonical_ok = (
                canonical_values == baseline_values
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
        robots = [item.get("content", "") for item in parser.metas if item.get("name", "").lower() in {"robots", "googlebot", "naverbot", "yeti"}]
        if any("noindex" in item.lower() for item in robots):
            failures["noindex"].append(relative)
        fragment = nav_fragment(source_text)
        entries = nav_entries(fragment, route) if fragment else []
        if len(entries) != 9 or tuple(item["route"] for item in entries[1:]) != EXPECTED_NAV_TARGETS:
            failures["nav_contract"].append({"path": relative, "entries": entries})
        grade = [item for item in entries if item["text"] == "학년별학원"]
        nav_links += len(grade)
        active = len(grade) == 1 and "active" in grade[0]["class"].split()
        nav_active += int(active)
        should_active = relative == PARENT_REL or relative.startswith("학년별학원/")
        if len(grade) != 1 or grade[0]["route"] != PARENT_ROUTE or active != should_active:
            failures["grade_nav"].append({"path": relative, "grade": grade, "expected_active": should_active})
        nodes: list[Mapping[str, Any]] = []
        for block in parser.ld_scripts:
            try:
                payload = json.loads(block)
                if not isinstance(payload, Mapping):
                    raise TypeError("JSON-LD root is not an object")
                graph_value = payload.get("@graph")
                nodes.extend(item for item in graph_value if isinstance(item, Mapping)) if isinstance(graph_value, list) else nodes.append(payload)
            except Exception as exc:
                failures["jsonld_syntax"].append({"path": relative, "error": str(exc)})
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
                image_host = urlsplit(urljoin(DOMAIN + route, attrs.get("src", ""))).netloc.lower()
                if relative in new_html and image_host not in HOSTS:
                    new_external += 1
            if tag not in {"img", "script", "link"}:
                continue
            if tag == "link" and not ({"stylesheet", "icon", "shortcut", "apple-touch-icon", "preload", "modulepreload"} & set(attrs.get("rel", "").lower().split())):
                continue
            raw = attrs.get("src" if tag in {"img", "script"} else "href", "").strip()
            if not raw or raw.startswith(IGNORED_SCHEMES):
                continue
            target_url = urlsplit(urljoin(DOMAIN + route, html.unescape(raw)))
            if target_url.netloc.lower() not in HOSTS:
                continue
            resource = unquote(target_url.path).lstrip("/")
            if resource:
                resources[resource] += 1
                resource_samples.setdefault(resource, {"page": relative, "tag": tag, "value": raw})

        if relative == PARENT_REL:
            if len(data_nodes(parser, "data-grade-directory", "parent")) != 1:
                failures["parent_main_hook"].append(relative)
            cards = [item for item in parser.anchors if "subject-category-card" in item.get("class", "").split()]
            routes = [normalize_route(item.get("href", ""), base_route=route) for item in cards]
            expected = [
                PARENT_ROUTE + quote(slug, safe="") + "/" for slug in (
                    "중1수학학원", "중1영어학원", "중2수학학원", "중2영어학원",
                    "중3수학학원", "중3영어학원", CATEGORY_SLUG,
                )
            ]
            if routes != expected:
                failures["parent_category_cards"].append(routes)
            faq_count, faq_values = visible_faq(source_text)
            if faq_count != 1 or len(faq_values) != 2 or faq_values != schema_faq(nodes):
                failures["parent_faq_parity"].append({"visible": faq_values, "schema": schema_faq(nodes)})
            for kind in ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage"):
                if sum(type_has(node, kind) for node in nodes) != 1:
                    failures["parent_schema_cardinality"].append(kind)
            collections = [node for node in nodes if type_has(node, "CollectionPage")]
            item_lists = [node for node in nodes if type_has(node, "ItemList")]
            if len(collections) == 1:
                if not isinstance(collections[0].get("hasPart"), list) or len(collections[0]["hasPart"]) != 7:
                    failures["parent_haspart"].append(collections[0].get("hasPart"))
            if len(item_lists) == 1:
                elements = item_lists[0].get("itemListElement")
                if item_lists[0].get("numberOfItems") != 7 or not isinstance(elements, list) or len(elements) != 7:
                    failures["parent_itemlist"].append(item_lists[0])

        if relative == CATEGORY_REL:
            if len(data_nodes(parser, "data-grade-directory", CATEGORY_HOOK)) != 1:
                failures["hub_main_hook"].append(relative)
            for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
                if len(data_nodes(parser, hook)) != 1:
                    failures["hub_search_hook"].append(hook)
            cards = data_nodes(parser, "data-grade-locality")
            names = [attrs.get("data-grade-locality", "") for _, attrs in cards]
            if names != list(source.localities) or len(set(names)) != DETAILS_PER_CATEGORY:
                failures["hub_card_contract"].append({"total": len(names), "ordered": names == list(source.localities)})
            counts = Counter(normalize_route(item.get("href", ""), base_route=route) for item in parser.anchors)
            bad = [CATEGORY_ROUTE + quote(locality, safe="") + "/" for locality in source.localities if counts[CATEGORY_ROUTE + quote(locality, safe="") + "/"] != 1]
            if bad:
                failures["hub_detail_links"].append(bad[:20])
            faq_count, faq_values = visible_faq(source_text)
            if faq_count != 1 or len(faq_values) != 2 or faq_values != schema_faq(nodes):
                failures["hub_faq_parity"].append({"visible": faq_values, "schema": schema_faq(nodes)})
            for kind in ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage"):
                if sum(type_has(node, kind) for node in nodes) != 1:
                    failures["hub_schema_cardinality"].append(kind)
            item_lists = [node for node in nodes if type_has(node, "ItemList")]
            if len(item_lists) == 1:
                elements = item_lists[0].get("itemListElement")
                if item_lists[0].get("numberOfItems") != DETAILS_PER_CATEGORY or not isinstance(elements, list) or len(elements) != DETAILS_PER_CATEGORY:
                    failures["hub_itemlist"].append(item_lists[0].get("numberOfItems"))

        parts = PurePosixPath(relative).parts
        if len(parts) != 4 or parts[:2] != ("학년별학원", CATEGORY_SLUG) or parts[3] != "index.html":
            continue
        locality = parts[2]
        mains = [attrs for tag, attrs in parser.starts if tag == "main" and attrs.get("data-grade-page") == CATEGORY_HOOK]
        status = mains[0].get("data-source-status", "") if len(mains) == 1 else ""
        expected_status = "supported" if "고2" in authority.grades.get(locality, ()) else "unconfirmed-grade"
        if len(mains) != 1 or status != expected_status:
            failures["detail_status"].append({"path": relative, "expected": expected_status, "actual": status})
        status_counts[status] += 1
        fields = Counter(attrs.get("data-source-field", "") for _, attrs in data_nodes(parser, "data-source-field"))
        if fields != Counter({"grade": 1, "high-schools": 1, "address": 1, "registration": 1, "fee": 1}):
            failures["detail_source_fields"].append({"path": relative, "actual": fields})
        school_nodes = [attrs for _, attrs in data_nodes(parser, "data-source-field", "high-schools")]
        expected_school = "provided" if authority.high_schools.get(locality, "") else "missing"
        actual_school = school_nodes[0].get("data-source-status", "") if len(school_nodes) == 1 else ""
        if actual_school != expected_school:
            failures["detail_school_status"].append({"path": relative, "expected": expected_school, "actual": actual_school})
        school_counts[actual_school] += 1
        sections = data_nodes(parser, "data-manuscript-section")
        if len(data_nodes(parser, "data-manuscript")) != 1 or not sections:
            failures["detail_manuscript"].append(relative)
        if len(data_nodes(parser, "data-faq")) != 1 or len(data_nodes(parser, "data-review")) != 1:
            failures["detail_faq_review"].append(relative)
        article_match = re.search(r"<article\b(?=[^>]*\bdata-manuscript(?:\s*=|\s|>))[^>]*>.*?</article\s*>", source_text, re.I | re.S)
        if article_match is None or DANGEROUS_RE.search(article_match.group(0)):
            failures["detail_manuscript_safety"].append(relative)
        roles = [attrs.get("data-image-role", "") for attrs in parser.images]
        role_images = {key: [attrs for attrs in parser.images if attrs.get("data-image-role") == key] for key in ("body", "map")}
        if len(parser.images) != 2 or roles != ["body", "map"]:
            failures["detail_image_dom"].append({"path": relative, "roles": roles})
        body_map += sum(len(items) for items in role_images.values())
        for role, items in role_images.items():
            if len(items) != 1:
                continue
            attrs = items[0]
            valid_size = all(attrs.get(key, "").isdigit() and int(attrs[key]) > 0 for key in ("width", "height"))
            if not valid_size or attrs.get("loading") != ("eager" if role == "body" else "lazy") or attrs.get("decoding") != "async" or not attrs.get("alt", ""):
                failures["detail_image_attributes"].append({"path": relative, "role": role, "attrs": attrs})
            if role == "body" and attrs.get("fetchpriority") != "high":
                failures["detail_body_priority"].append(relative)
        checked_types = ("WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject", "Service", "Offer")
        required = {"WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject"}
        if status == "supported":
            required |= {"Service", "Offer"}
        actual_types = {kind for kind in checked_types if any(type_has(node, kind) for node in nodes)}
        if actual_types != required:
            failures["detail_schema_types"].append({"path": relative, "expected": sorted(required), "actual": sorted(actual_types)})
        for kind in checked_types:
            if sum(type_has(node, kind) for node in nodes) != (1 if kind in required else 0):
                failures["detail_schema_cardinality"].append({"path": relative, "type": kind})
        organizations = [node for node in nodes if type_has(node, "EducationalOrganization")]
        businesses = [node for node in nodes if type_has(node, "LocalBusiness")]
        services = [node for node in nodes if type_has(node, "Service")]
        offers = [node for node in nodes if type_has(node, "Offer")]
        actual_levels = organizations[0].get("educationalLevel") if len(organizations) == 1 else None
        if actual_levels != list(authority.grades.get(locality, ())):
            failures["detail_educational_level"].append({"path": relative, "expected": authority.grades.get(locality), "actual": actual_levels})
        if len(organizations) == 1 and len(businesses) == 1:
            if status == "supported":
                offer_id = offers[0].get("@id") if len(offers) == 1 else None
                service_id = services[0].get("@id") if len(services) == 1 else None
                expected_offer = [{"@id": offer_id}] if offer_id else None
                if organizations[0].get("makesOffer") != expected_offer or businesses[0].get("makesOffer") != expected_offer:
                    failures["detail_makesoffer"].append(relative)
                if len(services) != 1 or services[0].get("offers") != ({"@id": offer_id} if offer_id else None):
                    failures["detail_service_offer"].append(relative)
                if len(offers) != 1 or offers[0].get("itemOffered") != ({"@id": service_id} if service_id else None):
                    failures["detail_offer_service"].append(relative)
            elif "makesOffer" in organizations[0] or "makesOffer" in businesses[0]:
                failures["detail_unconfirmed_offer"].append(relative)
        webpages = [node for node in nodes if type_has(node, "WebPage")]
        articles = [node for node in nodes if type_has(node, "Article")]
        if len(webpages) == 1 and len(articles) == 1:
            page_about, page_mentions, page_parts = webpages[0].get("about"), webpages[0].get("mentions"), webpages[0].get("hasPart")
            article_about, article_mentions = articles[0].get("about"), articles[0].get("mentions")
            article_parts, article_sections = articles[0].get("hasPart"), articles[0].get("articleSection")
            semantic = (
                isinstance(page_about, list) and len(page_about) >= 2
                and isinstance(page_mentions, list) and len(page_mentions) >= 6
                and isinstance(page_parts, list) and len(page_parts) == len(sections) + 3
                and isinstance(article_about, list) and len(article_about) >= 2
                and isinstance(article_mentions, list) and article_mentions == page_mentions
                and isinstance(article_parts, list) and len(article_parts) == len(sections)
                and isinstance(article_sections, list) and len(article_sections) == len(sections)
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
            dom_paths = {unquote(urlsplit(urljoin(DOMAIN + route, item.get("src", ""))).path).lstrip("/") for item in parser.images}
            if split.scheme != "https" or split.netloc.lower() not in HOSTS or image_relative not in filesystem_files or image_relative in dom_paths:
                failures["detail_representative_local_hidden"].append(relative)
        faq_count, faq_values = manuscript_faq(source_text)
        if faq_count != 1 or not faq_values or faq_values != schema_faq(nodes):
            failures["detail_faq_schema_parity"].append(relative)
        if len(parser.titles) == 1 and not all(item in parser.titles[0] for item in (locality, "고2", "수학학원")):
            failures["detail_title_structure"].append({"path": relative, "title": parser.titles[0]})
        if len(parser.h1s) == 1 and not all(item in parser.h1s[0] for item in (locality, "고2", "수학학원")):
            failures["detail_h1_structure"].append({"path": relative, "h1": parser.h1s[0]})
        details.append(DetailReport(relative, route, locality, status, expected_school == "missing"))

    for code, values in failures.items():
        audit.extend(code, values)
    audit.hard(len(canonicals) == FINAL_HTML_COUNT and len(set(canonicals)) == FINAL_HTML_COUNT, "canonical_cardinality", {"total": len(canonicals), "unique": len(set(canonicals))})
    audit.hard(legacy_raw == 28, "legacy_raw_canonical_baseline", legacy_raw)
    audit.hard(nav_links == FINAL_HTML_COUNT, "grade_nav_link_total", nav_links)
    audit.hard(nav_active == GRADE_ACTIVE_COUNT, "grade_nav_active_total", nav_active)
    audit.hard(len(details) == NEW_DETAIL_COUNT, "detail_count", len(details))
    audit.hard(status_counts == Counter({"supported": EXPECTED_SUPPORTED, "unconfirmed-grade": EXPECTED_UNCONFIRMED}), "detail_status_total", status_counts)
    audit.hard(school_counts == Counter({"provided": EXPECTED_SCHOOL_PROVIDED, "missing": EXPECTED_SCHOOL_MISSING}), "detail_school_total", school_counts)
    audit.hard(body_map == NEW_DETAIL_COUNT * 2, "detail_body_map_total", body_map)
    missing_resources = [
        {"resource": item, "count": count, "sample": resource_samples[item]}
        for item, count in resources.items()
        if item not in projection.documents and item not in filesystem_files
    ]
    audit.extend("missing_local_resource", missing_resources)
    audit.hard(broken == Counter({KNOWN_BROKEN_ROUTE: KNOWN_BROKEN_OCCURRENCES}), "internal_link_regression", {"actual": broken, "samples": broken_samples})
    audit.hard(bulk_hidden == KNOWN_BULK_HIDDEN_IMAGES, "baseline_bulk_hidden_images", bulk_hidden)
    audit.hard(missing_dimensions == KNOWN_MISSING_DIMENSION_IMAGES, "baseline_missing_dimensions", missing_dimensions)
    audit.hard(known_external == KNOWN_EXTERNAL_IMAGE_OCCURRENCES, "baseline_known_external_404", known_external)
    audit.hard(new_external == 0, "new_external_images", new_external)
    distances = {"/": 0}
    queue: deque[str] = deque(["/"])
    while queue:
        current = queue.popleft()
        for target in graph[current]:
            if target not in distances:
                distances[target] = distances[current] + 1
                queue.append(target)
    orphans = sorted(set(route_to_relative) - set(distances))
    audit.hard(not orphans, "orphan_routes", [route_to_relative[item] for item in orphans[:30]])
    audit.hard(max(distances.values(), default=0) <= 4, "internal_link_max_depth", max(distances.values(), default=0))
    audit.hard(distances.get(PARENT_ROUTE) == 1, "parent_link_depth", distances.get(PARENT_ROUTE))
    audit.hard(distances.get(CATEGORY_ROUTE) == 2, "category_link_depth", distances.get(CATEGORY_ROUTE))
    audit.extend("detail_link_depth", [(item.route, distances.get(item.route)) for item in details if distances.get(item.route) != 3])
    audit.observations["documents"] = {
        "html": len(all_html), "canonical": len(canonicals), "nav_links": nav_links,
        "nav_active": nav_active, "details": len(details), "status": status_counts,
        "schools": school_counts, "legacy_raw_canonicals": legacy_raw,
    }
    audit.observations["links"] = {
        "edges": sum(len(items) for items in graph.values()), "broken": broken,
        "reachable": len(distances), "orphans": len(orphans), "max_depth": max(distances.values(), default=0),
    }
    return details


def validate_pins(root: Path, projection: Projection, generator: Path, content_auditor: Path, audit: Audit) -> None:
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


def validate_git_scope(root: Path, expected_plan: set[str], audit: Audit, *, release_gate: bool) -> None:
    expected = expected_plan | {GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL}
    tracked_raw = run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"])
    changed = {item.decode("utf-8") for item in tracked_raw.split(b"\0") if item}
    untracked_raw = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    changed |= {item.decode("utf-8") for item in untracked_raw.split(b"\0") if item}
    audit.hard(changed <= expected, "git_authorized_scope", {
        "authorized": len(expected), "actual": len(changed), "extra": sorted(changed - expected)[:30],
    })
    deleted_raw = run_git(root, ["diff", "--name-only", "--diff-filter=D", "-z", BASELINE_COMMIT, "--"])
    deleted = [item.decode("utf-8") for item in deleted_raw.split(b"\0") if item]
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
                text_value = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                security.append({"path": relative, "reason": "not-utf8", "error": str(exc)})
                text_value = ""
            if value.startswith(b"\xef\xbb\xbf"):
                security.append({"path": relative, "reason": "bom"})
            if CONTROL_RE.search(text_value):
                security.append({"path": relative, "reason": "control-character"})
            for pattern in SECRET_PATTERNS:
                if pattern.search(text_value):
                    security.append({"path": relative, "reason": "secret-pattern", "pattern": pattern.pattern[:80]})
    audit.extend("release_security", security)
    baseline_files = set(baseline_paths(root))
    residue: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if any(part in {".git", ".vercel", "node_modules"} for part in path.relative_to(root).parts):
            continue
        name = path.name.lower()
        suspicious = (
            path.is_dir() and (name == "__pycache__" or name.startswith((".grade3-math-transaction-", ".middle-grade-transaction-", ".high2-math-transaction-")))
        ) or (
            path.is_file() and (name.endswith((".pyc", ".pyo", ".txn", ".journal", ".rollback", ".partial", ".bak", ".tmp")) or re.search(r"high2.math.*lock", name))
        )
        if suspicious:
            if path.is_dir():
                descendants = {
                    item.relative_to(root).as_posix() for item in path.rglob("*") if item.is_file()
                }
                if descendants and descendants <= baseline_files:
                    continue
            if relative not in baseline_files:
                residue.append(relative + ("/" if path.is_dir() else ""))
    audit.hard(not residue, "release_residue", sorted(residue)[:50])
    head = run_git(root, ["rev-parse", "HEAD"]).decode().strip()
    origin_main = run_git(root, ["rev-parse", "--verify", "refs/remotes/origin/main"], check=False).decode().strip()
    worktree_status = run_git(root, ["status", "--porcelain=v1", "-z"])
    tracked = [item for item in run_git(root, ["ls-files", "-z"]).split(b"\0") if item]
    if release_gate:
        audit.hard(changed == expected, "git_exact_release_scope", {
            "expected": len(expected), "actual": len(changed),
            "missing": sorted(expected - changed)[:30], "extra": sorted(changed - expected)[:30],
        })
        audit.hard(len(changed) == RELEASE_CHANGE_COUNT, "git_release_change_count", len(changed))
        audit.hard(not worktree_status, "git_release_commit_required")
        audit.hard(head != BASELINE_COMMIT, "git_release_head_advanced", head)
        audit.hard(bool(origin_main) and origin_main == head, "git_origin_main_release_parity", {"head": head, "origin_main": origin_main or "MISSING"})
        audit.hard(len(tracked) == FINAL_TRACKED_COUNT, "git_final_tracked_count", len(tracked))
    else:
        audit.hard(len(tracked) in {BASELINE_TRACKED_COUNT, FINAL_TRACKED_COUNT}, "git_tracked_count_phase", len(tracked))
    audit.observations["git_scope"] = {
        "expected": len(expected), "actual": len(changed), "tracked": len(tracked),
        "head": head, "origin_main": origin_main or "MISSING", "worktree_clean": not worktree_status,
        "release_gate": release_gate, "residue": residue,
    }


def select_browser_cases(details: Sequence[DetailReport], audit: Audit) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = [
        {"kind": "parent", "route": PARENT_ROUTE, "relative": PARENT_REL, "hook": "parent"},
        {"kind": "hub", "route": CATEGORY_ROUTE, "relative": CATEGORY_REL, "hook": CATEGORY_HOOK},
    ]
    selected: list[DetailReport] = []
    seen: set[str] = set()

    def add(item: DetailReport | None) -> None:
        if item is not None and item.relative not in seen and len(selected) < BROWSER_ROUTE_COUNT - 2:
            seen.add(item.relative)
            selected.append(item)

    for status in ("supported", "unconfirmed-grade"):
        for missing in (False, True):
            add(next((item for item in details if item.status == status and item.school_missing == missing), None))
    for locality in ("명일동", "해운대 중동", "노형동", "연동", "흥덕마을"):
        add(next((item for item in details if item.locality == locality), None))
    if details:
        for index in range(0, len(details), max(1, len(details) // 20)):
            add(details[index])
    for item in details:
        add(item)
    audit.hard(len(selected) == BROWSER_ROUTE_COUNT - 2, "browser_case_count", len(selected))
    audit.hard({item.status for item in selected} == {"supported", "unconfirmed-grade"}, "browser_case_status_coverage")
    audit.hard({item.school_missing for item in selected} == {False, True}, "browser_case_school_coverage")
    cases.extend({
        "kind": "unconfirmed" if item.status == "unconfirmed-grade" else "supported",
        "route": item.route, "relative": item.relative, "hook": CATEGORY_HOOK, "status": item.status,
    } for item in selected)
    return cases


def parse_browser_targets(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--browser-target requires NAME=URL: {value}")
        name, raw = value.split("=", 1)
        name, base = name.strip().lower(), raw.strip().rstrip("/")
        split = urlsplit(base)
        if name not in {"local", "preview", "live"} or name in result:
            raise ValueError(f"invalid or duplicate browser target: {name}")
        if split.scheme not in {"http", "https"} or not split.netloc or split.path not in {"", "/"} or split.query or split.fragment:
            raise ValueError(f"browser target must be an origin URL: {base}")
        host = (split.hostname or "").lower()
        if name == "local" and host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("local target must use loopback")
        if name == "preview" and (split.scheme != "https" or not host.endswith(".vercel.app")):
            raise ValueError("preview target must be an HTTPS vercel.app origin")
        if name == "live" and (split.scheme != "https" or host not in HOSTS):
            raise ValueError("live target must be wawa-center.kr over HTTPS")
        result[name] = base
    return result


def run_browser(base: str, cases: Sequence[Mapping[str, str]], timeout: int, *, bypass_secret: str | None = None) -> dict[str, Any]:
    node = BASE.find_node()
    node_path = BASE.find_playwright_node_path()
    if node is None or node_path is None:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": "node or playwright not found"}
    headers = {}
    if bypass_secret:
        headers = {"x-vercel-protection-bypass": bypass_secret, "x-vercel-set-bypass-cookie": "true"}
    payload = base64.b64encode(json.dumps({
        "base": base.rstrip("/"), "domain": DOMAIN, "cases": list(cases),
        "widths": BROWSER_WIDTHS, "headers": headers,
    }, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = r'''
const {chromium}=require('playwright');
const cfg=JSON.parse(Buffer.from(process.argv[1],'base64').toString('utf8'));
(async()=>{const browser=await chromium.launch({headless:true});const rows=[];let hubTests=0;const baseOrigin=new URL(cfg.base).origin;
for(const item of cfg.cases){for(const width of cfg.widths){const context=await browser.newContext({viewport:{width,height:900},locale:'ko-KR'});const page=await context.newPage();
if(Object.keys(cfg.headers).length){await page.route('**/*',async route=>{const req=route.request();if(new URL(req.url()).origin===baseOrigin)await route.continue({headers:{...req.headers(),...cfg.headers}});else await route.continue()})}
const consoleErrors=[],pageErrors=[],network=[];page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});page.on('pageerror',e=>pageErrors.push(String(e)));page.on('requestfailed',r=>network.push('FAIL '+r.url()+' '+(r.failure()?.errorText||'')));page.on('response',r=>{if(r.status()>=400)network.push(r.status()+' '+r.url())});let responseStatus=0,navigationError='';
try{const response=await page.goto(cfg.base+item.route,{waitUntil:'networkidle',timeout:45000});responseStatus=response?response.status():0;await page.waitForTimeout(120)}catch(e){navigationError=String(e)}
if(['supported','unconfirmed'].includes(item.kind)){for(const role of ['body','map']){const image=page.locator(`[data-image-role="${role}"]`);if(await image.count()===1){try{await image.scrollIntoViewIfNeeded({timeout:3000});await page.waitForFunction(r=>{const e=document.querySelector(`[data-image-role="${r}"]`);return !!e&&e.complete&&e.naturalWidth>0},role,{timeout:10000})}catch{}}}}
const state=await page.evaluate(({item,domain,width})=>{const visible=e=>{if(!e)return false;const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&!e.hidden&&r.width>0&&r.height>0};const nav=[...document.querySelectorAll('.site-header .nav-links a')],rects=nav.map(e=>e.getBoundingClientRect()),overlaps=[];for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++){const a=rects[i],b=rects[j];if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.5&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.5)overlaps.push([i,j])}const tops=[...new Set(rects.map(r=>Math.round(r.top)))],rowCounts=tops.map(top=>rects.filter(r=>Math.abs(Math.round(r.top)-top)<=1).length),grade=nav.filter(a=>(a.textContent||'').replace(/\s+/g,' ').trim()==='학년별학원'),canonical=[...document.querySelectorAll('link[rel~="canonical"]')].map(e=>e.href),robots=[...document.querySelectorAll('meta[name="robots" i],meta[name="googlebot" i],meta[name="naverbot" i],meta[name="yeti" i]')].map(e=>e.content||''),header=document.querySelector('.site-header'),main=document.querySelector('main'),imgs=[...document.images].map(e=>({complete:e.complete,naturalWidth:e.naturalWidth,visible:visible(e),role:e.dataset.imageRole||''})),faq=document.querySelectorAll('[data-faq]'),faqDetails=faq.length===1?[...faq[0].querySelectorAll('details')]:[];return{title:document.title,h1:document.querySelectorAll('h1').length,canonical,expectedCanonical:domain+item.route,noindex:robots.some(x=>/noindex/i.test(x)),overflow:document.documentElement.scrollWidth>innerWidth+1,navCount:nav.length,gradeCount:grade.length,gradeActive:grade.length===1&&grade[0].classList.contains('active'),navRows:tops.length,rowCounts,overlaps,navBounds:rects.filter(r=>r.left<-1||r.right>innerWidth+1).length,headerHeight:header?.getBoundingClientRect().height||0,expectedMobile:width<=1120,mainDirectory:main?.dataset.gradeDirectory||'',mainPage:main?.dataset.gradePage||'',mainStatus:main?.dataset.sourceStatus||'',faqCount:faq.length,faqVisible:faq.length===1&&visible(faq[0]),faqDetails:faqDetails.length,roleImages:imgs.filter(x=>x.role==='body'||x.role==='map')}} ,{item,domain:cfg.domain,width});
const failures=[];if(responseStatus!==200)failures.push('http');if(navigationError)failures.push('navigation');if(consoleErrors.length)failures.push('console');if(pageErrors.length)failures.push('pageerror');if(network.length)failures.push('network');if(state.h1!==1||state.canonical.length!==1||state.canonical[0]!==state.expectedCanonical||state.noindex)failures.push('seo');if(state.overflow||state.navCount!==8||state.gradeCount!==1||!state.gradeActive||state.overlaps.length||state.navBounds)failures.push('nav');if(state.expectedMobile){if(state.navRows!==2||state.rowCounts.slice().sort().join(',')!=='4,4'||Math.abs(state.headerHeight-132)>2)failures.push('mobile-layout')}else{if(state.navRows!==1||state.rowCounts[0]!==8||Math.abs(state.headerHeight-72)>2)failures.push('desktop-layout')}if(item.kind==='parent'&&state.mainDirectory!=='parent')failures.push('parent-hook');if(item.kind==='hub'&&state.mainDirectory!==item.hook)failures.push('hub-hook');if(['supported','unconfirmed'].includes(item.kind)&&(state.mainPage!==item.hook||state.mainStatus!==item.status))failures.push('detail-hook');if(['parent','hub'].includes(item.kind)&&(state.faqCount!==1||!state.faqVisible||state.faqDetails!==2))failures.push('hub-faq');if(['supported','unconfirmed'].includes(item.kind)&&(state.faqCount!==1||!state.faqVisible||state.faqDetails<1))failures.push('detail-faq');if(['supported','unconfirmed'].includes(item.kind)&&(state.roleImages.length!==2||state.roleImages.some(x=>!x.complete||x.naturalWidth<=0||!x.visible)))failures.push('images');
let hub=null;if(item.kind==='hub'){hubTests++;hub=await page.evaluate(async()=>{const input=document.querySelector('[data-grade-search]'),clear=document.querySelector('[data-grade-clear]'),status=document.querySelector('[data-grade-status]'),cards=[...document.querySelectorAll('[data-grade-locality]')],visible=e=>{const s=getComputedStyle(e);return !e.hidden&&s.display!=='none'&&s.visibility!=='hidden'};if(!input||!clear||!status)return{error:'missing-hooks'};const initial={visible:cards.filter(visible).length,status:(status.textContent||'').replace(/\s+/g,' ').trim()};input.focus();input.value='명일동';input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,100));const filtered={visible:cards.filter(visible).length,names:cards.filter(visible).map(e=>e.getAttribute('data-grade-locality'))};clear.click();await new Promise(r=>setTimeout(r,100));return{initial,filtered,reset:{visible:cards.filter(visible).length,status:(status.textContent||'').replace(/\s+/g,' ').trim(),value:input.value,focused:document.activeElement===input}}});if(hub.error||hub.initial.visible!==371||hub.filtered.visible!==1||hub.filtered.names[0]!=='명일동'||hub.reset.visible!==371||hub.reset.value!==''||hub.reset.status!==hub.initial.status||!hub.reset.focused)failures.push('hub-search')}
rows.push({kind:item.kind,route:item.route,width,responseStatus,navigationError,consoleErrors,pageErrors,network,state,hub,failures});await context.close()}}
await browser.close();const failed=rows.filter(row=>row.failures.length);console.log(JSON.stringify({tests:rows.length,hub_tests:hubTests,failures:failed.length,failureRows:failed.slice(0,30)}))})().catch(e=>{console.error(e);process.exit(1)});
'''
    env = dict(os.environ)
    env["NODE_PATH"] = node_path
    try:
        result = subprocess.run([node, "-e", script, payload], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": "browser timeout"}
    if result.returncode:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": result.stderr.decode("utf-8", "replace")[-4000:]}
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except Exception as exc:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": f"invalid browser JSON: {exc}"}


def run_browser_matrix(targets: Mapping[str, str], cases: Sequence[Mapping[str, str]], timeout: int, bypass_secret: str | None, audit: Audit, *, release_gate: bool) -> None:
    if release_gate:
        audit.hard(set(targets) == {"local", "preview", "live"}, "browser_release_matrix", sorted(targets))
    results: dict[str, Any] = {}
    for name in ("local", "preview", "live"):
        base = targets.get(name)
        if not base:
            continue
        if name == "preview":
            audit.hard(bool(bypass_secret), "preview_bypass_secret_missing")
            if not bypass_secret:
                continue
        result = run_browser(base, cases, timeout, bypass_secret=bypass_secret if name == "preview" else None)
        results[name] = result
        audit.hard(result.get("tests") == BROWSER_TEST_COUNT, "browser_test_count", {"target": name, "actual": result.get("tests")})
        audit.hard(result.get("hub_tests") == BROWSER_HUB_TEST_COUNT, "browser_hub_test_count", {"target": name, "actual": result.get("hub_tests")})
        audit.hard(result.get("failures") == 0, "browser_failures", {"target": name, "result": result})
    audit.observations["browser"] = results


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def inspect_vercel(url: str) -> dict[str, Any]:
    executable = shutil.which("vercel.cmd") or shutil.which("vercel")
    if executable is None:
        return {"ok": False, "error": "vercel CLI not found"}
    result = subprocess.run([executable, "inspect", url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    output = ANSI_RE.sub("", (result.stdout + result.stderr).decode("utf-8", "replace"))
    deployment = re.search(r"\bid\s+(dpl_[A-Za-z0-9]+)", output)
    return {
        "ok": result.returncode == 0,
        "id": deployment.group(1) if deployment else "",
        "ready": bool(re.search(r"\bstatus\s+[^\r\n]*\bReady\b", output, re.I)),
        "production": bool(re.search(r"\btarget\s+production\b", output, re.I)),
        "wawa_alias": "https://wawa-center.kr" in output,
        "output_tail": output[-2500:],
    }


def validate_deployments(targets: Mapping[str, str], expected_preview_id: str | None, expected_production_id: str | None, audit: Audit, *, release_gate: bool) -> None:
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
    audit.hard(route_for_relative("학년별학원/고2수학학원/명일동/index.html") == CATEGORY_ROUTE + quote("명일동", safe="") + "/", "self_route_encoding")
    audit.hard(normalize_route("/index.html") == "/", "self_route_normalize")
    audit.hard(normalize_route("https://wawa-center.kr/학년별학원/") == PARENT_ROUTE, "self_unicode_route")
    audit.hard(normalized_text("prefix\r\n") == "prefix\n", "self_crlf")
    fragment = '<header class="site-header"><a href="/">와와</a><a class="active" href="/학년별학원/">학년별학원</a></header>'
    entries = nav_entries(fragment, PARENT_ROUTE)
    audit.hard(len(entries) == 2 and entries[1]["route"] == PARENT_ROUTE, "self_nav")
    faq = '<div data-faq><details><summary><span>Q1.</span> 질문</summary><p><strong>A.</strong> 답변</p></details></div>'
    audit.hard(visible_faq(faq) == (1, [("질문", "답변")]), "self_faq")
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
    return {"status": "FAIL" if audit.errors else "PASS", "errors": audit.errors, "holds": audit.holds, "observations": {"tests": 9}}


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--common-dir", type=Path)
    parser.add_argument("--workbook", type=Path, default=Path.home() / "Desktop" / "고2 수학학원.xlsx")
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
    workbook = args.workbook.expanduser().resolve()
    status_before = b""
    common_before: tuple[str, int, int] | None = None
    workbook_before = ""
    try:
        audit.hard(root.is_dir(), "root_missing", str(root))
        if not root.is_dir():
            raise RuntimeError(f"root directory does not exist: {root}")
        status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
        validate_repository(root, audit)
        common_dir = discover_common_dir(root, args.common_dir)
        common_before = directory_snapshot(common_dir)
        audit.hard(common_before == EXPECTED_COMMON_SNAPSHOT, "common_snapshot", {"expected": EXPECTED_COMMON_SNAPSHOT, "actual": common_before})
        _, authority = load_authority(common_dir, audit)
        locality_order = tuple(authority.grades)
        source = inspect_workbook(workbook, locality_order, audit)
        workbook_before = sha256(workbook.read_bytes()) if workbook.is_file() else "MISSING"
        existing_middle = {
            path.parent.name for path in (root / "학년별학원" / "중3수학학원").glob("*/index.html")
        }
        audit.hard(existing_middle == source.locality_set, "workbook_route_locality_parity", {
            "existing_only": sorted(existing_middle - source.locality_set)[:20],
            "source_only": sorted(source.locality_set - existing_middle)[:20],
        })
        expected_plan = expected_plan_paths(source)
        audit.hard(len(expected_plan) == PLAN_DOCUMENT_COUNT, "expected_plan_count", len(expected_plan))
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
            audit.observations["phase"] = "actual" if not projection.changed else "projected"
            validate_projected_security(root, projection, audit)
            validate_preservation(root, projection, source, audit)
            new_html = expected_new_html(source)
            all_html = sorted(set(baseline_paths(root, "index.html")) | new_html)
            details = audit_documents(root, projection, source, authority, all_html, new_html, audit)
            sitemap = projection.documents.get(SITEMAP_REL)
            llms = projection.documents.get(LLMS_REL)
            audit.hard(sitemap is not None, "projection_sitemap_missing")
            audit.hard(llms is not None, "projection_llms_missing")
            if sitemap is not None:
                validate_sitemap(root, sitemap, all_html, new_html, source, audit)
            if llms is not None:
                validate_llms(root, llms, audit)
            validate_pins(root, projection, generator, content_auditor, audit)
            validate_git_scope(root, expected_plan, audit, release_gate=args.release_gate)
            targets = parse_browser_targets(args.browser_target)
            cases = select_browser_cases(details, audit)
            if targets:
                secret = os.environ.get(args.preview_bypass_env, "") or None
                run_browser_matrix(targets, cases, args.browser_timeout, secret, audit, release_gate=args.release_gate)
            elif args.release_gate:
                audit.hard(False, "browser_release_matrix_missing")
            validate_deployments(targets, args.expected_preview_id, args.expected_production_id, audit, release_gate=args.release_gate)
    except Exception as exc:
        audit.hard(False, "auditor_exception", f"{type(exc).__name__}: {exc}")
    finally:
        if root.is_dir():
            audit.hard(status_before == run_git(root, ["status", "--porcelain=v1", "-z"]), "auditor_git_status_read_only")
        if common_before is not None:
            try:
                audit.hard(common_before == directory_snapshot(discover_common_dir(root, args.common_dir)), "auditor_common_read_only")
            except Exception as exc:
                audit.hard(False, "auditor_common_read_only", str(exc))
        if workbook_before:
            actual = sha256(workbook.read_bytes()) if workbook.is_file() else "MISSING"
            audit.hard(workbook_before == actual, "auditor_workbook_read_only")
    status = "FAIL" if audit.errors else "HOLD" if audit.holds else "PASS"
    report = {
        "status": status, "errors": audit.errors, "holds": audit.holds,
        "observations": audit.observations, "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if status == "FAIL" else 2 if status == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
