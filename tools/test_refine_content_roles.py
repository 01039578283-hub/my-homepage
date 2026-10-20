import unittest
from refine_content_roles import grammar,transform,EXAMPLES
class RoleTests(unittest.TestCase):
 def test_particle_fix_does_not_damage_compound_word(self):
  self.assertEqual(grammar('서술형 풀이과 복습 · 풀이과정 · 신원고'), '서술형 풀이와 복습 · 풀이과정 · 신원고')
 def test_attributes_code_and_school_name_preserved(self):
  s='<html><head></head><body><p>서술형 풀이과 복습</p><img src="/서술형 풀이과.png"><script>let x="학원를";</script><p>신원고 발표 원고를 준비합니다.</p></body></html>'
  out,_=transform('test.html',s,{'links':{}})
  self.assertIn('src="/서술형 풀이과.png"',out);self.assertIn('let x="학원를"',out);self.assertIn('신원고 발표 원고를',out)
 def test_example_disclosure_retained(self):
  out=grammar('제공된 원고를 바탕으로 상담에서 살펴볼 수 있는 상황을 정리한 사례형 예시입니다.')
  self.assertIn('가상 상황 예시',out)
 def test_middle_math_examples_have_correct_values(self):
  self.assertEqual([x for x in range(-10,11) if x*x-5*x+6==0],[2,3]);self.assertIn('2와 3',EXAMPLES['중3','수학'][1])
 def test_attributed_heading_cannot_consume_following_sections(self):
  s='<html><head></head><body><main><h1>가경동 중1 수학학원</h1><section id="section-02" class="math-prose-section"><h2 data-source-heading>개념을 확인하기</h2><p data-source-paragraph>기존 고유 설명을 유지합니다.</p></section><section id="section-03"><h2>다음 내용</h2><p>다음 문단</p><img src="/original.jpg"></section></main></body></html>'
  out,_=transform('학년별학원/중1수학학원/가경동/index.html',s,{'tasks':{'중1수학':{'task':'조건을 식으로 옮기기'}},'links':{}})
  self.assertIn('기존 고유 설명을 유지합니다.',out);self.assertIn('<section id="section-03"><h2>다음 내용</h2><p>다음 문단</p><img src="/original.jpg"></section>',out)
  self.assertEqual(out.count('<section '),out.count('</section>'));self.assertIn('data-role-exercise',out)
if __name__=='__main__':unittest.main()
