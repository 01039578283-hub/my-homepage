"""Regression cases chosen independently from the workbook's reviewed cells."""

import copy
import json
import unittest
from pathlib import Path

from branch_course_guidance import (
    GRADES, branch_course_answer, center_notes, course_answer, course_guidance,
    format_grades, rules_data, weekend_guidance,
)
from generate_branch_directory import weekend_summary

ROOT = Path(__file__).resolve().parents[1]
CENTERS = {c["routeName"]: c for c in json.loads((ROOT / "tools/data/branch-directory/branches.json").read_text(encoding="utf-8"))["centers"]}


class CourseGuidanceTest(unittest.TestCase):
    def test_all_source_grades_preserved(self):
        before = copy.deepcopy(CENTERS)
        for center in CENTERS.values():
            for subject in ("국어", "영어", "수학", "과학", "사회"):
                for prefix in (None, "초", "중", "고"):
                    view = course_guidance(center, subject, prefix)
                    self.assertEqual(set(view["grades"]) | set(view["pendingGrades"]), set(view["rawGrades"]))
                    self.assertFalse(set(view["grades"]) & set(view["pendingGrades"]))
        self.assertEqual(CENTERS, before)

    def test_missing_grades_never_interpolated(self):
        self.assertEqual(format_grades(["초1", "초2", "초3", "초4", "초5", "중2", "중3"]), "초1~초5 · 중2~중3")
        self.assertEqual(format_grades(["고3", "고1"]), "고1 · 고3")
        self.assertEqual(format_grades(list(GRADES)), "초1~고3")
        self.assertEqual(format_grades([]), "")
        with self.assertRaises(ValueError):
            format_grades(["초7"])

    def test_myeongil_subject_ranges(self):
        c = CENTERS["명일점"]
        self.assertEqual(course_guidance(c, "영어")["label"], "초5~고3")
        self.assertEqual(course_guidance(c, "수학")["label"], "초4~고2")
        self.assertEqual(course_guidance(c, "영어", "초")["grades"], ["초5", "초6"])
        self.assertEqual(course_guidance(c, "수학", "고")["grades"], ["고1", "고2"])

    def test_wonju_third_grade_inquiry(self):
        c = CENTERS["원주시청점"]
        self.assertEqual(course_guidance(c, "영어", "고")["grades"], ["고1", "고2"])
        self.assertIn("고3 영어는 별도 문의", course_answer(c, "영어", "고"))
        self.assertNotIn("고3 영어", course_answer(c, "영어", "초"))
        self.assertEqual(course_guidance(c, "국어", "초")["grades"], [])
        self.assertIn("특강", weekend_guidance(c))

    def test_gwanpyeong_gaps_and_condition(self):
        c = CENTERS["관평점"]
        self.assertEqual(course_guidance(c, "국어")["label"], "초1~초5 · 중2~중3")
        self.assertIn("6개월", course_answer(c, "영어", "고"))
        self.assertNotIn("6개월", course_answer(c, "영어", "초"))
        self.assertNotIn("6개월", course_answer(c, "수학", "고"))

    def test_conflicts_are_partial_not_all_center(self):
        for name in ("가좌점", "원당점"):
            view = course_guidance(CENTERS[name], "수학", "초")
            self.assertEqual(view["grades"], ["초4", "초5", "초6"])
            self.assertEqual(view["pendingGrades"], ["초1", "초2", "초3"])
        for name in ("신도림점", "범박점"):
            self.assertEqual(course_guidance(CENTERS[name], "수학", "고")["grades"], ["고1", "고2"])
        self.assertTrue(course_guidance(CENTERS["소하점"], "수학")["grades"])
        self.assertFalse(course_guidance(CENTERS["소하점"], "영어")["grades"])
        self.assertFalse(course_guidance(CENTERS["수지점"], "수학")["grades"])
        self.assertTrue(course_guidance(CENTERS["수지점"], "영어")["grades"])

    def test_unrecorded_is_not_unavailable(self):
        for name, subject, prefix in [("석사점", "수학", "초"), ("교하점", "영어", "중"), ("화성태안점", "수학", "고"), ("두호점", "영어", "초")]:
            answer = course_answer(CENTERS[name], subject, prefix)
            self.assertIn("먼저 확인", answer)
            self.assertNotIn("수업 불가", answer)
            self.assertFalse(course_guidance(CENTERS[name], subject, prefix)["grades"])

    def test_pending_subject_particles_and_no_repeated_lead(self):
        answer = course_answer(CENTERS["소하점"], "영어", "고")
        self.assertNotIn("영어은", answer)
        self.assertEqual(answer.count("개설 여부를 먼저 확인"), 1)
        self.assertIn("고1~고3 영어 수업", answer)

    def test_unsupported_high_grades_not_expanded(self):
        for name in ("광장점", "금천점", "상현점", "이곡점", "이충점", "화명점"):
            self.assertNotIn("고3", course_guidance(CENTERS[name], "수학", "고")["grades"])
        self.assertEqual(course_guidance(CENTERS["미사점"], "영어", "고")["grades"], ["고1"])
        self.assertIn("화상", course_answer(CENTERS["당산점"], "영어", "고"))
        self.assertEqual(course_guidance(CENTERS["당산점"], "영어", "고")["grades"], ["고1"])

    def test_phonics_scope(self):
        for name in ("향남점", "호평점"):
            self.assertIn("파닉스", course_answer(CENTERS[name], "영어", "초"))
            self.assertNotIn("파닉스", course_answer(CENTERS[name], "수학", "초"))

    def test_weekend_negation_is_scoped(self):
        parsed = weekend_summary("토요일 과학수업만가능.일요일불가능", "2시-5시 과학수업가능")
        self.assertIn("토요일은 과학", parsed)
        self.assertNotIn("주말 정규 수업은 운영하지", parsed)
        self.assertIn("일요일 수업은 운영하지", parsed)
        self.assertIn("오후 2시~5시", weekend_guidance(CENTERS["신도림점"]))
        self.assertIn("확인", weekend_guidance(CENTERS["광장점"]))

    def test_stale_capacity_is_not_current_capacity(self):
        for name in ("고잔점", "상남점", "장기점", "진월점", "침산점"):
            answer = course_answer(CENTERS[name], "영어", "고")
            self.assertNotIn("현재 마감", answer)
            self.assertNotIn("현재 만석", answer)
            self.assertIn("등록", answer)

    def test_rule_identity_guard(self):
        bad = {**CENTERS["가좌점"], "sourceRow": 99}
        with self.assertRaises(ValueError):
            course_guidance(bad, "수학")
        self.assertEqual(len(rules_data()["centers"]), 58)
        self.assertEqual(set(rules_data()["centers"]) - set(CENTERS), set())


if __name__ == "__main__":
    unittest.main()
