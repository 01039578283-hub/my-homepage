#!/usr/bin/env python3
"""Read-only technical and release gate for the five middle-grade directories.

The attached archives are data only.  This program imports the approved
generator, obtains its in-memory plan, proves deterministic/idempotent/reverse
order behavior, and audits the projected or materialized site.  It never calls
the generator apply path and never writes to the repository, source archives,
or common-data directory.
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
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, unquote, urljoin, urlsplit
from zipfile import ZipFile


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://wawa-center.kr"
HOSTS = {"wawa-center.kr", "www.wawa-center.kr"}
BASELINE_COMMIT = "9e0eee90aa21394eafd5979dd00a4f3e4f29417e"
BASELINE_TREE = "03085f37982f950d556102127b2f91f296505ed2"
BASELINE_HTML_COUNT = 14_997
BASELINE_TRACKED_COUNT = 18_418
IMMUTABLE_HTML_COUNT = 14_996
EXISTING_MIDDLE3_MATH_HTML_COUNT = 372
NEW_CATEGORY_COUNT = 5
DETAILS_PER_CATEGORY = 371
NEW_DETAIL_COUNT = 1_855
NEW_HTML_COUNT = 1_860
PLAN_DOCUMENT_COUNT = 1_863
FINAL_HTML_COUNT = 16_857
RELEASE_CHANGE_COUNT = 1_866
FINAL_TRACKED_COUNT = 20_281
GRADE_ACTIVE_COUNT = 2_233
RELEASE_DATE = "2026-08-20"

PARENT_REL = "학년별학원/index.html"
PARENT_ROUTE = "/" + quote("학년별학원", safe="") + "/"
GENERATOR_REL = "tools/generate_middle_grade_pages.py"
CONTENT_AUDITOR_REL = "tools/audit_middle_grade_content.py"
TECHNICAL_AUDITOR_REL = "tools/audit_middle_grade_technical.py"
BASE_GENERATOR_REL = "tools/generate_grade3_math_pages.py"
BASE_CONTENT_AUDITOR_REL = "tools/audit_grade3_math_content.py"
BASE_TECHNICAL_AUDITOR_REL = "tools/audit_grade3_math_technical.py"
HEADER_CSS_REL = "assets/header.css"
SITEMAP_REL = "sitemap.xml"
LLMS_REL = "llms.txt"
ROBOTS_REL = "robots.txt"
VERCEL_REL = "vercel.json"

# These three values deliberately remain pending until the generator/content
# freeze is approved.  Pending pins yield HOLD, never a false PASS.
APPROVED_GENERATOR_SHA256 = "46874729b875197b7b4c5dfc6f302aa720bf5388d2ba4d32593008346a1b36cf"
APPROVED_CONTENT_AUDITOR_SHA256 = "086273c5529ebf406624a987a7e8a231233380b912b5df6b5f2aaba528de57c6"
APPROVED_PLAN_CANDIDATE_SHA256 = "ae1a111a4642e4906dc735a51da6533a205d23cff72c254232c2507dfd1614a0"
APPROVED_PROJECTED_MANIFEST = "3dfa6a02626fb9f5840aac4fa8b086bb90c55f632aca5c1a244fbf8358bfaada"

BASE_HEADER_CSS_SHA256 = "2a4bf6dc5520ef8c194087a6530deca17eedf744933286a3c220249308ab00c7"
BASE_ROOT_HTML_SHA256 = "a53e0cbc0b5db103dfa5f80b99819a53647ef17f02463946528d20ffdf9e29f5"
BASE_ROBOTS_SHA256 = "8885ec5209a9731d33a7c774d489fe59de13182ee277bcb130f2987ce12e1794"
BASE_VERCEL_SHA256 = "64cc7a45a72a46477323ebfb2d4cac71d2a67e3012078d79093c18c60e51e53d"
BASE_GENERATOR_SHA256 = "3f16b2834ef503c239ea01bd5300599976692c4d933ba72382d931924acf1d33"
BASE_CONTENT_AUDITOR_SHA256 = "895370c5a46ba9374123d0d9f6a644b7ab0d9cc009f40ea2d0696bf3b71f4865"
BASE_TECHNICAL_AUDITOR_SHA256 = "d3f098505622127dfda5ca594b3f4251385ef99b8f5e691f31abe3222e0d68b5"
BASE_IMMUTABLE_HTML_MANIFEST = "7844dcf232eaec0bed96bcf73ed93f2cc0818488b8f155f657c549a65a29d718"
BASE_MIDDLE3_MATH_MANIFEST = "81cb8ed8492eacd3e6a2a95568452f50c5067957dde6b99cc872ae61053f0765"
BASE_SITEMAP_SHA256 = "f4c0b0c1a9fc25072f8348621119ed510a494676398067fc442842e0b69de7b4"
BASE_LLMS_SHA256 = "47bf25190544402fe5dcccd133d6bd62c5c33eecd1574c217cc885176e2c6d9b"

EXPECTED_COMMON_SNAPSHOT = (
    "18f93e215247e5089b4a7e20677e3e860165f1104007965b6d89e6980e5a6e21",
    640,
    119_418_807,
)
EXPECTED_CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
EXPECTED_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"
CENTER_DATA_NAME = "센터정보 정리.csv"


@dataclass(frozen=True)
class Category:
    key: str
    grade: str
    subject: str
    slug: str
    hook: str
    zip_name: str
    zip_sha256: str
    supported: int
    unconfirmed: int

    @property
    def label(self) -> str:
        return f"{self.grade} {self.subject}학원"

    @property
    def suffix(self) -> str:
        return f" {self.label}.txt"

    @property
    def category_rel(self) -> str:
        return f"학년별학원/{self.slug}/index.html"

    @property
    def category_route(self) -> str:
        return PARENT_ROUTE + quote(self.slug, safe="") + "/"


CATEGORIES: tuple[Category, ...] = (
    Category(
        "middle1_math", "중1", "수학", "중1수학학원", "middle1-math", "중1 수학학원.zip",
        "83ac704c654d50d98d17d38a44024358d558c3ba03c38a9799cc5fef361a6e72", 358, 13,
    ),
    Category(
        "middle1_english", "중1", "영어", "중1영어학원", "middle1-english", "중1 영어학원.zip",
        "2521a37d5c4fdb04a52eae23c33e20a4df6e9eb294782fa4505ed06d0d648154", 363, 8,
    ),
    Category(
        "middle2_math", "중2", "수학", "중2수학학원", "middle2-math", "중2 수학학원.zip",
        "d778f3839932567c78b0276360a2ad6ea4aba84127aafcd0c08ba78fab8c84d9", 358, 13,
    ),
    Category(
        "middle2_english", "중2", "영어", "중2영어학원", "middle2-english", "중2 영어학원.zip",
        "a2976c3e0e4624354cd5a63413e002e1f9cb60b4cef8a2911cf10cc3a80fa171", 363, 8,
    ),
    Category(
        "middle3_english", "중3", "영어", "중3영어학원", "middle3-english", "중3 영어학원.zip",
        "e39f5be8889607b557bb8bc1a6ec7e3cae97b51cc1fc6407b52380f5d12cfa36", 363, 8,
    ),
)
CATEGORY_BY_SLUG = {item.slug: item for item in CATEGORIES}
CATEGORY_BY_KEY = {item.key: item for item in CATEGORIES}

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
BROWSER_HUB_TEST_COUNT = 40
PRUNED_DIRS = {".git", ".vercel", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MUTATION_PRUNED_DIRS = {".git", ".vercel", "node_modules"}
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
RESIDUE_SUFFIXES = (".pyc", ".pyo", ".txn", ".journal", ".rollback", ".partial", ".bak", ".tmp")
TRANSACTION_PREFIXES = (".grade3-math-transaction-", ".middle-grade-transaction-")
ALLOWED_BASELINE_RESIDUE = {
    "tmp/__pycache__/generate_topic_child_pages.cpython-313.pyc":
        "3902772278900f03b38fab62e8a638152716069e466472b8ad50c700dfd5d1b5",
}


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return clean(re.sub(r"<[^>]*>", " ", value or ""))


def run_git(root: Path, args: Sequence[str], *, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if check and result.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            + result.stderr.decode("utf-8", "replace")[-3000:]
        )
    return result.stdout


def baseline_paths(root: Path, suffix: str | None = None) -> list[str]:
    raw = run_git(root, ["ls-tree", "-r", "--name-only", "-z", BASELINE_COMMIT])
    values = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    return values if suffix is None else [item for item in values if item.endswith(suffix)]


def git_blobs_batch(root: Path, relatives: Sequence[str]) -> dict[str, bytes]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"], cwd=root,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        query = b"".join(f"{BASELINE_COMMIT}:{relative}\n".encode("utf-8") for relative in relatives)
        stdout, stderr = process.communicate(input=query)
        if process.returncode:
            raise RuntimeError(f"git cat-file failed: {stderr.decode('utf-8', 'replace')[-3000:]}")
        result: dict[str, bytes] = {}
        offset = 0
        for relative in relatives:
            line_end = stdout.find(b"\n", offset)
            if line_end < 0:
                raise RuntimeError(f"missing cat-file header: {relative}")
            header = stdout[offset:line_end].decode("utf-8", "replace")
            parts = header.rsplit(" ", 2)
            if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
                raise RuntimeError(f"invalid cat-file header for {relative}: {header}")
            size = int(parts[2])
            start = line_end + 1
            end = start + size
            if end >= len(stdout) or stdout[end:end + 1] != b"\n":
                raise RuntimeError(f"truncated cat-file blob: {relative}")
            result[relative] = stdout[start:end]
            offset = end + 1
        if offset != len(stdout):
            raise RuntimeError(f"unexpected cat-file trailing bytes: {len(stdout) - offset}")
        return result
    finally:
        if process.poll() is None:
            process.kill()


def fs_bytes(root: Path, relative: str) -> bytes | None:
    path = root / PurePosixPath(relative)
    return path.read_bytes() if path.is_file() else None


def manifest(documents: Mapping[str, bytes]) -> str:
    rows = [f"{relative}\0{sha256(documents[relative])}" for relative in sorted(documents)]
    return sha256("\n".join(rows).encode("utf-8"))


def paths_manifest(documents: Mapping[str, bytes], paths: Iterable[str]) -> str:
    selected = {path: documents[path] for path in sorted(paths)}
    return manifest(selected)


def tree_snapshot(root: Path, content_paths: Iterable[str] = ()) -> tuple[str, int, int]:
    """Bounded mutation fingerprint; hash scoped files and metadata for the 1GB tree."""

    strong = set(content_paths)
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative_path = path.relative_to(root)
        if any(part in MUTATION_PRUNED_DIRS for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        stat = path.lstat()
        kind = "L" if path.is_symlink() else "F" if path.is_file() else "D" if path.is_dir() else "O"
        digest.update(
            f"{kind}\0{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8")
        )
        if kind != "F":
            continue
        if relative in strong:
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        count += 1
        total += stat.st_size
    return digest.hexdigest(), count, total


def directory_snapshot(root: Path) -> tuple[str, int, int]:
    if not root.is_dir():
        return "MISSING", 0, 0
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or any(part in PRUNED_DIRS for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        value = path.read_bytes()
        digest.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(value).digest())
        count += 1
        total += len(value)
    return digest.hexdigest(), count, total


def route_for_relative(relative: str) -> str:
    path = PurePosixPath(relative)
    if path.name != "index.html":
        raise ValueError(f"not an index page: {relative}")
    if str(path.parent) == ".":
        return "/"
    return "/" + "/".join(quote(part, safe="") for part in path.parent.parts) + "/"


def normalize_route(value: str, *, base_route: str = "/") -> str | None:
    value = html.unescape((value or "").strip())
    if not value or value.startswith(("#", *IGNORED_SCHEMES)):
        return None
    parts = urlsplit(urljoin(DOMAIN + base_route, value))
    if parts.scheme not in {"http", "https"} or parts.netloc.lower() not in HOSTS:
        return None
    raw = unquote(parts.path or "/").replace("\\", "/")
    raw = re.sub(r"/{2,}", "/", raw)
    if raw == "/index.html":
        raw = "/"
    elif raw.endswith("/index.html"):
        raw = raw[: -len("index.html")]
    if raw != "/" and not raw.endswith("/"):
        raw += "/"
    if raw == "/":
        return "/"
    return "/" + "/".join(quote(part, safe="") for part in raw.strip("/").split("/")) + "/"


def attrs_from_tag(value: str) -> dict[str, str]:
    attrs = {
        key.lower(): html.unescape(content)
        for key, _, content in re.findall(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", value, re.S)
    }
    for key in ("hidden", "disabled", "open"):
        if re.search(rf"(?:^|\s){key}(?:\s|>|$)", value, re.I):
            attrs.setdefault(key, "")
    return attrs


@dataclass
class Audit:
    errors: list[dict[str, Any]] = field(default_factory=list)
    holds: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)

    def hard(self, condition: bool, code: str, detail: Any = None) -> None:
        if not condition:
            self.errors.append({"code": code, "detail": detail})

    def hold(self, condition: bool, code: str, detail: Any = None) -> None:
        if not condition:
            self.holds.append({"code": code, "detail": detail})

    def extend(self, code: str, values: Iterable[Any], *, limit: int = 30) -> None:
        values = list(values)
        if values:
            self.errors.append({"code": code, "count": len(values), "samples": values[:limit]})


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.starts: list[tuple[str, dict[str, str]]] = []
        self.anchors: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.metas: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.ld_scripts: list[str] = []
        self.titles: list[str] = []
        self.h1s: list[str] = []
        self.h2s: list[str] = []
        self._capture: str | None = None
        self._capture_depth = 0
        self._capture_data: list[str] = []
        self._ld_depth = 0
        self._ld_data: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        self.starts.append((tag, data))
        if tag == "a":
            self.anchors.append(data)
        elif tag == "img":
            self.images.append(data)
        elif tag == "link":
            self.links.append(data)
        elif tag == "meta":
            self.metas.append(data)
        elif tag == "script":
            self.scripts.append(data)
            if data.get("type", "").lower() == "application/ld+json":
                self._ld_depth = 1
                self._ld_data = []
        if tag in {"title", "h1", "h2"} and self._capture is None:
            self._capture = tag
            self._capture_depth = 1
            self._capture_data = []
        elif self._capture == tag:
            self._capture_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._ld_depth and tag == "script":
            self.ld_scripts.append("".join(self._ld_data).strip())
            self._ld_depth = 0
            self._ld_data = []
        if self._capture == tag:
            self._capture_depth -= 1
            if self._capture_depth == 0:
                value = clean("".join(self._capture_data))
                if tag == "title":
                    self.titles.append(value)
                elif tag == "h1":
                    self.h1s.append(value)
                else:
                    self.h2s.append(value)
                self._capture = None
                self._capture_data = []

    def handle_data(self, data: str) -> None:
        if self._ld_depth:
            self._ld_data.append(data)
        if self._capture:
            self._capture_data.append(data)


def parse_document(value: bytes, relative: str, audit: Audit) -> tuple[str, DocumentParser] | None:
    try:
        source = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        audit.hard(False, "html_utf8", {"path": relative, "error": str(exc)})
        return None
    audit.hard(not value.startswith(b"\xef\xbb\xbf"), "html_bom", relative)
    parser = DocumentParser()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        audit.hard(False, "html_parse", {"path": relative, "error": str(exc)})
        return None
    return source, parser


def nav_fragment(source: str) -> str | None:
    match = re.search(
        r"<header\b[^>]*\bclass=[\"'][^\"']*\bsite-header\b[^\"']*[\"'][^>]*>.*?</header\s*>",
        source, re.I | re.S,
    )
    return match.group(0) if match else None


def nav_entries(fragment: str, page_route: str) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a\s*>", fragment, re.I | re.S):
        attrs = attrs_from_tag(match.group(1))
        values.append(
            {
                "text": strip_tags(match.group(2)),
                "href": attrs.get("href", ""),
                "route": normalize_route(attrs.get("href", ""), base_route=page_route) or "",
                "class": " ".join(sorted(attrs.get("class", "").split())),
            }
        )
    return values


def data_nodes(parser: DocumentParser, key: str, value: str | None = None) -> list[tuple[str, dict[str, str]]]:
    return [
        (tag, attrs) for tag, attrs in parser.starts
        if key in attrs and (value is None or attrs.get(key) == value)
    ]


def schema_nodes(parser: DocumentParser) -> list[Mapping[str, Any]]:
    values: list[Mapping[str, Any]] = []
    for block in parser.ld_scripts:
        try:
            payload = json.loads(block)
        except Exception:
            continue
        if isinstance(payload, Mapping):
            graph = payload.get("@graph")
            if isinstance(graph, list):
                values.extend(item for item in graph if isinstance(item, Mapping))
            else:
                values.append(payload)
    return values


def type_has(node: Mapping[str, Any], value: str) -> bool:
    raw = node.get("@type")
    return raw == value or isinstance(raw, list) and value in raw


def recursive_urls(value: Any, key: str | None = None) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for item_key, item_value in value.items():
            result |= recursive_urls(item_value, str(item_key))
    elif isinstance(value, list):
        for item in value:
            result |= recursive_urls(item, key)
    elif isinstance(value, str) and key in {"image", "url", "contentUrl", "thumbnailUrl"}:
        if re.search(r"\.(?:gif|jpe?g|png|webp)(?:$|[?#])", value, re.I):
            result.add(value)
    return result


@dataclass(frozen=True)
class SourceSet:
    zip_paths: Mapping[str, Path]
    localities: Mapping[str, tuple[str, ...]]
    locality_set: frozenset[str]
    source_hashes: Mapping[str, str]


@dataclass(frozen=True)
class GradeAuthority:
    """Pinned per-locality subject grades read independently from common data."""

    english: Mapping[str, tuple[str, ...]]
    math: Mapping[str, tuple[str, ...]]

    def for_page(self, category: Category, locality: str) -> tuple[str, ...] | None:
        values = self.english if category.subject == "영어" else self.math
        return values.get(locality)


def _csv_header(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r", "").replace("\n", "").strip()


def _csv_tokens(value: str) -> tuple[str, ...]:
    values = (
        unicodedata.normalize("NFC", item.strip())
        for item in value.split(",")
    )
    return tuple(dict.fromkeys(item for item in values if item))


def load_grade_authority(common_dir: Path, source: SourceSet, audit: Audit) -> GradeAuthority:
    """Read only the pinned fields needed to catch math-to-English grade leakage."""

    path = common_dir / CENTER_DATA_NAME
    audit.hard(path.is_file(), "grade_authority_missing", str(path))
    if not path.is_file():
        return GradeAuthority({}, {})
    raw = path.read_bytes()
    digest = sha256(raw)
    audit.hard(
        digest == EXPECTED_CENTER_CSV_SHA256,
        "grade_authority_sha256",
        {"expected": EXPECTED_CENTER_CSV_SHA256, "actual": digest},
    )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        audit.hard(False, "grade_authority_utf8", str(exc))
        return GradeAuthority({}, {})
    # This pinned file contains one historical backspace in an unrelated prose
    # cell.  No control value is accepted in the three fields consumed here.
    controls = CONTROL_RE.findall(text)
    audit.hard(controls in ([], ["\x08"]), "grade_authority_control_baseline", controls)
    if controls == ["\x08"]:
        text = text.replace("\x08", "")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        raw_headers = reader.fieldnames or []
        headers = [_csv_header(item) for item in raw_headers]
        audit.hard(len(headers) == len(set(headers)), "grade_authority_unique_headers")
        required = {"근처 수업가능 동네", "가능학년(영어)", "가능학년(수학)"}
        audit.hard(required <= set(headers), "grade_authority_headers", headers)
        english: dict[str, tuple[str, ...]] = {}
        math: dict[str, tuple[str, ...]] = {}
        malformed: list[Any] = []
        for row_number, raw_row in enumerate(reader, 2):
            if None in raw_row:
                malformed.append({"row": row_number, "reason": "excess-fields"})
                continue
            row = {
                normalized: unicodedata.normalize("NFC", (raw_row[original] or "").strip())
                for original, normalized in zip(raw_headers, headers)
            }
            locality = row.get("근처 수업가능 동네", "")
            if not locality or locality in english:
                malformed.append({"row": row_number, "reason": "blank-or-duplicate-locality", "locality": locality})
                continue
            for field in required:
                if CONTROL_RE.search(row.get(field, "")):
                    malformed.append({"row": row_number, "reason": "control-in-authoritative-field", "field": field})
            english[locality] = _csv_tokens(row.get("가능학년(영어)", ""))
            math[locality] = _csv_tokens(row.get("가능학년(수학)", ""))
    except (csv.Error, UnicodeError) as exc:
        audit.hard(False, "grade_authority_parse", f"{type(exc).__name__}: {exc}")
        return GradeAuthority({}, {})
    audit.extend("grade_authority_malformed", malformed)
    audit.hard(len(english) == DETAILS_PER_CATEGORY, "grade_authority_rows", len(english))
    audit.hard(set(english) == source.locality_set and set(math) == source.locality_set, "grade_authority_locality_parity", {
        "english_only": sorted(set(english) - source.locality_set)[:20],
        "source_only": sorted(source.locality_set - set(english))[:20],
    })
    supported: dict[str, int] = {}
    for category in CATEGORIES:
        values = english if category.subject == "영어" else math
        count = sum(category.grade in levels for levels in values.values())
        supported[category.key] = count
        audit.hard(count == category.supported, "grade_authority_supported", {
            "category": category.key, "expected": category.supported, "actual": count,
        })
    divergent = sum(english.get(locality) != math.get(locality) for locality in source.locality_set)
    audit.hard(divergent > 0, "grade_authority_subject_distinction", divergent)
    audit.observations["grade_authority"] = {
        "path": str(path), "sha256": digest, "rows": len(english),
        "supported": supported, "english_math_different": divergent,
    }
    return GradeAuthority(english, math)


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


def parse_zip_args(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--zip requires KEY=PATH: {value}")
        key, path = value.split("=", 1)
        if key not in CATEGORY_BY_KEY or key in result:
            raise ValueError(f"unknown or duplicate ZIP key: {key}")
        result[key] = Path(path).expanduser().resolve()
    if not result:
        folder = Path.home() / "Desktop" / "새 폴더 (2)"
        result = {item.key: (folder / item.zip_name).resolve() for item in CATEGORIES}
    if set(result) != set(CATEGORY_BY_KEY):
        raise ValueError(f"ZIP keys must be exactly {sorted(CATEGORY_BY_KEY)}")
    return result


def inspect_sources(zip_paths: Mapping[str, Path], audit: Audit) -> SourceSet:
    localities: dict[str, tuple[str, ...]] = {}
    hashes: dict[str, str] = {}
    for category in CATEGORIES:
        path = zip_paths[category.key]
        audit.hard(path.is_file(), "zip_missing", {"key": category.key, "path": str(path)})
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = sha256(raw)
        hashes[category.key] = digest
        audit.hard(
            digest == category.zip_sha256,
            "zip_sha256",
            {"key": category.key, "expected": category.zip_sha256, "actual": digest},
        )
        with ZipFile(path) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in infos]
        unsafe = [
            name for name in names
            if name.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:", name)
            or any(part == ".." for part in re.split(r"[\\/]", name))
            or "\x00" in name or "/" in name or "\\" in name
        ]
        non_nfc = [name for name in names if name != unicodedata.normalize("NFC", name)]
        suspicious_members = [
            {
                "name": item.filename, "size": item.file_size,
                "compressed": item.compress_size,
            }
            for item in infos
            if item.file_size <= 0 or item.file_size > 1_000_000
            or (item.compress_size > 0 and item.file_size / item.compress_size > 100)
            or ((item.external_attr >> 16) & 0o170000) == 0o120000
        ]
        wrong = [name for name in names if not name.endswith(category.suffix)]
        values = tuple(name[: -len(category.suffix)] for name in names if name.endswith(category.suffix))
        invalid = [
            value for value in values
            if not value.strip() or value != value.strip() or CONTROL_RE.search(value)
            or value.endswith((".", " "))
            or value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        ]
        audit.hard(len(infos) == DETAILS_PER_CATEGORY, "zip_entry_count", {"key": category.key, "actual": len(infos)})
        audit.hard(len(names) == len(set(names)), "zip_unique_entries", category.key)
        audit.hard(not unsafe, "zip_unsafe_entries", {"key": category.key, "samples": unsafe[:20]})
        audit.hard(not non_nfc, "zip_nfc_entries", {"key": category.key, "samples": non_nfc[:20]})
        audit.hard(not suspicious_members, "zip_member_security", {"key": category.key, "samples": suspicious_members[:20]})
        audit.hard(not wrong, "zip_suffix_contract", {"key": category.key, "samples": wrong[:20]})
        audit.hard(len(values) == DETAILS_PER_CATEGORY and len(set(values)) == DETAILS_PER_CATEGORY, "zip_locality_count", category.key)
        audit.hard(not invalid, "zip_locality_safety", {"key": category.key, "samples": invalid[:20]})
        audit.hard(not any(item.flag_bits & 1 for item in infos), "zip_encrypted", category.key)
        audit.hard(not any(item.file_size == 0 for item in infos), "zip_empty_member", category.key)
        localities[category.key] = values
    sets = {key: frozenset(values) for key, values in localities.items()}
    reference = next(iter(sets.values()), frozenset())
    audit.hard(len(sets) == NEW_CATEGORY_COUNT, "zip_category_count", len(sets))
    audit.hard(all(value == reference for value in sets.values()), "zip_locality_sets_equal")
    audit.hard(len(reference) == DETAILS_PER_CATEGORY, "zip_reference_locality_count", len(reference))
    audit.observations["sources"] = {
        "hashes": hashes,
        "entries": {key: len(value) for key, value in localities.items()},
        "unique_localities": len(reference),
    }
    return SourceSet(dict(zip_paths), localities, reference, hashes)


def expected_new_html(source: SourceSet) -> set[str]:
    values: set[str] = set()
    for category in CATEGORIES:
        values.add(category.category_rel)
        values.update(
            f"학년별학원/{category.slug}/{locality}/index.html"
            for locality in source.locality_set
        )
    return values


def expected_plan_paths(source: SourceSet) -> set[str]:
    return {PARENT_REL, SITEMAP_REL, LLMS_REL, *expected_new_html(source)}


def load_module(path: Path) -> Any:
    name = f"_middle_grade_generator_{sha256(path.read_bytes())[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plan_value(plan: Any, name: str, default: Any = None) -> Any:
    if isinstance(plan, Mapping):
        return plan.get(name, default)
    return getattr(plan, name, default)


def normalize_relative(root: Path, key: Any) -> str:
    path = Path(str(key))
    if path.is_absolute():
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    else:
        relative = PurePosixPath(str(key).replace("\\", "/")).as_posix()
    pure = PurePosixPath(relative)
    if relative in {"", "."} or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe relative path: {key}")
    resolved = (root / pure).resolve()
    resolved.relative_to(root.resolve())
    return relative


def normalize_documents(root: Path, plan: Any, audit: Audit, code: str) -> dict[str, bytes]:
    raw = plan_value(plan, "authorized_documents")
    audit.hard(isinstance(raw, Mapping), code + "_mapping", type(raw).__name__)
    result: dict[str, bytes] = {}
    errors: list[Any] = []
    if not isinstance(raw, Mapping):
        return result
    for key, value in raw.items():
        try:
            relative = normalize_relative(root, key)
            if relative in result:
                raise ValueError("duplicate path")
            if not isinstance(value, (str, bytes)):
                raise TypeError(type(value).__name__)
            result[relative] = value if isinstance(value, bytes) else value.encode("utf-8")
        except Exception as exc:
            errors.append({"key": str(key), "error": str(exc)})
    audit.extend(code + "_contract", errors)
    return result


def normalize_changed(root: Path, raw: Any, audit: Audit, code: str) -> set[str]:
    if raw is None:
        raw = ()
    audit.hard(isinstance(raw, (list, tuple, set, frozenset)), code + "_type", type(raw).__name__)
    values: set[str] = set()
    errors: list[Any] = []
    if isinstance(raw, (list, tuple, set, frozenset)):
        for item in raw:
            try:
                relative = normalize_relative(root, item)
                if relative in values:
                    raise ValueError("duplicate")
                values.add(relative)
            except Exception as exc:
                errors.append({"value": str(item), "error": str(exc)})
    audit.extend(code + "_contract", errors)
    return values


def normalize_hashes(root: Path, raw: Any, audit: Audit, code: str) -> dict[str, str]:
    audit.hard(isinstance(raw, Mapping), code + "_type", type(raw).__name__)
    values: dict[str, str] = {}
    errors: list[Any] = []
    if isinstance(raw, Mapping):
        for key, digest in raw.items():
            try:
                relative = normalize_relative(root, key)
                digest = str(digest).lower()
                if not re.fullmatch(r"[0-9a-f]{64}", digest) or relative in values:
                    raise ValueError("invalid or duplicate hash row")
                values[relative] = digest
            except Exception as exc:
                errors.append({"key": str(key), "value": str(digest), "error": str(exc)})
    audit.extend(code + "_contract", errors)
    return values


@dataclass(frozen=True)
class Projection:
    documents: Mapping[str, bytes]
    changed: frozenset[str]
    candidate_sha256: str
    projected_manifest: str
    generator_sha256: str


def call_build_plan(
    function: Any,
    *,
    root: Path,
    zip_paths: Mapping[str, Path],
    common_dir: Path,
    overrides: Mapping[str, bytes] | None,
) -> Any:
    signature = inspect.signature(function)
    required = {"root", "zip_paths", "common_dir", "current_overrides"}
    if not required <= set(signature.parameters):
        raise TypeError(f"build_plan signature must contain {sorted(required)}: {signature}")
    payload = None if overrides is None else {Path(path): value for path, value in overrides.items()}
    return function(root=root, zip_paths=zip_paths, common_dir=common_dir, current_overrides=payload)


def compare_documents(expected: Mapping[str, bytes], actual: Mapping[str, bytes], audit: Audit, code: str) -> None:
    audit.hard(set(actual) == set(expected), code + "_scope", {
        "missing": sorted(set(expected) - set(actual))[:30],
        "extra": sorted(set(actual) - set(expected))[:30],
    })
    differences = [path for path in set(expected) & set(actual) if expected[path] != actual[path]]
    audit.extend(code + "_values", differences)


def compare_plan_streaming(
    root: Path,
    plan: Any,
    expected: Mapping[str, bytes],
    audit: Audit,
    code: str,
) -> str:
    raw = plan_value(plan, "authorized_documents")
    audit.hard(isinstance(raw, Mapping), code + "_mapping", type(raw).__name__)
    if not isinstance(raw, Mapping):
        return ""
    hashes: dict[str, str] = {}
    errors: list[Any] = []
    differences: list[str] = []
    for key, value in raw.items():
        try:
            relative = normalize_relative(root, key)
            if relative in hashes:
                raise ValueError("duplicate path")
            if not isinstance(value, (str, bytes)):
                raise TypeError(type(value).__name__)
            encoded = value if isinstance(value, bytes) else value.encode("utf-8")
            hashes[relative] = sha256(encoded)
            if relative not in expected or expected[relative] != encoded:
                differences.append(relative)
            del encoded
        except Exception as exc:
            errors.append({"key": str(key), "error": str(exc)})
    audit.extend(code + "_contract", errors)
    audit.hard(set(hashes) == set(expected), code + "_scope", {
        "missing": sorted(set(expected) - set(hashes))[:30],
        "extra": sorted(set(hashes) - set(expected))[:30],
    })
    audit.extend(code + "_values", differences)
    rows = [f"{relative}\0{hashes[relative]}" for relative in sorted(hashes)]
    return sha256("\n".join(rows).encode("utf-8"))


def run_projection(
    root: Path,
    generator_path: Path,
    source: SourceSet,
    common_dir: Path,
    expected: set[str],
    audit: Audit,
) -> Projection | None:
    generator_sha = sha256(generator_path.read_bytes())
    strong_paths = {
        *expected, GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL,
        BASE_GENERATOR_REL, BASE_CONTENT_AUDITOR_REL, BASE_TECHNICAL_AUDITOR_REL,
        HEADER_CSS_REL, "index.html", ROBOTS_REL, VERCEL_REL,
    }
    repo_before = tree_snapshot(root, strong_paths)
    common_before = directory_snapshot(common_dir)
    zip_before = {key: sha256(path.read_bytes()) for key, path in source.zip_paths.items()}
    status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
    try:
        module = load_module(generator_path)
        function = getattr(module, "build_plan", None)
        audit.hard(callable(function), "generator_build_plan")
        if not callable(function):
            return None

        first = call_build_plan(
            function, root=root, zip_paths=source.zip_paths, common_dir=common_dir, overrides=None
        )
        documents = normalize_documents(root, first, audit, "projection_first")
        audit.hard(set(documents) == expected, "projection_exact_scope", {
            "expected": len(expected), "actual": len(documents),
            "missing": sorted(expected - set(documents))[:30], "extra": sorted(set(documents) - expected)[:30],
        })
        audit.hard(len(documents) == PLAN_DOCUMENT_COUNT, "projection_document_count", len(documents))
        projected_manifest = manifest(documents) if documents else ""

        before_manifest = normalize_hashes(root, plan_value(first, "before_manifest"), audit, "projection_before")
        after_manifest = normalize_hashes(root, plan_value(first, "after_manifest"), audit, "projection_after")
        expected_after = {path: sha256(value) for path, value in documents.items()}
        audit.hard(set(before_manifest) == expected, "projection_before_scope")
        audit.hard(after_manifest == expected_after, "projection_after_values", {
            "declared": len(after_manifest), "expected": len(expected_after)
        })
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
                before_errors.append({"path": relative, "exists": before_exists.get(relative), "actual": current is not None})
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
        immutable_manifest = str(plan_value(first, "immutable_html_manifest_sha256", "")).lower()
        middle3_manifest = str(plan_value(first, "middle3_math_manifest_sha256", "")).lower()
        audit.hard(immutable_manifest == BASE_IMMUTABLE_HTML_MANIFEST, "projection_immutable_manifest", immutable_manifest)
        audit.hard(middle3_manifest == BASE_MIDDLE3_MATH_MANIFEST, "projection_middle3_manifest", middle3_manifest)
        _PROJECTION_FIELDS.clear()
        _PROJECTION_FIELDS.update({
            "immutable_html_manifest_sha256": immutable_manifest,
            "middle3_math_manifest_sha256": middle3_manifest,
        })
        source_manifest = plan_value(first, "source_manifest", {})
        audit.hard(isinstance(source_manifest, Mapping), "projection_source_manifest_type")
        if isinstance(source_manifest, Mapping):
            source_values = {str(key): str(value).lower() for key, value in source_manifest.items()}
            audit.hard(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in source_values.values()), "projection_source_manifest_hashes")
            for category in CATEGORIES:
                matches = [value for key, value in source_values.items() if category.key in key or category.slug in key]
                audit.hard(category.zip_sha256 in matches or category.zip_sha256 in source_values.values(), "projection_source_zip_pin", category.key)
            audit.hard(EXPECTED_CENTER_CSV_SHA256 in source_values.values(), "projection_center_csv_pin")
            audit.hard(EXPECTED_SCHOOL_CSV_SHA256 in source_values.values(), "projection_school_csv_pin")

        del first
        gc.collect()
        repeat = call_build_plan(
            function, root=root, zip_paths=source.zip_paths, common_dir=common_dir, overrides=None
        )
        repeat_manifest = compare_plan_streaming(root, repeat, documents, audit, "projection_repeat")
        audit.hard(repeat_manifest == projected_manifest, "projection_repeat_manifest", {"first": projected_manifest, "repeat": repeat_manifest})
        audit.hard(str(plan_value(repeat, "candidate_sha256", "")).lower() == candidate, "projection_repeat_candidate")
        del repeat
        gc.collect()

        second = call_build_plan(
            function, root=root, zip_paths=source.zip_paths, common_dir=common_dir, overrides=documents
        )
        second_manifest = compare_plan_streaming(root, second, documents, audit, "projection_second")
        audit.hard(second_manifest == projected_manifest, "projection_second_manifest", {"first": projected_manifest, "second": second_manifest})
        second_changed = normalize_changed(root, plan_value(second, "changed_paths", ()), audit, "projection_second_changed")
        audit.hard(not second_changed, "projection_second_changed_zero", sorted(second_changed)[:30])
        audit.hard(str(plan_value(second, "candidate_sha256", "")).lower() == candidate, "projection_second_candidate")
        del second
        gc.collect()

        reversed_documents = dict(reversed(list(documents.items())))
        reverse = call_build_plan(
            function, root=root, zip_paths=source.zip_paths, common_dir=common_dir, overrides=reversed_documents
        )
        reverse_manifest = compare_plan_streaming(root, reverse, documents, audit, "projection_reverse")
        audit.hard(reverse_manifest == projected_manifest, "projection_reverse_manifest", {"first": projected_manifest, "reverse": reverse_manifest})
        reverse_changed = normalize_changed(root, plan_value(reverse, "changed_paths", ()), audit, "projection_reverse_changed")
        audit.hard(not reverse_changed, "projection_reverse_changed_zero", sorted(reverse_changed)[:30])
        audit.hard(str(plan_value(reverse, "candidate_sha256", "")).lower() == candidate, "projection_reverse_candidate")
        del reverse, reversed_documents
        gc.collect()

        audit.observations["projection"] = {
            "documents": len(documents), "changed": len(actual_changed),
            "second_changed": len(second_changed), "reverse_changed": len(reverse_changed),
            "manifest": projected_manifest, "candidate_sha256": candidate,
            "generator_sha256": generator_sha,
        }
        return Projection(documents, frozenset(actual_changed), candidate, projected_manifest, generator_sha)
    finally:
        repo_after = tree_snapshot(root, strong_paths)
        common_after = directory_snapshot(common_dir)
        zip_after = {key: sha256(path.read_bytes()) for key, path in source.zip_paths.items() if path.is_file()}
        status_after = run_git(root, ["status", "--porcelain=v1", "-z"])
        audit.hard(repo_before == repo_after, "projection_repo_read_only", {"before": repo_before, "after": repo_after})
        audit.hard(common_before == common_after, "projection_common_read_only", {"before": common_before, "after": common_after})
        audit.hard(zip_before == zip_after, "projection_zips_read_only")
        audit.hard(status_before == status_after, "projection_git_status_read_only")
        audit.observations["projection_freeze"] = {
            "repo": repo_before, "common": common_before, "zips": zip_before,
            "git_status_equal": status_before == status_after,
        }


def git_blob(root: Path, relative: str) -> bytes:
    return run_git(root, ["show", f"{BASELINE_COMMIT}:{relative}"])


def generator_files_manifest(paths: Iterable[str], reader: Any) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        value = reader(relative)
        if value is None:
            raise FileNotFoundError(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(value).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def parse_sitemap(value: bytes, audit: Audit, code: str) -> tuple[list[tuple[str, str]], list[str]]:
    try:
        source = value.decode("utf-8")
        root = ET.fromstring(source)
    except Exception as exc:
        audit.hard(False, code + "_xml", f"{type(exc).__name__}: {exc}")
        return [], []
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    audit.hard(root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset", code + "_root", root.tag)
    rows = [
        (
            (node.findtext("s:loc", default="", namespaces=namespace) or "").strip(),
            (node.findtext("s:lastmod", default="", namespaces=namespace) or "").strip(),
        )
        for node in root.findall("s:url", namespace)
    ]
    blocks = re.findall(r"[ \t]*<url>.*?</url>", normalized_text(source), re.S)
    audit.hard(len(rows) == len(blocks), code + "_block_count", {"rows": len(rows), "blocks": len(blocks)})
    return rows, blocks


class FAQParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.faq_count = 0
        self._faq_depth = 0
        self._details_depth = 0
        self._capture: str | None = None
        self._capture_depth = 0
        self._capture_data: list[str] = []
        self.questions: list[str] = []
        self.answers: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if self._faq_depth:
            self._faq_depth += 1
        elif "data-faq" in data:
            self._faq_depth = 1
            self.faq_count += 1
        if not self._faq_depth:
            return
        if tag == "details":
            self._details_depth += 1
        if self._details_depth and tag in {"summary", "p"} and self._capture is None:
            self._capture = tag
            self._capture_depth = 1
            self._capture_data = []
        elif self._capture == tag:
            self._capture_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture == tag:
            self._capture_depth -= 1
            if self._capture_depth == 0:
                value = clean("".join(self._capture_data))
                if tag == "summary":
                    value = re.sub(r"^Q\d+[.)]?\s*", "", value).strip()
                    self.questions.append(value)
                else:
                    value = re.sub(r"^A[.)]?\s*", "", value).strip()
                    self.answers.append(value)
                self._capture = None
                self._capture_data = []
        if self._faq_depth:
            if tag == "details" and self._details_depth:
                self._details_depth -= 1
            self._faq_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._capture_data.append(data)


def visible_faq(source: str) -> tuple[int, list[tuple[str, str]]]:
    parser = FAQParser()
    parser.feed(source)
    parser.close()
    return parser.faq_count, list(zip(parser.questions, parser.answers))


def schema_faq(nodes: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    pages = [node for node in nodes if type_has(node, "FAQPage")]
    if len(pages) != 1 or not isinstance(pages[0].get("mainEntity"), list):
        return []
    values: list[tuple[str, str]] = []
    for item in pages[0]["mainEntity"]:
        if not isinstance(item, Mapping):
            continue
        answer = item.get("acceptedAnswer")
        if isinstance(answer, Mapping):
            values.append((clean(str(item.get("name", ""))), clean(str(answer.get("text", "")))))
    return values


def validate_sitemap(
    root: Path,
    value: bytes,
    all_html: Sequence[str],
    new_html: set[str],
    locality_order: Sequence[str],
    audit: Audit,
) -> None:
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
    expected_new_urls = {DOMAIN + route_for_relative(relative) for relative in new_html}
    expected_new_order: list[str] = []
    for category in CATEGORIES:
        expected_new_order.append(DOMAIN + category.category_route)
        expected_new_order.extend(
            DOMAIN + category.category_route + quote(locality, safe="") + "/"
            for locality in locality_order
        )
    audit.hard(len(appended) == NEW_HTML_COUNT, "sitemap_appended_count", len(appended))
    audit.hard({location for location, _ in appended} == expected_new_urls, "sitemap_appended_scope")
    audit.hard([location for location, _ in appended] == expected_new_order, "sitemap_appended_order")
    audit.hard(all(lastmod == RELEASE_DATE for _, lastmod in appended), "sitemap_new_lastmod")
    audit.observations["sitemap"] = {
        "rows": len(rows), "unique": len(set(locations)), "appended": len(appended),
        "release_date": sum(lastmod == RELEASE_DATE for _, lastmod in rows),
    }


def validate_llms(root: Path, value: bytes, audit: Audit) -> None:
    try:
        source = value.decode("utf-8")
        baseline = git_blob(root, LLMS_REL).decode("utf-8")
    except Exception as exc:
        audit.hard(False, "llms_utf8", str(exc))
        return
    marker = "## 학년별학원 핵심 허브"
    audit.hard(source.count(marker) == 1, "llms_marker", source.count(marker))
    audit.hard(baseline.count(marker) == 1, "llms_baseline_marker", baseline.count(marker))
    if marker in source and marker in baseline:
        source_prefix = normalized_text(source[: source.index(marker)])
        baseline_prefix = normalized_text(baseline[: baseline.index(marker)])
        audit.hard(source_prefix == baseline_prefix, "llms_prefix_preservation")
    raw_parent = DOMAIN + "/학년별학원/"
    category_urls = [
        *[raw_parent + item.slug + "/" for item in CATEGORIES],
        raw_parent + "중3수학학원/",
    ]
    source_lines = normalized_text(source).splitlines()
    url_counts = {url: source.count(url) for url in category_urls}
    url_counts[raw_parent] = source_lines.count(f"- 학년별학원: {raw_parent}")
    audit.hard(all(count == 1 for count in url_counts.values()), "llms_grade_urls", url_counts)
    audit.hard(all(item.label in source for item in CATEGORIES), "llms_category_labels")
    ordered_categories = (
        ("중1", "수학", "중1수학학원"), ("중1", "영어", "중1영어학원"),
        ("중2", "수학", "중2수학학원"), ("중2", "영어", "중2영어학원"),
        ("중3", "수학", "중3수학학원"), ("중3", "영어", "중3영어학원"),
    )
    expected_lines = [
        marker, "",
        f"- 학년별학원: {raw_parent}",
        "  - 중1·중2·중3의 영어·수학 지역 안내를 학년과 과목별로 찾는 핵심 허브입니다.",
    ]
    for grade, subject, slug in ordered_categories:
        expected_lines.extend([
            f"- {grade} {subject}학원: {raw_parent}{slug}/",
            f"  - {grade} {subject} 진단·학교 자료·오답 재학습·상담 기준을 371개 동네별 원고로 안내합니다.",
        ])
    expected_block = "\n".join(expected_lines) + "\n"
    actual_block = normalized_text(source[source.index(marker):]) if marker in source else ""
    audit.hard(actual_block == expected_block, "llms_unicode_block_exact")


@dataclass(frozen=True)
class DetailReport:
    relative: str
    route: str
    category: Category
    locality: str
    status: str
    school_missing: bool


def detail_identity(relative: str) -> tuple[Category, str] | None:
    parts = PurePosixPath(relative).parts
    if len(parts) != 4 or parts[0] != "학년별학원" or parts[3] != "index.html":
        return None
    category = CATEGORY_BY_SLUG.get(parts[1])
    return (category, parts[2]) if category else None


def audit_documents(
    root: Path,
    projection: Projection,
    source: SourceSet,
    grade_authority: GradeAuthority,
    all_html: list[str],
    new_html: set[str],
    audit: Audit,
) -> list[DetailReport]:
    audit.hard(len(all_html) == FINAL_HTML_COUNT, "final_html_count", len(all_html))
    route_to_relative = {route_for_relative(relative): relative for relative in all_html}
    audit.hard(len(route_to_relative) == FINAL_HTML_COUNT, "final_route_unique", len(route_to_relative))
    filesystem_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not any(part in PRUNED_DIRS for part in path.relative_to(root).parts)
    }

    def read(relative: str) -> bytes | None:
        return projection.documents.get(relative, fs_bytes(root, relative))

    hard_samples: defaultdict[str, list[Any]] = defaultdict(list)
    canonicals: list[str] = []
    graph: defaultdict[str, set[str]] = defaultdict(set)
    broken: Counter[str] = Counter()
    broken_samples: dict[str, Any] = {}
    resource_refs: Counter[str] = Counter()
    resource_samples: dict[str, Any] = {}
    details: list[DetailReport] = []
    status_counts: Counter[str] = Counter()
    category_status: defaultdict[str, Counter[str]] = defaultdict(Counter)
    nav_links = 0
    nav_active = 0
    jsonld_blocks = 0
    missing_dimensions = 0
    bulk_hidden_images = 0
    known_external_images = 0
    new_external_images = 0
    body_map_images = 0
    authoritative_level_pages = 0
    english_distinct_pages = 0
    legacy_raw_canonicals = 0

    for relative in all_html:
        value = read(relative)
        if value is None:
            hard_samples["document_missing"].append(relative)
            continue
        parsed = parse_document(value, relative, audit)
        if parsed is None:
            continue
        source_text, parser = parsed
        route = route_for_relative(relative)
        if CONTROL_RE.search(source_text):
            hard_samples["control_character"].append(relative)
        if len(parser.titles) != 1 or not parser.titles[0]:
            hard_samples["title_count"].append({"path": relative, "values": parser.titles})
        if len(parser.h1s) != 1 or not parser.h1s[0]:
            hard_samples["h1_count"].append({"path": relative, "values": parser.h1s})

        canonical_values = [item.get("href", "") for item in parser.links if "canonical" in item.get("rel", "").lower().split()]
        og_values = [item.get("content", "") for item in parser.metas if item.get("property", "").lower() == "og:url"]
        expected_canonical = DOMAIN + route
        strict_canonical = relative in new_html or relative == PARENT_REL
        canonical_ok = len(canonical_values) == 1 and canonical_values[0] == expected_canonical
        if not canonical_ok and not strict_canonical and len(canonical_values) == 1:
            # Twenty-eight immutable baseline documents use raw Korean URL
            # characters.  Permit only their exact baseline value and semantic
            # route; all 1,860 new documents retain the encoded-byte hard gate.
            baseline_value = git_blob(root, relative)
            baseline_parsed = parse_document(baseline_value, relative + "@baseline", audit)
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
            if canonical_ok:
                legacy_raw_canonicals += 1
        if not canonical_ok:
            hard_samples["canonical"].append({"path": relative, "expected": expected_canonical, "actual": canonical_values})
        else:
            canonicals.append(expected_canonical)
        if len(og_values) != 1 or og_values != canonical_values:
            hard_samples["og_url"].append({"path": relative, "canonical": canonical_values, "og": og_values})
        robots = [
            item.get("content", "") for item in parser.metas
            if item.get("name", "").lower() in {"robots", "googlebot", "naverbot", "yeti"}
        ]
        if any("noindex" in item.lower() for item in robots):
            hard_samples["noindex"].append(relative)

        fragment = nav_fragment(source_text)
        entries = nav_entries(fragment, route) if fragment else []
        if fragment is None:
            hard_samples["nav_missing"].append(relative)
        if len(entries) != 9 or tuple(item["route"] for item in entries[1:]) != EXPECTED_NAV_TARGETS:
            hard_samples["nav_contract"].append({"path": relative, "entries": entries})
        grade = [item for item in entries if item["text"] == "학년별학원"]
        nav_links += len(grade)
        active = len(grade) == 1 and "active" in grade[0]["class"].split()
        nav_active += int(active)
        should_active = relative == PARENT_REL or relative.startswith("학년별학원/")
        if len(grade) != 1 or grade[0]["route"] != PARENT_ROUTE or active != should_active:
            hard_samples["grade_nav"].append({"path": relative, "grade": grade, "expected_active": should_active})

        nodes: list[Mapping[str, Any]] = []
        for block in parser.ld_scripts:
            jsonld_blocks += 1
            try:
                payload = json.loads(block)
                if isinstance(payload, Mapping):
                    graph_value = payload.get("@graph")
                    if isinstance(graph_value, list):
                        nodes.extend(item for item in graph_value if isinstance(item, Mapping))
                    else:
                        nodes.append(payload)
            except Exception as exc:
                hard_samples["jsonld_syntax"].append({"path": relative, "error": str(exc)})

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
                    bulk_hidden_images += 1
                if attrs.get("src") == KNOWN_EXTERNAL_IMAGE:
                    known_external_images += 1
                image_host = urlsplit(urljoin(DOMAIN + route, attrs.get("src", ""))).netloc.lower()
                if relative in new_html and image_host not in HOSTS:
                    new_external_images += 1
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
                resource_refs[resource] += 1
                resource_samples.setdefault(resource, {"page": relative, "tag": tag, "value": raw})

        if relative == PARENT_REL:
            mains = data_nodes(parser, "data-grade-directory", "parent")
            if len(mains) != 1:
                hard_samples["parent_main_hook"].append(len(mains))
            cards = [attrs for attrs in parser.anchors if "subject-category-card" in attrs.get("class", "").split()]
            card_routes = [normalize_route(attrs.get("href", ""), base_route=route) for attrs in cards]
            expected_card_routes = [
                *[item.category_route for item in CATEGORIES[:4]],
                PARENT_ROUTE + quote("중3수학학원", safe="") + "/",
                CATEGORIES[4].category_route,
            ]
            if card_routes != expected_card_routes:
                hard_samples["parent_category_cards"].append(card_routes)
            faq_count, visible = visible_faq(source_text)
            if faq_count != 1 or len(visible) != 2 or visible != schema_faq(nodes):
                hard_samples["parent_faq_parity"].append({"faq_count": faq_count, "visible": visible, "schema": schema_faq(nodes)})
            parent_types = ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage")
            parent_counts = Counter(kind for kind in parent_types for node in nodes if type_has(node, kind))
            if any(parent_counts[kind] != 1 for kind in parent_types):
                hard_samples["parent_schema_cardinality"].append(parent_counts)
            collections = [node for node in nodes if type_has(node, "CollectionPage")]
            item_lists = [node for node in nodes if type_has(node, "ItemList")]
            if len(collections) == 1:
                about = collections[0].get("about")
                has_part = collections[0].get("hasPart")
                if not isinstance(about, list) or len(about) < 2 or not isinstance(has_part, list) or len(has_part) != 6:
                    hard_samples["parent_schema_semantics"].append({"about": about, "hasPart": has_part})
            if len(item_lists) == 1:
                elements = item_lists[0].get("itemListElement")
                if item_lists[0].get("numberOfItems") != 6 or not isinstance(elements, list) or len(elements) != 6:
                    hard_samples["parent_itemlist"].append(item_lists[0])

        category_hub = next((item for item in CATEGORIES if relative == item.category_rel), None)
        if category_hub is not None:
            if len(data_nodes(parser, "data-grade-directory", category_hub.hook)) != 1:
                hard_samples["hub_main_hook"].append(relative)
            for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
                if len(data_nodes(parser, hook)) != 1:
                    hard_samples["hub_search_hook"].append({"path": relative, "hook": hook})
            cards = data_nodes(parser, "data-grade-locality")
            names = [attrs.get("data-grade-locality", "") for _, attrs in cards]
            if (
                len(cards) != DETAILS_PER_CATEGORY or len(set(names)) != DETAILS_PER_CATEGORY
                or set(names) != source.locality_set or names != list(grade_authority.english)
            ):
                hard_samples["hub_card_contract"].append({
                    "path": relative, "total": len(cards), "unique": len(set(names)),
                    "ordered": names == list(grade_authority.english),
                })
            expected_routes = {
                category_hub.category_route + quote(locality, safe="") + "/"
                for locality in source.locality_set
            }
            counts = Counter(normalize_route(item.get("href", ""), base_route=route) for item in parser.anchors)
            bad = [target for target in expected_routes if counts[target] != 1]
            if bad:
                hard_samples["hub_detail_links"].append({"path": relative, "bad": bad[:20]})
            faq_count, visible = visible_faq(source_text)
            if faq_count != 1 or len(visible) != 2 or visible != schema_faq(nodes):
                hard_samples["hub_faq_parity"].append({"path": relative, "visible": visible, "schema": schema_faq(nodes)})
            hub_types = ("EducationalOrganization", "CollectionPage", "BreadcrumbList", "ItemList", "FAQPage")
            hub_counts = Counter(kind for kind in hub_types for node in nodes if type_has(node, kind))
            if any(hub_counts[kind] != 1 for kind in hub_types):
                hard_samples["hub_schema_cardinality"].append({"path": relative, "actual": hub_counts})
            collections = [node for node in nodes if type_has(node, "CollectionPage")]
            item_lists = [node for node in nodes if type_has(node, "ItemList")]
            if len(collections) == 1:
                about = collections[0].get("about")
                has_part = collections[0].get("hasPart")
                if not isinstance(about, list) or len(about) < 2 or not isinstance(has_part, list) or len(has_part) != 1:
                    hard_samples["hub_schema_semantics"].append({"path": relative, "about": about, "hasPart": has_part})
            if len(item_lists) == 1:
                elements = item_lists[0].get("itemListElement")
                if item_lists[0].get("numberOfItems") != DETAILS_PER_CATEGORY or not isinstance(elements, list) or len(elements) != DETAILS_PER_CATEGORY:
                    hard_samples["hub_itemlist"].append({"path": relative, "number": item_lists[0].get("numberOfItems"), "elements": len(elements) if isinstance(elements, list) else None})

        identity = detail_identity(relative)
        if identity is None:
            continue
        category, locality = identity
        mains = [attrs for tag, attrs in parser.starts if tag == "main" and attrs.get("data-grade-page") == category.hook]
        status = mains[0].get("data-source-status", "") if len(mains) == 1 else ""
        if len(mains) != 1 or status not in {"supported", "unconfirmed-grade"}:
            hard_samples["detail_main_hook"].append({"path": relative, "mains": mains})
        status_counts[status] += 1
        category_status[category.key][status] += 1

        source_fields = Counter(attrs.get("data-source-field", "") for _, attrs in data_nodes(parser, "data-source-field"))
        expected_fields = Counter({"grade": 1, "middle-schools": 1, "address": 1, "registration": 1, "fee": 1})
        if source_fields != expected_fields:
            hard_samples["detail_source_fields"].append({"path": relative, "actual": source_fields})
        school_nodes = [attrs for _, attrs in data_nodes(parser, "data-source-field", "middle-schools")]
        school_missing = len(school_nodes) == 1 and school_nodes[0].get("data-source-status") == "missing"
        if len(school_nodes) != 1 or school_nodes[0].get("data-source-status") not in {"provided", "missing"}:
            hard_samples["detail_school_source"].append({"path": relative, "nodes": school_nodes})
        manuscript_sections = data_nodes(parser, "data-manuscript-section")
        if len(data_nodes(parser, "data-manuscript")) != 1 or not manuscript_sections:
            hard_samples["detail_manuscript"].append(relative)
        if len(data_nodes(parser, "data-faq")) != 1 or len(data_nodes(parser, "data-review")) != 1:
            hard_samples["detail_faq_review"].append(relative)
        article_match = re.search(r"<article\b(?=[^>]*\bdata-manuscript(?:\s*=|\s|>))[^>]*>.*?</article\s*>", source_text, re.I | re.S)
        if article_match is None or DANGEROUS_RE.search(article_match.group(0)):
            hard_samples["detail_manuscript_safety"].append(relative)

        image_roles = [attrs.get("data-image-role", "") for attrs in parser.images]
        role_images = {role: [attrs for attrs in parser.images if attrs.get("data-image-role") == role] for role in ("body", "map")}
        if len(parser.images) != 2 or image_roles != ["body", "map"]:
            hard_samples["detail_image_dom"].append({"path": relative, "roles": image_roles})
        body_map_images += sum(len(value) for value in role_images.values())
        for role, values in role_images.items():
            if len(values) != 1:
                continue
            attrs = values[0]
            valid_size = all(attrs.get(key, "").isdigit() and int(attrs[key]) > 0 for key in ("width", "height"))
            expected_loading = "eager" if role == "body" else "lazy"
            if not valid_size or attrs.get("loading") != expected_loading or attrs.get("decoding") != "async" or not attrs.get("alt", "").strip():
                hard_samples["detail_image_attributes"].append({"path": relative, "role": role, "attrs": attrs})
            if role == "body" and attrs.get("fetchpriority") != "high":
                hard_samples["detail_body_priority"].append(relative)

        og_images = [item.get("content", "") for item in parser.metas if item.get("property", "").lower() == "og:image"]
        twitter_images = [item.get("content", "") for item in parser.metas if item.get("name", item.get("property", "")).lower() == "twitter:image"]
        articles = [node for node in nodes if type_has(node, "Article")]
        image_objects = [node for node in nodes if type_has(node, "ImageObject")]
        checked_types = ("WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject", "Service", "Offer")
        schema_counts = Counter(
            kind for kind in checked_types for node in nodes if type_has(node, kind)
        )
        schema_types = {kind for kind in checked_types if any(type_has(node, kind) for node in nodes)}
        required_types = {"WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject"}
        if status == "supported":
            required_types |= {"Service", "Offer"}
        if schema_types != required_types:
            hard_samples["detail_schema_types"].append({"path": relative, "actual": sorted(schema_types)})
        if any(schema_counts[kind] != (1 if kind in required_types else 0) for kind in checked_types):
            hard_samples["detail_schema_cardinality"].append({"path": relative, "actual": schema_counts})

        organizations = [node for node in nodes if type_has(node, "EducationalOrganization")]
        expected_levels = grade_authority.for_page(category, locality)
        actual_levels: tuple[str, ...] | None = None
        if len(organizations) == 1 and isinstance(organizations[0].get("educationalLevel"), list):
            raw_levels = organizations[0]["educationalLevel"]
            if all(isinstance(item, str) and item for item in raw_levels):
                actual_levels = tuple(raw_levels)
        if expected_levels is None or actual_levels != expected_levels:
            hard_samples["detail_authoritative_educational_level"].append({
                "path": relative, "subject": category.subject,
                "expected": expected_levels, "actual": actual_levels,
            })
        else:
            authoritative_level_pages += 1
        expected_status = "supported" if expected_levels is not None and category.grade in expected_levels else "unconfirmed-grade"
        if status != expected_status:
            hard_samples["detail_authoritative_status"].append({
                "path": relative, "expected": expected_status, "actual": status,
            })
        if category.subject == "영어":
            math_levels = grade_authority.math.get(locality)
            if expected_levels != math_levels:
                english_distinct_pages += 1
                if actual_levels == math_levels:
                    hard_samples["detail_english_math_grade_leak"].append({
                        "path": relative, "english": expected_levels, "math": math_levels,
                    })
        web_pages = [node for node in nodes if type_has(node, "WebPage")]
        local_businesses = [node for node in nodes if type_has(node, "LocalBusiness")]
        breadcrumbs = [node for node in nodes if type_has(node, "BreadcrumbList")]
        item_lists = [node for node in nodes if type_has(node, "ItemList")]
        if len(web_pages) == 1 and len(articles) == 1:
            page_about = web_pages[0].get("about")
            page_mentions = web_pages[0].get("mentions")
            page_parts = web_pages[0].get("hasPart")
            article_about = articles[0].get("about")
            article_mentions = articles[0].get("mentions")
            article_parts = articles[0].get("hasPart")
            article_sections = articles[0].get("articleSection")
            semantic_ok = (
                isinstance(page_about, list) and len(page_about) >= 2
                and isinstance(page_mentions, list) and len(page_mentions) >= 6
                and isinstance(page_parts, list) and len(page_parts) == len(manuscript_sections) + 3
                and isinstance(article_about, list) and len(article_about) >= 2
                and isinstance(article_mentions, list) and article_mentions == page_mentions
                and isinstance(article_parts, list) and len(article_parts) == len(manuscript_sections)
                and isinstance(article_sections, list) and len(article_sections) == len(manuscript_sections)
                and all(isinstance(item, str) and item and item in parser.h2s for item in article_sections)
            )
            if not semantic_ok:
                hard_samples["detail_about_mentions_haspart_article_section"].append({
                    "path": relative, "page_about": page_about,
                    "page_mentions": len(page_mentions) if isinstance(page_mentions, list) else None,
                    "page_hasPart": len(page_parts) if isinstance(page_parts, list) else None,
                    "article_about": article_about,
                    "article_mentions": len(article_mentions) if isinstance(article_mentions, list) else None,
                    "article_hasPart": len(article_parts) if isinstance(article_parts, list) else None,
                    "articleSection": article_sections,
                    "visible_sections": len(manuscript_sections),
                })
        if len(breadcrumbs) == 1:
            elements = breadcrumbs[0].get("itemListElement")
            positions = [item.get("position") for item in elements if isinstance(item, Mapping)] if isinstance(elements, list) else []
            last_item = elements[-1].get("item") if isinstance(elements, list) and elements and isinstance(elements[-1], Mapping) else None
            if not isinstance(elements, list) or len(elements) != 4 or positions != [1, 2, 3, 4] or last_item != expected_canonical:
                hard_samples["detail_breadcrumb_schema"].append({"path": relative, "positions": positions, "last": last_item})
        if len(item_lists) == 1:
            elements = item_lists[0].get("itemListElement")
            if item_lists[0].get("numberOfItems") != 7 or not isinstance(elements, list) or len(elements) != 7:
                hard_samples["detail_itemlist_schema"].append({
                    "path": relative, "number": item_lists[0].get("numberOfItems"),
                    "elements": len(elements) if isinstance(elements, list) else None,
                })
        if len(organizations) == 1 and len(local_businesses) == 1:
            organization_offer = organizations[0].get("makesOffer")
            local_offer = local_businesses[0].get("makesOffer")
            services = [node for node in nodes if type_has(node, "Service")]
            offers = [node for node in nodes if type_has(node, "Offer")]
            if status == "supported":
                offer_id = offers[0].get("@id") if len(offers) == 1 else None
                service_id = services[0].get("@id") if len(services) == 1 else None
                expected_offer_ref = [{"@id": offer_id}] if offer_id else None
                service_offer = services[0].get("offers") if len(services) == 1 else None
                offer_service = offers[0].get("itemOffered") if len(offers) == 1 else None
                if (
                    organization_offer != expected_offer_ref or local_offer != expected_offer_ref
                    or service_offer != ({"@id": offer_id} if offer_id else None)
                    or offer_service != ({"@id": service_id} if service_id else None)
                ):
                    hard_samples["detail_makesoffer_schema"].append({
                        "path": relative, "organization": organization_offer,
                        "local_business": local_offer, "service_offer": service_offer,
                        "offer_service": offer_service,
                    })
            elif "makesOffer" in organizations[0] or "makesOffer" in local_businesses[0]:
                hard_samples["detail_unconfirmed_makesoffer"].append(relative)
        if len(og_images) != 1 or twitter_images != og_images or len(articles) != 1 or len(image_objects) != 1:
            hard_samples["detail_representative_cardinality"].append(relative)
        elif articles[0].get("image") != og_images[0] or image_objects[0].get("url") != og_images[0] or image_objects[0].get("contentUrl") != og_images[0]:
            hard_samples["detail_representative_parity"].append(relative)
        if og_images:
            image_url = urlsplit(og_images[0])
            image_relative = unquote(image_url.path).lstrip("/")
            dom_paths = {unquote(urlsplit(urljoin(DOMAIN + route, attrs.get("src", ""))).path).lstrip("/") for attrs in parser.images}
            if image_url.scheme != "https" or image_url.netloc.lower() not in HOSTS or image_relative not in filesystem_files or image_relative in dom_paths:
                hard_samples["detail_representative_local_hidden"].append({"path": relative, "url": og_images[0]})
        faq_count, visible = visible_faq(source_text)
        if faq_count != 1 or not visible or visible != schema_faq(nodes):
            hard_samples["detail_faq_schema_parity"].append({"path": relative, "visible": visible, "schema": schema_faq(nodes)})
        if len(parser.titles) == 1 and not all(value in parser.titles[0] for value in (locality, category.grade, category.subject + "학원")):
            hard_samples["detail_title_structure"].append({"path": relative, "title": parser.titles[0]})
        if len(parser.h1s) == 1 and not all(value in parser.h1s[0] for value in (locality, category.grade, category.subject + "학원")):
            hard_samples["detail_h1_structure"].append({"path": relative, "h1": parser.h1s[0]})
        details.append(DetailReport(relative, route, category, locality, status, school_missing))

    for code, values in hard_samples.items():
        audit.extend(code, values)
    audit.hard(len(canonicals) == FINAL_HTML_COUNT and len(set(canonicals)) == FINAL_HTML_COUNT, "canonical_cardinality", {"total": len(canonicals), "unique": len(set(canonicals))})
    audit.hard(legacy_raw_canonicals == 28, "legacy_raw_canonical_baseline", legacy_raw_canonicals)
    audit.hard(nav_links == FINAL_HTML_COUNT, "grade_nav_link_total", nav_links)
    audit.hard(nav_active == GRADE_ACTIVE_COUNT, "grade_nav_active_total", nav_active)
    audit.hard(len(details) == NEW_DETAIL_COUNT, "detail_count", len(details))
    audit.hard(status_counts == Counter({"supported": 1_805, "unconfirmed-grade": 50}), "detail_status_total", status_counts)
    for category in CATEGORIES:
        audit.hard(category_status[category.key] == Counter({"supported": category.supported, "unconfirmed-grade": category.unconfirmed}), "detail_category_status", {"category": category.key, "actual": category_status[category.key]})
    audit.hard(body_map_images == NEW_DETAIL_COUNT * 2, "detail_body_map_total", body_map_images)
    audit.hard(authoritative_level_pages == NEW_DETAIL_COUNT, "detail_authoritative_level_total", authoritative_level_pages)
    audit.hard(english_distinct_pages > 0, "detail_english_distinct_level_coverage", english_distinct_pages)

    missing_resources = [
        {"resource": resource, "count": count, "sample": resource_samples[resource]}
        for resource, count in resource_refs.items()
        if resource not in projection.documents and resource not in filesystem_files
    ]
    audit.extend("missing_local_resource", missing_resources)
    audit.hard(not missing_resources, "missing_local_resource_total", len(missing_resources))
    expected_broken = Counter({KNOWN_BROKEN_ROUTE: KNOWN_BROKEN_OCCURRENCES})
    audit.hard(broken == expected_broken, "internal_link_regression", {"expected": expected_broken, "actual": broken, "samples": broken_samples})
    audit.hard(bulk_hidden_images == KNOWN_BULK_HIDDEN_IMAGES, "baseline_bulk_hidden_images", bulk_hidden_images)
    audit.hard(missing_dimensions == KNOWN_MISSING_DIMENSION_IMAGES, "baseline_missing_dimensions", missing_dimensions)
    audit.hard(known_external_images == KNOWN_EXTERNAL_IMAGE_OCCURRENCES, "baseline_known_external_404", known_external_images)
    audit.hard(new_external_images == 0, "new_external_images", new_external_images)

    distances: dict[str, int] = {"/": 0}
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
    for category in CATEGORIES:
        audit.hard(distances.get(category.category_route) == 2, "category_link_depth", {"category": category.key, "depth": distances.get(category.category_route)})
    detail_routes = {item.route for item in details}
    bad_depths = [(route, distances.get(route)) for route in detail_routes if distances.get(route) != 3]
    audit.extend("detail_link_depth", bad_depths)
    audit.observations["documents"] = {
        "html": len(all_html), "canonical": len(canonicals), "canonical_unique": len(set(canonicals)),
        "nav_links": nav_links, "nav_active": nav_active, "jsonld_blocks": jsonld_blocks,
        "details": len(details), "status": status_counts, "body_map_images": body_map_images,
        "authoritative_level_pages": authoritative_level_pages,
        "english_distinct_level_pages": english_distinct_pages,
        "legacy_raw_canonicals": legacy_raw_canonicals,
    }
    audit.observations["links"] = {
        "edges": sum(len(value) for value in graph.values()), "broken": broken,
        "reachable": len(distances), "orphans": len(orphans), "max_depth": max(distances.values(), default=0),
    }
    audit.observations["resources"] = {
        "references": sum(resource_refs.values()), "unique": len(resource_refs), "missing": len(missing_resources),
        "legacy_bulk_hidden": bulk_hidden_images, "legacy_missing_dimensions": missing_dimensions,
        "known_external_404": known_external_images, "new_external": new_external_images,
    }
    return details


def validate_preservation(
    root: Path,
    projection: Projection,
    all_html: Sequence[str],
    new_html: set[str],
    audit: Audit,
) -> None:
    head = run_git(root, ["rev-parse", BASELINE_COMMIT]).decode().strip()
    tree = run_git(root, ["rev-parse", f"{BASELINE_COMMIT}^{{tree}}"]).decode().strip()
    audit.hard(head == BASELINE_COMMIT, "baseline_commit", head)
    audit.hard(tree == BASELINE_TREE, "baseline_tree", {"expected": BASELINE_TREE, "actual": tree})
    baseline_html = baseline_paths(root, "index.html")
    audit.hard(len(baseline_html) == BASELINE_HTML_COUNT, "baseline_html_count", len(baseline_html))
    audit.hard(len(new_html) == NEW_HTML_COUNT and not (set(baseline_html) & new_html), "new_html_disjoint", {
        "new": len(new_html), "collisions": sorted(set(baseline_html) & new_html)[:30]
    })
    audit.hard(set(all_html) == set(baseline_html) | new_html, "final_html_scope")
    authorized_existing_html = set(projection.documents) & set(baseline_html)
    audit.hard(authorized_existing_html == {PARENT_REL}, "existing_html_authorization", sorted(authorized_existing_html))

    diff = run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"])
    tracked_changed = {item.decode("utf-8") for item in diff.split(b"\0") if item}
    immutable_html = set(baseline_html) - {PARENT_REL}
    audit.hard(not (tracked_changed & immutable_html), "immutable_html_git_preservation", sorted(tracked_changed & immutable_html)[:30])
    audit.hard(len(immutable_html) == IMMUTABLE_HTML_COUNT, "immutable_html_count", len(immutable_html))
    middle3 = {path for path in baseline_html if path.startswith("학년별학원/중3수학학원/")}
    audit.hard(len(middle3) == EXISTING_MIDDLE3_MATH_HTML_COUNT, "middle3_math_count", len(middle3))
    audit.hard(not (tracked_changed & middle3), "middle3_math_git_preservation", sorted(tracked_changed & middle3)[:30])
    protected = {"index.html", HEADER_CSS_REL, ROBOTS_REL, VERCEL_REL, BASE_GENERATOR_REL, BASE_CONTENT_AUDITOR_REL, BASE_TECHNICAL_AUDITOR_REL}
    audit.hard(not (tracked_changed & protected), "protected_file_preservation", sorted(tracked_changed & protected))
    protected_pins = {
        "index.html": BASE_ROOT_HTML_SHA256,
        HEADER_CSS_REL: BASE_HEADER_CSS_SHA256,
        ROBOTS_REL: BASE_ROBOTS_SHA256,
        VERCEL_REL: BASE_VERCEL_SHA256,
        BASE_GENERATOR_REL: BASE_GENERATOR_SHA256,
        BASE_CONTENT_AUDITOR_REL: BASE_CONTENT_AUDITOR_SHA256,
        BASE_TECHNICAL_AUDITOR_REL: BASE_TECHNICAL_AUDITOR_SHA256,
    }
    protected_errors: list[Any] = []
    for relative, expected_digest in protected_pins.items():
        baseline_value = git_blob(root, relative)
        current_value = fs_bytes(root, relative)
        baseline_digest = sha256(baseline_value)
        current_digest = "MISSING"
        if current_value is not None:
            try:
                current_digest = sha256(normalized_text(current_value.decode("utf-8")).encode("utf-8"))
            except UnicodeDecodeError:
                current_digest = sha256(current_value)
        if baseline_digest != expected_digest or current_digest != expected_digest:
            protected_errors.append({
                "path": relative, "expected": expected_digest,
                "baseline": baseline_digest, "current": current_digest,
            })
    audit.extend("protected_file_sha256", protected_errors)

    declared_immutable = str(plan_value_from_projection_field(root, "immutable_html_manifest_sha256") or "").lower()
    declared_middle3 = str(plan_value_from_projection_field(root, "middle3_math_manifest_sha256") or "").lower()
    # The generator exposes these values on its BuildPlan.  run_projection
    # validates them directly and stores the observations; this fallback is
    # retained only for an older duck-typed plan and therefore yields HOLD.
    if not declared_immutable:
        audit.hold(False, "immutable_manifest_projection_field_pending")
    if not declared_middle3:
        audit.hold(False, "middle3_manifest_projection_field_pending")

    current_parent = projection.documents.get(PARENT_REL, fs_bytes(root, PARENT_REL) or b"")
    try:
        current_fragment = nav_fragment(current_parent.decode("utf-8"))
        baseline_fragment = nav_fragment(git_blob(root, PARENT_REL).decode("utf-8"))
        audit.hard(
            current_fragment is not None and baseline_fragment is not None
            and normalized_text(current_fragment) == normalized_text(baseline_fragment),
            "parent_nav_preservation",
        )
    except Exception as exc:
        audit.hard(False, "parent_nav_preservation_exception", str(exc))
    audit.observations["preservation"] = {
        "baseline_html": len(baseline_html), "immutable_html": len(immutable_html),
        "middle3_math": len(middle3), "tracked_changed": len(tracked_changed),
        "existing_html_authorized": sorted(authorized_existing_html),
        "protected_files": len(protected_pins),
    }


# Populated by run_projection without retaining the full plan object.
_PROJECTION_FIELDS: dict[str, Any] = {}


def plan_value_from_projection_field(root: Path, name: str) -> Any:
    del root
    return _PROJECTION_FIELDS.get(name)


def validate_pins(
    root: Path,
    projection: Projection,
    generator: Path,
    content_auditor: Path,
    audit: Audit,
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
            audit.hard(canonical_digest == digest, "pin_digest_parity", relative)
            actual[relative] = canonical_digest
        if approved == "PENDING":
            pending.append(relative)
        else:
            audit.hard(digest == approved, "pin_sha256", {"path": relative, "expected": approved, "actual": digest})
    if APPROVED_PLAN_CANDIDATE_SHA256 == "PENDING":
        pending.append("candidate_sha256")
    else:
        audit.hard(projection.candidate_sha256 == APPROVED_PLAN_CANDIDATE_SHA256, "pin_candidate", projection.candidate_sha256)
    if APPROVED_PROJECTED_MANIFEST == "PENDING":
        pending.append("projected_manifest")
    else:
        audit.hard(projection.projected_manifest == APPROVED_PROJECTED_MANIFEST, "pin_projected_manifest", projection.projected_manifest)
    audit.hold(not pending, "freeze_pins_pending", pending)
    audit.observations["pins"] = {
        "actual": actual, "candidate_sha256": projection.candidate_sha256,
        "projected_manifest": projection.projected_manifest, "pending": pending,
    }


def validate_git_scope(root: Path, expected_plan: set[str], audit: Audit) -> None:
    expected = expected_plan | {GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL}
    tracked_raw = run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"])
    changed = {item.decode("utf-8") for item in tracked_raw.split(b"\0") if item}
    untracked_raw = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    changed |= {item.decode("utf-8") for item in untracked_raw.split(b"\0") if item}
    audit.hard(changed == expected, "git_exact_change_scope", {
        "expected_count": len(expected), "actual_count": len(changed),
        "missing": sorted(expected - changed)[:30], "extra": sorted(changed - expected)[:30],
    })
    audit.hard(len(changed) == RELEASE_CHANGE_COUNT, "git_change_count", len(changed))
    deleted_raw = run_git(root, ["diff", "--name-only", "--diff-filter=D", "-z", BASELINE_COMMIT, "--"])
    deleted = [item.decode("utf-8") for item in deleted_raw.split(b"\0") if item]
    audit.hard(not deleted, "git_no_deletions", deleted[:30])
    diff_check = subprocess.run(
        ["git", "diff", "--check", BASELINE_COMMIT, "--"], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    audit.hard(diff_check.returncode == 0, "git_diff_check", (diff_check.stdout + diff_check.stderr).decode("utf-8", "replace")[-3000:])
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"], cwd=root, check=False)
    audit.hard(ancestor.returncode == 0, "baseline_is_ancestor")
    worktree_status = run_git(root, ["status", "--porcelain=v1", "-z"])
    audit.hard(not worktree_status, "git_release_commit_required")
    head = run_git(root, ["rev-parse", "HEAD"]).decode().strip()
    audit.hard(head != BASELINE_COMMIT, "git_release_head_advanced", head)
    origin_main = run_git(root, ["rev-parse", "--verify", "refs/remotes/origin/main"], check=False).decode().strip()
    audit.hard(bool(origin_main) and origin_main == head, "git_origin_main_release_parity", {
        "head": head, "origin_main": origin_main or "MISSING",
    })

    security: list[Any] = []
    for relative in sorted(changed):
        path = root / PurePosixPath(relative)
        if path.is_symlink():
            security.append({"path": relative, "reason": "symlink"})
            continue
        if not path.is_file():
            security.append({"path": relative, "reason": "missing-or-nonfile"})
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

    allowed_cache_dirs = {str(PurePosixPath(relative).parent) for relative in ALLOWED_BASELINE_RESIDUE}
    allowed_residue_errors: list[Any] = []
    for relative, expected_digest in ALLOWED_BASELINE_RESIDUE.items():
        path = root / PurePosixPath(relative)
        current_digest = sha256(path.read_bytes()) if path.is_file() else "MISSING"
        try:
            baseline_digest = sha256(git_blob(root, relative))
        except Exception as exc:
            baseline_digest = f"ERROR:{exc}"
        if current_digest != expected_digest or baseline_digest != expected_digest:
            allowed_residue_errors.append({
                "path": relative, "expected": expected_digest,
                "baseline": baseline_digest, "current": current_digest,
            })
    for directory in allowed_cache_dirs:
        path = root / PurePosixPath(directory)
        actual = {
            item.relative_to(root).as_posix() for item in path.rglob("*") if item.is_file()
        } if path.is_dir() else set()
        expected_allowed = {
            relative for relative in ALLOWED_BASELINE_RESIDUE
            if str(PurePosixPath(relative).parent) == directory
        }
        if actual != expected_allowed:
            allowed_residue_errors.append({
                "directory": directory, "expected": sorted(expected_allowed), "actual": sorted(actual),
            })
    audit.extend("baseline_tracked_residue_drift", allowed_residue_errors)

    residue: list[str] = []
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if ".git" in relative.parts or ".vercel" in relative.parts or "node_modules" in relative.parts:
            continue
        name = path.name.lower()
        if path.is_dir() and (name == "__pycache__" or name.startswith(TRANSACTION_PREFIXES)):
            if relative.as_posix() not in allowed_cache_dirs:
                residue.append(relative.as_posix() + "/")
        elif path.is_file() and (name.endswith(RESIDUE_SUFFIXES) or re.search(r"middle.grade.*lock", name)):
            if relative.as_posix() not in ALLOWED_BASELINE_RESIDUE:
                residue.append(relative.as_posix())
    audit.hard(not residue, "release_residue", sorted(residue)[:50])
    tracked = [item for item in run_git(root, ["ls-files", "-z"]).split(b"\0") if item]
    audit.hard(len(tracked) in {BASELINE_TRACKED_COUNT, FINAL_TRACKED_COUNT}, "tracked_file_count_phase", len(tracked))
    audit.observations["git_scope"] = {
        "expected": len(expected), "actual": len(changed), "tracked": len(tracked),
        "security_errors": len(security), "residue": sorted(residue),
        "allowed_baseline_residue": sorted(ALLOWED_BASELINE_RESIDUE),
        "head": head, "origin_main": origin_main or "MISSING", "worktree_clean": not worktree_status,
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
    audit.hard(len(cases) == BROWSER_ROUTE_COUNT, "browser_route_count", cases)
    audit.hard(len({item["route"] for item in cases}) == BROWSER_ROUTE_COUNT, "browser_route_unique")
    audit.observations["browser_cases"] = cases
    return cases


def find_node() -> str | None:
    direct = shutil.which("node")
    if direct:
        return direct
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    values = [path for path in local.glob("Microsoft/WinGet/Packages/OpenJS.NodeJS*/node-*-win-x64/node.exe") if path.is_file()]
    return str(max(values, key=lambda path: path.stat().st_mtime_ns)) if values else None


def find_playwright_node_path() -> str | None:
    candidates: list[Path] = []
    configured = os.environ.get("NODE_PATH")
    if configured:
        candidates.extend(Path(value) for value in configured.split(os.pathsep) if (Path(value) / "playwright" / "package.json").is_file())
    npx = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    if npx.is_dir():
        candidates.extend(path.parent.parent for path in npx.glob("*/node_modules/playwright/package.json"))
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        result = subprocess.run([npm, "root", "-g"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode == 0:
            path = Path(result.stdout.decode("utf-8", "replace").strip())
            if (path / "playwright" / "package.json").is_file():
                candidates.append(path)
    if not candidates:
        return None

    def version(path: Path) -> tuple[int, ...]:
        try:
            value = json.loads((path / "playwright" / "package.json").read_text("utf-8"))
            return tuple(int(item) for item in re.findall(r"\d+", str(value.get("version", "0")))[:3])
        except Exception:
            return (0,)

    return str(max(set(candidates), key=version))


def run_browser(
    base: str,
    cases: Sequence[Mapping[str, str]],
    timeout: int,
    *,
    bypass_secret: str | None = None,
) -> dict[str, Any]:
    node = find_node()
    node_path = find_playwright_node_path()
    if node is None or node_path is None:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": "node or playwright not found"}
    headers: dict[str, str] = {}
    if bypass_secret:
        headers = {
            "x-vercel-protection-bypass": bypass_secret,
            "x-vercel-set-bypass-cookie": "true",
        }
    payload = base64.b64encode(json.dumps({
        "base": base.rstrip("/"), "domain": DOMAIN, "cases": list(cases),
        "widths": BROWSER_WIDTHS, "headers": headers,
    }, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = r'''
const {chromium}=require('playwright');
const cfg=JSON.parse(Buffer.from(process.argv[1],'base64').toString('utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true}); const rows=[]; let hubTests=0;
 for(const item of cfg.cases){ for(const width of cfg.widths){
  const context=await browser.newContext({viewport:{width,height:900},locale:'ko-KR',extraHTTPHeaders:cfg.headers});
  const page=await context.newPage(); const consoleErrors=[],pageErrors=[],network=[];
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
  page.on('pageerror',e=>pageErrors.push(String(e)));
  page.on('requestfailed',r=>network.push('FAIL '+r.url()+' '+(r.failure()?.errorText||'')));
  page.on('response',r=>{if(r.status()>=400)network.push(r.status()+' '+r.url())});
  let responseStatus=0,navigationError='';
  try{const response=await page.goto(cfg.base+item.route,{waitUntil:'networkidle',timeout:45000});responseStatus=response?response.status():0;await page.waitForTimeout(120)}catch(e){navigationError=String(e)}
  if(['supported','unconfirmed'].includes(item.kind)){
   for(const role of ['body','map']){const image=page.locator(`[data-image-role="${role}"]`);if(await image.count()===1){try{await image.scrollIntoViewIfNeeded({timeout:3000});await page.waitForFunction(r=>{const e=document.querySelector(`[data-image-role="${r}"]`);return !!e&&e.complete&&e.naturalWidth>0},role,{timeout:10000})}catch{}}}
  }
  const state=await page.evaluate(({item,domain,width})=>{
   const visible=e=>{if(!e)return false;const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&!e.hidden&&r.width>0&&r.height>0};
   const nav=[...document.querySelectorAll('.site-header .nav-links a')],rects=nav.map(e=>e.getBoundingClientRect());
   const overlaps=[];for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++){const a=rects[i],b=rects[j];if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.5&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.5)overlaps.push([i,j])}
   const rowTops=[...new Set(rects.map(r=>Math.round(r.top)))],rowCounts=rowTops.map(top=>rects.filter(r=>Math.abs(Math.round(r.top)-top)<=1).length);
   const grade=nav.filter(a=>(a.textContent||'').replace(/\s+/g,' ').trim()==='학년별학원');
   const canonical=[...document.querySelectorAll('link[rel~="canonical"]')].map(e=>e.href);
   const robots=[...document.querySelectorAll('meta[name="robots" i],meta[name="googlebot" i],meta[name="naverbot" i],meta[name="yeti" i]')].map(e=>e.content||'');
   const header=document.querySelector('.site-header'),headerRect=header?.getBoundingClientRect(),main=document.querySelector('main');
   const imgs=[...document.images].map(e=>({complete:e.complete,naturalWidth:e.naturalWidth,visible:visible(e),role:e.dataset.imageRole||''}));
   const faq=document.querySelectorAll('[data-faq]'),faqDetails=faq.length===1?[...faq[0].querySelectorAll('details')]:[];
   return {title:document.title,h1:document.querySelectorAll('h1').length,canonical,expectedCanonical:domain+item.route,noindex:robots.some(x=>/noindex/i.test(x)),overflow:document.documentElement.scrollWidth>innerWidth+1,navCount:nav.length,gradeCount:grade.length,gradeActive:grade.length===1&&grade[0].classList.contains('active'),navRows:rowTops.length,rowCounts,overlaps,navBounds:rects.filter(r=>r.left<-1||r.right>innerWidth+1).length,headerHeight:headerRect?.height||0,expectedMobile:width<=1120,mainDirectory:main?.dataset.gradeDirectory||'',mainPage:main?.dataset.gradePage||'',mainStatus:main?.dataset.sourceStatus||'',faqCount:faq.length,faqVisible:faq.length===1&&visible(faq[0]),faqDetails:faqDetails.length,roleImages:imgs.filter(x=>x.role==='body'||x.role==='map')};
  },{item,domain:cfg.domain,width});
  const failures=[];if(responseStatus!==200)failures.push('http');if(navigationError)failures.push('navigation');if(consoleErrors.length)failures.push('console');if(pageErrors.length)failures.push('pageerror');if(network.length)failures.push('network');
  if(state.h1!==1||state.canonical.length!==1||state.canonical[0]!==state.expectedCanonical||state.noindex)failures.push('seo');
  if(state.overflow||state.navCount!==8||state.gradeCount!==1||!state.gradeActive||state.overlaps.length||state.navBounds)failures.push('nav');
  if(state.expectedMobile){if(state.navRows!==2||state.rowCounts.slice().sort().join(',')!=='4,4'||Math.abs(state.headerHeight-132)>2)failures.push('mobile-layout')}else{if(state.navRows!==1||state.rowCounts[0]!==8||Math.abs(state.headerHeight-72)>2)failures.push('desktop-layout')}
  if(item.kind==='parent'&&state.mainDirectory!=='parent')failures.push('parent-hook');
  if(item.kind==='hub'&&state.mainDirectory!==item.hook)failures.push('hub-hook');
  if(['supported','unconfirmed'].includes(item.kind)&&(state.mainPage!==item.hook||state.mainStatus!==item.status))failures.push('detail-hook');
  if(['parent','hub'].includes(item.kind)&&(state.faqCount!==1||!state.faqVisible||state.faqDetails!==2))failures.push('hub-faq');
  if(['supported','unconfirmed'].includes(item.kind)&&(state.roleImages.length!==2||state.roleImages.some(x=>!x.complete||x.naturalWidth<=0||!x.visible)))failures.push('images');
  let hub=null;if(item.kind==='hub'){
   hubTests++;hub=await page.evaluate(async()=>{const input=document.querySelector('[data-grade-search]'),clear=document.querySelector('[data-grade-clear]'),status=document.querySelector('[data-grade-status]'),cards=[...document.querySelectorAll('[data-grade-locality]')],visible=e=>{const s=getComputedStyle(e);return !e.hidden&&s.display!=='none'&&s.visibility!=='hidden'};if(!input||!clear||!status)return {error:'missing-hooks'};const initial={visible:cards.filter(visible).length,status:(status.textContent||'').replace(/\s+/g,' ').trim()};input.focus();input.value='명일동';input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,100));const filtered={visible:cards.filter(visible).length,names:cards.filter(visible).map(e=>e.getAttribute('data-grade-locality'))};clear.click();await new Promise(r=>setTimeout(r,100));return {initial,filtered,reset:{visible:cards.filter(visible).length,status:(status.textContent||'').replace(/\s+/g,' ').trim(),value:input.value,focused:document.activeElement===input}}});
   if(hub.error||hub.initial.visible!==371||hub.filtered.visible!==1||hub.filtered.names[0]!=='명일동'||hub.reset.visible!==371||hub.reset.value!==''||hub.reset.status!==hub.initial.status||!hub.reset.focused)failures.push('hub-search');
  }
  rows.push({kind:item.kind,route:item.route,width,responseStatus,navigationError,consoleErrors,pageErrors,network,state,hub,failures});await context.close();
 }}
 await browser.close();const failed=rows.filter(row=>row.failures.length);console.log(JSON.stringify({tests:rows.length,hub_tests:hubTests,failures:failed.length,failureRows:failed.slice(0,30)}));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    env = dict(os.environ)
    env["NODE_PATH"] = node_path
    try:
        result = subprocess.run(
            [node, "-e", script, payload], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": "browser timeout"}
    if result.returncode:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": result.stderr.decode("utf-8", "replace")[-4000:]}
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except Exception as exc:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": f"invalid browser JSON: {exc}"}


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
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    audit.hard(ancestor.returncode == 0, "repository_baseline_ancestor", ancestor.stderr.decode("utf-8", "replace"))
    remote = run_git(root, ["remote", "get-url", "origin"], check=False).decode("utf-8", "replace").strip()
    audit.hard(
        remote.rstrip("/") in {
            "https://github.com/01039578283-hub/my-homepage.git",
            "git@github.com:01039578283-hub/my-homepage.git",
        },
        "repository_origin", remote,
    )
    disk_html = sum(1 for path in root.rglob("index.html") if not any(part in PRUNED_DIRS for part in path.relative_to(root).parts))
    audit.hard(disk_html in {BASELINE_HTML_COUNT, FINAL_HTML_COUNT}, "repository_disk_html_phase", disk_html)
    branch = run_git(root, ["branch", "--show-current"], check=False).decode("utf-8", "replace").strip()
    autocrlf = run_git(root, ["config", "--get", "core.autocrlf"], check=False).decode("utf-8", "replace").strip()
    audit.observations["repository"] = {
        "root": str(root), "baseline": BASELINE_COMMIT, "tree": tree,
        "baseline_tracked": len(baseline_files), "baseline_html": len(baseline_html),
        "disk_html": disk_html, "branch": branch, "origin": remote,
        "core_autocrlf": autocrlf,
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
    audit.observations["projected_security"] = {
        "documents": len(projection.documents), "errors": len(errors),
    }


def parse_browser_targets(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    allowed = {"local", "preview", "live"}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--browser-target requires NAME=URL: {value}")
        name, base = value.split("=", 1)
        name = name.strip().lower()
        base = base.strip().rstrip("/")
        split = urlsplit(base)
        if name not in allowed or name in result:
            raise ValueError(f"browser target must be one unique value from {sorted(allowed)}: {name}")
        if split.scheme not in {"http", "https"} or not split.netloc or split.path not in {"", "/"} or split.query or split.fragment:
            raise ValueError(f"browser target must be an origin URL: {base}")
        if name in {"preview", "live"} and split.scheme != "https":
            raise ValueError(f"{name} browser target must use HTTPS")
        hostname = (split.hostname or "").lower()
        if name == "local" and hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("local browser target must use a loopback host")
        if name == "preview" and not hostname.endswith(".vercel.app"):
            raise ValueError("preview browser target must use a vercel.app deployment origin")
        if name == "live" and hostname not in HOSTS:
            raise ValueError(f"live browser target must use {DOMAIN}")
        result[name] = base
    return result


def run_browser_matrix(
    targets: Mapping[str, str],
    cases: Sequence[Mapping[str, str]],
    timeout: int,
    bypass_secret: str | None,
    audit: Audit,
) -> None:
    expected_names = {"local", "preview", "live"}
    audit.hard(set(targets) == expected_names, "browser_target_matrix", {
        "expected": sorted(expected_names), "actual": sorted(targets),
    })
    results: dict[str, Any] = {}
    for name in ("local", "preview", "live"):
        base = targets.get(name)
        if not base:
            continue
        if name == "preview":
            audit.hard(bool(bypass_secret), "preview_bypass_secret_missing")
            if not bypass_secret:
                continue
        result = run_browser(
            base, cases, timeout,
            bypass_secret=bypass_secret if name == "preview" else None,
        )
        results[name] = result
        audit.hard(result.get("tests") == BROWSER_TEST_COUNT, "browser_test_count", {
            "target": name, "expected": BROWSER_TEST_COUNT, "actual": result.get("tests"),
        })
        audit.hard(result.get("hub_tests") == BROWSER_HUB_TEST_COUNT, "browser_hub_test_count", {
            "target": name, "expected": BROWSER_HUB_TEST_COUNT, "actual": result.get("hub_tests"),
        })
        audit.hard(result.get("failures") == 0, "browser_failures", {
            "target": name, "result": result,
        })
    audit.observations["browser"] = results


def run_self_test() -> dict[str, Any]:
    audit = Audit()
    audit.hard(route_for_relative("index.html") == "/", "self_route_root")
    audit.hard(
        route_for_relative("학년별학원/중1영어학원/명일동/index.html")
        == "/%ED%95%99%EB%85%84%EB%B3%84%ED%95%99%EC%9B%90/%EC%A4%911%EC%98%81%EC%96%B4%ED%95%99%EC%9B%90/%EB%AA%85%EC%9D%BC%EB%8F%99/",
        "self_route_encoding",
    )
    audit.hard(normalize_route("/index.html") == "/", "self_route_normalize")
    audit.hard(
        normalize_route("https://wawa-center.kr/학년별학원/") == PARENT_ROUTE,
        "self_legacy_unicode_canonical_semantics",
    )
    audit.hard(normalized_text("prefix\r\n") == "prefix\n", "self_crlf_semantics")
    llms_sample = "- 학년별학원: https://wawa-center.kr/학년별학원/\n- 중1 수학학원: https://wawa-center.kr/학년별학원/중1수학학원/\n"
    audit.hard(
        llms_sample.splitlines().count("- 학년별학원: https://wawa-center.kr/학년별학원/") == 1,
        "self_llms_parent_line_not_url_prefix",
    )
    fragment = '<header class="site-header"><a href="/">와와</a><a class="active" href="/학년별학원/">학년별학원</a></header>'
    entries = nav_entries(fragment, PARENT_ROUTE)
    audit.hard(len(entries) == 2 and entries[1]["route"] == PARENT_ROUTE, "self_nav")
    faq_html = '<div data-faq><details><summary><span>Q1.</span> 질문</summary><p><strong>A.</strong> 답변</p></details></div>'
    audit.hard(visible_faq(faq_html) == (1, [("질문", "답변")]), "self_faq", visible_faq(faq_html))
    try:
        normalize_relative(ROOT, "../escape")
    except ValueError:
        pass
    else:
        audit.hard(False, "self_relative_escape")
    audit.hard(
        NEW_CATEGORY_COUNT * (DETAILS_PER_CATEGORY + 1) == NEW_HTML_COUNT
        and BASELINE_HTML_COUNT + NEW_HTML_COUNT == FINAL_HTML_COUNT
        and PLAN_DOCUMENT_COUNT + 3 == RELEASE_CHANGE_COUNT,
        "self_cardinality",
    )
    return {
        "status": "FAIL" if audit.errors else "PASS",
        "errors": audit.errors,
        "holds": audit.holds,
        "observations": {"tests": 10},
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--common-dir", type=Path)
    parser.add_argument(
        "--zip", action="append", default=[], metavar="KEY=PATH",
        help="repeat for all five category keys; defaults to the supplied Desktop folder",
    )
    parser.add_argument("--generator", type=Path)
    parser.add_argument("--content-auditor", type=Path)
    parser.add_argument("--browser-target", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--browser-timeout", type=int, default=1_800)
    parser.add_argument("--preview-bypass-env", default="VERCEL_AUTOMATION_BYPASS_SECRET")
    parser.add_argument("--baseline-only", action="store_true")
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
    common_before: tuple[str, int, int] | None = None
    zip_before: dict[str, str] = {}
    source: SourceSet | None = None
    common_dir: Path | None = None
    try:
        audit.hard(root.is_dir(), "root_missing", str(root))
        if not root.is_dir():
            raise RuntimeError(f"root directory does not exist: {root}")
        status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
        validate_repository(root, audit)
        common_dir = discover_common_dir(root, args.common_dir)
        common_before = directory_snapshot(common_dir)
        audit.hard(common_before == EXPECTED_COMMON_SNAPSHOT, "common_snapshot", {
            "expected": EXPECTED_COMMON_SNAPSHOT, "actual": common_before,
        })
        zip_paths = parse_zip_args(args.zip)
        zip_before = {key: sha256(path.read_bytes()) for key, path in zip_paths.items() if path.is_file()}
        source = inspect_sources(zip_paths, audit)
        authority = load_grade_authority(common_dir, source, audit)
        expected_plan = expected_plan_paths(source)
        audit.hard(len(expected_plan) == PLAN_DOCUMENT_COUNT, "expected_plan_count", len(expected_plan))

        if args.baseline_only:
            audit.hold(False, "baseline_only_release_not_projected")
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
            audit.hard(len(projection.changed) in {0, PLAN_DOCUMENT_COUNT}, "release_phase_change_count", len(projection.changed))
            audit.observations["phase"] = phase
            validate_projected_security(root, projection, audit)

            new_html = expected_new_html(source)
            all_html = sorted(set(baseline_paths(root, "index.html")) | new_html)
            sitemap = projection.documents.get(SITEMAP_REL)
            llms = projection.documents.get(LLMS_REL)
            audit.hard(sitemap is not None, "projected_sitemap_missing")
            audit.hard(llms is not None, "projected_llms_missing")
            if sitemap is not None:
                validate_sitemap(root, sitemap, all_html, new_html, tuple(authority.english), audit)
            if llms is not None:
                validate_llms(root, llms, audit)
            details = audit_documents(root, projection, source, authority, all_html, new_html, audit)
            validate_preservation(root, projection, all_html, new_html, audit)
            validate_pins(root, projection, generator, content_auditor, audit)
            cases = select_browser_cases(details, audit)

            targets = parse_browser_targets(args.browser_target)
            if phase == "actual":
                validate_git_scope(root, expected_plan, audit)
                bypass_secret = os.environ.get(args.preview_bypass_env, "") if args.preview_bypass_env else ""
                run_browser_matrix(targets, cases, args.browser_timeout, bypass_secret or None, audit)
            else:
                audit.hard(not targets, "projected_browser_targets_not_allowed", sorted(targets))
                audit.observations["browser"] = {
                    "status": "not-run-unmaterialized", "required_after_materialization": ["local", "preview", "live"],
                    "routes": BROWSER_ROUTE_COUNT, "widths": list(BROWSER_WIDTHS),
                    "tests_per_target": BROWSER_TEST_COUNT,
                }
    except Exception as exc:
        audit.hard(False, "audit_exception", f"{type(exc).__name__}: {exc}")
    finally:
        if root.is_dir() and status_before:
            try:
                status_after = run_git(root, ["status", "--porcelain=v1", "-z"])
                audit.hard(status_before == status_after, "audit_git_status_read_only")
            except Exception as exc:
                audit.hard(False, "audit_status_recheck", str(exc))
        if common_dir is not None and common_before is not None:
            try:
                audit.hard(common_before == directory_snapshot(common_dir), "audit_common_read_only")
            except Exception as exc:
                audit.hard(False, "audit_common_recheck", str(exc))
        if source is not None:
            try:
                zip_after = {
                    key: sha256(path.read_bytes()) for key, path in source.zip_paths.items() if path.is_file()
                }
                audit.hard(zip_before == zip_after, "audit_zips_read_only")
            except Exception as exc:
                audit.hard(False, "audit_zip_recheck", str(exc))

    status = "FAIL" if audit.errors else "HOLD" if audit.holds else "PASS"
    report = {
        "status": status,
        "errors": audit.errors,
        "holds": audit.holds,
        "observations": audit.observations,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if status == "FAIL" else 2 if status == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
