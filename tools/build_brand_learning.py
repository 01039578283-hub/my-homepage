"""Publish rewritten brand learning explanations without replacing existing modules.

Source: https://www.wawacenter.com/ (owner-authorized text and photographs).
School schedules and planner records below are explicitly illustrative, not
claims that all local centers provide the same service, class size or results.
"""
from pathlib import Path
from html import escape
from urllib.parse import quote
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://wawa-center.kr'
DATE = '2026-10-03'
PAGES = [
    ('수업형식-비교', '강의식·개별 맞춤 수업, 우리 아이에게 맞는 방식 찾기',
     '강의식과 개별 맞춤 수업의 진도·피드백 차이를 비교하고, 학생 상황에 맞는 선택 기준과 상담 질문을 확인하세요.'),
    ('학교별-내신관리', '학교별 내신 준비, 시험 범위에서 복습까지 연결하기',
     '학교 시험 범위와 수업 자료를 기준으로 개념·문제·서술형·오답 복습을 연결하고, 내신 상담에 필요한 질문을 준비하세요.'),
    ('플래너-학습관리', '플래너 학습관리, 계획·실행·피드백을 이어가기',
     '플래너에 구체적인 과제와 확인 결과를 기록하는 방법, 미완료 과제 조정과 학부모 대화·상담 질문을 살펴보세요.'),
]

def link(path, label, primary=False):
    return f'<a class="wb-link{" wb-primary" if primary else ""}" href="{quote(path, safe="/#")}">{escape(label)} <span aria-hidden="true">→</span></a>'

def actions(items):
    return '<div class="wb-actions">' + ''.join(link(*item) for item in items) + '</div>'

ROWS = [
    ('출발 기준', '학년·학교 진도와 공통 시험 범위를 중심으로 시작합니다.', '현재 이해도와 막히는 지점을 확인해 시작 단원을 정합니다.'),
    ('진도·과제', '공통 설명과 과제를 따라가며 함께 진도를 나갑니다.', '부족한 선수 개념과 현재 단원을 연결하고 과제 난도를 조정합니다.'),
    ('질문·피드백', '공통 설명 뒤 질문 시간과 과제 점검 방식이 중요합니다.', '학생의 풀이·설명을 확인하고 오류 원인에 맞춰 다시 지도합니다.'),
    ('잘 맞을 수 있는 상황', '공통 진도를 따라갈 기초가 있고, 설명을 들은 뒤 혼자 복습할 수 있습니다.', '이해도 차이가 크거나 기초 공백이 있어, 출발점·속도·복습을 따로 조정해야 합니다.'),
    ('상담에서 확인할 것', '모르는 내용을 질문할 기회와 수업 후 복습 점검이 충분한지 확인합니다.', '진단 결과가 과제에 반영되는지, 설명·질문·재확인이 어떻게 이루어지는지 확인합니다.'),
    ('기초와 심화', '공통 수업 밖에서 필요한 보충·심화 과제를 어떻게 받을지 확인합니다.', '쉬운 단원에 머무르지 않고, 도달 기준에 따라 다음 단계로 넘어가는지 확인합니다.'),
    ('학교 시험 연결', '학교별 시험 범위가 공통 수업과 다를 때 보완 방법을 확인합니다.', '학생별 계획이 학교 진도·시험 일정·평가 자료와 함께 조정되는지 확인합니다.'),
    ('주의할 점', '수업을 이해한 느낌과 혼자 풀 수 있는 상태가 다를 수 있습니다.', '교재만 다르게 배정하면 충분하지 않습니다. 진단과 피드백의 연결이 필요합니다.'),
]

def table(full=False):
    rows = ROWS if full else ROWS[:5]
    return '<div class="wb-table-wrap"><table class="wb-table"><caption>수업형식 비교표 · 실제 운영은 지점 상담에서 확인해 주세요.</caption><thead><tr><th scope="col">비교 기준</th><th scope="col">강의식 수업</th><th scope="col">개별 맞춤·무학년 수업</th></tr></thead><tbody>' + ''.join(
        '<tr><th scope="row">' + escape(a) + '</th><td>' + escape(b) + '</td><td>' + escape(c) + '</td></tr>' for a,b,c in rows
    ) + '</tbody></table></div>'

def card(n, title, text, path, label):
    return f'<article class="wb-card"><span class="wb-number">{n}</span><h3>{title}</h3><p>{text}</p>{actions([(path,label)])}</article>'

def photo(name, width, height, alt, caption):
    return f'<figure class="wb-figure"><img src="/assets/official-learning/{name}.webp" width="{width}" height="{height}" loading="lazy" decoding="async" alt="{alt}"><figcaption>{caption}</figcaption></figure>'

HOME = '''<section class="wb-section wu-wrap" id="class-comparison" aria-labelledby="home-comparison-title"><p class="wb-kicker">수업 선택의 기준</p><h2 id="home-comparison-title">같은 내용을 배워도,<br>필요한 도움은 다를 수 있습니다.</h2><p class="wb-lead">설명을 들으면 이해하는데 혼자 풀기 어렵나요? 학교 진도보다 앞선 문제를 풀고 싶나요? 강의식과 개별 맞춤 수업은 시작점과 피드백 방식이 다릅니다. 아이의 현재 상태와 실제 수업 운영을 함께 비교해 보세요.</p>''' + table() + '''<p class="wb-note">무학년 수업은 학년을 무시한다는 뜻이 아닙니다. 필요한 기초를 보완하면서 현재 학교 수업과 연결하는 방식입니다. ‘1:1 맞춤 코칭’도 항상 선생님과 학생 단둘이 수업한다는 뜻은 아니므로, 수업 인원과 개별 질문 시간을 함께 확인해 주세요.</p>''' + actions([('/overview/수업형식-비교/','상황별 선택 기준과 질문 보기',True),('/지점안내/','가까운 지점에서 수업 방식 확인')]) + '''</section>
<section class="wb-section wu-wrap" id="learning-process" aria-labelledby="home-process-title"><p class="wb-kicker">공부를 이어가는 과정</p><h2 id="home-process-title">학교 자료, 오늘의 과제,<br>다음 복습을 하나의 흐름으로.</h2><p class="wb-lead">와와학습코칭센터의 학습 진단·계획·지도 안내를 바탕으로, 학생과 학부모가 상담에서 살펴볼 과정을 정리했습니다. 공부량뿐 아니라 무엇을 이해했고 어디에서 멈췄는지 함께 확인하는 것이 출발점입니다.</p><div class="wb-grid">''' + card('01 · 학교 시험','시험 범위부터 확인하기','교과서와 학교 프린트, 평가 안내를 모아 지금 준비할 내용을 정합니다. 개념 설명·문제 풀이·서술형 답안을 나누어 확인해 보세요.','/overview/학교별-내신관리/','학교별 내신 준비 과정') + card('02 · 학습 습관','플래너에 확인 결과 남기기','‘수학 1시간’ 대신 오늘 풀 문제와 점검 방법을 씁니다. 못 끝낸 과제는 분량·시간·어려움을 나누어 다음 계획에 반영합니다.','/overview/플래너-학습관리/','플래너 기록 예시 보기') + card('03 · 현재 이해도','막힌 개념부터 다시 연결하기','학년표나 문제집 권수만으로 출발점을 정하지 않습니다. 혼자 설명하거나 풀 수 있는지 확인하고, 기초 보완과 학교 진도를 연결합니다.','/overview/수업형식-비교/#student-situations','우리 아이 상황별 점검') + '''</div><div class="wb-feature"><div><h3>질문할 수 있는 공부,<br>설명해 볼 수 있는 공부.</h3><p class="wb-lead">둥지형 학습은 선생님을 중심으로 여러 학생이 함께 배우며 질문과 피드백을 주고받는 형태로 안내됩니다. 학생별 계획을 따르더라도, 혼자 교재만 푸는 시간과 필요한 지도를 받는 시간을 구분해 확인해 보세요.</p>''' + actions([('/overview/','4C 코칭과 학습 관리 살펴보기'),('/선생님찾기/','지점별 선생님 안내')]) + '''</div>''' + photo('planner-coaching',555,555,'와와학습코칭센터 선생님과 학생이 학습 기록을 함께 확인하는 모습','와와학습코칭센터 브랜드 안내 이미지 · 수업 구성은 지점별 상담에서 확인해 주세요.') + '''</div></section>'''

def topic_cards(id, title, intro):
    return f'<section class="wb-section {"wb-guide" if id=="guide-academy-learning" else "wu-wrap"}" id="{id}" aria-labelledby="{id}-title"><p class="wb-kicker">학습과 수업을 연결하는 질문</p><h2 id="{id}-title">{title}</h2><p class="wb-lead">{intro}</p><div class="wb-grid">' + ''.join([
        card('수업 방식','아이에게 맞는 수업형식','강의식과 개별 맞춤 수업의 진도·피드백을 비교하고, 학생 상황별 질문을 준비하세요.','/overview/수업형식-비교/','수업형식 비교하기'),
        card('학교 시험','학교별 내신 준비','학교 자료와 시험 범위를 바탕으로 개념·문제·서술형·복습을 연결하는 예시를 확인하세요.','/overview/학교별-내신관리/','내신 준비 과정 보기'),
        card('공부 습관','계획이 실행으로 이어지는 플래너','구체적인 과제 기록과 실행 확인, 못 끝낸 과제를 조정하는 방법을 살펴보세요.','/overview/플래너-학습관리/','플래너 예시 보기'),
    ]) + '</div></section>'

FAQS = {
 '수업형식-비교': [
  ('개별 맞춤 수업이면 항상 선생님과 단둘이 수업하나요?', '학생별 진도와 피드백을 맞춘다는 의미이며, 반드시 선생님과 학생 단둘이 수업한다는 뜻은 아닙니다. 둥지형 학습에서는 여러 학생이 함께 배우는 형태도 안내됩니다. 실제 인원과 질문·설명 시간은 지점에서 확인해 주세요.'),
  ('무학년 수업을 하면 학교 진도를 놓치지 않을까요?', '기초를 보완하는 계획과 학교 수업·시험 준비를 함께 확인해야 합니다. 어떤 개념을 먼저 보완할지, 학교 과제와 시험 범위는 언제 다룰지, 다음 단계로 넘어가는 기준은 무엇인지 질문해 보세요.'),
  ('성적이 낮으면 개별 맞춤, 높으면 강의식이 맞나요?', '점수 하나만으로 정하기 어렵습니다. 틀린 원인, 설명을 듣는 방식, 혼자 복습하는 능력, 필요한 질문 시간을 함께 봐야 합니다. 수업 후 혼자 해결할 수 있는지 확인하는 과정도 중요합니다.'),
 ],
 '학교별-내신관리': [
  ('학교별 내신 준비를 위해 무엇을 가져가면 좋을까요?', '현재 교과서와 부교재, 학교 프린트, 시험 범위·평가 안내, 최근 시험지와 풀이 기록을 준비해 주세요. 자료가 아직 없다면 현재 진도와 어려운 단원부터 정리해 상담할 수 있습니다.'),
  ('수행평가도 학원에서 대신 준비해 주나요?', '수행평가의 제출 조건·평가 기준·기한을 확인하고 필요한 개념과 연습을 준비하는 방향으로 상담하세요. 과제와 제출물은 학생이 직접 작성해야 하며, 지점에서 도울 수 있는 범위는 별도로 확인해 주세요.'),
  ('기초가 부족해도 시험 범위를 먼저 공부해야 하나요?', '현재 시험 단원과 연결되는 선수 개념을 찾아 함께 보완하는 방법을 검토할 수 있습니다. 남은 시간과 학습량에 따라 우선순위를 정해야 하며, 모든 이전 단원을 끝내거나 문제를 많이 푸는 것만으로 결정하지 않습니다.'),
 ],
 '플래너-학습관리': [
  ('플래너는 매일 빈칸 없이 써야 효과가 있나요?', '빈칸을 채우는 것보다 계획과 실제 실행을 비교할 수 있는 기록이 중요합니다. 해야 할 과제, 완료 확인 방법, 어려웠던 점과 다음 행동을 간단히 남기는 것부터 시작해 보세요.'),
  ('계획한 공부를 못 끝내면 어떻게 해야 하나요?', '과제 분량이 많았는지, 시간이 부족했는지, 개념이 어려웠는지부터 나누어 봅니다. 원인에 맞춰 과제를 줄이거나 설명을 요청하고, 남은 과제를 다음 날 계획에 무조건 더하지 않도록 조정해 주세요.'),
  ('학부모는 무엇을 확인하면 좋을까요?', '공부 시간이나 체크 표시만 보기보다 아이가 혼자 설명할 수 있는 내용, 막힌 이유, 다음에 시도할 행동을 물어보세요. 지점과 공유하는 기록의 종류와 상담 방식은 실제 운영에 맞춰 확인해 주세요.'),
 ],
}

def faq(slug):
    return '<section class="wb-content" id="questions"><h2>학생·학부모가 자주 묻는 질문</h2>' + ''.join(f'<details class="wb-faq"><summary>{escape(q)}</summary><p>{escape(a)}</p></details>' for q,a in FAQS[slug]) + '</section>'

def related(items):
    return '<aside class="wb-related" aria-label="함께 볼 학습 정보"><h3>상담 전에 함께 살펴보세요.</h3><p class="wb-lead">공부 방법을 확인한 뒤, 가까운 지점에서 학생의 현재 과제와 필요한 도움을 이야기해 보세요.</p>' + actions(items+[('/지점안내/','가까운 지점 안내',True),('/선생님찾기/','지점별 선생님 안내')]) + '</aside>'

BODY_COMPARE = '''<section class="wb-content" id="comparison"><h2>수업형식은 무엇이 다를까요?</h2><p class="wb-lead">아래 표는 두 방식의 일반적인 차이를 정리한 선택 안내입니다. 한 수업 안에 공통 설명과 개별 지도가 함께 운영될 수 있으므로, 실제 시간 배분과 피드백 과정을 확인하는 데 활용해 주세요.</p>''' + table(True) + '''<p class="wb-note">어느 방식이 항상 더 낫다고 정할 수는 없습니다. 학생이 필요한 설명을 받고, 수업 뒤 혼자 해결할 수 있는지 확인할 기회가 있는지가 중요한 비교 기준입니다.</p></section>
<section class="wb-content" id="student-situations"><h2>우리 아이의 상황에서 질문을 시작해 보세요.</h2><div class="wb-grid">''' + card('상황 01','설명을 들으면 알겠는데 혼자 못 풀어요.','비슷한 문제를 다시 풀 때 어디에서 멈추는지 살펴보세요. 풀이 첫 단계, 개념 이해, 조건 해석 중 무엇을 도와주는지 질문해 보세요.','/guide/retrieval-spaced-review/','혼자 떠올려 보는 복습 방법') + card('상황 02','학교 진도는 나가는데 기초가 흔들려요.','현재 단원에 필요한 이전 개념을 좁혀 보세요. 기초 보완과 학교 과제를 어떻게 배분하고, 다시 확인하는지 상담에서 물어보세요.','/커리큘럼/','학년·과목별 확인 과제') + card('상황 03','빨리 끝내지만 왜 맞았는지 설명하기 어려워요.','풀이 속도만으로 다음 진도를 정하지 않도록 설명·응용 문제를 확인해 보세요. 심화 과제의 기준과 피드백 방식을 질문할 수 있습니다.','/guide/math-graphs/','표·식·그래프를 연결하는 연습') + '''</div></section>
<section class="wb-content" id="coaching-flow"><h2>개별 맞춤은 진단·과제·재확인이 연결되어야 합니다.</h2><ol class="wb-steps"><li><h3>현재 상태를 확인합니다.</h3><p>최근 시험지와 실제 풀이를 보며 아는 부분, 설명이 필요한 부분, 반복해서 틀리는 부분을 나눕니다. 학년이나 총점뿐 아니라 문제를 해결하는 과정을 살펴봅니다.</p></li><li><h3>확인한 이유에 맞춰 과제를 정합니다.</h3><p>예를 들어 분수 계산에서 자주 막힌다면, 지금 배우는 식의 계산과 연결되는 분수 개념부터 점검할 수 있습니다. 이는 학습 계획의 예시이며 실제 출발점은 학생별 진단에 따라 달라집니다.</p></li><li><h3>질문과 설명을 주고받습니다.</h3><p>교재를 혼자 푸는 것만으로 개별 코칭이 완성되지는 않습니다. 왜 그렇게 풀었는지 설명하고, 선생님의 도움을 받은 뒤 스스로 다시 시도할 기회가 필요합니다.</p></li><li><h3>다음 학습의 기준을 확인합니다.</h3><p>정답을 본 직후 맞힌 결과와 며칠 뒤 혼자 해결한 결과를 구분해 봅니다. 이해한 내용을 학교 과제나 다른 문제에도 적용할 수 있는지 확인하며 다음 단원을 정합니다.</p></li></ol></section>
<section class="wb-content" id="consult-check"><h2>상담에서는 수업 이름보다 운영 과정을 확인하세요.</h2><ul class="wb-list"><li>현재 단원과 부족한 선수 개념을 어떤 자료로 진단하나요?</li><li>한 수업에서 설명·개별 과제·질문·오답 확인은 어떻게 이루어지나요?</li><li>여러 학생이 함께 배우는 경우 학생별 질문 시간은 어떻게 확보하나요?</li><li>학교 진도와 시험 범위가 다를 때 과제를 어떻게 조정하나요?</li><li>기초 보완을 끝내고 다음 단계로 넘어가는 기준은 무엇인가요?</li><li>수업 뒤 학생·학부모가 확인할 수 있는 기록은 무엇인가요?</li></ul><p class="wb-note">최근 교재와 시험지, 어려웠던 문제 두세 개를 가져가면 질문을 구체화하기 좋습니다. 지점별 지도 과목, 수업 인원, 시간표와 프로그램 운영은 상담에서 확인해 주세요.</p></section>''' + faq('수업형식-비교') + related([('/overview/학교별-내신관리/','학교 시험과 학습 계획 연결'),('/overview/플래너-학습관리/','플래너 실행 기록 보기')])

BODY_SCHOOL = '''<section class="wb-content" id="school-materials"><h2>학교별 내신 준비는 같은 학년이어도 출발 자료가 다릅니다.</h2><div class="wb-feature"><div><p class="wb-lead">시험을 준비할 때는 학교에서 안내한 범위와 수업 자료를 먼저 확인해 보세요. 같은 학년이라도 사용하는 교과서·부교재·프린트와 평가 일정이 다를 수 있습니다. 익숙한 문제집 순서만 따라가기보다 실제 평가 범위와 현재 이해도를 연결하는 것이 중요합니다.</p><ul class="wb-list"><li><strong>범위:</strong> 시험 범위 공지와 현재 수업 진도</li><li><strong>자료:</strong> 교과서, 부교재, 학교 프린트와 필기</li><li><strong>평가:</strong> 서술형·수행평가의 요구 조건과 제출 일정</li><li><strong>현재 상태:</strong> 최근 시험지, 미완료 과제, 설명하기 어려운 개념</li></ul></div>''' + photo('school-preparation',558,377,'와와학습코칭센터의 학교별 내신 자료와 학습 계획 기록 예시','브랜드 안내 이미지 · 학교 자료를 활용하는 방법과 준비 범위는 지점별로 확인해 주세요.') + '''</div><p class="wb-note">학교 평가 안내와 선생님의 지시를 우선 확인하세요. 공개된 자료와 학생이 받은 수업 자료를 바탕으로 준비하며, 출제 문제나 성적을 보장하는 안내는 아닙니다.</p></section>
<section class="wb-content" id="preparation-flow"><h2>개념·문제·답안·복습을 나누어 점검하세요.</h2><ol class="wb-steps"><li><h3>시험 범위를 작은 과제로 나눕니다.</h3><p>‘수학 시험 공부’ 대신 ‘이차방정식 풀이 과정을 설명하기’, ‘학교 프린트에서 막힌 문제 다시 풀기’처럼 확인할 수 있는 과제로 정합니다. 학교 자료와 교재의 연결되는 부분도 표시해 보세요.</p></li><li><h3>틀린 원인을 구분합니다.</h3><p>개념을 몰랐는지, 문제 조건을 놓쳤는지, 계산·표현에서 실수했는지 나눕니다. 개념이 부족하면 설명과 간단한 적용부터, 조건 해석이 어려우면 읽기와 표현 연습부터 준비할 수 있습니다.</p></li><li><h3>서술형은 요구 조건에 맞춰 씁니다.</h3><p>정답뿐 아니라 풀이 근거, 설명해야 할 개념, 필요한 단위·표현이 있는지 확인합니다. 국어는 질문과 근거, 영어는 문장 구조와 표현, 수학은 풀이 단계와 조건처럼 과목에 맞는 점검이 필요합니다.</p></li><li><h3>시간을 두고 다시 확인합니다.</h3><p>해설을 읽은 문제는 잠시 뒤 책을 덮고 다시 풀거나 설명해 봅니다. 한 번 맞혔다고 끝내기보다 혼자 해결한 결과를 플래너에 남겨 다음 복습 과제를 정합니다.</p></li></ol>''' + actions([('/guide/korean-written-answer/','국어 서술형 답안 연습'),('/guide/english-sentence-structure/','영어 문장 구조 점검'),('/overview/플래너-학습관리/','확인 결과 기록하기')]) + '''</section>
<section class="wb-content" id="exam-schedule"><h2>남은 기간에서 거꾸로 계획하는 예시</h2><p class="wb-lead">다음은 시험까지 약 3~4주가 남았을 때의 예시입니다. 학교 시험 일정, 현재 진도와 하루에 가능한 공부 시간에 맞춰 순서와 분량을 조정해 주세요. 모든 지점에 적용되는 고정 운영표는 아닙니다.</p><div class="wb-table-wrap"><table class="wb-table"><caption>시험 준비 일정 예시 · 기간보다 확인할 과제가 중요합니다.</caption><thead><tr><th scope="col">시점</th><th scope="col">준비할 과제</th><th scope="col">확인할 결과</th></tr></thead><tbody><tr><th scope="row">3~4주 전</th><td>범위·학교 자료를 모으고, 이해가 부족한 개념을 표시합니다.</td><td>어떤 단원을 설명하거나 풀기 어려운지 목록으로 남깁니다.</td></tr><tr><th scope="row">약 2주 전</th><td>학교 자료와 연결되는 문제를 풀고 서술형 답안을 연습합니다.</td><td>틀린 원인과 다시 연습할 과제를 구분합니다.</td></tr><tr><th scope="row">약 1주 전</th><td>취약 과제를 다시 풀고, 필요한 풀이·표현을 시간 안에 정리합니다.</td><td>해설 없이 해결했는지와 아직 필요한 도움을 확인합니다.</td></tr><tr><th scope="row">직전·시험 후</th><td>새 자료를 과하게 늘리지 않고 핵심 내용을 확인합니다. 시험 후 풀이를 돌아봅니다.</td><td>남은 공백과 다음 단원에 이어질 복습 과제를 정합니다.</td></tr></tbody></table></div></section>
<section class="wb-content" id="consult-check"><h2>내신 상담에서 함께 확인할 질문</h2><ul class="wb-list"><li>우리 학교의 교과서·프린트·평가 안내는 어떤 방식으로 학습 계획에 반영하나요?</li><li>현재 시험 단원과 연결된 기초가 부족할 때 무엇부터 보완하나요?</li><li>틀린 원인을 구분하고 다시 푸는 기록을 어떻게 확인하나요?</li><li>서술형 답안의 근거와 표현은 어떻게 점검하나요?</li><li>수행평가 준비에서 지도할 수 있는 범위와 학생이 직접 해야 할 부분은 무엇인가요?</li><li>시험 이후에도 남은 공백을 다음 학습으로 연결하나요?</li></ul><p class="wb-note">시험 일정과 최근 과제, 하루에 가능한 공부 시간을 함께 알려 주세요. 지점별 지도 과목과 학교 자료 활용 범위, 상담·피드백 방식은 실제 운영에 따라 확인이 필요합니다.</p></section>''' + faq('학교별-내신관리') + related([('/커리큘럼/학교별-학습계획/','학교 진도와 커리큘럼 연결'),('/guide/','과목별 학습가이드 찾기')])

BODY_PLANNER = '''<section class="wb-content" id="record-method"><h2>플래너의 역할은 공부 시간을 채우는 것보다 구체적입니다.</h2><div class="wb-feature"><div><p class="wb-lead">계획을 세웠는데 과제가 계속 남는다면, 공부 시간을 늘리기 전에 기록을 살펴보세요. 플래너는 무엇을 할지 정하고, 실제로 해 본 결과와 막힌 이유를 남겨 다음 행동을 바꾸는 도구로 사용할 수 있습니다.</p><ul class="wb-list"><li><strong>계획:</strong> 오늘 할 과제와 사용할 자료를 정합니다.</li><li><strong>확인:</strong> 무엇을 혼자 해결했는지 남깁니다.</li><li><strong>피드백:</strong> 시간이 부족했는지, 내용이 어려웠는지 구분합니다.</li><li><strong>조정:</strong> 필요한 설명·재연습·분량 변경을 다음 계획에 반영합니다.</li></ul></div>''' + photo('planner-coaching',555,555,'와와학습코칭센터 선생님과 학생이 플래너 학습 기록을 함께 확인하는 모습','브랜드 플래너 안내 이미지 · 기록과 공유 방식은 지점별로 확인해 주세요.') + '''</div></section>
<section class="wb-content" id="planner-example"><h2>‘공부했다’에서 ‘확인했다’로 바꾸는 기록 예시</h2><p class="wb-lead">다음 표는 기록 방법을 설명하는 가상 예시입니다. 실제 학년·교재·문제 수는 학생에게 맞춰 정하고, 기록이 부담스러우면 한 과제부터 시작해 보세요.</p><div class="wb-table-wrap"><table class="wb-table"><caption>플래너 작성 예시 · 과제와 완료 확인을 함께 기록하기</caption><thead><tr><th scope="col">과목</th><th scope="col">오늘 할 과제</th><th scope="col">확인 결과와 다음 행동</th></tr></thead><tbody><tr><th scope="row">수학</th><td>현재 단원의 틀린 문제 두 개를 해설 없이 다시 풀고, 첫 풀이 단계를 설명합니다.</td><td>한 문제는 혼자 해결했습니다. 다른 문제는 조건 해석을 질문한 뒤 다음 날 다시 확인합니다.</td></tr><tr><th scope="row">영어</th><td>학교 지문에서 막힌 문장 세 개의 주어·동사와 수식 부분을 나누어 읽습니다.</td><td>두 문장은 설명했습니다. 남은 문장은 문장 구조 설명을 듣고 새 예문에도 적용해 봅니다.</td></tr><tr><th scope="row">국어</th><td>서술형 질문 한 개에 답하고, 답을 뒷받침하는 본문 근거를 표시합니다.</td><td>근거는 찾았지만 질문의 조건 한 가지를 빠뜨렸습니다. 답안을 고쳐 다시 설명합니다.</td></tr></tbody></table></div><p class="wb-note">위 예시의 문제 수와 분량은 권장 최소량이나 학원 숙제 기준이 아닙니다. 핵심은 실제로 가능한 과제를 정하고, 도움 없이 확인한 결과를 남기는 것입니다.</p></section>
<section class="wb-content" id="unfinished-work"><h2>계획을 못 끝냈다면 원인별로 다르게 조정합니다.</h2><div class="wb-grid"><article class="wb-card"><span class="wb-number">분량 문제</span><h3>할 일이 너무 많았어요.</h3><p>학교 과제·등원·쉬는 시간을 포함해 가능한 시간을 다시 확인합니다. 지금 필요한 핵심 과제를 남기고, 나머지는 일정에 다시 배분해 보세요.</p></article><article class="wb-card"><span class="wb-number">이해 문제</span><h3>어려워서 계속 멈췄어요.</h3><p>멈춘 문제나 문장을 표시하고 필요한 설명을 요청합니다. 같은 과제를 더 오래 시키기보다 선수 개념과 더 작은 연습을 연결해 보세요.</p></article><article class="wb-card"><span class="wb-number">실행 문제</span><h3>시작하지 못했어요.</h3><p>시작 시각과 장소, 첫 행동을 작게 정합니다. 예를 들어 교재와 필기를 펴고 어제 표시한 문제 하나를 확인하는 단계부터 시도할 수 있습니다.</p></article></div>''' + actions([('/guide/learning-workload/','남는 과제 조정하는 방법'),('/guide/retrieval-spaced-review/','책을 덮고 다시 확인하기')]) + '''</section>
<section class="wb-content" id="parent-conversation"><h2>학생·학부모·선생님이 같은 기록을 보고 대화하세요.</h2><ol class="wb-steps"><li><h3>학생은 계획과 실제 결과를 비교합니다.</h3><p>계획을 지킨 날만 표시하기보다 혼자 해결한 내용과 도움을 받은 내용을 구분합니다. 다음에 필요한 행동을 학생이 말해 볼 수 있도록 해 주세요.</p></li><li><h3>학부모는 확인 질문을 바꿔 봅니다.</h3><p>‘몇 시간 했니?’와 함께 ‘오늘 혼자 설명할 수 있는 건 뭐야?’, ‘어디에서 막혔어?’, ‘다음에는 무엇을 해 볼까?’를 물어보세요. 매일 모든 기록을 검사하기보다 아이가 도움을 요청할 내용을 함께 정리합니다.</p></li><li><h3>상담에서는 기록을 활용하는 방식을 확인합니다.</h3><p>어떤 항목을 기록하고 누가 확인하는지, 미완료 과제를 어떻게 조정하는지, 학부모와 어떤 내용을 공유하는지 물어보세요. 공유 주기와 전달 방식은 지점별 운영을 확인해야 합니다.</p></li></ol></section>
<section class="wb-content" id="consult-check"><h2>플래너 관리 상담 체크리스트</h2><ul class="wb-list"><li>학생이 과제를 정하는 데 어느 정도 참여하나요?</li><li>완료 표시는 시간·분량·이해도 중 무엇을 기준으로 확인하나요?</li><li>못 끝낸 이유를 어떻게 구분하고 다음 계획을 조정하나요?</li><li>오답과 학교 시험 준비가 플래너에 어떻게 연결되나요?</li><li>기록에 부담을 느끼는 학생에게 분량이나 형식을 조정할 수 있나요?</li><li>학생·학부모가 받을 수 있는 피드백과 공유 방식은 무엇인가요?</li></ul></section>''' + faq('플래너-학습관리') + related([('/overview/학교별-내신관리/','시험 준비 일정 예시'),('/guide/','다른 공부 습관 가이드')])

BODIES = [BODY_COMPARE, BODY_SCHOOL, BODY_PLANNER]
SUMMARIES = [
 '강의식은 공통 설명과 진도를, 개별 맞춤은 현재 이해도에 따른 과제와 피드백을 중심으로 살펴볼 수 있습니다. 성적이나 수업 이름만으로 정하지 않고, 필요한 설명·질문·혼자 확인할 기회를 비교해 보세요.',
 '학교별 내신 준비는 시험 범위와 수업 자료를 먼저 확인하고, 현재 이해도에 맞춰 개념·문제·서술형·오답 복습을 연결하는 과정입니다. 학생의 학교 자료와 실제 풀이를 함께 보며 상담 질문을 준비하세요.',
 '플래너는 오늘 할 과제, 혼자 확인한 결과, 막힌 이유와 다음 행동을 연결하는 기록입니다. 시간과 체크 표시만 남기기보다 실행 결과를 보고 과제 분량과 공부 방법을 조정하는 데 활용해 보세요.',
]
TOCS = [
 [('comparison','비교표'),('student-situations','상황별 질문'),('coaching-flow','코칭 과정'),('consult-check','상담 체크리스트'),('questions','자주 묻는 질문')],
 [('school-materials','준비할 자료'),('preparation-flow','준비 과정'),('exam-schedule','일정 예시'),('consult-check','상담 체크리스트'),('questions','자주 묻는 질문')],
 [('record-method','기록 방법'),('planner-example','작성 예시'),('unfinished-work','미완료 과제'),('parent-conversation','함께 대화하기'),('questions','자주 묻는 질문')],
]

def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value,encoding='utf-8',newline='\n')

def module(source, marker, content, before):
    block = f'<!-- {marker}:start -->\n{content}\n<!-- {marker}:end -->'
    pattern = rf'<!-- {re.escape(marker)}:start -->.*?<!-- {re.escape(marker)}:end -->'
    if re.search(pattern,source,re.S): return re.sub(pattern,lambda _:block,source,flags=re.S)
    assert source.count(before)==1, (marker,before)
    return source.replace(before,block+'\n'+before,1)

def style(source):
    tag = '<link rel="stylesheet" href="/assets/brand-learning.css?v=20261003">'
    return source if tag in source else source.replace('</head>',tag+'\n</head>',1)

overview=(ROOT/'overview/index.html').read_text(encoding='utf-8')
home=(ROOT/'index.html').read_text(encoding='utf-8')
head = overview.split('</head>')[0]+'</head>'
head = re.sub(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>', '', head, flags=re.S)
head = head.replace('../assets/','/assets/')
shell = re.search(r'<body\b.*?<main\b[^>]*>',overview,re.S).group()
shell = shell.replace('aria-current="page"','aria-current="location"')
footer = home.split('</main>',1)[1]
changed = []
seo = json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8'))
for i,(slug,title,description) in enumerate(PAGES):
    path='/overview/'+slug+'/'
    url=ORIGIN+quote(path)
    newhead=re.sub(r'<title>.*?</title>',f'<title>{title} | 와와학습코칭센터</title>',head,flags=re.S)
    for name, value in [('description',description),('og:description',description),('twitter:description',description),('og:title',title+' | 와와학습코칭센터'),('og:url',url)]:
        pattern=rf'(<meta\b[^>]*(?:name|property)=["\']{re.escape(name)}["\'][^>]*content=["\'])[^"\']*(["\'][^>]*>)'
        newhead,n=re.subn(pattern,lambda m:m[1]+escape(value,quote=True)+m[2],newhead)
        if not n:newhead=newhead.replace('</head>',f'<meta name="{name}" content="{escape(value,quote=True)}">\n</head>')
    newhead=re.sub(r'(<link rel="canonical" href=")[^"]+("[^>]*>)',lambda m:m[1]+url+m[2],newhead)
    schema={'@context':'https://schema.org','@graph':[
      {'@type':'WebPage','@id':url+'#webpage','url':url,'name':title,'description':description,'inLanguage':'ko-KR','dateModified':DATE,'isPartOf':{'@id':ORIGIN+'/#website'}},
      {'@type':'BreadcrumbList','@id':url+'#breadcrumb','itemListElement':[{'@type':'ListItem','position':1,'name':'홈','item':ORIGIN+'/'},{'@type':'ListItem','position':2,'name':'학원소개','item':ORIGIN+'/overview/'},{'@type':'ListItem','position':3,'name':title,'item':url}]},
      {'@type':'FAQPage','@id':url+'#faq','mainEntity':[{'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a in FAQS[slug]]},
    ]}
    newhead=newhead.replace('</head>','<script type="application/ld+json">'+json.dumps(schema,ensure_ascii=False,separators=(',',':'))+'</script>\n</head>')
    toc='<nav class="wb-toc" aria-label="이 페이지 내용">'+''.join(f'<a href="#{anchor}">{label}</a>' for anchor,label in TOCS[i])+'</nav>'
    intro=f'<section class="wb-intro"><nav class="wb-breadcrumb" aria-label="현재 위치"><a href="/">홈</a><span aria-hidden="true">/</span><a href="/overview/">학원소개</a><span aria-hidden="true">/</span><span aria-current="page">{title.split(",")[0]}</span></nav><p class="wb-kicker">와와학습코칭센터 · 학습 과정 안내</p><h1>{title}</h1><p class="wb-summary">{SUMMARIES[i]}</p>{toc}</section>'
    source='<p class="wb-source">와와학습코칭센터의 <a href="https://www.wawacenter.com/" target="_blank" rel="noopener">브랜드 안내</a>를 바탕으로 학생·학부모의 확인 질문과 예시를 정리했습니다. 지점별 과목·수업 방식·프로그램 운영은 해당 지점에 확인해 주세요.</p>'
    page=style(newhead)+ '\n'+shell+'<article class="wb-section wu-wrap">'+intro+BODIES[i]+source+'</article></main>'+footer
    page=re.sub(r'[ \t]+\n','\n',page)
    name='overview/'+slug+'/index.html';write(ROOT/name,page);changed.append(name)
    seo['pages'][path.rstrip('/')]={'description':description,'sources':[description]}

home=module(home,'brand-learning',HOME,'<section class="wu-band" id="learning-space"')
if 'href="#class-comparison"' not in home:
    home=home.replace('<a href="#academy">','<a href="#class-comparison">수업형식 비교</a><a href="#learning-process">학교·플래너 관리</a><a href="#academy">',1)
write(ROOT/'index.html',style(home));changed.append('index.html')
overview=module(overview,'brand-learning',topic_cards('overview-learning','우리 아이의 공부, 무엇부터 확인할까요?','4C 학습코칭 안내와 함께, 실제 수업 방식·학교 시험 준비·플래너 기록을 확인할 질문을 살펴보세요.'),'<section class="wu-section wu-wrap" id="four-c"')
if 'href="#overview-learning"' not in overview: overview=overview.replace('<a href="#four-c">','<a href="#overview-learning">수업·학습 과정</a><a href="#four-c">',1)
write(ROOT/'overview/index.html',style(overview));changed.append('overview/index.html')
guide=(ROOT/'guide/index.html').read_text(encoding='utf-8')
guide=module(guide,'brand-learning',topic_cards('guide-academy-learning','공부법을 확인했다면, 수업과 상담으로 이어가세요.','학습가이드에서 찾은 어려움을 수업 선택, 학교 시험 준비와 플래너 관리 질문으로 연결해 보세요.'),'<section class="lg-container lg-hub-section lg-howto"')
write(ROOT/'guide/index.html',style(guide));changed.append('guide/index.html')
write(ROOT/'seo-descriptions.json',json.dumps(seo,ensure_ascii=False,indent=2)+'\n')

sitemap=(ROOT/'sitemap.xml').read_text(encoding='utf-8')
for slug,_,_ in PAGES:
    url=ORIGIN+quote('/overview/'+slug+'/')
    if f'<loc>{url}</loc>' not in sitemap:
        sitemap=sitemap.replace('</urlset>',f'<url><loc>{url}</loc><lastmod>{DATE}</lastmod></url>\n</urlset>')
write(ROOT/'sitemap.xml',sitemap);changed.append('sitemap.xml')
llms=(ROOT/'llms.txt').read_text(encoding='utf-8')
block='## 수업과 학습 과정 안내\n\n'+ '\n'.join(f'- {title}: {ORIGIN}/overview/{slug}/' for slug,title,_ in PAGES)
if '## 수업과 학습 과정 안내' in llms: llms=llms.split('## 수업과 학습 과정 안내')[0].rstrip()+'\n\n'+block+'\n'
else: llms=llms.rstrip()+'\n\n'+block+'\n'
write(ROOT/'llms.txt',llms);changed.append('llms.txt')
changed += ['assets/brand-learning.css','assets/official-learning/school-preparation.webp','assets/official-learning/planner-coaching.webp']
manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8'))
for name in changed:
    raw=(ROOT/name).read_bytes();manifest['files'][name]=hashlib.sha256(raw).hexdigest()
    if name.endswith(('.html','.css','.xml','.txt')):manifest.setdefault('textSha256',{})[name]=hashlib.sha256(raw.decode('utf-8').replace('\r\n','\n').encode('utf-8')).hexdigest()
manifest['sitemapPages']=len(ET.fromstring(sitemap).findall('{*}url'))
manifest['updatedDate']=DATE
write(ROOT/'release-public-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'changedPublicFiles':changed,'newPages':len(PAGES),'publicFiles':len(manifest['files']),'sitemapPages':manifest['sitemapPages']},ensure_ascii=False))
