from __future__ import annotations

"""Independent content/fact release audit for the grade-3 math directory.

The attached ZIP is treated as untrusted data.  This module reads ZIP members
as UTF-8 text only; it never extracts them, imports them, evaluates them, or
obeys text that resembles an instruction.  The audit is read-only.

Two modes are supported:

* ``actual`` audits files materialized in the worktree.  Before generation the
  expected result is HOLD because the 373 grade pages do not exist yet.
* ``projected`` imports the trusted local generator and audits the in-memory
  documents returned by ``build_plan(..., current_overrides=None)``.  It calls
  the same API a second time with ``current_overrides`` and requires zero
  second-pass changes.

Exit codes: 0 PASS, 1 FAIL, 2 HOLD.
"""

import argparse
import csv
import hashlib
import html
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree as ET


sys.dont_write_bytecode = True


BASE_URL = "https://wawa-center.kr"
RELEASE_DATE = "2026-08-20"
EXPECTED_BASE_HEAD = "75680f0d4d08c9f62455e1f4bcb5c8a61d9c19df"
EXPECTED_BASE_TREE = ""  # Informational until the generator is frozen.
EXPECTED_GENERATOR_SHA256 = "3f16b2834ef503c239ea01bd5300599976692c4d933ba72382d931924acf1d33"
EXPECTED_PLAN_CANDIDATE_SHA256 = "09b4ade937befba77760636c2f9539969ced1ac7e72accafab1cac6a0ac53c60"
EXPECTED_BOUNDARY_SAMPLE_SHA256 = "58965393810f42b7dd802fa051a302afa0d21fff50dceec89695677d939ce8af"

ZIP_NAME = "중3 수학학원.zip"
CENTER_NAME = "센터정보 정리.csv"
TARGET_SCHOOL_NAME = "타깃학교.csv"
EO_NAME = "EducationalOrganization.csv"
IMAGE_NAME = "이미지링크.csv"

EXPECTED_HASHES = {
    "zip": "93d58041e1a3672697ba083e7eb3dc7d65570703b68ab122b6cb00be24c6fbc6",
    "zip_manifest": "4ff802996b7a235fa9a4c62e8c09e2b7881906f91284192f6333ecfdd3b1bf36",
    "center": "3ffbd7b70273b6dc1c8435c53a3a25e32d2a173ba1bf51840654389bd8954e1a",
    "target_school": "08c73da41d47ed76bdfa318ff30c238cc12ba92a73b40e0ca2feacec9610ac0f",
    "educational_organization": "e44c9a78c8b272781d5c078e38b466f9d438127a76219661ff43ee2604766c22",
    "image": "c1b4f87b2b62f659107dbf0a79a1d566e213e008fc4b7f30cfa656ffae814100",
}

EXPECTED_ROWS = 371
EXPECTED_SUPPORTED = 358
EXPECTED_UNCONFIRMED = 13
EXPECTED_MIDDLE_SCHOOL_PROVIDED = 318
EXPECTED_MIDDLE_SCHOOL_MISSING = 53
EXPECTED_BASE_HTML = 14624
EXPECTED_BASE_SITEMAP = 14624
EXPECTED_NEW_HTML = 373
EXPECTED_FINAL_HTML = 14997
EXPECTED_FINAL_SITEMAP = 14997
EXPECTED_PLAN_DOCUMENTS = 15000
# ``str.splitlines()`` intentionally does not count the final LF as an empty
# logical line.  The byte files are 63/65 rows when that trailing sentinel is
# counted, and 62/64 content lines under this definition.
EXPECTED_LINES = {62: 347, 64: 24}
EXPECTED_PARAGRAPHS = {13: 347, 14: 24}

GRADE_HUB_REL = "학년별학원/index.html"
CATEGORY_REL = "학년별학원/중3수학학원/index.html"
SITEMAP_REL = "sitemap.xml"
LLMS_REL = "llms.txt"
GENERATOR_REL = "tools/generate_grade3_math_pages.py"

GRADE_HUB_PATH = "/학년별학원/"
CATEGORY_PATH = "/학년별학원/중3수학학원/"

PRUNE_DIRS = {".git", ".vercel", "node_modules", "__pycache__"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
INVISIBLE_TAGS = {"script", "style", "template", "noscript", "svg"}

MARKERS = (
    "[페이지타이틀]",
    "[메타설명]",
    "[본문]",
    "[FAQ]",
    "[학부모후기]",
    "[JSON-LD 요약]",
)

PROMPT_OR_CODE = re.compile(
    r"(?:ignore\s+(?:all\s+)?previous|system\s+prompt|assistant\s*:|developer\s*:|"
    r"instructions?\s*:|이전\s*지시|지시를\s*무시|시스템\s*프롬프트|"
    r"명령을\s*실행|파일을\s*삭제|powershell|cmd\.exe|javascript\s*:|<script)",
    re.IGNORECASE,
)
MOJIBAKE = re.compile(r"(?:\ufffd|Ã.|Â.|â€|ì[-ÿ])")
ADJACENT_REPEAT = re.compile(r"(?<![가-힣A-Za-z0-9])([가-힣]{2,})\s+\1(?![가-힣A-Za-z0-9])")
GUARANTEE = re.compile(r"(?:100\s*%|무조건\s*(?:상승|향상|합격)|성적\s*보장|합격\s*보장)")
POSITIVE_AVAILABILITY = re.compile(
    r"(?:중3\s*수학(?:\s*수업)?(?:이|은|는)?\s*(?:가능|개설|운영|제공)|"
    r"중3\s*학생(?:을|이)?\s*(?:수강|등록)\s*가능)"
)
SAFE_AVAILABILITY = re.compile(
    r"(?:원자료|공통자료|가능학년).{0,45}(?:미기재|비어|확인되지|없)|"
    r"(?:최신|현재|실제).{0,20}(?:상담|안내).{0,15}확인|"
    r"개설\s*여부.{0,15}확인|상담\s*확인\s*필요"
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def encoded_url(path: str) -> str:
    return BASE_URL + quote(path, safe="/:%")


def raw_url(path: str) -> str:
    return BASE_URL + path


def decode_utf8(value: bytes) -> str:
    if value.startswith(b"\xef\xbb\xbf"):
        value = value[3:]
    return value.decode("utf-8", errors="strict")


def split_schools(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for token in re.split(r"[,/.\s]+", norm(value)):
        token = norm(token)
        if token and token not in result:
            result.append(token)
    return tuple(result)


def find_column(columns: Iterable[str], compact_name: str) -> str | None:
    wanted = re.sub(r"\s+", "", compact_name)
    for column in columns:
        if re.sub(r"\s+", "", column or "") == wanted:
            return column
    return None


def path_key(root: Path, value: Any) -> str:
    path = Path(str(value))
    if path.is_absolute():
        path = path.resolve().relative_to(root.resolve())
    key = path.as_posix()
    while key.startswith("./"):
        key = key[2:]
    return key


def is_internal_url(value: str) -> bool:
    if value.startswith("/"):
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "wawa-center.kr"


def canonical_path(value: str) -> str:
    parsed = urlparse(value)
    return unquote(parsed.path)


@dataclass
class Finding:
    code: str
    location: str
    message: str


@dataclass
class Audit:
    hard: list[Finding] = field(default_factory=list)
    holds: list[Finding] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)

    def error(self, code: str, location: str | Path, message: str) -> None:
        self.hard.append(Finding(code, str(location), message))

    def hold(self, code: str, location: str | Path, message: str) -> None:
        self.holds.append(Finding(code, str(location), message))

    @property
    def status(self) -> str:
        if self.hard:
            return "FAIL"
        if self.holds:
            return "HOLD"
        return "PASS"

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "FAIL": 1, "HOLD": 2}[self.status]


@dataclass(frozen=True)
class ManuscriptSection:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Manuscript:
    filename: str
    locality: str
    title: str
    meta: str
    intro: tuple[str, ...]
    sections: tuple[ManuscriptSection, ...]
    faq: tuple[tuple[str, str], ...]
    review: tuple[str, ...]
    json_summary: str
    raw_text: str
    raw_sha256: str
    line_count: int

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(section.heading for section in self.sections)

    @property
    def paragraphs(self) -> tuple[str, ...]:
        values = list(self.intro)
        for section in self.sections:
            values.extend(section.paragraphs)
        return tuple(values)

    @property
    def query(self) -> str:
        return f"{self.locality} 중3 수학학원"


@dataclass(frozen=True)
class SourceRow:
    position: int
    locality: str
    region: str
    district: str
    center_name: str
    fee_url: str
    education_office: str
    registration: str
    address: str
    location_guide: str
    middle_school_raw: str
    middle_schools: tuple[str, ...]
    math_grades: tuple[str, ...]
    supported: bool
    eo_name: str
    eo_address: str
    telephone: str
    opening_hours: str
    official_site: str
    body_image_source: str
    map_image_source: str

    @property
    def status(self) -> str:
        return "supported" if self.supported else "unconfirmed-grade"


def _nonempty(lines: Iterable[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def parse_manuscript(filename: str, raw: bytes, audit: Audit) -> Manuscript | None:
    location = f"zip:{filename}"
    try:
        text = decode_utf8(raw)
    except UnicodeError as exc:
        audit.error("zip_encoding", location, str(exc))
        return None
    lines = text.splitlines()
    marker_indices: dict[str, int] = {}
    for marker in MARKERS:
        matches = [index for index, line in enumerate(lines) if line.strip() == marker]
        if len(matches) != 1:
            audit.error("manuscript_marker", location, f"{marker} count={len(matches)}")
            return None
        marker_indices[marker] = matches[0]
    if [marker_indices[item] for item in MARKERS] != sorted(marker_indices.values()):
        audit.error("manuscript_marker_order", location, "marker order differs")
        return None

    def segment(start: str, end: str | None) -> list[str]:
        left = marker_indices[start] + 1
        right = marker_indices[end] if end else len(lines)
        return _nonempty(lines[left:right])

    title_values = segment("[페이지타이틀]", "[메타설명]")
    meta_values = segment("[메타설명]", "[본문]")
    body_values = segment("[본문]", "[FAQ]")
    faq_values = segment("[FAQ]", "[학부모후기]")
    review_values = segment("[학부모후기]", "[JSON-LD 요약]")
    summary_values = segment("[JSON-LD 요약]", None)
    if len(title_values) != 1 or len(meta_values) != 1 or len(summary_values) != 1:
        audit.error(
            "manuscript_singletons",
            location,
            f"title={len(title_values)}, meta={len(meta_values)}, summary={len(summary_values)}",
        )
        return None

    locality_match = re.fullmatch(r"(.+) 중3 수학학원\.txt", filename)
    if not locality_match:
        audit.error("zip_filename", location, "filename does not match the required pattern")
        return None
    locality = locality_match.group(1)
    expected_title = f"{locality} 중3 수학학원"
    if title_values[0] != expected_title:
        audit.error("manuscript_title", location, f"actual={title_values[0]!r}, expected={expected_title!r}")

    intro: list[str] = []
    sections: list[ManuscriptSection] = []
    current_heading: str | None = None
    current_paragraphs: list[str] = []
    for block in body_values:
        if block.startswith("## "):
            if current_heading is not None:
                sections.append(ManuscriptSection(current_heading, tuple(current_paragraphs)))
            current_heading = block[3:].strip()
            current_paragraphs = []
        elif current_heading is None:
            intro.append(block)
        else:
            current_paragraphs.append(block)
    if current_heading is not None:
        sections.append(ManuscriptSection(current_heading, tuple(current_paragraphs)))
    if len(sections) != 6 or not all(section.paragraphs for section in sections):
        audit.error(
            "manuscript_body",
            location,
            f"intro={len(intro)}, sections={len(sections)}, paragraphs={[len(s.paragraphs) for s in sections]}",
        )

    faq: list[tuple[str, str]] = []
    cursor = 0
    while cursor < len(faq_values):
        question = faq_values[cursor]
        if not re.match(rf"^Q{len(faq)+1}\.\s+", question):
            audit.error("manuscript_faq_question", location, f"value={question!r}")
            break
        cursor += 1
        if cursor >= len(faq_values) or not faq_values[cursor].startswith("A. "):
            audit.error("manuscript_faq_answer", location, f"question={question!r}")
            break
        answer = faq_values[cursor][3:].strip()
        faq.append((re.sub(r"^Q\d+\.\s+", "", question), answer))
        cursor += 1
    if len(faq) != 3 or cursor != len(faq_values):
        audit.error("manuscript_faq_count", location, f"pairs={len(faq)}, blocks={len(faq_values)}")

    if len(review_values) != 2:
        audit.error("manuscript_review", location, f"blocks={len(review_values)}")
    elif not re.search(r"(?:아니|가상|재구성|상황형\s*예시)", review_values[0]):
        audit.error("manuscript_review_disclaimer", location, review_values[0])

    if PROMPT_OR_CODE.search(text):
        audit.error("zip_instruction_or_code", location, "instruction/code-like content found")
    if "\x00" in text or re.search(r"https?://|<[/A-Za-z]", text):
        audit.error("zip_active_content", location, "URL, markup, or NUL found")
    if MOJIBAKE.search(text):
        audit.error("zip_mojibake", location, "replacement/mojibake sequence found")
    if GUARANTEE.search(text):
        audit.error("manuscript_guarantee", location, GUARANTEE.search(text).group(0))
    if ADJACENT_REPEAT.search(text):
        audit.error("manuscript_adjacent_repeat", location, ADJACENT_REPEAT.search(text).group(0))

    return Manuscript(
        filename=filename,
        locality=locality,
        title=title_values[0],
        meta=meta_values[0],
        intro=tuple(intro),
        sections=tuple(sections),
        faq=tuple(faq),
        review=tuple(review_values),
        json_summary=summary_values[0],
        raw_text=text,
        raw_sha256=sha256_bytes(raw),
        line_count=len(lines),
    )


def load_zip(path: Path, audit: Audit) -> tuple[list[Manuscript], str]:
    if not path.is_file():
        audit.error("zip_missing", path, "authoritative manuscript archive missing")
        return [], ""
    zip_sha = sha256_file(path)
    if zip_sha != EXPECTED_HASHES["zip"]:
        audit.error("zip_hash", path, f"actual={zip_sha}, expected={EXPECTED_HASHES['zip']}")
    manuscripts: list[Manuscript] = []
    manifest_lines: list[str] = []
    names: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) != EXPECTED_ROWS:
                audit.error("zip_count", path, f"entries={len(infos)}, expected={EXPECTED_ROWS}")
            for info in infos:
                name = info.filename
                names.append(name)
                pure = Path(name)
                mode = (info.external_attr >> 16) & 0o170000
                unsafe = (
                    info.is_dir()
                    or pure.is_absolute()
                    or len(pure.parts) != 1
                    or ".." in pure.parts
                    or ":" in name
                    or info.flag_bits & 0x1
                    or mode == 0o120000
                    or not name.endswith(".txt")
                    or nfc(name) != name
                )
                if unsafe:
                    audit.error("zip_member_safety", f"zip:{name}", "unsafe/non-text member")
                    continue
                raw = archive.read(info)
                if not raw.startswith(b"\xef\xbb\xbf"):
                    audit.error("zip_bom", f"zip:{name}", "UTF-8 BOM missing")
                if b"\r\n" in raw or b"\x00" in raw:
                    audit.error("zip_line_encoding", f"zip:{name}", "expected LF-only text without NUL")
                file_sha = sha256_bytes(raw)
                manifest_lines.append(f"{name}\0{len(raw)}\0{file_sha}\n")
                parsed = parse_manuscript(name, raw, audit)
                if parsed is not None:
                    manuscripts.append(parsed)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        audit.error("zip_read", path, repr(exc))
        return [], zip_sha

    if len(names) != len(set(names)):
        audit.error("zip_duplicate_name", path, "duplicate member filename")
    if len({item.locality for item in manuscripts}) != len(manuscripts):
        audit.error("zip_duplicate_locality", path, "duplicate locality")
    if len({item.raw_sha256 for item in manuscripts}) != len(manuscripts):
        audit.error("zip_duplicate_content", path, "duplicate raw manuscript")
    manifest_sha = sha256_bytes("".join(sorted(manifest_lines)).encode("utf-8"))
    if manifest_sha != EXPECTED_HASHES["zip_manifest"]:
        audit.error(
            "zip_manifest_hash",
            path,
            f"actual={manifest_sha}, expected={EXPECTED_HASHES['zip_manifest']}",
        )
    line_distribution = Counter(item.line_count for item in manuscripts)
    paragraph_distribution = Counter(len(item.paragraphs) for item in manuscripts)
    if dict(line_distribution) != EXPECTED_LINES:
        audit.error("manuscript_line_distribution", path, f"actual={dict(line_distribution)}")
    if dict(paragraph_distribution) != EXPECTED_PARAGRAPHS:
        audit.error("manuscript_paragraph_distribution", path, f"actual={dict(paragraph_distribution)}")
    query_counts = [item.raw_text.count(item.query) for item in manuscripts]
    if query_counts and (min(query_counts) < 11 or max(query_counts) > 23):
        audit.error("manuscript_query_density", path, f"min={min(query_counts)}, max={max(query_counts)}")
    audit.observations["zip"] = {
        "sha256": zip_sha,
        "manifest_sha256": manifest_sha,
        "entries": len(manuscripts),
        "bytes": path.stat().st_size,
        "line_distribution": dict(sorted(line_distribution.items())),
        "paragraph_distribution": dict(sorted(paragraph_distribution.items())),
        "query_min": min(query_counts) if query_counts else 0,
        "query_max": max(query_counts) if query_counts else 0,
    }
    return manuscripts, zip_sha


def read_csv(path: Path, expected_sha: str, audit: Audit, code: str) -> list[dict[str, str]]:
    if not path.is_file():
        audit.error(f"{code}_missing", path, "authoritative CSV missing")
        return []
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        audit.error(f"{code}_hash", path, f"actual={actual_sha}, expected={expected_sha}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        audit.error(f"{code}_read", path, repr(exc))
        return []
    if len(rows) != EXPECTED_ROWS:
        audit.error(f"{code}_count", path, f"rows={len(rows)}, expected={EXPECTED_ROWS}")
    return rows


def load_sources(common: Path, manuscripts: Sequence[Manuscript], audit: Audit) -> list[SourceRow]:
    center_path = common / CENTER_NAME
    target_path = common / TARGET_SCHOOL_NAME
    eo_path = common / EO_NAME
    image_path = common / IMAGE_NAME
    center = read_csv(center_path, EXPECTED_HASHES["center"], audit, "center")
    target = read_csv(target_path, EXPECTED_HASHES["target_school"], audit, "target_school")
    eo = read_csv(eo_path, EXPECTED_HASHES["educational_organization"], audit, "eo")
    images = read_csv(image_path, EXPECTED_HASHES["image"], audit, "image")
    if not all((center, target, eo, images)):
        return []

    center_columns = tuple(center[0])
    target_columns = tuple(target[0])
    middle_col = find_column(center_columns, "타깃학교(중)")
    target_middle_col = find_column(target_columns, "타깃학교(중)")
    math_col = find_column(center_columns, "가능학년(수학)")
    required = {
        "middle_col": middle_col,
        "target_middle_col": target_middle_col,
        "math_col": math_col,
    }
    if not all(required.values()):
        audit.error("source_columns", center_path, repr(required))
        return []

    manuscript_order = [item.locality for item in manuscripts]
    for label, rows, key in (
        ("center", center, "근처 수업가능 동네"),
        ("target", target, "근처 수업가능 동네"),
        ("eo", eo, "서비스 제공 지역"),
        ("image", images, "제목"),
    ):
        actual = [norm(row.get(key)) for row in rows]
        if actual != manuscript_order:
            audit.error("source_order", label, "371 locality order differs from the ZIP")
        if len(actual) != len(set(actual)):
            audit.error("source_duplicate_locality", label, "duplicate locality")

    result: list[SourceRow] = []
    supported = 0
    school_provided = 0
    for index, (center_row, target_row, eo_row, image_row) in enumerate(
        zip(center, target, eo, images, strict=False), start=1
    ):
        locality = norm(center_row.get("근처 수업가능 동네"))
        location = f"source:{locality}"
        parity_fields = (
            ("근처 수업가능 동네", "근처 수업가능 동네"),
            ("지역", "지역"),
            ("시or구", "시or구"),
            ("센터명", "센터명"),
            (middle_col, target_middle_col),
        )
        for center_key, target_key in parity_fields:
            if norm(center_row.get(center_key)) != norm(target_row.get(target_key)):
                audit.error(
                    "source_target_parity",
                    location,
                    f"field={center_key!r}, center={center_row.get(center_key)!r}, target={target_row.get(target_key)!r}",
                )
        grades = tuple(token for token in re.split(r"[,\s]+", norm(center_row.get(math_col))) if token)
        is_supported = "중3" in grades
        supported += int(is_supported)
        middle_raw = norm(center_row.get(middle_col))
        schools = split_schools(middle_raw)
        school_provided += int(bool(schools))
        center_name = norm(center_row.get("센터명"))
        address = norm(center_row.get("센터 주소"))
        eo_name = norm(eo_row.get("실제 센터명"))
        eo_address = norm(eo_row.get("도로명 주소"))
        if eo_name != center_name:
            audit.error("source_eo_name", location, f"center={center_name!r}, eo={eo_name!r}")
        if eo_address != address:
            audit.error("source_eo_address", location, f"center={address!r}, eo={eo_address!r}")
        if norm(eo_row.get("서비스 제공 지역")) != locality:
            audit.error("source_eo_locality", location, repr(eo_row.get("서비스 제공 지역")))
        if norm(image_row.get("제목")) != locality:
            audit.error("source_image_locality", location, repr(image_row.get("제목")))
        result.append(
            SourceRow(
                position=index,
                locality=locality,
                region=norm(center_row.get("지역")),
                district=norm(center_row.get("시or구")),
                center_name=center_name,
                fee_url=norm(center_row.get("센터 교습비")),
                education_office=norm(center_row.get("교육지원청명칭")),
                registration=norm(center_row.get("교육지원청 등록번호")),
                address=address,
                location_guide=norm(center_row.get("위치안내")),
                middle_school_raw=middle_raw,
                middle_schools=schools,
                math_grades=grades,
                supported=is_supported,
                eo_name=eo_name,
                eo_address=eo_address,
                telephone=norm(eo_row.get("전화번호")),
                opening_hours=norm(eo_row.get("운영 시간")),
                official_site=norm(eo_row.get("공식 홈페이지")),
                body_image_source=norm(image_row.get("본문")),
                map_image_source=norm(image_row.get("지도")),
            )
        )
    if supported != EXPECTED_SUPPORTED or len(result) - supported != EXPECTED_UNCONFIRMED:
        audit.error(
            "source_supported_count",
            center_path,
            f"supported={supported}, unconfirmed={len(result)-supported}",
        )
    if school_provided != EXPECTED_MIDDLE_SCHOOL_PROVIDED:
        audit.error("source_school_count", center_path, f"provided={school_provided}")
    if len(result) - school_provided != EXPECTED_MIDDLE_SCHOOL_MISSING:
        audit.error("source_school_missing", center_path, f"missing={len(result)-school_provided}")
    audit.observations["common"] = {
        "rows": len(result),
        "supported": supported,
        "unconfirmed_grade": len(result) - supported,
        "middle_school_provided": school_provided,
        "middle_school_missing": len(result) - school_provided,
        "hashes": {key: EXPECTED_HASHES[key] for key in ("center", "target_school", "educational_organization", "image")},
    }
    return result


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    parent: "Element | None" = None
    children: list["Element"] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)

    def text(self, *, visible: bool = True) -> str:
        if visible and self.tag in INVISIBLE_TAGS:
            return ""
        parts = list(self.chunks)
        for child in self.children:
            value = child.text(visible=visible)
            if value:
                parts.append(value)
        return norm(" ".join(parts))

    def descendants(self, *, include_self: bool = False) -> Iterator["Element"]:
        if include_self:
            yield self
        for child in self.children:
            yield child
            yield from child.descendants()


class DOMParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document", {})
        self.stack: list[Element] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Element(tag.lower(), {name.lower(): value or "" for name, value in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in VOID_TAGS:
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
        self.stack[-1].chunks.append(data)


def parse_dom(text: str, audit: Audit, location: str) -> Element | None:
    parser = DOMParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001
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
                if actual is None:
                    matched = False
            elif actual != expected:
                matched = False
        if matched:
            result.append(node)
    return result


def has_class(node: Element, value: str) -> bool:
    return value in node.attrs.get("class", "").split()


def ancestor_has_attr(node: Element, name: str, value: str | None = None) -> bool:
    current = node.parent
    while current is not None:
        if name in current.attrs and (value is None or current.attrs[name] == value):
            return True
        current = current.parent
    return False


def json_graph(root: Element, audit: Audit, location: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    for script in find_elements(root, "script", type="application/ld+json"):
        raw = script.text(visible=False)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            audit.error("jsonld_parse", location, str(exc))
            continue
        items: Any
        if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
            items = payload["@graph"]
        elif isinstance(payload, list):
            items = payload
        else:
            items = [payload]
        for item in items:
            if isinstance(item, dict):
                graph.append(item)
    return graph


def node_types(node: Mapping[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def graph_type(graph: Sequence[dict[str, Any]], value: str) -> list[dict[str, Any]]:
    return [node for node in graph if value in node_types(node)]


def walk_json(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def json_names(value: Any) -> set[str]:
    return {norm(node.get("name")) for node in walk_json(value) if isinstance(node.get("name"), str)}


def json_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    for node in walk_json(value):
        for key in ("@id", "url", "item"):
            if isinstance(node.get(key), str):
                refs.add(node[key])
    return refs


def faq_schema_pairs(node: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    entities = node.get("mainEntity")
    if not isinstance(entities, list):
        return ()
    for question in entities:
        if not isinstance(question, dict):
            continue
        answer = question.get("acceptedAnswer")
        if isinstance(answer, dict):
            result.append((norm(question.get("name")), norm(answer.get("text"))))
    return tuple(result)


def expected_detail_rel(locality: str) -> str:
    return (Path("학년별학원") / "중3수학학원" / locality / "index.html").as_posix()


def expected_detail_path(locality: str) -> str:
    return f"/학년별학원/중3수학학원/{locality}/"


def expected_new_paths(rows: Sequence[SourceRow]) -> set[str]:
    return {GRADE_HUB_REL, CATEGORY_REL, *(expected_detail_rel(row.locality) for row in rows)}


def iter_repo_files(root: Path) -> Iterator[Path]:
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = [name for name in dirs if name not in PRUNE_DIRS]
        base = Path(current)
        for name in files:
            yield base / name


def repository_manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(iter_repo_files(root), key=lambda item: item.as_posix()):
        result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


class View:
    def __init__(self, root: Path, overrides: Mapping[str, str] | None = None) -> None:
        self.root = root
        self.overrides = dict(overrides or {})

    def exists(self, rel: str) -> bool:
        return rel in self.overrides or (self.root / rel).is_file()

    def text(self, rel: str) -> str:
        if rel in self.overrides:
            return self.overrides[rel]
        return decode_utf8((self.root / rel).read_bytes())

    def html_paths(self) -> set[str]:
        values = {
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*.html")
            if not any(part in PRUNE_DIRS for part in path.relative_to(self.root).parts)
        }
        values.update(key for key in self.overrides if key.endswith(".html"))
        return values


def import_generator(path: Path, audit: Audit) -> ModuleType | None:
    if not path.is_file():
        audit.hold("generator_missing", path, "generator is not present yet")
        return None
    spec = importlib.util.spec_from_file_location("_grade3_math_projection", path)
    if spec is None or spec.loader is None:
        audit.error("generator_import", path, "cannot create import spec")
        return None
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - a trusted local generator failure must be reported
        audit.error("generator_import", path, repr(exc))
        return None
    finally:
        sys.dont_write_bytecode = old
    return module


def call_build_plan(
    module: ModuleType,
    root: Path,
    zip_path: Path,
    common: Path,
    current_overrides: Mapping[Any, Any] | None,
    audit: Audit,
) -> Any:
    build = getattr(module, "build_plan", None)
    if not callable(build):
        audit.error("generator_contract", "generator", "build_plan is missing")
        return None
    signature = inspect.signature(build)
    required = {"root", "zip_path", "common_dir", "current_overrides"}
    if not required.issubset(signature.parameters):
        audit.error("generator_signature", "generator", f"signature={signature}")
        return None
    try:
        return build(
            root=root,
            zip_path=zip_path,
            common_dir=common,
            current_overrides=current_overrides,
        )
    except Exception as exc:  # noqa: BLE001
        audit.error("generator_build", "generator", repr(exc))
        return None


def plan_documents(plan: Any, root: Path, audit: Audit, label: str) -> tuple[dict[str, str], Mapping[Any, Any]]:
    raw = getattr(plan, "authorized_documents", None)
    if not isinstance(raw, Mapping):
        audit.error("plan_contract", label, "authorized_documents must be a mapping")
        return {}, {}
    result: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        try:
            key = path_key(root, raw_key)
        except (ValueError, OSError) as exc:
            audit.error("plan_scope", label, f"path={raw_key!r}: {exc}")
            continue
        if key in result:
            audit.error("plan_duplicate", label, key)
            continue
        try:
            if isinstance(raw_value, bytes):
                value = decode_utf8(raw_value)
            elif isinstance(raw_value, str):
                value = raw_value
            else:
                raise TypeError(type(raw_value).__name__)
        except (UnicodeError, TypeError) as exc:
            audit.error("plan_value", key, str(exc))
            continue
        result[key] = value
    return result, raw


def normalized_path_set(values: Any, root: Path, audit: Audit, label: str) -> set[str]:
    if values is None:
        return set()
    try:
        return {path_key(root, value) for value in values}
    except (TypeError, ValueError, OSError) as exc:
        audit.error("plan_paths", label, repr(exc))
        return set()


def plan_manifest_summary(value: Any, root: Path, audit: Audit, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        audit.error("plan_manifest", label, "manifest must be a mapping")
        return {"count": 0, "sha256": ""}
    normalized: list[tuple[str, str]] = []
    for key, digest in value.items():
        try:
            rel = path_key(root, key)
        except (ValueError, OSError) as exc:
            audit.error("plan_manifest", label, f"path={key!r}: {exc}")
            continue
        normalized.append((rel, str(digest)))
    payload = "".join(f"{rel}\0{digest}\n" for rel, digest in sorted(normalized)).encode("utf-8")
    return {"count": len(normalized), "sha256": sha256_bytes(payload)}


def allowed_plan_path(rel: str, baseline_html: set[str], new_paths: set[str]) -> bool:
    return rel in baseline_html or rel in new_paths or rel in {
        SITEMAP_REL,
        LLMS_REL,
        "assets/header.css",
    }


def projected_view(
    root: Path,
    zip_path: Path,
    common: Path,
    generator: Path,
    expected_generator_sha: str,
    rows: Sequence[SourceRow],
    audit: Audit,
) -> View:
    baseline_html = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.html")
        if not any(part in PRUNE_DIRS for part in path.relative_to(root).parts)
    }
    new_paths = expected_new_paths(rows)
    actual_sha = sha256_file(generator) if generator.is_file() else ""
    if expected_generator_sha in {"", "PENDING"}:
        audit.hold("generator_pin_pending", generator, f"actual_sha256={actual_sha or 'missing'}")
    elif actual_sha != expected_generator_sha.lower():
        audit.error("generator_hash", generator, f"actual={actual_sha}, expected={expected_generator_sha}")
    module = import_generator(generator, audit)
    if module is None:
        return View(root)

    repo_before = repository_manifest(root)
    source_paths = (zip_path, common / CENTER_NAME, common / TARGET_SCHOOL_NAME, common / EO_NAME, common / IMAGE_NAME)
    source_before = {str(path): sha256_file(path) for path in source_paths if path.is_file()}
    first = call_build_plan(module, root, zip_path, common, None, audit)
    if first is None:
        return View(root)
    first_docs, first_raw = plan_documents(first, root, audit, "first-plan")
    if getattr(first, "candidate_sha256", None) != EXPECTED_PLAN_CANDIDATE_SHA256:
        audit.error(
            "plan_candidate_hash",
            generator,
            f"actual={getattr(first, 'candidate_sha256', None)!r}, expected={EXPECTED_PLAN_CANDIDATE_SHA256}",
        )
    expected_docs = baseline_html | new_paths | {SITEMAP_REL, LLMS_REL, "assets/header.css"}
    if set(first_docs) != expected_docs or len(first_docs) != EXPECTED_PLAN_DOCUMENTS:
        missing = sorted(expected_docs - set(first_docs))
        extra = sorted(set(first_docs) - expected_docs)
        audit.error(
            "plan_document_set",
            generator,
            f"actual={len(first_docs)}, expected={EXPECTED_PLAN_DOCUMENTS}, "
            f"missing={len(missing)} {missing[:5]!r}, extra={len(extra)} {extra[:5]!r}",
        )
    for rel in first_docs:
        if not allowed_plan_path(rel, baseline_html, new_paths):
            audit.error("plan_scope", rel, "unauthorized document")
    source_manifest = getattr(first, "source_manifest", None)
    if not isinstance(source_manifest, Mapping):
        audit.error("plan_source_manifest", generator, "source_manifest must be a mapping")
    else:
        expected_plan_sources = {
            "manuscript_zip": EXPECTED_HASHES["zip"],
            "center_csv": EXPECTED_HASHES["center"],
            "target_school_csv": EXPECTED_HASHES["target_school"],
        }
        actual_plan_sources = {str(key): str(value) for key, value in source_manifest.items()}
        if actual_plan_sources != expected_plan_sources:
            audit.error(
                "plan_source_manifest",
                generator,
                f"actual={actual_plan_sources!r}, expected={expected_plan_sources!r}",
            )
    before_manifest_summary = plan_manifest_summary(
        getattr(first, "before_manifest", None), root, audit, "before_manifest"
    )
    after_manifest_summary = plan_manifest_summary(
        getattr(first, "after_manifest", None), root, audit, "after_manifest"
    )
    for label, summary in (("before", before_manifest_summary), ("after", after_manifest_summary)):
        if summary["count"] != EXPECTED_PLAN_DOCUMENTS:
            audit.error("plan_manifest_count", generator, f"{label}={summary['count']}")
    changed_reported = normalized_path_set(getattr(first, "changed_paths", None), root, audit, "first-plan")
    changed_actual = {
        rel
        for rel, value in first_docs.items()
        if not (root / rel).is_file() or decode_utf8((root / rel).read_bytes()) != value
    }
    if changed_reported and changed_reported != changed_actual:
        audit.error(
            "plan_changed_paths",
            generator,
            f"reported={len(changed_reported)}, actual={len(changed_actual)}, delta={len(changed_reported ^ changed_actual)}",
        )
    if getattr(first, "second_pass_changes", ()):
        audit.error("plan_second_pass", generator, repr(getattr(first, "second_pass_changes"))[:1000])

    second = call_build_plan(module, root, zip_path, common, first_raw, audit)
    if second is not None:
        second_docs, _ = plan_documents(second, root, audit, "second-plan")
        if getattr(second, "candidate_sha256", None) != EXPECTED_PLAN_CANDIDATE_SHA256:
            audit.error(
                "plan_candidate_hash",
                generator,
                f"second={getattr(second, 'candidate_sha256', None)!r}, expected={EXPECTED_PLAN_CANDIDATE_SHA256}",
            )
        if second_docs != first_docs:
            delta = {key for key in set(second_docs) | set(first_docs) if second_docs.get(key) != first_docs.get(key)}
            audit.error("plan_idempotency", generator, f"document delta={len(delta)}")
        if normalized_path_set(getattr(second, "changed_paths", None), root, audit, "second-plan"):
            audit.error("plan_idempotency", generator, "second changed_paths is non-empty")
        if getattr(second, "second_pass_changes", ()):
            audit.error("plan_idempotency", generator, "second_pass_changes is non-empty")

    repo_after = repository_manifest(root)
    source_after = {str(path): sha256_file(path) for path in source_paths if path.is_file()}
    if repo_after != repo_before:
        changed = {key for key in set(repo_before) | set(repo_after) if repo_before.get(key) != repo_after.get(key)}
        audit.error("generator_mutation", generator, f"build_plan mutated {len(changed)} repo paths")
    if source_after != source_before:
        audit.error("generator_source_mutation", generator, "ZIP/common source changed")
    audit.observations["projection"] = {
        "generator": str(generator),
        "generator_sha256": actual_sha,
        "documents": len(first_docs),
        "changed_paths": len(changed_actual),
        "second_pass_changes": 0 if second is not None else None,
        "candidate_sha256": getattr(first, "candidate_sha256", None),
        "before_manifest": before_manifest_summary,
        "after_manifest": after_manifest_summary,
        "metrics": dict(getattr(first, "metrics", {}) or {}),
    }
    return View(root, first_docs)


def meta_content(dom: Element, *, name: str | None = None, prop: str | None = None) -> list[str]:
    result: list[str] = []
    for node in find_elements(dom, "meta"):
        if name is not None and node.attrs.get("name", "").lower() != name.lower():
            continue
        if prop is not None and node.attrs.get("property", "").lower() != prop.lower():
            continue
        result.append(node.attrs.get("content", ""))
    return result


def canonical_links(dom: Element) -> list[str]:
    return [
        node.attrs.get("href", "")
        for node in find_elements(dom, "link")
        if "canonical" in node.attrs.get("rel", "").lower().split()
    ]


def nav_grade_links(dom: Element) -> list[Element]:
    result: list[Element] = []
    for anchor in find_elements(dom, "a"):
        if anchor.attrs.get("href") != GRADE_HUB_PATH or anchor.text() != "학년별학원":
            continue
        current = anchor.parent
        while current is not None:
            if has_class(current, "nav-links"):
                result.append(anchor)
                break
            current = current.parent
    return result


def exact_nodes(dom: Element, attr: str, value: str | None = None) -> list[Element]:
    key = attr.lower()
    return [
        node
        for node in dom.descendants()
        if key in node.attrs and (value is None or node.attrs.get(key) == value)
    ]


def text_contains_in_order(container: str, values: Sequence[str]) -> bool:
    cursor = 0
    for value in values:
        value = norm(value)
        index = container.find(value, cursor)
        if index < 0:
            return False
        cursor = index + len(value)
    return True


def expected_images(root: Path, row: SourceRow, audit: Audit) -> tuple[str, ...]:
    rel = (Path("과목별학원") / "수학학원" / row.locality / "index.html").as_posix()
    path = root / rel
    if not path.is_file():
        audit.error("baseline_math_page", rel, "existing page missing")
        return ()
    dom = parse_dom(decode_utf8(path.read_bytes()), audit, rel)
    if dom is None:
        return ()
    sources = tuple(node.attrs.get("src", "") for node in find_elements(dom, "img"))
    if len(sources) != 3:
        audit.error("baseline_images", rel, f"count={len(sources)}")
    for source in sources:
        if source.startswith("/") and not (root / source.lstrip("/")).is_file():
            audit.error("baseline_image_missing", rel, source)
    return sources


def require_single(
    values: Sequence[Any],
    audit: Audit,
    code: str,
    location: str,
    expected: Any | None = None,
) -> Any | None:
    if len(values) != 1:
        audit.error(code, location, f"count={len(values)}, expected=1")
        return None
    value = values[0]
    if expected is not None and value != expected:
        audit.error(code, location, f"actual={value!r}, expected={expected!r}")
    return value


def schema_address(node: Mapping[str, Any]) -> str:
    address = node.get("address")
    if isinstance(address, dict):
        return norm(address.get("streetAddress"))
    return norm(address)


def validate_physical_node(
    node: Mapping[str, Any],
    row: SourceRow,
    audit: Audit,
    location: str,
    kind: str,
) -> None:
    if norm(node.get("name")) != row.eo_name:
        audit.error("schema_physical_name", location, f"type={kind}, value={node.get('name')!r}")
    if schema_address(node) != row.eo_address:
        audit.error("schema_physical_address", location, f"type={kind}, value={schema_address(node)!r}")
    if norm(node.get("telephone")) != row.telephone:
        audit.error("schema_physical_phone", location, f"type={kind}, value={node.get('telephone')!r}")
    names = json_names(node.get("areaServed"))
    if row.locality not in names:
        audit.error("schema_physical_area", location, f"type={kind}, names={sorted(names)}")
    if row.registration:
        values = {norm(item.get("value")) for item in walk_json(node.get("identifier")) if item.get("value")}
        if row.registration not in values:
            audit.error("schema_registration", location, f"type={kind}, values={sorted(values)}")


def validate_detail(
    text: str,
    manuscript: Manuscript,
    row: SourceRow,
    root: Path,
    all_school_names: set[str],
    audit: Audit,
    mode: str,
) -> None:
    rel = expected_detail_rel(row.locality)
    dom = parse_dom(text, audit, rel)
    if dom is None:
        return
    path = expected_detail_path(row.locality)
    url = encoded_url(path)
    require_single(canonical_links(dom), audit, "canonical", rel, url)
    require_single(meta_content(dom, prop="og:url"), audit, "og_url", rel, url)
    require_single(meta_content(dom, name="description"), audit, "meta_description", rel, manuscript.meta)
    titles = [node.text() for node in find_elements(dom, "title")]
    require_single(titles, audit, "title", rel, f"{manuscript.title} | 와와학습코칭센터 영어수학 전문학원")
    h1 = [node.text() for node in find_elements(dom, "h1")]
    require_single(h1, audit, "h1", rel, manuscript.title)

    mains = exact_nodes(dom, "data-grade-page", "middle3-math")
    main = require_single(mains, audit, "grade_main", rel)
    if main is not None and main.attrs.get("data-source-status") != row.status:
        audit.error(
            "source_status",
            rel,
            f"main={main.attrs.get('data-source-status')!r}, expected={row.status!r}",
        )
    require_single(exact_nodes(dom, "data-source-status", row.status), audit, "source_status", rel)

    articles = exact_nodes(dom, "data-manuscript")
    article = require_single(articles, audit, "manuscript_article", rel)
    if article is not None:
        article_text = article.text()
        blocks: list[str] = [*manuscript.intro]
        for section in manuscript.sections:
            blocks.append(section.heading)
            blocks.extend(section.paragraphs)
        if not text_contains_in_order(article_text, blocks):
            audit.error("manuscript_roundtrip", rel, "source body blocks are not present in exact order")
        for block in manuscript.paragraphs:
            count = article_text.count(norm(block))
            if count != 1:
                audit.error("manuscript_paragraph_roundtrip", rel, f"count={count}, block={block[:100]!r}")
        headings = [node.text() for node in article.descendants() if node.tag == "h2"]
        if tuple(headings) != manuscript.headings:
            audit.error("manuscript_h2_roundtrip", rel, f"actual={headings!r}")
        section_nodes = exact_nodes(article, "data-manuscript-section")
        actual_ids = [node.attrs.get("data-manuscript-section") for node in section_nodes]
        if actual_ids != [f"{number:02}" for number in range(1, 7)]:
            audit.error("manuscript_section_ids", rel, f"actual={actual_ids}")
        page_query_count = article_text.count(manuscript.query)
        source_query_count = sum(block.count(manuscript.query) for block in blocks)
        if page_query_count != source_query_count or page_query_count > 23:
            audit.error(
                "query_density",
                rel,
                f"rendered={page_query_count}, source={source_query_count}, chars={len(article_text)}",
            )
        if MOJIBAKE.search(article_text) or ADJACENT_REPEAT.search(article_text) or GUARANTEE.search(article_text):
            audit.error("naturalness_redteam", rel, "mojibake/repeat/guarantee pattern")

    faq_nodes = exact_nodes(dom, "data-faq")
    faq_node = require_single(faq_nodes, audit, "faq_visible", rel)
    if faq_node is not None:
        expected_faq_blocks = [value for pair in manuscript.faq for value in pair]
        if not text_contains_in_order(faq_node.text(), expected_faq_blocks):
            audit.error("faq_visible_parity", rel, "FAQ questions/answers differ from source")
        faq_details = [node for node in faq_node.descendants() if node.tag == "details"]
        answer_markers = [node.text() for node in faq_node.descendants() if node.tag == "strong"]
        if len(faq_details) != 3 or answer_markers.count("A.") != 3:
            audit.error(
                "faq_visible_structure",
                rel,
                f"details={len(faq_details)}, A.={answer_markers.count('A.')}",
            )
    review_nodes = exact_nodes(dom, "data-review")
    review_node = require_single(review_nodes, audit, "review_visible", rel)
    if review_node is not None and not text_contains_in_order(review_node.text(), manuscript.review):
        audit.error("review_roundtrip", rel, "review disclaimer/scenario differs from source")

    expected_fields = ("grade", "middle-schools", "address", "registration", "fee")
    actual_fields = [node.attrs.get("data-source-field", "") for node in exact_nodes(dom, "data-source-field")]
    if Counter(actual_fields) != Counter(expected_fields):
        audit.error("source_field_set", rel, f"actual={actual_fields!r}, expected={expected_fields!r}")
    field_nodes: dict[str, Element | None] = {}
    for field_name in expected_fields:
        field_nodes[field_name] = require_single(
            exact_nodes(dom, "data-source-field", field_name),
            audit,
            "source_field",
            f"{rel}:{field_name}",
        )
    if field_nodes["grade"] is not None:
        grade_text = field_nodes["grade"].text()
        if row.supported and "중3" not in grade_text:
            audit.error("source_grade", rel, grade_text)
        if not row.supported and not SAFE_AVAILABILITY.search(grade_text):
            audit.error("source_grade_unconfirmed", rel, grade_text)
    school_node = field_nodes["middle-schools"]
    if school_node is not None:
        school_text = school_node.text()
        school_state = school_node.attrs.get("data-source-state") or school_node.attrs.get("data-source-status")
        missing_state = school_state in {"missing", "unprovided"}
        if row.middle_schools:
            absent = [school for school in row.middle_schools if school not in school_text]
            if absent:
                audit.error("source_schools", rel, f"missing={absent}")
            if school_state not in {"provided", "source-provided"}:
                audit.error("source_schools_state", rel, f"state={school_state!r}")
        elif not missing_state or not re.search(
            r"(?:미기재|제공되지|기재되지|비어|확인\s*(?:필요|해))",
            school_text,
        ):
            audit.error("source_schools_missing", rel, school_text)
        unauthorized = sorted(school for school in all_school_names if school not in row.middle_schools and re.search(
            rf"(?<![가-힣A-Za-z0-9]){re.escape(school)}(?![가-힣A-Za-z0-9])", school_text
        ))
        if unauthorized:
            audit.error("source_school_invention", rel, f"schools={unauthorized}")
    if field_nodes["address"] is not None and row.address not in field_nodes["address"].text():
        audit.error("source_address", rel, field_nodes["address"].text())
    if field_nodes["registration"] is not None:
        registration_text = field_nodes["registration"].text()
        if row.registration and row.registration not in registration_text:
            audit.error("source_registration", rel, f"missing={row.registration!r}")
    if field_nodes["fee"] is not None:
        hrefs = {node.attrs.get("href") for node in field_nodes["fee"].descendants() if node.tag == "a"}
        if row.fee_url and row.fee_url not in hrefs:
            audit.error("source_fee", rel, f"expected href={row.fee_url!r}, actual={sorted(hrefs)}")
    images = tuple(node.attrs.get("src", "") for node in find_elements(dom, "img"))
    expected_image_sources = expected_images(root, row, audit)
    expected_dom_images = expected_image_sources[1:] if len(expected_image_sources) == 3 else ()
    if images != expected_dom_images:
        audit.error("images", rel, f"actual={images}, expected={expected_dom_images}")
    roles = tuple(node.attrs.get("data-image-role", "") for node in find_elements(dom, "img"))
    if roles != ("body", "map"):
        audit.error("image_roles", rel, f"actual={roles!r}")
    for image in find_elements(dom, "img"):
        if manuscript.title not in image.attrs.get("alt", ""):
            audit.error("image_alt", rel, image.attrs.get("alt", ""))
    map_cards = [node for node in dom.descendants() if node.tag == "figure" and has_class(node, "math-map-card")]
    map_card = require_single(map_cards, audit, "map_card", rel)
    if map_card is not None and not all(term in map_card.text() for term in ("제공 주소", "직접 확인")):
        audit.error("location_redteam", rel, map_card.text())
    if len(expected_image_sources) == 3:
        representative_url = BASE_URL + quote(expected_image_sources[0], safe="/%")
        require_single(meta_content(dom, prop="og:image"), audit, "representative_og", rel, representative_url)
        require_single(
            meta_content(dom, name="twitter:image"),
            audit,
            "representative_twitter",
            rel,
            representative_url,
        )
    else:
        representative_url = ""

    if main is not None:
        full_query_count = main.text().count(manuscript.query)
        raw_query_count = manuscript.raw_text.count(manuscript.query)
        if full_query_count < page_query_count or full_query_count > raw_query_count + 8:
            audit.error(
                "query_density_full_page",
                rel,
                f"main={full_query_count}, manuscript={raw_query_count}, article={page_query_count}",
            )
        for tag in ("h2", "p", "blockquote", "li"):
            visible_blocks = [
                node.text()
                for node in main.descendants()
                if node.tag == tag and len(node.text()) >= 40
            ]
            duplicates = [value for value, count in Counter(visible_blocks).items() if count > 1]
            if duplicates:
                audit.error(
                    "within_page_visible_duplicate",
                    rel,
                    f"tag={tag}, duplicates={len(duplicates)}, sample={duplicates[0][:120]!r}",
                )

    nav = nav_grade_links(dom)
    require_single(nav, audit, "grade_nav", rel)
    if nav and not has_class(nav[0], "active"):
        audit.error("grade_nav_active", rel, "grade nav link is not active")

    graph = json_graph(dom, audit, rel)
    web_pages = graph_type(graph, "WebPage")
    articles = graph_type(graph, "Article")
    breadcrumbs = graph_type(graph, "BreadcrumbList")
    faqs = graph_type(graph, "FAQPage")
    lists = graph_type(graph, "ItemList")
    image_objects = graph_type(graph, "ImageObject")
    organizations = graph_type(graph, "EducationalOrganization")
    businesses = graph_type(graph, "LocalBusiness")
    services = [node for node in walk_json(graph) if "Service" in node_types(node)]
    offers = [node for node in walk_json(graph) if "Offer" in node_types(node)]
    web_page = require_single(web_pages, audit, "schema_webpage", rel)
    schema_article = require_single(articles, audit, "schema_article", rel)
    breadcrumb = require_single(breadcrumbs, audit, "schema_breadcrumb", rel)
    faq_schema = require_single(faqs, audit, "schema_faq", rel)
    image_object = require_single(image_objects, audit, "schema_image_object", rel)
    require_single(organizations, audit, "schema_educational_organization", rel)
    require_single(businesses, audit, "schema_local_business", rel)
    if not lists:
        audit.error("schema_itemlist", rel, "ItemList missing")
    if row.supported:
        if len(services) != 1 or len(offers) != 1:
            audit.error("schema_service_offer", rel, f"services={len(services)}, offers={len(offers)}")
    elif services or offers:
        audit.error("schema_unsupported_offer", rel, f"services={len(services)}, offers={len(offers)}")

    if organizations:
        validate_physical_node(organizations[0], row, audit, rel, "EducationalOrganization")
    if businesses:
        validate_physical_node(businesses[0], row, audit, rel, "LocalBusiness")
        if organizations and businesses[0].get("url") != organizations[0].get("url"):
            audit.error("schema_physical_url", rel, "EO and LocalBusiness URL differ")

    if organizations and businesses:
        organization_id = organizations[0].get("@id")
        if businesses[0].get("parentOrganization") != {"@id": organization_id}:
            audit.error("schema_physical_relationship", rel, repr(businesses[0].get("parentOrganization")))
        if row.supported and len(services) == 1 and len(offers) == 1:
            service_id = services[0].get("@id")
            offer_id = offers[0].get("@id")
            if not service_id or services[0].get("provider") != {"@id": organization_id}:
                audit.error("schema_service_provider", rel, repr(services[0].get("provider")))
            if row.locality not in json_names(services[0].get("areaServed")):
                audit.error("schema_service_area", rel, repr(services[0].get("areaServed")))
            if offer_id not in json_refs(services[0].get("offers")):
                audit.error("schema_service_offer_link", rel, repr(services[0].get("offers")))
            if service_id not in json_refs(offers[0].get("itemOffered")):
                audit.error("schema_offer_service_link", rel, repr(offers[0].get("itemOffered")))
            for physical, kind in ((organizations[0], "EducationalOrganization"), (businesses[0], "LocalBusiness")):
                if offer_id not in json_refs(physical.get("makesOffer")):
                    audit.error("schema_makes_offer", rel, f"type={kind}, value={physical.get('makesOffer')!r}")
        elif not row.supported:
            for physical, kind in ((organizations[0], "EducationalOrganization"), (businesses[0], "LocalBusiness")):
                if physical.get("makesOffer"):
                    audit.error("schema_unsupported_makes_offer", rel, f"type={kind}")

    for node, kind, expected_id in (
        (web_page, "WebPage", f"{url}#webpage"),
        (schema_article, "Article", f"{url}#article"),
        (breadcrumb, "BreadcrumbList", f"{url}#breadcrumb"),
        (faq_schema, "FAQPage", f"{url}#faq"),
    ):
        if node is not None and node.get("@id") != expected_id:
            audit.error("schema_id", rel, f"type={kind}, actual={node.get('@id')!r}, expected={expected_id!r}")
    if web_page is not None:
        expected_web_name = f"{manuscript.title} | 와와학습코칭센터 영어수학 전문학원"
        if web_page.get("url") != url or norm(web_page.get("name")) != expected_web_name:
            audit.error("schema_webpage_identity", rel, repr({"url": web_page.get("url"), "name": web_page.get("name")}))
        for date_field in ("datePublished", "dateModified"):
            if web_page.get(date_field) != RELEASE_DATE:
                audit.error("schema_date", rel, f"WebPage.{date_field}={web_page.get(date_field)!r}")
        names = json_names(web_page.get("about"))
        if manuscript.title not in names or not any("중3" in value for value in names):
            audit.error("schema_about", rel, f"WebPage about={sorted(names)}")
        mention_names = json_names(web_page.get("mentions"))
        required_mentions = {row.locality, *row.middle_schools}
        if not required_mentions.issubset(mention_names):
            audit.error("schema_mentions", rel, f"WebPage missing={sorted(required_mentions-mention_names)}")
        if representative_url:
            primary_refs = json_refs(web_page.get("primaryImageOfPage"))
            if f"{url}#primaryimage" not in primary_refs:
                audit.error("schema_primary_image", rel, repr(web_page.get("primaryImageOfPage")))
        part_names = json_names(web_page.get("hasPart"))
        if not set(manuscript.headings).issubset(part_names):
            audit.error("schema_haspart", rel, f"WebPage missing={sorted(set(manuscript.headings)-part_names)}")
    if schema_article is not None:
        if norm(schema_article.get("headline")) != manuscript.title:
            audit.error("schema_article_headline", rel, repr(schema_article.get("headline")))
        if norm(schema_article.get("description")) != manuscript.json_summary:
            audit.error("schema_article_description", rel, "JSON-LD summary did not round-trip")
        if representative_url and schema_article.get("image") != representative_url:
            audit.error("schema_article_image", rel, repr(schema_article.get("image")))
        for date_field in ("datePublished", "dateModified"):
            if schema_article.get(date_field) != RELEASE_DATE:
                audit.error("schema_date", rel, f"Article.{date_field}={schema_article.get(date_field)!r}")
        article_sections = schema_article.get("articleSection")
        if not isinstance(article_sections, list) or not set(manuscript.headings).issubset(map(norm, article_sections)):
            audit.error("schema_article_section", rel, repr(article_sections))
        part_names = json_names(schema_article.get("hasPart"))
        if not set(manuscript.headings).issubset(part_names):
            audit.error("schema_haspart", rel, f"Article missing={sorted(set(manuscript.headings)-part_names)}")
        about_names = json_names(schema_article.get("about"))
        if manuscript.title not in about_names or not any("중3" in value for value in about_names):
            audit.error("schema_about", rel, f"Article about={sorted(about_names)}")
        mention_names = json_names(schema_article.get("mentions"))
        required_mentions = {row.locality, *row.middle_schools}
        if not required_mentions.issubset(mention_names):
            audit.error("schema_mentions", rel, f"missing={sorted(required_mentions-mention_names)}")
        invented = sorted((mention_names & all_school_names) - set(row.middle_schools))
        if invented:
            audit.error("schema_school_invention", rel, repr(invented))
    if image_object is not None and representative_url:
        expected_image_id = f"{url}#primaryimage"
        if (
            image_object.get("@id") != expected_image_id
            or image_object.get("url") != representative_url
            or image_object.get("contentUrl") != representative_url
        ):
            audit.error(
                "schema_image_identity",
                rel,
                repr({key: image_object.get(key) for key in ("@id", "url", "contentUrl")}),
            )
    if faq_schema is not None and faq_schema_pairs(faq_schema) != manuscript.faq:
        audit.error("schema_faq_parity", rel, f"actual={faq_schema_pairs(faq_schema)!r}")
    if breadcrumb is not None:
        items = breadcrumb.get("itemListElement")
        expected_names = ["홈", "학년별학원", "중3 수학학원", manuscript.title]
        expected_urls = [
            BASE_URL + "/",
            encoded_url(GRADE_HUB_PATH),
            encoded_url(CATEGORY_PATH),
            url,
        ]
        if not isinstance(items, list) or len(items) != 4:
            audit.error("schema_breadcrumb_items", rel, repr(items))
        else:
            names = [norm(item.get("name")) for item in items if isinstance(item, dict)]
            urls = [item.get("item") or item.get("url") for item in items if isinstance(item, dict)]
            positions = [item.get("position") for item in items if isinstance(item, dict)]
            if names != expected_names or urls != expected_urls or positions != [1, 2, 3, 4]:
                audit.error("schema_breadcrumb_items", rel, repr({"names": names, "urls": urls, "positions": positions}))
    for item_list in lists:
        items = item_list.get("itemListElement")
        if not isinstance(items, list):
            audit.error("schema_itemlist_items", rel, "itemListElement is not a list")
            continue
        positions = [item.get("position") for item in items if isinstance(item, dict)]
        if positions and positions != list(range(1, len(positions) + 1)):
            audit.error("schema_itemlist_positions", rel, repr(positions))
        for item in items:
            if isinstance(item, dict):
                target = item.get("url") or item.get("item")
                if isinstance(target, str) and not is_internal_url(target):
                    audit.error("schema_itemlist_external", rel, target)

    if not row.supported and main is not None:
        page_text = main.text()
        extra_text = page_text
        if article is not None:
            extra_text = extra_text.replace(article.text(), " ")
        for match in POSITIVE_AVAILABILITY.finditer(extra_text):
            window = extra_text[max(0, match.start() - 80) : match.end() + 80]
            if not SAFE_AVAILABILITY.search(window):
                audit.error("unsupported_visible_claim", rel, window)


def validate_directory_page(
    text: str,
    rel: str,
    expected_path: str,
    expected_h1_term: str,
    rows: Sequence[SourceRow],
    audit: Audit,
    *,
    category: bool,
) -> None:
    dom = parse_dom(text, audit, rel)
    if dom is None:
        return
    url = encoded_url(expected_path)
    require_single(canonical_links(dom), audit, "directory_canonical", rel, url)
    require_single(meta_content(dom, prop="og:url"), audit, "directory_og_url", rel, url)
    title_values = [node.text() for node in find_elements(dom, "title")]
    title_value = require_single(title_values, audit, "directory_title", rel)
    if title_value is not None and (expected_h1_term not in title_value or "와와학습코칭센터" not in title_value):
        audit.error("directory_title", rel, repr(title_value))
    description_values = meta_content(dom, name="description")
    description_value = require_single(description_values, audit, "directory_description", rel)
    if description_value is not None and len(norm(description_value)) < 40:
        audit.error("directory_description", rel, f"too short: {description_value!r}")
    if title_value is not None:
        require_single(meta_content(dom, prop="og:title"), audit, "directory_og_title", rel, title_value)
    if description_value is not None:
        require_single(
            meta_content(dom, prop="og:description"),
            audit,
            "directory_og_description",
            rel,
            description_value,
        )
    h1_values = [node.text() for node in find_elements(dom, "h1")]
    if len(h1_values) != 1 or expected_h1_term not in h1_values[0]:
        audit.error("directory_h1", rel, repr(h1_values))
    directory_main = require_single(exact_nodes(dom, "data-grade-directory"), audit, "directory_main", rel)
    nav = nav_grade_links(dom)
    require_single(nav, audit, "directory_nav", rel)
    if nav and not has_class(nav[0], "active"):
        audit.error("directory_nav_active", rel, "grade nav link is not active")
    hrefs = [node.attrs.get("href", "") for node in find_elements(dom, "a")]
    if category:
        for attr in ("data-grade-search", "data-grade-status", "data-grade-list"):
            require_single(exact_nodes(dom, attr), audit, "directory_hook", f"{rel}:{attr}")
        expected_hrefs = [expected_detail_path(row.locality) for row in rows]
        counts = Counter(hrefs)
        missing = [href for href in expected_hrefs if counts[href] != 1]
        if missing:
            audit.error("directory_links", rel, f"non-single links={len(missing)}, sample={missing[:10]}")
    elif CATEGORY_PATH not in hrefs:
        audit.error("directory_category_link", rel, CATEGORY_PATH)
    graph = json_graph(dom, audit, rel)
    collections = graph_type(graph, "CollectionPage")
    if not collections:
        collections = graph_type(graph, "WebPage")
    collection = require_single(collections, audit, "directory_schema_page", rel)
    if collection is not None:
        if collection.get("url") != url or (title_value is not None and norm(collection.get("name")) != title_value):
            audit.error(
                "directory_schema_identity",
                rel,
                repr({"url": collection.get("url"), "name": collection.get("name")}),
            )
        for date_field in ("datePublished", "dateModified"):
            if collection.get(date_field) != RELEASE_DATE:
                audit.error("directory_schema_date", rel, f"{date_field}={collection.get(date_field)!r}")
        about_names = json_names(collection.get("about"))
        if not any(expected_h1_term in name or name in expected_h1_term for name in about_names):
            audit.error("directory_schema_about", rel, repr(sorted(about_names)))
        if not json_refs(collection.get("hasPart")):
            audit.error("directory_schema_haspart", rel, repr(collection.get("hasPart")))
    breadcrumbs = graph_type(graph, "BreadcrumbList")
    breadcrumb = require_single(breadcrumbs, audit, "directory_schema_breadcrumb", rel)
    if breadcrumb is not None:
        expected_names = ["홈", "학년별학원", *( ["중3 수학학원"] if category else [])]
        expected_urls = [BASE_URL + "/", encoded_url(GRADE_HUB_PATH), *( [encoded_url(CATEGORY_PATH)] if category else [])]
        items = breadcrumb.get("itemListElement")
        if not isinstance(items, list):
            audit.error("directory_schema_breadcrumb_items", rel, repr(items))
        else:
            names = [norm(item.get("name")) for item in items if isinstance(item, dict)]
            urls = [item.get("item") or item.get("url") for item in items if isinstance(item, dict)]
            positions = [item.get("position") for item in items if isinstance(item, dict)]
            if names != expected_names or urls != expected_urls or positions != list(range(1, len(expected_names) + 1)):
                audit.error(
                    "directory_schema_breadcrumb_items",
                    rel,
                    repr({"names": names, "urls": urls, "positions": positions}),
                )
    lists = graph_type(graph, "ItemList")
    item_list = require_single(lists, audit, "directory_schema_itemlist", rel)
    if category and item_list is not None:
        items = item_list.get("itemListElement")
        if not isinstance(items, list) or len(items) != EXPECTED_ROWS:
            audit.error("directory_schema_count", rel, f"count={len(items) if isinstance(items, list) else 'invalid'}")
        else:
            expected_urls = [encoded_url(expected_detail_path(row.locality)) for row in rows]
            actual_urls = [item.get("url") or item.get("item") for item in items if isinstance(item, dict)]
            positions = [item.get("position") for item in items if isinstance(item, dict)]
            if actual_urls != expected_urls or positions != list(range(1, EXPECTED_ROWS + 1)):
                audit.error("directory_schema_items", rel, "URL/order/position mismatch")
    for faq in graph_type(graph, "FAQPage"):
        pairs = faq_schema_pairs(faq)
        visible_values = [value for pair in pairs for value in pair]
        if not pairs or directory_main is None or not text_contains_in_order(directory_main.text(), visible_values):
            audit.error("directory_faq_visible_parity", rel, f"schema_pairs={len(pairs)}")


def validate_nav(view: View, audit: Audit, mode: str) -> None:
    paths = view.html_paths()
    if len(paths) != EXPECTED_FINAL_HTML:
        message = f"html={len(paths)}, expected={EXPECTED_FINAL_HTML}"
        if mode == "actual" and len(paths) == EXPECTED_BASE_HTML:
            audit.hold("html_count", "repo", message)
        else:
            audit.error("html_count", "repo", message)
    missing = 0
    duplicate = 0
    for rel in sorted(paths):
        dom = parse_dom(view.text(rel), audit, rel)
        if dom is None:
            continue
        count = len(nav_grade_links(dom))
        if count == 0:
            missing += 1
        elif count != 1:
            duplicate += 1
    if missing:
        message = f"pages missing grade nav={missing}"
        if mode == "actual" and missing == EXPECTED_BASE_HTML:
            audit.hold("grade_nav_missing", "repo", message)
        else:
            audit.error("grade_nav_missing", "repo", message)
    if duplicate:
        audit.error("grade_nav_duplicate", "repo", f"pages={duplicate}")
    audit.observations["nav"] = {"html": len(paths), "missing": missing, "duplicate": duplicate}


def parse_sitemap(text: str, audit: Audit, location: str) -> dict[str, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        audit.error("sitemap_parse", location, str(exc))
        return {}
    result: dict[str, str] = {}
    duplicate = 0
    for url_node in root.iter():
        if not url_node.tag.endswith("url"):
            continue
        loc = ""
        lastmod = ""
        for child in url_node:
            if child.tag.endswith("loc"):
                loc = norm(child.text)
            elif child.tag.endswith("lastmod"):
                lastmod = norm(child.text)
        if not loc:
            audit.error("sitemap_loc", location, "empty loc")
            continue
        if loc in result:
            duplicate += 1
        result[loc] = lastmod
    if duplicate:
        audit.error("sitemap_duplicate", location, f"duplicates={duplicate}")
    return result


def read_head_blob(
    root: Path,
    rel: str,
    audit: Audit,
    *,
    runner: Any = subprocess.run,
) -> str | None:
    try:
        result = runner(
            ["git", "-C", str(root), "show", f"HEAD:{rel}"],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        audit.error("git_blob_read", rel, repr(exc))
        return None
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else str(result.stderr or "")
        audit.error("git_blob_read", rel, f"exit={result.returncode}, stderr={norm(stderr)[:300]!r}")
        return None
    try:
        raw = result.stdout if isinstance(result.stdout, bytes) else str(result.stdout).encode("utf-8")
        return decode_utf8(raw)
    except UnicodeError as exc:
        audit.error("git_blob_read", rel, f"UTF-8 decode failed: {exc}")
        return None


def validate_sitemap(view: View, root: Path, rows: Sequence[SourceRow], audit: Audit, mode: str) -> None:
    if not view.exists(SITEMAP_REL):
        audit.error("sitemap_missing", SITEMAP_REL, "missing")
        return
    if mode == "actual":
        baseline_text = read_head_blob(root, SITEMAP_REL, audit)
        if baseline_text is None:
            return
    else:
        baseline_text = decode_utf8((root / SITEMAP_REL).read_bytes())
    baseline = parse_sitemap(baseline_text, audit, "baseline:sitemap")
    final = parse_sitemap(view.text(SITEMAP_REL), audit, SITEMAP_REL)
    expected_new = {
        encoded_url(GRADE_HUB_PATH),
        encoded_url(CATEGORY_PATH),
        *(encoded_url(expected_detail_path(row.locality)) for row in rows),
    }
    if len(baseline) != EXPECTED_BASE_SITEMAP:
        audit.error("sitemap_baseline_count", SITEMAP_REL, f"actual={len(baseline)}")
    if len(final) != EXPECTED_FINAL_SITEMAP:
        message = f"actual={len(final)}, expected={EXPECTED_FINAL_SITEMAP}"
        if mode == "actual" and final == baseline:
            audit.hold("sitemap_count", SITEMAP_REL, message)
        else:
            audit.error("sitemap_count", SITEMAP_REL, message)
    for url, lastmod in baseline.items():
        if final.get(url) != lastmod:
            audit.error("sitemap_non_target", SITEMAP_REL, f"url={url}, before={lastmod}, after={final.get(url)}")
            if len(audit.hard) > 200:
                break
    new_actual = set(final) - set(baseline)
    if new_actual != expected_new:
        message = f"missing={len(expected_new-new_actual)}, extra={len(new_actual-expected_new)}"
        if mode == "actual" and not new_actual:
            audit.hold("sitemap_new_urls", SITEMAP_REL, message)
        else:
            audit.error("sitemap_new_urls", SITEMAP_REL, message)
    for url in expected_new & set(final):
        if final[url] != RELEASE_DATE:
            audit.error("sitemap_lastmod", SITEMAP_REL, f"url={url}, lastmod={final[url]!r}")
    audit.observations["sitemap"] = {"baseline": len(baseline), "final": len(final), "new": len(new_actual)}


GRADE_NAV_TAG = re.compile(
    r"\s*<a(?=[^>]*\bhref=[\"']/학년별학원/[\"'])[^>]*>\s*학년별학원\s*</a>",
    re.IGNORECASE,
)
JSONLD_SCRIPT = re.compile(
    r"(<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>)(.*?)(</script>)",
    re.IGNORECASE | re.DOTALL,
)


def prune_grade_haspart(value: Any) -> Any:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                url_values = [item.get("url"), item.get("@id"), item.get("item")]
                if item.get("name") == "학년별학원" or any(
                    isinstance(candidate, str) and canonical_path(candidate) == GRADE_HUB_PATH
                    for candidate in url_values
                ):
                    continue
            result.append(prune_grade_haspart(item))
        return result
    if isinstance(value, dict):
        return {key: prune_grade_haspart(child) for key, child in value.items()}
    return value


def normalize_preserved_html(text: str, *, home: bool) -> str:
    text = text.replace("\r\n", "\n")
    text = GRADE_NAV_TAG.sub("", text)
    if home:
        def replace(match: re.Match[str]) -> str:
            try:
                value = json.loads(match.group(2))
            except json.JSONDecodeError:
                return match.group(0)
            value = prune_grade_haspart(value)
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return match.group(1) + payload + match.group(3)

        text = JSONLD_SCRIPT.sub(replace, text)
    return "\n".join(line.rstrip() for line in text.split("\n") if line.strip())


def validate_non_target_preservation(view: View, root: Path, audit: Audit) -> None:
    baseline_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.html")
        if not any(part in PRUNE_DIRS for part in path.relative_to(root).parts)
    }
    changed = 0
    for rel in sorted(baseline_paths):
        before = decode_utf8((root / rel).read_bytes())
        after = view.text(rel)
        if normalize_preserved_html(before, home=rel == "index.html") != normalize_preserved_html(
            after, home=rel == "index.html"
        ):
            audit.error("non_target_html", rel, "change exceeds grade nav/root hasPart allowance")
            changed += 1
            if changed >= 30:
                break
    audit.observations["preservation"] = {"baseline_html": len(baseline_paths), "violations": changed}


def validate_root_haspart(view: View, audit: Audit, mode: str) -> None:
    if not view.exists("index.html"):
        audit.error("root_missing", "index.html", "missing")
        return
    dom = parse_dom(view.text("index.html"), audit, "index.html")
    if dom is None:
        return
    graph = json_graph(dom, audit, "index.html")
    pages = [node for node in graph_type(graph, "WebPage") if node.get("url") == BASE_URL + "/"]
    page = require_single(pages, audit, "root_schema_webpage", "index.html")
    present = False
    if page is not None:
        present = any(canonical_path(ref) == GRADE_HUB_PATH for ref in json_refs(page.get("hasPart")))
    if not present:
        if mode == "actual":
            audit.hold("root_haspart", "index.html", "grade hub missing")
        else:
            audit.error("root_haspart", "index.html", "grade hub missing")


def is_subsequence(before: Sequence[str], after: Sequence[str]) -> bool:
    cursor = 0
    for value in before:
        while cursor < len(after) and after[cursor] != value:
            cursor += 1
        if cursor == len(after):
            return False
        cursor += 1
    return True


def validate_llms(view: View, root: Path, audit: Audit, mode: str) -> None:
    if not view.exists(LLMS_REL):
        audit.error("llms_missing", LLMS_REL, "missing")
        return
    before = decode_utf8((root / LLMS_REL).read_bytes())
    after = view.text(LLMS_REL)
    before_lines = [line.rstrip() for line in before.replace("\r\n", "\n").split("\n") if line.strip()]
    after_lines = [line.rstrip() for line in after.replace("\r\n", "\n").split("\n") if line.strip()]
    if not is_subsequence(before_lines, after_lines):
        audit.error("llms_preservation", LLMS_REL, "pre-existing non-empty lines are not an ordered subsequence")
    required = (raw_url(GRADE_HUB_PATH), raw_url(CATEGORY_PATH), "중3 수학학원")
    missing = [value for value in required if value not in after]
    if missing:
        if mode == "actual" and after == before:
            audit.hold("llms_grade", LLMS_REL, f"missing={missing}")
        else:
            audit.error("llms_grade", LLMS_REL, f"missing={missing}")


def normalized_template(value: str, manuscript: Manuscript, row: SourceRow) -> str:
    text = norm(unicodedata.normalize("NFKC", value)).lower()
    replacements = [
        manuscript.title,
        manuscript.query,
        row.address,
        row.center_name,
        row.registration,
        row.education_office,
        row.fee_url,
        row.locality,
        row.region,
        row.district,
        *sorted(row.middle_schools, key=len, reverse=True),
    ]
    for replacement in sorted({item for item in replacements if item}, key=len, reverse=True):
        text = text.replace(norm(replacement).lower(), " {fact} ")
    text = re.sub(r"\d+", "{n}", text)
    return norm(text)


def document_frequency(
    manuscripts: Sequence[Manuscript],
    rows: Sequence[SourceRow],
    selector: str,
) -> Counter[str]:
    result: Counter[str] = Counter()
    for manuscript, row in zip(manuscripts, rows, strict=False):
        if selector == "h2":
            values = manuscript.headings
        elif selector == "paragraph":
            values = manuscript.paragraphs
        else:
            values = tuple(
                sentence
                for paragraph in manuscript.paragraphs
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
                if norm(sentence)
            )
        result.update({normalized_template(value, manuscript, row) for value in values})
    return result


def validate_naturalness(manuscripts: Sequence[Manuscript], rows: Sequence[SourceRow], audit: Audit) -> None:
    within_duplicates = 0
    for manuscript, row in zip(manuscripts, rows, strict=False):
        for label, values in (
            ("h2", manuscript.headings),
            ("paragraph", manuscript.paragraphs),
        ):
            normalized = [normalized_template(value, manuscript, row) for value in values]
            duplicates = [value for value, count in Counter(normalized).items() if count > 1]
            if duplicates:
                within_duplicates += 1
                audit.error("within_page_duplicate", manuscript.filename, f"kind={label}, count={len(duplicates)}")
    metrics: dict[str, Any] = {"within_page_duplicates": within_duplicates}
    # These caps are deliberately above the immutable source baseline but low
    # enough to catch accidental copy/paste of a new shared section.
    caps = {"h2": 80, "paragraph": 140, "sentence": 140}
    for selector, cap in caps.items():
        values = document_frequency(manuscripts, rows, selector)
        maximum = max(values.values(), default=0)
        top = values.most_common(5)
        metrics[f"{selector}_max_df"] = maximum
        metrics[f"{selector}_top"] = top
        if maximum > cap:
            audit.error("cross_page_df", selector, f"max={maximum}, cap={cap}, top={top[:3]!r}")
    audit.observations["naturalness"] = metrics


def reconstructed_body(manuscript: Manuscript) -> str:
    blocks: list[str] = [*manuscript.intro]
    for section in manuscript.sections:
        blocks.append(f"## {section.heading}")
        blocks.extend(section.paragraphs)
    return "\n".join(blocks)


def boundary_sample(
    manuscripts: Sequence[Manuscript],
    rows: Sequence[SourceRow],
    audit: Audit,
) -> list[tuple[Manuscript, SourceRow]]:
    if len(manuscripts) != EXPECTED_ROWS or len(rows) != EXPECTED_ROWS:
        audit.error("boundary_sample_source", "source", "371 aligned rows are required")
        return []
    selected: set[int] = set()
    selected.update(index for index, row in enumerate(rows) if not row.supported)
    selected.update(index for index, row in enumerate(rows) if " " in row.locality)
    for value in (
        lambda item: len(item.title),
        lambda item: len(item.meta),
        lambda item: len(reconstructed_body(item)),
    ):
        maximum = max(value(item) for item in manuscripts)
        selected.add(next(index for index, item in enumerate(manuscripts) if value(item) == maximum))

    missing_school = [index for index, row in enumerate(rows) if not row.middle_schools]
    if len(missing_school) != EXPECTED_MIDDLE_SCHOOL_MISSING:
        audit.error("boundary_sample_missing_school", "source", f"actual={len(missing_school)}")
        return []
    # Nearest-integer ordinal spread over positions 0..52, matching the manual
    # content red-read contract: pos=(j*52+9)//19 for j=0..19.
    selected.update(missing_school[(j * 52 + 9) // 19] for j in range(20))

    # Fill to 66 by repeatedly choosing the ZIP ordinal farthest from any
    # already selected ordinal.  Ties resolve to the lower ordinal.
    while len(selected) < 66:
        candidates = (index for index in range(EXPECTED_ROWS) if index not in selected)
        chosen = max(candidates, key=lambda index: (min(abs(index - prior) for prior in selected), -index))
        selected.add(chosen)
    if len(selected) != 66:
        audit.error("boundary_sample_count", "source", f"actual={len(selected)}")
    sample = [(manuscripts[index], rows[index]) for index in sorted(selected)]
    paths = [expected_detail_rel(row.locality) for _, row in sample]
    payload = "".join(f"{path}\n" for path in paths).encode("utf-8")
    actual_sha = sha256_bytes(payload)
    if actual_sha != EXPECTED_BOUNDARY_SAMPLE_SHA256:
        audit.error(
            "boundary_sample_hash",
            "source",
            f"actual={actual_sha}, expected={EXPECTED_BOUNDARY_SAMPLE_SHA256}",
        )
    audit.observations["boundary_sample"] = {
        "count": len(sample),
        "sha256": actual_sha,
        "ordinals_1_based": [item.position for _, item in sample],
        "paths": paths,
    }
    return sample


def validate_boundary_sample(
    view: View,
    manuscripts: Sequence[Manuscript],
    rows: Sequence[SourceRow],
    audit: Audit,
) -> None:
    for manuscript, row in boundary_sample(manuscripts, rows, audit):
        rel = expected_detail_rel(row.locality)
        dom = parse_dom(view.text(rel), audit, f"boundary:{rel}")
        if dom is None:
            continue
        main = require_single(
            exact_nodes(dom, "data-grade-page", "middle3-math"),
            audit,
            "boundary_main",
            rel,
        )
        if main is None:
            continue
        heroes = [node for node in main.descendants() if node.tag == "section" and has_class(node, "math-hero")]
        hero = require_single(heroes, audit, "boundary_hero", rel)
        if hero is not None:
            hero_h1 = [node.text() for node in hero.descendants() if node.tag == "h1"]
            require_single(hero_h1, audit, "boundary_hero_h1", rel, manuscript.title)
            if manuscript.meta not in hero.text():
                audit.error("boundary_hero_meta", rel, "raw meta is absent from the hero")
        summaries = [node for node in main.descendants() if has_class(node, "math-summary-card")]
        summary = require_single(summaries, audit, "boundary_summary", rel)
        if summary is not None and summary.text().count(manuscript.json_summary) != 1:
            audit.error("boundary_summary_roundtrip", rel, "JSON-LD summary visible count is not one")
        fields = [node.attrs.get("data-source-field") for node in exact_nodes(main, "data-source-field")]
        if Counter(fields) != Counter(("grade", "middle-schools", "address", "registration", "fee")):
            audit.error("boundary_facts", rel, repr(fields))
        alerts = [node for node in main.descendants() if has_class(node, "grade-source-alert")]
        if len(alerts) != (0 if row.supported else 1):
            audit.error("boundary_alert", rel, f"count={len(alerts)}, supported={row.supported}")
        elif alerts and not SAFE_AVAILABILITY.search(alerts[0].text()):
            audit.error("boundary_alert_copy", rel, alerts[0].text())
        article = require_single(exact_nodes(main, "data-manuscript"), audit, "boundary_article", rel)
        if article is not None:
            article_h2 = [node.text() for node in article.descendants() if node.tag == "h2"]
            if len(article_h2) != 6 or tuple(article_h2) != manuscript.headings:
                audit.error("boundary_h2", rel, repr(article_h2))
        faq = require_single(exact_nodes(main, "data-faq"), audit, "boundary_faq", rel)
        if faq is not None and not text_contains_in_order(faq.text(), [value for pair in manuscript.faq for value in pair]):
            audit.error("boundary_faq_roundtrip", rel, "raw FAQ mismatch")
        review = require_single(exact_nodes(main, "data-review"), audit, "boundary_review", rel)
        if review is not None and not text_contains_in_order(review.text(), manuscript.review):
            audit.error("boundary_review_roundtrip", rel, "raw review mismatch")
        visible = main.text()
        if any(marker in visible for marker in MARKERS) or re.search(r"(?:\$\{|\{fact\}|undefined|\bNone\b)", visible):
            audit.error("boundary_template_artifact", rel, "marker/template artifact in visible copy")
        if MOJIBAKE.search(visible) or ADJACENT_REPEAT.search(visible) or GUARANTEE.search(visible):
            audit.error("boundary_naturalness", rel, "mojibake/repetition/guarantee pattern")


def validate_source_rendering(
    view: View,
    root: Path,
    manuscripts: Sequence[Manuscript],
    rows: Sequence[SourceRow],
    audit: Audit,
    mode: str,
) -> None:
    manuscript_by_locality = {item.locality: item for item in manuscripts}
    all_school_names = {school for row in rows for school in row.middle_schools}
    missing: list[str] = []
    for row in rows:
        rel = expected_detail_rel(row.locality)
        if not view.exists(rel):
            missing.append(rel)
            continue
        manuscript = manuscript_by_locality.get(row.locality)
        if manuscript is None:
            audit.error("manuscript_mapping", rel, "source manuscript missing")
            continue
        validate_detail(view.text(rel), manuscript, row, root, all_school_names, audit, mode)
    if missing:
        message = f"missing detail pages={len(missing)}, sample={missing[:5]}"
        if mode == "actual" and len(missing) == EXPECTED_ROWS:
            audit.hold("detail_pages_missing", "학년별학원/중3수학학원", message)
        else:
            audit.error("detail_pages_missing", "학년별학원/중3수학학원", message)
    else:
        validate_boundary_sample(view, manuscripts, rows, audit)
        validate_rendered_naturalness(view, manuscripts, rows, audit)


def validate_rendered_naturalness(
    view: View,
    manuscripts: Sequence[Manuscript],
    rows: Sequence[SourceRow],
    audit: Audit,
) -> None:
    counters: dict[str, Counter[str]] = {
        "h2": Counter(),
        "paragraph": Counter(),
        "sentence": Counter(),
    }
    query_counts: list[int] = []
    for manuscript, row in zip(manuscripts, rows, strict=False):
        rel = expected_detail_rel(row.locality)
        dom = parse_dom(view.text(rel), audit, f"rendered-naturalness:{rel}")
        if dom is None:
            continue
        main = require_single(
            exact_nodes(dom, "data-grade-page", "middle3-math"),
            audit,
            "rendered_naturalness_main",
            rel,
        )
        if main is None:
            continue
        h2_values = [node.text() for node in main.descendants() if node.tag == "h2" and node.text()]
        paragraph_values = [
            node.text()
            for node in main.descendants()
            if node.tag in {"p", "blockquote", "li"} and len(node.text()) >= 20
        ]
        sentence_values = [
            sentence
            for paragraph in paragraph_values
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if len(norm(sentence)) >= 20
        ]
        for label, values in (
            ("h2", h2_values),
            ("paragraph", paragraph_values),
            ("sentence", sentence_values),
        ):
            counters[label].update({normalized_template(value, manuscript, row) for value in values})
        query_counts.append(main.text().count(manuscript.query))
    metrics: dict[str, Any] = {
        "pages": len(query_counts),
        "query_min": min(query_counts, default=0),
        "query_max": max(query_counts, default=0),
    }
    for label, counter in counters.items():
        metrics[f"{label}_max_df"] = max(counter.values(), default=0)
        metrics[f"{label}_top"] = counter.most_common(5)
    audit.observations["rendered_naturalness"] = metrics


def validate_hubs(view: View, rows: Sequence[SourceRow], audit: Audit, mode: str) -> None:
    expected = (
        (GRADE_HUB_REL, GRADE_HUB_PATH, "학년별학원", False),
        (CATEGORY_REL, CATEGORY_PATH, "중3 수학학원", True),
    )
    for rel, path, h1, category in expected:
        if not view.exists(rel):
            if mode == "actual":
                audit.hold("directory_missing", rel, "not generated yet")
            else:
                audit.error("directory_missing", rel, "missing")
            continue
        validate_directory_page(view.text(rel), rel, path, h1, rows, audit, category=category)


def validate_git_baseline(root: Path, audit: Audit) -> None:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        audit.error("git_head", root, repr(exc))
        return
    if head != EXPECTED_BASE_HEAD:
        audit.error("git_head", root, f"actual={head}, expected={EXPECTED_BASE_HEAD}")
    audit.observations["git"] = {"head": head}


def source_snapshot(zip_path: Path, common: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (zip_path, common / CENTER_NAME, common / TARGET_SCHOOL_NAME, common / EO_NAME, common / IMAGE_NAME):
        if path.is_file():
            result[str(path)] = sha256_file(path)
    return result


def run(
    root: Path,
    zip_path: Path,
    common: Path,
    mode: str,
    generator: Path,
    expected_generator_sha: str,
) -> Audit:
    audit = Audit()
    root = root.resolve()
    zip_path = zip_path.resolve()
    common = common.resolve()
    source_before = source_snapshot(zip_path, common)
    manuscripts, _ = load_zip(zip_path, audit)
    rows = load_sources(common, manuscripts, audit)
    if len(manuscripts) != EXPECTED_ROWS or len(rows) != EXPECTED_ROWS:
        return audit
    validate_git_baseline(root, audit)
    validate_naturalness(manuscripts, rows, audit)
    view = View(root)
    if mode == "projected":
        view = projected_view(root, zip_path, common, generator.resolve(), expected_generator_sha, rows, audit)
    validate_source_rendering(view, root, manuscripts, rows, audit, mode)
    validate_hubs(view, rows, audit, mode)
    validate_nav(view, audit, mode)
    validate_sitemap(view, root, rows, audit, mode)
    validate_root_haspart(view, audit, mode)
    validate_llms(view, root, audit, mode)
    if mode == "projected":
        validate_non_target_preservation(view, root, audit)
    source_after = source_snapshot(zip_path, common)
    if source_after != source_before:
        audit.error("source_mutation", "source", "authoritative files changed during audit")
    audit.observations["result"] = {
        "mode": mode,
        "status": audit.status,
        "hard": len(audit.hard),
        "holds": len(audit.holds),
        "details": EXPECTED_ROWS,
    }
    return audit


def self_test() -> None:
    assert split_schools("나곡중/보라중/상갈중") == ("나곡중", "보라중", "상갈중")
    assert split_schools("쌍용중.계광중.월봉중") == ("쌍용중", "계광중", "월봉중")
    assert split_schools("천호중, 배재중, 명일중") == ("천호중", "배재중", "명일중")
    assert expected_detail_rel("부천 상동") == "학년별학원/중3수학학원/부천 상동/index.html"
    assert encoded_url(expected_detail_path("부천 상동")).endswith("/%EB%B6%80%EC%B2%9C%20%EC%83%81%EB%8F%99/")
    sample = """<!doctype html><html><head><title>테스트</title></head><body>
    <nav class="nav"><div class="nav-links"><a href="/학년별학원/">학년별학원</a></div></nav>
    <main data-grade-page="middle3-math"><p data-source-status="supported">확인</p></main>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage"}</script>
    </body></html>"""
    audit = Audit()
    dom = parse_dom(sample, audit, "selftest")
    assert dom is not None and not audit.hard
    assert len(nav_grade_links(dom)) == 1
    assert len(exact_nodes(dom, "data-grade-page", "middle3-math")) == 1
    assert len(json_graph(dom, audit, "selftest")) == 1
    assert text_contains_in_order("가 나 다 라", ["가 나", "다 라"])
    before = '<nav><a href="/x/">x</a></nav>'
    after = '<nav><a href="/x/">x</a>\n<a href="/학년별학원/">학년별학원</a></nav>'
    assert normalize_preserved_html(before, home=False) == normalize_preserved_html(after, home=False)
    positive_audit = Audit()
    positive = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"<urlset/>\n", b"")
    assert read_head_blob(Path("."), SITEMAP_REL, positive_audit, runner=positive) == "<urlset/>\n"
    assert not positive_audit.hard
    negative_audit = Audit()
    negative = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 128, b"", b"missing blob")
    assert read_head_blob(Path("."), SITEMAP_REL, negative_audit, runner=negative) is None
    assert [item.code for item in negative_audit.hard] == ["git_blob_read"]


def audit_payload(audit: Audit, max_findings: int) -> dict[str, Any]:
    def serialize(values: Sequence[Finding]) -> list[dict[str, str]]:
        return [
            {"code": item.code, "location": item.location, "message": item.message}
            for item in values[:max_findings]
        ]

    return {
        "status": audit.status,
        "exit_code": audit.exit_code,
        "hard_count": len(audit.hard),
        "hold_count": len(audit.holds),
        "hard": serialize(audit.hard),
        "holds": serialize(audit.holds),
        "observations": audit.observations,
    }


def default_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    zip_path = Path.home() / "Desktop" / ZIP_NAME
    common = root.parent / "참고자료" / "공통자료"
    return root, zip_path, common


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    root, zip_path, common = default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--zip-path", type=Path, default=zip_path)
    parser.add_argument("--common-dir", type=Path, default=common)
    parser.add_argument("--mode", choices=("actual", "projected"), default="actual")
    parser.add_argument("--generator", type=Path, default=root / GENERATOR_REL)
    parser.add_argument("--expected-generator-sha256", default=EXPECTED_GENERATOR_SHA256)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-findings", type=int, default=40)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
        print("SELFTEST PASS")
        return 0
    audit = run(
        root=args.root,
        zip_path=args.zip_path,
        common=args.common_dir,
        mode=args.mode,
        generator=args.generator,
        expected_generator_sha=str(args.expected_generator_sha256).lower(),
    )
    payload = audit_payload(audit, max(1, args.max_findings))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(
            f"{payload['status']} mode={args.mode} hard={payload['hard_count']} "
            f"holds={payload['hold_count']} details={EXPECTED_ROWS}"
        )
        for label in ("hard", "holds"):
            for item in payload[label]:
                print(f"{label.upper()} {item['code']} {item['location']}: {item['message']}")
        print("OBSERVATIONS " + json.dumps(payload["observations"], ensure_ascii=False, default=str))
    return audit.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
