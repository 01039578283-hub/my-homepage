"""Stage Step 4 and change only existing metadata, abstracts and hero leads.

No deployment or Git operations. Before writing any destination, compare the
entire remaining DOM/schema and guard all source/manifests/assets/feeds by hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from lxml import html

import generate_branch_directory as directory
import generate_branch_topic_pages as topics
from branch_course_guidance import verify_source
from branch_manuscript_editorial import AUTHORING, edit_manuscript, other_level_school_names
from branch_page_summaries import center_summaries, topic_summaries, validate_summaries, summary_document_errors

ROOT = topics.ROOT
REPORT_ROOT = Path(r"C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-step4-20260920")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph(document) -> list[dict]:
    return json.loads(document.xpath('//script[@type="application/ld+json"]/text()')[0])["@graph"]


def scope_fingerprint(raw: str) -> dict:
    document = html.fromstring(raw)
    schema = graph(document)
    for node in schema:
        if node.get("@type") in ("Article", "WebPage"):
            node.pop("description", None)
        if node.get("@type") == "Article":
            node.pop("abstract", None)
    for element in document.xpath('//meta[@name="description" or @property="og:description"] | //p[@class="branch-lead"] | //script[@type="application/ld+json"]'):
        element.getparent().remove(element)
    return {"schema": schema, "protectedHTML": html.tostring(document, encoding="unicode")}


def read_summary(raw: str) -> dict:
    doc = html.fromstring(raw)
    article = next(n for n in graph(doc) if n.get("@type") == "Article")
    return {
        "description": doc.xpath('//meta[@name="description"]/@content')[0],
        "abstract": article["abstract"],
        "lead": doc.xpath('//p[@class="branch-lead"]')[0].text_content(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    verify_source(directory.SOURCE_WORKBOOK)
    centers = json.loads(topics.BRANCH_MANIFEST.read_text(encoding="utf-8"))["centers"]
    records = json.loads((topics.DATA_ROOT / "pages.json").read_text(encoding="utf-8"))["pages"]
    assert len(centers) == 193 and len(records) == 2226
    by_name = {center["routeName"]: center for center in centers}
    originals = topics.load_manuscripts()
    stage = REPORT_ROOT / "staged-site"
    backup = REPORT_ROOT / "before-step4"
    protected = [topics.BRANCH_MANIFEST, topics.DATA_ROOT / "pages.json", ROOT / "sitemap.xml", ROOT / "rss.xml", directory.SOURCE_WORKBOOK]
    protected += [topics.MANUSCRIPT_ROOT / topic["zip"] for topic in topics.TOPICS]
    protected += list((ROOT / "assets").rglob("*.css"))
    protected += list((ROOT / "tools/data/branch-directory").glob("*.json"))
    protected += list((ROOT / "tools/data/branch-topic-pages").glob("*.json"))
    source_hashes = {str(path): sha(path) for path in protected}
    directory.OUTPUT_ROOT = stage / "지점안내"
    staged = []
    for center in centers:
        path = directory.generate_branch_page(center)
        staged.append((path.strip("/") + "/index.html", center, None, center_summaries(center)))
    for record in records:
        center = by_name[record["center"]]
        source = originals[(record["locality"], record["level"], record["subject"])]
        item, _ = edit_manuscript(center, source)
        summary = topic_summaries(center, item)
        validate_summaries(center, summary, item)
        path, relative = topics.render_page(center, source, output_root=stage)
        if path != record["path"] or Path(relative).as_posix() != Path(record["file"]).as_posix():
            raise ValueError(f"기존 경로가 달라졌습니다: {record['path']}")
        staged.append((relative, center, item, summary))

    counts = Counter()
    prior_issues = Counter()
    all_summaries = []
    changes = []
    for relative, center, item, expected in staged:
        destination = (ROOT / relative).resolve()
        if not destination.is_relative_to((ROOT / "지점안내").resolve()) or not destination.is_file():
            raise ValueError(f"기존 지점 페이지 밖의 경로: {relative}")
        old = destination.read_text(encoding="utf-8")
        new = (stage / relative).read_text(encoding="utf-8")
        before = scope_fingerprint(old)
        after = scope_fingerprint(new)
        if before != after:
            fields = [key for key in before if before[key] != after[key]]
            raise ValueError(f"요약 수정 범위 밖 변경: {relative}/{fields}")
        doc = html.fromstring(new)
        errors = summary_document_errors(doc, graph(doc), expected)
        if errors:
            raise ValueError(f"{relative}: {errors}")
        baseline = (backup / relative).read_text(encoding="utf-8") if (backup / relative).is_file() else old
        previous = read_summary(baseline)
        kind = "children" if item else "centers"
        counts[f"{kind}.pagesChanged"] += baseline != new
        counts["changedThisRun"] += old != new
        prior_issues["metaEqualsLead"] += previous["description"] == previous["lead"]
        prior_issues["metaEqualsAbstract"] += previous["description"] == previous["abstract"]
        prior_issues["abstractAuthoring"] += bool(AUTHORING.search(previous["abstract"]))
        prior_issues["abstractForeignTypo"] += "तथा" in previous["abstract"]
        if item:
            for field in ("description", "abstract"):
                prior_issues[field + "OtherLevelSchools"] += bool(other_level_school_names(center, item["level"], previous[field]))
        for field in expected:
            counts[f"{kind}.{field}Changed"] += previous[field] != expected[field]
        all_summaries.append(expected)
        changes.append({"file": relative, "before": previous, "after": expected})
    duplicates = {field: len(all_summaries) - len({s[field] for s in all_summaries}) for field in ("description", "abstract", "lead")}
    if any(duplicates.values()):
        raise ValueError(f"요약 필드 중복: {duplicates}")
    if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
        raise ValueError("원본·보호 파일이 실행 도중 변경되었습니다.")
    if args.write:
        for relative, *_ in staged:
            destination = ROOT / relative
            before_path = backup / relative
            before_path.parent.mkdir(parents=True, exist_ok=True)
            if not before_path.exists():
                before_path.write_bytes(destination.read_bytes())
            generated = (stage / relative).read_bytes()
            if destination.read_bytes() != generated:
                destination.write_bytes(generated)
    report = {
        "centerPages": len(centers), "childPages": len(records), "counts": dict(counts),
        "previousIssues": dict(prior_issues), "duplicateSummaryFields": duplicates,
        "descriptionLength": {"min": min(len(s["description"]) for s in all_summaries), "max": max(len(s["description"]) for s in all_summaries)},
        "scopeValidationErrors": 0, "summaryValidationErrors": 0,
        "protected": ["URLs", "title", "H1", "canonical", "course first answer and qualifications", "full body", "FAQ", "examples", "all image attributes and order", "all links", "CSS", "source files", "manifests", "sitemap", "RSS"],
        "sourceHashes": source_hashes, "appliedLocally": args.write, "deployed": False,
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT_ROOT / "summary-diff.json").write_text(json.dumps(changes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "sourceHashes"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
