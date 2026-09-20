"""Stage/check Step 7 and optionally write exactly 636 local HTML files.

Never commits, pushes, deploys or calls webmaster tools. Sources and backup/
verification outputs remain outside the website's public directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from lxml import html
from openpyxl import load_workbook

from branch_course_guidance import course_guidance
from generate_branch_directory import SOURCE_WORKBOOK, TARGET_WORKBOOK, branch_key, clean, school_key, split_values
from refresh_branch_learning_routes import route_errors
from refresh_subject_guide_facts import verify_centers
from subject_guide_schema import (
    ROOT, allowed_schema_fingerprint, card_school_names, clean_schema,
    confirmed_high_schools, load_targets, outside_schema, paired_routes,
    read_graph, schema_errors,
)

REPORT_ROOT = Path(r'C:\Users\1992k\Desktop\CodexData\audit-output\wawa-center-step7-20260920')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_school_sources(records: list[dict], centers: dict) -> dict:
    """Reconcile reviewed school lists to the two source workbooks read-only."""
    school_workbook = load_workbook(TARGET_WORKBOOK, read_only=True, data_only=True)
    center_workbook = load_workbook(SOURCE_WORKBOOK, read_only=True, data_only=True)
    try:
        grouped = {}
        school_rows = {}
        for number, row in enumerate(school_workbook.active.iter_rows(min_row=2, values_only=True), 2):
            if not row[0] or not row[3]:
                continue
            key = branch_key(row[3])
            group = grouped.setdefault(key, {'초등': [], '중등': [], '고등': []})
            school_rows.setdefault(key, []).append(number)
            for level, value in zip(('초등', '중등', '고등'), row[4:7]):
                for school in split_values(value):
                    if school not in group[level]:
                        group[level].append(school)
        source_rows = {i: row for i, row in enumerate(center_workbook['센터정보'].iter_rows(min_row=2, values_only=True), 2)}
        evidence = []
        for name in sorted({r['center'] for r in records}):
            center = centers[name]
            if not center['sourceRow']:
                raise ValueError(f'원본 학교 자료 별도 검토 필요: {name}')
            row = source_rows[center['sourceRow']]
            key = branch_key(center['sourceName'])
            mapped = grouped.get(key, {})
            for level, column in (('초등', 13), ('중등', 14), ('고등', 15)):
                schools, seen = [], set()
                for school in mapped.get(level, []) + split_values(row[column]):
                    school = clean(school)
                    normalized = school_key(school)
                    if school and normalized not in seen:
                        schools.append(school)
                        seen.add(normalized)
                if schools != center['schools'][level]:
                    raise ValueError(f'학교 자료와 검토본 불일치: {name}/{level}')
            evidence.append({'center': name, 'centerSheet': '센터정보', 'centerSchoolCells': f'N{center["sourceRow"]}:P{center["sourceRow"]}', 'schoolSheet': school_workbook.active.title, 'schoolRowNumbers': school_rows.get(key, []), 'schoolColumns': 'E:G'})
        return {'centerCount': len(evidence), 'workbooks': [{'name': p.name, 'sha256': sha(p)} for p in (SOURCE_WORKBOOK, TARGET_WORKBOOK)], 'evidence': evidence}
    finally:
        school_workbook.close()
        center_workbook.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='apply staged files locally; does not deploy')
    args = parser.parse_args()
    records, centers = load_targets()
    sources = verify_centers(records, centers)
    school_sources = verify_school_sources(records, centers)
    target_files = {(ROOT / r['path'].strip('/') / 'index.html').resolve() for r in records}
    protected = [p for p in ROOT.rglob('*.html') if p.resolve() not in target_files]
    protected += [p for folder in ('assets', 'tools/data') for p in (ROOT / folder).rglob('*') if p.is_file()]
    protected += [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.xml', '.json', '.toml')]
    protected += [ROOT / 'robots.txt', SOURCE_WORKBOOK, TARGET_WORKBOOK]
    manuscript_root = Path(r'C:\Users\1992k\Desktop\프로그램 원고')
    protected += [manuscript_root / f'{level} {subject}학원.zip' for level in ('초등', '중등', '고등') for subject in ('수학', '영어')]
    protected = sorted(set(protected))
    print(f'636개 안내 / {len(sources)}개 센터 원본 대조 완료. 보호 파일 {len(protected)}개 확인 중', flush=True)
    before_hashes = {str(p): sha(p) for p in protected}
    stage, backup = REPORT_ROOT / 'staged-site', REPORT_ROOT / 'before-step7'
    changes, counts = [], Counter()
    for record in records:
        relative = Path(record['path'].strip('/')) / 'index.html'
        destination = (ROOT / relative).resolve()
        if not destination.is_relative_to((ROOT / '과목별학원').resolve()) or destination not in target_files:
            raise ValueError(f'대상 밖 경로: {relative}')
        old_bytes = destination.read_bytes()
        old = old_bytes.decode('utf-8')
        center = centers[record['center']]
        new = clean_schema(old, record, center)
        if outside_schema(old) != outside_schema(new):
            raise ValueError(f'화면 HTML 변경: {relative}')
        if allowed_schema_fingerprint(old, record, center) != allowed_schema_fingerprint(new, record, center):
            raise ValueError(f'허용 범위 밖 JSON-LD 변경: {relative}')
        errors = schema_errors(new, record, center)
        errors += route_errors(new, center, record, 'guide', paired_routes(center, record), ROOT, stage)
        if errors:
            raise ValueError(f'{relative}: {errors}')
        output = stage / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(new.encode('utf-8'))
        original = backup / relative
        baseline = original.read_bytes().decode('utf-8') if original.exists() else old
        old_graph, new_graph = read_graph(baseline), read_graph(new)
        counts['changedThisRun'] += old != new
        counts['pagesChanged'] += baseline != new
        counts['hoursNodesRemoved'] += sum('openingHoursSpecification' in n for n in old_graph) - sum('openingHoursSpecification' in n for n in new_graph)
        counts['wholeCenterGradeNodesRemoved'] += sum('educationalLevel' in n for n in old_graph) - sum('educationalLevel' in n for n in new_graph)
        counts['offerFieldsRemoved'] += sum('makesOffer' in n or 'offers' in n for n in old_graph) - sum('makesOffer' in n or 'offers' in n for n in new_graph)
        counts['unsupportedServiceNodesRemoved'] += sum(n.get('@type') == 'Service' for n in old_graph) - sum(n.get('@type') == 'Service' for n in new_graph)
        counts['retainedServices'] += sum(n.get('@type') == 'Service' for n in new_graph)
        counts['schemaBytesSaved'] += len(baseline.encode('utf-8')) - len(new.encode('utf-8'))
        counts['schoolMentionEntriesRemoved'] += sum(len(n.get('mentions', [])) for n in old_graph if n.get('@type') in ('WebPage', 'Article')) - sum(len(n.get('mentions', [])) for n in new_graph if n.get('@type') in ('WebPage', 'Article'))
        doc = html.fromstring(new)
        displayed = card_school_names(doc)
        high_school_names = confirmed_high_schools(doc, center)
        changes.append({**record, 'publishedGrades': course_guidance(center, record['subject'], '고')['grades'], 'visibleSchoolReferences': displayed, 'schemaConfirmedHighSchools': [s for s in displayed if s in high_school_names], 'beforeSha256': hashlib.sha256(old_bytes).hexdigest(), 'afterSha256': sha(output)})
    print('636개 구조화 데이터 / 화면 HTML 보존 / 기존 연결 / 재적용 검증 완료', flush=True)
    if any(sha(Path(p)) != digest for p, digest in before_hashes.items()):
        raise ValueError('작업 중 원본 또는 보호 파일 변경')
    for change in changes:
        if sha(ROOT / change['path'].strip('/') / 'index.html') != change['beforeSha256']:
            raise ValueError('작업 중 대상 페이지 변경')
    if args.write:
        for change in changes:
            relative = Path(change['path'].strip('/')) / 'index.html'
            destination, original = ROOT / relative, backup / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            if not original.exists():
                original.write_bytes(destination.read_bytes())
            if sha(destination) != change['afterSha256']:
                destination.write_bytes((stage / relative).read_bytes())
        if any(sha(Path(p)) != digest for p, digest in before_hashes.items()):
            raise ValueError('적용 후 보호 파일 불일치')
        if any(sha(ROOT / c['path'].strip('/') / 'index.html') != c['afterSha256'] for c in changes):
            raise ValueError('적용 후 대상 페이지 불일치')
    report = {'pages': len(records), 'centers': len(sources), 'counts': dict(counts), 'schemaErrors': 0, 'visibleHtmlChanges': 0, 'outsideSchemaScopeChanges': 0, 'protectedFileCount': len(protected), 'nonTargetHtmlCount': sum(p.suffix == '.html' for p in protected), 'protectedHashes': before_hashes, 'centerEvidence': sources, 'schoolSourceEvidence': school_sources, 'appliedLocally': args.write, 'deployed': False}
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (REPORT_ROOT / 'changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('protectedHashes', 'centerEvidence', 'schoolSourceEvidence')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
