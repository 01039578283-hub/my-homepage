"""Step 6: original-source facts, course conditions and strict scope guards."""

import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from lxml import html

from branch_course_guidance import course_answer, course_guidance
from branch_learning_routes import ROOT, paired_routes
from refresh_branch_learning_routes import legacy_fact_differences, route_errors
from refresh_subject_guide_facts import (
    REPORT_ROOT, factual_errors, graph, scope_fingerprint, verify_centers,
)
from subject_guide_facts import align_guide, corrected_text, serialize_page, targets


class SubjectGuideFactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = targets()
        cls.centers = {
            c['routeName']: c for c in json.loads(
                (ROOT / 'tools/data/branch-directory/branches.json').read_text(encoding='utf-8')
            )['centers']
        }
        cls.cases = []
        for record in cls.records:
            relative = Path(record['path'].strip('/')) / 'index.html'
            baseline = REPORT_ROOT / 'before-step6' / relative
            raw = (baseline if baseline.exists() else ROOT / relative).read_text(encoding='utf-8')
            center = cls.centers[record['center']]
            cls.cases.append((record, center, raw, align_guide(raw, record, center)))

    def sample(self, locality, subject):
        return next(c for c in self.cases if c[0]['locality'] == locality and c[0]['subject'] == subject)

    def test_106_explicit_targets_42_centers_and_original_differences(self):
        self.assertEqual(len(self.records), 106)
        self.assertEqual(len({r['path'] for r in self.records}), 106)
        self.assertEqual(len({r['center'] for r in self.records}), 42)
        self.assertEqual(sum('grades' in r['initialDifferences'] for r in self.records), 84)
        self.assertEqual(sum(r['previousName'] != self.centers[r['center']]['displayName'] for r in self.records), 14)
        self.assertEqual(sum(r['previousAddress'] != self.centers[r['center']]['address'] for r in self.records), 12)

    def test_41_workbook_centers_and_one_supplemental_reconcile(self):
        evidence = verify_centers(self.records, self.centers)
        self.assertEqual(len(evidence), 42)
        self.assertEqual(sum('sheet' in row for row in evidence), 41)
        self.assertEqual([row['center'] for row in evidence if 'sheet' not in row], ['화성태안점'])

    def test_all_facts_scope_and_idempotency(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                self.assertEqual(factual_errors(updated, record, center), [])
                self.assertEqual(scope_fingerprint(raw, record, center), scope_fingerprint(updated, record, center))
                self.assertEqual(align_guide(updated, record, center), updated)
                self.assertEqual(legacy_fact_differences(updated, center, record), {})

    def test_all_existing_uri_values_and_full_images_preserved(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                before, after = html.fromstring(raw), html.fromstring(updated)
                self.assertEqual(Counter(before.xpath('//a/@href')), Counter(after.xpath('//a/@href')))
                self.assertEqual([dict(n.attrib) for n in before.xpath('//img | //source')], [dict(n.attrib) for n in after.xpath('//img | //source')])
                self.assertEqual(before.xpath('//link[@rel="canonical"]/@href'), after.xpath('//link[@rel="canonical"]/@href'))
                self.assertEqual(before.xpath('//title/text()'), after.xpath('//title/text()'))
                self.assertEqual(before.xpath('//h1/text()'), after.xpath('//h1/text()'))

    def test_learning_navigation_and_schema_relations_still_work(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                self.assertEqual(route_errors(updated, center, record, 'guide', paired_routes(center, record), ROOT, REPORT_ROOT / 'staged-site'), [])

    def test_english_not_accidentally_using_math_grade_range(self):
        record, center, raw, updated = self.sample('명일동', '영어')
        self.assertEqual(course_guidance(center, '수학', '고')['grades'], ['고1', '고2'])
        self.assertEqual(course_guidance(center, '영어', '고')['grades'], ['고1', '고2', '고3'])
        doc = html.fromstring(updated)
        self.assertEqual(doc.xpath('//*[@data-guide-fact="grades"]//div[@class="math-tag-list"]/span/text()'), ['고1', '고2', '고3'])
        service = next(n for n in graph(doc) if n.get('@type') == 'Service')
        self.assertEqual(service['audience']['audienceType'], '고1~고3')
        self.assertEqual(doc.xpath('//*[@id="guide-course-note"]'), [])

    def test_partial_pending_grades_are_not_published_as_available(self):
        record, center, raw, updated = self.sample('범박동', '수학')
        doc = html.fromstring(updated)
        self.assertEqual(doc.xpath('//*[@data-guide-fact="grades"]//span/text()'), ['고1', '고2'])
        self.assertIn('고3 수학 수업은 현재 개설 여부', doc.xpath('//*[@id="guide-course-note"]')[0].text_content())
        service = next(n for n in graph(doc) if n.get('@type') == 'Service')
        self.assertEqual(service['audience']['audienceType'], '고1~고2')
        self.assertIn('고3 수학 수업은 현재 개설 여부', service['description'])

    def test_all_pending_and_unrecorded_courses_stay_distinct(self):
        for locality, subject, pending in [('소하동', '영어', ['고1', '고2', '고3']), ('화성태안', '수학', [])]:
            with self.subTest(locality=locality):
                record, center, raw, updated = self.sample(locality, subject)
                view = course_guidance(center, subject, '고')
                self.assertEqual(view['pendingGrades'], pending)
                self.assertEqual(view['grades'], [])
                doc = html.fromstring(updated)
                self.assertEqual([n for n in graph(doc) if n.get('@type') == 'Service'], [])
                self.assertNotIn('#service', json.dumps(graph(doc), ensure_ascii=False))
                self.assertIn('확인해 주세요', doc.xpath('//*[@id="guide-course-note"]')[0].text_content())
                self.assertNotIn('수업이 불가능', updated)

    def test_actual_modu_brand_and_legal_name_are_separate(self):
        record, center, raw, updated = self.sample('별내중앙', '영어')
        doc = html.fromstring(updated)
        self.assertEqual(doc.xpath('//*[@data-guide-fact="name"]/dd/text()'), ['모두오름학습코칭학원 별내중앙점'])
        self.assertEqual(doc.xpath('//*[@data-guide-fact="legal-name"]/dd/text()'), [center['registeredName']])
        self.assertNotIn(record['previousName'], updated)
        self.assertEqual(html.fromstring(raw).xpath('//h1/text()'), doc.xpath('//h1/text()'))

    def test_exact_old_addresses_are_corrected_without_locality_replacement(self):
        record, center, raw, updated = self.sample('위례', '수학')
        self.assertNotIn(record['previousAddress'], updated)
        self.assertIn(center['address'], updated)
        ordinary = '위례에서 수학을 배우는 학생의 학습 계획을 점검합니다.'
        self.assertEqual(corrected_text(ordinary, record, center), ordinary)
        self.assertEqual(html.fromstring(raw).xpath('//a/@href'), html.fromstring(updated).xpath('//a/@href'))

    def test_unverified_hours_offers_and_whole_center_grades_removed(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                orgs = [n for n in graph(html.fromstring(updated)) if n.get('@type') in ('EducationalOrganization', 'LocalBusiness')]
                self.assertEqual(len(orgs), 2)
                for node in orgs:
                    for field in ('openingHoursSpecification', 'openingHours', 'offers', 'makesOffer', 'educationalLevel', 'teaches'):
                        self.assertNotIn(field, node)

    def test_existing_faqs_preserved_and_new_faq_schema_exact(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                before, after = html.fromstring(raw), html.fromstring(updated)
                old = before.xpath('//div[@class="math-faq-list"]/details[not(@id="verified-course-faq")]')
                current = after.xpath('//div[@class="math-faq-list"]/details[not(@id="verified-course-faq")]')
                self.assertEqual(len(old), len(current))
                for a, b in zip(old, current):
                    self.assertEqual(corrected_text(a.text_content(), record, center), b.text_content())
                    self.assertEqual(dict(a.attrib), dict(b.attrib))
                faq = next(n for n in graph(after) if n.get('@type') == 'FAQPage')['mainEntity'][0]
                self.assertEqual(faq['acceptedAnswer']['text'], course_answer(center, record['subject'], '고'))
                self.assertNotIn('open', after.xpath('//*[@id="verified-course-faq"]')[0].attrib)

    def test_only_displayed_high_schools_used_in_schema_mentions(self):
        for record, center, raw, updated in self.cases:
            with self.subTest(path=record['path']):
                doc = html.fromstring(updated)
                schools = center.get('schools', {}).get('고등', [])[:10]
                self.assertEqual(doc.xpath('//*[@data-guide-fact="schools"]//span/text()'), schools)
                for node in graph(doc):
                    if node.get('@type') in ('WebPage', 'Article', 'Service'):
                        names = [n.get('name') for n in node['mentions'] if isinstance(n, dict)]
                        self.assertTrue(all(school in names for school in schools))
                        self.assertFalse((set(record['previousSchools']) - set(schools)) & set(names))

    def test_scope_guard_rejects_unrelated_content_and_metadata_edits(self):
        record, center, raw, updated = self.sample('명일동', '영어')
        baseline = scope_fingerprint(updated, record, center)
        for query, attribute in [('//h1', None), ('//title', None), ('//meta[@name="description"]', 'content'), ('//img', 'alt'), ('//img', 'src'), ('//a[@href]', 'href'), ('//section[contains(@class,"math-prose-section")]//p', None)]:
            with self.subTest(query=query, attribute=attribute):
                doc = html.fromstring(updated)
                node = doc.xpath(query)[0]
                if attribute:
                    node.set(attribute, 'unexpected-change')
                else:
                    node.text = 'unexpected-change'
                self.assertNotEqual(baseline, scope_fingerprint(serialize_page(doc), record, center))

    def test_scope_guard_rejects_unrelated_schema_edits(self):
        record, center, raw, updated = self.sample('명일동', '영어')
        baseline = scope_fingerprint(updated, record, center)
        for kind, key in [('Article', 'headline'), ('Article', 'datePublished'), ('Service', 'provider'), ('WebPage', 'relatedLink')]:
            with self.subTest(kind=kind, key=key):
                doc = html.fromstring(updated)
                script = doc.xpath('//script[@type="application/ld+json"]')[0]
                payload = json.loads(script.text)
                next(n for n in payload['@graph'] if n.get('@type') == kind)[key] = 'unexpected-change'
                script.text = json.dumps(payload, ensure_ascii=False)
                self.assertNotEqual(baseline, scope_fingerprint(serialize_page(doc), record, center))

    def test_wrong_canonical_and_wrong_center_are_rejected(self):
        record, center, raw, updated = self.sample('명일동', '영어')
        with self.assertRaises(ValueError):
            align_guide(raw.replace('rel="canonical"', 'rel="other"'), record, center)
        with self.assertRaises(ValueError):
            align_guide(raw, record, self.centers['원주시청점'])

    def test_inputs_never_mutated(self):
        record, center, raw, updated = self.sample('범박동', '영어')
        original_record, original_center = copy.deepcopy(record), copy.deepcopy(center)
        align_guide(raw, record, center)
        self.assertEqual(record, original_record)
        self.assertEqual(center, original_center)

    def test_korean_url_serialization_is_stable(self):
        record, center, raw, updated = self.sample('갈현동', '영어')
        self.assertIn('/과목별학원/', html.fromstring(updated).xpath('//a/@href'))
        self.assertEqual(Counter(html.fromstring(raw).xpath('//a/@href')), Counter(html.fromstring(updated).xpath('//a/@href')))
        self.assertEqual(align_guide(updated, record, center), updated)


if __name__ == '__main__':
    unittest.main()
