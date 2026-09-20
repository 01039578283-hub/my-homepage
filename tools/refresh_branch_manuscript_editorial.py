"""Stage Step 3, audit scope and content, then optionally update existing pages.

The private report contains before/after excerpts. This tool never creates URLs,
deletes pages, changes source ZIPs/workbooks, rewrites feeds, or deploys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from lxml import html

import generate_branch_directory as directory
import generate_branch_topic_pages as topics
from branch_course_guidance import verify_source
from branch_manuscript_editorial import AUTHORING, corrections, edit_manuscript

ROOT = topics.ROOT
REPORT_ROOT = Path(r"C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-step3-20260920")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph(doc) -> list[dict]:
    return json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])["@graph"]


def scope_fingerprint(raw: str, child: bool, metadata: bool, abstract: bool) -> dict:
    doc = html.fromstring(raw)
    schema = graph(doc)
    for node in schema:
        if child and node.get("@type") == "FAQPage":
            # The course FAQ is immutable; only manuscript FAQs are editable.
            node["mainEntity"] = node["mainEntity"][:1]
        if child and node.get("@type") == "Article":
            node.pop("articleSection", None)
            if abstract:
                node.pop("abstract", None)
        if metadata and node.get("@type") in ("Article", "WebPage"):
            node.pop("description", None)
    result = {"schema": schema}
    editable = ["article", "faq"] if child else ["learning"]
    for identity in editable:
        for element in doc.xpath(f'//*[@id="{identity}"]'):
            element.getparent().remove(element)
    if child:
        for element in doc.xpath('//section[contains(@class,"branch-topic-example")]'):
            element.getparent().remove(element)
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        script.getparent().remove(script)
    if metadata:
        for element in doc.xpath('//meta[@name="description" or @property="og:description"] | //p[@class="branch-lead"]'):
            element.getparent().remove(element)
    result["protectedHTML"] = html.tostring(doc, encoding="unicode")
    return result


def validate_editorial(item: dict, edited: dict, path: str) -> None:
    headings = [s["heading"] for s in edited["sections"]]
    texts = edited["intro"] + headings + [p for s in edited["sections"] for p in s["paragraphs"]]
    texts += [f["question"] + " " + f["answer"] for f in edited["faq"]] + edited["example"]
    if any(AUTHORING.search(t) for t in texts):
        raise ValueError(f"작성용 표현 잔존: {path}")
    if len({f["question"] for f in edited["faq"]}) != len(edited["faq"]):
        raise ValueError(f"FAQ 질문 중복: {path}")
    if len(headings) != len(item["sections"]) or len(set(headings)) != len(headings):
        raise ValueError(f"본문 구조 누락 또는 제목 중복: {path}")
    if any(not s["paragraphs"] for s in edited["sections"]):
        raise ValueError(f"빈 본문: {path}")
    correction = corrections().get((item["locality"], item["level"], item["subject"]))
    if correction and re.search(correction["pattern"], " ".join(texts) + edited["description"] + edited["abstract"]):
        raise ValueError(f"교정 대상 예시가 남음: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    verify_source(directory.SOURCE_WORKBOOK)
    protected = [topics.BRANCH_MANIFEST, topics.DATA_ROOT / "pages.json", ROOT / "sitemap.xml", ROOT / "rss.xml", directory.SOURCE_WORKBOOK]
    protected += [topics.MANUSCRIPT_ROOT / topic["zip"] for topic in topics.TOPICS]
    source_hashes = {str(path): sha(path) for path in protected}
    centers = json.loads(topics.BRANCH_MANIFEST.read_text(encoding="utf-8"))["centers"]
    records = json.loads((topics.DATA_ROOT / "pages.json").read_text(encoding="utf-8"))["pages"]
    by_name = {c["routeName"]: c for c in centers}
    originals = topics.load_manuscripts()
    assert len(centers) == 193 and len(records) == 2226
    stage = REPORT_ROOT / "staged-site"
    backup = REPORT_ROOT / "before-step3"
    directory.OUTPUT_ROOT = stage / "지점안내"
    staged: list[tuple[str, bool, bool, bool]] = []
    edits = []
    totals = Counter()
    page_stats = Counter()
    for center in centers:
        path = directory.generate_branch_page(center)
        staged.append((path.strip("/") + "/index.html", False, False, False))
    for record in records:
        source = originals[(record["locality"], record["level"], record["subject"])]
        center = by_name[record["center"]]
        edited, events = edit_manuscript(center, source)
        validate_editorial(source, edited, record["path"])
        # Rendering applies the same deterministic editor once to the source.
        path, relative = topics.render_page(center, source, output_root=stage)
        if path != record["path"] or Path(relative).as_posix() != Path(record["file"]).as_posix():
            raise ValueError(f"기존 경로 변경: {record['path']}")
        meta_changed = source["description"] != edited["description"]
        abstract_changed = source["abstract"] != edited["abstract"]
        staged.append((relative, True, meta_changed, abstract_changed))
        totals.update(e["kind"] for e in events)
        page_stats.update(set(e["kind"] for e in events))
        page_stats["changedFromSource"] += source != edited
        page_stats["descriptionCorrected"] += meta_changed
        page_stats["abstractCorrected"] += abstract_changed
        edits.append({"path": path, "events": events})

    changed = Counter()
    for relative, child, metadata, abstract in staged:
        destination = (ROOT / relative).resolve()
        if not destination.is_relative_to((ROOT / "지점안내").resolve()) or not destination.is_file():
            raise ValueError(f"기존 지점안내 밖의 경로: {relative}")
        old = destination.read_text(encoding="utf-8")
        new = (stage / relative).read_text(encoding="utf-8")
        before = scope_fingerprint(old, child, metadata, abstract)
        after = scope_fingerprint(new, child, metadata, abstract)
        if before != after:
            keys = [key for key in before if before[key] != after[key]]
            raise ValueError(f"본문 교정 범위 밖 변경: {relative}/{keys}")
        if old != new:
            changed["children" if child else "centers"] += 1
        doc = html.fromstring(new)
        ids = doc.xpath('//*[@id]/@id')
        if len(ids) != len(set(ids)):
            raise ValueError(f"중복 HTML id: {relative}")
        faq = next(n for n in graph(doc) if n.get("@type") == "FAQPage")
        visible = [(d.xpath('./summary')[0].text_content(), d.xpath('./p')[0].text_content()) for d in doc.xpath('//section[@id="faq"]//details')]
        if visible != [(q["name"], q["acceptedAnswer"]["text"]) for q in faq["mainEntity"]]:
            raise ValueError(f"FAQ 본문/구조화 데이터 불일치: {relative}")

    # Check every source hash again before changing a single destination.
    if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
        raise RuntimeError("실행 도중 원본 또는 보호 파일이 바뀌었습니다.")
    if args.write:
        for relative, *_ in staged:
            destination = ROOT / relative
            original_copy = backup / relative
            original_copy.parent.mkdir(parents=True, exist_ok=True)
            if not original_copy.exists():
                original_copy.write_bytes(destination.read_bytes())
            if destination.read_bytes() != (stage / relative).read_bytes():
                destination.write_bytes((stage / relative).read_bytes())
    report = {
        "centerPages": 193, "childPages": 2226, "changedThisRun": dict(changed),
        "cumulativeChangedSinceStep2": {
            "centers": sum((backup / relative).is_file() and (backup / relative).read_bytes() != (stage / relative).read_bytes() for relative, child, *_ in staged if not child),
            "children": sum((backup / relative).is_file() and (backup / relative).read_bytes() != (stage / relative).read_bytes() for relative, child, *_ in staged if child),
        } if args.write else None,
        "sourcePageChanges": dict(page_stats), "editCounts": dict(totals),
        "protected": ["title", "H1", "canonical", "URLs", "first course answer", "course conditions", "image attributes and order", "full body-image display", "internal links", "source files", "sitemap", "RSS"],
        "narrowMetadataExceptions": "교정한 과목·학교급 예시가 남는 description/abstract만 함께 수정; 전체 메타 역할 정리는 다음 단계",
        "sourceHashes": source_hashes, "appliedLocally": args.write, "deployed": False,
        "scopeValidationErrors": 0, "editorialValidationErrors": 0,
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT_ROOT / "editorial-diff.json").write_text(json.dumps(edits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "sourceHashes"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
