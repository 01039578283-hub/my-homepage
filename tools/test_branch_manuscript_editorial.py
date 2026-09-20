"""Editorial regressions, source boundaries and all-manuscript invariants."""

import copy
import json
import re
import unittest

import generate_branch_topic_pages as topics
from branch_manuscript_editorial import (
    AUTHORING, clean_authoring, corrections, edit_manuscript,
    learning_points, object_form, school_aliases,
)
from refresh_branch_manuscript_editorial import validate_editorial


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manuscripts = topics.load_manuscripts()
        cls.centers = json.loads(topics.BRANCH_MANIFEST.read_text(encoding="utf-8"))["centers"]
        cls.by_local = {name: center for center in cls.centers for name in center["neighborhoods"]}

    def edit(self, key):
        return edit_manuscript(self.by_local[key[0]], self.manuscripts[key])[0]

    def body(self, item):
        return " ".join(item["intro"] + [s["heading"] + " ".join(s["paragraphs"]) for s in item["sections"]] + [f["question"] + f["answer"] for f in item["faq"]] + item["example"])

    def test_source_and_facts_not_mutated(self):
        key = ("명일동", "고등", "수학")
        source, center = copy.deepcopy(self.manuscripts[key]), copy.deepcopy(self.by_local[key[0]])
        one = self.edit(key)
        self.assertEqual(self.manuscripts[key], source)
        self.assertEqual(self.by_local[key[0]], center)
        self.assertEqual(one, self.edit(key))

    def test_korean_particles(self):
        self.assertEqual(object_form("풀이"), "풀이를")
        self.assertEqual(object_form("기록"), "기록을")

    def test_authoring_aside_removed_but_advice_retained(self):
        value = "원고 참고 키워드인 영어 수학을 함께 봅니다. 과목별 과제를 기록해 보세요."
        self.assertEqual(clean_authoring(value), "과목별 과제를 기록해 보세요.")

    def test_legitimate_speech_manuscript_and_study_keywords_retained(self):
        value = "발표 원고를 소리 내어 읽고 핵심 키워드를 적어 보세요."
        self.assertEqual(clean_authoring(value), value)

    def test_math_input_and_output_not_authoring(self):
        value = "함수의 입력과 출력의 관계를 표로 나타내 보세요."
        self.assertEqual(clean_authoring(value), value)
        self.assertFalse(AUTHORING.search("신원고와 덕원고 학생의 학습 기록"))

    def test_full_school_name_and_aliases(self):
        names = school_aliases("서울고명초등학교")
        self.assertIn("고명초", names)
        self.assertIn("명일여고", school_aliases("명일여자고등학교"))

    def test_myeongil_high_school_and_math_example(self):
        text = self.body(self.edit(("명일동", "고등", "수학")))
        self.assertIn("강동고등학교", text)
        self.assertNotIn("천호중", text)
        self.assertNotIn("심리 연구", text)
        self.assertIn("공식의 이름과 사용 조건", text)

    def test_duho_primary_school_not_middle_school(self):
        text = self.body(self.edit(("두호동", "초등", "영어")))
        self.assertIn("두호남부초등학교", text)
        self.assertNotIn("환호여중", text)
        self.assertNotIn("두호고", text)
        self.assertIn("용두산길 32 3층", text)

    def test_fictional_example_does_not_reintroduce_wrong_school(self):
        text = " ".join(self.edit(("관저동", "중등", "수학"))["example"])
        self.assertNotIn("서일여고", text)
        self.assertIn("상황 예시", text)

    def test_school_name_with_quotative_particle_and_in_question(self):
        text = self.body(self.edit(("운정신도시", "고등", "영어")))
        self.assertNotIn("한가람초", text)
        self.assertIn("학교 자료는 어떤 기준", text)

    def test_age_appropriate_geometry_and_metadata_consistency(self):
        item = self.edit(("반달마을", "초등", "수학"))
        self.assertNotIn("접선", self.body(item) + item["description"] + item["abstract"])
        self.assertIn("반지름", self.body(item))

    def test_primary_english_focus_not_advanced_grammar_drill(self):
        item = self.edit(("운정", "초등", "영어"))
        self.assertNotIn("관계사", self.body(item))
        self.assertIn("짧은 문장", self.body(item))
        self.assertEqual(len({q["question"] for q in item["faq"]}), 4)

    def test_multiple_school_headings_do_not_collapse(self):
        for key in (("송탄", "고등", "영어"), ("화정동", "고등", "영어")):
            headings = [s["heading"] for s in self.edit(key)["sections"]]
            self.assertEqual(len(headings), len(set(headings)))

    def test_math_does_not_use_reading_book_transition_as_course_topic(self):
        for key in (("칠성동", "초등", "수학"), ("반구동", "중등", "수학"), ("약사동", "고등", "수학")):
            self.assertNotIn("챕터북", self.body(self.edit(key)))

    def test_original_metadata_preserved_except_reviewed_mismatches(self):
        for key, original in self.manuscripts.items():
            edited = self.edit(key)
            self.assertEqual(edited["title"], original["title"])
            for field in ("description", "abstract"):
                if edited[field] != original[field]:
                    self.assertIn(key, corrections())
                    self.assertRegex(original[field], corrections()[key]["pattern"])

    def test_all_manuscripts_have_nonempty_unique_sections_and_faqs(self):
        for key, original in self.manuscripts.items():
            edited = self.edit(key)
            validate_editorial(original, edited, str(key))
            self.assertGreater(len(self.body(edited)), 1200, key)

    def test_all_center_learning_cards_have_supported_category(self):
        for center in self.centers:
            points = learning_points(center)
            self.assertGreaterEqual(len(points), 1)
            self.assertLessEqual(len(points), 4)
            self.assertTrue(all(copy.endswith(("보세요.", "하세요.")) for _, copy in points), center["routeName"])


if __name__ == "__main__":
    unittest.main()
