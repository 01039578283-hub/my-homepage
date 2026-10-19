import unittest
from lxml import html
from editorial_html_cleanup import structure,grammar,transform,COMMON_TEACHER

class CleanupTests(unittest.TestCase):
 def test_nested_fragments_preserve_actual_assets_and_script_literals(self):
  s='<html><head><html><head><link href="/x.css"></head></html><html><head><script>let x="<head>";</script></head></html></head><body><img src="/x.jpg"></body></html>'
  expected='<html><head><link href="/x.css"><script>let x="<head>";</script></head><body><img src="/x.jpg"></body></html>'
  self.assertEqual(structure(s),expected);self.assertEqual(structure(expected),expected)
 def test_unexpected_nested_body_is_not_flattened(self):
  with self.assertRaises(AssertionError):structure('<html><head></head><body><html><head></head><body>x</body></html></body></html>')
 def test_fragment_creation_does_not_insert_document(self):
  self.assertEqual(html.fragment_fromstring('<link rel="stylesheet" href="/a.css">').tag,'link')
  self.assertEqual(html.fragment_fromstring('<script defer src="/a.js"></script>').tag,'script')
 def test_reviewed_grammar_handles_korean_grade_particles(self):
  self.assertEqual(grammar('최근 최근 시험지와 고1·고2 이 안내된 자료, 중3가 대상인 글, 오답를 확인'), '최근 시험지와 고1·고2가 안내된 자료, 중3이 대상인 글, 오답을 확인')
 def test_after_and_next_retain_their_different_meanings(self):
  self.assertEqual(grammar('확인한 다음 다음 단계로, 보완한 다음 다음 단원으로'), '확인하고 다음 단계로, 보완하고 다음 단원으로')
 def test_combined_subject_worksheet_keeps_both_subjects(self):
  s='<html><head></head><body><section class="article-local-feature-section"><h2>선생님 특징</h2><p>'+COMMON_TEACHER+'</p><p>'+COMMON_TEACHER+'</p></section></body></html>'
  out,_=transform('center/region/district/area/mathenglish/index.html',s)
  self.assertIn('영어와 수학 중 혼자 시작하기 어려운 과제',out)
 def test_guide_wrapper_repair_keeps_text_and_media(self):
  s='<html><head></head><body><article><div><section><p>실행 내용</p><img src="/old.jpg"></section></div></section>\n<section class="lg-section lg-example-box" id="lg-example"><p>연습 예시</p></section></div></article></body></html>'
  out,reasons=transform('guide/study-planner/index.html',s)
  self.assertIn('<img src="/old.jpg">',out);self.assertIn('<p>연습 예시</p>',out)
  self.assertEqual(reasons['guideContainerNesting'],1)
  self.assertEqual(out.count('<div>'),out.count('</div>'))
 def test_attributes_and_code_are_not_rewritten(self):
  s='<html><head></head><body><a href="/최근 최근/">최근 최근 시험지</a><script>let x="최근 최근";</script><img src="/최근 최근.png"></body></html>'
  actual,_=transform('test/index.html',s)
  self.assertIn('href="/최근 최근/"',actual);self.assertIn('src="/최근 최근.png"',actual);self.assertIn('let x="최근 최근"',actual);self.assertIn('>최근 시험지</a>',actual)

if __name__=='__main__':unittest.main()
