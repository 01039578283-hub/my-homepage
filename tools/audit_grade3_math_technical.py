from __future__ import annotations

"""Read-only technical and release gate for the grade-directory release.

This auditor never applies a generation plan.  It imports the approved generator,
asks it for an in-memory plan, proves determinism/idempotence, and audits either
that projection or the already materialized tree.  A materialized release cannot
pass without the browser matrix.
"""

import argparse
import base64
import gc
import hashlib
import html
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
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
BASELINE_COMMIT = "75680f0d4d08c9f62455e1f4bcb5c8a61d9c19df"
BASELINE_TREE = "efdb69ec52437eb4b342a5c7484db33cca2607c5"
BASELINE_HTML_COUNT = 14_624
NEW_DETAIL_COUNT = 371
NEW_HTML_COUNT = 373
FINAL_HTML_COUNT = 14_997
PLAN_DOCUMENT_COUNT = 15_000
RELEASE_CHANGE_COUNT = 15_003
RELEASE_DATE = "2026-08-20"
EXPECTED_SCHOOL_CHIPS = 889
EXPECTED_VISIBLE_SCHOOL_PAIRS = 529

GRADE_PARENT = "학년별학원"
GRADE_CATEGORY = "중3수학학원"
GRADE_LABEL = "학년별학원"
ZIP_SUFFIX = " 중3 수학학원.txt"
PARENT_REL = f"{GRADE_PARENT}/index.html"
CATEGORY_REL = f"{GRADE_PARENT}/{GRADE_CATEGORY}/index.html"
PARENT_ROUTE = f"/{quote(GRADE_PARENT, safe='')}/"
CATEGORY_ROUTE = f"/{quote(GRADE_PARENT, safe='')}/{quote(GRADE_CATEGORY, safe='')}/"
LLMS_PARENT_URL = f"{DOMAIN}/{GRADE_PARENT}/"
LLMS_CATEGORY_URL = f"{DOMAIN}/{GRADE_PARENT}/{GRADE_CATEGORY}/"

GENERATOR_REL = "tools/generate_grade3_math_pages.py"
CONTENT_AUDITOR_REL = "tools/audit_grade3_math_content.py"
TECHNICAL_AUDITOR_REL = "tools/audit_grade3_math_technical.py"
HEADER_CSS_REL = "assets/header.css"
LLMS_REL = "llms.txt"
SITEMAP_REL = "sitemap.xml"
ROBOTS_REL = "robots.txt"

# Frozen release inputs approved by the owning generator/content audits.
APPROVED_GENERATOR_SHA256 = "3f16b2834ef503c239ea01bd5300599976692c4d933ba72382d931924acf1d33"
APPROVED_CONTENT_AUDITOR_SHA256 = "895370c5a46ba9374123d0d9f6a644b7ab0d9cc009f40ea2d0696bf3b71f4865"
APPROVED_SOURCE_SHA256 = "93d58041e1a3672697ba083e7eb3dc7d65570703b68ab122b6cb00be24c6fbc6"
APPROVED_PLAN_CANDIDATE_SHA256 = "09b4ade937befba77760636c2f9539969ced1ac7e72accafab1cac6a0ac53c60"
APPROVED_PROJECTED_MANIFEST = "91416acd3301cf19c2d2a4a2aaf44d4a8135102ee082805dcf7c38c9125a9ab9"

KNOWN_BASELINE_BROKEN_ROUTE = (
    "/" + "/".join(quote(part, safe="") for part in ("교육정보", "수학-단어-암기법")) + "/"
)
KNOWN_BASELINE_BROKEN_OCCURRENCES = 1
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
BROWSER_WIDTHS = (320, 390, 900, 901, 1024, 1120, 1121, 1440)
PRUNED_DIRS = {".git", ".vercel", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}
IGNORED_SCHEMES = ("tel:", "sms:", "mailto:", "javascript:", "data:", "blob:")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DANGEROUS_MANUSCRIPT_RE = re.compile(
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
TRANSACTION_PATTERNS = (
    "*.txn",
    "*.journal",
    "*.rollback",
    "*.partial",
    "*.bak",
    "*.tmp",
    ".grade3-math-*",
    "*grade3*lock*",
)


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
            + result.stderr.decode("utf-8", "replace")[-2000:]
        )
    return result.stdout


def git_blob(root: Path, relative: str, ref: str = BASELINE_COMMIT) -> bytes:
    return run_git(root, ["show", f"{ref}:{relative}"])


def git_blobs_batch(root: Path, relatives: Sequence[str], ref: str = BASELINE_COMMIT) -> dict[str, memoryview]:
    """Read many blobs through one cat-file process (14k subprocesses is prohibitive)."""
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        query = b"".join(f"{ref}:{relative}\n".encode("utf-8") for relative in relatives)
        stdout, stderr = process.communicate(input=query)
        if process.returncode:
            raise RuntimeError(f"git cat-file failed ({process.returncode}): {stderr.decode('utf-8', 'replace')[-2000:]}")
        result: dict[str, memoryview] = {}
        view = memoryview(stdout)
        offset = 0
        for relative in relatives:
            line_end = stdout.find(b"\n", offset)
            if line_end < 0:
                raise RuntimeError(f"cat-file missing header for {relative}")
            header = stdout[offset:line_end].decode("utf-8", "replace")
            offset = line_end + 1
            parts = header.rsplit(" ", 2)
            if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
                raise RuntimeError(f"cat-file failed for {relative}: {header}")
            size = int(parts[2])
            end = offset + size
            if end > len(stdout) or stdout[end:end + 1] != b"\n":
                raise RuntimeError(f"cat-file truncated for {relative}")
            result[relative] = view[offset:end]
            offset = end + 1
        if offset != len(stdout):
            raise RuntimeError(f"cat-file unexpected trailing bytes: {len(stdout) - offset}")
        return result
    finally:
        if process.poll() is None:
            process.kill()


def baseline_paths(root: Path, pattern: str | None = None) -> list[str]:
    raw = run_git(root, ["ls-tree", "-r", "--name-only", "-z", BASELINE_COMMIT])
    values = [part.decode("utf-8") for part in raw.split(b"\0") if part]
    if pattern is None:
        return values
    return [value for value in values if PurePosixPath(value).match(pattern)]


def fs_bytes(root: Path, relative: str) -> bytes | None:
    path = root / PurePosixPath(relative)
    return path.read_bytes() if path.is_file() else None


def manifest(documents: Mapping[str, bytes]) -> str:
    rows = [f"{key}\0{sha256(documents[key])}" for key in sorted(documents)]
    return sha256("\n".join(rows).encode("utf-8"))


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
    return {
        key.lower(): html.unescape(content)
        for key, _, content in re.findall(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", value, re.S)
    }


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
        for value in list(values)[:limit]:
            self.errors.append({"code": code, "detail": value})


class DocumentParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.starts: list[tuple[str, dict[str, str]]] = []
        self.title_chunks: list[list[str]] = []
        self.h1_chunks: list[list[str]] = []
        self._title_depth = 0
        self._h1_depth = 0
        self._anchor_depth = 0
        self._anchor_chunks: list[str] = []
        self._anchor_attrs: dict[str, str] | None = None
        self._ld_depth = 0
        self._ld_chunks: list[str] = []
        self.ld_scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {key.lower(): value or "" for key, value in attrs}
        self.starts.append((tag, data))
        if tag == "meta":
            self.metas.append(data)
        elif tag == "link":
            self.links.append(data)
        elif tag == "img":
            self.images.append(data)
        if tag == "title":
            self.title_chunks.append([])
            self._title_depth = 1
        elif self._title_depth and tag not in self.VOID:
            self._title_depth += 1
        if tag == "h1":
            self.h1_chunks.append([])
            self._h1_depth = 1
        elif self._h1_depth and tag not in self.VOID:
            self._h1_depth += 1
        if tag == "a":
            self._anchor_depth = 1
            self._anchor_chunks = []
            self._anchor_attrs = data
        elif self._anchor_depth and tag not in self.VOID:
            self._anchor_depth += 1
        if tag == "script" and data.get("type", "").lower() == "application/ld+json":
            self._ld_depth = 1
            self._ld_chunks = []
        elif self._ld_depth and tag not in self.VOID:
            self._ld_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.VOID:
            return
        if self._title_depth:
            self._title_depth -= 1
        if self._h1_depth:
            self._h1_depth -= 1
        if self._anchor_depth:
            self._anchor_depth -= 1
            if not self._anchor_depth and self._anchor_attrs is not None:
                item = dict(self._anchor_attrs)
                item["_text"] = clean("".join(self._anchor_chunks))
                self.anchors.append(item)
                self._anchor_attrs = None
        if self._ld_depth:
            self._ld_depth -= 1
            if not self._ld_depth:
                self.ld_scripts.append("".join(self._ld_chunks).strip())
                self._ld_chunks = []

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            if self.title_chunks:
                self.title_chunks[-1].append(data)
        if self._h1_depth and self.h1_chunks:
            self.h1_chunks[-1].append(data)
        if self._anchor_depth:
            self._anchor_chunks.append(data)
        if self._ld_depth:
            self._ld_chunks.append(data)

    @property
    def titles(self) -> list[str]:
        return [clean("".join(chunks)) for chunks in self.title_chunks]

    @property
    def h1s(self) -> list[str]:
        return [clean("".join(chunks)) for chunks in self.h1_chunks]


def hidden_attributes(attrs: Mapping[str, str]) -> bool:
    return (
        "hidden" in attrs
        or attrs.get("aria-hidden", "").lower() == "true"
        or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", attrs.get("style", ""), re.I))
    )


class VisibleFAQParser(HTMLParser):
    """Collect ordered visible-source FAQ pairs from the single data-faq subtree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.faq_depth = 0
        self.faq_count = 0
        self.root_hidden: list[bool] = []
        self.current: dict[str, Any] | None = None
        self.summary_depth = 0
        self.answer_depth = 0
        self.details: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {key.lower(): value or "" for key, value in attrs}
        inside = self.faq_depth > 0
        if "data-faq" in data:
            self.faq_count += 1
            self.root_hidden.append(hidden_attributes(data))
            if tag not in DocumentParser.VOID:
                self.faq_depth = self.faq_depth + 1 if inside else 1
        elif inside and tag not in DocumentParser.VOID:
            self.faq_depth += 1
        if self.faq_depth <= 0:
            return
        if tag == "details":
            if self.current is not None:
                self.current["nested_details"] = True
            self.current = {
                "hidden": hidden_attributes(data),
                "summary_count": 0,
                "answer_count": 0,
                "summary": [],
                "answer": [],
                "nested_details": False,
            }
        elif self.current is not None:
            if tag == "summary":
                self.current["summary_count"] += 1
                self.summary_depth = 1
            elif self.summary_depth and tag not in DocumentParser.VOID:
                self.summary_depth += 1
            if tag == "p":
                self.current["answer_count"] += 1
                self.answer_depth = 1
            elif self.answer_depth and tag not in DocumentParser.VOID:
                self.answer_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in DocumentParser.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DocumentParser.VOID or self.faq_depth <= 0:
            return
        if self.summary_depth:
            self.summary_depth -= 1
        if self.answer_depth:
            self.answer_depth -= 1
        if tag == "details" and self.current is not None:
            self.details.append(self.current)
            self.current = None
            self.summary_depth = 0
            self.answer_depth = 0
        self.faq_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return
        if self.summary_depth:
            self.current["summary"].append(data)
        if self.answer_depth:
            self.current["answer"].append(data)


def parse_document(value: bytes, relative: str, audit: Audit) -> tuple[str, DocumentParser] | None:
    try:
        source = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        audit.hard(False, "utf8_document", {"path": relative, "error": str(exc)})
        return None
    parser = DocumentParser()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        audit.hard(False, "html_parse", {"path": relative, "error": f"{type(exc).__name__}: {exc}"})
        return None
    return source, parser


def nav_fragment(source: str) -> str | None:
    match = re.search(
        r"<nav\b(?=[^>]*\bclass=[\"'][^\"']*\bnav\b[^\"']*[\"'])[^>]*>.*?</nav\s*>",
        source,
        re.I | re.S,
    )
    return match.group(0) if match else None


def strip_nav(source: str) -> str:
    return re.sub(
        r"<nav\b(?=[^>]*\bclass=[\"'][^\"']*\bnav\b[^\"']*[\"'])[^>]*>.*?</nav\s*>",
        "<nav data-release-audit-placeholder></nav>",
        normalized_text(source),
        count=1,
        flags=re.I | re.S,
    )


ROOT_LD_RE = re.compile(
    r"(<script\b(?=[^>]*\btype=[\"']application/ld\+json[\"'])[^>]*>)(.*?)(</script\s*>)",
    re.I | re.S,
)


def validate_root_schema_exception(baseline: str, current: str) -> tuple[bool, Any]:
    """Allow only one appended grade WebPage in root WebPage.hasPart."""
    baseline_navless = strip_nav(baseline)
    current_navless = strip_nav(current)
    baseline_matches = list(ROOT_LD_RE.finditer(baseline_navless))
    current_matches = list(ROOT_LD_RE.finditer(current_navless))
    if len(baseline_matches) != 1 or len(current_matches) != 1:
        return False, {"baseline_ld": len(baseline_matches), "current_ld": len(current_matches)}
    try:
        baseline_data = json.loads(baseline_matches[0].group(2))
        current_data = json.loads(current_matches[0].group(2))
    except Exception as exc:
        return False, f"JSON parse: {type(exc).__name__}: {exc}"
    baseline_graph = baseline_data.get("@graph", []) if isinstance(baseline_data, Mapping) else []
    current_graph = current_data.get("@graph", []) if isinstance(current_data, Mapping) else []
    baseline_pages = [node for node in baseline_graph if isinstance(node, Mapping) and node.get("@type") == "WebPage" and node.get("@id") == DOMAIN + "/#webpage"]
    current_pages = [node for node in current_graph if isinstance(node, Mapping) and node.get("@type") == "WebPage" and node.get("@id") == DOMAIN + "/#webpage"]
    if len(baseline_pages) != 1 or len(current_pages) != 1:
        return False, {"baseline_webpage": len(baseline_pages), "current_webpage": len(current_pages)}
    expected = {"@type": "WebPage", "name": GRADE_LABEL, "url": DOMAIN + PARENT_ROUTE}
    baseline_parts = baseline_pages[0].get("hasPart")
    current_parts = current_pages[0].get("hasPart")
    if not isinstance(baseline_parts, list) or not isinstance(current_parts, list) or current_parts != [*baseline_parts, expected]:
        return False, {"baseline_hasPart": baseline_parts, "current_hasPart": current_parts, "expected_append": expected}
    # Remove only the approved append, then the complete graph must be semantically equal.
    current_parts.pop()
    if current_data != baseline_data:
        return False, "root JSON-LD differs beyond approved hasPart append"
    baseline_shell = ROOT_LD_RE.sub(r"\1__ROOT_JSONLD__\3", baseline_navless, count=1)
    current_shell = ROOT_LD_RE.sub(r"\1__ROOT_JSONLD__\3", current_navless, count=1)
    if baseline_shell != current_shell:
        return False, "root HTML outside nav/JSON-LD differs"
    return True, {"approved_append": expected, "baseline_hasPart": len(baseline_parts)}


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
                "aria-current": attrs.get("aria-current", ""),
            }
        )
    return values


def tree_snapshot(root: Path) -> tuple[str, int, int]:
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


def discover_common_dir(root: Path, supplied: Path | None) -> Path:
    candidates = [
        supplied,
        root.parent / "참고자료" / "공통자료",
        root.parent.parent / "참고자료" / "공통자료",
        Path.home() / "Desktop" / "홈페이지 정리" / "참고자료" / "공통자료",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError("common data directory not found; pass --common-dir")


def discover_zip(supplied: Path | None) -> Path:
    candidates = [supplied, Path.home() / "Desktop" / "중3 수학학원.zip"]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("source ZIP not found; pass --zip-path")


@dataclass(frozen=True)
class SourceIndex:
    zip_path: Path
    sha256: str
    entry_names: tuple[str, ...]
    localities: tuple[str, ...]
    total_uncompressed: int


def inspect_zip(zip_path: Path, audit: Audit) -> SourceIndex:
    digest = sha256(zip_path.read_bytes())
    with ZipFile(zip_path) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
    names = [item.filename for item in infos]
    unsafe = [
        name
        for name in names
        if name.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", name)
        or any(part == ".." for part in re.split(r"[\\/]", name))
        or "\x00" in name
        or "/" in name
        or "\\" in name
    ]
    wrong_suffix = [name for name in names if not name.endswith(ZIP_SUFFIX)]
    localities = [name[: -len(ZIP_SUFFIX)] for name in names if name.endswith(ZIP_SUFFIX)]
    invalid_localities = [
        value
        for value in localities
        if not value.strip()
        or value != value.strip()
        or CONTROL_RE.search(value)
        or value.endswith((".", " "))
        or value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    ]
    audit.hard(len(infos) == NEW_DETAIL_COUNT, "zip_entry_count", {"expected": NEW_DETAIL_COUNT, "actual": len(infos)})
    audit.hard(len(names) == len(set(names)), "zip_unique_names", len(names) - len(set(names)))
    audit.hard(not unsafe, "zip_unsafe_names", unsafe[:20])
    audit.hard(not wrong_suffix, "zip_filename_contract", wrong_suffix[:20])
    audit.hard(len(localities) == NEW_DETAIL_COUNT and len(set(localities)) == NEW_DETAIL_COUNT, "zip_locality_cardinality", {"total": len(localities), "unique": len(set(localities))})
    audit.hard(not invalid_localities, "zip_locality_safety", invalid_localities[:20])
    audit.hard(not any(item.flag_bits & 1 for item in infos), "zip_encrypted_entries")
    audit.hard(not any(item.file_size == 0 for item in infos), "zip_empty_entries")
    audit.observations["source_zip"] = {
        "path": str(zip_path),
        "sha256": digest,
        "entries": len(infos),
        "unique_localities": len(set(localities)),
        "uncompressed_bytes": sum(item.file_size for item in infos),
        "nested": len(unsafe),
    }
    return SourceIndex(
        zip_path=zip_path,
        sha256=digest,
        entry_names=tuple(names),
        localities=tuple(localities),
        total_uncompressed=sum(item.file_size for item in infos),
    )


def expected_new_html(source: SourceIndex) -> list[str]:
    return [
        PARENT_REL,
        CATEGORY_REL,
        *(f"{GRADE_PARENT}/{GRADE_CATEGORY}/{locality}/index.html" for locality in source.localities),
    ]


def expected_plan_paths(root: Path, source: SourceIndex) -> tuple[list[str], set[str], set[str]]:
    old_html = baseline_paths(root, "*.html")
    new_html = expected_new_html(source)
    all_html = old_html + new_html
    documents = set(all_html) | {SITEMAP_REL, HEADER_CSS_REL, LLMS_REL}
    return all_html, set(new_html), documents


def load_module(path: Path) -> Any:
    name = f"_grade3_generator_{sha256(str(path).encode())[:12]}_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)


def plan_value(plan: Any, name: str, default: Any = None) -> Any:
    if isinstance(plan, Mapping):
        return plan.get(name, default)
    return getattr(plan, name, default)


def normalize_plan_documents(root: Path, plan: Any, audit: Audit, code: str) -> dict[str, bytes]:
    raw = plan_value(plan, "documents")
    if raw is None:
        raw = plan_value(plan, "files")
    if raw is None:
        raw = plan_value(plan, "authorized_documents")
    if not isinstance(raw, Mapping):
        audit.hard(False, code + "_mapping", type(raw).__name__)
        return {}
    result: dict[str, bytes] = {}
    folded: dict[str, str] = {}
    errors: list[Any] = []
    for key, value in raw.items():
        try:
            path = Path(key)
            if path.is_absolute():
                relative = path.resolve().relative_to(root.resolve()).as_posix()
            else:
                relative = PurePosixPath(str(key).replace("\\", "/")).as_posix()
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts or CONTROL_RE.search(relative):
                raise ValueError("unsafe relative path")
            lowered = relative.casefold()
            if lowered in folded:
                raise ValueError(f"case/duplicate collision with {folded[lowered]}")
            folded[lowered] = relative
            if isinstance(value, str):
                data = value.encode("utf-8")
            elif isinstance(value, (bytes, bytearray)):
                data = bytes(value)
            else:
                raise TypeError(f"unsupported value {type(value).__name__}")
            result[relative] = data
        except Exception as exc:
            errors.append({"key": str(key), "error": f"{type(exc).__name__}: {exc}"})
    audit.extend(code + "_contract", errors)
    return result


def compare_plan_documents_streaming(
    root: Path,
    plan: Any,
    expected: Mapping[str, bytes],
    audit: Audit,
    code: str,
) -> str:
    """Compare a repeated plan without retaining another ~650 MB byte mapping."""
    raw = plan_value(plan, "documents")
    if raw is None:
        raw = plan_value(plan, "files")
    if raw is None:
        raw = plan_value(plan, "authorized_documents")
    if not isinstance(raw, Mapping):
        audit.hard(False, code + "_mapping", type(raw).__name__)
        return ""
    keyed: dict[str, Any] = {}
    folded: dict[str, str] = {}
    errors: list[Any] = []
    for key, value in raw.items():
        try:
            path = Path(key)
            if path.is_absolute():
                relative = path.resolve().relative_to(root.resolve()).as_posix()
            else:
                relative = PurePosixPath(str(key).replace("\\", "/")).as_posix()
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts or CONTROL_RE.search(relative):
                raise ValueError("unsafe relative path")
            lowered = relative.casefold()
            if lowered in folded:
                raise ValueError(f"case/duplicate collision with {folded[lowered]}")
            folded[lowered] = relative
            if not isinstance(value, (str, bytes, bytearray)):
                raise TypeError(f"unsupported value {type(value).__name__}")
            keyed[relative] = value
        except Exception as exc:
            errors.append({"key": str(key), "error": f"{type(exc).__name__}: {exc}"})
    audit.extend(code + "_contract", errors)
    expected_keys = set(expected)
    actual_keys = set(keyed)
    audit.hard(
        actual_keys == expected_keys,
        code + "_scope",
        {"missing": sorted(expected_keys - actual_keys)[:30], "extra": sorted(actual_keys - expected_keys)[:30]},
    )
    rows: list[str] = []
    mismatch_count = 0
    mismatch_samples: list[Any] = []
    for relative in sorted(keyed):
        value = keyed[relative]
        data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
        digest = sha256(data)
        rows.append(f"{relative}\0{digest}")
        expected_value = expected.get(relative)
        if expected_value != data:
            mismatch_count += 1
            if len(mismatch_samples) < 30:
                mismatch_samples.append(
                    {
                        "path": relative,
                        "expected": sha256(expected_value) if expected_value is not None else "MISSING",
                        "actual": digest,
                    }
                )
    audit.hard(
        mismatch_count == 0,
        code + "_bytes",
        {"count": mismatch_count, "samples": mismatch_samples},
    )
    return sha256("\n".join(rows).encode("utf-8")) if rows else ""


def normalize_changed_paths(root: Path, value: Any, audit: Audit, code: str) -> set[str]:
    if value is None:
        return set()
    result: set[str] = set()
    errors: list[Any] = []
    for item in value:
        try:
            path = Path(item)
            relative = (
                path.resolve().relative_to(root.resolve()).as_posix()
                if path.is_absolute()
                else PurePosixPath(str(item).replace("\\", "/")).as_posix()
            )
            if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
                raise ValueError("unsafe path")
            result.add(relative)
        except Exception as exc:
            errors.append({"path": str(item), "error": str(exc)})
    audit.extend(code, errors)
    return result


def normalize_hash_mapping(root: Path, value: Any, audit: Audit, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        audit.hard(False, code + "_mapping", type(value).__name__)
        return {}
    result: dict[str, str] = {}
    errors: list[Any] = []
    for key, digest in value.items():
        try:
            path = Path(key)
            relative = (
                path.resolve().relative_to(root.resolve()).as_posix()
                if path.is_absolute()
                else PurePosixPath(str(key).replace("\\", "/")).as_posix()
            )
            if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
                raise ValueError("unsafe path")
            digest = str(digest).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid SHA-256")
            if relative in result:
                raise ValueError("duplicate path")
            result[relative] = digest
        except Exception as exc:
            errors.append({"key": str(key), "digest": str(digest), "error": str(exc)})
    audit.extend(code + "_contract", errors)
    return result


@dataclass
class Projection:
    documents: dict[str, bytes]
    changed_paths: set[str]
    generator_sha256: str
    source_sha256: str
    projected_manifest: str


def validate_plan_stability_metadata(label: str, plan: Any, audit: Audit) -> None:
    declared = plan_value(plan, "second_pass_changes", 0)
    try:
        count = len(declared) if not isinstance(declared, (int, float)) else int(declared)
    except Exception:
        count = -1
    audit.hard(count == 0, f"projection_{label}_second_pass_changes", count)
    diagnostics = plan_value(plan, "diagnostics", {})
    if diagnostics is not None:
        audit.hard(isinstance(diagnostics, Mapping), f"projection_{label}_diagnostics_type", type(diagnostics).__name__)
        if isinstance(diagnostics, Mapping):
            errors = diagnostics.get("errors", ())
            audit.hard(
                not errors,
                f"projection_{label}_diagnostics_errors",
                list(errors)[:30] if isinstance(errors, (list, tuple, set)) else errors,
            )


def run_projection(
    root: Path,
    generator: Path,
    zip_path: Path,
    common_dir: Path,
    expected: set[str],
    audit: Audit,
) -> Projection | None:
    generator_digest = sha256(generator.read_bytes())
    repo_before = tree_snapshot(root)
    common_before = directory_snapshot(common_dir)
    zip_before = sha256(zip_path.read_bytes())
    status_before = run_git(root, ["status", "--porcelain=v1", "-z"], check=True)
    try:
        module = load_module(generator)
        build_plan = getattr(module, "build_plan", None)
        audit.hard(callable(build_plan), "generator_build_plan", "missing callable build_plan")
        if not callable(build_plan):
            return None
        signature = inspect.signature(build_plan)
        required = {"root", "zip_path", "common_dir", "current_overrides"}
        audit.hard(required <= set(signature.parameters), "generator_api_signature", str(signature))
        if not required <= set(signature.parameters):
            return None

        kwargs = {"root": root, "zip_path": zip_path, "common_dir": common_dir, "current_overrides": None}
        first = build_plan(**kwargs)
        documents = normalize_plan_documents(root, first, audit, "projection_first")
        audit.hard(set(documents) == expected, "projection_scope", {"missing": sorted(expected - set(documents))[:30], "extra": sorted(set(documents) - expected)[:30]})
        audit.hard(len(documents) == PLAN_DOCUMENT_COUNT, "projection_document_count", {"expected": PLAN_DOCUMENT_COUNT, "actual": len(documents)})
        projected_manifest = manifest(documents) if documents else ""
        first_before = normalize_hash_mapping(root, plan_value(first, "before_manifest"), audit, "projection_before_manifest")
        first_after = normalize_hash_mapping(root, plan_value(first, "after_manifest"), audit, "projection_after_manifest")
        expected_after = {relative: sha256(value) for relative, value in documents.items()}
        audit.hard(set(first_before) == expected, "projection_before_manifest_scope", {"missing": sorted(expected - set(first_before))[:30], "extra": sorted(set(first_before) - expected)[:30]})
        audit.hard(first_after == expected_after, "projection_after_manifest_values", {"declared_paths": len(first_after), "expected_paths": len(expected_after)})
        raw_before_exists = plan_value(first, "before_exists")
        audit.hard(isinstance(raw_before_exists, Mapping), "projection_before_exists_mapping", type(raw_before_exists).__name__)
        normalized_before_exists: dict[str, bool] = {}
        if isinstance(raw_before_exists, Mapping):
            for key, exists in raw_before_exists.items():
                path = Path(key)
                relative = path.resolve().relative_to(root.resolve()).as_posix() if path.is_absolute() else PurePosixPath(str(key).replace("\\", "/")).as_posix()
                normalized_before_exists[relative] = bool(exists)
        audit.hard(set(normalized_before_exists) == expected, "projection_before_exists_scope", {"missing": sorted(expected - set(normalized_before_exists))[:30], "extra": sorted(set(normalized_before_exists) - expected)[:30]})
        before_value_errors: list[Any] = []
        for relative in expected:
            current = fs_bytes(root, relative)
            declared_exists = normalized_before_exists.get(relative)
            if declared_exists != (current is not None):
                before_value_errors.append({"path": relative, "declared_exists": declared_exists, "actual_exists": current is not None})
            elif current is not None and first_before.get(relative) != sha256(current):
                before_value_errors.append({"path": relative, "declared": first_before.get(relative), "actual": sha256(current)})
        audit.extend("projection_before_manifest_values", before_value_errors)
        source_manifest = plan_value(first, "source_manifest")
        audit.hard(isinstance(source_manifest, Mapping), "projection_source_manifest_type", type(source_manifest).__name__)
        normalized_sources = {str(key): str(value).lower() for key, value in source_manifest.items()} if isinstance(source_manifest, Mapping) else {}
        audit.hard(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in normalized_sources.values()), "projection_source_manifest_hashes", normalized_sources)
        audit.hard(normalized_sources.get("manuscript_zip") == zip_before, "projection_source_manifest_zip", {"declared": normalized_sources.get("manuscript_zip"), "actual": zip_before})
        common_sources = {
            "center_csv": common_dir / "센터정보 정리.csv",
            "target_school_csv": common_dir / "타깃학교.csv",
        }
        for name, path in common_sources.items():
            audit.hard(path.is_file(), "projection_common_source_missing", str(path))
            if path.is_file():
                actual_digest = sha256(path.read_bytes())
                audit.hard(normalized_sources.get(name) == actual_digest, "projection_common_source_sha256", {"name": name, "declared": normalized_sources.get(name), "actual": actual_digest})
        source_metrics = plan_value(first, "source_metrics")
        audit.hard(isinstance(source_metrics, Mapping), "projection_source_metrics_type", type(source_metrics).__name__)
        school_metric_contract = {
            "provided_middle_school_source_tokens": EXPECTED_SCHOOL_CHIPS,
            "provided_unique_middle_school_tokens": EXPECTED_SCHOOL_CHIPS,
            "screen_unique_authoritative_middle_school_mentions": EXPECTED_SCHOOL_CHIPS,
            "manuscript_visible_authoritative_middle_school_source_token_pairs": EXPECTED_VISIBLE_SCHOOL_PAIRS,
            "manuscript_visible_unique_authoritative_middle_school_pairs": EXPECTED_VISIBLE_SCHOOL_PAIRS,
        }
        if isinstance(source_metrics, Mapping):
            for name, expected_value in school_metric_contract.items():
                audit.hard(
                    source_metrics.get(name) == expected_value,
                    "projection_school_metric",
                    {"name": name, "expected": expected_value, "actual": source_metrics.get(name)},
                )
        candidate = str(plan_value(first, "candidate_sha256", "")).lower()
        audit.hard(bool(re.fullmatch(r"[0-9a-f]{64}", candidate)), "projection_candidate_sha256", candidate)
        audit.hard(
            candidate == APPROVED_PLAN_CANDIDATE_SHA256,
            "pinned_plan_candidate_sha256",
            {"expected": APPROVED_PLAN_CANDIDATE_SHA256, "actual": candidate},
        )
        source_digest = str(plan_value(first, "source_sha256", zip_before) or zip_before).lower()
        audit.hard(source_digest == zip_before, "projection_source_sha256", {"declared": source_digest, "actual": zip_before})
        validate_plan_stability_metadata("first", first, audit)

        actual_changed = {
            relative
            for relative, value in documents.items()
            if fs_bytes(root, relative) != value
        }
        declared_changed = normalize_changed_paths(root, plan_value(first, "changed_paths", ()), audit, "projection_first_changed")
        audit.hard(declared_changed == actual_changed, "projection_declared_changed", {"declared_only": sorted(declared_changed - actual_changed)[:30], "actual_only": sorted(actual_changed - declared_changed)[:30]})
        audit.hard(len(actual_changed) in {0, PLAN_DOCUMENT_COUNT}, "projection_partial_materialization", {"expected": [0, PLAN_DOCUMENT_COUNT], "actual": len(actual_changed)})
        del first
        gc.collect()

        repeat = build_plan(**kwargs)
        repeat_manifest = compare_plan_documents_streaming(root, repeat, documents, audit, "projection_repeat")
        audit.hard(repeat_manifest == projected_manifest, "projection_deterministic_manifest", {"first": projected_manifest, "repeat": repeat_manifest})
        audit.hard(str(plan_value(repeat, "candidate_sha256", "")).lower() == candidate, "projection_candidate_repeat")
        validate_plan_stability_metadata("repeat", repeat, audit)
        del repeat
        gc.collect()

        overrides = {relative: value for relative, value in documents.items()}
        second = build_plan(root=root, zip_path=zip_path, common_dir=common_dir, current_overrides=overrides)
        second_manifest = compare_plan_documents_streaming(root, second, documents, audit, "projection_second")
        second_changed = normalize_changed_paths(root, plan_value(second, "changed_paths", ()), audit, "projection_second_changed")
        audit.hard(second_manifest == projected_manifest, "projection_second_manifest", {"first": projected_manifest, "second": second_manifest})
        audit.hard(not second_changed, "projection_second_changed_paths", sorted(second_changed)[:30])
        audit.hard(normalize_hash_mapping(root, plan_value(second, "after_manifest"), audit, "projection_second_after_manifest") == expected_after, "projection_second_after_manifest_values")
        audit.hard(str(plan_value(second, "candidate_sha256", "")).lower() == candidate, "projection_candidate_second")
        validate_plan_stability_metadata("second", second, audit)
        second_changed_count = len(second_changed)
        del second
        gc.collect()

        reverse_overrides = dict(reversed(list(overrides.items())))
        reverse = build_plan(root=root, zip_path=zip_path, common_dir=common_dir, current_overrides=reverse_overrides)
        reverse_manifest = compare_plan_documents_streaming(root, reverse, documents, audit, "projection_reverse")
        reverse_changed = normalize_changed_paths(root, plan_value(reverse, "changed_paths", ()), audit, "projection_reverse_changed")
        audit.hard(reverse_manifest == projected_manifest, "projection_reverse_order_manifest", {"first": projected_manifest, "reverse": reverse_manifest})
        audit.hard(not reverse_changed, "projection_reverse_changed_paths", sorted(reverse_changed)[:30])
        audit.hard(normalize_hash_mapping(root, plan_value(reverse, "after_manifest"), audit, "projection_reverse_after_manifest") == expected_after, "projection_reverse_after_manifest_values")
        audit.hard(str(plan_value(reverse, "candidate_sha256", "")).lower() == candidate, "projection_candidate_reverse")
        validate_plan_stability_metadata("reverse", reverse, audit)
        reverse_changed_count = len(reverse_changed)
        del reverse, reverse_overrides
        gc.collect()

        audit.observations["projection"] = {
            "documents": len(documents),
            "changed": len(actual_changed),
            "second_changed": second_changed_count,
            "reverse_changed": reverse_changed_count,
            "manifest": projected_manifest,
            "generator_sha256": generator_digest,
            "source_sha256": source_digest,
            "candidate_sha256": candidate,
            "source_manifest": normalized_sources,
        }
        return Projection(documents, actual_changed, generator_digest, source_digest, projected_manifest)
    finally:
        repo_after = tree_snapshot(root)
        common_after = directory_snapshot(common_dir)
        zip_after = sha256(zip_path.read_bytes())
        status_after = run_git(root, ["status", "--porcelain=v1", "-z"], check=True)
        audit.hard(repo_before == repo_after, "projection_repo_read_only", {"before": repo_before, "after": repo_after})
        audit.hard(common_before == common_after, "projection_common_read_only", {"before": common_before, "after": common_after})
        audit.hard(zip_before == zip_after, "projection_zip_read_only", {"before": zip_before, "after": zip_after})
        audit.hard(status_before == status_after, "projection_git_status_read_only")
        audit.observations["projection_freeze"] = {
            "repo": repo_before,
            "common": common_before,
            "zip_sha256": zip_before,
            "git_status_equal": status_before == status_after,
        }


def pin_inputs(
    root: Path,
    projection: Projection | None,
    source: SourceIndex,
    generator: Path,
    content_auditor: Path,
    audit: Audit,
) -> None:
    paths = {
        GENERATOR_REL: (generator, APPROVED_GENERATOR_SHA256),
        CONTENT_AUDITOR_REL: (content_auditor, APPROVED_CONTENT_AUDITOR_SHA256),
    }
    actual: dict[str, str] = {}
    pending: list[str] = []
    for relative, (path, approved) in paths.items():
        canonical_path = root / PurePosixPath(relative)
        audit.hard(canonical_path.is_file(), "pinned_file_missing", relative)
        audit.hard(path.is_file(), "pinned_override_missing", str(path))
        digest = sha256(canonical_path.read_bytes()) if canonical_path.is_file() else "MISSING"
        override_digest = sha256(path.read_bytes()) if path.is_file() else "MISSING"
        audit.hard(
            digest == override_digest,
            "pinned_override_parity",
            {"path": relative, "canonical": digest, "override": override_digest},
        )
        actual[relative] = digest
        if approved == "PENDING":
            pending.append(relative)
        else:
            audit.hard(digest == approved, "pinned_file_sha256", {"path": relative, "expected": approved, "actual": digest})
    if APPROVED_SOURCE_SHA256 == "PENDING":
        pending.append("source_zip")
    else:
        audit.hard(source.sha256 == APPROVED_SOURCE_SHA256, "pinned_source_sha256", {"expected": APPROVED_SOURCE_SHA256, "actual": source.sha256})
    if projection is not None:
        if APPROVED_PROJECTED_MANIFEST == "PENDING":
            pending.append("projected_manifest")
        else:
            audit.hard(projection.projected_manifest == APPROVED_PROJECTED_MANIFEST, "pinned_projected_manifest", {"expected": APPROVED_PROJECTED_MANIFEST, "actual": projection.projected_manifest})
    audit.hold(not pending, "freeze_pins_pending", pending)
    audit.observations["pins"] = {
        "actual": actual,
        "source_sha256": source.sha256,
        "projected_manifest": projection.projected_manifest if projection else None,
        "pending": pending,
    }


def validate_source_localities(root: Path, source: SourceIndex, audit: Audit) -> None:
    reference = root / "과목별학원" / "고등내신학원"
    values = [path.parent.name for path in reference.glob("*/index.html")]
    audit.hard(len(values) == NEW_DETAIL_COUNT, "reference_locality_count", len(values))
    audit.hard(set(values) == set(source.localities), "source_locality_set", {"zip_only": sorted(set(source.localities) - set(values))[:30], "reference_only": sorted(set(values) - set(source.localities))[:30]})
    audit.observations["localities"] = {
        "zip_order_count": len(source.localities),
        "reference_count": len(values),
        "sets_equal": set(values) == set(source.localities),
        "space_routes": sum(" " in value for value in source.localities),
        "longest": max(source.localities, key=lambda value: (len(value), -source.localities.index(value))) if source.localities else None,
    }


def parse_sitemap(value: bytes, code: str, audit: Audit) -> tuple[str, list[tuple[str, str]], list[str]]:
    try:
        text = value.decode("utf-8")
        root = ET.fromstring(text)
    except Exception as exc:
        audit.hard(False, code + "_xml", f"{type(exc).__name__}: {exc}")
        return "", [], []
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    rows: list[tuple[str, str]] = []
    for node in root.findall("s:url", namespace):
        rows.append(((node.findtext("s:loc", default="", namespaces=namespace) or "").strip(), (node.findtext("s:lastmod", default="", namespaces=namespace) or "").strip()))
    blocks = re.findall(r"[ \t]*<url>.*?</url>", normalized_text(text), re.S)
    return text, rows, blocks


def validate_sitemap(root: Path, value: bytes, all_html: list[str], new_html: list[str], audit: Audit) -> None:
    baseline_text, baseline_rows, baseline_blocks = parse_sitemap(git_blob(root, SITEMAP_REL), "baseline_sitemap", audit)
    final_text, final_rows, final_blocks = parse_sitemap(value, "final_sitemap", audit)
    audit.hard(len(baseline_rows) == BASELINE_HTML_COUNT, "baseline_sitemap_count", len(baseline_rows))
    audit.hard(len(final_rows) == FINAL_HTML_COUNT, "final_sitemap_count", len(final_rows))
    audit.hard(len({loc for loc, _ in final_rows}) == FINAL_HTML_COUNT, "final_sitemap_unique")
    audit.hard(final_rows[:BASELINE_HTML_COUNT] == baseline_rows, "sitemap_non_target_rows_preserved", {"baseline": len(baseline_rows), "matching_prefix": next((index for index, (left, right) in enumerate(zip(final_rows, baseline_rows)) if left != right), BASELINE_HTML_COUNT)})
    audit.hard(final_blocks[:BASELINE_HTML_COUNT] == baseline_blocks, "sitemap_non_target_raw_blocks_preserved")
    expected_tail = [(DOMAIN + route_for_relative(relative), RELEASE_DATE) for relative in new_html]
    audit.hard(final_rows[BASELINE_HTML_COUNT:] == expected_tail, "sitemap_target_tail_order", {"expected_first": expected_tail[:3], "actual_first": final_rows[BASELINE_HTML_COUNT:BASELINE_HTML_COUNT + 3], "expected_last": expected_tail[-3:], "actual_last": final_rows[-3:]})
    expected_routes = {route_for_relative(relative) for relative in all_html}
    actual_routes = {normalize_route(loc) for loc, _ in final_rows}
    audit.hard(actual_routes == expected_routes, "sitemap_html_route_set", {"missing": sorted(expected_routes - actual_routes)[:30], "extra": sorted(actual_routes - expected_routes)[:30]})
    audit.hard(all(lastmod for _, lastmod in final_rows), "sitemap_lastmod_presence")
    audit.hard(normalized_text(final_text).startswith(normalized_text(baseline_text).split("</urlset>", 1)[0]), "sitemap_baseline_prefix_preserved")
    audit.observations["sitemap"] = {
        "baseline_rows": len(baseline_rows),
        "final_rows": len(final_rows),
        "new_rows": len(final_rows) - len(baseline_rows),
        "unique": len({loc for loc, _ in final_rows}),
        "new_lastmod": Counter(lastmod for _, lastmod in final_rows[BASELINE_HTML_COUNT:]),
    }


def validate_header_css(root: Path, value: bytes, audit: Audit) -> None:
    baseline = normalized_text(git_blob(root, HEADER_CSS_REL).decode("utf-8"))
    final = normalized_text(value.decode("utf-8"))
    expected = baseline.replace("@media (max-width: 900px)", "@media (max-width: 1120px)")
    audit.hard(baseline.count("@media (max-width: 900px)") == 1, "baseline_header_breakpoint")
    audit.hard(final == expected, "header_css_only_breakpoint_change")
    audit.hard(final.count("@media (max-width: 1120px)") == 1, "header_css_1120_breakpoint")
    audit.hard("grid-template-columns: repeat(4, minmax(0, 1fr))" in final, "header_css_mobile_columns")
    audit.hard("grid-template-rows: repeat(2, 32px)" in final, "header_css_mobile_rows")


def validate_llms(root: Path, value: bytes, audit: Audit) -> None:
    baseline = normalized_text(git_blob(root, LLMS_REL).decode("utf-8"))
    final = normalized_text(value.decode("utf-8"))
    block = (
        "## 학년별학원 핵심 허브\n\n"
        f"- 학년별학원: {LLMS_PARENT_URL}\n"
        "  - 학생 학년을 먼저 선택해 현재 제공되는 과목별 지역 안내를 찾는 핵심 허브입니다.\n"
        f"- 중3 수학학원: {LLMS_CATEGORY_URL}\n"
        "  - 중3 수학 진단·학교 자료·오답 재학습·상담 기준을 371개 동네별 원고로 안내합니다.\n"
    )
    expected = baseline + ("\n" if baseline.endswith("\n") else "\n\n") + block
    audit.hard(final == expected, "llms_exact_approved_append", {"expected_chars": len(expected), "actual_chars": len(final)})
    appended = final[len(baseline):] if final.startswith(baseline) else ""
    urls = re.findall(r"https://wawa-center\.kr/[^\s<>]*", appended)
    routes = [normalize_route(value.rstrip(".,;:)]")) for value in urls]
    parent_hits = routes.count(PARENT_ROUTE)
    category_hits = routes.count(CATEGORY_ROUTE)
    audit.hard(parent_hits == 1, "llms_parent_url", parent_hits)
    audit.hard(category_hits == 1, "llms_category_url", category_hits)
    audit.hard(appended.count("## 학년별학원 핵심 허브") == 1, "llms_heading_count")


def recursive_image_urls(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "image":
                result |= image_value_urls(item)
            result |= recursive_image_urls(item)
    elif isinstance(value, list):
        for item in value:
            result |= recursive_image_urls(item)
    return result


def image_value_urls(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        return {str(value[key]) for key in ("url", "contentUrl") if isinstance(value.get(key), str)} | recursive_image_urls(value)
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= image_value_urls(item)
        return result
    return set()


def find_main(parser: DocumentParser, **attrs: str) -> list[dict[str, str]]:
    return [data for tag, data in parser.starts if tag == "main" and all(data.get(key) == value for key, value in attrs.items())]


def data_nodes(parser: DocumentParser, key: str, value: str | None = None) -> list[tuple[str, dict[str, str]]]:
    return [(tag, data) for tag, data in parser.starts if key in data and (value is None or data.get(key) == value)]


def schema_graph_nodes(parser: DocumentParser) -> list[Mapping[str, Any]]:
    nodes: list[Mapping[str, Any]] = []
    for block in parser.ld_scripts:
        try:
            value = json.loads(block)
        except Exception:
            continue
        if not isinstance(value, Mapping):
            continue
        graph = value.get("@graph")
        if isinstance(graph, list):
            nodes.extend(item for item in graph if isinstance(item, Mapping))
        else:
            nodes.append(value)
    return nodes


def validate_hub_faq(source: str, parser: DocumentParser, relative: str, audit: Audit) -> None:
    """Require two source-visible hub Q&As and exact ordered FAQPage parity."""
    faq_nodes = data_nodes(parser, "data-faq")
    audit.hard(len(faq_nodes) == 1, "hub_faq_hook", {"path": relative, "count": len(faq_nodes)})
    visible = VisibleFAQParser()
    try:
        visible.feed(source)
        visible.close()
    except Exception as exc:
        audit.hard(False, "hub_faq_visible_parse", {"path": relative, "error": f"{type(exc).__name__}: {exc}"})
        return
    audit.hard(
        visible.faq_count == 1 and visible.root_hidden == [False],
        "hub_faq_visible_wrapper",
        {"path": relative, "count": visible.faq_count, "hidden": visible.root_hidden},
    )
    pairs: list[tuple[str, str]] = []
    detail_errors: list[Any] = []
    for index, detail in enumerate(visible.details, 1):
        question_text = clean("".join(detail["summary"]))
        answer_text = clean("".join(detail["answer"]))
        if (
            detail["hidden"]
            or detail["nested_details"]
            or detail["summary_count"] != 1
            or detail["answer_count"] != 1
            or not question_text
            or not answer_text
        ):
            detail_errors.append(
                {
                    "index": index,
                    "hidden": detail["hidden"],
                    "nested_details": detail["nested_details"],
                    "summaries": detail["summary_count"],
                    "answers": detail["answer_count"],
                    "question": question_text,
                    "answer": answer_text,
                }
            )
        pairs.append((question_text, answer_text))
    audit.hard(
        len(visible.details) == 2 and len(pairs) == 2 and len(set(pairs)) == 2 and not detail_errors,
        "hub_faq_visible_two_unique",
        {"path": relative, "count": len(visible.details), "pairs": pairs, "errors": detail_errors},
    )
    faq_pages = [node for node in schema_graph_nodes(parser) if node.get("@type") == "FAQPage"]
    expected_entities = [
        {
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {"@type": "Answer", "text": answer},
        }
        for question, answer in pairs
    ]
    actual_entities = faq_pages[0].get("mainEntity") if len(faq_pages) == 1 else None
    audit.hard(
        len(faq_pages) == 1 and actual_entities == expected_entities,
        "hub_faq_schema_visible_exact_parity",
        {
            "path": relative,
            "faq_page_count": len(faq_pages),
            "expected": expected_entities,
            "actual": actual_entities,
        },
    )


@dataclass
class DetailReport:
    relative: str
    route: str
    locality: str
    status: str
    blank_school: bool


def audit_documents(
    root: Path,
    documents: Mapping[str, bytes],
    all_html: list[str],
    new_html: set[str],
    source: SourceIndex,
    audit: Audit,
) -> list[DetailReport]:
    audit.hard(len(all_html) == FINAL_HTML_COUNT, "final_html_path_count", len(all_html))
    route_to_relative = {route_for_relative(relative): relative for relative in all_html}
    audit.hard(len(route_to_relative) == FINAL_HTML_COUNT, "final_html_route_unique")
    filesystem_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not any(part in PRUNED_DIRS for part in path.relative_to(root).parts)
    }
    parsed: dict[str, tuple[str, DocumentParser]] = {}
    hard_samples: defaultdict[str, list[Any]] = defaultdict(list)
    canonicals: list[str] = []
    grade_active = 0
    grade_links = 0
    jsonld_blocks = 0
    jsonld_errors = 0
    resource_refs: Counter[str] = Counter()
    resource_samples: dict[str, Any] = {}
    graph: defaultdict[str, set[str]] = defaultdict(set)
    broken: Counter[str] = Counter()
    broken_samples: dict[str, Any] = {}
    details: list[DetailReport] = []
    school_chip_total = 0

    for relative in all_html:
        value = documents.get(relative)
        if value is None:
            hard_samples["document_missing"].append(relative)
            continue
        result = parse_document(value, relative, audit)
        if result is None:
            continue
        source_text, parser = result
        parsed[relative] = result
        route = route_for_relative(relative)
        if CONTROL_RE.search(source_text):
            hard_samples["control_character"].append(relative)
        if len(parser.titles) != 1 or not parser.titles[0]:
            hard_samples["title_count"].append({"path": relative, "values": parser.titles})
        if len(parser.h1s) != 1 or not parser.h1s[0]:
            hard_samples["h1_count"].append({"path": relative, "values": parser.h1s})
        canonical_values = [item.get("href", "") for item in parser.links if "canonical" in item.get("rel", "").lower().split()]
        og_values = [item.get("content", "") for item in parser.metas if item.get("property", "").lower() == "og:url"]
        if len(canonical_values) != 1 or normalize_route(canonical_values[0] if canonical_values else "") != route:
            hard_samples["canonical"].append({"path": relative, "route": route, "values": canonical_values})
        else:
            canonicals.append(canonical_values[0])
            if relative in new_html and canonical_values[0] != DOMAIN + route:
                hard_samples["new_canonical_raw"].append({"path": relative, "expected": DOMAIN + route, "actual": canonical_values[0]})
        if len(og_values) != 1 or og_values != canonical_values:
            hard_samples["og_url"].append({"path": relative, "canonical": canonical_values, "og": og_values})
        robots = [item.get("content", "") for item in parser.metas if item.get("name", "").lower() in {"robots", "googlebot", "naverbot", "yeti"}]
        if any("noindex" in value.lower() for value in robots):
            hard_samples["noindex"].append(relative)
        if relative == PARENT_REL and (
            "학년별학원" not in (parser.titles[0] if len(parser.titles) == 1 else "")
            or "학년별학원" not in (parser.h1s[0] if len(parser.h1s) == 1 else "")
        ):
            hard_samples["parent_title_h1_structure"].append({"title": parser.titles, "h1": parser.h1s})
        if relative == CATEGORY_REL and (
            "중3" not in (parser.titles[0] if len(parser.titles) == 1 else "")
            or "수학학원" not in (parser.titles[0] if len(parser.titles) == 1 else "")
            or "중3" not in (parser.h1s[0] if len(parser.h1s) == 1 else "")
            or "수학학원" not in (parser.h1s[0] if len(parser.h1s) == 1 else "")
        ):
            hard_samples["category_title_h1_structure"].append({"title": parser.titles, "h1": parser.h1s})

        fragment = nav_fragment(source_text)
        if fragment is None:
            hard_samples["nav_missing"].append(relative)
            entries: list[dict[str, str]] = []
        else:
            entries = nav_entries(fragment, route)
        grade = [item for item in entries if item["text"] == GRADE_LABEL]
        grade_links += len(grade)
        if len(grade) != 1 or grade[0]["route"] != PARENT_ROUTE:
            hard_samples["grade_nav_link"].append({"path": relative, "grade": grade})
        active = bool(grade and "active" in grade[0]["class"].split())
        if active:
            grade_active += 1
        should_active = relative in new_html
        if active != should_active:
            hard_samples["grade_nav_active"].append({"path": relative, "expected": should_active, "actual": active})
        menu = [item for item in entries if item["text"] != entries[0]["text"]] if entries else []
        if len(entries) != 9 or tuple(item["route"] for item in entries[1:]) != EXPECTED_NAV_TARGETS:
            hard_samples["nav_contract"].append({"path": relative, "entries": entries})

        for block in parser.ld_scripts:
            jsonld_blocks += 1
            try:
                json.loads(block)
            except Exception as exc:
                jsonld_errors += 1
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
            if tag not in {"img", "script", "link"}:
                continue
            if tag == "link" and attrs.get("rel", "").lower() not in {"stylesheet", "icon", "shortcut icon", "apple-touch-icon", "preload", "modulepreload"}:
                continue
            raw = attrs.get("src" if tag in {"img", "script"} else "href", "").strip()
            if not raw or raw.startswith(IGNORED_SCHEMES):
                continue
            target_url = urlsplit(urljoin(DOMAIN + route, html.unescape(raw)))
            if target_url.netloc.lower() not in HOSTS:
                continue
            path = unquote(target_url.path).lstrip("/")
            if not path:
                continue
            resource_refs[path] += 1
            resource_samples.setdefault(path, {"page": relative, "tag": tag, "value": raw})

    for code, values in hard_samples.items():
        audit.extend(code, values)
    audit.hard(len(canonicals) == FINAL_HTML_COUNT and len(set(canonicals)) == FINAL_HTML_COUNT, "canonical_cardinality", {"total": len(canonicals), "unique": len(set(canonicals))})
    audit.hard(grade_links == FINAL_HTML_COUNT, "grade_nav_total", {"expected": FINAL_HTML_COUNT, "actual": grade_links})
    audit.hard(grade_active == NEW_HTML_COUNT, "grade_nav_active_total", {"expected": NEW_HTML_COUNT, "actual": grade_active})
    audit.hard(jsonld_errors == 0, "jsonld_syntax_total", jsonld_errors)

    # Existing documents may change only inside the shared nav element.
    preservation_errors: list[Any] = []
    nav_preservation_errors: list[Any] = []
    old_relatives = baseline_paths(root, "*.html")
    baseline_documents = git_blobs_batch(root, old_relatives)
    for relative in old_relatives:
        current = parsed.get(relative)
        if current is None:
            continue
        current_source = current[0]
        baseline_source = bytes(baseline_documents[relative]).decode("utf-8")
        if relative == "index.html":
            root_ok, root_detail = validate_root_schema_exception(baseline_source, current_source)
            if not root_ok:
                preservation_errors.append({"path": relative, "detail": root_detail})
            else:
                audit.observations["root_schema_exception"] = root_detail
        elif strip_nav(current_source) != strip_nav(baseline_source):
            preservation_errors.append(relative)
        base_fragment = nav_fragment(baseline_source)
        final_fragment = nav_fragment(current_source)
        if base_fragment and final_fragment:
            base_entries = nav_entries(base_fragment, route_for_relative(relative))
            final_entries = [item for item in nav_entries(final_fragment, route_for_relative(relative)) if item["text"] != GRADE_LABEL]
            if base_entries != final_entries:
                nav_preservation_errors.append(relative)
    audit.extend("non_target_outside_nav_preservation", preservation_errors)
    audit.extend("non_target_existing_nav_preservation", nav_preservation_errors)

    # Parent/category hooks and link/card contracts.
    parent_source, parent_parser = parsed.get(PARENT_REL, ("", DocumentParser()))
    category_source, category_parser = parsed.get(CATEGORY_REL, ("", DocumentParser()))
    audit.hard(len(find_main(parent_parser, **{"data-grade-directory": "parent"})) == 1, "parent_main_hook")
    audit.hard(len(find_main(category_parser, **{"data-grade-directory": "middle3-math"})) == 1, "category_main_hook")
    validate_hub_faq(parent_source, parent_parser, PARENT_REL, audit)
    validate_hub_faq(category_source, category_parser, CATEGORY_REL, audit)
    parent_targets = [normalize_route(item.get("href", ""), base_route=PARENT_ROUTE) for item in parent_parser.anchors]
    audit.hard(parent_targets.count(CATEGORY_ROUTE) == 1, "parent_category_link", parent_targets.count(CATEGORY_ROUTE))
    for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
        audit.hard(len(data_nodes(category_parser, hook)) == 1, "category_hook_" + hook.removeprefix("data-"), len(data_nodes(category_parser, hook)))
    cards = data_nodes(category_parser, "data-grade-locality")
    card_names = [attrs.get("data-grade-locality", "") for _, attrs in cards]
    audit.hard(len(cards) == NEW_DETAIL_COUNT and len(set(card_names)) == NEW_DETAIL_COUNT, "category_card_count", {"total": len(cards), "unique": len(set(card_names))})
    audit.hard(card_names == list(source.localities), "category_card_zip_order", {"expected_first": list(source.localities[:5]), "actual_first": card_names[:5]})
    category_links = Counter(normalize_route(item.get("href", ""), base_route=CATEGORY_ROUTE) for item in category_parser.anchors)
    expected_detail_routes = [route_for_relative(relative) for relative in expected_new_html(source)[2:]]
    audit.hard(all(category_links[route] == 1 for route in expected_detail_routes), "category_detail_links", {"missing_or_duplicate": [route for route in expected_detail_routes if category_links[route] != 1][:30]})

    for locality, relative in zip(source.localities, expected_new_html(source)[2:]):
        current = parsed.get(relative)
        if current is None:
            continue
        source_text, parser = current
        route = route_for_relative(relative)
        mains = [data for tag, data in parser.starts if tag == "main" and data.get("data-grade-page") == "middle3-math"]
        status = mains[0].get("data-source-status", "") if len(mains) == 1 else ""
        if len(mains) != 1 or status not in {"supported", "unconfirmed-grade"}:
            hard_samples["detail_main_hook"].append({"path": relative, "mains": mains})
        school_nodes = [data for _, data in data_nodes(parser, "data-source-field", "middle-schools")]
        blank_school = any(data.get("data-source-status") == "missing" for data in school_nodes)
        source_fields = Counter(data.get("data-source-field", "") for _, data in data_nodes(parser, "data-source-field"))
        expected_source_fields = Counter({"grade": 1, "middle-schools": 1, "address": 1, "registration": 1, "fee": 1})
        if source_fields != expected_source_fields:
            hard_samples["detail_source_field_contract"].append({"path": relative, "expected": expected_source_fields, "actual": source_fields})
        if len(school_nodes) != 1 or school_nodes[0].get("data-source-status") not in {"provided", "missing"}:
            hard_samples["detail_middle_schools_source_node"].append({"path": relative, "nodes": school_nodes})
        school_fact = re.search(
            r'<div\b(?=[^>]*\bdata-source-field=["\']middle-schools["\'])[^>]*>(.*?)</div\s*>',
            source_text,
            re.I | re.S,
        )
        school_chips = (
            [strip_tags(value) for value in re.findall(r"<span\b[^>]*>(.*?)</span\s*>", school_fact.group(1), re.I | re.S)]
            if school_fact
            else []
        )
        school_chip_total += len(school_chips)
        school_node_status = school_nodes[0].get("data-source-status") if len(school_nodes) == 1 else ""
        if (
            school_fact is None
            or any(not value for value in school_chips)
            or len(school_chips) != len(set(school_chips))
            or (school_node_status == "provided" and not school_chips)
            or (school_node_status == "missing" and school_chips)
        ):
            hard_samples["detail_middle_school_chip_contract"].append(
                {"path": relative, "status": school_node_status, "chips": school_chips}
            )
        if len(data_nodes(parser, "data-manuscript")) != 1:
            hard_samples["detail_manuscript"] .append(relative)
        sections = data_nodes(parser, "data-manuscript-section")
        section_ids = [attrs.get("data-manuscript-section", "") for _, attrs in sections]
        if len(sections) != 6 or len(set(section_ids)) != 6 or not all(section_ids):
            hard_samples["detail_manuscript_sections"].append({"path": relative, "count": len(sections), "values": section_ids})
        if len(data_nodes(parser, "data-faq")) != 1:
            hard_samples["detail_faq"].append(relative)
        if len(data_nodes(parser, "data-review")) != 1:
            hard_samples["detail_review"].append(relative)
        manuscript_match = re.search(r"<article\b(?=[^>]*\bdata-manuscript(?:\s*=|\s|>))[^>]*>.*?</article\s*>", source_text, re.I | re.S)
        if manuscript_match and DANGEROUS_MANUSCRIPT_RE.search(manuscript_match.group(0)):
            hard_samples["detail_manuscript_unsafe"].append(relative)

        role_images = {role: [attrs for attrs in parser.images if attrs.get("data-image-role") == role] for role in ("body", "map")}
        image_roles = Counter(attrs.get("data-image-role", "") for attrs in parser.images)
        image_role_order = [attrs.get("data-image-role", "") for attrs in parser.images]
        if (
            len(parser.images) != 2
            or image_roles != Counter({"body": 1, "map": 1})
            or image_role_order != ["body", "map"]
        ):
            hard_samples["detail_image_dom_contract"].append(
                {"path": relative, "count": len(parser.images), "roles": image_roles, "order": image_role_order}
            )
        for role, images in role_images.items():
            if len(images) != 1:
                hard_samples["detail_image_role"].append({"path": relative, "role": role, "count": len(images)})
                continue
            image = images[0]
            expected_loading = "eager" if role == "body" else "lazy"
            valid_dimension = all(str(image.get(key, "")).isdigit() and int(image[key]) > 0 for key in ("width", "height"))
            hidden = "hidden" in image or image.get("aria-hidden", "").lower() == "true" or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", image.get("style", ""), re.I))
            if image.get("loading") != expected_loading or image.get("decoding") != "async" or not valid_dimension or hidden or not image.get("alt", "").strip():
                hard_samples["detail_image_attributes"].append({"path": relative, "role": role, "attrs": image})
            if role == "body" and image.get("fetchpriority") != "high":
                hard_samples["detail_body_fetchpriority"].append({"path": relative, "attrs": image})
        representative_dom = [attrs for attrs in parser.images if attrs.get("data-image-role") == "representative"]
        if representative_dom:
            hard_samples["detail_representative_dom"] .append(relative)
        og_images = [item.get("content", "") for item in parser.metas if item.get("property", "").lower() == "og:image"]
        twitter_images = [
            item.get("content", "")
            for item in parser.metas
            if item.get("name", item.get("property", "")).lower() == "twitter:image"
        ]
        schemas: list[Any] = []
        for block in parser.ld_scripts:
            try:
                schemas.append(json.loads(block))
            except Exception:
                pass
        schema_images: set[str] = set()
        schema_nodes: list[Mapping[str, Any]] = []
        for schema in schemas:
            schema_images |= recursive_image_urls(schema)
            if isinstance(schema, Mapping):
                graph_value = schema.get("@graph", ())
                if isinstance(graph_value, list):
                    schema_nodes.extend(item for item in graph_value if isinstance(item, Mapping))
                else:
                    schema_nodes.append(schema)
        articles = [node for node in schema_nodes if node.get("@type") == "Article" or isinstance(node.get("@type"), list) and "Article" in node.get("@type", [])]
        image_objects = [node for node in schema_nodes if node.get("@type") == "ImageObject" or isinstance(node.get("@type"), list) and "ImageObject" in node.get("@type", [])]
        schema_exact = bool(
            len(og_images) == 1
            and len(articles) == 1
            and articles[0].get("image") == og_images[0]
            and len(image_objects) == 1
            and image_objects[0].get("url") == og_images[0]
            and image_objects[0].get("contentUrl") == og_images[0]
        )
        if len(og_images) != 1 or len(twitter_images) != 1 or og_images[0] not in schema_images or twitter_images != og_images or not schema_exact:
            hard_samples["detail_representative_parity"].append({"path": relative, "og": og_images, "twitter": twitter_images, "schema_images": sorted(schema_images)[:20]})
        if og_images:
            representative = urlsplit(urljoin(DOMAIN + route, og_images[0]))
            representative_key = (representative.netloc.lower(), unquote(representative.path))
            percent_safe_path = quote(unquote(representative.path), safe="/")
            if (
                representative.scheme != "https"
                or representative.netloc.lower() != "wawa-center.kr"
                or representative.query
                or representative.fragment
                or representative.path != percent_safe_path
            ):
                hard_samples["detail_representative_url_contract"].append(
                    {"path": relative, "url": og_images[0], "normalized_path": percent_safe_path}
                )
            dom_keys = set()
            for attrs in parser.images:
                dom_value = urlsplit(urljoin(DOMAIN + route, attrs.get("src", "")))
                dom_keys.add((dom_value.netloc.lower(), unquote(dom_value.path)))
            if representative_key in dom_keys:
                hard_samples["detail_representative_hidden_dom"].append(relative)
            representative_relative = unquote(representative.path).lstrip("/")
            if representative.netloc.lower() not in HOSTS or representative_relative not in filesystem_files:
                hard_samples["detail_representative_local_file"].append({"path": relative, "url": og_images[0]})
        if len(parser.h1s) == 1 and (locality not in parser.h1s[0] or "중3" not in parser.h1s[0] or "수학학원" not in parser.h1s[0]):
            hard_samples["detail_h1_structure"].append({"path": relative, "h1": parser.h1s[0]})
        if len(parser.titles) == 1 and (locality not in parser.titles[0] or "중3" not in parser.titles[0] or "수학학원" not in parser.titles[0]):
            hard_samples["detail_title_structure"].append({"path": relative, "title": parser.titles[0]})
        details.append(DetailReport(relative, route, locality, status, blank_school))

    for code in (
        "detail_main_hook", "detail_manuscript", "detail_manuscript_sections", "detail_faq", "detail_review",
        "detail_manuscript_unsafe", "detail_image_role", "detail_image_dom_contract", "detail_image_attributes", "detail_body_fetchpriority",
        "detail_representative_dom", "detail_representative_parity", "detail_representative_hidden_dom", "detail_h1_structure",
        "detail_representative_local_file", "detail_representative_url_contract", "detail_title_structure",
        "detail_middle_schools_source_node",
        "detail_middle_school_chip_contract",
        "detail_source_field_contract",
    ):
        audit.extend(code, hard_samples[code])
    audit.hard(len(details) == NEW_DETAIL_COUNT, "detail_report_count", len(details))
    audit.hard(any(item.status == "supported" for item in details), "detail_supported_boundary")
    audit.hard(any(item.status == "unconfirmed-grade" for item in details), "detail_unsupported_boundary")
    audit.hard(any(item.blank_school for item in details), "detail_blank_school_boundary")
    audit.hard(
        school_chip_total == EXPECTED_SCHOOL_CHIPS,
        "detail_middle_school_chip_total",
        {"expected": EXPECTED_SCHOOL_CHIPS, "actual": school_chip_total},
    )

    missing_resources: list[Any] = []
    for resource, count in resource_refs.items():
        exists = resource in documents or resource in filesystem_files
        if not exists:
            missing_resources.append({"resource": resource, "count": count, "sample": resource_samples[resource]})
    audit.extend("missing_local_resource", missing_resources)
    audit.hard(not missing_resources, "missing_local_resource_total", len(missing_resources))

    expected_broken = Counter({KNOWN_BASELINE_BROKEN_ROUTE: KNOWN_BASELINE_BROKEN_OCCURRENCES})
    audit.hard(broken == expected_broken, "internal_link_regression", {"expected": expected_broken, "actual": broken, "samples": broken_samples})
    distances: dict[str, int] = {"/": 0}
    queue: deque[str] = deque(["/"])
    while queue:
        current = queue.popleft()
        for target in graph[current]:
            if target not in distances:
                distances[target] = distances[current] + 1
                queue.append(target)
    orphans = sorted(set(route_to_relative) - set(distances))
    audit.hard(not orphans, "orphan_routes", [route_to_relative[route] for route in orphans[:30]])
    audit.hard(max(distances.values(), default=0) <= 4, "internal_link_max_depth", max(distances.values(), default=0))
    audit.hard(distances.get(PARENT_ROUTE) == 1, "parent_link_depth", distances.get(PARENT_ROUTE))
    audit.hard(distances.get(CATEGORY_ROUTE) == 2, "category_link_depth", distances.get(CATEGORY_ROUTE))
    audit.hard(all(distances.get(route) == 3 for route in expected_detail_routes), "detail_link_depth", {"bad": [(route, distances.get(route)) for route in expected_detail_routes if distances.get(route) != 3][:30]})

    audit.observations["documents"] = {
        "html": len(all_html),
        "canonical_total": len(canonicals),
        "canonical_unique": len(set(canonicals)),
        "grade_nav_links": grade_links,
        "grade_nav_active": grade_active,
        "jsonld_blocks": jsonld_blocks,
        "jsonld_errors": jsonld_errors,
        "detail_status": Counter(item.status for item in details),
        "blank_school_details": sum(item.blank_school for item in details),
        "middle_school_chips": school_chip_total,
    }
    audit.observations["links"] = {
        "edges": sum(len(values) for values in graph.values()),
        "broken": broken,
        "reachable": len(distances),
        "orphans": len(orphans),
        "max_depth": max(distances.values(), default=0),
        "depths": Counter(distances.values()),
    }
    audit.observations["resources"] = {
        "references": sum(resource_refs.values()),
        "unique": len(resource_refs),
        "missing": len(missing_resources),
    }
    return details


def validate_git_scope(root: Path, all_html: list[str], new_html: set[str], audit: Audit) -> None:
    expected = set(all_html) | {
        SITEMAP_REL,
        HEADER_CSS_REL,
        LLMS_REL,
        GENERATOR_REL,
        CONTENT_AUDITOR_REL,
        TECHNICAL_AUDITOR_REL,
    }
    diff = run_git(root, ["diff", "--name-only", "-z", BASELINE_COMMIT, "--"])
    changed = {part.decode("utf-8") for part in diff.split(b"\0") if part}
    untracked = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    changed |= {part.decode("utf-8") for part in untracked.split(b"\0") if part}
    audit.hard(changed == expected, "git_exact_change_scope", {"expected_count": len(expected), "actual_count": len(changed), "missing": sorted(expected - changed)[:30], "extra": sorted(changed - expected)[:30]})
    audit.hard(len(changed) == RELEASE_CHANGE_COUNT, "git_change_count", {"expected": RELEASE_CHANGE_COUNT, "actual": len(changed)})
    diff_check = subprocess.run(["git", "diff", "--check", BASELINE_COMMIT, "--"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    audit.hard(diff_check.returncode == 0, "git_diff_check", (diff_check.stdout + diff_check.stderr).decode("utf-8", "replace")[-3000:])
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"], cwd=root, check=False)
    audit.hard(ancestor.returncode == 0, "baseline_is_ancestor")
    for relative in baseline_paths(root):
        if relative in expected and relative not in new_html and relative not in {GENERATOR_REL, CONTENT_AUDITOR_REL, TECHNICAL_AUDITOR_REL}:
            audit.hard((root / PurePosixPath(relative)).exists(), "baseline_file_not_deleted", relative)
    security_errors: list[Any] = []
    for relative in sorted(changed):
        path = root / PurePosixPath(relative)
        if path.is_symlink():
            security_errors.append({"path": relative, "reason": "symlink"})
            continue
        if path.is_file():
            value = path.read_bytes()
            if len(value) > 50_000_000:
                security_errors.append({"path": relative, "reason": "oversize", "bytes": len(value)})
            if path.suffix.lower() in {".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi"}:
                security_errors.append({"path": relative, "reason": "executable"})
            text = value.decode("utf-8", "ignore")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    security_errors.append({"path": relative, "reason": "secret-pattern", "pattern": pattern.pattern[:60]})
    audit.extend("release_security", security_errors)
    residue: set[str] = set()
    for pattern in TRANSACTION_PATTERNS:
        for path in root.rglob(pattern):
            if any(part in PRUNED_DIRS for part in path.relative_to(root).parts):
                continue
            residue.add(path.relative_to(root).as_posix())
    audit.hard(not residue, "transaction_residue", sorted(residue)[:30])
    audit.observations["git_scope"] = {
        "expected": len(expected),
        "actual": len(changed),
        "baseline_html_modified": len((set(all_html) - new_html) & changed),
        "new_html": len(new_html & changed),
        "extra": sorted(changed - expected),
    }


def select_browser_cases(details: Sequence[DetailReport], source: SourceIndex, audit: Audit) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = [
        {"kind": "parent", "route": PARENT_ROUTE, "relative": PARENT_REL},
        {"kind": "category", "route": CATEGORY_ROUTE, "relative": CATEGORY_REL},
    ]
    used: set[str] = set()

    def choose(kind: str, predicate: Any) -> None:
        candidates = [item for item in details if item.route not in used and predicate(item)]
        audit.hard(bool(candidates), "browser_case_" + kind)
        if candidates:
            item = candidates[0]
            used.add(item.route)
            cases.append({"kind": kind, "route": item.route, "relative": item.relative, "locality": item.locality, "status": item.status})

    choose("supported", lambda item: item.status == "supported" and not item.blank_school)
    choose("unsupported", lambda item: item.status == "unconfirmed-grade" and not item.blank_school)
    choose("blank-school", lambda item: item.blank_school)
    choose("space-route", lambda item: " " in item.locality)
    max_length = max((len(item.locality) for item in details), default=0)
    choose("longest", lambda item: len(item.locality) == max_length)
    audit.hard(len(cases) == 7 and len({item["route"] for item in cases}) == 7, "browser_case_cardinality", cases)
    audit.observations["browser_cases"] = cases
    return cases


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
            raw = json.loads((path / "playwright" / "package.json").read_text("utf-8"))
            return tuple(int(part) for part in re.findall(r"\d+", str(raw.get("version", "0")))[:3])
        except Exception:
            return (0,)

    return str(max(set(candidates), key=version))


def find_node() -> str | None:
    direct = shutil.which("node")
    if direct:
        return direct
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [*local.glob("Microsoft/WinGet/Packages/OpenJS.NodeJS*/node-*-win-x64/node.exe")]
    existing = [path for path in candidates if path.is_file()]
    return str(max(existing, key=lambda path: path.stat().st_mtime_ns)) if existing else None


def run_browser(base: str, cases: Sequence[Mapping[str, str]], timeout: int) -> dict[str, Any]:
    node_path = find_playwright_node_path()
    node = find_node()
    if node_path is None or node is None:
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": "playwright or node not found"}
    payload = base64.b64encode(json.dumps({"base": base.rstrip("/"), "domain": DOMAIN, "cases": list(cases), "widths": BROWSER_WIDTHS}, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = r'''
const {chromium}=require('playwright');
const cfg=JSON.parse(Buffer.from(process.argv[1],'base64').toString('utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true}); const rows=[]; let hubTests=0;
 for(const item of cfg.cases){ for(const width of cfg.widths){
  const context=await browser.newContext({viewport:{width,height:900},locale:'ko-KR'});
  const page=await context.newPage(); const consoleErrors=[],pageErrors=[],network=[];
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
  page.on('pageerror',e=>pageErrors.push(String(e)));
  page.on('requestfailed',r=>network.push('FAIL '+r.url()+' '+(r.failure()?.errorText||'')));
  page.on('response',r=>{if(r.status()>=400)network.push(r.status()+' '+r.url())});
  let responseStatus=0,navigationError='';
  try{const response=await page.goto(cfg.base+item.route,{waitUntil:'networkidle',timeout:45000});responseStatus=response?response.status():0;await page.waitForTimeout(150)}catch(e){navigationError=String(e)}
  if(!['parent','category'].includes(item.kind)){
   for(const role of ['body','map']){const image=page.locator(`[data-image-role="${role}"]`);if(await image.count()===1){try{await image.scrollIntoViewIfNeeded({timeout:3000});await page.waitForFunction(r=>{const e=document.querySelector(`[data-image-role="${r}"]`);return !!e&&e.complete&&e.naturalWidth>0},role,{timeout:10000})}catch{}}}
  }
  const state=await page.evaluate(({item,domain,width})=>{
   const visible=e=>{if(!e)return false;const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&!e.hidden&&r.width>0&&r.height>0};
   const nav=[...document.querySelectorAll('.site-header .nav-links a')]; const rects=nav.map(e=>e.getBoundingClientRect());
   const overlaps=[]; for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++){const a=rects[i],b=rects[j];if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.5&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.5)overlaps.push([i,j]);}
   const rows=[...new Set(rects.map(r=>Math.round(r.top)))]; const rowCounts=rows.map(top=>rects.filter(r=>Math.abs(Math.round(r.top)-top)<=1).length);
   const grade=nav.filter(a=>(a.textContent||'').replace(/\s+/g,' ').trim()==='학년별학원');
   const canonical=[...document.querySelectorAll('link[rel~="canonical"]')].map(e=>e.href);
   const robots=[...document.querySelectorAll('meta[name="robots" i],meta[name="googlebot" i],meta[name="naverbot" i],meta[name="yeti" i]')].map(e=>e.content||'');
   const header=document.querySelector('.site-header'); const headerRect=header?.getBoundingClientRect();
   const imgs=[...document.images].map(e=>({src:e.currentSrc||e.src,complete:e.complete,naturalWidth:e.naturalWidth,visible:visible(e),role:e.dataset.imageRole||''}));
   const main=document.querySelector('main');
   const faqSections=[...document.querySelectorAll('[data-faq]')]; const faqDetails=faqSections.length===1?[...faqSections[0].querySelectorAll('details')]:[];
   return {title:document.title,h1:document.querySelectorAll('h1').length,canonical,expectedCanonical:domain+item.route,noindex:robots.some(x=>/noindex/i.test(x)),overflow:document.documentElement.scrollWidth>innerWidth+1,navCount:nav.length,gradeCount:grade.length,gradeActive:grade.length===1&&grade[0].classList.contains('active'),navRows:rows.length,rowCounts,overlaps,navBounds:rects.filter(r=>r.left<-1||r.right>innerWidth+1).length,headerHeight:headerRect?.height||0,expectedMobile:width<=1120,mainGradeDirectory:main?.dataset.gradeDirectory||'',mainGradePage:main?.dataset.gradePage||'',mainSourceStatus:main?.dataset.sourceStatus||'',hubFaqCount:faqSections.length,hubFaqVisible:faqSections.length===1&&visible(faqSections[0]),hubFaqDetails:faqDetails.length,images:imgs,roleImages:imgs.filter(x=>x.role==='body'||x.role==='map')};
  },{item,domain:cfg.domain,width});
  const failures=[]; if(responseStatus!==200)failures.push('http'); if(navigationError)failures.push('navigation'); if(consoleErrors.length)failures.push('console'); if(pageErrors.length)failures.push('pageerror'); if(network.length)failures.push('network');
  if(state.h1!==1||state.canonical.length!==1||state.canonical[0]!==state.expectedCanonical||state.noindex)failures.push('seo');
  if(state.overflow||state.navCount!==8||state.gradeCount!==1||!state.gradeActive||state.overlaps.length||state.navBounds)failures.push('nav');
  if(state.expectedMobile){if(state.navRows!==2||state.rowCounts.slice().sort().join(',')!=='4,4'||Math.abs(state.headerHeight-132)>2)failures.push('mobile-layout')}else{if(state.navRows!==1||state.rowCounts[0]!==8||Math.abs(state.headerHeight-72)>2)failures.push('desktop-layout')}
  if(item.kind==='parent'&&state.mainGradeDirectory!=='parent')failures.push('parent-hook'); if(item.kind==='category'&&state.mainGradeDirectory!=='middle3-math')failures.push('category-hook');
  if(['parent','category'].includes(item.kind)&&(state.hubFaqCount!==1||!state.hubFaqVisible||state.hubFaqDetails!==2))failures.push('hub-faq');
  if(!['parent','category'].includes(item.kind)){if(state.mainGradePage!=='middle3-math'||state.mainSourceStatus!==item.status)failures.push('detail-hook');if(state.roleImages.length!==2||state.roleImages.some(x=>!x.complete||x.naturalWidth<=0||!x.visible))failures.push('images')}
  let hub=null;
  if(item.kind==='category'){
   hubTests++;
   hub=await page.evaluate(async()=>{const input=document.querySelector('[data-grade-search]'),clear=document.querySelector('[data-grade-clear]'),status=document.querySelector('[data-grade-status]'),cards=[...document.querySelectorAll('[data-grade-locality]')],visible=e=>{const s=getComputedStyle(e);return !e.hidden&&s.display!=='none'&&s.visibility!=='hidden'};const initial={visible:cards.filter(visible).length,status:(status?.textContent||'').replace(/\s+/g,' ').trim()};input.focus();input.value='명일동';input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,120));const filtered={visible:cards.filter(visible).length,names:cards.filter(visible).map(e=>e.getAttribute('data-grade-locality'))};clear.click();await new Promise(r=>setTimeout(r,120));return {initial,filtered,reset:{visible:cards.filter(visible).length,status:(status?.textContent||'').replace(/\s+/g,' ').trim(),value:input.value,focused:document.activeElement===input}};});
   if(hub.initial.visible!==371||hub.filtered.visible!==1||hub.filtered.names[0]!=='명일동'||hub.reset.visible!==371||hub.reset.value!==''||hub.reset.status!==hub.initial.status||!hub.reset.focused)failures.push('hub-search');
  }
  rows.push({kind:item.kind,route:item.route,width,responseStatus,navigationError,consoleErrors,pageErrors,network,state,hub,failures}); await context.close();
 }} await browser.close(); const failed=rows.filter(row=>row.failures.length); console.log(JSON.stringify({tests:rows.length,hub_tests:hubTests,failures:failed.length,failureRows:failed.slice(0,30),rows}));
})().catch(e=>{console.error(e);process.exit(1)});
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
        return {"tests": 0, "hub_tests": 0, "failures": 1, "error": f"invalid browser JSON: {exc}: {result.stdout[-2000:]!r}"}


def validate_baseline(root: Path, audit: Audit) -> None:
    head = run_git(root, ["rev-parse", BASELINE_COMMIT]).decode().strip()
    tree = run_git(root, ["rev-parse", f"{BASELINE_COMMIT}^{{tree}}"]).decode().strip()
    audit.hard(head == BASELINE_COMMIT, "baseline_commit")
    audit.hard(tree == BASELINE_TREE, "baseline_tree", {"expected": BASELINE_TREE, "actual": tree})
    html_paths = [path.relative_to(root).as_posix() for path in root.rglob("index.html") if not any(part in PRUNED_DIRS for part in path.relative_to(root).parts)]
    audit.hard(len(html_paths) == BASELINE_HTML_COUNT, "baseline_html_count", len(html_paths))
    feature = root / PARENT_REL
    audit.hard(not feature.exists(), "baseline_feature_absent_tree", str(feature))
    sitemap = fs_bytes(root, SITEMAP_REL)
    if sitemap is not None:
        _, rows, _ = parse_sitemap(sitemap, "baseline_worktree_sitemap", audit)
        audit.hard(len(rows) == BASELINE_HTML_COUNT and len({loc for loc, _ in rows}) == BASELINE_HTML_COUNT, "baseline_worktree_sitemap_count", len(rows))
        audit.hard(not any(normalize_route(loc) == PARENT_ROUTE for loc, _ in rows), "baseline_feature_absent_sitemap")
    nav_hits = 0
    for relative in html_paths:
        value = fs_bytes(root, relative)
        if value is None:
            continue
        try:
            fragment = nav_fragment(value.decode("utf-8"))
        except UnicodeDecodeError:
            fragment = None
        if fragment:
            nav_hits += sum(item["text"] == GRADE_LABEL for item in nav_entries(fragment, route_for_relative(relative)))
    audit.hard(nav_hits == 0, "baseline_feature_absent_nav", nav_hits)
    audit.hold(False, "feature_absent", {"new_html": 0, "expected_new_html": NEW_HTML_COUNT})
    audit.observations["baseline"] = {"html": len(html_paths), "nav_grade_links": nav_hits, "sitemap": BASELINE_HTML_COUNT, "expected_release_html": FINAL_HTML_COUNT}


def self_test(audit: Audit) -> None:
    audit.hard(route_for_relative("index.html") == "/", "selftest_root_route")
    batch = git_blobs_batch(ROOT, ("index.html", "robots.txt"))
    audit.hard(
        all(bytes(batch[path]) == git_blob(ROOT, path) for path in batch),
        "selftest_git_batch_communicate",
    )
    sitemap_old = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url>\n    <loc>https://wawa-center.kr/</loc>\n    <lastmod>2026-08-04</lastmod>\n  </url>\n'
        '</urlset>\n'
    )
    sitemap_appended = sitemap_old.replace(
        "</urlset>",
        '  <url>\n    <loc>https://wawa-center.kr/new/</loc>\n    <lastmod>2026-08-20</lastmod>\n  </url>\n</urlset>',
    )
    sitemap_mutated = sitemap_appended.replace("2026-08-04", "2026-08-05", 1)
    _, _, old_blocks = parse_sitemap(sitemap_old.encode("utf-8"), "selftest_sitemap_old", audit)
    _, _, appended_blocks = parse_sitemap(sitemap_appended.encode("utf-8"), "selftest_sitemap_append", audit)
    _, _, mutated_blocks = parse_sitemap(sitemap_mutated.encode("utf-8"), "selftest_sitemap_mutation", audit)
    audit.hard(
        len(old_blocks) == 1 and appended_blocks[:1] == old_blocks,
        "selftest_sitemap_append_boundary_positive",
        {"old": old_blocks, "appended": appended_blocks[:1]},
    )
    audit.hard(
        len(mutated_blocks) == 2 and mutated_blocks[:1] != old_blocks,
        "selftest_sitemap_append_boundary_negative",
    )
    relative = f"{GRADE_PARENT}/{GRADE_CATEGORY}/부천 상동/index.html"
    route = route_for_relative(relative)
    audit.hard("%20" in route and normalize_route(DOMAIN + route) == route, "selftest_space_route", route)
    source = '<nav class="nav"><a class="logo" href="/">브랜드</a><div class="nav-links"><a href="/x/">X</a><a class="active" href="/학년별학원/">학년별학원</a></div></nav>'
    entries = nav_entries(nav_fragment(source) or "", "/")
    audit.hard(len(entries) == 3 and entries[-1]["route"] == PARENT_ROUTE and "active" in entries[-1]["class"], "selftest_nav", entries)
    heading_parser = DocumentParser()
    heading_parser.feed("<h1>첫 줄<br>둘째 줄</h1><p>제외할 본문</p>")
    heading_parser.close()
    audit.hard(heading_parser.h1s == ["첫 줄둘째 줄"], "selftest_void_heading_depth", heading_parser.h1s)
    unsafe = '<article data-manuscript><p>ok</p><script>alert(1)</script></article>'
    audit.hard(bool(DANGEROUS_MANUSCRIPT_RE.search(unsafe)), "selftest_dangerous_manuscript")
    faq_entities = [
        {"@type": "Question", "name": "질문 하나?", "acceptedAnswer": {"@type": "Answer", "text": "답변 하나."}},
        {"@type": "Question", "name": "질문 둘?", "acceptedAnswer": {"@type": "Answer", "text": "답변 둘."}},
    ]
    faq_source = (
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@graph": [{"@type": "FAQPage", "mainEntity": faq_entities}]}, ensure_ascii=False)
        + '</script><section><div data-faq><details><summary>질문 하나?</summary><p>답변 하나.</p></details>'
        '<details><summary>질문 둘?</summary><p>답변 둘.</p></details></div></section>'
    )
    faq_parser = DocumentParser()
    faq_parser.feed(faq_source)
    faq_parser.close()
    faq_audit = Audit()
    validate_hub_faq(faq_source, faq_parser, "selftest.html", faq_audit)
    audit.hard(not faq_audit.errors, "selftest_hub_faq", faq_audit.errors)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only technical/release gate for wawa-center.kr grade-3 math pages")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--zip-path", type=Path)
    parser.add_argument("--common-dir", type=Path)
    parser.add_argument("--generator", type=Path, default=Path(GENERATOR_REL))
    parser.add_argument("--content-auditor", type=Path, default=Path(CONTENT_AUDITOR_REL))
    parser.add_argument("--browser-base")
    parser.add_argument("--browser-timeout", type=int, default=600_000)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    audit = Audit()
    started = time.time()
    mode = "unknown"
    browser: dict[str, Any] | None = None

    if args.self_test:
        self_test(audit)
        mode = "self-test"
    elif args.baseline_only:
        validate_baseline(root, audit)
        mode = "baseline"
    else:
        release_before = tree_snapshot(root)
        release_status_before = run_git(root, ["status", "--porcelain=v1", "-z"])
        try:
            source = inspect_zip(discover_zip(args.zip_path), audit)
            common_dir = discover_common_dir(root, args.common_dir)
            validate_source_localities(root, source, audit)
            all_html, new_html, expected_documents = expected_plan_paths(root, source)
            audit.hard(len(all_html) == FINAL_HTML_COUNT, "expected_html_count", len(all_html))
            audit.hard(len(new_html) == NEW_HTML_COUNT, "expected_new_html_count", len(new_html))
            audit.hard(len(expected_documents) == PLAN_DOCUMENT_COUNT, "expected_plan_document_count", len(expected_documents))
            generator = args.generator if args.generator.is_absolute() else root / args.generator
            content_auditor = args.content_auditor if args.content_auditor.is_absolute() else root / args.content_auditor
            audit.hard(generator.is_file(), "generator_missing", str(generator))
            projection = run_projection(root, generator.resolve(), source.zip_path, common_dir, expected_documents, audit) if generator.is_file() else None
            pin_inputs(
                root,
                projection,
                source,
                generator.resolve(),
                content_auditor.resolve(),
                audit,
            )
            if projection is not None:
                mode = "actual" if not projection.changed_paths else "projected"
                validate_header_css(root, projection.documents.get(HEADER_CSS_REL, b""), audit)
                validate_llms(root, projection.documents.get(LLMS_REL, b""), audit)
                validate_sitemap(root, projection.documents.get(SITEMAP_REL, b""), all_html, expected_new_html(source), audit)
                details = audit_documents(root, projection.documents, all_html, new_html, source, audit)
                cases = select_browser_cases(details, source, audit)
                if mode == "actual":
                    validate_git_scope(root, all_html, new_html, audit)
                    audit.hard(bool(args.browser_base), "actual_browser_required", "pass --browser-base for materialized release")
                    if args.browser_base:
                        if audit.errors:
                            audit.hard(False, "browser_skipped_static_errors", {"pre_browser_errors": len(audit.errors)})
                        else:
                            browser = run_browser(args.browser_base, cases, args.browser_timeout)
                            audit.hard(browser.get("tests") == 56, "browser_test_count", {"expected": 56, "actual": browser.get("tests")})
                            audit.hard(browser.get("hub_tests") == 8, "browser_hub_test_count", {"expected": 8, "actual": browser.get("hub_tests")})
                            audit.hard(browser.get("failures") == 0, "browser_contract", {key: value for key, value in browser.items() if key != "rows"})
                elif args.browser_base:
                    audit.hard(False, "browser_requires_materialized_tree", mode)
            else:
                mode = "projection-failed"
        except Exception as exc:
            audit.hard(False, "audit_exception", f"{type(exc).__name__}: {exc}")
        finally:
            release_after = tree_snapshot(root)
            release_status_after = run_git(root, ["status", "--porcelain=v1", "-z"])
            audit.hard(release_before == release_after, "release_auditor_read_only", {"before": release_before, "after": release_after})
            audit.hard(release_status_before == release_status_after, "release_git_status_read_only")
            audit.observations["release_freeze"] = {"before": release_before, "after": release_after, "git_status_equal": release_status_before == release_status_after}

    status = "FAIL" if audit.errors else "HOLD" if audit.holds else "PASS"
    report = {
        "status": status,
        "ok": status == "PASS",
        "mode": mode,
        "error_count": len(audit.errors),
        "hold_count": len(audit.holds),
        "errors": audit.errors[:300],
        "holds": audit.holds,
        "observations": audit.observations,
        "browser": browser,
        "technical_auditor_sha256": sha256(Path(__file__).read_bytes()),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=lambda value: dict(value) if isinstance(value, Counter) else str(value)))
    return 1 if audit.errors else 2 if audit.holds else 0


if __name__ == "__main__":
    raise SystemExit(main())
