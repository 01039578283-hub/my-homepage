"""Step 4 contracts, including meaningful school/function/availability guards."""

import copy
import json
import unittest

from lxml import html

from branch_course_guidance import course_guidance
from branch_manuscript_editorial import edit_manuscript, other_level_school_names
from branch_page_summaries import (
    center_summaries, topic_summaries, validate_summaries, summary_document_errors,
)
from generate_branch_topic_pages import load_manuscripts, BRANCH_MANIFEST, ROOT
from refresh_branch_page_summaries import scope_fingerprint


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers = json.loads(BRANCH_MANIFEST.read_text(encoding="utf-8"))["centers"]
        cls.by_area = {area: center for center in cls.centers for area in center["neighborhoods"]}
        cls.originals = load_manuscripts()
        cls.edited = {key: edit_manuscript(cls.by_area[key[0]], source)[0] for key, source in cls.originals.items()}
        cls.summaries = {key: topic_summaries(cls.by_area[key[0]], item) for key, item in cls.edited.items()}

    def test_all_2226_topic_summaries_and_193_center_summaries(self):
        self.assertEqual(len(self.summaries), 2226)
        self.assertEqual(len(self.centers), 193)
        for key, summary in self.summaries.items():
            with self.subTest(key=key):
                validate_summaries(self.by_area[key[0]], summary, self.edited[key])
        for center in self.centers:
            validate_summaries(center, center_summaries(center))

    def test_all_three_fields_unique_across_all_target_pages(self):
        summaries = list(self.summaries.values()) + [center_summaries(c) for c in self.centers]
        for field in ("description", "abstract", "lead"):
            self.assertEqual(len(summaries), len({s[field] for s in summaries}))

    def test_source_and_edited_manuscripts_not_mutated(self):
        key = ("명일동", "고등", "수학")
        before = copy.deepcopy(self.edited[key])
        summary = topic_summaries(self.by_area[key[0]], self.edited[key])
        self.assertEqual(before, self.edited[key])
        self.assertNotEqual(summary["description"], before["description"])
        self.assertNotIn("명일점 안내 학년·수업 조건도", self.originals[key]["description"])

    def test_learning_lead_comes_from_body_not_school_list(self):
        for key, summary in self.summaries.items():
            self.assertNotIn("상담에서 참고할 학교", summary["lead"])
            self.assertNotIn("안내 주소는", summary["lead"])

    def test_unconfirmed_courses_start_with_qualification(self):
        count = 0
        for key, item in self.edited.items():
            center = self.by_area[key[0]]
            view = course_guidance(center, item["subject"], item["prefix"])
            if not view["grades"]:
                count += 1
                self.assertTrue(self.summaries[key]["description"].startswith(f'{center["routeName"]} {item["level"]} {item["subject"]} 개설 여부는 상담 확인이 필요합니다.'))
                self.assertNotIn("수업 불가", self.summaries[key]["description"])
        self.assertEqual(count, 52)

    def test_pending_grades_are_not_turned_into_available_courses(self):
        for key, item in self.edited.items():
            view = course_guidance(self.by_area[key[0]], item["subject"], item["prefix"])
            if view["grades"] and view["pendingGrades"]:
                self.assertIn("일부 학년은 조건 확인이 필요합니다", self.summaries[key]["description"])

    def test_mixed_school_level_lists_removed_from_summaries(self):
        for key, summary in self.summaries.items():
            for value in summary.values():
                self.assertFalse(other_level_school_names(self.by_area[key[0]], key[1], value))
        self.assertIn("초등학교 학습 자료", self.summaries[("삼송", "초등", "영어")]["description"])
        self.assertIn("어법 문장", self.summaries[("삼송", "초등", "영어")]["lead"])

    def test_math_input_and_student_speech_are_not_authoring_instructions(self):
        self.assertIn("입력값", self.summaries[("석사동", "고등", "수학")]["description"])
        self.assertIn("원고 수정", self.summaries[("송촌동", "중등", "영어")]["description"])

    def test_foreign_typo_removed_without_losing_topic(self):
        abstract = self.summaries[("두호동", "고등", "수학")]["abstract"]
        self.assertNotIn("तथा", abstract)
        self.assertIn("반 이동", abstract)
        self.assertIn("및 학습클리닉", abstract)

    def test_html_contract_catches_changed_or_missing_fields(self):
        expected = {"description": "검색 설명", "abstract": "본문 요약", "lead": "첫 안내"}
        doc = html.fromstring('<html><head><meta name="description" content="검색 설명"><meta property="og:description" content="검색 설명"></head><body><p class="branch-lead">첫 안내</p></body></html>')
        schema = [{"@type": "WebPage", "description": "검색 설명"}, {"@type": "Article", "description": "검색 설명", "abstract": "본문 요약"}]
        self.assertEqual(summary_document_errors(doc, schema, expected), [])
        schema[1]["abstract"] = "검색 설명"
        self.assertTrue(summary_document_errors(doc, schema, expected))
        doc.xpath('//p')[0].text = "관련 없는 안내"
        self.assertIn("첫 학습 안내와 본문 근거 불일치", summary_document_errors(doc, schema, expected))

    def test_scope_guard_rejects_body_images_courses_links_and_titles(self):
        file = ROOT / "지점안내/서울/명일점/명일동고등수학학원/index.html"
        raw = file.read_text(encoding="utf-8")
        before = scope_fingerprint(raw)
        for xpath, attribute in (("//h1", None), ('//*[@id="article"]//p', None), ('//*[@id="overview"]//p[@class="branch-first-answer"]', None), ('//*[@id="faq"]//p', None), ('//img', "alt"), ('//*[@id="related-pages"]//a', "href")):
            with self.subTest(xpath=xpath):
                doc = html.fromstring(raw)
                node = doc.xpath(xpath)[0]
                if attribute:
                    node.set(attribute, "changed")
                else:
                    node.text = "changed"
                self.assertNotEqual(before, scope_fingerprint(html.tostring(doc, encoding="unicode")))


if __name__ == "__main__":
    unittest.main()
