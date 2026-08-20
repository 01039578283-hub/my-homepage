#!/usr/bin/env python3
"""Build the wawa-center.kr middle-school grade 3 mathematics page set.

The attached ZIP is treated strictly as UTF-8 content data.  The default CLI is
read-only: it constructs and audits a complete in-memory plan.  Files are only
written when ``--apply --go APPLY-GO`` is supplied, through the recoverable
transaction implemented at the end of this module.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4
from zipfile import ZipFile


SITE_ORIGIN = "https://wawa-center.kr"
PUBLISHED_DATE = "2026-08-20"
ZIP_SHA256 = "93d58041e1a3672697ba083e7eb3dc7d65570703b68ab122b6cb00be24c6fbc6"
CENTER_CSV_SHA256 = "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a"
TARGET_SCHOOL_CSV_SHA256 = "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f"
EXPECTED_MANUSCRIPTS = 371
EXPECTED_EXISTING_HTML = 14_624
EXPECTED_NEW_HTML = 373
EXPECTED_FINAL_HTML = 14_997
EXPECTED_AUTHORIZED_DOCUMENTS = 15_000
EXPECTED_SUPPORTED = 358
EXPECTED_UNSUPPORTED = 13
EXPECTED_FAQS = 1_113
EXPECTED_MANUSCRIPT_H2 = 2_226
ABSENT_SHA256 = hashlib.sha256(b"wawa-grade3-math:absent-v1").hexdigest()

PARENT_REL = Path("학년별학원/index.html")
CATEGORY_REL = Path("학년별학원/중3수학학원/index.html")
HEADER_CSS_REL = Path("assets/header.css")
SITEMAP_REL = Path("sitemap.xml")
LLMS_REL = Path("llms.txt")
ROOT_REL = Path("index.html")
GRADE_NAV_HREF = "/학년별학원/"
LLMS_MARKER = "## 학년별학원 핵심 허브"
TRANSACTION_PREFIX = ".grade3-math-transaction-"

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SCRIPT_JSON_RE = re.compile(
    r"(<script\b[^>]*\btype=[\"']application/ld\+json[\"'][^>]*>)(.*?)(</script>)",
    re.IGNORECASE | re.DOTALL,
)
NAV_RE = re.compile(
    r"(<div\b[^>]*\bclass=[\"'][^\"']*\bnav-links\b[^\"']*[\"'][^>]*>)(.*?)(</div>)",
    re.IGNORECASE | re.DOTALL,
)
ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"\bhref\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
URL_BLOCK_RE = re.compile(r"<url>.*?</url>", re.DOTALL)
LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
LASTMOD_RE = re.compile(r"<lastmod>(.*?)</lastmod>", re.DOTALL)


class BuildError(RuntimeError):
    """Raised whenever a source, rendering, or transaction invariant fails."""


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
    review_disclaimer: str
    review_quote: str
    jsonld_summary: str
    raw_bytes: bytes
    raw_text: str


@dataclass(frozen=True)
class CenterRecord:
    locality: str
    locality_en: str
    region: str
    region_en: str
    city: str
    city_en: str
    center_name: str
    tuition_url: str
    registration_name: str
    registration_number: str
    address: str
    location_note: str
    elementary_schools: tuple[str, ...]
    middle_schools: tuple[str, ...]
    middle_school_source_tokens: tuple[str, ...]
    high_schools: tuple[str, ...]
    korean_grades: tuple[str, ...]
    english_grades: tuple[str, ...]
    math_grades: tuple[str, ...]
    science_grades: tuple[str, ...]
    social_grades: tuple[str, ...]

    @property
    def supports_middle3_math(self) -> bool:
        return "중3" in self.math_grades


@dataclass(frozen=True)
class PageAssets:
    representative_src: str
    representative_size: tuple[int, int]
    body_src: str
    body_size: tuple[int, int]
    map_src: str
    map_size: tuple[int, int]
    organization: Mapping[str, Any]
    local_business: Mapping[str, Any]
    center_url: str
    telephone: str


@dataclass(frozen=True)
class BuildPlan:
    """A fully materialized, root-relative write plan.

    ``authorized_documents`` deliberately contains every final document, not
    merely changed files.  Absence is represented by ``before_exists`` and a
    valid SHA-256 sentinel in ``before_manifest``.
    """

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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _as_bytes(value: str | bytes) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else value


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label}: UTF-8 decode failed: {exc}") from exc


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _json_script(value: Any) -> str:
    # Prevent a data string from terminating its script element.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _normalize_header(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r", "").replace("\n", "").strip()


def _split_csv_tokens(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    tokens = tuple(
        token
        for token in (unicodedata.normalize("NFC", part.strip()) for part in value.split(","))
        if token
    )
    if not tokens:
        raise BuildError(f"malformed CSV token list: {value!r}")
    # Pinned source rows occasionally repeat a school. A visible/schema list is
    # set-like, so preserve first occurrence order and never render duplicates.
    return tuple(dict.fromkeys(tokens))


def _split_csv_source_tokens(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    tokens = tuple(
        token
        for token in (
            unicodedata.normalize("NFC", part.strip())
            for part in re.split(r"[,/\.\s]+", value)
        )
        if token
    )
    unique = tuple(dict.fromkeys(tokens))
    if any(
        not re.fullmatch(r"[0-9A-Za-z가-힣·()\-]+", token)
        or not token.endswith(("중", "중학교"))
        for token in unique
    ):
        raise BuildError(f"unsafe middle-school token list: {value!r}")
    return unique


def _encoded_site_url(*parts: str) -> str:
    if not parts:
        return SITE_ORIGIN + "/"
    return SITE_ORIGIN + "/" + "/".join(quote(part, safe="") for part in parts) + "/"


def _detail_rel(locality: str) -> Path:
    return Path("학년별학원") / "중3수학학원" / locality / "index.html"


def _generic_math_rel(locality: str) -> Path:
    return Path("과목별학원") / "수학학원" / locality / "index.html"


def _safe_relative_path(root: Path, key: Path | str) -> Path:
    root_resolved = root.resolve()
    path = Path(key)
    if path.is_absolute():
        try:
            rel = path.resolve(strict=False).relative_to(root_resolved)
        except ValueError as exc:
            raise BuildError(f"override path escapes root: {key}") from exc
    else:
        rel = Path(os.path.normpath(str(path)))
    if rel == Path(".") or rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise BuildError(f"unsafe relative path: {key}")
    candidate = (root_resolved / rel).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise BuildError(f"path escapes root: {key}") from exc
    return rel


def _normalize_overrides(
    root: Path, overrides: Mapping[Path | str, str | bytes] | None
) -> dict[Path, str | bytes]:
    normalized: dict[Path, str | bytes] = {}
    for key, value in (overrides or {}).items():
        if not isinstance(value, (str, bytes)):
            raise BuildError(f"override value must be str or bytes: {key}")
        rel = _safe_relative_path(root, key)
        if rel in normalized:
            raise BuildError(f"duplicate normalized override path: {rel}")
        normalized[rel] = value
    return normalized


def _read_current_bytes(root: Path, rel: Path, overrides: Mapping[Path, str | bytes]) -> bytes:
    if rel in overrides:
        return _as_bytes(overrides[rel])
    path = root / rel
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise BuildError(f"required current document is missing: {rel}") from exc


def _read_optional_current_bytes(
    root: Path, rel: Path, overrides: Mapping[Path, str | bytes]
) -> tuple[bool, bytes]:
    if rel in overrides:
        return True, _as_bytes(overrides[rel])
    path = root / rel
    if path.is_file():
        return True, path.read_bytes()
    return False, b""


def _enumerate_html(root: Path, overrides: Mapping[Path, str | bytes]) -> set[Path]:
    paths: set[Path] = set()
    for path in root.rglob("index.html"):
        rel = path.relative_to(root)
        if any(part.startswith(TRANSACTION_PREFIX) for part in rel.parts):
            continue
        paths.add(rel)
    paths.update(rel for rel in overrides if rel.name == "index.html")
    return paths


def _validate_plain_text(text: str, label: str) -> int:
    controls = CONTROL_RE.findall(text)
    if controls:
        raise BuildError(f"{label}: contains {len(controls)} forbidden control characters")
    trailing = sum(1 for line in text.splitlines() if line.rstrip(" \t") != line)
    if trailing:
        raise BuildError(f"{label}: contains {trailing} lines with trailing whitespace")
    return trailing


def _parse_manuscript(member_name: str, raw: bytes) -> Manuscript:
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{member_name}: not strict UTF-8: {exc}") from exc
    bom = raw.startswith(b"\xef\xbb\xbf")
    reconstructed = (b"\xef\xbb\xbf" if bom else b"") + decoded.encode("utf-8")
    if reconstructed != raw:
        raise BuildError(f"{member_name}: raw UTF-8 round-trip failed")
    _validate_plain_text(decoded, member_name)
    text = decoded.replace("\r\n", "\n").replace("\r", "\n")
    labels = ("페이지타이틀", "메타설명", "본문", "FAQ", "학부모후기", "JSON-LD 요약")
    matches = list(re.finditer(r"(?m)^\[([^\]\n]+)\]\n", text))
    if tuple(match.group(1) for match in matches) != labels:
        raise BuildError(f"{member_name}: section labels/order are malformed")
    if text[: matches[0].start()].strip():
        raise BuildError(f"{member_name}: data before first section")
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        values[match.group(1)] = text[match.end() : end].strip("\n")
    if any(not values[label].strip() for label in labels):
        raise BuildError(f"{member_name}: empty required section")

    suffix = " 중3 수학학원.txt"
    if "/" in member_name or "\\" in member_name or not member_name.endswith(suffix):
        raise BuildError(f"unsafe or unexpected ZIP member name: {member_name}")
    locality = unicodedata.normalize("NFC", member_name[: -len(suffix)])
    title = values["페이지타이틀"].strip()
    if title != f"{locality} 중3 수학학원":
        raise BuildError(f"{member_name}: title does not match member locality")
    meta = values["메타설명"].strip()
    if "\n" in meta:
        raise BuildError(f"{member_name}: metadata must be one paragraph")

    body_blocks = [block.strip() for block in re.split(r"\n[ \t]*\n", values["본문"].strip())]
    intro: list[str] = []
    sections: list[BodySection] = []
    current_heading: str | None = None
    current_paragraphs: list[str] = []
    for block in body_blocks:
        if block.startswith("## "):
            if "\n" in block:
                raise BuildError(f"{member_name}: H2 block contains paragraph text")
            if current_heading is not None:
                if not current_paragraphs:
                    raise BuildError(f"{member_name}: H2 has no paragraph")
                sections.append(BodySection(current_heading, tuple(current_paragraphs)))
            current_heading = block[3:].strip()
            current_paragraphs = []
        elif current_heading is None:
            intro.append(block)
        else:
            current_paragraphs.append(block)
    if current_heading is not None:
        if not current_paragraphs:
            raise BuildError(f"{member_name}: final H2 has no paragraph")
        sections.append(BodySection(current_heading, tuple(current_paragraphs)))
    if not intro or len(sections) != 6 or any(not section.heading for section in sections):
        raise BuildError(f"{member_name}: expected intro and exactly six H2 sections")

    faq_blocks = [block.strip() for block in re.split(r"\n[ \t]*\n", values["FAQ"].strip())]
    faqs: list[FAQ] = []
    for block in faq_blocks:
        faq_match = re.fullmatch(r"Q([1-9][0-9]*)\.\s+(.+?)\nA\.\s+(.+)", block, re.DOTALL)
        if not faq_match:
            raise BuildError(f"{member_name}: malformed FAQ block")
        faqs.append(
            FAQ(
                number=int(faq_match.group(1)),
                question=faq_match.group(2).strip(),
                answer=faq_match.group(3).strip(),
            )
        )
    if [faq.number for faq in faqs] != [1, 2, 3]:
        raise BuildError(f"{member_name}: expected Q1/Q2/Q3 with A. answers")

    review_blocks = [block.strip() for block in re.split(r"\n[ \t]*\n", values["학부모후기"].strip())]
    if len(review_blocks) != 2 or not review_blocks[0].startswith("※"):
        raise BuildError(f"{member_name}: review must be disclaimer then quotation")
    review_quote = review_blocks[1]
    if not (review_quote.startswith("“") and review_quote.endswith("”")):
        raise BuildError(f"{member_name}: review quotation must preserve curly quotes")
    jsonld_summary = values["JSON-LD 요약"].strip()
    if "\n\n" in jsonld_summary:
        raise BuildError(f"{member_name}: JSON-LD summary must be one paragraph")
    return Manuscript(
        member_name=member_name,
        locality=locality,
        title=title,
        meta_description=meta,
        intro_paragraphs=tuple(intro),
        sections=tuple(sections),
        faqs=tuple(faqs),
        review_disclaimer=review_blocks[0],
        review_quote=review_quote,
        jsonld_summary=jsonld_summary,
        raw_bytes=raw,
        raw_text=decoded,
    )


def _load_manuscripts(zip_path: Path) -> tuple[tuple[Manuscript, ...], Mapping[str, Any]]:
    raw_zip = zip_path.read_bytes()
    digest = _sha256(raw_zip)
    if digest != ZIP_SHA256:
        raise BuildError(f"ZIP SHA-256 mismatch: {digest}")
    manuscripts: list[Manuscript] = []
    total_uncompressed = 0
    with ZipFile(io.BytesIO(raw_zip), "r") as archive:
        infos = archive.infolist()
        if len(infos) != EXPECTED_MANUSCRIPTS:
            raise BuildError(f"ZIP must contain {EXPECTED_MANUSCRIPTS} members, got {len(infos)}")
        seen_names: set[str] = set()
        for info in infos:
            name = unicodedata.normalize("NFC", info.filename)
            if info.is_dir() or info.flag_bits & 0x1 or info.filename != name:
                raise BuildError(f"unsafe directory, encrypted, or non-NFC ZIP member: {info.filename!r}")
            if Path(name).name != name or name in seen_names or CONTROL_RE.search(name):
                raise BuildError(f"unsafe or duplicate ZIP member: {name!r}")
            if info.file_size <= 0 or info.file_size > 1_000_000:
                raise BuildError(f"unexpected ZIP member size: {name}")
            if info.compress_size and info.file_size / info.compress_size > 100:
                raise BuildError(f"suspicious ZIP compression ratio: {name}")
            seen_names.add(name)
            raw = archive.read(info)
            if len(raw) != info.file_size:
                raise BuildError(f"ZIP member length mismatch: {name}")
            total_uncompressed += len(raw)
            manuscripts.append(_parse_manuscript(name, raw))
    localities = [item.locality for item in manuscripts]
    if len(set(localities)) != EXPECTED_MANUSCRIPTS:
        raise BuildError("ZIP locality names are not unique")
    h2_count = sum(len(item.sections) for item in manuscripts)
    faq_count = sum(len(item.faqs) for item in manuscripts)
    if h2_count != EXPECTED_MANUSCRIPT_H2 or faq_count != EXPECTED_FAQS:
        raise BuildError(f"manuscript parity failed: H2={h2_count}, FAQ={faq_count}")
    metrics = {
        "zip_members": len(manuscripts),
        "zip_uncompressed_bytes": total_uncompressed,
        "raw_manuscript_roundtrip": len(manuscripts),
        "manuscript_h2": h2_count,
        "manuscript_faqs": faq_count,
        "manuscript_reviews": len(manuscripts),
    }
    return tuple(manuscripts), MappingProxyType(metrics)


def _read_csv_rows(path: Path, expected_sha: str) -> list[dict[str, str]]:
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != expected_sha:
        raise BuildError(f"{path.name} SHA-256 mismatch: {digest}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{path.name}: not strict UTF-8") from exc
    controls = CONTROL_RE.findall(text)
    # The pinned center CSV has one legacy backspace in an unused 위치안내
    # prose cell. Remove that exact known byte before parsing; no control can
    # reach rendered output, and every other control pattern remains fatal.
    if controls:
        if expected_sha != CENTER_CSV_SHA256 or controls != ["\x08"]:
            raise BuildError(f"{path.name}: unexpected control characters in pinned CSV")
        text = text.replace("\x08", "")
    if CONTROL_RE.search(text):
        raise BuildError(f"{path.name}: control sanitization failed")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise BuildError(f"{path.name}: missing CSV header")
    normalized_headers = [_normalize_header(header) for header in reader.fieldnames]
    if len(set(normalized_headers)) != len(normalized_headers):
        raise BuildError(f"{path.name}: duplicate normalized headers")
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        if None in raw_row:
            raise BuildError(f"{path.name}: row has excess fields")
        row = {
            normalized: unicodedata.normalize("NFC", (raw_row[original] or "").strip())
            for original, normalized in zip(reader.fieldnames, normalized_headers)
        }
        rows.append(row)
    if len(rows) != EXPECTED_MANUSCRIPTS:
        raise BuildError(f"{path.name}: expected 371 rows, got {len(rows)}")
    return rows


def _load_centers(common_dir: Path) -> tuple[Mapping[str, CenterRecord], Mapping[str, Any]]:
    center_path = common_dir / "센터정보 정리.csv"
    target_path = common_dir / "타깃학교.csv"
    center_rows = _read_csv_rows(center_path, CENTER_CSV_SHA256)
    target_rows = _read_csv_rows(target_path, TARGET_SCHOOL_CSV_SHA256)
    required = {
        "근처 수업가능 동네", "동 영어", "지역", "지역 영어", "시or구", "시or구 영어",
        "센터명", "센터 교습비", "교육지원청명칭", "교육지원청 등록번호", "센터 주소", "위치안내",
        "타깃학교(초)", "타깃학교(중)", "타깃학교(고)", "가능학년(국어)", "가능학년(영어)",
        "가능학년(수학)", "가능학년(과학)", "가능학년(사회)",
    }
    if not center_rows or not required.issubset(center_rows[0]):
        raise BuildError("센터정보 정리.csv required headers are missing")
    target_required = {"근처 수업가능 동네", "지역", "시or구", "센터명", "타깃학교(초)", "타깃학교(중)", "타깃학교(고)"}
    if not target_rows or not target_required.issubset(target_rows[0]):
        raise BuildError("타깃학교.csv required headers are missing")
    target_by_local = {row["근처 수업가능 동네"]: row for row in target_rows}
    if len(target_by_local) != EXPECTED_MANUSCRIPTS:
        raise BuildError("타깃학교.csv locality names are not unique")
    records: dict[str, CenterRecord] = {}
    parity_fields = tuple(target_required)
    for row in center_rows:
        locality = row["근처 수업가능 동네"]
        if not locality or locality in records:
            raise BuildError(f"duplicate or blank center locality: {locality!r}")
        target = target_by_local.get(locality)
        if target is None or any(row[field] != target[field] for field in parity_fields):
            raise BuildError(f"center/target-school seven-field parity failed: {locality}")
        records[locality] = CenterRecord(
            locality=locality,
            locality_en=row["동 영어"],
            region=row["지역"],
            region_en=row["지역 영어"],
            city=row["시or구"],
            city_en=row["시or구 영어"],
            center_name=row["센터명"],
            tuition_url=row["센터 교습비"],
            registration_name=row["교육지원청명칭"],
            registration_number=row["교육지원청 등록번호"],
            address=row["센터 주소"],
            location_note=row["위치안내"],
            elementary_schools=_split_csv_tokens(row["타깃학교(초)"]),
            middle_schools=_split_csv_source_tokens(row["타깃학교(중)"]),
            middle_school_source_tokens=_split_csv_source_tokens(row["타깃학교(중)"]),
            high_schools=_split_csv_tokens(row["타깃학교(고)"]),
            korean_grades=_split_csv_tokens(row["가능학년(국어)"]),
            english_grades=_split_csv_tokens(row["가능학년(영어)"]),
            math_grades=_split_csv_tokens(row["가능학년(수학)"]),
            science_grades=_split_csv_tokens(row["가능학년(과학)"]),
            social_grades=_split_csv_tokens(row["가능학년(사회)"]),
        )
    supported = sum(record.supports_middle3_math for record in records.values())
    if supported != EXPECTED_SUPPORTED:
        raise BuildError(f"expected {EXPECTED_SUPPORTED} supported centers, got {supported}")
    middle_school_token_count = sum(len(record.middle_schools) for record in records.values())
    global_middle_school_count = len({
        school for record in records.values() for school in record.middle_schools
    })
    if middle_school_token_count != 889 or global_middle_school_count != 405:
        raise BuildError(
            "middle-school composite token parity failed: "
            f"tokens={middle_school_token_count}, global={global_middle_school_count}"
        )
    metrics = {
        "center_rows": len(records),
        "target_school_rows": len(target_rows),
        "target_school_parity_fields": len(parity_fields),
        "supported_middle3_math": supported,
        "unconfirmed_middle3_math": len(records) - supported,
        "provided_middle_school_source_tokens": sum(len(record.middle_school_source_tokens) for record in records.values()),
        "provided_unique_middle_school_tokens": middle_school_token_count,
        "globally_unique_middle_school_names": global_middle_school_count,
        "missing_middle_school_rows": sum(not record.middle_schools for record in records.values()),
    }
    if metrics["unconfirmed_middle3_math"] != EXPECTED_UNSUPPORTED:
        raise BuildError("unsupported center count mismatch")
    return MappingProxyType(records), MappingProxyType(metrics)


def _extract_jsonld_graph(document: str, label: str) -> tuple[dict[str, Any], re.Match[str]]:
    matches = list(SCRIPT_JSON_RE.finditer(document))
    for match in matches:
        try:
            value = json.loads(match.group(2).replace("<\\/", "</"))
        except json.JSONDecodeError as exc:
            raise BuildError(f"{label}: malformed JSON-LD: {exc}") from exc
        if isinstance(value, dict) and isinstance(value.get("@graph"), list):
            return value, match
    raise BuildError(f"{label}: JSON-LD @graph script not found")


def _find_graph_node(graph: Sequence[Any], node_type: str, label: str) -> dict[str, Any]:
    nodes = [
        node for node in graph
        if isinstance(node, dict)
        and (node.get("@type") == node_type or node_type in (node.get("@type") or []))
    ]
    if len(nodes) != 1:
        raise BuildError(f"{label}: expected one {node_type}, got {len(nodes)}")
    return nodes[0]


def _extract_attr_from_tag(tag: str, attr: str, label: str) -> str:
    match = re.search(rf"\b{re.escape(attr)}\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE | re.DOTALL)
    if not match:
        raise BuildError(f"{label}: missing {attr} attribute")
    return html.unescape(match.group(2))


def _extract_img_src(document: str, figure_class: str, label: str) -> str:
    pattern = re.compile(
        rf"<figure\b[^>]*\bclass=[\"'][^\"']*\b{re.escape(figure_class)}\b[^\"']*[\"'][^>]*>\s*(<img\b[^>]*>)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(document)
    if not match:
        raise BuildError(f"{label}: {figure_class} image not found")
    return _extract_attr_from_tag(match.group(1), "src", label)


def _extract_meta_content(document: str, property_name: str, label: str) -> str:
    for tag in re.findall(r"<meta\b[^>]*>", document, re.IGNORECASE):
        prop_match = re.search(r"\bproperty\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE)
        if prop_match and prop_match.group(2).casefold() == property_name.casefold():
            return _extract_attr_from_tag(tag, "content", label)
    raise BuildError(f"{label}: meta property {property_name} not found")


def _local_asset_file(root: Path, src: str, label: str) -> Path:
    parsed = urlsplit(src)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not parsed.path.startswith("/assets/"):
        raise BuildError(f"{label}: image must be a query-free local /assets path: {src}")
    rel = Path(unquote(parsed.path.lstrip("/")))
    if any(part in ("", ".", "..") for part in rel.parts):
        raise BuildError(f"{label}: unsafe image path: {src}")
    target = (root / rel).resolve(strict=False)
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise BuildError(f"{label}: image path escapes root: {src}") from exc
    if not target.is_file():
        raise BuildError(f"{label}: local image is missing: {src}")
    return target


def _image_size(path: Path) -> tuple[int, int]:
    # Intrinsic headers occur near the beginning; avoid loading whole assets.
    with path.open("rb") as handle:
        data = handle.read(1_048_576)
    width = height = 0
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
    elif data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
    elif data.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset : offset + 2], "big")
            if length < 2 or offset + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if length < 7:
                    break
                height = int.from_bytes(data[offset + 3 : offset + 5], "big")
                width = int.from_bytes(data[offset + 5 : offset + 7], "big")
                break
            offset += length
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif chunk == b"VP8L" and data[20] == 0x2F:
            b1, b2, b3, b4 = data[21:25]
            width = 1 + b1 + ((b2 & 0x3F) << 8)
            height = 1 + (b2 >> 6) + (b3 << 2) + ((b4 & 0x0F) << 10)
        else:
            signature = data.find(b"\x9d\x01\x2a", 20)
            if signature >= 0 and signature + 7 <= len(data):
                width = int.from_bytes(data[signature + 3 : signature + 5], "little") & 0x3FFF
                height = int.from_bytes(data[signature + 5 : signature + 7], "little") & 0x3FFF
    if width <= 0 or height <= 0 or width > 50_000 or height > 50_000:
        raise BuildError(f"could not read intrinsic image dimensions: {path}")
    return width, height


def _load_page_assets(root: Path, locality: str, document: str) -> PageAssets:
    label = f"generic math page {locality}"
    jsonld, _ = _extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    organization = copy.deepcopy(_find_graph_node(graph, "EducationalOrganization", label))
    local_business = copy.deepcopy(_find_graph_node(graph, "LocalBusiness", label))
    representative_absolute = _extract_meta_content(document, "og:image", label)
    parsed_rep = urlsplit(representative_absolute)
    if parsed_rep.scheme != "https" or parsed_rep.netloc != "wawa-center.kr":
        raise BuildError(f"{label}: representative image must be on wawa-center.kr")
    representative_src = unquote(parsed_rep.path)
    body_src = _extract_img_src(document, "math-visible-image", label)
    map_src = _extract_img_src(document, "math-map-card", label)
    if len({representative_src, body_src, map_src}) != 3:
        raise BuildError(f"{label}: representative/body/map paths must differ")
    representative_file = _local_asset_file(root, representative_src, label)
    body_file = _local_asset_file(root, body_src, label)
    map_file = _local_asset_file(root, map_src, label)
    center_url = str(organization.get("url", ""))
    telephone = str(organization.get("telephone", ""))
    if not center_url.startswith(SITE_ORIGIN + "/center/") or not telephone:
        raise BuildError(f"{label}: physical center URL/telephone missing")
    return PageAssets(
        representative_src=representative_src,
        representative_size=_image_size(representative_file),
        body_src=body_src,
        body_size=_image_size(body_file),
        map_src=map_src,
        map_size=_image_size(map_file),
        organization=MappingProxyType(organization),
        local_business=MappingProxyType(local_business),
        center_url=center_url,
        telephone=telephone,
    )


def _physical_nodes(
    record: CenterRecord,
    assets: PageAssets,
    detail_url: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    organization = copy.deepcopy(dict(assets.organization))
    local_business = copy.deepcopy(dict(assets.local_business))
    organization_id = str(organization.get("@id", ""))
    local_business_id = str(local_business.get("@id", ""))
    if not organization_id or not local_business_id:
        raise BuildError(f"{record.locality}: physical schema IDs missing")
    address = {
        "@type": "PostalAddress",
        "streetAddress": record.address,
        "addressRegion": record.region,
        "addressLocality": record.city,
        "addressCountry": "KR",
    }
    identifier = {
        "@type": "PropertyValue",
        "name": "교육지원청 등록번호",
        "value": record.registration_number,
    }
    for node in (organization, local_business):
        node["name"] = record.center_name
        node["url"] = assets.center_url
        node["address"] = copy.deepcopy(address)
        node["areaServed"] = {"@type": "Place", "name": record.locality}
        node["identifier"] = copy.deepcopy(identifier)
        node.pop("makesOffer", None)
    organization["legalName"] = record.registration_name
    organization["educationalLevel"] = list(record.math_grades)
    organization["description"] = (
        f"{record.center_name}의 제공 주소는 {record.address}입니다. "
        + (
            "제공된 수학 가능 학년 자료에 중3이 기재되어 있으며 실제 시작 시점과 수업 조건은 상담에서 확인합니다."
            if record.supports_middle3_math
            else "제공된 수학 가능 학년 자료에는 중3이 기재되어 있지 않아 실제 수업 가능 여부를 상담에서 확인해야 합니다."
        )
    )
    local_business["parentOrganization"] = {"@id": organization_id}
    extra_nodes: list[dict[str, Any]] = []
    if record.supports_middle3_math:
        service_id = detail_url + "#service"
        offer_id = detail_url + "#offer"
        service = {
            "@type": "Service",
            "@id": service_id,
            "name": f"{record.locality} 중3 수학학원 학습상담",
            "serviceType": "중3 수학 학습상담 및 학습관리",
            "provider": {"@id": organization_id},
            "areaServed": {"@type": "Place", "name": record.locality},
            "audience": {
                "@type": "EducationalAudience",
                "educationalRole": "student",
                "audienceType": "중학교 3학년(중3)",
            },
            "offers": {"@id": offer_id},
        }
        offer: dict[str, Any] = {
            "@type": "Offer",
            "@id": offer_id,
            "name": f"{record.locality} 중3 수학 학습상담",
            "itemOffered": {"@id": service_id},
        }
        if record.tuition_url:
            offer["url"] = record.tuition_url
        else:
            offer["url"] = detail_url
        offer_ref = {"@id": offer_id}
        organization["makesOffer"] = [copy.deepcopy(offer_ref)]
        local_business["makesOffer"] = [copy.deepcopy(offer_ref)]
        extra_nodes.extend((service, offer))
    return organization, local_business, extra_nodes


def _school_mentions(record: CenterRecord) -> list[dict[str, str]]:
    return [{"@type": "Thing", "name": school} for school in record.middle_schools]


def _detail_schema(
    manuscript: Manuscript,
    record: CenterRecord,
    assets: PageAssets,
    detail_url: str,
    related: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    organization, local_business, service_offer = _physical_nodes(record, assets, detail_url)
    organization_id = organization["@id"]
    image_url = SITE_ORIGIN + quote(assets.representative_src, safe="/%")
    common_mentions: list[dict[str, str]] = [
        {"@type": "Place", "name": record.region},
        {"@type": "Place", "name": record.city},
        {"@type": "Place", "name": record.locality},
        {"@type": "Thing", "name": "중3 수학"},
        {"@type": "Thing", "name": "수학 내신"},
        {"@type": "Thing", "name": "오답 재학습"},
        *_school_mentions(record),
    ]
    heading_parts = [{"@type": "WebPageElement", "name": section.heading} for section in manuscript.sections]
    breadcrumb_id = detail_url + "#breadcrumb"
    article_id = detail_url + "#article"
    faq_id = detail_url + "#faq"
    links_id = detail_url + "#links"
    image_id = detail_url + "#primaryimage"
    web_page: dict[str, Any] = {
        "@type": "WebPage",
        "@id": detail_url + "#webpage",
        "url": detail_url,
        "name": f"{manuscript.title} | 와와학습코칭센터",
        "description": manuscript.meta_description,
        "inLanguage": "ko-KR",
        "isPartOf": {"@id": SITE_ORIGIN + "/#website"},
        "publisher": {"@id": organization_id},
        "breadcrumb": {"@id": breadcrumb_id},
        "mainEntity": {"@id": article_id},
        "primaryImageOfPage": {"@id": image_id},
        "about": [
            {"@type": "Thing", "name": manuscript.title},
            {"@type": "Thing", "name": "중3 수학 학습 정보"},
        ],
        "mentions": copy.deepcopy(common_mentions),
        "hasPart": [
            {"@id": article_id}, {"@id": faq_id}, {"@id": links_id}, *copy.deepcopy(heading_parts)
        ],
        "datePublished": PUBLISHED_DATE,
        "dateModified": PUBLISHED_DATE,
    }
    article = {
        "@type": "Article",
        "@id": article_id,
        "headline": manuscript.title,
        "description": manuscript.jsonld_summary,
        "image": image_url,
        "inLanguage": "ko-KR",
        "datePublished": PUBLISHED_DATE,
        "dateModified": PUBLISHED_DATE,
        "mainEntityOfPage": {"@id": web_page["@id"]},
        "author": {"@id": organization_id},
        "publisher": {"@id": organization_id},
        "articleSection": [section.heading for section in manuscript.sections],
        "about": [
            {"@type": "Thing", "name": manuscript.title},
            {"@type": "Thing", "name": "중3 수학 학습 진단"},
        ],
        "mentions": copy.deepcopy(common_mentions),
        "hasPart": copy.deepcopy(heading_parts),
    }
    breadcrumb = {
        "@type": "BreadcrumbList",
        "@id": breadcrumb_id,
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_ORIGIN + "/"},
            {"@type": "ListItem", "position": 2, "name": "학년별학원", "item": _encoded_site_url("학년별학원")},
            {"@type": "ListItem", "position": 3, "name": "중3 수학학원", "item": _encoded_site_url("학년별학원", "중3수학학원")},
            {"@type": "ListItem", "position": 4, "name": manuscript.title, "item": detail_url},
        ],
    }
    faq_page = {
        "@type": "FAQPage",
        "@id": faq_id,
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq.question,
                "acceptedAnswer": {"@type": "Answer", "text": faq.answer},
            }
            for faq in manuscript.faqs
        ],
    }
    item_list = {
        "@type": "ItemList",
        "@id": links_id,
        "name": f"{manuscript.title} 관련 페이지",
        "numberOfItems": len(related),
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "url": url}
            for index, (name, url) in enumerate(related, 1)
        ],
    }
    image_object = {
        "@type": "ImageObject",
        "@id": image_id,
        "url": image_url,
        "contentUrl": image_url,
        "width": assets.representative_size[0],
        "height": assets.representative_size[1],
        "caption": f"{manuscript.title} 대표 이미지",
    }
    graph: list[dict[str, Any]] = [
        web_page,
        organization,
        local_business,
        breadcrumb,
        article,
        faq_page,
        item_list,
        image_object,
        *service_offer,
    ]
    return {"@context": "https://schema.org", "@graph": graph}


def _nav_markup() -> str:
    return """<header class="site-header">
    <nav class="nav" aria-label="주요 메뉴">
      <a class="logo" href="/"><span class="brand-orange">와와</span>학습<span class="brand-orange">코칭</span>센터 <span class="brand-tail">영어수학 전문학원</span></a>
      <div class="nav-links" aria-label="페이지 이동">
        <a href="/">홈</a>
        <a href="/overview/">학원소개</a>
        <a href="/guide/">학습가이드</a>
        <a href="/교육정보/">교육정보</a>
        <a href="/학부모후기/">학부모후기</a>
        <a href="/과목별학원/">과목별학원</a>
        <a class="active" href="/학년별학원/">학년별학원</a>
        <a href="/center/">전국센터</a>
      </div>
    </nav>
  </header>"""


def _fab_markup(telephone: str = "010-3957-8283") -> str:
    digits = re.sub(r"\D", "", telephone)
    return f"""<div class="wawa-fixed-fab-container">
    <a href="tel:{_escape(telephone)}" class="wawa-fab-item fab-call"><span class="fab-icon">📞</span><span class="fab-text">전화문의</span></a>
    <a href="https://blogsms.net/{digits}" target="_blank" rel="noopener" class="wawa-fab-item fab-sms"><span class="fab-icon">💬</span><span class="fab-text">문자문의</span></a>
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSdb2oE5Qk5YS0TfYDxyV1w-IOTkhkjOCmmpAKTI9FmqpVj6Yg/viewform" target="_blank" rel="noopener" class="wawa-fab-item fab-consult pulse-effect"><span class="fab-icon">📝</span><span class="fab-text">상담신청</span></a>
  </div>"""


def _clean_document(document: str) -> str:
    if CONTROL_RE.search(document):
        raise BuildError("rendered document contains forbidden control characters")
    return "\n".join(line.rstrip(" \t") for line in document.splitlines()) + "\n"


def _paragraph_markup(value: str) -> str:
    return _escape(value).replace("\n", "<br>\n")


def _render_detail(
    manuscript: Manuscript,
    record: CenterRecord,
    assets: PageAssets,
    previous_locality: str,
    next_locality: str,
) -> str:
    locality = record.locality
    detail_url = _encoded_site_url("학년별학원", "중3수학학원", locality)
    parent_url = _encoded_site_url("학년별학원")
    category_url = _encoded_site_url("학년별학원", "중3수학학원")
    generic_math_url = _encoded_site_url("과목별학원", "수학학원", locality)
    study_url = _encoded_site_url("교육정보", "수학-공부법")
    previous_url = _encoded_site_url("학년별학원", "중3수학학원", previous_locality)
    next_url = _encoded_site_url("학년별학원", "중3수학학원", next_locality)
    related = (
        ("학년별학원 안내", parent_url),
        ("중3 수학학원 전체 지역", category_url),
        (f"{locality} 수학학원 안내", generic_math_url),
        (f"{locality} 센터 안내", assets.center_url),
        ("수학 공부법", study_url),
        (f"이전 지역 · {previous_locality}", previous_url),
        (f"다음 지역 · {next_locality}", next_url),
    )
    schema = _detail_schema(manuscript, record, assets, detail_url, related)
    image_url = SITE_ORIGIN + quote(assets.representative_src, safe="/%")
    source_status = "supported" if record.supports_middle3_math else "unconfirmed-grade"
    source_status_detail = (
        "제공된 센터 자료의 수학 가능 학년에 중3이 기재되어 있습니다. 시작 시점·시간·반 구성은 상담에서 최신 내용을 확인하세요."
        if record.supports_middle3_math
        else "제공 자료의 수학 가능 학년에 중3이 기재되지 않아 이 페이지는 선택 기준을 설명하는 정보 글이며, 해당 센터의 중3 수학 수업 제공을 뜻하지 않습니다. 실제 가능 여부는 상담에서 확인하세요."
    )
    hero_status_copy = (
        f"{locality} 원고의 최근 풀이·학교 자료·오답 회수 순서를 읽고 학생의 실제 자료와 대조해 보세요."
        if record.supports_middle3_math
        else f"{locality} 원고는 중3 수학 선택 기준을 설명합니다. 센터 수업 가능 여부는 아래 자료 상태와 상담 답변을 따로 확인하세요."
    )
    source_card_note = (
        source_status_detail
        if record.supports_middle3_math
        else "가능 학년 원자료 상태는 아래 학년 항목에 표시했으며, 현재 제공 여부를 원고의 일반 학습 조언과 구분해 확인해야 합니다."
    )
    school_status = "provided" if record.middle_schools else "missing"
    if record.middle_schools:
        school_value = '<div class="math-tag-list">' + "".join(
            f"<span>{_escape(school)}</span>" for school in record.middle_schools
        ) + "</div>"
    else:
        school_value = "원자료에 중학교명이 기재되지 않아 재학 학교와 현재 수업 가능 여부를 상담에서 확인해 주세요."
    grades_value = " · ".join(record.math_grades) if record.math_grades else "원자료 미기재"
    if record.supports_middle3_math:
        grade_value = f"중3 확인 · 전체 기재 학년: {_escape(grades_value)}"
    else:
        grade_value = f"중3 상담 확인 필요 · 전체 기재 학년: {_escape(grades_value)}"
    registration_value = record.registration_number or "원자료 미기재 — 상담 확인"
    if record.tuition_url:
        fee_value = (
            f'<a class="math-tuition-link" href="{_escape(record.tuition_url)}" target="_blank" '
            'rel="noopener noreferrer">센터 교습비 자료 확인 <span aria-hidden="true">↗</span></a>'
        )
    else:
        fee_value = "원자료에 교습비 링크가 없어 상담에서 최신 비용을 확인해 주세요."
    intro_markup = "\n".join(
        f"        <p>{_paragraph_markup(paragraph)}</p>" for paragraph in manuscript.intro_paragraphs
    )
    section_markup = "\n".join(
        "\n".join(
            [
                f'      <section class="math-prose-section" data-manuscript-section="{index:02d}">',
                f"        <h2>{_escape(section.heading)}</h2>",
                *[f"        <p>{_paragraph_markup(paragraph)}</p>" for paragraph in section.paragraphs],
                "      </section>",
            ]
        )
        for index, section in enumerate(manuscript.sections, 1)
    )
    faq_markup = "\n".join(
        "\n".join(
            [
                f'        <details class="math-faq-item"{" open" if faq.number == 1 else ""}>',
                f"          <summary><span>Q{faq.number}.</span> {_escape(faq.question)}</summary>",
                f"          <p><strong>A.</strong> {_paragraph_markup(faq.answer)}</p>",
                "        </details>",
            ]
        )
        for faq in manuscript.faqs
    )
    related_markup = "".join(
        f'<a href="{_escape(url)}">{_escape(name)}</a>' for name, url in related
    )
    unsupported_alert = "" if record.supports_middle3_math else (
        f'<section class="math-section grade-source-alert" aria-label="{_escape(locality)} 중3 수학 수업 확인 안내">'
        f'<div class="math-narrow"><strong>상담 확인이 필요한 페이지입니다.</strong><p>{_escape(source_status_detail)}</p></div></section>'
    )
    body_w, body_h = assets.body_size
    map_w, map_h = assets.map_size
    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(manuscript.title)} | 와와학습코칭센터</title>
  <meta name="description" content="{_escape(manuscript.meta_description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{detail_url}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{_escape(manuscript.title)} | 와와학습코칭센터">
  <meta property="og:description" content="{_escape(manuscript.meta_description)}">
  <meta property="og:url" content="{detail_url}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:site_name" content="와와학습코칭센터">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_escape(manuscript.title)} | 와와학습코칭센터">
  <meta name="twitter:description" content="{_escape(manuscript.meta_description)}">
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
  {_nav_markup()}
  <main data-grade-page="middle3-math" data-source-status="{source_status}">
    <section class="math-hero">
      <div class="math-container">
        <nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/학년별학원/">학년별학원</a><span>›</span><a href="/학년별학원/중3수학학원/">중3 수학학원</a><span>›</span><span aria-current="page">{_escape(manuscript.title)}</span></nav>
        <div class="math-hero-grid">
          <div><p class="math-eyebrow">MIDDLE SCHOOL GRADE 3 MATH GUIDE</p><h1>{_escape(manuscript.title)}</h1><p class="math-hero-lead">{_escape(manuscript.meta_description)}</p></div>
          <aside class="math-hero-panel"><strong>{_escape(locality)} 중3 수학 상담의 출발점</strong><p>{_escape(hero_status_copy)}</p><div class="math-step-row"><span>현재 풀이</span><span>학교 자료</span><span>재점검</span></div></aside>
        </div>
      </div>
    </section>
    {unsupported_alert}
    <section class="math-media-section" aria-label="{_escape(manuscript.title)} 이미지 안내">
      <div class="math-container math-media-stack">
        <figure class="math-visible-image"><img data-image-role="body" src="{_escape(assets.body_src)}" alt="{_escape(manuscript.title)} 본문 와와학습코칭센터" loading="eager" fetchpriority="high" decoding="async" width="{body_w}" height="{body_h}"></figure>
        <figure class="math-map-card"><img data-image-role="map" src="{_escape(assets.map_src)}" alt="{_escape(manuscript.title)} 센터 위치 지도" loading="lazy" decoding="async" width="{map_w}" height="{map_h}"><figcaption class="math-map-caption">제공 주소를 기준으로 등원 시간과 귀가 동선을 상담 전에 직접 확인할 때 참고하는 위치 이미지입니다.</figcaption></figure>
      </div>
    </section>
    <section class="math-section paper"><div class="math-container math-quick-grid">
      <article class="math-summary-card"><strong>핵심 요약</strong><h2>{_escape(locality)} 중3 수학학원 선택 기준</h2><p>{_escape(manuscript.jsonld_summary)}</p></article>
      <aside class="math-info-card"><h2>지역·학년·수업 자료 확인</h2><p class="grade-source-note">{_escape(source_card_note)}</p><dl>
        <div><dt>지역</dt><dd>{_escape(record.region)} {_escape(record.city)} {_escape(locality)}</dd></div>
        <div><dt>센터 기준</dt><dd>{_escape(record.center_name)}</dd></div>
        <div data-source-field="grade"><dt>수학 가능 학년</dt><dd>{grade_value}</dd></div>
        <div data-source-field="middle-schools" data-source-status="{school_status}"><dt>수업 가능 학교 자료</dt><dd>{school_value}</dd></div>
        <div data-source-field="address"><dt>제공 주소</dt><dd>{_escape(record.address)}</dd></div>
        <div data-source-field="registration"><dt>교육지원청 등록번호</dt><dd>{_escape(registration_value)}</dd></div>
        <div data-source-field="fee"><dt>센터 교습비</dt><dd>{fee_value}</dd></div>
      </dl></aside>
    </div></section>
    <section class="math-section"><article class="math-narrow math-article" data-manuscript>
      <div class="math-article-intro">
{intro_markup}
      </div>
{section_markup}
    </article></section>
    <section class="math-section paper"><div class="math-narrow math-links-card"><p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>{_escape(locality)} 상담 전 체크리스트</h2><ul class="grade-checklist"><li>□ {_escape(locality)} 학생의 최근 시험지와 실제 풀이가 남은 문제집</li><li>□ 학교 교과서·시험 범위표와 수행평가 일정</li><li>□ 일주일 중 혼자 복습할 수 있는 시간과 실제 등원 동선</li><li>□ 오답을 다시 확인할 날짜와 상담에서 물어볼 운영 조건</li></ul></div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card" data-faq><p class="math-eyebrow">FAQ</p><h2>{_escape(locality)} 중3 수학학원 자주 묻는 질문</h2><div class="math-faq-list">
{faq_markup}
      </div></div></section>
    <section class="math-section"><div class="math-narrow math-review-card" data-review><p class="math-eyebrow">PARENT COMMENT</p><h2>{_escape(locality)} 학부모 상담 관점</h2><p class="math-review-note">{_escape(manuscript.review_disclaimer)}</p><blockquote class="math-review-quote">{_escape(manuscript.review_quote)}</blockquote></div></section>
    <section class="math-section paper"><div class="math-narrow math-links-card"><p class="math-eyebrow">RELATED PAGES</p><h2>{_escape(locality)} 관련 내부 링크</h2><div class="math-links">{related_markup}</div></div></section>
  </main>
  {_fab_markup(assets.telephone)}
  <footer class="math-footer"><strong>와와학습코칭센터</strong><br>원고와 제공된 센터·학교 자료를 기준으로 구성했으며, 실제 수업 가능 여부·비용·일정은 상담에서 최신 내용을 확인해 주세요.</footer>
</body>
</html>"""
    return _clean_document(document)


def _directory_org() -> dict[str, Any]:
    return {
        "@type": "EducationalOrganization",
        "@id": SITE_ORIGIN + "/#organization",
        "name": "와와학습코칭센터",
        "url": SITE_ORIGIN + "/",
        "telephone": "010-3957-8283",
        "areaServed": {"@type": "Country", "name": "대한민국"},
        "knowsAbout": ["중3 수학", "수학 내신", "오답 재학습", "학습 계획"],
    }


def _directory_head(title: str, description: str, canonical: str, schema: Mapping[str, Any]) -> str:
    image_url = SITE_ORIGIN + "/assets/title.png"
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
  <meta property="og:image" content="{image_url}">
  <meta property="og:site_name" content="와와학습코칭센터">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_escape(title)}">
  <meta name="twitter:description" content="{_escape(description)}">
  <meta name="twitter:image" content="{image_url}">
  <link rel="icon" href="/assets/favicon.png">
  <link rel="stylesheet" href="/assets/fab.css">
  <link rel="stylesheet" href="/assets/header.css">
  <link rel="stylesheet" href="/assets/subject-academy.css">
  <link rel="stylesheet" href="/assets/math-academy.css">
  <script type="application/ld+json">{_json_script(schema)}</script>
</head>"""


def _render_parent_hub() -> str:
    canonical = _encoded_site_url("학년별학원")
    category = _encoded_site_url("학년별학원", "중3수학학원")
    title = "학년별학원 안내 | 와와학습코칭센터"
    description = "학년에 맞는 학습 진단과 과목별 복습 기준을 찾을 수 있는 안내입니다. 현재 중3 수학학원 371개 지역 원고를 제공합니다."
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            _directory_org(),
            {
                "@type": "CollectionPage", "@id": canonical + "#webpage", "url": canonical,
                "name": title, "description": description, "inLanguage": "ko-KR",
                "isPartOf": {"@id": SITE_ORIGIN + "/#website"},
                "publisher": {"@id": SITE_ORIGIN + "/#organization"},
                "breadcrumb": {"@id": canonical + "#breadcrumb"},
                "about": [{"@type": "Thing", "name": "학년별학원"}, {"@type": "Thing", "name": "중3 수학"}],
                "hasPart": [{"@type": "CollectionPage", "name": "중3 수학학원", "url": category}],
                "datePublished": PUBLISHED_DATE, "dateModified": PUBLISHED_DATE,
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
                "numberOfItems": 1,
                "itemListElement": [{"@type": "ListItem", "position": 1, "name": "중3 수학학원", "url": category}],
            },
            {
                "@type": "FAQPage", "@id": canonical + "#faq", "mainEntity": [
                    {"@type": "Question", "name": "학년별학원 페이지에서는 무엇을 확인하나요?", "acceptedAnswer": {"@type": "Answer", "text": "학생 학년을 먼저 정한 뒤 과목별 진단, 학교 자료, 복습과 상담 기준을 지역별 원고에서 확인할 수 있습니다."}},
                    {"@type": "Question", "name": "현재 제공되는 학년별 분류는 무엇인가요?", "acceptedAnswer": {"@type": "Answer", "text": "현재는 중학교 3학년 수학 안내를 371개 동네별로 제공합니다."}},
                ],
            },
        ],
    }
    document = f"""<!doctype html>
<html lang="ko">
{_directory_head(title, description, canonical, schema)}
<body class="subject-page">
  {_nav_markup()}
  <main data-grade-directory="parent">
    <section class="subject-hero"><div class="subject-container"><nav class="subject-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><span aria-current="page">학년별학원</span></nav><div class="subject-hero-grid"><div><p class="subject-kicker">GRADE ACADEMY GUIDE</p><h1>학년별학원에서 학년부터 고르고<br>필요한 과목을 확인하세요</h1><p class="subject-hero-copy">학생의 현재 학년을 출발점으로 학교 자료, 취약 단원, 오답 재학습과 주간 계획을 지역별로 확인하는 안내입니다.</p></div><aside class="subject-hero-panel"><strong>학년명만으로 수업을 단정하지 않습니다</strong><p>지역 원고와 제공된 가능 학년 자료를 함께 보고, 실제 수업 시작 시점과 조건은 상담에서 확인하세요.</p><div class="subject-hero-tags"><span>현재 학년</span><span>학교 자료</span><span>오답 기록</span><span>주간 계획</span></div></aside></div></div></section>
    <section class="subject-section paper"><div class="subject-container"><div class="subject-section-head"><p class="subject-kicker">GRADE CATEGORIES</p><h2>현재 확인할 수 있는 학년별 안내</h2><p>첫 분류로 중3 수학학원 371개 지역 원고를 제공합니다.</p></div><div class="subject-category-grid"><a class="subject-category-card" data-number="01" href="/학년별학원/중3수학학원/"><small>MIDDLE SCHOOL GRADE 3</small><h3>중3 수학학원</h3><p>개념·오답 습관, 실제 학교 자료, 주간 진도와 복습, 등원 시간과 상담 질문을 동네별로 확인합니다.</p><span class="subject-status">371개 지역 안내 보기 →</span></a></div></div></section>
    <section class="subject-section"><div class="subject-container"><div class="subject-section-head"><p class="subject-kicker">HOW TO USE</p><h2>지역 원고를 확인하는 순서</h2></div><div class="subject-point-grid"><article><strong>01</strong><h3>현재 풀이를 준비합니다</h3><p>최근 시험지와 답지를 보지 않은 풀이를 함께 준비합니다.</p></article><article><strong>02</strong><h3>학교 자료를 대조합니다</h3><p>교과서, 범위표와 평가 일정을 실제 자료로 확인합니다.</p></article><article><strong>03</strong><h3>수업 가능 여부를 확인합니다</h3><p>제공 자료와 상담 안내를 구분해 시작 시점과 비용을 확인합니다.</p></article></div></div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card" data-faq><p class="math-eyebrow">FAQ</p><h2>학년별학원 자주 묻는 질문</h2><div class="math-faq-list"><details class="math-faq-item" open><summary>학년별학원 페이지에서는 무엇을 확인하나요?</summary><p>학생 학년을 먼저 정한 뒤 과목별 진단, 학교 자료, 복습과 상담 기준을 지역별 원고에서 확인할 수 있습니다.</p></details><details class="math-faq-item"><summary>현재 제공되는 학년별 분류는 무엇인가요?</summary><p>현재는 중학교 3학년 수학 안내를 371개 동네별로 제공합니다.</p></details></div></div></section>
  </main>
  {_fab_markup()}
  <footer class="subject-footer"><strong>와와학습코칭센터</strong><br>학년별 페이지는 원고와 제공 자료를 기준으로 구성하며 실제 수업 조건은 상담에서 확인해 주세요.</footer>
</body>
</html>"""
    return _clean_document(document)


def _group_centers(manuscripts: Sequence[Manuscript], centers: Mapping[str, CenterRecord]) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for manuscript in manuscripts:
        record = centers[manuscript.locality]
        grouped.setdefault(record.region, {}).setdefault(record.city, []).append(record.locality)
    return [(region, list(cities.items())) for region, cities in grouped.items()]


def _render_category_hub(manuscripts: Sequence[Manuscript], centers: Mapping[str, CenterRecord]) -> str:
    canonical = _encoded_site_url("학년별학원", "중3수학학원")
    parent = _encoded_site_url("학년별학원")
    title = "중3 수학학원 371개 지역 안내 | 와와학습코칭센터"
    description = "중3 수학학원 선택에 필요한 개념·오답 진단, 학교 자료, 주간 복습과 상담 확인 항목을 371개 동네별 원고에서 찾으세요."
    item_elements = [
        {
            "@type": "ListItem", "position": index, "name": manuscript.title,
            "url": _encoded_site_url("학년별학원", "중3수학학원", manuscript.locality),
        }
        for index, manuscript in enumerate(manuscripts, 1)
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            _directory_org(),
            {
                "@type": "CollectionPage", "@id": canonical + "#webpage", "url": canonical,
                "name": title, "description": description, "inLanguage": "ko-KR",
                "isPartOf": {"@id": SITE_ORIGIN + "/#website"},
                "publisher": {"@id": SITE_ORIGIN + "/#organization"},
                "breadcrumb": {"@id": canonical + "#breadcrumb"},
                "mainEntity": {"@id": canonical + "#regions"},
                "about": [{"@type": "Thing", "name": "중3 수학학원"}, {"@type": "Thing", "name": "중3 수학 내신"}],
                "mentions": [{"@type": "Thing", "name": "오답 재학습"}, {"@type": "Thing", "name": "학교별 시험 자료"}],
                "hasPart": [{"@id": canonical + "#regions"}],
                "datePublished": PUBLISHED_DATE, "dateModified": PUBLISHED_DATE,
            },
            {
                "@type": "BreadcrumbList", "@id": canonical + "#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_ORIGIN + "/"},
                    {"@type": "ListItem", "position": 2, "name": "학년별학원", "item": parent},
                    {"@type": "ListItem", "position": 3, "name": "중3 수학학원", "item": canonical},
                ],
            },
            {
                "@type": "ItemList", "@id": canonical + "#regions", "name": "중3 수학학원 지역 목록",
                "numberOfItems": EXPECTED_MANUSCRIPTS, "itemListElement": item_elements,
            },
            {
                "@type": "FAQPage", "@id": canonical + "#faq", "mainEntity": [
                    {"@type": "Question", "name": "중3 수학학원 상담에 무엇을 가져가면 좋나요?", "acceptedAnswer": {"@type": "Answer", "text": "최근 시험지, 실제 풀이가 남은 문제집, 학교 교과서와 범위표, 일주일 시간표를 준비하면 진단과 복습 계획을 구체적으로 비교할 수 있습니다."}},
                    {"@type": "Question", "name": "지역 페이지에 학교명이 없으면 어떻게 하나요?", "acceptedAnswer": {"@type": "Answer", "text": "제공 자료에 중학교명이 없는 경우 임의로 학교를 추가하지 않으며, 재학 학교의 실제 교과서와 시험 범위 대응 여부를 상담에서 확인해야 합니다."}},
                ],
            },
        ],
    }
    region_markup_parts: list[str] = []
    for region, cities in _group_centers(manuscripts, centers):
        region_count = sum(len(localities) for _, localities in cities)
        city_parts: list[str] = []
        for city, localities in cities:
            links = "".join(
                f'<a href="/학년별학원/중3수학학원/{_escape(locality)}/" data-grade-locality="{_escape(locality)}">{_escape(locality)} 중3 수학학원</a>'
                for locality in localities
            )
            city_parts.append(
                f'<section class="math-city" data-grade-city="{_escape(city)}"><h3>{_escape(city)}</h3><div class="math-local-grid">{links}</div></section>'
            )
        region_markup_parts.append(
            f'<details class="math-region" data-grade-region="{_escape(region)}"><summary><strong>{_escape(region)}</strong><span>{region_count}개 지역</span></summary><div class="math-region-body">{"".join(city_parts)}</div></details>'
        )
    region_markup = "\n".join(region_markup_parts)
    document = f"""<!doctype html>
<html lang="ko">
{_directory_head(title, description, canonical, schema)}
<body class="math-academy-page">
  {_nav_markup()}
  <main data-grade-directory="middle3-math">
    <section class="math-hero"><div class="math-container"><nav class="math-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span>›</span><a href="/학년별학원/">학년별학원</a><span>›</span><span aria-current="page">중3 수학학원</span></nav><div class="math-hero-grid"><div><p class="math-eyebrow">MIDDLE SCHOOL GRADE 3 MATH</p><h1>중3 수학학원 371개 지역 안내</h1><p class="math-hero-lead">중3 수학의 개념·오답 습관, 학교 자료 확인, 주간 진도와 복습, 상담 질문을 동네별 원고에서 확인하세요.</p></div><aside class="math-hero-panel"><strong>학교명만으로 시험 유형을 단정하지 않습니다</strong><p>지역을 찾은 뒤 학생의 실제 교과서, 시험 범위와 풀이 기록을 함께 대조하세요.</p><div class="math-step-row"><span>지역 찾기</span><span>원고 읽기</span><span>상담 확인</span></div></aside></div></div></section>
    <section class="math-section paper"><div class="math-container"><div class="math-section-head"><p class="math-eyebrow">LOCAL DIRECTORY</p><h2>동네별 중3 수학학원 원고 찾기</h2><p>지역명 일부를 입력하면 목록을 바로 좁힐 수 있습니다.</p></div><div class="math-search-card"><label for="grade-local-search">동네 검색</label><div class="math-search-row"><input id="grade-local-search" type="search" placeholder="예: 명일동" autocomplete="off" data-grade-search><button type="button" data-grade-clear>검색 지우기</button></div><p aria-live="polite" data-grade-status>전체 371개 지역</p></div><div class="math-directory" data-grade-list>{region_markup}</div></div></section>
    <section class="math-section paper"><div class="math-narrow math-faq-card" data-faq><p class="math-eyebrow">FAQ</p><h2>중3 수학학원 자주 묻는 질문</h2><div class="math-faq-list"><details class="math-faq-item" open><summary>중3 수학학원 상담에 무엇을 가져가면 좋나요?</summary><p>최근 시험지, 실제 풀이가 남은 문제집, 학교 교과서와 범위표, 일주일 시간표를 준비하면 진단과 복습 계획을 구체적으로 비교할 수 있습니다.</p></details><details class="math-faq-item"><summary>지역 페이지에 학교명이 없으면 어떻게 하나요?</summary><p>제공 자료에 중학교명이 없는 경우 임의로 학교를 추가하지 않으며, 재학 학교의 실제 교과서와 시험 범위 대응 여부를 상담에서 확인해야 합니다.</p></details></div></div></section>
    <section class="math-section"><div class="math-narrow math-links-card"><p class="math-eyebrow">CHECK BEFORE CONSULTATION</p><h2>중3 수학 상담 전 준비 자료</h2><div class="math-links"><a href="/학년별학원/">학년별학원 안내</a><a href="/과목별학원/수학학원/">수학학원 전체 지역</a><a href="/교육정보/수학-공부법/">수학 공부법</a><a href="/center/">전국센터 찾기</a></div></div></section>
  </main>
  {_fab_markup()}
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
      status.textContent = query ? `${{visible}}개 지역 검색됨` : '전체 371개 지역';
    }};
    input.addEventListener('input', update);
    clear.addEventListener('click', () => {{ input.value = ''; update(); input.focus(); }});
  }})();
  </script>
</body>
</html>"""
    return _clean_document(document)


def _anchor_text(match: re.Match[str]) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", match.group("body"))).strip()


def _anchor_href(match: re.Match[str]) -> str:
    href = HREF_RE.search(match.group("attrs"))
    return html.unescape(href.group(2)) if href else ""


def _active_nav_signature(nav_inner: str) -> tuple[tuple[str, str], ...]:
    signature: list[tuple[str, str]] = []
    for anchor in ANCHOR_RE.finditer(nav_inner):
        class_match = re.search(r"\bclass\s*=\s*([\"'])(.*?)\1", anchor.group("attrs"), re.IGNORECASE | re.DOTALL)
        classes = class_match.group(2).split() if class_match else []
        if "active" in classes:
            signature.append((_anchor_href(anchor), _anchor_text(anchor)))
    return tuple(signature)


def _insert_grade_nav(document: str, label: str) -> str:
    nav_matches = list(NAV_RE.finditer(document))
    if len(nav_matches) != 1:
        raise BuildError(f"{label}: expected exactly one nav-links container")
    nav_match = nav_matches[0]
    inner = nav_match.group(2)
    anchors = list(ANCHOR_RE.finditer(inner))
    subjects = [anchor for anchor in anchors if _anchor_text(anchor) == "과목별학원"]
    grade_links = [anchor for anchor in anchors if _anchor_href(anchor) == GRADE_NAV_HREF]
    before_active = _active_nav_signature(inner)
    if len(subjects) != 1 or len(grade_links) > 1:
        raise BuildError(f"{label}: invalid subject/grade navigation cardinality")
    if not grade_links:
        subject = subjects[0]
        newline = "\r\n" if "\r\n" in document else "\n"
        line_start = inner.rfind("\n", 0, subject.start()) + 1
        indentation_match = re.match(r"[ \t]*", inner[line_start:subject.start()])
        indentation = indentation_match.group(0) if indentation_match else ""
        insertion = f'{newline}{indentation}<a href="{GRADE_NAV_HREF}">학년별학원</a>'
        inner = inner[: subject.end()] + insertion + inner[subject.end() :]
    final_anchors = list(ANCHOR_RE.finditer(inner))
    subject_positions = [i for i, anchor in enumerate(final_anchors) if _anchor_text(anchor) == "과목별학원"]
    grade_positions = [i for i, anchor in enumerate(final_anchors) if _anchor_href(anchor) == GRADE_NAV_HREF]
    if len(subject_positions) != 1 or len(grade_positions) != 1 or grade_positions[0] != subject_positions[0] + 1:
        raise BuildError(f"{label}: grade nav is not immediately after subject nav")
    if _active_nav_signature(inner) != before_active:
        raise BuildError(f"{label}: existing active navigation state changed")
    return document[: nav_match.start(2)] + inner + document[nav_match.end(2) :]


def _update_root_haspart(document: str) -> str:
    jsonld, match = _extract_jsonld_graph(document, "root index")
    candidates = [
        node for node in jsonld["@graph"]
        if isinstance(node, dict)
        and node.get("@type") == "WebPage"
        and node.get("@id") == SITE_ORIGIN + "/#webpage"
    ]
    if len(candidates) != 1:
        raise BuildError("root index: canonical WebPage node not found uniquely")
    webpage = candidates[0]
    has_part = webpage.setdefault("hasPart", [])
    if not isinstance(has_part, list):
        raise BuildError("root index: WebPage.hasPart must be a list")
    grade_url = _encoded_site_url("학년별학원")
    matching = [
        item for item in has_part
        if isinstance(item, dict) and (item.get("name") == "학년별학원" or item.get("url") == grade_url)
    ]
    expected = {"@type": "WebPage", "name": "학년별학원", "url": grade_url}
    if not matching:
        has_part.append(expected)
    elif len(matching) != 1 or matching[0] != expected:
        raise BuildError("root index: conflicting 학년별학원 hasPart entry")
    serialized = _json_script(jsonld)
    return document[: match.start(2)] + serialized + document[match.end(2) :]


def _update_header_css(document: str) -> str:
    old = "@media (max-width: 900px) {"
    new = "@media (max-width: 1120px) {"
    old_count = document.count(old)
    new_count = document.count(new)
    if (old_count, new_count) == (1, 0):
        return document.replace(old, new, 1)
    if (old_count, new_count) == (0, 1):
        return document
    raise BuildError(f"header.css: expected one exact 900px or 1120px rule, got {old_count}/{new_count}")


def _sitemap_new_urls(manuscripts: Sequence[Manuscript]) -> tuple[str, ...]:
    return (
        _encoded_site_url("학년별학원"),
        _encoded_site_url("학년별학원", "중3수학학원"),
        *(
            _encoded_site_url("학년별학원", "중3수학학원", manuscript.locality)
            for manuscript in manuscripts
        ),
    )


def _url_block_values(document: str) -> tuple[tuple[str, str, str], ...]:
    values: list[tuple[str, str, str]] = []
    for block_match in URL_BLOCK_RE.finditer(document):
        block = block_match.group(0)
        loc = LOC_RE.findall(block)
        lastmod = LASTMOD_RE.findall(block)
        if len(loc) != 1 or len(lastmod) != 1:
            raise BuildError("sitemap.xml: each URL block must contain one loc and lastmod")
        values.append((html.unescape(loc[0].strip()), lastmod[0].strip(), block))
    return tuple(values)


def _update_sitemap(document: str, manuscripts: Sequence[Manuscript]) -> str:
    closing_positions = [match.start() for match in re.finditer(r"</urlset>", document)]
    if len(closing_positions) != 1:
        raise BuildError("sitemap.xml: expected one closing urlset")
    blocks = _url_block_values(document)
    new_urls = _sitemap_new_urls(manuscripts)
    present_positions = [index for index, (loc, _, _) in enumerate(blocks) if loc in set(new_urls)]
    if not present_positions:
        if len(blocks) != EXPECTED_EXISTING_HTML:
            raise BuildError(f"sitemap.xml: expected 14624 existing URL blocks, got {len(blocks)}")
        position = closing_positions[0]
        prefix, suffix = document[:position], document[position:]
        newline = "\r\n" if "\r\n" in document else "\n"
        if not prefix.endswith(newline):
            raise BuildError("sitemap.xml: closing urlset must begin on its own line")
        appended = "".join(
            f"  <url>{newline}    <loc>{_escape(url)}</loc>{newline}    <lastmod>{PUBLISHED_DATE}</lastmod>{newline}  </url>{newline}"
            for url in new_urls
        )
        updated = prefix + appended + suffix
        # The original prefix, including all URL blocks and lastmods, is byte-for-byte unchanged.
        if not updated.startswith(prefix):
            raise BuildError("sitemap.xml: existing raw prefix preservation failed")
        return updated
    if len(present_positions) != len(new_urls):
        raise BuildError("sitemap.xml: partial new grade URL set detected")
    if len(blocks) != EXPECTED_FINAL_HTML or tuple(loc for loc, _, _ in blocks[-len(new_urls):]) != new_urls:
        raise BuildError("sitemap.xml: new URLs are not the final 373 blocks in required order")
    if any(lastmod != PUBLISHED_DATE for _, lastmod, _ in blocks[-len(new_urls):]):
        raise BuildError("sitemap.xml: new grade URL lastmod mismatch")
    return document


def _update_llms(document: str) -> str:
    marker_count = document.count(LLMS_MARKER)
    block = (
        f"{LLMS_MARKER}\n\n"
        f"- 학년별학원: {SITE_ORIGIN}/학년별학원/\n"
        "  - 학생 학년을 먼저 선택해 현재 제공되는 과목별 지역 안내를 찾는 핵심 허브입니다.\n"
        f"- 중3 수학학원: {SITE_ORIGIN}/학년별학원/중3수학학원/\n"
        "  - 중3 수학 진단·학교 자료·오답 재학습·상담 기준을 371개 동네별 원고로 안내합니다.\n"
    )
    if marker_count == 0:
        separator = "\n" if document.endswith(("\n", "\r")) else "\n\n"
        return document + separator + block
    if marker_count != 1:
        raise BuildError("llms.txt: duplicate grade hub markers")
    marker_index = document.index(LLMS_MARKER)
    if document[marker_index:] != block:
        raise BuildError("llms.txt: existing grade block conflicts with canonical block")
    return document


def _transform_existing_html(rel: Path, document: str) -> str:
    transformed = _insert_grade_nav(document, rel.as_posix())
    if rel == ROOT_REL:
        transformed = _update_root_haspart(transformed)
    return transformed


class _StrictHTMLAudit(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, label: str) -> None:
        super().__init__(convert_charrefs=True)
        self.label = label
        self.stack: list[str] = []
        self.anchors: list[str] = []
        self.images: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self.start_tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = [name.casefold() for name, _ in attrs]
        if len(names) != len(set(names)):
            raise BuildError(f"{self.label}: duplicate HTML attribute on <{tag}>")
        attr_map = {name.casefold(): value or "" for name, value in attrs}
        tag = tag.casefold()
        self.start_tags.append((tag, attr_map))
        if tag == "a" and "href" in attr_map:
            self.anchors.append(attr_map["href"])
        if tag == "img":
            self.images.append(attr_map)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if not self.stack or self.stack[-1] != tag:
            expected = self.stack[-1] if self.stack else "none"
            raise BuildError(f"{self.label}: malformed closing </{tag}>; expected </{expected}>")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)

    def close(self) -> None:
        super().close()
        if self.stack:
            raise BuildError(f"{self.label}: unclosed HTML tags: {self.stack[-8:]}")


def _audit_html(document: str, label: str) -> _StrictHTMLAudit:
    audit = _StrictHTMLAudit(label)
    try:
        audit.feed(document)
        audit.close()
    except (BuildError, AssertionError) as exc:
        if isinstance(exc, BuildError):
            raise
        raise BuildError(f"{label}: HTML parser assertion failed") from exc
    return audit


def _schema_types(graph: Sequence[Any]) -> Counter[str]:
    result: Counter[str] = Counter()
    for node in graph:
        if not isinstance(node, dict):
            continue
        value = node.get("@type")
        if isinstance(value, str):
            result[value] += 1
        elif isinstance(value, list):
            result.update(item for item in value if isinstance(item, str))
    return result


def _meta_values(document: str, *, name: str | None = None, property_name: str | None = None) -> list[str]:
    result: list[str] = []
    for tag in re.findall(r"<meta\b[^>]*>", document, re.IGNORECASE):
        selector = "name" if name is not None else "property"
        expected = name if name is not None else property_name
        selector_match = re.search(rf"\b{selector}\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE)
        if selector_match and selector_match.group(2).casefold() == str(expected).casefold():
            result.append(_extract_attr_from_tag(tag, "content", "metadata audit"))
    return result


def _canonical_values(document: str) -> list[str]:
    values: list[str] = []
    for tag in re.findall(r"<link\b[^>]*>", document, re.IGNORECASE):
        rel_match = re.search(r"\brel\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE)
        if rel_match and "canonical" in rel_match.group(2).casefold().split():
            values.append(_extract_attr_from_tag(tag, "href", "canonical audit"))
    return values


def _validate_nav(document: str, label: str, *, grade_active: bool) -> None:
    nav_matches = list(NAV_RE.finditer(document))
    if len(nav_matches) != 1:
        raise BuildError(f"{label}: final nav-links cardinality failed")
    anchors = list(ANCHOR_RE.finditer(nav_matches[0].group(2)))
    subjects = [i for i, anchor in enumerate(anchors) if _anchor_text(anchor) == "과목별학원"]
    grades = [i for i, anchor in enumerate(anchors) if _anchor_href(anchor) == GRADE_NAV_HREF]
    if len(subjects) != 1 or len(grades) != 1 or grades[0] != subjects[0] + 1:
        raise BuildError(f"{label}: final grade navigation placement failed")
    grade_anchor = anchors[grades[0]]
    class_match = re.search(r"\bclass\s*=\s*([\"'])(.*?)\1", grade_anchor.group("attrs"), re.IGNORECASE)
    is_active = bool(class_match and "active" in class_match.group(2).split())
    if is_active != grade_active:
        raise BuildError(f"{label}: grade active state mismatch")


def _validate_detail(
    document: str,
    manuscript: Manuscript,
    record: CenterRecord,
    assets: PageAssets,
) -> None:
    label = manuscript.member_name
    audit = _audit_html(document, label)
    _validate_nav(document, label, grade_active=True)
    status = "supported" if record.supports_middle3_math else "unconfirmed-grade"
    expected_main = [attrs for tag, attrs in audit.start_tags if tag == "main" and attrs.get("data-grade-page") == "middle3-math"]
    if len(expected_main) != 1 or expected_main[0].get("data-source-status") != status:
        raise BuildError(f"{label}: detail main source status hook mismatch")
    if document.count(" data-manuscript>") != 1:
        raise BuildError(f"{label}: manuscript article hook count mismatch")
    section_values = re.findall(r'data-manuscript-section="([0-9]{2})"', document)
    if section_values != ["01", "02", "03", "04", "05", "06"]:
        raise BuildError(f"{label}: manuscript section hooks mismatch")
    if document.count(" data-faq>") != 1 or document.count(" data-review>") != 1:
        raise BuildError(f"{label}: FAQ/review hooks mismatch")
    for field in ("grade", "middle-schools", "address", "registration", "fee"):
        if len(re.findall(rf'data-source-field="{re.escape(field)}"', document)) != 1:
            raise BuildError(f"{label}: source fact hook {field} mismatch")
    school_hook = re.search(
        r'<div\b[^>]*data-source-field="middle-schools"[^>]*data-source-status="([^"]+)"[^>]*>',
        document,
    )
    expected_school_status = "provided" if record.middle_schools else "missing"
    if not school_hook or school_hook.group(1) != expected_school_status:
        raise BuildError(f"{label}: middle-school source status mismatch")
    detail_url = _encoded_site_url("학년별학원", "중3수학학원", record.locality)
    image_url = SITE_ORIGIN + quote(assets.representative_src, safe="/%")
    if _canonical_values(document) != [detail_url] or _meta_values(document, property_name="og:url") != [detail_url]:
        raise BuildError(f"{label}: canonical/og:url parity failed")
    if _meta_values(document, property_name="og:image") != [image_url] or _meta_values(document, name="twitter:image") != [image_url]:
        raise BuildError(f"{label}: representative head parity failed")
    title_match = re.search(r"<title>(.*?)</title>", document, re.DOTALL | re.IGNORECASE)
    h1_match = re.search(r"<h1>(.*?)</h1>", document, re.DOTALL | re.IGNORECASE)
    if not title_match or html.unescape(title_match.group(1)) != f"{manuscript.title} | 와와학습코칭센터":
        raise BuildError(f"{label}: title mismatch")
    if not h1_match or html.unescape(re.sub(r"<[^>]+>", "", h1_match.group(1))) != manuscript.title:
        raise BuildError(f"{label}: H1 mismatch")
    if any(img.get("src") == assets.representative_src for img in audit.images):
        raise BuildError(f"{label}: representative image must not appear in DOM")
    body_images = [img for img in audit.images if img.get("data-image-role") == "body"]
    map_images = [img for img in audit.images if img.get("data-image-role") == "map"]
    if len(body_images) != 1 or len(map_images) != 1:
        raise BuildError(f"{label}: body/map image role cardinality failed")
    body, map_image = body_images[0], map_images[0]
    if (
        body.get("src") != assets.body_src
        or body.get("loading") != "eager"
        or body.get("fetchpriority") != "high"
        or body.get("decoding") != "async"
        or (body.get("width"), body.get("height")) != tuple(map(str, assets.body_size))
    ):
        raise BuildError(f"{label}: visible body image policy failed")
    if (
        map_image.get("src") != assets.map_src
        or map_image.get("loading") != "lazy"
        or map_image.get("decoding") != "async"
        or (map_image.get("width"), map_image.get("height")) != tuple(map(str, assets.map_size))
    ):
        raise BuildError(f"{label}: map image policy failed")
    jsonld, _ = _extract_jsonld_graph(document, label)
    graph = jsonld["@graph"]
    types = _schema_types(graph)
    for required_type in ("WebPage", "EducationalOrganization", "LocalBusiness", "BreadcrumbList", "Article", "FAQPage", "ItemList", "ImageObject"):
        if types[required_type] != 1:
            raise BuildError(f"{label}: schema type {required_type} count mismatch")
    if record.supports_middle3_math:
        if types["Service"] != 1 or types["Offer"] != 1:
            raise BuildError(f"{label}: supported Service/Offer schema missing")
        service = _find_graph_node(graph, "Service", label)
        audience = service.get("audience")
        if not isinstance(audience, dict) or "중3" not in str(audience.get("audienceType", "")):
            raise BuildError(f"{label}: supported audience is not explicitly 중3")
        for node_type in ("EducationalOrganization", "LocalBusiness"):
            if "makesOffer" not in _find_graph_node(graph, node_type, label):
                raise BuildError(f"{label}: supported physical {node_type}.makesOffer missing")
    else:
        if types["Service"] or types["Offer"]:
            raise BuildError(f"{label}: unconfirmed page must contain no Service/Offer type")
        for node_type in ("EducationalOrganization", "LocalBusiness"):
            if "makesOffer" in _find_graph_node(graph, node_type, label):
                raise BuildError(f"{label}: unconfirmed physical node must contain no makesOffer")
        if "해당 센터의 중3 수학 수업 제공을 뜻하지 않습니다" not in document:
            raise BuildError(f"{label}: explicit unconfirmed-grade disclaimer missing")
    article = _find_graph_node(graph, "Article", label)
    if article.get("headline") != manuscript.title or article.get("image") != image_url:
        raise BuildError(f"{label}: Article headline/image parity failed")
    if article.get("articleSection") != [section.heading for section in manuscript.sections]:
        raise BuildError(f"{label}: Article.articleSection parity failed")
    image_object = _find_graph_node(graph, "ImageObject", label)
    if image_object.get("url") != image_url or image_object.get("contentUrl") != image_url:
        raise BuildError(f"{label}: ImageObject representative parity failed")
    faq_page = _find_graph_node(graph, "FAQPage", label)
    faq_entities = faq_page.get("mainEntity")
    expected_faqs = [
        {"@type": "Question", "name": faq.question, "acceptedAnswer": {"@type": "Answer", "text": faq.answer}}
        for faq in manuscript.faqs
    ]
    if faq_entities != expected_faqs:
        raise BuildError(f"{label}: FAQ schema/source parity failed")
    text_content = " ".join(audit.text_parts)
    for school in record.middle_schools:
        if school not in text_content:
            raise BuildError(f"{label}: schema/source school is not visible: {school}")
    if record.middle_schools:
        school_fact = re.search(
            r'<div\b[^>]*data-source-field="middle-schools"[^>]*>(.*?)</div>\s*</dd>\s*</div>',
            document,
            re.DOTALL | re.IGNORECASE,
        )
        if not school_fact:
            raise BuildError(f"{label}: middle-school visible fact extraction failed")
        visible_school_chips = tuple(
            html.unescape(value) for value in re.findall(r"<span>(.*?)</span>", school_fact.group(1), re.DOTALL)
        )
    else:
        visible_school_chips = ()
    if visible_school_chips != record.middle_schools:
        raise BuildError(f"{label}: middle-school visible chip/source parity failed")
    for node_type in ("WebPage", "Article"):
        node = _find_graph_node(graph, node_type, label)
        mention_names = [
            mention.get("name") for mention in node.get("mentions", [])
            if isinstance(mention, dict) and mention.get("name") in set(record.middle_schools)
        ]
        if tuple(mention_names) != record.middle_schools:
            raise BuildError(f"{label}: {node_type} middle-school mentions/source parity failed")
    article_match = re.search(r"<article\b[^>]*data-manuscript[^>]*>(.*?)</article>", document, re.DOTALL | re.IGNORECASE)
    if not article_match:
        raise BuildError(f"{label}: manuscript article not found")
    article_html = article_match.group(1)
    for paragraph in manuscript.intro_paragraphs:
        if article_html.count(_paragraph_markup(paragraph)) != 1:
            raise BuildError(f"{label}: intro manuscript paragraph parity failed")
    for section in manuscript.sections:
        if article_html.count(_escape(section.heading)) != 1:
            raise BuildError(f"{label}: manuscript H2 text parity failed")
        for paragraph in section.paragraphs:
            if article_html.count(_paragraph_markup(paragraph)) != 1:
                raise BuildError(f"{label}: manuscript paragraph parity failed")
    faq_wrapper = re.search(r"<div\b[^>]*data-faq[^>]*>(.*?)</div></section>", document, re.DOTALL | re.IGNORECASE)
    if not faq_wrapper:
        raise BuildError(f"{label}: FAQ wrapper extraction failed")
    for faq in manuscript.faqs:
        if faq_wrapper.group(1).count(_escape(faq.question)) != 1 or faq_wrapper.group(1).count(_paragraph_markup(faq.answer)) != 1:
            raise BuildError(f"{label}: visible FAQ source parity failed")
    disclaimer_position = document.find(_escape(manuscript.review_disclaimer))
    quote_position = document.find(_escape(manuscript.review_quote))
    if disclaimer_position < 0 or quote_position <= disclaimer_position:
        raise BuildError(f"{label}: review order/source parity failed")


def _decoded_internal_route(href: str) -> str | None:
    parsed = urlsplit(href)
    if parsed.scheme in ("tel", "mailto", "javascript") or href.startswith("#"):
        return None
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in ("http", "https") or parsed.netloc != "wawa-center.kr":
            return None
    path = unquote(parsed.path or "/")
    if not path.startswith("/"):
        raise BuildError(f"generated anchor must be root-relative or canonical absolute: {href}")
    if not path.endswith("/"):
        path += "/"
    return path


def _route_for_rel(rel: Path) -> str:
    if rel == ROOT_REL:
        return "/"
    return "/" + rel.parent.as_posix() + "/"


def _validate_generated_links(documents: Mapping[Path, str | bytes], generated_paths: set[Path]) -> int:
    routes = {_route_for_rel(rel) for rel in documents if rel.name == "index.html"}
    checked = 0
    for rel in generated_paths:
        document = _decode_utf8(_as_bytes(documents[rel]), rel.as_posix())
        audit = _audit_html(document, rel.as_posix())
        for href in audit.anchors:
            route = _decoded_internal_route(href)
            if route is None:
                continue
            checked += 1
            if route not in routes:
                raise BuildError(f"{rel}: broken generated internal link: {href}")
    return checked


def _normalized_fragment(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", value)


def _duplication_metrics(manuscripts: Sequence[Manuscript]) -> dict[str, int]:
    document_sets: dict[str, set[str]] = defaultdict(set)
    within = 0
    paragraph_count = 0
    for manuscript in manuscripts:
        fragments = [
            *manuscript.intro_paragraphs,
            *(paragraph for section in manuscript.sections for paragraph in section.paragraphs),
            *(section.heading for section in manuscript.sections),
            *(faq.question for faq in manuscript.faqs),
            *(faq.answer for faq in manuscript.faqs),
            manuscript.review_disclaimer,
            manuscript.review_quote,
        ]
        paragraph_count += len(manuscript.intro_paragraphs) + sum(len(section.paragraphs) for section in manuscript.sections)
        normalized = [_normalized_fragment(fragment) for fragment in fragments]
        within += len(normalized) - len(set(normalized))
        for fragment in set(normalized):
            document_sets[fragment].add(manuscript.locality)
    cross = [len(localities) for localities in document_sets.values() if len(localities) > 1]
    return {
        "manuscript_body_paragraphs": paragraph_count,
        "normalized_within_page_duplicates_observed": within,
        "normalized_cross_document_duplicate_keys_observed": len(cross),
        "normalized_max_cross_document_frequency": max(cross, default=1),
    }


def _generated_visible_duplication_metrics(
    documents: Mapping[Path, str | bytes], generated_paths: Iterable[Path]
) -> dict[str, int]:
    pattern = re.compile(
        r"<(?P<tag>p|li|blockquote|summary)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
        re.IGNORECASE | re.DOTALL,
    )
    cross_documents: dict[str, set[str]] = defaultdict(set)
    within_duplicates = 0
    block_count = 0
    for rel in generated_paths:
        document = _decode_utf8(_as_bytes(documents[rel]), rel.as_posix())
        blocks: list[str] = []
        for match in pattern.finditer(document):
            value = html.unescape(re.sub(r"<[^>]+>", " ", match.group("body")))
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                blocks.append(_normalized_fragment(value))
        block_count += len(blocks)
        within_duplicates += len(blocks) - len(set(blocks))
        for block in set(blocks):
            cross_documents[block].add(rel.as_posix())
    cross = [len(paths) for paths in cross_documents.values() if len(paths) > 1]
    return {
        "generated_visible_prose_blocks": block_count,
        "generated_visible_within_page_duplicates": within_duplicates,
        "generated_visible_cross_document_duplicate_keys_observed": len(cross),
        "generated_visible_max_cross_document_frequency": max(cross, default=1),
    }


def _manifest_candidate(after_manifest: Mapping[Path, str], source_manifest: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for name, value in sorted(source_manifest.items()):
        digest.update(name.encode("utf-8")); digest.update(b"\0"); digest.update(value.encode("ascii")); digest.update(b"\n")
    for rel in sorted(after_manifest, key=lambda path: path.as_posix()):
        digest.update(rel.as_posix().encode("utf-8")); digest.update(b"\0"); digest.update(after_manifest[rel].encode("ascii")); digest.update(b"\n")
    return digest.hexdigest()


def _crosscheck_physical_source(record: CenterRecord, assets: PageAssets) -> None:
    organization = assets.organization
    if organization.get("name") != record.center_name:
        raise BuildError(f"{record.locality}: generic physical organization name differs from authoritative CSV")
    address = organization.get("address")
    if not isinstance(address, dict) or address.get("streetAddress") != record.address:
        raise BuildError(f"{record.locality}: generic physical address differs from authoritative CSV")
    identifier = organization.get("identifier")
    if not isinstance(identifier, dict) or identifier.get("value") != record.registration_number:
        raise BuildError(f"{record.locality}: generic registration differs from authoritative CSV")
    levels = organization.get("educationalLevel")
    if levels is not None and tuple(levels) != record.math_grades:
        raise BuildError(f"{record.locality}: generic math grades differ from authoritative CSV")
    offers = organization.get("makesOffer")
    offer_urls: set[str] = set()
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict) and isinstance(offer.get("url"), str):
                offer_urls.add(offer["url"])
    if record.tuition_url and record.tuition_url not in offer_urls:
        raise BuildError(f"{record.locality}: generic tuition URL differs from authoritative CSV")
    if not record.tuition_url and offer_urls:
        raise BuildError(f"{record.locality}: generic tuition URL exists but authoritative CSV is blank")


def _validate_directory_pages(parent: str, category: str, manuscripts: Sequence[Manuscript]) -> None:
    parent_audit = _audit_html(parent, "grade parent hub")
    category_audit = _audit_html(category, "middle3 math category hub")
    _validate_nav(parent, "grade parent hub", grade_active=True)
    _validate_nav(category, "middle3 math category hub", grade_active=True)
    parent_mains = [attrs for tag, attrs in parent_audit.start_tags if tag == "main" and attrs.get("data-grade-directory") == "parent"]
    category_mains = [attrs for tag, attrs in category_audit.start_tags if tag == "main" and attrs.get("data-grade-directory") == "middle3-math"]
    if len(parent_mains) != 1 or len(category_mains) != 1:
        raise BuildError("directory main hooks mismatch")
    for hook in ("data-grade-search", "data-grade-clear", "data-grade-status", "data-grade-list"):
        if category.count(hook) < 1:
            raise BuildError(f"category search hook missing: {hook}")
    localities = re.findall(r'data-grade-locality="([^"]+)"', category)
    expected = [manuscript.locality for manuscript in manuscripts]
    if localities != expected:
        raise BuildError("category locality link order/content mismatch")
    query = " 명일동 ".strip().casefold()
    visible = [locality for locality in localities if query in locality.strip().casefold()]
    if visible != ["명일동"]:
        raise BuildError("category 명일동 search synthetic must return exactly one result")
    required_script_fragments = (
        "toLocaleLowerCase('ko-KR')",
        "input.value = ''",
        "update(); input.focus();",
        "'전체 371개 지역'",
    )
    if any(fragment not in category for fragment in required_script_fragments):
        raise BuildError("category clear/reset/normalize behavior contract missing")
    category_json, _ = _extract_jsonld_graph(category, "middle3 math category hub")
    item_list = _find_graph_node(category_json["@graph"], "ItemList", "middle3 math category hub")
    if item_list.get("numberOfItems") != EXPECTED_MANUSCRIPTS or len(item_list.get("itemListElement", [])) != EXPECTED_MANUSCRIPTS:
        raise BuildError("category ItemList count mismatch")
    for label, document in (("grade parent hub", parent), ("middle3 math category hub", category)):
        jsonld, _ = _extract_jsonld_graph(document, label)
        faq_page = _find_graph_node(jsonld["@graph"], "FAQPage", label)
        entities = faq_page.get("mainEntity")
        if not isinstance(entities, list) or len(entities) != 2 or document.count(" data-faq>") != 1:
            raise BuildError(f"{label}: visible FAQ/schema cardinality mismatch")
        for entity in entities:
            question = entity.get("name") if isinstance(entity, dict) else None
            accepted = entity.get("acceptedAnswer") if isinstance(entity, dict) else None
            answer = accepted.get("text") if isinstance(accepted, dict) else None
            if not isinstance(question, str) or not isinstance(answer, str):
                raise BuildError(f"{label}: malformed FAQ schema entity")
            # One visible copy plus one JSON-LD copy; exact source strings must match.
            if document.count(_escape(question)) != 2 or document.count(_escape(answer)) != 2:
                raise BuildError(f"{label}: visible FAQ text does not exactly match FAQPage")


def build_plan(
    root: Path | str,
    zip_path: Path | str,
    common_dir: Path | str,
    current_overrides: Mapping[Path | str, str | bytes] | None = None,
) -> BuildPlan:
    """Build and audit an exact 15,000-document plan without writing anything."""

    root = Path(root).resolve()
    zip_path = Path(zip_path).resolve()
    common_dir = Path(common_dir).resolve()
    if not root.is_dir() or not zip_path.is_file() or not common_dir.is_dir():
        raise BuildError("root, ZIP, and common data directory must already exist")
    pending = [path for path in root.iterdir() if path.is_dir() and path.name.startswith(TRANSACTION_PREFIX)]
    if pending:
        raise BuildError("pending transaction detected; use --apply recovery before building a new plan")
    overrides = _normalize_overrides(root, current_overrides)
    manuscripts, manuscript_metrics = _load_manuscripts(zip_path)
    centers, center_metrics = _load_centers(common_dir)
    manuscript_localities = [item.locality for item in manuscripts]
    if set(manuscript_localities) != set(centers):
        missing = sorted(set(centers) - set(manuscript_localities))
        extra = sorted(set(manuscript_localities) - set(centers))
        raise BuildError(f"ZIP/center locality set mismatch; missing={missing[:4]}, extra={extra[:4]}")

    html_paths = _enumerate_html(root, overrides)
    new_html_paths = {PARENT_REL, CATEGORY_REL, *(_detail_rel(locality) for locality in manuscript_localities)}
    present_new = html_paths & new_html_paths
    if present_new and present_new != new_html_paths:
        raise BuildError(f"partial generated grade tree detected: {len(present_new)}/{len(new_html_paths)}")
    existing_html_paths = html_paths - new_html_paths
    if len(existing_html_paths) != EXPECTED_EXISTING_HTML:
        raise BuildError(f"expected {EXPECTED_EXISTING_HTML} existing HTML files, got {len(existing_html_paths)}")
    if ROOT_REL not in existing_html_paths:
        raise BuildError("root index is missing from existing HTML set")
    for locality in manuscript_localities:
        if _generic_math_rel(locality) not in existing_html_paths:
            raise BuildError(f"generic math source page missing: {locality}")

    assets_by_locality: dict[str, PageAssets] = {}
    for locality in manuscript_localities:
        rel = _generic_math_rel(locality)
        source_document = _decode_utf8(_read_current_bytes(root, rel, overrides), rel.as_posix())
        assets = _load_page_assets(root, locality, source_document)
        _crosscheck_physical_source(centers[locality], assets)
        assets_by_locality[locality] = assets

    generated: dict[Path, str] = {
        PARENT_REL: _render_parent_hub(),
        CATEGORY_REL: _render_category_hub(manuscripts, centers),
    }
    for index, manuscript in enumerate(manuscripts):
        previous_locality = manuscripts[index - 1].locality
        next_locality = manuscripts[(index + 1) % len(manuscripts)].locality
        generated[_detail_rel(manuscript.locality)] = _render_detail(
            manuscript,
            centers[manuscript.locality],
            assets_by_locality[manuscript.locality],
            previous_locality,
            next_locality,
        )

    documents: dict[Path, str | bytes] = {}
    for rel in sorted(existing_html_paths, key=lambda value: value.as_posix()):
        current = _decode_utf8(_read_current_bytes(root, rel, overrides), rel.as_posix())
        documents[rel] = _transform_existing_html(rel, current)
    documents.update(generated)
    header_current = _decode_utf8(_read_current_bytes(root, HEADER_CSS_REL, overrides), HEADER_CSS_REL.as_posix())
    sitemap_current = _decode_utf8(_read_current_bytes(root, SITEMAP_REL, overrides), SITEMAP_REL.as_posix())
    llms_current = _decode_utf8(_read_current_bytes(root, LLMS_REL, overrides), LLMS_REL.as_posix())
    documents[HEADER_CSS_REL] = _update_header_css(header_current)
    documents[SITEMAP_REL] = _update_sitemap(sitemap_current, manuscripts)
    documents[LLMS_REL] = _update_llms(llms_current)
    if len(documents) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError(f"authorized document count must be 15000, got {len(documents)}")
    extra_overrides = set(overrides) - set(documents)
    if extra_overrides:
        raise BuildError(f"current_overrides contains unauthorized paths: {sorted(map(str, extra_overrides))[:4]}")

    _validate_directory_pages(generated[PARENT_REL], generated[CATEGORY_REL], manuscripts)
    for manuscript in manuscripts:
        _validate_detail(
            generated[_detail_rel(manuscript.locality)],
            manuscript,
            centers[manuscript.locality],
            assets_by_locality[manuscript.locality],
        )
    internal_links_checked = _validate_generated_links(documents, new_html_paths)
    generated_duplication = _generated_visible_duplication_metrics(documents, new_html_paths)
    if generated_duplication["generated_visible_within_page_duplicates"] != 0:
        raise BuildError(
            "generated visible within-page normalized duplicates: "
            f"{generated_duplication['generated_visible_within_page_duplicates']}"
        )

    nav_count = 0
    for rel in sorted((path for path in documents if path.name == "index.html"), key=lambda value: value.as_posix()):
        document = _decode_utf8(_as_bytes(documents[rel]), rel.as_posix())
        _validate_nav(document, rel.as_posix(), grade_active=rel in new_html_paths)
        nav_count += 1
    if nav_count != EXPECTED_FINAL_HTML:
        raise BuildError("final navigation page count mismatch")

    final_sitemap = _decode_utf8(_as_bytes(documents[SITEMAP_REL]), SITEMAP_REL.as_posix())
    final_sitemap_blocks = _url_block_values(final_sitemap)
    if len(final_sitemap_blocks) != EXPECTED_FINAL_HTML:
        raise BuildError("final sitemap URL count mismatch")
    original_sitemap_blocks = _url_block_values(sitemap_current)
    if tuple(block for _, _, block in final_sitemap_blocks[:EXPECTED_EXISTING_HTML]) != tuple(
        block for _, _, block in original_sitemap_blocks[:EXPECTED_EXISTING_HTML]
    ):
        raise BuildError("existing 14624 sitemap URL blocks did not remain byte-identical")
    if tuple(loc for loc, _, _ in final_sitemap_blocks[-EXPECTED_NEW_HTML:]) != _sitemap_new_urls(manuscripts):
        raise BuildError("final sitemap append order mismatch")
    if any(lastmod != PUBLISHED_DATE for _, lastmod, _ in final_sitemap_blocks[-EXPECTED_NEW_HTML:]):
        raise BuildError("final sitemap new lastmod mismatch")
    final_header = _decode_utf8(_as_bytes(documents[HEADER_CSS_REL]), HEADER_CSS_REL.as_posix())
    if final_header.count("@media (max-width: 1120px) {") != 1 or "@media (max-width: 900px) {" in final_header:
        raise BuildError("final header breakpoint gate failed")
    final_llms = _decode_utf8(_as_bytes(documents[LLMS_REL]), LLMS_REL.as_posix())
    if final_llms.count(LLMS_MARKER) != 1:
        raise BuildError("final llms grade block gate failed")
    llms_grade_block = final_llms[final_llms.index(LLMS_MARKER):]
    expected_raw_llms_lines = (
        f"- 학년별학원: {SITE_ORIGIN}/학년별학원/",
        f"- 중3 수학학원: {SITE_ORIGIN}/학년별학원/중3수학학원/",
    )
    llms_grade_lines = llms_grade_block.splitlines()
    if any(llms_grade_lines.count(line) != 1 for line in expected_raw_llms_lines) or "%ED%95%99%EB%85%84" in llms_grade_block:
        raise BuildError("final llms grade URLs must be exact raw Korean URLs")
    if LLMS_MARKER not in llms_current and not final_llms.startswith(llms_current):
        raise BuildError("llms baseline prefix preservation failed")

    before_manifest: dict[Path, str] = {}
    after_manifest: dict[Path, str] = {}
    before_exists: dict[Path, bool] = {}
    changed: list[Path] = []
    for rel in sorted(documents, key=lambda value: value.as_posix()):
        exists, before = _read_optional_current_bytes(root, rel, overrides)
        after = _as_bytes(documents[rel])
        before_exists[rel] = exists
        before_manifest[rel] = _sha256(before) if exists else ABSENT_SHA256
        after_manifest[rel] = _sha256(after)
        if not exists or before != after:
            changed.append(rel)

    second_pass: list[Path] = []
    for rel in sorted(documents, key=lambda value: value.as_posix()):
        after_text = _decode_utf8(_as_bytes(documents[rel]), rel.as_posix())
        if rel.name == "index.html":
            second = _transform_existing_html(rel, after_text) if rel in existing_html_paths else _insert_grade_nav(after_text, rel.as_posix())
        elif rel == HEADER_CSS_REL:
            second = _update_header_css(after_text)
        elif rel == SITEMAP_REL:
            second = _update_sitemap(after_text, manuscripts)
        elif rel == LLMS_REL:
            second = _update_llms(after_text)
        else:
            raise BuildError(f"unexpected authorized document during second pass: {rel}")
        if _as_bytes(second) != _as_bytes(documents[rel]):
            second_pass.append(rel)
    if second_pass:
        raise BuildError(f"second-pass idempotency failed for {len(second_pass)} paths")

    duplication = _duplication_metrics(manuscripts)
    if duplication["manuscript_body_paragraphs"] != 4_847:
        raise BuildError(f"manuscript body paragraph count mismatch: {duplication['manuscript_body_paragraphs']}")
    visible_school_pairs = sum(
        school in manuscript.raw_text
        for manuscript in manuscripts
        for school in centers[manuscript.locality].middle_school_source_tokens
    )
    unique_visible_school_pairs = sum(
        school in manuscript.raw_text
        for manuscript in manuscripts
        for school in centers[manuscript.locality].middle_schools
    )
    if visible_school_pairs != 529 or unique_visible_school_pairs != 529:
        raise BuildError(
            "manuscript-visible authoritative middle-school parity failed: "
            f"source={visible_school_pairs}, unique={unique_visible_school_pairs}"
        )
    source_manifest = {
        "manuscript_zip": ZIP_SHA256,
        "center_csv": CENTER_CSV_SHA256,
        "target_school_csv": TARGET_SCHOOL_CSV_SHA256,
    }
    source_metrics = {
        **dict(manuscript_metrics),
        **dict(center_metrics),
        **duplication,
        **generated_duplication,
        "manuscript_visible_authoritative_middle_school_source_token_pairs": visible_school_pairs,
        "manuscript_visible_unique_authoritative_middle_school_pairs": unique_visible_school_pairs,
        "screen_unique_authoritative_middle_school_mentions": sum(
            len(record.middle_schools) for record in centers.values()
        ),
        "manuscript_control_characters": 0,
        "manuscript_trailing_whitespace_lines": 0,
        "pinned_center_csv_known_backspaces_sanitized": 1,
        "pinned_center_csv_source_trailing_whitespace_lines_trimmed_by_cell_parser": 5,
    }
    before_metrics = {
        "html_documents": len(html_paths),
        "existing_html_documents": len(existing_html_paths),
        "already_present_new_html": len(present_new),
        "sitemap_urls": len(original_sitemap_blocks),
        "llms_grade_blocks": llms_current.count(LLMS_MARKER),
        "header_900_breakpoints": header_current.count("@media (max-width: 900px) {"),
        "header_1120_breakpoints": header_current.count("@media (max-width: 1120px) {"),
    }
    after_metrics = {
        "authorized_documents": len(documents),
        "html_documents": EXPECTED_FINAL_HTML,
        "new_html_documents": EXPECTED_NEW_HTML,
        "detail_documents": EXPECTED_MANUSCRIPTS,
        "nav_grade_links": nav_count,
        "nav_grade_active_pages": EXPECTED_NEW_HTML,
        "sitemap_urls": len(final_sitemap_blocks),
        "sitemap_existing_raw_blocks_preserved": EXPECTED_EXISTING_HTML,
        "sitemap_new_urls_appended": EXPECTED_NEW_HTML,
        "sitemap_new_lastmod": PUBLISHED_DATE,
        "llms_grade_blocks": 1,
        "root_grade_haspart": 1,
        "source_fact_nodes": EXPECTED_MANUSCRIPTS * 5,
        "body_image_policy_pages": EXPECTED_MANUSCRIPTS,
        "map_image_policy_pages": EXPECTED_MANUSCRIPTS,
        "representative_image_dom_nodes": 0,
        "representative_head_schema_parity_pages": EXPECTED_MANUSCRIPTS,
        "supported_service_offer_pages": EXPECTED_SUPPORTED,
        "unconfirmed_no_service_offer_pages": EXPECTED_UNSUPPORTED,
        "faq_source_schema_parity": EXPECTED_FAQS,
        "review_source_parity": EXPECTED_MANUSCRIPTS,
        "manuscript_h2_source_parity": EXPECTED_MANUSCRIPT_H2,
        "internal_links_checked": internal_links_checked,
        "malformed_generated_html": 0,
        "generated_trailing_whitespace_lines": 0,
        "generated_control_characters": 0,
        "second_pass_changes": len(second_pass),
    }
    metrics = {
        "changed_paths": len(changed),
        "unchanged_paths": len(documents) - len(changed),
        "facts_assets_nav_sitemap_gate": "pass",
        **source_metrics,
        **{f"after_{key}": value for key, value in after_metrics.items()},
    }
    candidate = _manifest_candidate(after_manifest, source_manifest)
    return BuildPlan(
        root=root,
        authorized_documents=MappingProxyType(documents),
        changed_paths=tuple(changed),
        second_pass_changes=tuple(second_pass),
        source_manifest=MappingProxyType(source_manifest),
        before_manifest=MappingProxyType(before_manifest),
        after_manifest=MappingProxyType(after_manifest),
        before_exists=MappingProxyType(before_exists),
        source_metrics=MappingProxyType(source_metrics),
        before_metrics=MappingProxyType(before_metrics),
        after_metrics=MappingProxyType(after_metrics),
        metrics=MappingProxyType(metrics),
        candidate_sha256=candidate,
    )


def _safe_target(root: Path, rel: Path) -> Path:
    rel = _safe_relative_path(root, rel)
    root_resolved = root.resolve()
    target = root_resolved / rel
    current = root_resolved
    for part in rel.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise BuildError(f"transaction path contains a symlink: {rel}")
    try:
        target.resolve(strict=False).relative_to(root_resolved)
    except ValueError as exc:
        raise BuildError(f"transaction target escapes root: {rel}") from exc
    return target


def _fsync_file(path: Path) -> None:
    # Windows requires a writable descriptor for FlushFileBuffers/os.fsync.
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes_fsync(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    _write_bytes_fsync(temporary, data)
    os.replace(temporary, path)
    _fsync_file(path)
    _fsync_directory(path.parent)


def _transaction_directory_ok(root: Path, transaction: Path) -> bool:
    try:
        return (
            transaction.parent.resolve() == root.resolve()
            and transaction.name.startswith(TRANSACTION_PREFIX)
            and transaction.resolve(strict=False).parent == root.resolve()
            and not transaction.is_symlink()
        )
    except OSError:
        return False


def _remove_transaction_directory(root: Path, transaction: Path) -> None:
    if not _transaction_directory_ok(root, transaction):
        raise BuildError(f"refusing to remove unsafe transaction directory: {transaction}")
    if transaction.exists():
        shutil.rmtree(transaction)
        _fsync_directory(root)


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"{label}: unreadable transaction JSON: {path}") from exc


def _load_transaction_manifest(root: Path, transaction: Path) -> dict[str, Any]:
    manifest = _read_json(transaction / "manifest.json", "transaction manifest")
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("root") != str(root.resolve()):
        raise BuildError(f"invalid transaction manifest identity: {transaction}")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise BuildError(f"transaction manifest has no entries: {transaction}")
    seen: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise BuildError("transaction manifest entry is not an object")
        rel = _safe_relative_path(root, str(entry.get("path", "")))
        if rel in seen:
            raise BuildError(f"duplicate transaction manifest path: {rel}")
        seen.add(rel)
        for field in ("before_sha256", "after_sha256"):
            value = entry.get(field)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise BuildError(f"transaction manifest has invalid {field}: {rel}")
        if not isinstance(entry.get("before_exists"), bool):
            raise BuildError(f"transaction manifest has invalid before_exists: {rel}")
    return manifest


def _target_state(root: Path, transaction: Path, entry: Mapping[str, Any]) -> str:
    rel = _safe_relative_path(root, str(entry["path"]))
    target = _safe_target(root, rel)
    stage = transaction / "stage" / rel
    target_exists = target.is_file()
    stage_exists = stage.is_file()
    target_hash = _sha256(target.read_bytes()) if target_exists else None
    stage_hash = _sha256(stage.read_bytes()) if stage_exists else None
    before_exists = bool(entry["before_exists"])
    before_hash = str(entry["before_sha256"])
    after_hash = str(entry["after_sha256"])
    before_target = target_exists and before_exists and target_hash == before_hash
    if not before_exists and not target_exists:
        before_target = True
    if before_target and stage_exists and stage_hash == after_hash:
        return "not-swapped"
    if target_exists and target_hash == after_hash and not stage_exists:
        return "swapped"
    raise BuildError(
        f"transaction path is neither expected before/staged nor after/swapped state: {rel}"
    )


def _remove_empty_new_parents(root: Path, rel: Path) -> None:
    current = (root / rel).parent
    while current != root:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _rollback_transaction(root: Path, transaction: Path) -> None:
    if not _transaction_directory_ok(root, transaction):
        raise BuildError("unsafe transaction rollback directory")
    manifest = _load_transaction_manifest(root, transaction)
    entries = list(manifest["entries"])
    states = [(entry, _target_state(root, transaction, entry)) for entry in entries]
    for entry, state in reversed(states):
        if state != "swapped":
            continue
        rel = _safe_relative_path(root, str(entry["path"]))
        target = _safe_target(root, rel)
        if entry["before_exists"]:
            backup = transaction / "backup" / rel
            if not backup.is_file() or _sha256(backup.read_bytes()) != entry["before_sha256"]:
                raise BuildError(f"rollback backup missing or hash-invalid: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup, target)
            _fsync_file(target)
            _fsync_directory(target.parent)
        else:
            if not target.is_file() or _sha256(target.read_bytes()) != entry["after_sha256"]:
                raise BuildError(f"rollback new target hash mismatch: {rel}")
            target.unlink()
            _fsync_directory(target.parent)
            _remove_empty_new_parents(root, rel)
    for entry in entries:
        rel = _safe_relative_path(root, str(entry["path"]))
        target = _safe_target(root, rel)
        if entry["before_exists"]:
            if not target.is_file() or _sha256(target.read_bytes()) != entry["before_sha256"]:
                raise BuildError(f"rollback verification failed: {rel}")
        elif target.exists():
            raise BuildError(f"rollback failed to remove new target: {rel}")
    _atomic_json(transaction / "state.json", {"state": "rolled-back", "time": time.time()})
    _remove_transaction_directory(root, transaction)


def _recover_transaction(root: Path, transaction: Path) -> str:
    if not _transaction_directory_ok(root, transaction):
        raise BuildError(f"unsafe transaction directory found: {transaction}")
    state_path = transaction / "state.json"
    manifest_path = transaction / "manifest.json"
    if not state_path.exists():
        if manifest_path.exists():
            raise BuildError(f"transaction has manifest but no state: {transaction}")
        _remove_transaction_directory(root, transaction)
        return "discarded-empty"
    state_value = _read_json(state_path, "transaction state")
    state = state_value.get("state") if isinstance(state_value, dict) else None
    if state in ("preparing", "prepared"):
        if manifest_path.exists():
            manifest = _load_transaction_manifest(root, transaction)
            for entry in manifest["entries"]:
                if _target_state(root, transaction, entry) != "not-swapped":
                    raise BuildError("prepared transaction unexpectedly changed a target")
        _remove_transaction_directory(root, transaction)
        return "discarded-prepared"
    if state == "committing":
        _rollback_transaction(root, transaction)
        return "rolled-back-committing"
    if state == "committed":
        manifest = _load_transaction_manifest(root, transaction)
        for entry in manifest["entries"]:
            rel = _safe_relative_path(root, str(entry["path"]))
            target = _safe_target(root, rel)
            if not target.is_file() or _sha256(target.read_bytes()) != entry["after_sha256"]:
                raise BuildError(f"committed transaction target verification failed: {rel}")
        _remove_transaction_directory(root, transaction)
        return "cleaned-committed"
    if state == "rolled-back":
        _remove_transaction_directory(root, transaction)
        return "cleaned-rolled-back"
    raise BuildError(f"unknown transaction state {state!r}: {transaction}")


def recover_transactions(root: Path | str) -> tuple[str, ...]:
    root = Path(root).resolve()
    results: list[str] = []
    for transaction in sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.startswith(TRANSACTION_PREFIX)),
        key=lambda path: path.name,
    ):
        results.append(_recover_transaction(root, transaction))
    return tuple(results)


class _SimulatedCrash(BaseException):
    pass


def _transaction_apply(
    root: Path,
    documents: Mapping[Path, str | bytes],
    before_exists: Mapping[Path, bool],
    before_manifest: Mapping[Path, str],
    after_manifest: Mapping[Path, str],
    *,
    fault_after: int | None = None,
    simulate_crash_after: int | None = None,
) -> None:
    root = root.resolve()
    if not documents:
        return
    rels = sorted(documents, key=lambda path: path.as_posix())
    if set(rels) != set(before_exists) or set(rels) != set(before_manifest) or set(rels) != set(after_manifest):
        raise BuildError("transaction mapping key sets differ")
    for rel in rels:
        target = _safe_target(root, rel)
        exists = target.is_file()
        if exists != before_exists[rel]:
            raise BuildError(f"transaction preflight existence changed: {rel}")
        current_hash = _sha256(target.read_bytes()) if exists else ABSENT_SHA256
        if current_hash != before_manifest[rel]:
            raise BuildError(f"transaction preflight hash changed: {rel}")
        if _sha256(_as_bytes(documents[rel])) != after_manifest[rel]:
            raise BuildError(f"transaction output hash mismatch: {rel}")
    transaction = root / f"{TRANSACTION_PREFIX}{uuid4().hex}"
    transaction.mkdir(parents=False, exist_ok=False)
    _fsync_directory(root)
    _atomic_json(transaction / "state.json", {"state": "preparing", "time": time.time()})
    entries: list[dict[str, Any]] = []
    try:
        for rel in rels:
            target = _safe_target(root, rel)
            stage = transaction / "stage" / rel
            backup = transaction / "backup" / rel
            _write_bytes_fsync(stage, _as_bytes(documents[rel]))
            if before_exists[rel]:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                _fsync_file(backup)
                _fsync_directory(backup.parent)
                if _sha256(backup.read_bytes()) != before_manifest[rel]:
                    raise BuildError(f"transaction backup verification failed: {rel}")
            entries.append(
                {
                    "path": rel.as_posix(),
                    "before_exists": before_exists[rel],
                    "before_sha256": before_manifest[rel],
                    "after_sha256": after_manifest[rel],
                }
            )
        manifest = {"version": 1, "root": str(root), "created": time.time(), "entries": entries}
        _atomic_json(transaction / "manifest.json", manifest)
        _atomic_json(transaction / "state.json", {"state": "prepared", "time": time.time()})
        _atomic_json(transaction / "state.json", {"state": "committing", "time": time.time()})
        commit_log = transaction / "commit.log"
        with commit_log.open("xb") as log_handle:
            for index, rel in enumerate(rels, 1):
                target = _safe_target(root, rel)
                stage = transaction / "stage" / rel
                if not stage.is_file() or _sha256(stage.read_bytes()) != after_manifest[rel]:
                    raise BuildError(f"transaction stage verification failed before swap: {rel}")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, target)
                _fsync_file(target)
                _fsync_directory(target.parent)
                log_handle.write((json.dumps({"index": index, "path": rel.as_posix()}) + "\n").encode("utf-8"))
                log_handle.flush()
                os.fsync(log_handle.fileno())
                if simulate_crash_after is not None and index >= simulate_crash_after:
                    raise _SimulatedCrash()
                if fault_after is not None and index >= fault_after:
                    raise RuntimeError("synthetic transaction fault")
        for rel in rels:
            target = _safe_target(root, rel)
            if not target.is_file() or _sha256(target.read_bytes()) != after_manifest[rel]:
                raise BuildError(f"transaction post-commit verification failed: {rel}")
        _atomic_json(transaction / "state.json", {"state": "committed", "time": time.time()})
        _remove_transaction_directory(root, transaction)
    except _SimulatedCrash:
        raise
    except Exception as exc:
        if transaction.exists() and (transaction / "manifest.json").exists():
            _rollback_transaction(root, transaction)
        elif transaction.exists():
            _remove_transaction_directory(root, transaction)
        if isinstance(exc, BuildError):
            raise
        raise BuildError(f"transaction failed and was rolled back: {exc}") from exc


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def _root_lock(root: Path) -> Iterable[None]:
    root = root.resolve()
    lock_hash = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:24]
    lock_path = Path(tempfile.gettempdir()) / f"wawa-grade3-math-{lock_hash}.lock"
    token = uuid4().hex
    payload = {"token": token, "pid": os.getpid(), "root": str(root), "created": time.time()}
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            break
        except FileExistsError:
            try:
                existing = json.loads(lock_path.read_text(encoding="utf-8"))
                existing_pid = int(existing.get("pid", -1))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise BuildError(f"unreadable transaction lock: {lock_path}") from exc
            if attempt == 0 and not _pid_is_alive(existing_pid):
                lock_path.unlink()
                continue
            raise BuildError(f"another grade3 transaction holds the root lock (pid {existing_pid})")
    else:
        raise BuildError("could not acquire root transaction lock")
    try:
        yield
    finally:
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
            if current.get("token") != token:
                raise BuildError("root lock ownership changed")
            lock_path.unlink()
        except FileNotFoundError:
            raise BuildError("root lock disappeared before release")


def _apply_plan_locked(plan: BuildPlan) -> None:
    if len(plan.authorized_documents) != EXPECTED_AUTHORIZED_DOCUMENTS:
        raise BuildError("refusing to apply a plan without exactly 15000 authorized documents")
    if plan.second_pass_changes:
        raise BuildError("refusing to apply a non-idempotent plan")
    for rel in plan.authorized_documents:
        target = _safe_target(plan.root, rel)
        exists = target.is_file()
        if exists != plan.before_exists[rel]:
            raise BuildError(f"plan preflight existence changed: {rel}")
        current_hash = _sha256(target.read_bytes()) if exists else ABSENT_SHA256
        if current_hash != plan.before_manifest[rel]:
            raise BuildError(f"plan preflight hash changed: {rel}")
    changed_docs = {rel: plan.authorized_documents[rel] for rel in plan.changed_paths}
    changed_exists = {rel: plan.before_exists[rel] for rel in plan.changed_paths}
    changed_before = {rel: plan.before_manifest[rel] for rel in plan.changed_paths}
    changed_after = {rel: plan.after_manifest[rel] for rel in plan.changed_paths}
    _transaction_apply(plan.root, changed_docs, changed_exists, changed_before, changed_after)
    for rel, expected in plan.after_manifest.items():
        target = _safe_target(plan.root, rel)
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            raise BuildError(f"final applied manifest verification failed: {rel}")


def apply_plan(plan: BuildPlan, *, go: str) -> None:
    if go != "APPLY-GO":
        raise BuildError("apply requires exact explicit go token APPLY-GO")
    with _root_lock(plan.root):
        recovered = recover_transactions(plan.root)
        if recovered:
            raise BuildError("recovery changed transaction state; rebuild the plan before applying")
        _apply_plan_locked(plan)


def transaction_self_test() -> Mapping[str, str]:
    with tempfile.TemporaryDirectory(prefix="wawa-grade3-transaction-test-") as temporary:
        root = Path(temporary) / "site"
        root.mkdir()
        try:
            _safe_relative_path(root, Path("..") / "escape.txt")
        except BuildError:
            pass
        else:
            raise BuildError("transaction path-escape synthetic failed")
        existing = Path("existing.txt")
        created = Path("new/deep/created.txt")
        (root / existing).write_bytes(b"before\n")
        documents: dict[Path, str | bytes] = {existing: "after\n", created: "created\n"}
        before_exists = {existing: True, created: False}
        before_manifest = {existing: _sha256(b"before\n"), created: ABSENT_SHA256}
        after_manifest = {rel: _sha256(_as_bytes(value)) for rel, value in documents.items()}
        _transaction_apply(root, documents, before_exists, before_manifest, after_manifest)
        if (root / existing).read_bytes() != b"after\n" or (root / created).read_bytes() != b"created\n":
            raise BuildError("transaction success synthetic failed")

        rollback_docs = {existing: "rollback-attempt\n", Path("fault-new.txt"): "fault-new\n"}
        rollback_exists = {existing: True, Path("fault-new.txt"): False}
        rollback_before = {existing: _sha256(b"after\n"), Path("fault-new.txt"): ABSENT_SHA256}
        rollback_after = {rel: _sha256(_as_bytes(value)) for rel, value in rollback_docs.items()}
        try:
            _transaction_apply(
                root, rollback_docs, rollback_exists, rollback_before, rollback_after, fault_after=1
            )
        except BuildError:
            pass
        else:
            raise BuildError("transaction rollback synthetic did not fault")
        if (root / existing).read_bytes() != b"after\n" or (root / "fault-new.txt").exists():
            raise BuildError("transaction rollback synthetic failed")

        crash_docs = {existing: "crash-attempt\n", Path("crash-new.txt"): "crash-new\n"}
        crash_exists = {existing: True, Path("crash-new.txt"): False}
        crash_before = {existing: _sha256(b"after\n"), Path("crash-new.txt"): ABSENT_SHA256}
        crash_after = {rel: _sha256(_as_bytes(value)) for rel, value in crash_docs.items()}
        try:
            _transaction_apply(
                root, crash_docs, crash_exists, crash_before, crash_after, simulate_crash_after=1
            )
        except _SimulatedCrash:
            pass
        else:
            raise BuildError("transaction recovery synthetic did not simulate a crash")
        recovery = recover_transactions(root)
        if recovery != ("rolled-back-committing",):
            raise BuildError(f"transaction recovery synthetic result mismatch: {recovery}")
        if (root / existing).read_bytes() != b"after\n" or (root / "crash-new.txt").exists():
            raise BuildError("transaction recovery synthetic failed")
        try:
            _transaction_apply(
                root,
                {existing: "should-not-write\n"},
                {existing: True},
                {existing: "0" * 64},
                {existing: _sha256(b"should-not-write\n")},
            )
        except BuildError:
            pass
        else:
            raise BuildError("transaction hash-freeze synthetic failed")
        if (root / existing).read_bytes() != b"after\n":
            raise BuildError("transaction hash-freeze synthetic mutated target")
    return MappingProxyType(
        {
            "success": "pass",
            "rollback": "pass",
            "crash_recovery": "pass",
            "path_escape_rejected": "pass",
            "hash_freeze_rejected": "pass",
        }
    )


def _default_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    desktop = Path.home() / "Desktop"
    zip_path = desktop / "중3 수학학원.zip"
    common_dir = desktop / "홈페이지 정리" / "참고자료" / "공통자료"
    return root, zip_path, common_dir


def _plan_report(plan: BuildPlan, mode: str, transaction_test: Mapping[str, str] | None) -> dict[str, Any]:
    return {
        "mode": mode,
        "root": str(plan.root),
        "candidate_sha256": plan.candidate_sha256,
        "source_manifest": dict(plan.source_manifest),
        "changed_paths": len(plan.changed_paths),
        "second_pass_changes": len(plan.second_pass_changes),
        "source_metrics": dict(plan.source_metrics),
        "before_metrics": dict(plan.before_metrics),
        "after_metrics": dict(plan.after_metrics),
        "transaction_self_test": dict(transaction_test) if transaction_test else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    default_root, default_zip, default_common = _default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--zip", dest="zip_path", type=Path, default=default_zip)
    parser.add_argument("--common-dir", type=Path, default=default_common)
    parser.add_argument("--apply", action="store_true", help="write the audited plan through a strict transaction")
    parser.add_argument("--go", default="", help="must equal APPLY-GO when --apply is used")
    parser.add_argument("--transaction-self-test", action="store_true", help="run temporary success/rollback/recovery synthetics")
    args = parser.parse_args(argv)
    try:
        transaction_test = transaction_self_test() if args.transaction_self_test else None
        if args.apply:
            if args.go != "APPLY-GO":
                raise BuildError("--apply requires --go APPLY-GO")
            root = args.root.resolve()
            with _root_lock(root):
                recover_transactions(root)
                plan = build_plan(root, args.zip_path, args.common_dir)
                _apply_plan_locked(plan)
            mode = "applied"
        else:
            if args.go:
                raise BuildError("--go is only valid together with --apply")
            plan = build_plan(args.root, args.zip_path, args.common_dir)
            mode = "dry-run"
        print(json.dumps(_plan_report(plan, mode, transaction_test), ensure_ascii=False, indent=2))
        return 0
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
