"""Add 742 manuscript-based hubs; preserve and relocate 2,226 course pages.

Explicit URL manifest, bounded individual removals, persistent publication
dates and exact incoming-link replacement keep this migration reproducible.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET

from lxml import html
from branch_urls import DOMAIN, LEVELS, SUBJECTS, center_path, hub_path, course_path, legacy_path, canonical, crumbs
from branch_course_guidance import course_guidance, center_notes, REGISTRATION_NOTE
from branch_hub_upgrade import child_directory, related_markup, upgrade_header
from branch_seo import PageDates, finalize_page, GRAPH
from generate_branch_topic_pages import header, footer, media_markup, breadcrumb
from local_subject_content import load_sources, clean_schools

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'tools/data/local-subject-hubs'
OUT = Path(r'C:\Users\1992k\Desktop\CodexData\outputs\wawa-local-subject-hubs-20260921')
TODAY = date.today().isoformat()
TOPICS = ROOT / 'tools/data/branch-topic-pages/pages.json'
TRACKER = '<script defer src="https://wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js" data-site="wawa-01" crossorigin="anonymous" referrerpolicy="no-referrer"></script>'
SKIP = {'tools','scripts','tmp','reports','generated_article_txt','assets','node_modules'}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding='utf-8') != value:
        path.write_text(value, encoding='utf-8')


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def graph_update(raw, change):
    m = GRAPH.search(raw)
    if not m:
        raise ValueError('Missing branch graph')
    data = json.loads(m[2]); change(data['@graph'])
    return raw[:m.start(2)] + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + raw[m.end(2):]


def replace_section(raw, section_id, markup):
    pattern = rf'<section\b[^>]*id="{re.escape(section_id)}"[^>]*>.*?</section>'
    result, count = re.subn(pattern, lambda _: markup, raw, flags=re.S)
    if count != 1:
        raise ValueError(f'Section not unique: {section_id}')
    return result


def stage_entries(center, item):
    return [{'@type': 'ListItem', 'position': i + 1, 'name': f'{item["locality"]} {level} {item["subject"]}학원',
             'url': canonical(course_path(center, item['locality'], level, item['subject']))}
            for i, level in enumerate(LEVELS)]


def hub_breadcrumb(center, item):
    rows = crumbs(center, item['locality'], item['subject'])
    links = ''.join(f'<li><a href="{escape(p)}">{escape(n)}</a></li>' for n, p in rows[:-1])
    return f'<nav class="branch-breadcrumb" aria-label="현재 위치"><ol>{links}<li><span aria-current="page">{escape(rows[-1][0])}</span></li></ol></nav>'


def render_hub(center, item, store):
    loc, sub = item['locality'], item['subject']
    path = hub_path(center, loc, sub); url = canonical(path); parent = canonical(center_path(center))
    name = item['title']; view = course_guidance(center, sub)
    description = f'{loc} {sub}학원을 찾는 가정을 위한 {item["focus"]} 안내입니다. {center["routeName"]}의 과목별 안내 학년·주소를 확인하고 초등·중등·고등 학습 준비로 이어서 살펴보세요.'
    title = f'{name} | {item["focus"]} · {center["routeName"]}'
    first = f'{loc}에서 {sub} 수업을 알아본다면 현재 학년과 학습에서 막힌 지점을 먼저 나누어 보세요. 이 안내에서는 {item["focus"]}을 중심으로 상담할 질문을 정리하고, {center["routeName"]}의 수업 정보와 학교급별 안내를 연결합니다.'
    # Correct Korean particles rather than appending a fixed particle to every
    # manuscript-derived phrase.
    focus = item['focus']; particle = '을' if (ord(focus[-1])-0xAC00) % 28 else '를'
    first = first.replace(focus + '을 중심', focus + particle + ' 중심')
    answer = (' '.join([f'{center["displayName"]}의 {sub} 안내 학년은 {view["label"]}입니다.' if view['grades'] else f'{center["displayName"]}의 {sub} 개설 학년은 먼저 확인해 주세요.', *dict.fromkeys([*view['notes'], *center_notes(center)]), REGISTRATION_NOTE]))
    faqs = [
        {'question': f'{loc} {sub}학원 상담에서는 무엇부터 확인하나요?',
         'answer': f'{item["concern"]} 학생이라면 최근 학습 자료에서 혼자 해결한 내용과 도움이 필요했던 내용을 나누어 보세요. {item["practice"]}'},
        {'question': f'{center["routeName"]}의 {sub} 안내 학년은 어떻게 되나요?', 'answer': answer},
        {'question': '초등·중등·고등 안내를 어떻게 골라 읽으면 좋을까요?',
         'answer': f'현재 재학 중인 학교급의 {sub} 안내부터 살펴보세요. 이전 개념을 확인하거나 다음 학교급을 준비하는 경우에만 다른 단계도 함께 읽으면 됩니다. 안내 페이지의 존재와 현재 개설 학년은 같지 않으므로 센터의 과목별 안내 학년을 함께 확인해 주세요.'},
        {'question': f'{center["routeName"]} 방문 전 준비할 것은 무엇인가요?',
         'answer': f'안내 주소는 {center["address"]}입니다. 재학 학교·학년, 사용 교재, 최근 학습 기록, 등원 가능한 요일을 준비하고 출발 장소에서의 이동 경로와 수업 종료 후 귀가 방법을 확인해 주세요.'},
    ]
    stages = []
    school_paragraphs = []
    stage_copy = {
        ('초등','수학'): '계산한 과정을 말로 설명하고 문장 속 조건을 표시하는 연습',
        ('중등','수학'): '현재 단원에 필요한 이전 개념과 서술형 풀이 과정 점검',
        ('고등','수학'): '이수 과목·학교 진도와 조건 해석·풀이 전략을 나누어 점검',
        ('초등','영어'): '소리 내어 읽기와 뜻 이해, 짧은 문장 쓰기의 균형',
        ('중등','영어'): '학교 본문·어휘·문장 구조와 서술형 답안의 연결',
        ('고등','영어'): '지문 근거·선택지 판단·학교 평가 범위의 우선순위',
    }
    for level in LEVELS:
        detail = stage_copy[(level, sub)]
        scope = course_guidance(center, sub, level[0])
        status = scope['label'] if scope['grades'] else '현재 개설 여부 별도 확인'
        stages.append(f'<a href="{escape(course_path(center,loc,level,sub))}"><strong>{level} {sub}학원 안내 <span aria-hidden="true">→</span></strong><span>{escape(detail)}</span><span>{escape(status)}</span></a>')
        schools = clean_schools(center, level)
        if schools:
            school_paragraphs.append(f'<p><strong>{level} 학교 자료:</strong> {escape(", ".join(schools))} 등 센터 상담에서 참고할 학교의 자료를 현재 학년에 맞게 준비해 주세요. 학교 이름만으로 교재나 평가 범위가 같다고 볼 수는 없습니다.</p>')
    if not school_paragraphs:
        school_paragraphs = ['<p>학교마다 진도와 평가 범위가 다를 수 있습니다. 재학 학교와 학년을 알려주고 실제 교과서와 최근 학습 자료를 함께 확인해 주세요.</p>']
    other = '영어' if sub == '수학' else '수학'
    prep = '풀이 과정을 지우지 않은 문제지와 학교 수학 공책을' if sub == '수학' else '학교 영어 자료와 직접 쓴 답안, 읽고 있는 교재를'
    guide = '/guide/error-management/' if sub == '수학' else '/guide/study-planner/'
    graph = [
        {'@type':'WebSite','@id':DOMAIN+'/#website','url':DOMAIN+'/','name':'와와학습코칭센터','inLanguage':'ko-KR'},
        {'@type':'Organization','@id':DOMAIN+'/#organization','name':'와와학습코칭센터','url':DOMAIN+'/'},
        {'@type':['EducationalOrganization','LocalBusiness'],'@id':parent+'#academy','name':center['displayName'],'legalName':center['registeredName'],'url':parent,
         'address':{'@type':'PostalAddress','streetAddress':center['address'],'addressRegion':center['region'],'addressLocality':center['district'],'addressCountry':'KR'},'identifier':center['registrationNumber']},
        {'@type':'WebPage','@id':url+'#webpage','url':url,'name':title,'description':description,'inLanguage':'ko-KR',
         'isPartOf':{'@id':parent+'#webpage'},'mainEntity':{'@id':url+'#article'},'breadcrumb':{'@id':url+'#breadcrumb'},
         'about':[{'@id':parent+'#academy'},{'@type':'Place','name':loc},{'@type':'Thing','name':sub+' 학습'}],
         'hasPart':[{'@type':'WebPageElement','@id':url+'#child-pages','name':'학교급별 학습 안내','mainEntity':{'@id':url+'#child-pages-list'}}]},
        {'@type':'Article','@id':url+'#article','headline':name,'description':description,
         'abstract':f'{loc}의 {sub} 상담을 준비하며 {item["concern"]} 상황을 점검하고, {item["habit"]} 학습 흐름을 다시 정리하는 방법을 설명합니다. 연결 센터의 안내 학년과 학교급별 준비 자료를 구분합니다.',
         'mainEntityOfPage':{'@id':url+'#webpage'},'author':{'@id':DOMAIN+'/#organization'},'publisher':{'@id':DOMAIN+'/#organization'},
         'inLanguage':'ko-KR','articleSection':[item['focus'],'복습을 이어가는 기록','학교 자료와 상담 준비','학교급별 학습 안내'],
         'image':[DOMAIN+quote(center['primaryMedia'][k]['src'],safe='/') for k in ('representative','body','map')]},
        {'@type':'BreadcrumbList','@id':url+'#breadcrumb','itemListElement':[{'@type':'ListItem','position':i+1,'name':n,'item':canonical(p)} for i,(n,p) in enumerate(crumbs(center,loc,sub))]},
        {'@type':'FAQPage','@id':url+'#faq','mainEntity':[{'@type':'Question','name':f['question'],'acceptedAnswer':{'@type':'Answer','text':f['answer']}} for f in faqs]},
        {'@type':'ItemList','@id':url+'#child-pages-list','name':name+' 학교급별 안내','numberOfItems':3,'itemListElement':stage_entries(center,item)},
    ]
    if view['grades']:
        graph.append({'@type':'Service','@id':url+'#service','name':name+' 학습 상담','serviceType':sub+' 학습코칭','description':answer,'provider':{'@id':parent+'#academy'},'areaServed':{'@type':'Place','name':loc},'audience':{'@type':'EducationalAudience','educationalRole':'student','audienceType':view['label']}})
    raw = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(description,quote=True)}">
<meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="{url}">
<link rel="icon" href="/assets/favicon.png"><link rel="alternate" type="application/rss+xml" href="{DOMAIN}/rss.xml" title="와와학습코칭센터 RSS">
<meta property="og:type" content="article"><meta property="og:locale" content="ko_KR"><meta property="og:site_name" content="와와학습코칭센터">
<meta property="og:title" content="{escape(title,quote=True)}"><meta property="og:description" content="{escape(description,quote=True)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{DOMAIN}{center['primaryMedia']['representative']['src']}">
<link rel="stylesheet" href="/assets/header.css"><link rel="stylesheet" href="/assets/fab.css"><link rel="stylesheet" href="/assets/branch-directory.css?v=20260921-seo"><link rel="stylesheet" href="/assets/local-subject-hubs.css?v=20260921">
<script type="application/ld+json">{json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False,separators=(',',':'))}</script>{TRACKER}</head>
<body class="branch-directory-page branch-topic-page local-subject-page">
{header()}{hub_breadcrumb(center,item)}<main id="main" class="branch-shell">
<section class="branch-topic-hero"><p class="branch-kicker">{escape(center['region'])} · {escape(center['district'])} · {escape(center['routeName'])}</p>
<h1>{escape(name)}</h1><p class="branch-lead">{escape(first)}</p>
<div class="branch-hero-actions"><a class="branch-button primary" href="#child-pages">학교급별 안내</a><a class="branch-button" href="{escape(center_path(center))}">{escape(center['routeName'])} 정보</a></div></section>
<section class="branch-answer" id="overview"><h2>{escape(center['routeName'])} {sub} 수업 확인</h2><p>{escape(answer)}</p></section>
<nav class="branch-toc" aria-label="페이지 목차"><a href="#learning-check">학습 점검</a><a href="#weekly-plan">복습 기록</a><a href="#school-materials">상담 준비</a><a href="#faq">FAQ</a><a href="#child-pages">학교급별 안내</a><a href="#center-reference">위치 안내</a></nav>
<div class="branch-topic-article">
<section id="learning-check"><p class="hub-case-label">현재 학습 상태에 맞춰 살펴보기</p><h2>{escape(item['focus'])}부터 점검하세요</h2>
<p>{escape(item['concern'])} 학생이라면 문제의 양이나 진도만으로 현재 상태를 판단하기 어렵습니다. 이런 상황에 해당하는지 최근 학습 기록을 먼저 확인해 보세요.</p>
<p>{escape(item['practice'])}</p><p>{escape(loc)} {sub} 상담에는 잘한 결과만 골라 가져가기보다, 처음 막힌 부분과 도움 뒤 해결한 부분을 함께 보여 주세요. 설명이 필요한 지점과 스스로 연습할 분량을 구분하는 데 도움이 됩니다.</p></section>
<section id="weekly-plan"><h2>다음 공부로 이어지는 복습 기록</h2><p>{escape(item['habit'])} 상황도 함께 살펴볼 필요가 있습니다. 공부를 시작한 시점과 혼자 마친 범위를 짧게 적으면 과제를 했다는 말만으로는 알기 어려운 차이가 드러납니다.</p>
<p>{escape(item['followup'])}</p><ol class="hub-step-list"><li>시작 전: 오늘 확인할 개념이나 문장을 하나 정합니다.</li><li>마친 뒤: 혼자 해결한 내용과 남은 질문을 구분합니다.</li><li>다음 학습: 질문했던 부분을 도움 없이 다시 해 보고 기록을 비교합니다.</li></ol>
<p>이 기록을 활용하는 방법은 <a class="hub-inline-link" href="{guide}">{'오답 재학습 가이드' if sub=='수학' else '주간 학습계획 가이드'}</a>에서 이어서 살펴볼 수 있습니다. 실제 과제 점검 방식과 보호자 피드백 주기는 센터 상담에서 확인해 주세요.</p></section>
<section id="school-materials"><h2>{escape(center['routeName'])} 상담에 챙길 학교 자료</h2><p>{escape(prep)} 준비해 주세요. 같은 학교에 다녀도 현재 단원과 혼자 공부할 수 있는 범위가 다를 수 있으므로 진도와 보완할 내용을 나누어 상담하는 편이 좋습니다.</p>
{''.join(school_paragraphs)}<p>아래의 초등·중등·고등 안내에서는 해당 학교급에 맞는 질문과 준비 방법을 더 구체적으로 확인할 수 있습니다.</p></section></div>
<section class="branch-section branch-faq" id="faq"><div class="branch-section-head"><p class="branch-kicker">FAQ</p><h2>{escape(name)} 자주 묻는 질문</h2></div>{''.join('<details><summary>'+escape(f['question'])+'</summary><p>'+escape(f['answer'])+'</p></details>' for f in faqs)}</section>
<section class="branch-section" id="child-pages"><div class="branch-section-head"><p class="branch-kicker">SCHOOL STAGE</p><h2>{escape(loc)} {sub} 학교급별 안내</h2><p>현재 학교급부터 선택하고, 센터의 실제 안내 학년과 별도 확인 조건도 함께 살펴보세요.</p></div><div class="hub-stage-grid">{''.join(stages)}</div></section>
<section class="branch-section branch-related" id="related-pages"><h2>함께 확인할 안내</h2><div class="related-grid"><a href="{escape(hub_path(center,loc,other))}"><strong>{escape(loc)} {other}학원</strong><span>같은 동네의 다른 과목 학습 준비</span></a><a href="{escape(center_path(center))}"><strong>{escape(center['routeName'])} 지점안내</strong><span>주소·전체 과목·학교·수업 조건</span></a></div></section>
{media_markup(center,name)}
<section class="branch-section" id="center-reference"><div class="branch-section-head"><p class="branch-kicker">CENTER INFORMATION</p><h2>{escape(center['routeName'])} 방문 정보</h2></div><dl class="info-list"><div><dt>센터</dt><dd>{escape(center['displayName'])}</dd></div><div><dt>주소</dt><dd>{escape(center['address'])}</dd></div><div><dt>등록 명칭</dt><dd>{escape(center['registeredName'])}</dd></div><div><dt>정보 확인 기준일</dt><dd>{escape(center['informationReviewedAt'])} · 제공 자료 기준</dd></div></dl><p>등원 가능 요일과 하교 후 출발 장소를 알려주고, 실제 시간표와 귀가 동선을 확인해 주세요.</p></section>
</main>{footer()}</body></html>'''
    raw = upgrade_header(raw)
    return finalize_page(raw, path, store=store), path


def mapping_replacer(mapping):
    pattern = re.compile(r'(?:/지점안내/|/'+quote('지점안내')+r'/)[^\s"\'<>#?]+',re.I)
    def change(m):
        value=m[0];decoded=unquote(value)
        suffix='index.html' if decoded.endswith('/index.html') else ''
        key=(decoded[:-len(suffix)] if suffix else decoded).rstrip('/')+'/'
        if key not in mapping:return value
        target=mapping[key]
        return quote(target,safe='/') if value.startswith('/%') else target
    return lambda raw:pattern.sub(change,raw)


def migrate_child(raw, center, item, replace):
    raw = replace(raw)
    raw, count = re.subn(r'<nav class="branch-breadcrumb".*?</nav>', lambda _: breadcrumb(center,item), raw, count=1, flags=re.S)
    if count != 1: raise ValueError('Missing breadcrumbs')
    block, related = related_markup(center,item)
    raw = replace_section(raw,'related-pages',block)
    parent_hub = canonical(hub_path(center,item['locality'],item['subject']))
    def update(nodes):
        for node in nodes:
            if node.get('@type')=='BreadcrumbList':
                node['itemListElement']=[{'@type':'ListItem','position':i+1,'name':n,'item':canonical(p)} for i,(n,p) in enumerate(crumbs(center,item['locality'],item['subject'],item['level']))]
            elif node.get('@type')=='WebPage':
                node['isPartOf']={'@id':parent_hub+'#webpage'}
                node['relatedLink']=[r['url'] for r in related]
            elif node.get('@type')=='ItemList' and node.get('@id','').endswith('#related-pages'):
                node['itemListElement']=related;node['numberOfItems']=len(related)
    raw = graph_update(raw,update)
    # Preserve all original manuscripts, images, availability and first answer.
    return raw


def center_hubs(raw, center):
    if not center['neighborhoods']: return raw
    raw = replace_section(raw,'learning-pages',child_directory(center))
    entries=[{'@type':'ListItem','position':i+1,'name':f'{loc} {sub}학원','url':canonical(hub_path(center,loc,sub))}
             for i,(loc,sub) in enumerate(( (loc,sub) for loc in center['neighborhoods'] for sub in SUBJECTS ))]
    def update(nodes):
        listing=next(n for n in nodes if n.get('@type')=='ItemList' and '#learning-pages' in n.get('@id',''))
        listing.update(itemListElement=entries,numberOfItems=len(entries))
    return graph_update(raw,update)


def sync_sitemap(paths, store, replace):
    file=ROOT/'sitemap.xml';raw=replace(file.read_text(encoding='utf-8'))
    def update(m):
        block=m[0];loc=re.search(r'<loc>(.*?)</loc>',block)
        if not loc:return block
        path=unquote(urlsplit(loc[1]).path)
        if path in store.records:
            block=re.sub(r'<lastmod>.*?</lastmod>',f'<lastmod>{store.records[path]["dateModified"]}</lastmod>',block)
        return block
    raw=re.sub(r'<url>.*?</url>',update,raw,flags=re.S)
    raw=re.sub(r'\s*<!-- local-subject-hubs:start -->.*?<!-- local-subject-hubs:end -->','',raw,flags=re.S)
    block='\n  <!-- local-subject-hubs:start -->\n'+''.join(f'  <url><loc>{canonical(p)}</loc><lastmod>{store.records[p]["dateModified"]}</lastmod></url>\n' for p in paths)+'  <!-- local-subject-hubs:end -->\n'
    raw=raw.replace('</urlset>',block+'</urlset>')
    entries=ET.fromstring(raw).findall('{*}url')
    assert len(entries)==21543 and len({e.findtext('{*}loc') for e in entries})==len(entries)
    write(file,raw)


def redirects():
    file=ROOT/'vercel.json';data=json.loads(file.read_text(encoding='utf-8'))
    existing=[r for r in data['redirects'] if not unquote(r['source']).startswith('/지점안내/:region/:center/:locality')]
    rules=[]
    for level in LEVELS:
        for subject in SUBJECTS:
            # Vercel's static routing matcher receives percent-encoded paths.
            # Encode only literal segments; captures keep the original values.
            prefix=quote('/지점안내',safe='/')+'/:region/:center/:locality'
            source=prefix+'([^/]+)'+quote(f'{level}{subject}학원',safe='')
            dest=prefix+quote(f'{subject}학원/{level}/',safe='/')
            rules.extend([{'source':source+'/index.html','destination':dest,'permanent':True},
                          {'source':source+'/','destination':dest,'permanent':True},
                          {'source':source,'destination':dest,'permanent':True}])
    data['redirects']=rules+existing
    write(file,json_text(data))


def public_files():
    # Avoid source HTML snapshots and all private/report files.
    for directory in ROOT.iterdir():
        if directory.name.startswith('.') or directory.name in SKIP: continue
        if directory.is_file():
            if directory.suffix in ('.html','.xml','.txt'):yield directory
        elif directory.is_dir():
            yield from directory.rglob('*.html')


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    byloc={loc:c for c in centers for loc in c['neighborhoods']}
    assert len(byloc)==371
    sources=load_sources()
    assert {r['locality'] for r in sources}==set(byloc)
    old_data=json.loads(TOPICS.read_text(encoding='utf-8'))
    store=PageDates(ROOT)
    mapping={legacy_path(byloc[r['locality']],r['locality'],r['level'],r['subject']):course_path(byloc[r['locality']],r['locality'],r['level'],r['subject']) for r in old_data['pages']}
    assert len(mapping)==len(set(mapping.values()))==2226
    replace=mapping_replacer(mapping)
    write(OUT/'url-migration.json',json_text(mapping))
    pages=[]; stats=Counter(); retained=[]
    for row in old_data['pages']:
        c=byloc[row['locality']]; old=legacy_path(c,row['locality'],row['level'],row['subject']);new=mapping[old]
        old_file=ROOT/old.strip('/')/'index.html';new_file=ROOT/new.strip('/')/'index.html'
        source=old_file if old_file.exists() else new_file
        raw=source.read_text(encoding='utf-8')
        if old in store.records:
            record=store.records.pop(old)
            if new not in store.records:store.records[new]=record
        if new not in store.records:raise ValueError('Publication history missing: '+new)
        after=migrate_child(raw,c,row,replace)
        after=finalize_page(after,new,store=store)
        doc_before=html.fromstring(raw);doc_after=html.fromstring(after)
        for cls in ('branch-topic-article','branch-primary-media','branch-course-summary'):
            xp=f'//*[contains(concat(" ",normalize-space(@class)," ")," {cls} ")]'
            assert [html.tostring(n) for n in doc_before.xpath(xp)]==[html.tostring(n) for n in doc_after.xpath(xp)],(old,cls)
        write(new_file,after)
        # Non-recursive removal of an exact manifest-identified old HTML only.
        if old_file.exists() and old_file != new_file:
            assert old_file.resolve().is_relative_to((ROOT/'지점안내').resolve()) and old_file.name=='index.html'
            old_file.unlink()
            if not any(old_file.parent.iterdir()):old_file.parent.rmdir()
        pages.append({**row,'path':new,'file':new_file.relative_to(ROOT).as_posix(),'hubPath':hub_path(c,row['locality'],row['subject']),'legacyPath':old})
        stats['migratedCourses']+=1
        if stats['migratedCourses']%500==0:print(f'Courses processed: {stats["migratedCourses"]}',flush=True)
    store.save()
    hub_pages=[]
    for item in sources:
        c=byloc[item['locality']];raw,path=render_hub(c,item,store)
        write(ROOT/path.strip('/')/'index.html',raw)
        hub_pages.append({**item,'path':path,'center':c['routeName'],'region':c['region']})
    for c in centers:
        path=center_path(c);file=ROOT/path.strip('/')/'index.html';raw=file.read_text(encoding='utf-8')
        after=center_hubs(raw,c)
        if after!=raw:
            write(file,finalize_page(after,path,store=store));stats['updatedCenters']+=1
    for file in public_files():
        before=file.read_text(encoding='utf-8');after=replace(before)
        if before!=after:
            path='/'+file.relative_to(ROOT).parent.as_posix().strip('/')+'/'
            if path in store.records:after=finalize_page(after,path,store=store)
            write(file,after);stats['incomingLinkFiles']+=1
    old_data.update(generatedAt=TODAY,pages=pages)
    write(TOPICS,json_text(old_data))
    write(DATA/'hubs.json',json_text({'generatedAt':TODAY,'hubCount':742,'pages':hub_pages}))
    write(DATA/'url-migration.json',json_text(mapping))
    store.save()
    sync_sitemap([r['path'] for r in hub_pages],store,replace)
    redirects()
    # Existing education-focused RSS items remain articles, not a mass URL list.
    # All new/moved URLs are discoverable in the complete sitemap.
    llms=ROOT/'llms.txt';raw=llms.read_text(encoding='utf-8')
    marker='\n## 지점별 동네·과목·학교급 안내\n'
    raw=raw.split(marker)[0].rstrip()+marker+'\n- 지점안내: https://wawa-center.kr/지점안내/\n- 지역 → 지점 → 동네별 수학·영어학원 → 초등·중등·고등 순으로 안내합니다.\n- 예시: https://wawa-center.kr/지점안내/경기/풍동점/풍동수학학원/\n- 학교급별 예시: https://wawa-center.kr/지점안내/경기/풍동점/풍동수학학원/고등/\n- 각 학습 안내와 센터의 현재 개설 학년은 구분하며, 과목별 안내 학년과 별도 확인 조건을 함께 읽습니다.\n'
    write(llms,raw)
    stats.update(newHubs=742,totalBranchPages=3178,totalSitemapUrls=21543)
    write(OUT/'generation.json',json_text(dict(stats)))
    print(json.dumps(dict(stats),ensure_ascii=False,indent=2))


def refresh_hubs():
    """Refresh only the new hub content; never regenerate old grade manuscripts."""
    centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    byloc={loc:c for c in centers for loc in c['neighborhoods']}
    store=PageDates(ROOT);pages=[]
    for item in load_sources():
        c=byloc[item['locality']];raw,path=render_hub(c,item,store)
        write(ROOT/path.strip('/')/'index.html',raw)
        pages.append({**item,'path':path,'center':c['routeName'],'region':c['region']})
    assert len(pages)==742
    write(DATA/'hubs.json',json_text({'generatedAt':TODAY,'hubCount':742,'pages':pages}))
    store.save()
    sync_sitemap([r['path'] for r in pages],store,lambda raw:raw)
    print('Refreshed 742 neighborhood subject hubs; existing grade manuscripts unchanged.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write',action='store_true')
    mode.add_argument('--refresh-hubs',action='store_true')
    args=parser.parse_args()
    refresh_hubs() if args.refresh_hubs else run()
