"""Align the explicitly reviewed 106 legacy learning guides with branch facts.

Source manuscripts, destinations and images are not regenerated. Only exact
old center names/addresses, the fact card, one factual FAQ and corresponding
schema are changed. Missing/conflicting courses never become availability.
"""

from __future__ import annotations

import copy
import json
from html import escape
from urllib.parse import unquote, urlsplit

from lxml import html

from branch_course_guidance import REGISTRATION_NOTE, center_notes, course_answer, course_guidance
from branch_learning_routes import ROOT, canonical, paired_routes

TARGETS_FILE = ROOT / 'tools/data/subject-guide-facts/targets.json'
STYLE = '/assets/subject-guide-facts.css?v=20260920'
REVIEW_DATE = '2026-09-20'
URL_ATTRIBUTES = {'href', 'src', 'srcset', 'action', 'formaction', 'poster', 'cite', 'background', 'longdesc', 'usemap'}


def targets() -> list[dict]:
    data = json.loads(TARGETS_FILE.read_text(encoding='utf-8'))
    rows = data['targets']
    if len(rows) != data['targetCount'] or len({r['path'] for r in rows}) != len(rows):
        raise ValueError('중복 또는 누락된 사실 정리 대상')
    return rows


def corrected_text(value: str, record: dict, center: dict) -> str:
    pairs = [(record['previousAddress'], center['address']), (record['previousName'], center['displayName'])]
    for old, new in pairs:
        if old != new:
            # Longest exact published address/name first; never replace grades
            # or ordinary locality words in the learning manuscript.
            value = value.replace(old, new)
    return value


def corrected_json(value, record: dict, center: dict):
    if isinstance(value, dict):
        return {key: corrected_json(item, record, center) for key, item in value.items()}
    if isinstance(value, list):
        return [corrected_json(item, record, center) for item in value]
    if isinstance(value, str):
        return corrected_text(value, record, center)
    return value


def exact_fact_substitutions(doc, record: dict, center: dict) -> None:
    for element in doc.iter():
        if not isinstance(element.tag, str) or element.tag in ('script', 'style'):
            continue
        for field in ('text', 'tail'):
            if getattr(element, field):
                setattr(element, field, corrected_text(getattr(element, field), record, center))
        if element.tag == 'meta' and (element.get('name') in ('description', 'twitter:description') or element.get('property') == 'og:description'):
            element.set('content', corrected_text(element.get('content', ''), record, center))


def source_schools(center: dict) -> list[str]:
    # A short reference list, not an assertion of an exclusive school contract.
    return center.get('schools', {}).get('고등', [])[:10]


def factual_question(center: dict, record: dict) -> str:
    return f'{center["routeName"]}의 고등 {record["subject"]} 안내 학년과 수업 조건은 무엇인가요?'


def condition_texts(center: dict, record: dict) -> list[str]:
    view = course_guidance(center, record['subject'], '고')
    return list(dict.fromkeys([*view['notes'], *center_notes(center, '고'), REGISTRATION_NOTE]))


def set_row(dl, label: str, contents: str, key: str, aliases: tuple[str, ...] = (), after: str | None = None) -> None:
    matched = [row for row in dl if row.find('dt') is not None and row.find('dt').text_content() in (label, *aliases)]
    if len(matched) > 1:
        raise ValueError(f'중복 정보 행: {label}')
    row = html.fragment_fromstring(f'<div data-guide-fact="{key}"><dt>{escape(label)}</dt><dd>{contents}</dd></div>')
    if matched:
        row.tail = matched[0].tail
        dl.replace(matched[0], row)
    else:
        anchors = [node for node in dl if node.get('data-guide-fact') == after] if after else []
        dl.insert(list(dl).index(anchors[0]) + 1 if anchors else len(dl), row)


def update_card(doc, record: dict, center: dict) -> None:
    cards = doc.xpath('//aside[@class="math-info-card"]')
    if len(cards) != 1:
        raise ValueError('센터 정보 카드 위치 오류')
    card = cards[0]
    card.set('id', 'reviewed-center-info')
    card.set('data-facts-reviewed', REVIEW_DATE)
    dl = card.find('dl')
    view = course_guidance(center, record['subject'], '고')
    set_row(dl, '센터 기준', escape(center['displayName']), 'name')
    set_row(dl, '등록 명칭', escape(center['registeredName']), 'legal-name', after='name')
    set_row(dl, '제공 주소', escape(center['address']), 'address')
    grades = '<div class="math-tag-list">' + ''.join(f'<span>{escape(g)}</span>' for g in view['grades']) + '</div>' if view['grades'] else '<span class="guide-grade-inquiry">개설 학년 문의</span>'
    set_row(dl, f'고등 {record["subject"]} 안내 학년', grades, 'grades', aliases=(f'고등 {record["subject"]} 수업 가능 학년',))
    conditions = ''.join(f'<p>{escape(note)}</p>' for note in condition_texts(center, record))
    set_row(dl, '확인할 수업 조건', conditions, 'conditions', after='grades')
    set_row(dl, '교육지원청 등록번호', escape(center['registrationNumber']), 'registration')
    set_row(dl, '정보 확인 기준일', escape(center['informationReviewedAt']) + ' · 제공된 센터 자료 기준', 'review-date', after='registration')
    schools = source_schools(center)
    school_text = '<div class="math-tag-list">' + ''.join(f'<span>{escape(s)}</span>' for s in schools) + '</div>' if schools else '상담에서 학교와 학년을 확인해 주세요.'
    school_text += '<p class="guide-school-note">학교별 평가 범위와 학생의 재학 정보를 함께 확인해 주세요.</p>'
    set_row(dl, '고등학교 참고', school_text, 'schools', aliases=('제공 학교 참고',), after='review-date')


def update_faq_and_notice(doc, record: dict, center: dict) -> None:
    faq_lists = doc.xpath('//div[@class="math-faq-list"]')
    if len(faq_lists) != 1:
        raise ValueError('FAQ 목록 위치 오류')
    for existing in doc.xpath('//*[@id="verified-course-faq"]'):
        existing.getparent().remove(existing)
    answer = course_answer(center, record['subject'], '고')
    detail = html.fragment_fromstring(f'<details class="math-faq-item" id="verified-course-faq" data-guide-fact="availability"><summary>{escape(factual_question(center, record))}</summary><p>{escape(answer)}</p></details>')
    faq_lists[0].insert(0, detail)
    for existing in doc.xpath('//*[@id="guide-course-note"]'):
        existing.getparent().remove(existing)
    view = course_guidance(center, record['subject'], '고')
    if not view['grades'] or view['pendingGrades']:
        bridges = doc.xpath('//*[@id="learning-route-top"]/div[@class="learning-route-inner"]')
        if len(bridges) != 1:
            raise ValueError('먼저 5단계의 학습 안내 연결을 적용해 주세요.')
        notice = html.fragment_fromstring(f'<p class="guide-course-notice" id="guide-course-note"><strong>수업 조건 먼저 확인</strong>{escape(answer)}</p>')
        links = bridges[0].find('div')
        bridges[0].insert(list(bridges[0]).index(links), notice)


def update_graph(doc, payload: dict, record: dict, center: dict) -> dict:
    payload = corrected_json(copy.deepcopy(payload), record, center)
    graph = payload['@graph']
    view = course_guidance(center, record['subject'], '고')
    routes = paired_routes(center, record)
    parent_url = canonical(routes['parent'])
    article = next(n for n in graph if n.get('@type') == 'Article')
    old_school_names = set(record['previousSchools']) | set(source_schools(center))
    for node in graph:
        node_type = node.get('@type')
        if node_type in ('EducationalOrganization', 'LocalBusiness'):
            node['name'] = center['displayName']
            node['legalName'] = center['registeredName']
            node['url'] = parent_url
            node['address'] = {'@type': 'PostalAddress', 'streetAddress': center['address'], 'addressRegion': center['region'], 'addressLocality': center['district'], 'addressCountry': 'KR'}
            node['identifier'] = {'@type': 'PropertyValue', 'name': '교육지원청 등록번호', 'value': center['registrationNumber']}
            for key in ('openingHoursSpecification', 'openingHours', 'makesOffer', 'offers', 'educationalLevel', 'teaches'):
                node.pop(key, None)
        if node_type == 'WebPage':
            node['mainEntity'] = {'@id': article['@id']}
        if node_type in ('Article', 'WebPage'):
            node['dateModified'] = REVIEW_DATE
        if node_type == 'Service' and view['grades']:
            node['description'] = course_answer(center, record['subject'], '고')
            node['audience'] = {'@type': 'EducationalAudience', 'educationalRole': 'student', 'audienceType': view['label']}
            for key in ('makesOffer', 'offers'):
                node.pop(key, None)
        if node_type in ('Article', 'WebPage', 'Service'):
            mentions = [n for n in node.get('mentions', []) if not isinstance(n, dict) or n.get('name') not in old_school_names]
            node['mentions'] = mentions + [{'@type': 'Thing', 'name': school} for school in source_schools(center)]
        if node_type == 'FAQPage':
            node['mainEntity'] = [
                {'@type': 'Question', 'name': ' '.join(detail.find('summary').text_content().split()),
                 'acceptedAnswer': {'@type': 'Answer', 'text': ' '.join(detail.find('p').text_content().split())}}
                for detail in doc.xpath('//div[@class="math-faq-list"]/details')
            ]
    if not view['grades']:
        payload['@graph'] = [n for n in graph if n.get('@type') != 'Service']
    return payload


def serialize_page(doc) -> str:
    # libxml's HTML serializer can percent-encode Korean URLs depending on
    # document encoding metadata. Keep every existing URI attribute verbatim
    # (as a DOM value), rather than silently changing navigation or image URLs.
    substitutions = []
    for element in doc.iter():
        if not isinstance(element.tag, str):
            continue
        for key, value in list(element.attrib.items()):
            if key in URL_ATTRIBUTES:
                marker = f'__WAWA_GUIDE_URI_{len(substitutions):05d}__'
                substitutions.append((element, key, value, marker))
                element.set(key, marker)
    serialized = html.tostring(doc, encoding='unicode', method='html', doctype='<!doctype html>')
    for element, key, value, marker in substitutions:
        if serialized.count(marker) != 1 or '__WAWA_GUIDE_URI_' in value:
            raise ValueError('URI serialization marker collision')
        serialized = serialized.replace(marker, escape(value, quote=True))
        element.set(key, value)
    return serialized.rstrip() + '\n'


def align_guide(raw: str, record: dict, center: dict) -> str:
    routes = paired_routes(center, record)
    if not routes or routes['guide'] != record['path'] or center['routeName'] != record['center']:
        raise ValueError('검토 대상과 센터·동네·과목 경로 불일치')
    doc = html.document_fromstring(raw)
    urls = doc.xpath('//link[@rel="canonical"]/@href')
    if len(urls) != 1 or urlsplit(urls[0]).netloc != 'wawa-center.kr' or unquote(urlsplit(urls[0]).path) != record['path']:
        raise ValueError('페이지 canonical 불일치')
    scripts = doc.xpath('//script[@type="application/ld+json"]')
    if len(scripts) != 1:
        raise ValueError('JSON-LD 스크립트 개수 오류')
    payload = json.loads(scripts[0].text)
    exact_fact_substitutions(doc, record, center)
    update_card(doc, record, center)
    update_faq_and_notice(doc, record, center)
    if not doc.xpath(f'//link[@href="{STYLE}"]'):
        style = html.Element('link', rel='stylesheet', href=STYLE)
        doc.find('head').append(style)
    payload = update_graph(doc, payload, record, center)
    scripts[0].text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return serialize_page(doc)
