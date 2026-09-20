"""Step 7: schema-only cleanup of the other 636 high-school learning guides.

This deliberately does not serialize the HTML document: everything outside the
single JSON-LD payload remains byte-for-byte unchanged, including Korean URLs.
No grades, operating hours, offers or school identities are guessed.
"""

from __future__ import annotations

import copy
import json
from urllib.parse import unquote, urlsplit

from lxml import html

from branch_course_guidance import course_guidance
from branch_learning_routes import ROOT, SCRIPT, canonical, paired_routes
from refresh_branch_learning_routes import legacy_fact_differences
from subject_guide_facts import targets as fact_targets

ORG_REMOVALS = ('openingHoursSpecification', 'openingHours', 'educationalLevel', 'teaches', 'makesOffer', 'offers')
SERVICE_REMOVALS = ('makesOffer', 'offers')


def load_targets() -> tuple[list[dict], dict[str, dict]]:
    centers_list = json.loads((ROOT / 'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    centers = {c['routeName']: c for c in centers_list}
    if len(centers) != len(centers_list):
        raise ValueError('센터명 중복')
    reviewed = {r['path'] for r in fact_targets()}
    records = json.loads((ROOT / 'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']
    pairs = []
    result = []
    for record in records:
        routes = paired_routes(centers[record['center']], record)
        if not routes:
            continue
        pairs.append(routes['guide'])
        if routes['guide'] not in reviewed:
            result.append({key: record[key] for key in ('center', 'locality', 'level', 'subject')} | {'path': routes['guide']})
    if len(pairs) != 742 or len(set(pairs)) != 742 or len(reviewed) != 106 or not reviewed <= set(pairs) or len(result) != 636:
        raise ValueError('검토 대상 범위가 변경되었습니다. 742개 중 기존 106개를 제외한 636개만 처리합니다.')
    return result, centers


def schema_match(raw: str):
    matches = list(SCRIPT.finditer(raw))
    if len(matches) != 1:
        raise ValueError('JSON-LD 스크립트 개수 오류')
    return matches[0]


def outside_schema(raw: str) -> tuple[str, str]:
    match = schema_match(raw)
    return raw[:match.start(2)], raw[match.end(2):]


def read_graph(raw: str) -> list[dict]:
    return json.loads(schema_match(raw).group(2))['@graph']


def card_school_names(doc) -> list[str]:
    return list(dict.fromkeys(doc.xpath('//aside[@class="math-info-card"]/dl/div[dt="제공 학교 참고"]/dd//span/text()')))


def school_aliases(name: str) -> set[str]:
    # Only suffix equivalents of an explicitly sourced high-school name.
    # Do not drop regional prefixes, fuzzy-match or expand ambiguous names.
    result = {name}
    for full, short in (('고등학교', '고'), ('여자고등학교', '여고'), ('외국어고등학교', '외고'), ('과학고등학교', '과고')):
        if name.endswith(full):
            result.add(name[:-len(full)] + short)
    return result


def confirmed_high_schools(doc, center: dict) -> set[str]:
    aliases = set().union(*(school_aliases(name) for name in center.get('schools', {}).get('고등', [])))
    return set(card_school_names(doc)) & aliases


def filter_school_mentions(mentions: list, doc, center: dict) -> list:
    schools = set(card_school_names(doc))
    confirmed = confirmed_high_schools(doc, center)
    return [node for node in mentions if not isinstance(node, dict) or node.get('name') not in schools or node.get('name') in confirmed]


def checked_context(raw: str, record: dict, center: dict):
    routes = paired_routes(center, record)
    if not routes or record['path'] != routes['guide'] or record['center'] != center['routeName']:
        raise ValueError('센터·동네·과목 경로 불일치')
    doc = html.fromstring(raw)
    urls = doc.xpath('//link[@rel="canonical"]/@href')
    if len(urls) != 1 or urlsplit(urls[0]).netloc != 'wawa-center.kr' or unquote(urlsplit(urls[0]).path) != routes['guide']:
        raise ValueError('canonical 불일치')
    if doc.xpath('//*[@id="reviewed-center-info"]'):
        raise ValueError('이미 6단계에서 수정한 페이지는 7단계 대상이 아닙니다.')
    if legacy_fact_differences(raw, center, record):
        raise ValueError('화면의 센터명·주소·학년과 원본 자료가 다릅니다. 숨겨진 데이터만 바꾸지 않습니다.')
    links = doc.xpath('//*[@id="learning-route-top"]//a/@href')
    if routes['child'] + '#overview' not in links or routes['parent'] + '#center-info' not in links:
        raise ValueError('실제 조건을 확인할 지점 안내 링크 누락')
    payload = json.loads(schema_match(raw).group(2))
    graph = payload['@graph']
    for kind in ('WebPage', 'Article', 'EducationalOrganization', 'LocalBusiness', 'FAQPage', 'BreadcrumbList', 'ItemList'):
        if sum(n.get('@type') == kind for n in graph) != 1:
            raise ValueError(f'스키마 노드 개수 오류: {kind}')
    if sum(n.get('@type') == 'Service' for n in graph) > 1:
        raise ValueError('중복 Service')
    return doc, routes, payload


def clean_schema(raw: str, record: dict, center: dict) -> str:
    doc, routes, payload = checked_context(raw, record, center)
    payload = copy.deepcopy(payload)
    graph = payload['@graph']
    view = course_guidance(center, record['subject'], '고')
    if view['pendingGrades']:
        raise ValueError('별도 학년 보류가 있는 페이지는 먼저 화면 안내를 확인해야 합니다.')
    if view['grades'] and sum(n.get('@type') == 'Service' for n in graph) != 1:
        raise ValueError('기존 Service 누락: 새로 만들어 수업 가능성을 추정하지 않습니다.')
    article = next(n for n in graph if n.get('@type') == 'Article')
    child_reference = {'@type': 'WebPage', 'url': canonical(routes['child'])}
    for node in graph:
        kind = node.get('@type')
        if kind in ('EducationalOrganization', 'LocalBusiness'):
            for field in ORG_REMOVALS:
                node.pop(field, None)
            node['url'] = canonical(routes['parent'])
        if kind == 'WebPage':
            node['mainEntity'] = {'@id': article['@id']}
        if kind == 'Service':
            for field in SERVICE_REMOVALS:
                node.pop(field, None)
            if view['grades']:
                node['audience']['audienceType'] = view['label']
                if node.get('subjectOf', child_reference) != child_reference:
                    raise ValueError('기존 Service.subjectOf를 덮어쓰지 않습니다.')
                # The actual branch-course conditions are already linked in
                # the visible page. Do not copy hidden conditions into schema.
                node['subjectOf'] = child_reference
        if kind in ('WebPage', 'Article', 'Service') and 'mentions' in node:
            node['mentions'] = filter_school_mentions(node['mentions'], doc, center)
    if not view['grades']:
        payload['@graph'] = [n for n in graph if n.get('@type') != 'Service']
    match = schema_match(raw)
    replacement = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    return raw[:match.start(2)] + replacement + raw[match.end(2):]


def allowed_schema_fingerprint(raw: str, record: dict, center: dict) -> dict:
    """Normalize only the exact property allowlist; everything else is guarded."""
    doc = html.fromstring(raw)
    payload = copy.deepcopy(json.loads(schema_match(raw).group(2)))
    if not course_guidance(center, record['subject'], '고')['grades']:
        payload['@graph'] = [n for n in payload['@graph'] if n.get('@type') != 'Service']
    for node in payload['@graph']:
        kind = node.get('@type')
        if kind in ('EducationalOrganization', 'LocalBusiness'):
            for field in (*ORG_REMOVALS, 'url'):
                node.pop(field, None)
        if kind == 'WebPage':
            node.pop('mainEntity', None)
        if kind == 'Service':
            for field in (*SERVICE_REMOVALS, 'subjectOf'):
                node.pop(field, None)
            node['audience'].pop('audienceType', None)
        if kind in ('WebPage', 'Article', 'Service') and 'mentions' in node:
            node['mentions'] = filter_school_mentions(node['mentions'], doc, center)
    return payload


def schema_errors(raw: str, record: dict, center: dict) -> list[str]:
    doc, routes, payload = checked_context(raw, record, center)
    graph = payload['@graph']
    view = course_guidance(center, record['subject'], '고')
    errors = []
    orgs = [n for n in graph if n.get('@type') in ('EducationalOrganization', 'LocalBusiness')]
    for node in orgs:
        if any(key in node for key in ORG_REMOVALS):
            errors.append('unsupported organization fields')
        if node['url'] != canonical(routes['parent']):
            errors.append('organization parent URL')
    services = [n for n in graph if n.get('@type') == 'Service']
    if len(services) != int(bool(view['grades'])):
        errors.append('unsupported service')
    for node in services:
        if any(key in node for key in SERVICE_REMOVALS):
            errors.append('unsupported offer')
        if node['audience']['audienceType'] != view['label']:
            errors.append('service grade range')
        if node.get('subjectOf') != {'@type': 'WebPage', 'url': canonical(routes['child'])}:
            errors.append('service condition page')
        if node['provider']['@id'] not in {n['@id'] for n in orgs}:
            errors.append('dangling provider')
    if not view['grades'] and '#service' in json.dumps(graph, ensure_ascii=False):
        errors.append('dangling unavailable service')
    page = next(n for n in graph if n.get('@type') == 'WebPage')
    article = next(n for n in graph if n.get('@type') == 'Article')
    if page['mainEntity'] != {'@id': article['@id']}:
        errors.append('wrong learning guide main entity')
    for node in graph:
        if node.get('@type') in ('WebPage', 'Article', 'Service') and node.get('mentions', []) != filter_school_mentions(node.get('mentions', []), doc, center):
            errors.append('irrelevant or unverified school mentions')
    visible_faq = [(' '.join(d.find('summary').text_content().split()), ' '.join(d.find('p').text_content().split())) for d in doc.xpath('//div[@class="math-faq-list"]/details')]
    schema_faq = [(q['name'], q['acceptedAnswer']['text']) for q in next(n for n in graph if n.get('@type') == 'FAQPage')['mainEntity']]
    if visible_faq != schema_faq:
        errors.append('FAQ differs from visible answers')
    if clean_schema(raw, record, center) != raw:
        errors.append('not idempotent')
    return errors
