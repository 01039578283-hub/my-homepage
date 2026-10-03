"""Render the home content directory from existing, reviewed site destinations."""
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://wawa-center.kr'
DATE = '2026-10-03'
DESCRIPTION = '와와학습코칭센터의 지점·선생님 안내와 초중고 커리큘럼, 과목별 공부법·시험 준비·학부모 상담 정보를 찾아보세요.'
STYLE = '<link rel="stylesheet" href="/assets/home-resources.css?v=20261003">'
START = '<!-- home-resources:start -->'
END = '<!-- home-resources:end -->'
FEATURE_START = '<!-- home-reading:start -->'
FEATURE_END = '<!-- home-reading:end -->'

ACADEMY = [
    ('/overview/', '학원 소개', '진단·계획·수업·복습을 연결하는 코칭 방식과 학습 관리 내용을 살펴보세요.', '학습코칭 방식 살펴보기'),
    ('/지점안내/', '지점 안내', '지역에서 가까운 지점을 찾고 위치와 공개된 학년·과목 정보를 확인하세요.', '가까운 지점 안내 보기'),
    ('/선생님찾기/', '선생님 찾기', '지점별 선생님 소개와 담당 분야를 살펴보고 상담할 지점과 연결해 보세요.', '지점별 선생님 소개 보기'),
]
LEARNING = [
    ('/커리큘럼/', '학년·과목별 커리큘럼', '초1부터 고3까지 배우는 내용과 기초·표준·심화 학습 방향을 확인하세요.', '우리 아이 커리큘럼 찾기'),
    ('/guide/', '학습가이드', '과목별 공부법과 계획·시험·상담 주제를 검색하고, 기록 양식으로 직접 점검해 보세요.', '주제별 학습가이드 찾기'),
    ('/교육정보/', '교육정보', '수학 오답, 영어 독해, 공부 계획 등 지금의 어려움에 맞는 글을 순서대로 읽어 보세요.', '상황별 공부법 순서 보기'),
    ('/유용한정보/', '유용한정보', '시험 준비, 방학 계획, 학습 도구와 상담 등 일상에서 필요한 정보를 골라 보세요.', '공부·상담 정보 모아보기'),
]
ARTICLES = [
    ('/교육정보/오답노트-작성법/', '수학·오답', '오답노트를 써도 같은 문제에서 막히나요?', '첫 오류와 수정 이유를 짧게 남기고, 해설 없이 다시 풀어 본 결과를 확인해 보세요.', '오답노트 작성법 읽기'),
    ('/유용한정보/영어-어휘-문장-사용/', '영어·어휘', '단어 뜻은 아는데 문장에서 쓰기 어렵나요?', '학교 본문의 문맥과 함께 쓰는 표현을 확인한 뒤, 직접 쓴 한 문장으로 연습해 보세요.', '영어 어휘를 문장에서 쓰는 연습'),
    ('/유용한정보/넓은-시험범위-지도/', '시험·계획', '시험 범위가 넓어 어디서 시작할지 고민인가요?', '학교 자료와 단원별 질문을 나누고, 혼자 설명하기 어려운 부분부터 다음 공부를 정해 보세요.', '시험 범위 정리 방법 읽기'),
    ('/유용한정보/중간고사-답안-검토/', '시험·답안', '문제를 풀었는데 조건이나 단위를 놓치나요?', '최근 답안에서 반복된 누락을 골라, 다음 연습에 사용할 짧은 검토 목록을 만들어 보세요.', '중간고사 답안 검토 순서 보기'),
    ('/유용한정보/공부-앱-선택/', '계획·도구', '공부 앱을 쓰면 계획을 더 잘 지킬 수 있을까요?', '타이머·알림·할 일 중 필요한 기능을 먼저 고르고, 실제로 끝낸 과제와 방해 요인을 비교해 보세요.', '공부 앱 선택 기준 읽기'),
    ('/교육정보/학원-선택-체크리스트/', '학부모·상담', '학원 상담에서 무엇을 비교하면 좋을까요?', '학생에게 필요한 설명·연습·점검과 학년·과목·시간·교육비 조건을 같은 기준으로 확인해 보세요.', '학원 선택 체크리스트 보기'),
]
QUESTIONS = [
    ('어떤 학습정보부터 읽으면 좋을까요?', '특정 주제가 있다면 학습가이드에서 찾아보세요. 공부가 자꾸 멈추거나 오답이 쌓이는 상황이라면 교육정보의 읽기 순서로 시작할 수 있습니다.', '/교육정보/', '상황에 맞는 읽기 순서 찾기'),
    ('우리 아이 학년의 공부 범위는 어디서 보나요?', '커리큘럼에서 학년과 과목을 고르면 배우는 내용과 학습 방향을 볼 수 있습니다. 실제 공부 순서는 학교의 진도·평가 안내와 학생의 현재 이해도를 함께 확인해 정하세요.', '/커리큘럼/학교별-학습계획/', '학교 진도에 맞춘 학습계획 보기'),
    ('상담 전에 어떤 지점 정보를 확인하나요?', '지점 안내에서 위치와 공개된 학년·과목 정보를 살펴보고, 선생님 소개를 함께 읽어 보세요. 현재 모집 여부와 수업 시간·비용은 해당 지점에 확인해 주세요.', '/지점안내/', '지역별 지점 정보 확인하기'),
]

def e(value):
    return html.escape(value, quote=True)

def card(row, featured=False):
    path, title, description, label = row if not featured else (row[0], row[2], row[3], row[4])
    tag = f'<p class="hr-topic">{e(row[1])}</p>' if featured else ''
    return f'<article class="hr-card">{tag}<h4>{e(title)}</h4><p>{e(description)}</p><a class="hr-button" href="{e(path)}">{e(label)} <span aria-hidden="true">↗</span></a></article>'

def resources():
    academy = '\n'.join(card(row) for row in ACADEMY)
    learning = '\n'.join(card(row) for row in LEARNING)
    return f'''{START}
    <section class="hr-section wu-wrap" id="home-resources" aria-labelledby="home-resources-title">
      <div class="hr-heading"><p class="hr-kicker">학원 안내부터 집에서 하는 공부까지</p><h2 id="home-resources-title">지금 필요한 정보를 찾아보세요</h2><p>학원을 알아보고 있다면 지점·선생님 정보를, 공부 방법이 궁금하다면 학년과 상황에 맞는 글을 살펴보세요.</p></div>
      <div class="hr-groups">
        <section class="hr-group" id="home-academy-info" aria-labelledby="home-academy-title">
          <div class="hr-group-heading"><span class="hr-number" aria-hidden="true">01</span><div><h3 id="home-academy-title">학원·지점 정보</h3><p>수업 방식과 가까운 지점을 알아볼 때</p></div></div>
          <div class="hr-directory">{academy}</div>
          <nav class="hr-shortcuts" aria-label="학원 안내 더 찾아보기"><a href="/과목별학원/">과목별 학습·지역 안내 <span aria-hidden="true">→</span></a><a href="/학년별학원/">학년별 학습·지역 안내 <span aria-hidden="true">→</span></a></nav>
        </section>
        <section class="hr-group hr-study" id="home-study-info" aria-labelledby="home-study-title">
          <div class="hr-group-heading"><span class="hr-number" aria-hidden="true">02</span><div><h3 id="home-study-title">학생·학부모 학습정보</h3><p>배우는 내용과 다음 공부 방법을 찾을 때</p></div></div>
          <div class="hr-directory">{learning}</div>
          <nav class="hr-shortcuts" aria-label="학교급별 커리큘럼"><a href="/커리큘럼/초등/">초등 커리큘럼</a><a href="/커리큘럼/중등/">중등 커리큘럼</a><a href="/커리큘럼/고등/">고등 커리큘럼</a></nav>
        </section>
      </div>
      <p class="hr-next">고등학교 과목 선택이 궁금하다면 <a href="/커리큘럼/고등-선택과목/">선택과목 안내</a>를, 어느 수준에서 시작할지 고민이라면 <a href="/커리큘럼/수준별-학습방법/">기초·표준·심화 학습 방향</a>을 확인하세요.</p>
    </section>
    {END}'''

def reading():
    # Cards remain visible and crawlable without JavaScript.
    cards = '\n'.join(card(row, True).replace('<h4>', '<h3>').replace('</h4>', '</h3>') for row in ARTICLES)
    questions = '\n'.join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p><a class="hr-inline" href="{e(path)}">{e(label)} <span aria-hidden="true">→</span></a></details>' for q,a,path,label in QUESTIONS)
    return f'''{FEATURE_START}
    <section class="hr-section hr-reading wu-wrap" id="home-reading" aria-labelledby="home-reading-title">
      <div class="hr-heading"><p class="hr-kicker">학생과 학부모가 자주 겪는 상황</p><h2 id="home-reading-title">오늘의 질문에서 시작하는 공부</h2><p>글마다 해 볼 활동과 확인할 기록이 있습니다. 지금 겪는 상황에 가까운 글을 읽고, 다음 공부에서 한 가지를 실천해 보세요.</p></div>
      <div class="hr-reading-grid">{cards}</div>
      <nav class="hr-more" aria-label="학습 글 더 찾아보기"><a href="/guide/">전체 학습가이드 찾아보기 <span aria-hidden="true">→</span></a><a href="/유용한정보/">유용한정보 주제별로 보기 <span aria-hidden="true">→</span></a></nav>
      <div class="hr-faq"><h3>정보를 찾을 때 궁금한 점</h3>{questions}</div>
    </section>
    {FEATURE_END}'''

def item_list(id_, name, rows, featured=False):
    return {'@type':'ItemList', '@id':BASE+'/#'+id_, 'name':name, 'numberOfItems':len(rows),
            'itemListElement':[{'@type':'ListItem','position':i,'item':{'@type':'WebPage','url':BASE+r[0],
                'name':r[2] if featured else r[1], 'description':r[3] if featured else r[2]}} for i,r in enumerate(rows,1)]}

def main():
    path = ROOT/'index.html'
    original = path.read_bytes()
    newline = '\r\n' if b'\r\n' in original else '\n'
    text = original.decode('utf-8-sig').replace('\r\n','\n')
    text = re.sub(re.escape(START)+r'.*?'+re.escape(END)+'\n?', '', text, flags=re.S)
    text = re.sub(re.escape(FEATURE_START)+r'.*?'+re.escape(FEATURE_END)+'\n?', '', text, flags=re.S)
    text = re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->\n?', '', text, flags=re.S)
    text = text.replace(STYLE+'\n', '')
    text = re.sub(r'\s*<a class="wu-button hr-hero-link".*?</a>', '', text)
    anchor = '<a class="wu-button" href="/overview/#four-c">코칭 방식 알아보기</a>'
    assert text.count(anchor)==1
    text = text.replace(anchor, anchor+'\n          <a class="wu-button hr-hero-link" href="#home-resources">학원·교육정보 찾아보기 <span aria-hidden="true">↓</span></a>')
    jump = '<nav class="wu-jump wu-wrap" aria-label="메인 내용 바로가기">'
    assert text.count(jump)==1
    text = text.replace(jump, resources()+'\n\n    '+jump)
    text = re.sub(r'<a href="#home-reading">[^<]*</a>', '', text)
    text = text.replace(jump, jump+'\n      <a href="#home-reading">공부·상담 글</a>')
    anchor = '<!-- /WAWA_CONNECTIONS_20260915 -->'
    assert text.count(anchor)==1
    text = text.replace(anchor, anchor+'\n'+reading())
    text = text.replace('</head>', STYLE+'\n</head>')
    for attribute in ['name="description"', 'property="og:description"', 'name="twitter:description"']:
        text, n = re.subn('(<meta '+re.escape(attribute)+r' content=")[^"]*(")', lambda m:m[1]+e(DESCRIPTION)+m[2], text)
        assert n==1,attribute
    schema_match = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', text, re.S)
    schema = json.loads(schema_match[2]);graph=schema['@graph']
    graph[:] = [n for n in graph if n.get('@id') not in [BASE+'/#home-academy-list',BASE+'/#home-study-list',BASE+'/#home-reading-list']]
    page = next(n for n in graph if n.get('@id')==BASE+'/#webpage')
    page['description']=DESCRIPTION;page['dateModified']=DATE
    page['mainEntity']=[{'@id':BASE+'/#'+name} for name in ['home-academy-list','home-study-list','home-reading-list']]
    page['hasPart']=[n for n in page.get('hasPart',[]) if n.get('@id') not in [BASE+'/#home-resources',BASE+'/#home-reading']]
    for id_,name in [('home-resources','학원·지점 정보와 학생·학부모 학습정보'),('home-reading','오늘의 질문에서 시작하는 공부')]:
        page['hasPart'].append({'@type':'WebPageElement','@id':BASE+'/#'+id_,'url':BASE+'/#'+id_,'name':name,'isPartOf':{'@id':page['@id']}})
    graph.extend([item_list('home-academy-list','학원·지점 정보',ACADEMY),item_list('home-study-list','학생·학부모 학습정보',LEARNING),item_list('home-reading-list','오늘의 질문에서 시작하는 공부',ARTICLES,True)])
    faq=next(n for n in graph if n.get('@id')==BASE+'/#faq')
    faq['mainEntity']=[n for n in faq['mainEntity'] if n.get('name') not in {q[0] for q in QUESTIONS}]
    faq['mainEntity'].extend({'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a,_,_ in QUESTIONS)
    text=text[:schema_match.start(2)]+json.dumps(schema,ensure_ascii=False,separators=(',',':'))+text[schema_match.end(2):]
    text = re.sub(r'(?m)^[ \t]+$', '', text)
    raw = text.replace('\n',newline).encode('utf-8')
    path.write_bytes(raw)
    config_path=ROOT/'seo-descriptions.json'
    config=json.loads(config_path.read_text(encoding='utf-8-sig'));entry=config['pages']['/']
    entry['sources']=list(dict.fromkeys(entry['sources']+[entry['description'],DESCRIPTION]));entry['description']=DESCRIPTION
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sitemap_path=ROOT/'sitemap.xml';sitemap=sitemap_path.read_bytes()
    sitemap,n=re.subn(rb'(<loc>https://wawa-center\.kr/</loc>\s*<lastmod>)[^<]*(</lastmod>)',lambda m:m[1]+DATE.encode()+m[2],sitemap)
    assert n==1;sitemap_path.write_bytes(sitemap)
    manifest_path=ROOT/'release-public-manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    for name in ['index.html','assets/home-resources.css','sitemap.xml']:
        raw=(ROOT/name).read_bytes()
        manifest['files'][name]=hashlib.sha256(raw).hexdigest()
        if 'textSha256' in manifest:
            manifest['textSha256'][name]=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()
    manifest['files']=dict(sorted(manifest['files'].items()))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'homeDirectoryCards':len(ACADEMY)+len(LEARNING),'recommendedArticles':len(ARTICLES),'navigationQuestions':len(QUESTIONS),'publicFiles':len(manifest['files']),'descriptionLength':len(DESCRIPTION)},ensure_ascii=False))

if __name__=='__main__':
    main()
