"""Step 5: exact, reciprocal, additive-only learning navigation contracts."""

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from lxml import html

from branch_learning_routes import ROOT, SCRIPT, canonical, paired_routes, segment, upgrade_page
from refresh_branch_learning_routes import graph, route_errors, scope_fingerprint


class LearningRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers = json.loads((ROOT / 'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
        cls.by_name = {c['routeName']: c for c in cls.centers}
        cls.records = json.loads((ROOT / 'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']
        cls.center = cls.by_name['명일점']
        cls.item = {'locality': '명일동', 'level': '고등', 'subject': '수학'}
        cls.routes = paired_routes(cls.center, cls.item)

    def read(self, kind):
        return (ROOT / self.routes[kind].strip('/') / 'index.html').read_text(encoding='utf-8')

    def test_742_unique_exact_pairs_and_188_centers(self):
        pairs = [(r, paired_routes(self.by_name[r['center']], r)) for r in self.records]
        pairs = [(r, p) for r, p in pairs if p]
        self.assertEqual(len(pairs), 742)
        self.assertEqual(len({p['guide'] for _, p in pairs}), 742)
        self.assertEqual(len({r['center'] for r, _ in pairs}), 188)
        for record, pair in pairs:
            self.assertEqual(record['path'], pair['child'])
            self.assertIn(f'/고등{record["subject"]}학원/', pair['guide'])
            self.assertEqual(record['locality'], pair['guide'].strip('/').split('/')[-1])

    def test_malformed_path_segments_rejected(self):
        for value in ('..', '.', '', ' ', ' 명일동', '서울/명일점', '../명일동', 'a\\b', '%2e%2e', 'a?x', 'a#x', '<script>', 'a\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                segment(value)
        self.assertEqual(segment('대구 유천동'), '대구 유천동')

    def test_wrong_branch_cannot_be_linked_by_similar_name(self):
        with self.assertRaises(ValueError):
            paired_routes(self.by_name['원주시청점'], self.item)

    def test_wrong_canonical_refuses_changes(self):
        raw = self.read('guide').replace('rel="canonical"', 'rel="other"')
        with self.assertRaises(ValueError):
            upgrade_page(raw, self.center, self.item, 'guide')

    def test_lower_school_levels_are_noop(self):
        for level in ('초등', '중등'):
            item = {**self.item, 'level': level}
            self.assertIsNone(paired_routes(self.center, item))
            self.assertEqual(upgrade_page('unchanged', self.center, item, 'child'), 'unchanged')

    def test_missing_exact_guide_does_not_create_link(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(paired_routes(self.center, self.item, Path(directory)))
            self.assertEqual(upgrade_page('unchanged', self.center, self.item, 'child', Path(directory)), 'unchanged')

    def test_both_page_types_are_idempotent_and_in_scope(self):
        for kind in ('guide', 'child'):
            with self.subTest(kind=kind):
                raw = self.read(kind)
                updated = upgrade_page(raw, self.center, self.item, kind)
                self.assertEqual(upgrade_page(updated, self.center, self.item, kind), updated)
                self.assertEqual(scope_fingerprint(raw, kind, self.routes), scope_fingerprint(updated, kind, self.routes))
                self.assertEqual(route_errors(updated, self.center, self.item, kind, self.routes, ROOT, Path('nonexistent-stage')), [])

    def test_existing_links_are_never_truncated(self):
        raw = self.read('child')
        result = html.fromstring(upgrade_page(raw, self.center, self.item, 'child'))
        before = Counter(html.fromstring(raw).xpath('//a/@href'))
        self.assertFalse(before - Counter(result.xpath('//a/@href')))
        self.assertLessEqual(len(result.xpath('//*[@id="related-pages"]//div[@class="related-grid"]/a')), 10)
        self.assertEqual(len(result.xpath('//a[@data-learning-route="guide"]')), 1)

    def test_metadata_body_facts_faq_images_still_protected(self):
        for kind, queries in (('guide', ['//h1', '//meta[@name="description"]', '//aside[@class="math-info-card"]//dd', '//img']), ('child', ['//h1', '//*[@id="article"]//p', '//*[@id="overview"]//p[@class="branch-first-answer"]', '//*[@id="faq"]//p', '//img'])):
            raw = self.read(kind)
            before = scope_fingerprint(raw, kind, self.routes)
            for query in queries:
                with self.subTest(kind=kind, query=query):
                    doc = html.fromstring(raw)
                    node = doc.xpath(query)[0]
                    if node.tag == 'img':
                        node.set('alt', 'altered')
                    elif node.tag == 'meta':
                        node.set('content', 'altered')
                    else:
                        node.text = 'altered'
                    self.assertNotEqual(before, scope_fingerprint(html.tostring(doc, encoding='unicode'), kind, self.routes))

    def test_schema_course_facts_and_existing_related_links_preserved(self):
        raw = self.read('child')
        match = SCRIPT.search(raw)
        payload = json.loads(match.group(2))
        page = next(n for n in payload['@graph'] if n.get('@type') == 'WebPage')
        page['relatedLink'] = ['https://wawa-center.kr/guide/']
        inserted = raw[:match.start(2)] + json.dumps(payload, ensure_ascii=False) + raw[match.end(2):]
        result = graph(html.fromstring(upgrade_page(inserted, self.center, self.item, 'child')))
        updated_page = next(n for n in result if n.get('@type') == 'WebPage')
        self.assertIn('https://wawa-center.kr/guide/', updated_page['relatedLink'])
        self.assertIn(canonical(self.routes['guide']), updated_page['relatedLink'])
        self.assertEqual([n for n in payload['@graph'] if n.get('@type') == 'Service'], [n for n in result if n.get('@type') == 'Service'])

    def test_pending_course_wording_and_all_images_unchanged(self):
        for center_name, locality in (('소하점', '소하동'), ('석사점', '석사동')):
            center = self.by_name[center_name]
            item = {'locality': locality, 'level': '고등', 'subject': '영어'}
            routes = paired_routes(center, item)
            raw = (ROOT / routes['child'].strip('/') / 'index.html').read_text(encoding='utf-8')
            before = html.fromstring(raw)
            after = html.fromstring(upgrade_page(raw, center, item, 'child'))
            self.assertEqual(before.xpath('//*[@id="overview"]')[0].text_content(), after.xpath('//*[@id="overview"]')[0].text_content())
            self.assertEqual([dict(n.attrib) for n in before.xpath('//img | //source')], [dict(n.attrib) for n in after.xpath('//img | //source')])

    def test_generator_retains_navigation_without_mutating_manuscript(self):
        import generate_branch_topic_pages as generator
        source = generator.load_manuscripts()[('명일동', '고등', '수학')]
        before = copy.deepcopy(source)
        with tempfile.TemporaryDirectory() as directory:
            path, relative = generator.render_page(self.center, source, Path(directory))
            self.assertEqual(path, self.routes['child'])
            raw = (Path(directory) / relative).read_text(encoding='utf-8')
            self.assertEqual(route_errors(raw, self.center, source, 'child', self.routes, ROOT, Path(directory)), [])
        self.assertEqual(before, source)


if __name__ == '__main__':
    unittest.main()
