"""Add a useful-information hub and reviewed article adaptations without regenerating local pages."""
from __future__ import annotations
import argparse,copy,hashlib,html as H,json,re,zipfile
from datetime import datetime
from email.utils import format_datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote,unquote,urlparse
from lxml import html,etree
from useful_info_content import ARTICLES
from learning_guide_content import GUIDES,SOURCES as GUIDE_SOURCES
ROOT=Path(__file__).resolve().parents[1]
BASE='https://wawa-center.kr'; DATE='2026-10-02'; VERSION='20261002-useful'
SOURCES=copy.deepcopy(GUIDE_SOURCES)
SOURCES.update({
 'google':dict(name='Google · Android 디지털 웰빙과 집중 모드',url='https://support.google.com/android/answer/9346420?hl=ko',scope='지원 기기별 기능과 설정 안내'),
 'apple':dict(name='Apple · iPhone의 방해금지·집중 모드',url='https://support.apple.com/ko-kr/105112',scope='알림 허용과 일정 설정; 기기·버전에 따른 안내 확인'),
 'sleep':dict(name='CDC · 연령별 수면 권고와 수면 건강',url='https://www.cdc.gov/sleep/about/',scope='2024년 5월 15일 안내; 연령별 일반 권고'),
 'youth':dict(name='청소년1388 · 온라인 상담실 안내',url='https://www.1388.go.kr/cco/YTOSP_SC_CCI_01',scope='학업·진로·관계 등의 고민에 대한 상담 이용 안내')})
BY_PATH={a['path']:a for a in ARTICLES}; TITLES={g['path']:g['title'] for g in GUIDES}|{a['path']:a['title'] for a in ARTICLES}
NAV=f'<a href="/{quote("유용한정보")}/" data-useful-navigation>유용한정보</a>'
TRACKER='<script defer src="https://wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js" data-site="wawa-01" crossorigin="anonymous" referrerpolicy="no-referrer"></script>'
CHANGED={};HTML_CHANGED=set();REPORT=None;SELECTION=None
def esc(v):return H.escape(str(v),quote=True)
def href(path):return '/'+quote(path.strip('/'),safe='/-')+'/'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,data):
    raw=data if isinstance(data,bytes) else data.replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('utf-8')
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists() or p.read_bytes()!=raw:p.write_bytes(raw)
    CHANGED[name]=(sha(raw),None if isinstance(data,bytes) else sha(raw.replace(b'\r\n',b'\n')))
    if name.endswith('.html'):HTML_CHANGED.add(name)
def attach_nav(text):
    if 'data-useful-navigation' not in text:
        pattern=r'(<a\b[^>]*href="/(?:교육정보|'+quote('교육정보')+r')/"[^>]*>교육정보</a>)'
        text,n=re.subn(pattern,lambda m:m[0]+NAV,text,count=1)
        assert n==1,'Missing education menu'
    return text.replace('header.css?v=20261002-teachers','header.css?v='+VERSION)
def related_links(paths):return ''.join(f'<a href="{href(p)}">{esc(TITLES[p])} →</a>' for p in paths if p in TITLES)
def figure(image):return f'<figure class="ui-figure"><img src="/{quote(image["path"],safe="/-")}" alt="" width="{image["width"]}" height="{image["height"]}" loading="lazy" decoding="async"><figcaption>내용 이해를 돕는 참고 이미지</figcaption></figure>'
def chapters(a):
    result='';positions={0:0,len(a['sections'])//2:1,len(a['sections'])-1:2}
    for i,section in enumerate(a['sections']):
        result+=f'<section class="ui-chapter" id="ui-step-{i+1}"><h2>{i+1}. {esc(section[0])}</h2>'+''.join(f'<p>{esc(p)}</p>' for p in section[1:])+'</section>'
        if i in positions:result+=figure(a['images'][positions[i]])
    return result
def refs(a):return '<ol>'+''.join(f'<li><a href="{esc(SOURCES[s]["url"])}">{esc(SOURCES[s]["name"])}</a><br>{esc(SOURCES[s]["scope"])}</li>' for s in a['sources'])+'</ol>'
def places():return '''<section class="ui-places" id="ui-local-learning" data-ui-places><h2>우리 동네의 학습 안내 이어 보기</h2><p>글에서 정리한 질문을 가지고 가까운 지점의 소개와 동네 안내를 살펴보세요. 현재 모집·시간·비용·지원 범위는 해당 지점에 확인하세요.</p><div data-ui-place-controls hidden><div class="ui-places-grid"><div class="ui-place-search"><label for="ui-place-search">지점·동네 이름 검색</label><input type="search" id="ui-place-search" placeholder="예: 하계동, 하계점" autocomplete="off" data-ui-place-search></div><div><label for="ui-region">지역 선택</label><select id="ui-region" data-ui-region><option value="">모든 지역</option></select></div><div><label for="ui-branch">지점 선택</label><select id="ui-branch" data-ui-branch><option value="">지점을 선택하세요</option></select></div></div></div><p class="ui-place-status" role="status" aria-live="polite" data-ui-place-status>전국센터·지점 목록에서도 지역을 선택할 수 있습니다.</p><div data-ui-place-result hidden></div><div class="ui-buttons"><a href="/center/">동네·전국센터 안내</a><a href="/지점안내/">지점 전체 보기</a></div><noscript><p class="ui-place-fallback">위 목록에서 원하는 지역과 지점을 선택해 주세요.</p></noscript></section>'''
def head(a,collection=False):
    canonical=BASE+href(a['path']);typ='CollectionPage' if collection else 'Article'
    page={'@type':typ,'@id':canonical+'#page','url':canonical,'inLanguage':'ko-KR','description':a['description'],'name':a['title'],'dateModified':DATE,'publisher':{'@type':'Organization','name':'와와학습코칭센터','url':BASE+'/'}}
    graph=[page,{'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':i+1,'name':name,'item':BASE+href(p)} for i,(name,p) in enumerate([('홈',''),('유용한정보','유용한정보')]+([] if collection else [(a['title'],a['path'])]))]}]
    if not collection:
        page.update(headline=a['title'],datePublished=DATE,author={'@type':'Organization','name':'와와학습코칭센터'})
        graph.append({'@type':'FAQPage','mainEntity':[{'@type':'Question','name':a['faq'][0],'acceptedAnswer':{'@type':'Answer','text':a['faq'][1]}}]})
    else:graph.append({'@type':'ItemList','numberOfItems':len(ARTICLES),'itemListElement':[{'@type':'ListItem','position':i+1,'name':r['title'],'url':BASE+href(r['path'])} for i,r in enumerate(ARTICLES)]})
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(a['title'])} | 와와학습코칭센터</title><meta name="description" content="{esc(a['description'])}"><meta name="robots" content="index, follow"><link rel="canonical" href="{canonical}"><meta property="og:type" content="{'website' if collection else 'article'}"><meta property="og:title" content="{esc(a['title'])}"><meta property="og:description" content="{esc(a['description'])}"><meta property="og:url" content="{canonical}"><meta property="og:site_name" content="와와학습코칭센터"><meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(a['title'])}"><meta name="twitter:description" content="{esc(a['description'])}"><link rel="stylesheet" href="/assets/header.css?v={VERSION}"><link rel="stylesheet" href="/assets/useful-info.css?v={VERSION}"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&family=Noto+Serif+KR:wght@500;700&display=swap" rel="stylesheet"><script defer src="/assets/useful-info.js?v={VERSION}"></script><script type="application/ld+json">{json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False)}</script>{TRACKER}</head><body class="ui-page"><a class="ui-skip" href="#main-content">본문으로 건너뛰기</a>'''
def footer():return '<footer class="ui-footer"><div class="ui-wrap"><a href="/">와와학습코칭센터</a><nav aria-label="하단 메뉴"><a href="/유용한정보/">유용한정보</a><a href="/guide/">학습가이드</a><a href="/center/">전국센터</a><a href="/지점안내/">지점안내</a></nav></div></footer></body></html>'
def new_article(a,header):
    toc=''.join(f'<a href="#ui-step-{i+1}">{esc(s[0])}</a>' for i,s in enumerate(a['sections']))+'<a href="#ui-practice">상황 예시와 확인 목록</a><a href="#ui-local-learning">동네·지점 안내</a>'
    return head(a)+header+f'''<main id="main-content"><div class="ui-wrap"><nav class="ui-crumb" aria-label="현재 위치"><a href="/">홈</a> / <a href="/유용한정보/">유용한정보</a> / {esc(a['category'])}</nav><header class="ui-hero"><p class="ui-kicker">{esc(a['category'])}</p><h1>{esc(a['title'])}</h1><p class="ui-lead">{esc(a['intro'])}</p><p class="ui-meta">학생·학부모를 위한 학습 정보 · 내용 확인 {DATE}</p></header></div><article class="ui-paper" data-useful-article="{a['number']}"><nav class="ui-toc" aria-label="이 글의 목차">{toc}</nav>{chapters(a)}<section class="ui-box" id="ui-practice"><h2>내 상황에 맞춰 해 보기</h2>{''.join(f'<p>{esc(e)}</p>' for e in a['example'])}<p class="ui-meta">활동을 설명하기 위한 예시입니다. 자신의 학교 자료와 일정에 맞게 바꿔 보세요.</p><h3>오늘 남길 확인 목록</h3><ul>{''.join(f'<li>{esc(c)}</li>' for c in a['check'])}</ul></section><section class="ui-box"><h2>학부모는 이렇게 도와주세요</h2><p>{esc(a['parent'])}</p></section><section class="ui-faq"><h2>자주 묻는 질문</h2><details><summary>{esc(a['faq'][0])}</summary><p>{esc(a['faq'][1])}</p></details></section><section class="ui-refs"><h2>더 살펴볼 자료</h2><p>연구·기관 안내는 학습 활동을 구성할 때 참고한 자료입니다. 실제 학교 범위와 평가 조건은 학교 안내를 확인하세요.</p>{refs(a)}</section><section class="ui-article-related"><h2>다음 질문과 연결하기</h2>{related_links(a['related'])}<div class="ui-buttons"><a class="ui-primary" href="/유용한정보/">유용한정보 전체 보기</a><a href="/guide/">학습가이드와 기록 양식</a></div></section>{places()}</article></main>'''+footer()
def hub(header):
    a=dict(path='유용한정보',title='유용한정보, 학생·학부모를 위한 공부와 상담 이야기',description='시험 준비·방학·습관·과목별 학습·상담 정보를 찾고 동네와 지점의 학습 안내로 이어 보세요.')
    cats=list(dict.fromkeys(r['category'] for r in ARTICLES))
    cards=''.join(f'<article class="ui-card" data-ui-card data-category="{esc(r["category"])}"><span class="ui-kicker">{esc(r["category"])}</span><h3><a href="{href(r["path"])}">{esc(r["title"])}</a></h3><p>{esc(r["description"])}</p><a class="ui-card-link" href="{href(r["path"])}">글 읽기 →</a></article>' for r in ARTICLES)
    archives=''
    from learning_guide_content import CATEGORIES
    for key,(label,_) in CATEGORIES.items():
        remaining=[g for g in GUIDES if g['category']==key and g['path'] not in BY_PATH]
        archives+=f'<details><summary>{esc(label)} · {len(remaining)}개</summary><ul>'+''.join(f'<li><a href="{href(g["path"])}">{esc(g["title"])}</a></li>' for g in remaining)+'</ul></details>'
    return a,head(a,True)+header+f'''<main id="main-content" class="ui-wrap"><nav class="ui-crumb" aria-label="현재 위치"><a href="/">홈</a> / 유용한정보</nav><header class="ui-hero"><p class="ui-kicker">학생과 학부모의 다음 질문을 위해</p><h1>공부와 상담에 필요한<br>유용한정보</h1><p class="ui-lead">시험 준비가 막막할 때, 계획이 자꾸 밀릴 때, 자녀와 함께 도움을 정할 때.<br>지금 필요한 주제를 골라 한 가지 활동부터 해 보세요.</p><div class="ui-buttons"><a class="ui-primary" href="#ui-directory">30개 주제 찾아보기</a><a href="#ui-existing">기존 학습가이드 함께 보기</a></div></header><section id="ui-directory" data-ui-directory><h2>어떤 정보가 필요한가요?</h2><p>최근 학교 자료와 지금의 어려움을 떠올리며 찾아보세요. 기존 글과 연결되는 주제는 같은 주소에서 이어 볼 수 있습니다.</p><div class="ui-searchbar ui-filters" data-ui-filters hidden><div><label for="ui-search">주제 검색</label><input type="search" id="ui-search" placeholder="예: 중간고사, 영어, 학원, 방학" autocomplete="off" data-ui-search></div><div><label for="ui-category">분야 선택</label><select id="ui-category" data-ui-category><option value="">모든 분야</option>{''.join(f'<option>{esc(c)}</option>' for c in cats)}</select></div><button class="ui-reset" type="button" data-ui-reset>선택 초기화</button></div><p class="ui-meta" role="status" aria-live="polite" data-ui-count>30개 주제의 글을 볼 수 있습니다.</p><div hidden data-ui-empty><p>조건에 맞는 글이 없습니다. 단어를 짧게 바꾸거나 분야 선택을 초기화해 보세요.</p><button class="ui-reset" type="button" data-ui-reset>전체 글 보기</button></div><noscript><p>검색을 사용하지 않아도 아래에서 모든 글을 읽을 수 있습니다.</p></noscript><div class="ui-grid">{cards}</div></section><section class="ui-archived" id="ui-existing"><h2>기존 학습가이드도 함께 읽어보세요</h2><p>위 주제와 겹치는 글은 같은 주소에 모았습니다. 나머지 59개 가이드는 아래 분야에서 찾거나 학습가이드 메뉴에서 검색할 수 있습니다.</p>{archives}<div class="ui-buttons"><a href="/guide/">학습가이드 65개와 기록 양식</a><a href="/교육정보/">상황별 읽기 순서</a></div></section>{places()}</main>'''+footer()
def extend_existing(a,original):
    document=html.fromstring(original.encode('utf-8'));knowledge=document.xpath('//div[@class="lg-knowledge"]')[0]
    old_figures=''.join(html.tostring(n,encoding='unicode',with_tail=False) for n in knowledge.xpath('.//figure'))
    old_ids=[n.get('id') for n in knowledge.xpath('.//*[@id]')]
    aliases=''.join(f'<span id="{esc(i)}"></span>' for i in old_ids)
    original,n=re.subn(r'(<div class="lg-knowledge">).*?(</div>)',lambda m:m[1]+aliases+chapters(a)+old_figures+m[2],original,count=1,flags=re.S);assert n==1
    # Keep the existing form/download, FAQs, original images and named anchors.
    original=original.replace('<section class="lg-section" id="lg-related">',places()+'<section class="lg-section" id="lg-related">',1)
    original=original.replace('<a class="lg-inline-link" href="/guide/">',f'<a class="lg-inline-link" href="{href("유용한정보")}">유용한정보 전체 보기 →</a><a class="lg-inline-link" href="/guide/">',1)
    original=original.replace('</head>',f'<link rel="stylesheet" href="/assets/useful-info.css?v={VERSION}"><script defer src="/assets/useful-info.js?v={VERSION}"></script></head>',1)
    return attach_nav(original)
def context_block(name):
    if name=='index.html':chosen=['유용한정보/중간고사-답안-검토','유용한정보/공부-앱-선택','교육정보/학원-선택-체크리스트']
    elif '영어' in name:chosen=['유용한정보/영어-어법-독해-검토','유용한정보/영어-어휘-문장-사용']
    elif '수학' in name:chosen=['유용한정보/수학-풀이-선택-연습','교육정보/오답노트-작성법']
    elif '고등' in name or '고1' in name or '고2' in name:chosen=['유용한정보/고등-2학기-주간리듬','유용한정보/넓은-시험범위-지도']
    elif '초등' in name:chosen=['유용한정보/새학기-준비-점검','유용한정보/피드백과-학습-자신감']
    else:chosen=['유용한정보/중간고사-빈시간-계획','교육정보/학원-선택-체크리스트']
    chosen=[p for p in chosen if p+'/index.html'!=name]
    return '<!-- useful-links:start --><section class="useful-related" aria-labelledby="useful-related-title"><h2 id="useful-related-title">공부와 상담에 도움이 되는 정보</h2><p>학교 자료와 현재 어려움에 맞는 글을 골라 학습 질문을 정해 보세요.</p><div class="useful-related-links"><a href="/유용한정보/" class="useful-related-all">유용한정보 전체 보기 →</a>'+''.join(f'<a href="{href(p)}">{esc(TITLES[p])}</a>' for p in chosen)+'</div></section><!-- useful-links:end -->'
def branch_places(manifest):
    rows=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8-sig'))['centers']
    files=set(manifest['files']);result=[]
    for b in rows:
        path=f'지점안내/{b["region"]}/{b["routeName"]}';locals=[]
        for locality in b['neighborhoods']:
            # The branch-specific neighborhood/subject page keeps the location unambiguous across namesakes.
            localpath=next((f'{path}/{locality}{s}학원' for s in ['수학','영어','국어','사회','과학'] if f'{path}/{locality}{s}학원/index.html' in files),None)
            if localpath:locals.append(dict(name=locality,url=href(localpath)))
        assert path+'/index.html' in files,path
        result.append(dict(name=b['routeName'],region=b['region'],district=b['district'],address=b['address'],url=href(path),localities=locals))
    save('assets/useful-places.json',json.dumps(result,ensure_ascii=False,separators=(',',':')))
    return result
def main():
    global REPORT,SELECTION
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,required=True);parser.add_argument('--selection',type=Path,required=True);args=parser.parse_args()
    REPORT=args.report_dir;REPORT.mkdir(parents=True,exist_ok=True);SELECTION=json.loads(args.selection.read_text(encoding='utf-8'))
    current=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'))
    baselinepath=REPORT/'baseline-manifest.json'
    if not baselinepath.exists():baselinepath.write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    baseline=json.loads(baselinepath.read_text(encoding='utf-8'))
    if not (REPORT/'baseline-sitemap.xml').exists():
        (REPORT/'baseline-sitemap.xml').write_bytes((ROOT/'sitemap.xml').read_bytes())
    css=(ROOT/'assets/header.css').read_text(encoding='utf-8-sig')
    if not (REPORT/'baseline-header.css').exists():(REPORT/'baseline-header.css').write_text(css,encoding='utf-8')
    css=css.replace('--site-nav-offset:160px','--site-nav-offset:208px')
    if '/* Useful information links */' not in css:css+='''\n/* Useful information links */\n.useful-related{box-sizing:border-box;width:min(1180px,calc(100% - 32px));margin:32px auto;padding:24px;border:1px solid rgba(26,36,64,.18);background:#fff;color:#1a2440;font:14px/1.85 "Noto Sans KR","Malgun Gothic",sans-serif}.useful-related h2{margin:0 0 12px;font:700 22px/1.55 "Noto Serif KR",serif;word-break:keep-all}.useful-related p{margin:0 0 16px;color:#4d5770}.useful-related-links{display:flex;flex-wrap:wrap;gap:10px}.useful-related-links a{box-sizing:border-box;max-width:100%;display:block;border:1px solid rgba(26,36,64,.18);padding:10px 14px;color:#1a2440;background:#f6f2e9;text-decoration:none;border-radius:3px;overflow-wrap:anywhere}.useful-related-links .useful-related-all{color:#fff;background:#1a2440}.useful-related-links a:focus-visible{outline:3px solid #2166bf;outline-offset:3px}@media(max-width:600px){.useful-related{padding:20px;margin:26px auto}.useful-related h2{font-size:20px}.useful-related-links{flex-direction:column}.useful-related-links a{width:100%}}\n'''
    save('assets/header.css',css)
    header=attach_nav(re.search(r'<header class="site-header".*?</header>',(ROOT/'index.html').read_text(encoding='utf-8-sig'),re.S)[0])
    header=re.sub(r' class="active"| aria-current="page"','',header).replace('data-useful-navigation','data-useful-navigation class="active" aria-current="page"')
    oldzip=REPORT/'reused-originals.zip'
    if not oldzip.exists():
        with zipfile.ZipFile(oldzip,'w',zipfile.ZIP_DEFLATED) as z:
            for a in ARTICLES:
                if a['reuse']:z.write(ROOT/a['path']/'index.html',a['path']+'/index.html')
    chosen_by_number={r['number']:r for r in SELECTION['selection']}
    with zipfile.ZipFile(oldzip) as z:
        for a in ARTICLES:
            row=chosen_by_number[a['number']];a['images']=row['images'];a['sourceFolder']=row['folder']
            assert len(a['images'])==3 and len({im['sha256'] for im in a['images']})==3
            for im in a['images']:
                raw=(ROOT/im['path']).read_bytes();assert sha(raw)==im['sha256'];CHANGED[im['path']]=(sha(raw),None)
            save(a['path']+'/index.html',extend_existing(a,z.read(a['path']+'/index.html').decode('utf-8-sig')) if a['reuse'] else new_article(a,header))
    hubdata,page=hub(header);save('유용한정보/index.html',page)
    places_rows=branch_places(baseline)
    preserved=[];scope=Counter()
    def transform(name):
        raw=(ROOT/name).read_bytes();text=raw.decode('utf-8-sig')
        if name in {a['path']+'/index.html' for a in ARTICLES if a['reuse']}:return None
        old=text;updated=attach_nav(text)
        if '<!-- useful-links:start -->' not in updated:
            assert updated.count('</main>')==1,(name,updated.count('</main>'))
            updated=updated.replace('</main>',context_block(name)+'</main>',1)
        restored=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',updated,flags=re.S).replace(NAV,'').replace('header.css?v='+VERSION,'header.css?v=20261002-teachers')
        before=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',old,flags=re.S).replace(NAV,'').replace('header.css?v='+VERSION,'header.css?v=20261002-teachers')
        assert restored==before,name
        target=updated.replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('utf-8')
        if raw.startswith(b'\xef\xbb\xbf'):target=b'\xef\xbb\xbf'+target
        if target!=raw:(ROOT/name).write_bytes(target)
        return name,sha(target),sha(target.replace(b'\r\n',b'\n')),sha(restored.replace('\r\n','\n').encode('utf-8'))
    names=[n for n in baseline['files'] if n.endswith('.html')]
    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(transform,names):
            if result:
                n,d,t,p=result;CHANGED[n]=(d,t);HTML_CHANGED.add(n);preserved.append(dict(path=n,reconstructedTextSha256=p));scope[n.split('/')[0] if '/' in n else 'root']+=1
    for name in ['assets/useful-info.css','assets/useful-info.js']:
        raw=(ROOT/name).read_bytes();CHANGED[name]=(sha(raw),sha(raw.replace(b'\r\n',b'\n')))
    # Only real content updates change lastmod; menu/button additions do not alter all sitemap dates.
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'};sm=etree.parse(str(ROOT/'sitemap.xml'));root=sm.getroot()
    nodes={unquote(urlparse(n.findtext('s:loc',namespaces=ns)).path).strip('/'):n for n in root.findall('s:url',ns)}
    for a in [hubdata,*ARTICLES]:
        node=nodes.get(a['path'])
        if node is None:node=etree.SubElement(root,'{'+ns['s']+'}url');etree.SubElement(node,'{'+ns['s']+'}loc').text=BASE+href(a['path'])
        modified=node.find('s:lastmod',ns)
        if modified is None:modified=etree.SubElement(node,'{'+ns['s']+'}lastmod')
        modified.text=DATE
    save('sitemap.xml','<?xml version="1.0" encoding="UTF-8"?>\n'+etree.tostring(sm,encoding='unicode'))
    config=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8-sig'))
    for a in [hubdata,*ARTICLES]:
        key='/'+a['path'];old=config['pages'].get(key,{})
        if a.get('reuse'):a['description']=old['description'];continue
        config['pages'][key]=dict(description=a['description'],sources=[a['description']])
    (ROOT/'seo-descriptions.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rss=etree.parse(str(ROOT/'rss.xml'));channel=rss.getroot().find('channel');existing={unquote(urlparse(i.findtext('link')).path).strip('/'):i for i in channel.findall('item')}
    feed_date=format_datetime(datetime.now().astimezone())
    channel.find('lastBuildDate').text=feed_date
    for a in ARTICLES:
        item=existing.get(a['path'])
        if item is None:
            item=etree.SubElement(channel,'item')
            for k in ['title','link','guid','pubDate','description']:etree.SubElement(item,k)
            item.find('guid').set('isPermaLink','true');item.find('pubDate').text=feed_date
        item.find('title').text=a['title'];item.find('link').text=BASE+href(a['path']);item.find('guid').text=BASE+href(a['path']);item.find('description').text=a['description']
        doc=html.fromstring((ROOT/a['path']/'index.html').read_bytes());main=copy.deepcopy(doc.xpath('//main')[0])
        for n in main.xpath('.//form|.//*[@data-ui-places]|.//nav[contains(@class,"ui-toc") or contains(@class,"lg-toc")]'):n.getparent().remove(n)
        for n in main.xpath('.//a[starts-with(@href,"/")]'):n.set('href',BASE+n.get('href'))
        for n in main.xpath('.//img[starts-with(@src,"/")]'):n.set('src',BASE+n.get('src'))
        content=item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
        if content is None:content=etree.SubElement(item,'{http://purl.org/rss/1.0/modules/content/}encoded')
        content.text=etree.CDATA(html.tostring(main,encoding='unicode'))
    save('rss.xml','<?xml version="1.0" encoding="UTF-8"?>\n'+etree.tostring(rss,encoding='unicode'))
    for name,(rawhash,texthash) in CHANGED.items():
        current['files'][name]=rawhash
        if texthash:current.setdefault('textSha256',{})[name]=texthash
    current['sitemapPages']=len(root.findall('s:url',ns));current['updatedDate']=DATE
    (ROOT/'release-public-manifest.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    REPORT.joinpath('catalog.json').write_text(json.dumps(ARTICLES,ensure_ascii=False,indent=2),encoding='utf-8')
    REPORT.joinpath('changed-public-files.json').write_text(json.dumps(sorted(CHANGED),ensure_ascii=False,indent=2),encoding='utf-8')
    REPORT.joinpath('changed-html.json').write_text(json.dumps(sorted(HTML_CHANGED),ensure_ascii=False),encoding='utf-8')
    REPORT.joinpath('preserved-html.json').write_text(json.dumps(preserved,ensure_ascii=False),encoding='utf-8')
    summary=dict(selectedTopics=30,newArticles=24,improvedExisting=6,existingGuides=65,uniqueHubArticles=89,newHub=1,assignedImages=90,uniqueImages=len({im['path'] for a in ARTICLES for im in a['images']}),linkedExistingPages=sum(scope.values()),scope=dict(scope),branches=len(places_rows),neighborhoodLinks=sum(len(p['localities']) for p in places_rows),sitemapPages=current['sitemapPages'],publicFiles=len(current['files']))
    REPORT.joinpath('summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
