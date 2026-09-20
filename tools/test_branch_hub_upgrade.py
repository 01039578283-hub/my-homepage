"""Content, fact-boundaries, link budgets and regeneration regression tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from lxml import html

from branch_hub_upgrade import (
    ROOT, center_learning, child_directory, directory_learning,
    related_entries, upgrade_child, upgrade_center, upgrade_header, upgrade_directory,
)
from branch_course_guidance import course_guidance
from refresh_branch_hub_upgrade import protected_content, validate_page


class BranchHubUpgradeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers = json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
        cls.by_name = {c['routeName']: c for c in cls.centers}
        cls.records = json.loads((ROOT/'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']

    def test_all_related_links_are_contextual_and_bounded(self):
        for record in self.records:
            center = self.by_name[record['center']]
            links = related_entries(center, record)
            paths = [entry[1] for entry in links]
            self.assertIn(len(paths), (4,5))
            self.assertEqual(len(paths), len(set(paths)))
            self.assertNotIn(record['path'], paths)
            parent = record['path'].rsplit('/',2)[0] + '/'
            self.assertEqual(paths[0], parent)
            for path in paths[1:]:
                if path.startswith('/지점안내/'):
                    self.assertTrue(path.startswith(parent + record['locality']))
            if record['level'] == '초등':
                self.assertFalse(any('고등' in p for p in paths))
            if record['level'] == '고등':
                self.assertFalse(any('초등' in p for p in paths))

    def test_all_2226_children_remain_in_parent_directories(self):
        paths = []
        for center in self.centers:
            if not center['neighborhoods']:
                self.assertEqual(child_directory(center), '')
                continue
            doc = html.fromstring(child_directory(center))
            self.assertEqual(len(doc.xpath('//*[@class="hub-neighborhood-group"]')), len(center['neighborhoods']))
            paths.extend(doc.xpath('//a/@href'))
        self.assertEqual(set(paths), {r['path'] for r in self.records})
        self.assertEqual(len(paths), 2226)

    def test_reviewed_grade_ranges_only_in_learning_cards(self):
        for center in self.centers:
            doc = html.fromstring(center_learning(center))
            for level, prefix in (('초등','초'),('중등','중'),('고등','고')):
                actual = doc.xpath(f'//*[@data-learning-level="{level}"]//h4/text()')
                expected = [f'{s} · {course_guidance(center,s,prefix)["label"]}' for s in ('영어','수학') if course_guidance(center,s,prefix)['grades']]
                self.assertEqual(actual, expected)

    def test_modoo_centers_do_not_inherit_wawa_ai_program_claims(self):
        modoo = [c for c in self.centers if '모두' in c['brand']]
        self.assertTrue(modoo)
        for center in modoo:
            raw = center_learning(center)
            self.assertNotIn('/overview/', raw)
            self.assertNotIn('AI 학습', raw)
            self.assertIn('/guide/consultation-diagnosis/', raw)

    def test_myeongil_copy_uses_real_schools_and_not_all_grades(self):
        raw = center_learning(self.by_name['명일점'])
        self.assertIn('서울고명초등학교', raw)
        self.assertIn('명일동·천호동', raw)
        self.assertIn('수학 · 고1~고2', raw)
        self.assertNotIn('수학 · 고1~고3', raw)
        self.assertIn('학습 준비 방법', raw)

    def test_center_and_child_upgrade_are_idempotent_and_preserve_scope(self):
        center = self.by_name['명일점']
        for record in [r for r in self.records if r['center'] == '명일점']:
            before = (ROOT/record['file']).read_text(encoding='utf-8')
            after = upgrade_child(before, center, record)
            self.assertEqual(upgrade_child(after, center, record), after)
            self.assertEqual(protected_content(before,'child'), protected_content(after,'child'))
            validate_page(after, 'child', center, record)
        before = (ROOT/'지점안내/서울/명일점/index.html').read_text(encoding='utf-8')
        after = upgrade_center(before, center)
        self.assertEqual(upgrade_center(after,center), after)
        self.assertEqual(protected_content(before,'center'), protected_content(after,'center'))

    def test_header_keeps_existing_center_and_branch_routes(self):
        raw = (ROOT/'index.html').read_text(encoding='utf-8')
        new = upgrade_header(raw, '/')
        self.assertEqual(upgrade_header(new, '/'), new)
        doc = html.fromstring(new)
        self.assertEqual(len(doc.xpath('//header//a[@href="/center/"]')),1)
        self.assertEqual(len(doc.xpath('//header//a[@href="/지점안내/"]')),1)
        self.assertEqual(protected_content(raw,'core'), protected_content(new,'core'))

    def test_no_source_data_mutation(self):
        before = copy.deepcopy(self.centers)
        for center in self.centers:
            center_learning(center)
            child_directory(center)
        directory_learning(self.centers)
        self.assertEqual(before, self.centers)

    def test_future_generator_retains_new_sections_and_link_budget(self):
        import generate_branch_directory as directory
        import generate_branch_topic_pages as topics
        center = self.by_name['명일점']
        old_output = directory.OUTPUT_ROOT
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            try:
                directory.OUTPUT_ROOT = root/'지점안내'
                path = directory.generate_branch_page(center)
                raw = (root/path.strip('/')/'index.html').read_text(encoding='utf-8')
                self.assertIn('hub-stage-grid', raw)
                validate_page(raw, 'center', center)
                source = topics.load_manuscripts()[('명일동','고등','수학')]
                _, relative = topics.render_page(center, source, root)
                validate_page((root/relative).read_text(encoding='utf-8'), 'child', center, source)
            finally:
                directory.OUTPUT_ROOT = old_output


if __name__ == '__main__':
    unittest.main()
