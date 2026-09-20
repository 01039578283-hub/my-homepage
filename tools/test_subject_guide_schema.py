"""Schema-only cleanup and preservation tests for the remaining 636 guides."""

import copy
import json
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from lxml import html

from branch_course_guidance import course_guidance
from refresh_subject_guide_facts import verify_centers
from refresh_subject_guide_schema import REPORT_ROOT, verify_school_sources
from subject_guide_facts import targets as fact_targets
from subject_guide_schema import (
    ROOT, ORG_REMOVALS, allowed_schema_fingerprint, card_school_names,
    clean_schema, confirmed_high_schools, filter_school_mentions, load_targets,
    outside_schema, read_graph, schema_errors, schema_match, school_aliases,
)


class SubjectGuideSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.centers = load_targets()
        cls.cases = []
        for record in cls.records:
            relative = Path(record['path'].strip('/')) / 'index.html'
            baseline = REPORT_ROOT / 'before-step7' / relative
            raw = (baseline if baseline.exists() else ROOT / relative).read_bytes().decode('utf-8')
            center = cls.centers[record['center']]
            cls.cases.append((record, center, raw, clean_schema(raw, record, center)))

    def test_only_636_targets_outside_prior_106(self):
        paths = {r['path'] for r in self.records}
        reviewed = {r['path'] for r in fact_targets()}
        self.assertEqual(len(paths), 636)
        self.assertEqual(len({r['center'] for r in self.records}), 170)
        self.assertFalse(paths & reviewed)
        self.assertEqual(len(paths | reviewed), 742)

    def test_170_center_and_school_sources_reconcile(self):
        evidence = verify_centers(self.records, self.centers)
        self.assertEqual(len(evidence), 170)
        self.assertTrue(all('sheet' in row for row in evidence))
        self.assertEqual(verify_school_sources(self.records, self.centers)['centerCount'], 170)

    def test_all_schema_errors_zero_and_idempotent(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                self.assertEqual(schema_errors(updated, record, center), [])
                self.assertEqual(clean_schema(updated, record, center), updated)

    def test_all_visible_html_and_unrelated_schema_unchanged(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                self.assertEqual(outside_schema(raw), outside_schema(updated))
                self.assertEqual(allowed_schema_fingerprint(raw, record, center), allowed_schema_fingerprint(updated, record, center))

    def test_all_operating_hours_and_whole_center_grades_removed(self):
        counts = Counter()
        for record, center, raw, updated in self.cases:
            for node in read_graph(raw):
                counts['hours'] += 'openingHoursSpecification' in node
                counts['levels'] += 'educationalLevel' in node
            for node in read_graph(updated):
                if node['@type'] in ('EducationalOrganization', 'LocalBusiness'):
                    self.assertFalse(set(ORG_REMOVALS) & set(node))
        self.assertEqual(counts, {'hours': 1272, 'levels': 636})

    def test_missing_courses_remove_only_15_services_without_broken_refs(self):
        counts = Counter()
        for record, center, raw, updated in self.cases:
            nodes = read_graph(updated)
            service = [n for n in nodes if n['@type'] == 'Service']
            view = course_guidance(center, record['subject'], '고')
            self.assertEqual(bool(service), bool(view['grades']))
            if not view['grades']:
                counts['removed'] += 1
                self.assertNotIn('#service', json.dumps(nodes, ensure_ascii=False))
                self.assertEqual(outside_schema(raw), outside_schema(updated))
            else:
                counts['retained'] += 1
                self.assertEqual(service[0]['audience']['audienceType'], view['label'])
                self.assertNotIn('makesOffer', service[0])
                self.assertNotIn('offers', service[0])
                self.assertIn('/%EC%A7%80%EC%A0%90%EC%95%88%EB%82%B4/', service[0]['subjectOf']['url'])
        self.assertEqual(counts, {'removed': 15, 'retained': 621})

    def test_article_is_main_entity_without_changing_identity_or_dates(self):
        for record, center, raw, updated in self.cases:
            before, after = read_graph(raw), read_graph(updated)
            article = next(n for n in after if n['@type'] == 'Article')
            webpage = next(n for n in after if n['@type'] == 'WebPage')
            self.assertEqual(webpage['mainEntity'], {'@id': article['@id']})
            for kind in ('Article', 'WebPage'):
                a = next(n for n in before if n['@type'] == kind)
                b = next(n for n in after if n['@type'] == kind)
                for field in ('@id', 'datePublished', 'dateModified', 'description', 'image', 'headline', 'author', 'publisher'):
                    self.assertEqual(a.get(field), b.get(field))

    def test_school_aliases_are_narrow_and_do_not_change_identity(self):
        self.assertEqual(school_aliases('명일여자고등학교'), {'명일여자고등학교', '명일여자고', '명일여고'})
        self.assertIn('청주외고', school_aliases('청주외국어고등학교'))
        self.assertNotIn('서울고', school_aliases('부산고등학교'))
        self.assertNotIn('사대부고', school_aliases('충북대학교사범대학부설고등학교'))
        self.assertEqual(school_aliases('서현고'), {'서현고'})

    def test_only_visible_verified_high_schools_retained_in_mentions(self):
        for record, center, raw, updated in self.cases:
            doc = html.fromstring(raw)
            schools = set(card_school_names(doc))
            confirmed = confirmed_high_schools(doc, center)
            self.assertTrue(confirmed <= schools)
            for node in read_graph(updated):
                if node['@type'] in ('WebPage', 'Article', 'Service'):
                    names = {n.get('name') for n in node.get('mentions', []) if isinstance(n, dict)}
                    self.assertFalse((schools - confirmed) & names)
            # A wider list may remain visibly on the center-reference card;
            # this task must not silently change that manuscript/UI.
            self.assertEqual(card_school_names(html.fromstring(updated)), card_school_names(doc))

    def test_non_school_topics_are_not_stripped(self):
        record, center, raw, updated = self.cases[0]
        doc = html.fromstring(raw)
        concepts = [{'@type': 'Thing', 'name': '수학 오답관리'}, {'@type': 'Place', 'name': record['locality']}]
        self.assertEqual(filter_school_mentions(concepts, doc, center), concepts)

    def test_faq_breadcrumb_links_and_fee_buttons_unchanged(self):
        for record, center, raw, updated in self.cases:
            before, after = read_graph(raw), read_graph(updated)
            for kind in ('FAQPage', 'BreadcrumbList', 'ItemList'):
                self.assertEqual([n for n in before if n['@type'] == kind], [n for n in after if n['@type'] == kind])
            a, b = html.fromstring(raw), html.fromstring(updated)
            self.assertEqual(a.xpath('//a/@href'), b.xpath('//a/@href'))
            self.assertEqual([dict(n.attrib) for n in a.xpath('//img | //source')], [dict(n.attrib) for n in b.xpath('//img | //source')])

    def test_wrong_canonical_and_center_refuse_write(self):
        record, center, raw, updated = self.cases[0]
        with self.assertRaises(ValueError):
            clean_schema(raw.replace('rel="canonical"', 'rel="other"'), record, center)
        with self.assertRaises(ValueError):
            clean_schema(raw, record, self.centers['원주시청점'])

    def test_missing_visible_branch_link_and_wrong_visible_grades_refuse_write(self):
        record, center, raw, updated = self.cases[0]
        with self.assertRaises(ValueError):
            clean_schema(raw.replace('id="learning-route-top"', 'id="different"'), record, center)
        changed = raw.replace('<span>고3</span>', '<span>고9</span>')
        self.assertNotEqual(changed, raw)
        with self.assertRaises(ValueError):
            clean_schema(changed, record, center)

    def test_prior_106_pages_cannot_be_accidentally_refreshed(self):
        record = fact_targets()[0]
        raw = (ROOT / record['path'].strip('/') / 'index.html').read_bytes().decode('utf-8')
        with self.assertRaises(ValueError):
            clean_schema(raw, record, self.centers[record['center']])

    def test_hidden_pending_condition_cannot_be_invented(self):
        record, center, raw, updated = self.cases[0]
        view = copy.deepcopy(course_guidance(center, record['subject'], '고'))
        view['pendingGrades'] = ['고3']
        with patch('subject_guide_schema.course_guidance', return_value=view), self.assertRaises(ValueError):
            clean_schema(raw, record, center)

    def test_scope_guard_rejects_unrelated_schema_changes(self):
        record, center, raw, updated = self.cases[0]
        before = allowed_schema_fingerprint(updated, record, center)
        for kind, field in [('Article', 'description'), ('Article', 'datePublished'), ('WebPage', 'relatedLink'), ('EducationalOrganization', 'address'), ('Service', 'provider'), ('Service', 'description'), ('FAQPage', 'mainEntity')]:
            with self.subTest(kind=kind, field=field):
                match = schema_match(updated)
                payload = json.loads(match.group(2))
                next(n for n in payload['@graph'] if n['@type'] == kind)[field] = 'unauthorized-change'
                changed = updated[:match.start(2)] + json.dumps(payload, ensure_ascii=False) + updated[match.end(2):]
                self.assertNotEqual(before, allowed_schema_fingerprint(changed, record, center))

    def test_inputs_and_original_line_endings_are_preserved(self):
        record, center, raw, updated = self.cases[0]
        old_record, old_center = copy.deepcopy(record), copy.deepcopy(center)
        mixed = raw.replace('\r\n', '\n').replace('\n', '\r\n')
        changed = clean_schema(mixed, record, center)
        self.assertEqual(outside_schema(mixed), outside_schema(changed))
        self.assertEqual(old_record, record)
        self.assertEqual(old_center, center)


if __name__ == '__main__':
    unittest.main()
