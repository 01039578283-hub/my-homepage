"""Create curriculum reference pages and add reversible contextual links to local pages."""
from __future__ import annotations
import argparse,hashlib,html as H,json,re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote,unquote,urlparse
from lxml import etree
from build_useful_info import places,footer,TRACKER

ROOT=Path(__file__).resolve().parents[1]
BASE='https://wawa-center.kr'; DATE='2026-10-03'; VERSION='20261003-curriculum'
DATA=json.loads((ROOT/'tools/curriculum-content.json').read_text(encoding='utf-8'))
GRADES={g['grade']:g for g in DATA['grades']}
STAGES={'초등':('초등학생','초등학교'),'중등':('중학생','중학교'),'고등':('고등학생','고등학교')}
SUBJECTS=['국어','영어','수학','사회','과학','역사']
CATALOG=[];CHANGED={}
STYLE=f'<link rel="stylesheet" href="/assets/curriculum.css?v={VERSION}" data-curriculum-links-style>'
START='<!-- curriculum-links:start -->';END='<!-- curriculum-links:end -->'

def esc(value):return H.escape(str(value),quote=True)
def href(path):return '/'+quote(path.strip('/'),safe='/-')+'/' if path.strip('/') else '/'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stage_for(grade):return {'초':'초등','중':'중등','고':'고등'}[grade[0]]
def grade_title(grade):return f'{STAGES[stage_for(grade)][1]} {grade[1]}학년'
def grade_path(grade):return '커리큘럼/'+grade
def subject_path(row):return grade_path(row['grade'])+'/'+row['subject']
def label(row):
    if row['grade'] in ['초1','초2']:
        if row['subject']=='영어':return row['grade']+' 영어 선택 활동'
        if row['subject'] in ['사회','과학']:return row['grade']+' '+row['subject']+' 연계 활동'
    return row['grade']+' '+row['subject']
def save(name,content):
    raw=content if isinstance(content,bytes) else content.replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('utf-8')
    target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists() or target.read_bytes()!=raw:target.write_bytes(raw)
    CHANGED[name]={'raw':sha(raw),'text':sha(raw.replace(b'\r\n',b'\n'))}
def buttons(items):return '<div class="ui-buttons">'+''.join(f'<a href="{href(p)}">{esc(t)} →</a>' for t,p in items)+'</div>'
def section(id,title,body):return f'<section class="cu-section" id="{esc(id)}"><h2>{esc(title)}</h2>{body}</section>'
def sequence(text):return '<ol class="cu-flow">'+''.join('<li>'+esc(s.strip())+'</li>' for s in text.split('→'))+'</ol>'
def note(body):return '<aside class="cu-note">'+body+'</aside>'
def curriculum_note(grade=None):
    if grade:
        revision=GRADES[grade]['revision']
        text=f'2026학년도 {grade_title(grade)}에는 {revision} 교육과정을 적용합니다.'
        if grade in ['중3','고3']:text+=' 2027학년도 같은 학년에는 2022 개정 교육과정이 적용되므로 내년 계획과 구분해 보세요.'
    else:text='2026학년도에는 초1~6·중1~2·고1~2에 2022 개정 교육과정, 중3·고3에 2015 개정 교육과정이 적용됩니다.'
    return note('<strong>2026학년도 기준으로 확인하세요</strong><p>'+esc(text)+'</p><p>학습 순서와 과제는 공부 계획을 세우는 참고 예시입니다. 실제 교과서·학기 진도·평가 범위와 맞춰 사용하세요.</p>')
def refs(rows=None,books=False):
    refs={}
    for row in rows or []:
        url=row['source'];name='교육부 · 2015 개정 교육과정' if '60747' in url else '교육부 · 2022 개정 교육과정'
        if 'ebs' in url.lower():name='EBS · 교재·과목 학습 참고 자료'
        refs[url]=name
    if not refs:refs[DATA['grades'][0]['source']]='교육부 · 2022 개정 교육과정과 학년별 시행 일정'
    if books:
        for row in books:refs[row['source']]='EBS · 교재·과목 학습 참고 자료'
    return '<section class="cu-refs" id="cu-sources"><h2>내용을 확인할 수 있는 자료</h2><p>학습 내용의 기준 자료와 교재 정보입니다. 학교별 세부 계획은 학교 안내로 확인하세요. 자료 확인: 2026년 10월 3일.</p><ul>'+''.join(f'<li><a href="{esc(url)}">{esc(name)}</a></li>' for url,name in refs.items())+'</ul></section>'
def shell(path,title,description,body,header,crumbs=None,collection=False,items=None):
    assert len(description)<=80 and description.endswith('.'),(path,description)
    canonical=BASE+href(path)
    crumbs=[('홈',''),('커리큘럼','커리큘럼')]+(crumbs or [])
    if path=='커리큘럼':crumbs=crumbs[:2]
    elif not crumbs or crumbs[-1][1]!=path:crumbs.append((title,path))
    page={'@type':'CollectionPage' if collection else 'Article','@id':canonical+'#page','url':canonical,'name':title,'description':description,'inLanguage':'ko-KR','dateModified':DATE}
    if not collection:page.update(headline=title,datePublished=DATE,author={'@type':'Organization','name':'와와학습코칭센터','url':BASE+'/'})
    graph=[page,{'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':i+1,'name':t,'item':BASE+href(p)} for i,(t,p) in enumerate(crumbs)]}]
    if items:graph.append({'@type':'ItemList','numberOfItems':len(items),'itemListElement':[{'@type':'ListItem','position':i+1,'name':t,'url':BASE+href(p)} for i,(t,p) in enumerate(items)]})
    jsonld=json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False).replace('<','\\u003c')
    head=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} | 와와학습코칭센터</title><meta name="description" content="{esc(description)}"><meta name="robots" content="index, follow"><link rel="canonical" href="{canonical}"><meta property="og:type" content="{'website' if collection else 'article'}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{canonical}"><meta property="og:site_name" content="와와학습코칭센터"><meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(description)}"><link rel="stylesheet" href="/assets/header.css?v=20261002-useful"><link rel="stylesheet" href="/assets/useful-info.css?v=20261002-useful"><link rel="stylesheet" href="/assets/curriculum.css?v={VERSION}"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&family=Noto+Serif+KR:wght@500;700&display=swap" rel="stylesheet"><script defer src="/assets/useful-info.js?v=20261002-useful"></script><script defer src="/assets/curriculum.js?v={VERSION}"></script><script type="application/ld+json">{jsonld}</script>{TRACKER}</head><body class="ui-page cu-page"><a class="ui-skip" href="#main-content">본문으로 건너뛰기</a>'''
    trail='<nav class="ui-crumb" aria-label="현재 위치">'+' <span aria-hidden="true">/</span> '.join(f'<a href="{href(p)}">{esc(t)}</a>' if p!=path else f'<span aria-current="page">{esc(t)}</span>' for t,p in crumbs)+'</nav>'
    lead='<header class="ui-hero"><p class="cu-eyebrow">CURRICULUM · 2026</p><h1>'+esc(title)+'</h1><p class="ui-lead">'+esc(description)+'</p><p class="ui-meta">학습 참고 기준: 2026학년도 · 초등·중등·고등</p></header>'
    final=head+header+'<main id="main-content"><div class="ui-wrap">'+trail+lead+body+'</div></main>'+footer().replace('<a href="/유용한정보/">','<a href="/커리큘럼/">커리큘럼</a><a href="/유용한정보/">',1)
    save(path+'/index.html',final)
    CATALOG.append(dict(path=path,title=title,description=description,collection=collection))

def subject_card(row):
    stage=stage_for(row['grade'])
    return f'<article class="cu-card" data-cu-card data-stage="{stage}" data-grade="{row["grade"]}" data-subject="{row["subject"]}"><span class="cu-tag">{row["revision"]} · 2026</span><h3><a href="{href(subject_path(row))}">{esc(label(row))}</a></h3><p>{esc(row["focus"])}</p><small>{esc(row["scope"])}</small><a href="{href(subject_path(row))}">학습 내용과 공부 방법 보기 →</a></article>'
def grade_card(grade):
    row=GRADES[grade]
    return '<article class="cu-grade"><span class="cu-tag">'+esc(row['revision'])+'</span><h3><a href="'+href(grade_path(grade))+'">'+esc(grade_title(grade))+'</a></h3><p>'+esc(row['focus'])+'</p><small>'+esc(row['subjects'])+'</small><a href="'+href(grade_path(grade))+'">'+grade+' 커리큘럼 살펴보기 →</a></article>'
def parent_help(row):
    questions={
     '국어':['글에서 답의 근거가 되는 문장이나 표현은 어디인가요?','학생이 읽은 내용을 자기 말로 설명할 수 있나요?','글을 쓴 목적에 맞춰 표현을 고칠 부분은 무엇인가요?'],
     '영어':['소리나 문장의 뜻을 어떤 단서로 알았나요?','배운 표현을 다른 상황에서도 말하거나 쓸 수 있나요?','모르는 낱말과 이해되지 않는 문장 구조를 구분했나요?'],
     '수학':['그 식이나 그림은 어떤 관계를 나타내나요?','계산 전에 조건과 단위를 확인했나요?','답을 바꿔 넣거나 다른 방법으로 확인할 수 있나요?'],
     '사회':['지도·사진·통계가 직접 알려 주는 사실은 무엇인가요?','설명에 사용한 개념과 자료의 시점이 맞나요?','다른 관점에서 살펴볼 점은 무엇인가요?'],
     '과학':['관찰한 사실과 예상한 내용을 구별했나요?','비교할 조건과 같게 둘 조건은 무엇인가요?','그 결과로 설명할 수 있는 범위는 어디까지인가요?'],
     '역사':['사료의 시기와 작성한 사람은 누구인가요?','사건의 앞뒤 흐름과 원인을 자료로 설명할 수 있나요?','자료에 적힌 사실과 학생의 해석을 구별했나요?'],
    }[row['subject']]
    if row['grade'] in ['초1','초2'] and row['subject']=='영어':questions=['노래나 그림 활동에 학생이 편안하게 참여하나요?','어떤 소리나 표현에 관심을 보였나요?','원하지 않을 때 활동을 줄이거나 쉬어 갈 수 있나요?']
    return '<p>정답을 대신 알려 주기 전에 학생이 어디까지 혼자 했는지 들어 보세요. 아래 질문 중 과제에 맞는 것을 골라 묻고, 필요한 도움을 한 가지씩 정해 봅니다.</p><ul class="cu-checks">'+''.join('<li>'+esc(q)+'</li>' for q in questions)+'</ul><p>예시 과제: <strong>'+esc(row['task'])+'</strong></p><p>학생의 말이나 풀이에서 확인한 부분과 아직 설명하지 못한 부분을 따로 기록하면 다음 연습을 정하는 데 도움이 됩니다.</p>'
def level_records(row):
    if row['grade'] in ['초1','초2'] and row['subject'] in ['영어','사회','과학']:return []
    # The supplied social-studies rows explicitly cover history source/chronology work.
    subject='사회' if row['subject']=='역사' else row['subject']
    return [r for r in DATA['levels'] if r['stage']==GRADES[row['grade']]['stage'] and r['subject']==subject]
def level_cards(rows):
    out='<div class="cu-level-grid">'
    for row in rows:
        name=row['level'].removesuffix('반')
        steps='<ol>'+''.join('<li>'+esc(t.strip())+'</li>' for t in row['sequence'].split('→'))+'</ol>'
        out+='<article class="cu-level"><span class="cu-tag">학습 방법 참고</span><h3>'+esc(name)+'</h3><p>'+esc(row['forWhom'])+'</p><h4>어떤 순서로 공부할까요?</h4>'+steps+'<h4>이렇게 확인해 보세요</h4><p>'+esc(row['task'])+'</p><h4>다음 단계로 넘어갈 때</h4><p>'+esc(row['next'])+'</p><h4>교재·자료 후보</h4><p>'+esc(row['materials'])+'</p></article>'
    return out+'</div>'
def school_check(grade):
    g=GRADES[grade]
    checks=['학교·학년·학기와 교과서의 출판사·저자·단원 순서를 확인하세요.',g['schoolCheck'],'최근 과제나 답안을 펼쳐 혼자 해결한 부분과 도움받은 부분을 구분하세요.']
    if grade.startswith('고'):checks.append('입학 연도별 편제표에서 실제 이수 과목과 개설 학기·선이수 안내를 먼저 확인하세요.')
    return '<ul class="cu-checks">'+''.join('<li>'+esc(t)+'</li>' for t in checks)+'</ul>'+buttons([('학교 자료 확인 체크리스트','커리큘럼/학교별-학습계획'),('학습 수준 정하는 방법','커리큘럼/수준별-학습방법')])
def related_guides(subject=None):
    items=[('최근 답안으로 어려움 살펴보기','guide/consultation-diagnosis'),('학습가이드 전체 보기','guide')]
    if subject=='수학':items.insert(0,('오답노트 작성법','교육정보/오답노트-작성법'))
    if subject=='영어':items.insert(0,('영어 어휘를 문장에 사용하는 연습','유용한정보/영어-어휘-문장-사용'))
    return section('cu-guides','공부 방법을 더 살펴보세요',buttons(items))

def create_subjects(header):
    for row in DATA['subjects']:
        grade=row['grade'];name=label(row);levels=level_records(row);early=grade in ['초1','초2'] and row['subject'] in ['영어','사회','과학']
        title=f'2026 {name} · '+('활동 내용과 가정에서 돕는 방법' if early else '학습 내용과 수준별 공부 방법')
        description=f'{name}의 학습 내용과 순서, 확인 과제를 살펴보고 학교 진도에 맞는 공부 계획을 세워 보세요.'
        if early:description=f'{name}의 참고 활동과 확인 과제를 살펴보고 학생의 흥미와 학교 수업에 맞춰 활용하세요.'
        toc=[('cu-focus','배울 내용'),('cu-sequence','공부 순서'),('cu-task','확인 과제'),('cu-levels','학습 방법'),('cu-parents','학부모 질문'),('cu-school','학교 자료 확인'),('ui-local-learning','동네·지점 안내')]
        body='<article class="cu-reading">'+curriculum_note(grade)
        body+='<nav class="ui-toc" aria-label="이 페이지 목차"><strong>필요한 내용으로 이동</strong><div class="ui-buttons">'+''.join(f'<a href="#{i}">{t}</a>' for i,t in toc)+'</div></nav>'
        if early:
            text='영어는 초1·2의 정규 교과가 아닌 선택 활동입니다. 정규 영어를 위한 필수 선행 과정으로 삼지 않고, 학생이 원할 때 흥미에 맞춰 활용하세요.' if row['subject']=='영어' else '초1·2의 사회·과학은 독립 정규 과목이 아닙니다. 이 페이지는 슬기로운 생활과 연결한 관찰·생활 활동을 안내합니다.'
            body+=note('<p>'+text+'</p>')
        body+=section('cu-focus','이 학년에서 살펴볼 내용','<p>'+esc(row['summary'])+'</p><p><strong>학습 중점</strong><br>'+esc(row['focus'])+'</p><p class="ui-meta">범위: '+esc(row['scope'])+'</p>')
        body+=section('cu-sequence','공부 순서를 이렇게 잡아 보세요','<p>학교에서 배우는 단원과 현재 어려움을 먼저 확인하고 아래 순서를 조정하세요. 모든 학생에게 같은 순서나 학습량을 정하는 계획은 아닙니다.</p>'+sequence(row['sequence']))
        body+=section('cu-task','공부한 내용을 확인하는 과제','<div class="cu-answer"><h3>직접 해 볼 일</h3><p>'+esc(row['task'])+'</p></div><p>혼자 해 본 결과를 남기고, 막힌 낱말·개념·풀이 단계를 표시해 보세요. 답을 확인한 뒤에는 왜 그렇게 되는지 자기 말로 다시 설명합니다.</p>')
        if levels:
            level_title='사회·역사 자료를 읽는 수준별 학습 방법' if row['subject']=='역사' else '기초·표준·심화, 필요한 공부 방법을 고르세요'
            level_intro='<p>한 과목 안에서도 단원별로 출발점이 다를 수 있습니다. 아래는 학습 방법의 예시이며 공식 성취등급이나 특정 지점의 개설 반 안내가 아닙니다.</p>'
            if row['subject']=='역사':level_intro+='<p>사회·역사에 공통으로 활용할 수 있는 자료 읽기와 설명 방법입니다. 실제 역사 이수 범위와 사료에 맞춰 조정하세요.</p>'
            body+=section('cu-levels',level_title,level_intro+level_cards(levels)+'<p class="ui-meta">교재명은 선택 후보입니다. 학년·학기·교육과정·개정판·문항 수준을 확인한 후 고르며, 지점에서 사용하는 교재는 따로 확인하세요.</p>')
        else:
            body+=section('cu-levels','활동의 출발점을 학생에게 맞추세요','<p>먼저 '+esc(row['sequence'].split('→')[0].strip())+'부터 시작해 보세요. 익숙해지면 '+esc(row['task'])+'로 활동을 이어 갑니다.</p><p>초1·2 활동은 기초·표준·심화라는 이름으로 수준을 고정하거나 어려운 교재를 먼저 풀게 하기보다, 학교의 통합교과 내용과 학생의 관심·참여 정도에 맞추는 것이 좋습니다.</p>')
        body+=section('cu-parents','학부모는 이런 질문으로 도와주세요',parent_help(row))
        body+=section('cu-school','우리 학교 진도에 맞춰 확인할 것','<p>'+esc(row['schoolCheck'])+'</p>'+school_check(grade))
        if grade.startswith('고'):body+=section('cu-choices','선택과목은 학교의 실제 이수 계획부터', '<p>이 페이지의 과목 범위는 참고 예시입니다. 고등학교마다 선택과목의 개설 학년·학기와 선이수 안내가 다릅니다. 2022 개정 과목 안내와 2026학년도 고3의 2015 개정 과목을 구분하세요.</p>'+buttons([('2022 개정 고등 공통·선택과목 안내','커리큘럼/고등-선택과목')]))
        body+=section('cu-other','같은 학년의 다른 과목도 살펴보세요',buttons([(label(r),subject_path(r)) for r in DATA['subjects'] if r['grade']==grade and r['subject']!=row['subject']])+buttons([(grade+' 커리큘럼 전체',grade_path(grade)),('커리큘럼 전체 보기','커리큘럼')]))
        body+=related_guides(row['subject'])+places()+refs([row],books=levels)+'</article>'
        shell(subject_path(row),title,description,body,header,crumbs=[(stage_for(grade)+' 커리큘럼','커리큘럼/'+stage_for(grade)),(grade+' 커리큘럼',grade_path(grade))])

def create_grades(header):
    for grade,g in GRADES.items():
        rows=[r for r in DATA['subjects'] if r['grade']==grade];title=f'2026 {grade_title(grade)} 커리큘럼 · 과목별 학습 계획'
        description=f'{grade}의 과목별 학습 중점과 확인 과제를 살펴보고 학교 자료에 맞는 공부 계획을 준비하세요.'
        body=curriculum_note(grade)+section('cu-overview',grade+' 공부에서 먼저 살펴볼 점','<p>'+esc(g['focus'])+'을 중심으로 현재 배우는 단원과 연결해 보세요.</p><p>안내 범위: '+esc(g['subjects'])+'. 아래 과목·활동을 선택하면 학습 내용, 순서와 확인 과제를 자세히 볼 수 있습니다.</p>')
        if grade in ['초1','초2']:body+=note('<p>초1·2의 정규 교과는 국어·수학·통합교과입니다. 영어는 선택 활동으로, 사회·과학은 슬기로운 생활 연계 활동으로 구분해 안내합니다.</p>')
        body+=section('cu-subjects','과목별로 필요한 내용 찾기','<div class="cu-card-grid">'+''.join(subject_card(r) for r in rows)+'</div>')
        body+=section('cu-plan','학생과 함께 계획을 정하는 순서',sequence('이번 학기 교과서·단원 확인 → 최근 과제에서 어려움 찾기 → 필요한 개념·활동부터 연습 → 확인 과제로 다시 설명 → 학교 진도와 다음 과제에 연결'))
        body+=section('cu-parents','학부모가 함께 준비할 자료','<p>학교에서 배부한 학기 안내, 교과서의 현재 단원, 학생이 직접 한 최근 과제를 함께 펼쳐 보세요. 과목마다 혼자 할 수 있는 일과 필요한 도움이 다를 수 있습니다.</p>'+school_check(grade))
        others=[(q+' 커리큘럼',grade_path(q)) for q in GRADES if stage_for(q)==stage_for(grade) and q!=grade]
        body+=section('cu-neighbor-grades','같은 학교급의 학년별 안내',buttons(others)+'<p class="ui-meta">모두 2026학년도 기준입니다. 다른 연도의 예습 계획은 해당 학년의 교육과정과 학교 편제표를 다시 확인하세요.</p>')
        if grade.startswith('고'):body+=buttons([('고등 공통·선택과목 살펴보기','커리큘럼/고등-선택과목')])
        body+=places()+refs(rows)
        shell(grade_path(grade),title,description,body,header,crumbs=[(stage_for(grade)+' 커리큘럼','커리큘럼/'+stage_for(grade))],collection=True,items=[(label(r),subject_path(r)) for r in rows])

def create_stages(header):
    for stage,info in STAGES.items():
        grades=[g for g in GRADES if stage_for(g)==stage];title=f'2026 {stage} 커리큘럼 · 학년과 과목별 공부 안내'
        description=f'{stage} 학년별 학습 중점과 과목별 공부 방법을 확인하고 학생에게 필요한 학습 계획을 준비하세요.'
        body=curriculum_note()+section('cu-grades','학생의 학년부터 선택하세요','<div class="cu-grade-grid">'+''.join(grade_card(g) for g in grades)+'</div>')
        for subject in SUBJECTS:
            rows=[r for r in DATA['subjects'] if r['grade'] in grades and r['subject']==subject]
            if not rows:continue
            body+=section('cu-subject-'+subject,subject+' 학년별 내용 비교하기','<p>같은 과목도 학년에 따라 학습 범위와 확인 과제가 달라집니다. 현재 학년의 안내부터 살펴보세요.</p>'+buttons([(label(r),subject_path(r)) for r in rows]))
        body+=section('cu-plan','학습 수준과 학교 진도 함께 확인하기','<p>학년만으로 학습 방법을 고정하지 않고 교과서와 최근 과제를 바탕으로 출발점을 정해 보세요.</p>'+buttons([('기초·표준·심화 학습 방법','커리큘럼/수준별-학습방법'),('학교별 학습계획 확인','커리큘럼/학교별-학습계획')]))
        if stage=='고등':body+=buttons([('고등 공통·선택과목 안내','커리큘럼/고등-선택과목')])
        body+=places()+refs([GRADES[g] for g in grades])
        shell('커리큘럼/'+stage,title,description,body,header,collection=True,items=[(grade_title(g),grade_path(g)) for g in grades])

def create_choices(header):
    title='2022 개정 고등 공통·선택과목 · 학습 내용과 준비 개념'
    description='고등 공통·선택과목의 학습 내용과 준비 개념을 비교하고 학교의 실제 과목 선택 안내를 확인하세요.'
    body=note('<strong>2022 개정 교육과정의 과목 예시입니다</strong><p>2026학년도 고1·고2에 적용되는 과정입니다. 고3은 2015 개정 교육과정으로 구분해 확인하세요. 아래 29개 항목은 대표 과목 안내이며 전체 개설 과목이나 학교의 확정 시간표가 아닙니다.</p>')
    body+=section('cu-before','선택 전에 확인할 세 가지',sequence('입학 연도별 학교 편제표에서 개설 과목·학기 확인 → 과목에서 쓰는 준비 개념을 최근 답안으로 점검 → 관심 진로·부담·학교 안내를 함께 살펴 이수 계획 정하기'))
    body+='<nav class="ui-toc" aria-label="교과별 선택과목 목차">'+''.join(f'<a href="#cu-choice-{esc(subject)}">{esc(subject)} 과목</a>' for subject in dict.fromkeys(r['subject'] for r in DATA['choices']))+'</nav>'
    for subject in dict.fromkeys(r['subject'] for r in DATA['choices']):
        cards=''
        for index,row in enumerate(DATA['choices']):
            if row['subject']!=subject:continue
            cards+=f'<article class="cu-choice" id="cu-course-{index+1}"><span class="cu-eyebrow">{esc(row["category"])}</span><h3>{esc(row["name"])}</h3><dl><dt>학습 내용</dt><dd>{esc(row["scope"])}</dd><dt>먼저 확인할 개념</dt><dd>{esc(row["preparation"])}</dd><dt>공부를 연결하는 방법</dt><dd>{esc(row["connection"])}</dd><dt>학교에서 확인할 것</dt><dd>{esc(row["schoolCheck"])}</dd></dl></article>'
        body+=section('cu-choice-'+subject,subject+' 공통·선택과목','<div class="cu-choices">'+cards+'</div>')
    body+=note('<p>과목 이름이 비슷해도 교육과정에 따라 내용과 이수 계획이 다를 수 있습니다. 학교 수업 과목과 수능 응시 범위는 해당 학년도 공식 안내를 각각 확인하세요.</p>')
    body+=buttons([(g+' 전체 커리큘럼',grade_path(g)) for g in ['고1','고2','고3']])+places()+refs(DATA['choices'])
    shell('커리큘럼/고등-선택과목',title,description,body,header,crumbs=[('고등 커리큘럼','커리큘럼/고등')])

def create_levels(header):
    title='기초·표준·심화 학습 방법 · 현재 수준에 맞게 공부하기'
    description='초등·중등·고등의 과목별 학습 방법과 확인 과제를 비교하고 현재 어려움에 맞는 출발점을 정하세요.'
    body=note('<strong>수준 이름보다 실제 과제에서 할 수 있는 일을 보세요</strong><p>기초·표준·심화는 공부 방법을 비교하기 위한 참고 구분입니다. 공식 성취등급, 성적 기준 또는 특정 지점의 개설 반을 의미하지 않습니다. 같은 학생도 단원·영역마다 출발점이 다를 수 있습니다.</p>')
    body+=section('cu-choose','어디서 시작하면 좋을까요?',sequence('현재 배우는 과목·단원과 과제 확인 → 학생이 혼자 설명·해결한 부분 찾기 → 필요한 개념·기본 적용·확장 과제 중 선택 → 확인 과제를 해 본 뒤 다음 연습 조정'))
    body+='<nav class="ui-toc" aria-label="학교급별 학습 방법 목차">'+''.join(f'<a href="#cu-level-{s}">{s} 학습 방법</a>' for s in STAGES)+'</nav>'
    for stage,info in STAGES.items():
        block='<p>'+esc(info[0])+'의 교과서와 실제 과제에 맞춰 참고하세요.</p>'
        if stage=='초등':block+='<p>초1·2의 영어 선택 활동과 사회·과학 통합교과 활동은 학년별 페이지에서 따로 살펴보세요. 아래 과목별 교재 후보를 초1·2에 일괄 적용하지 않습니다.</p>'
        for subject in SUBJECTS[:-1]:
            rows=[r for r in DATA['levels'] if r['stage']==info[0] and r['subject']==subject]
            block+='<h3>'+subject+' 학습 방법</h3>'+level_cards(rows)
        block+=buttons([(g+' 과목별 내용',grade_path(g)) for g in GRADES if stage_for(g)==stage])
        body+=section('cu-level-'+stage,stage+' 기초·표준·심화 참고',block)
    body+=note('<p>교재·자료는 선택 후보이며 사용 교재를 확정하는 목록이 아닙니다. 학년·학기·개정판과 실제 과목을 확인하세요. 최근 과제·풀이·관찰 기록으로 학습 공백을 살피고, 특정 점수나 정해진 기간만으로 단계를 고정하지 않습니다.</p>')
    body+=places()+refs(DATA['levels'])
    shell('커리큘럼/수준별-학습방법',title,description,body,header)

def create_checklist(header):
    title='학교별 학습계획 체크리스트 · 교과서와 진도에 맞추기'
    description='교과서·학기 진도·선택과목·평가 계획을 확인하고 공통 커리큘럼을 우리 학교의 학습 계획에 맞춰 보세요.'
    body='<article class="cu-reading">'+curriculum_note()+section('cu-how','학교 안내와 함께 체크해 보세요','<p>학교마다 교과서, 단원 순서와 평가 계획이 다릅니다. 학교 홈페이지·가정통신문·교과서·평가 안내를 펼쳐 아래 항목을 확인해 보세요. 체크 표시는 현재 화면에서만 유지되며 개인정보나 답안을 전송하지 않습니다.</p>')
    checks='<ul class="cu-checklist">'
    for i,row in enumerate(DATA['schoolChecks']):
        checks+=f'<li><h3><label><input type="checkbox" aria-label="{esc(row["item"])} 확인">{esc(row["item"])}</label></h3><p><strong>대상:</strong> {esc(row["forWhom"])}</p><p><strong>확인할 자료:</strong> {esc(row["where"])}</p><p><strong>계획에 적용하기:</strong> {esc(row["action"])}</p><p>{esc(row["caution"])}</p></li>'
    body+=section('cu-checks','학습 계획을 정하기 전 확인할 항목',checks+'</ul>')
    body+=section('cu-record','학생과 함께 남길 간단한 기록','<ul class="cu-checks"><li>학교·학년·학기와 현재 배우는 과목·단원</li><li>교과서·학교 자료와 평가 안내에서 확인한 내용</li><li>최근 과제에서 혼자 한 부분과 막힌 부분</li><li>이번에 연습할 내용과 확인할 과제</li><li>학교나 지점에 확인하고 싶은 질문</li></ul><p>확인되지 않은 일정이나 수업 정보는 질문으로 남기고, 실제 안내를 받은 뒤 계획에 반영하세요.</p>')
    body+=buttons([('학년·과목별 커리큘럼 찾기','커리큘럼'),('수준별 학습 방법 확인','커리큘럼/수준별-학습방법')])+places()+refs(DATA['grades'])+'</article>'
    shell('커리큘럼/학교별-학습계획',title,description,body,header)

def create_hub(header):
    title='2026 초등·중등·고등 커리큘럼 · 학년별 공부 길잡이'
    description='12개 학년의 과목별 학습 내용과 수준별 공부 방법을 찾아 학생과 학부모의 학습 계획을 준비하세요.'
    body=curriculum_note()+'<div class="cu-stats"><span>12개 학년</span><span>66개 과목·활동 안내</span><span>기초·표준·심화 학습 방법</span><span>고등 공통·선택과목</span></div>'
    body+='<nav class="ui-toc" aria-label="커리큘럼 빠른 이동"><div class="ui-buttons"><a href="#cu-grades">학년별로 바로 보기</a><a href="#cu-directory">학년·과목 검색하기</a><a href="#cu-planning">수준별 학습·학교 계획 보기</a></div></nav>'
    stages=''
    for stage,info in STAGES.items():
        text={'초등':'한글·수 감각부터 읽기·연산·탐구까지, 학년별로 필요한 출발점을 살펴보세요.','중등':'개념과 자료 해석, 서술형·탐구 과제를 학교 진도에 맞춰 연결해 보세요.','고등':'입학 연도와 실제 이수 과목을 확인하고 필요한 개념·적용 과제를 정해 보세요.'}[stage]
        stages+='<article class="cu-stage"><span class="cu-eyebrow">'+esc(info[1])+'</span><h3>'+stage+' 커리큘럼</h3><p>'+text+'</p>'+buttons([(stage+' 학년별 안내','커리큘럼/'+stage)])+'</article>'
    body+=section('cu-stages','학교급부터 찾아보세요','<div class="cu-stage-grid">'+stages+'</div>')
    body+=section('cu-grades','학년별로 바로 보기','<div class="cu-grade-grid">'+''.join(grade_card(g) for g in GRADES)+'</div>')
    filters='<div class="cu-filter-grid" data-cu-filters hidden><div><label for="cu-search">내용 검색</label><input type="search" id="cu-search" data-cu-search placeholder="예: 분수, 문장, 선택 활동" autocomplete="off"></div><div><label for="cu-stage">학교급</label><select id="cu-stage" data-cu-stage><option value="">모든 학교급</option>'+''.join(f'<option value="{s}">{s}</option>' for s in STAGES)+'</select></div><div><label for="cu-grade">학년</label><select id="cu-grade" data-cu-grade><option value="">모든 학년</option>'+''.join(f'<option value="{g}">{g}</option>' for g in GRADES)+'</select></div><div><label for="cu-subject">과목·활동</label><select id="cu-subject" data-cu-subject><option value="">모든 과목·활동</option>'+''.join(f'<option value="{s}">{s}</option>' for s in SUBJECTS)+'</select></div><button type="button" class="ui-reset" data-cu-reset>선택 초기화</button></div>'
    directory='<div data-cu-directory>'+filters+'<p class="cu-result-count" role="status" aria-live="polite" data-cu-count>66개 학습 안내를 볼 수 있습니다.</p><div class="cu-card-grid">'+''.join(subject_card(r) for r in DATA['subjects'])+'</div><p data-cu-empty hidden>조건에 맞는 안내가 없습니다. 검색어나 학년·과목 선택을 바꿔 보세요.</p></div>'
    body+=section('cu-directory','학년·과목으로 필요한 내용 찾기',directory)
    body+=section('cu-planning','학습 계획을 정할 때 함께 보기',buttons([('기초·표준·심화 공부 방법','커리큘럼/수준별-학습방법'),('고등 공통·선택과목 비교','커리큘럼/고등-선택과목'),('학교별 학습계획 체크리스트','커리큘럼/학교별-학습계획')]))
    body+=related_guides()+places()+refs(DATA['grades'])
    shell('커리큘럼',title,description,body,header,collection=True,items=[(label(r),subject_path(r)) for r in DATA['subjects']])

def link_context(name):
    # Local Latin routes use elementary/middle/high tokens; Korean routes may name a grade.
    parts=name.split('/');family=parts[0]
    if family in ['과목별학원','학년별학원']:topic=parts[1] if len(parts)>2 else ''
    elif family=='center':topic=parts[-2] if len(parts)>2 else ''
    elif family=='지점안내':topic='/'.join(parts[3:-1])
    else:topic=''
    grade_match=re.search(r'(?:^|/)(초[1-6]|중[1-3]|고[1-3])',topic)
    grade=grade_match[1] if grade_match else None
    stage=stage_for(grade) if grade else next((s for s,pattern in [('초등',r'초등(?!동)|elementary'),('중등',r'중등|중학|middle'),('고등',r'고등(?!동)|고교|high')] if re.search(pattern,topic.lower())),None)
    subject=next((s for s,words in [('수학',['수학','math']),('영어',['영어','english']),('국어',['국어','korean']),('과학',['과학','science']),('역사',['역사','history']),('사회',['사회','social'])] if any(w in topic.lower() for w in words)),None)
    items=[]
    if grade and subject:
        row=next((r for r in DATA['subjects'] if r['grade']==grade and r['subject']==subject),None)
        if row:items.append((label(row)+' 학습 내용',subject_path(row),''))
        items.append((grade+' 과목별 커리큘럼',grade_path(grade),''))
    elif grade:items.append((grade+' 과목별 커리큘럼',grade_path(grade),''))
    elif stage and subject and any(r['subject']==subject and stage_for(r['grade'])==stage for r in DATA['subjects']):
        items.append((stage+' '+subject+' 학년별 공부 내용','커리큘럼/'+stage,'#cu-subject-'+subject))
        items.append((stage+' 학년별 커리큘럼','커리큘럼/'+stage,''))
    elif stage:items.append((stage+' 학년별 커리큘럼','커리큘럼/'+stage,''))
    items.append(('학년·과목별 커리큘럼 찾기','커리큘럼',''))
    if len(items)<3:items.append(('학교 진도에 맞춰 계획 세우기','커리큘럼/학교별-학습계획',''))
    intro='상담 전에 현재 학년에서 배우는 내용과 확인 과제를 살펴보세요. 학교 진도와 최근 과제를 함께 확인하면 필요한 도움을 구체적으로 이야기할 수 있습니다.'
    links=[]
    for i,(title,path,anchor) in enumerate(items):
        cls=' class="cu-primary"' if i==0 else ''
        links.append(f'<a{cls} href="{href(path)}{quote(anchor,safe="#-")}">{esc(title)} →</a>')
    return START+'<section class="cu-local" aria-labelledby="cu-local-title"><h2 id="cu-local-title">지금 배우는 내용, 어떻게 공부할까요?</h2><p>'+intro+'</p><div class="cu-local-links">'+''.join(links)+'</div></section>'+END

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,required=True);parser.add_argument('--pages-only',action='store_true');parser.add_argument('--refresh-pages',action='store_true');args=parser.parse_args();report=args.report_dir
    baseline=json.loads((report/'baseline-release-public-manifest.json').read_text(encoding='utf-8'))
    current=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'))
    header=re.search(r'<header class="site-header".*?</header>',(ROOT/'index.html').read_text(encoding='utf-8-sig'),re.S)[0]
    header=re.sub(r' class="active"| aria-current="page"','',header)
    create_subjects(header);create_grades(header);create_stages(header);create_choices(header);create_levels(header);create_checklist(header);create_hub(header)
    assert len(CATALOG)==85
    if args.pages_only:
        print('Created 85 curriculum pages for initial review.',flush=True)
        return
    if args.refresh_pages:
        assert all(a['path']+'/index.html' in current['files'] for a in CATALOG)
        for name,hashes in CHANGED.items():current['files'][name]=hashes['raw'];current.setdefault('textSha256',{})[name]=hashes['text']
        (ROOT/'release-public-manifest.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (report/'catalog.json').write_text(json.dumps(CATALOG,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Refreshed the 85 curriculum pages and their reviewed manifest hashes.',flush=True)
        return
    names=[n for n in baseline['files'] if n.endswith('.html') and (n.split('/')[0] in ['center','과목별학원','학년별학원','지점안내'] or n in ['index.html','guide/index.html','교육정보/index.html','유용한정보/index.html'])]
    scope=Counter();preserved=[]
    def transform(name):
        raw=(ROOT/name).read_bytes();text=raw.decode('utf-8-sig')
        before=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',text,flags=re.S).replace(STYLE,'')
        assert before.count('</main>')==1 and before.count('</head>')==1,name
        restored=before.replace('\r\n','\n').replace('\r','\n').encode('utf-8')
        expected=baseline.get('textSha256',{}).get(name)
        if expected:
            assert expected in {sha(restored),sha(b'\xef\xbb\xbf'+restored)},'Unexpected prior content change: '+name
        elif START not in text:assert sha(raw)==baseline['files'][name],name
        updated=before.replace('</head>',STYLE+'</head>',1).replace('</main>',link_context(name)+'</main>',1)
        assert re.sub(re.escape(START)+r'.*?'+re.escape(END),'',updated,flags=re.S).replace(STYLE,'')==before,name
        target=updated.replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('utf-8')
        if raw.startswith(b'\xef\xbb\xbf'):target=b'\xef\xbb\xbf'+target
        if target!=raw:(ROOT/name).write_bytes(target)
        return name,sha(target),sha(target.replace(b'\r\n',b'\n')),sha(restored)
    print('Adding curriculum links to '+str(len(names))+' existing pages.',flush=True)
    with ThreadPoolExecutor(max_workers=16) as pool:
        for i,result in enumerate(pool.map(transform,names),1):
            n,d,t,p=result;CHANGED[n]={'raw':d,'text':t};preserved.append(dict(path=n,reconstructedTextSha256=p));scope[n.split('/')[0] if '/' in n else 'root']+=1
            if i%4000==0:print('Linked '+str(i)+' pages.',flush=True)
    for name in ['assets/curriculum.css','assets/curriculum.js']:save(name,(ROOT/name).read_bytes())
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'};sm=etree.parse(str(report/'baseline-sitemap.xml'));root=sm.getroot()
    nodes={unquote(urlparse(n.findtext('s:loc',namespaces=ns)).path).strip('/'):n for n in root.findall('s:url',ns)}
    for a in CATALOG:
        assert a['path'] not in nodes,a['path']
        node=etree.SubElement(root,'{'+ns['s']+'}url');etree.SubElement(node,'{'+ns['s']+'}loc').text=BASE+href(a['path']);etree.SubElement(node,'{'+ns['s']+'}lastmod').text=DATE
    save('sitemap.xml','<?xml version="1.0" encoding="UTF-8"?>\n'+etree.tostring(sm,encoding='unicode'))
    config=json.loads((report/'baseline-seo-descriptions.json').read_text(encoding='utf-8-sig'))
    for a in CATALOG:config['pages']['/'+a['path']]=dict(description=a['description'],sources=[a['description']])
    (ROOT/'seo-descriptions.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,hashes in CHANGED.items():current['files'][name]=hashes['raw'];current.setdefault('textSha256',{})[name]=hashes['text']
    current['sitemapPages']=len(root.findall('s:url',ns));current['updatedDate']=DATE
    (ROOT/'release-public-manifest.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for filename,value in [('catalog.json',CATALOG),('linked-existing.json',names),('preserved-html.json',preserved),('changed-public-files.json',sorted(CHANGED)),('new-html.json',[a['path']+'/index.html' for a in CATALOG])]:
        (report/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(newPages=len(CATALOG),grades=12,subjectPages=66,levelMethods=45,highCourseEntries=29,schoolChecks=11,linkedExistingPages=len(names),linkedScope=dict(scope),sitemapPages=current['sitemapPages'],publicFiles=len(current['files']))
    (report/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
