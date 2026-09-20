"""Stage and audit Step 5 navigation before changing any existing page.

Run without flags for a dry run; --write applies locally, never deploys.
Immutable before-step5 snapshots and reports stay outside the public site.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import html

from branch_course_guidance import course_guidance
from branch_learning_routes import ROOT, STYLE, canonical, paired_routes, upgrade_page

REPORT_ROOT = Path(r"C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-step5-20260920")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph(doc) -> list[dict]:
    return json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])["@graph"]


def scope_fingerprint(raw: str, kind: str, routes: dict) -> dict:
    doc = html.fromstring(raw)
    schema = graph(doc)
    added = set(map(canonical, [routes["child"], routes["parent"]] if kind == "guide" else [routes["guide"]]))
    for node in schema:
        if node.get("@type") == "WebPage":
            links = node.get("relatedLink", [])
            links = [links] if isinstance(links, str) else links
            retained = [url for url in links if url not in added]
            if retained:
                node["relatedLink"] = retained
            else:
                node.pop("relatedLink", None)
        if kind == "child" and node.get("@type") == "ItemList" and node.get("@id", "").endswith("#related-pages"):
            node["itemListElement"] = [entry for entry in node["itemListElement"] if entry.get("url") != canonical(routes["guide"])]
            node["numberOfItems"] = len(node["itemListElement"])
    for element in doc.xpath(f'//link[@href="{STYLE}"] | //*[@id="learning-route-top" or @id="learning-route-bottom"] | //a[@data-learning-route="guide"] | //script[@type="application/ld+json"]'):
        element.getparent().remove(element)
    for comment in doc.xpath('//comment()'):
        if (comment.text or "").strip().startswith("learning-routes:"):
            comment.getparent().remove(comment)
    role_query = '//section[@class="math-hero"]//p[@class="math-eyebrow"]' if kind == "guide" else '//section[@class="branch-topic-hero"]/p[@class="branch-kicker"]'
    roles = doc.xpath(role_query)
    if len(roles) != 1:
        raise ValueError("역할 표시가 하나가 아닙니다.")
    roles[0].text = "[page-role]"
    # Ignore only inter-tag formatting, not any substantive text or attributes.
    for element in doc.iter():
        if element.text is not None and not element.text.strip():
            element.text = None
        if element.tail is not None and not element.tail.strip():
            element.tail = None
    return {"schema": schema, "html": html.tostring(doc, encoding="unicode")}


def route_errors(raw: str, center: dict, item: dict, kind: str, routes: dict, root: Path, stage: Path) -> list[str]:
    doc = html.fromstring(raw)
    errors = []
    ids = doc.xpath('//*[@id]/@id')
    if len(ids) != len(set(ids)):
        errors.append("duplicate IDs")
    top = doc.xpath('//*[@id="learning-route-top"]')
    bottom = doc.xpath('//*[@id="learning-route-bottom"]') if kind == "guide" else doc.xpath('//a[@data-learning-route="guide"]')
    if len(top) != 1 or len(bottom) != 1:
        errors.append("missing or repeated bridge")
    if len(doc.xpath(f'//link[@href="{STYLE}"]')) != 1:
        errors.append("route stylesheet count")
    expected = routes["child"] + "#overview" if kind == "guide" else routes["guide"]
    if not top or expected not in top[0].xpath('.//a/@href'):
        errors.append("wrong exact subject/level/locality route")
    elif not (doc.xpath('//main//*[self::nav or self::section]').index(top[0]) < next(i for i, el in enumerate(doc.xpath('//main//*[self::nav or self::section]')) if el.get('class') in ('math-media-section', 'branch-primary-media'))):
        errors.append("bridge is not above media")
    nodes = doc.xpath('//*[@id="learning-route-top" or @id="learning-route-bottom"]//a | //a[@data-learning-route="guide"]')
    for link in nodes:
        value = urlsplit(link.get("href", ""))
        if value.netloc or value.query or not value.path.startswith("/"):
            errors.append("non-local bridge")
            continue
        relative = Path(unquote(value.path).strip("/")) / "index.html"
        destination = stage / relative if (stage / relative).is_file() else root / relative
        if not destination.is_file():
            errors.append(f"missing route {relative}")
        elif value.fragment:
            target = html.fromstring(destination.read_text(encoding="utf-8"))
            if value.fragment not in target.xpath('//*[@id]/@id'):
                errors.append(f"missing fragment {value.fragment}")
    page = next(n for n in graph(doc) if n.get("@type") == "WebPage")
    for url in [routes["child"], routes["parent"]] if kind == "guide" else [routes["guide"]]:
        if canonical(url) not in page.get("relatedLink", []):
            errors.append("schema relatedLink mismatch")
    if kind == "child":
        lists = [n for n in graph(doc) if n.get("@id", "").endswith("#related-pages")]
        links = doc.xpath('//*[@id="related-pages"]//div[@class="related-grid"]/a')
        if len(lists) != 1 or lists[0]["numberOfItems"] != len(links):
            errors.append("related ItemList size")
        else:
            for i, (link, entry) in enumerate(zip(links, lists[0]["itemListElement"]), 1):
                if entry["position"] != i or entry["url"] != canonical(link.get("href")) or entry["name"] != link.xpath('./strong')[0].text_content():
                    errors.append("related ItemList content")
    if upgrade_page(raw, center, item, kind, root) != raw:
        errors.append("not idempotent")
    return errors


def legacy_fact_differences(raw: str, center: dict, item: dict) -> dict:
    doc = html.fromstring(raw)
    values = {}
    for row in doc.xpath('//aside[@class="math-info-card"]/dl/div'):
        values[row.find('dt').text_content()] = row.find('dd')
    view = course_guidance(center, item["subject"], "고")
    grade_value = values.get(f'고등 {item["subject"]} 안내 학년')
    if grade_value is None:
        grade_value = values[f'고등 {item["subject"]} 수업 가능 학년']
    grades = re.findall(r'고[1-3]', grade_value.text_content())
    result = {}
    old_name = values["센터 기준"].text_content().strip()
    if old_name != center["displayName"]:
        result["centerLabel"] = {"existing": old_name, "reviewed": center["displayName"]}
    if grades != view["grades"]:
        result["grades"] = {"existing": grades, "reviewed": view["grades"], "pending": view["pendingGrades"]}
    old_address = values["제공 주소"].text_content().strip()
    if re.sub(r'\s+', '', old_address) != re.sub(r'\s+', '', center["address"]):
        result["addressText"] = {"existing": old_address, "reviewed": center["address"]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    centers = json.loads((ROOT / "tools/data/branch-directory/branches.json").read_text(encoding="utf-8"))["centers"]
    records = json.loads((ROOT / "tools/data/branch-topic-pages/pages.json").read_text(encoding="utf-8"))["pages"]
    by_name = {c["routeName"]: c for c in centers}
    if len(by_name) != len(centers):
        raise ValueError("중복 센터명")
    pairs = []
    for item in records:
        center = by_name[item["center"]]
        routes = paired_routes(center, item)
        if routes:
            if routes["child"] != item["path"]:
                raise ValueError("manifest와 지점 경로가 다릅니다.")
            pairs.append((center, item, routes))
    if len(pairs) != 742 or len({r['child'] for _, _, r in pairs}) != 742 or len({r['guide'] for _, _, r in pairs}) != 742:
        raise ValueError(f"예상된 742개 고유 연결 쌍이 아닙니다: {len(pairs)}")
    target_files = {str((ROOT / routes[kind].strip('/') / 'index.html').resolve()) for _, _, routes in pairs for kind in ('guide', 'child')}
    protected = [p for p in ROOT.rglob('*.html') if str(p.resolve()) not in target_files]
    protected += list((ROOT / 'assets').rglob('*.*'))
    protected += list((ROOT / 'tools/data').rglob('*.json'))
    protected += [p for p in ROOT.glob('*.xml')]
    protected += [ROOT / 'robots.txt', Path(r'C:\Users\1992k\Desktop\센터정보\코칭센터_데이터_.xlsx')]
    source_root = Path(r'C:\Users\1992k\Desktop\프로그램 원고')
    protected += [source_root / f'{level} {subject}학원.zip' for level in ('초등', '중등', '고등') for subject in ('수학', '영어')]
    protected = sorted(set(protected))
    source_hashes = {str(p): sha(p) for p in protected}
    stage, backup = REPORT_ROOT / 'staged-site', REPORT_ROOT / 'before-step5'
    staged = []
    differences = []
    counts = Counter()
    for center, item, routes in pairs:
        for kind in ('guide', 'child'):
            relative = Path(routes[kind].strip('/')) / 'index.html'
            destination = (ROOT / relative).resolve()
            if not destination.is_relative_to(ROOT.resolve()) or not destination.is_file():
                raise ValueError(f"기존 페이지 밖 경로: {relative}")
            old = destination.read_text(encoding='utf-8')
            new = upgrade_page(old, center, item, kind)
            if scope_fingerprint(old, kind, routes) != scope_fingerprint(new, kind, routes):
                raise ValueError(f"역할·내부링크 범위 밖 변경: {relative}")
            # Refuse to lose even an existing duplicate link.
            before_links = Counter(html.fromstring(old).xpath('//a/@href'))
            after_links = Counter(html.fromstring(new).xpath('//a/@href'))
            if before_links - after_links:
                raise ValueError(f"기존 링크 손실: {relative}")
            if kind == 'guide':
                difference = legacy_fact_differences(old, center, item)
                if difference:
                    differences.append({'file': relative.as_posix(), 'center': center['routeName'], 'differences': difference})
            generated = stage / relative
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text(new, encoding='utf-8')
            counts['changedThisRun'] += old != new
            baseline = (backup / relative).read_text(encoding='utf-8') if (backup / relative).is_file() else old
            counts[kind + 'PagesChanged'] += baseline != new
            staged.append((relative, center, item, routes, kind, sha(destination)))
    for relative, center, item, routes, kind, digest in staged:
        errors = route_errors((stage / relative).read_text(encoding='utf-8'), center, item, kind, routes, ROOT, stage)
        if errors:
            raise ValueError(f'{relative}: {errors}')
        if sha(ROOT / relative) != digest:
            raise ValueError(f'작업 중 대상 페이지 변경: {relative}')
    if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
        raise ValueError('대상 밖 페이지·원본·자산·피드 변경')
    if args.write:
        for relative, *_ in staged:
            destination, original = ROOT / relative, backup / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            if not original.exists():
                original.write_bytes(destination.read_bytes())
            generated = (stage / relative).read_bytes()
            if destination.read_bytes() != generated:
                destination.write_bytes(generated)
        if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
            raise ValueError('적용 후 보호 파일 해시 불일치')
        if any(sha(ROOT / relative) != sha(stage / relative) for relative, *_ in staged):
            raise ValueError('적용 후 페이지 불일치')
    diff_counts = Counter(key for row in differences for key in row['differences'])
    report = {
        'pairs': len(pairs), 'pages': len(staged), 'centers': len({c['routeName'] for c, _, _ in pairs}),
        'counts': dict(counts), 'routeErrors': 0, 'scopeErrors': 0, 'existingLinksLost': 0,
        'protectedFileCount': len(source_hashes), 'protectedHashes': source_hashes,
        'nonTargetHtmlCount': sum(Path(p).suffix == '.html' for p in source_hashes),
        'legacyFactDifferencePages': len(differences), 'legacyFactDifferenceFields': dict(diff_counts),
        'appliedLocally': args.write, 'deployed': False,
        'pairsManifest': [{'guide': r['guide'], 'child': r['child'], 'parent': r['parent']} for _, _, r in pairs],
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (REPORT_ROOT / 'legacy-fact-review.json').write_text(json.dumps(differences, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('protectedHashes', 'pairsManifest')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
