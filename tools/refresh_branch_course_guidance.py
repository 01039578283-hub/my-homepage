"""Stage and verify Step 2 before updating only existing branch/topic pages.

No recursive deletion, media conversion, URL creation, sitemap/RSS update or
deployment. Originals and unrelated pages remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from lxml import html

import generate_branch_directory as directory
import generate_branch_topic_pages as topics
from branch_course_guidance import course_guidance, verify_source

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = Path(r"C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-step2-20260920")
MANIFEST = ROOT / "tools/data/branch-topic-pages/pages.json"


def fingerprint(raw: str, child: bool) -> dict:
    doc = html.fromstring(raw)
    sections = ["article", "related-pages"] if child else ["schools", "learning", "consult", "learning-pages"]
    fixed = {
        "title": doc.xpath('//title/text()'), "h1": doc.xpath('//h1/text()'),
        "canonical": doc.xpath('//link[@rel="canonical"]/@href'),
        "meta": doc.xpath('//meta[not(@name="viewport")]/@content'),
        "images": [dict(el.attrib) for el in doc.xpath('//img | //source')],
        "header": [html.tostring(el, encoding="unicode") for el in doc.xpath('//header')],
        "footer": [html.tostring(el, encoding="unicode") for el in doc.xpath('//footer')],
    }
    for section in sections:
        fixed[section] = [html.tostring(el, encoding="unicode") for el in doc.xpath(f'//*[@id="{section}"]')]
    if child:
        fixed["examples"] = [html.tostring(el, encoding="unicode") for el in doc.xpath('//section[contains(@class,"branch-topic-example")]')]
    for text in doc.xpath('//script[@type="application/ld+json"]/text()'):
        article = next((node for node in json.loads(text).get("@graph", []) if node.get("@type") == "Article"), {})
        fixed["articleMetadata"] = {k: article.get(k) for k in ("headline", "description", "abstract", "image", "datePublished")}
    return fixed


def verify_preserved(old: str, new: str, child: bool, path: str) -> None:
    before, after = fingerprint(old, child), fingerprint(new, child)
    changed = [key for key in before if before[key] != after[key]]
    if changed:
        raise ValueError(f"요청 범위 밖 변경: {path} / {changed}")
    if child:
        old_doc, new_doc = html.fromstring(old), html.fromstring(new)
        old_questions = {el.xpath('./summary')[0].text_content(): el.xpath('./p')[0].text_content() for el in old_doc.xpath('//section[@id="faq"]//details')}
        new_questions = {el.xpath('./summary')[0].text_content(): el.xpath('./p')[0].text_content() for el in new_doc.xpath('//section[@id="faq"]//details')}
        # Only the Step 2 grade FAQ may change on a later scoped regeneration.
        if any(new_questions.get(q) != answer for q, answer in old_questions.items() if not q.endswith("안내 학년과 수업 조건은 무엇인가요?")):
            raise ValueError(f"기존 원고 FAQ 변경: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="검증 성공 후 기존 파일에만 반영")
    args = parser.parse_args()
    verify_source(directory.SOURCE_WORKBOOK)
    branch_bytes = topics.BRANCH_MANIFEST.read_bytes()
    centers = json.loads(branch_bytes)["centers"]
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_name = {c["routeName"]: c for c in centers}
    assert len(centers) == 193 and len(records["pages"]) == 2226
    manuscripts = topics.load_manuscripts()
    stage = (REPORT_ROOT / "staged-site").resolve()
    if not stage.is_relative_to(REPORT_ROOT.resolve()):
        raise ValueError("스테이징 경로 오류")
    directory.OUTPUT_ROOT = stage / "지점안내"
    staged_files = []
    for center in centers:
        path = directory.generate_branch_page(center)
        staged_files.append((path.strip("/") + "/index.html", False))
    published = pending = changed = 0
    for record in records["pages"]:
        center = by_name[record["center"]]
        key = (record["locality"], record["level"], record["subject"])
        item = manuscripts[key]
        path, file_name = topics.render_page(center, item, output_root=stage)
        if path != record["path"] or Path(file_name).as_posix() != Path(record["file"]).as_posix():
            raise ValueError(f"기존 URL 매핑이 바뀜: {key}")
        view = course_guidance(center, record["subject"], item["prefix"])
        record["publishedGrades"] = view["grades"]
        record["confirmationGrades"] = view["pendingGrades"]
        published += bool(view["grades"])
        pending += bool(view["pendingGrades"])
        staged_files.append((file_name, True))
    for relative, child in staged_files:
        destination = (ROOT / relative).resolve()
        if not destination.is_relative_to((ROOT / "지점안내").resolve()) or not destination.is_file():
            raise ValueError(f"기존 지점안내 경로 밖: {relative}")
        original = destination.read_text(encoding="utf-8")
        generated = (stage / relative).read_text(encoding="utf-8")
        verify_preserved(original, generated, child, relative)
        changed += original != generated
    if args.write:
        for relative, _ in staged_files:
            (ROOT / relative).write_bytes((stage / relative).read_bytes())
        MANIFEST.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if topics.BRANCH_MANIFEST.read_bytes() != branch_bytes:
        raise RuntimeError("센터 원본 manifest가 변경됐습니다.")
    report = {
        "centerPages": len(centers), "childPages": len(records["pages"]),
        "changedPages": changed, "serviceSchemaPages": published,
        "childPagesWithPendingGrades": pending,
        "childPagesWithoutPublishedGrade": len(records["pages"]) - published,
        "originalGradeRecordAbsentPages": sum(not p["availableInCenterData"] for p in records["pages"]),
        "preserved": ["URLs", "title", "H1", "canonical", "metadata", "image attributes and order", "original manuscripts", "original FAQs", "internal links", "raw center data", "sitemap", "RSS"],
        "workbookSha256": hashlib.sha256(directory.SOURCE_WORKBOOK.read_bytes()).hexdigest(),
        "appliedLocally": args.write, "deployed": False,
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
