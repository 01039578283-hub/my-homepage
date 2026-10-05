"""Extend the existing information menu while preserving previously published article bodies."""
import argparse,copy,hashlib,html as H,json,re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote,unquote,urlparse
from lxml import html,etree
import build_useful_info as ui
from useful_info_expansion_content import ARTICLES as NEW
ROOT=Path(__file__).resolve().parents[1]
BASE='https://wawa-center.kr';DATE='2026-10-05';CHANGED={}
OLD=copy.deepcopy(ui.ARTICLES)
ui.ARTICLES=NEW+OLD
ui.BY_PATH={a['path']:a for a in ui.ARTICLES}
ui.TITLES.update({a['path']:a['title'] for a in NEW})
ui.TITLES.update({'overview/수업형식-비교':'수업형식 비교, 필요한 도움과 실제 진행 살펴보기','선생님찾기':'우리 지점 선생님 안내'})
ui.DATE=DATE;ui.VERSION='20261005-useful'
ui.SOURCES.update({
 'ies':dict(name='IES · 공부와 연습을 설계하는 가이드',url='https://ies.ed.gov/ncee/wwc/PracticeGuide/1',scope='예시 풀이·설명 질문·복습 활동을 다루는 교사용 자료'),
 'styles':dict(name='EEF · 학습 유형 분류의 근거와 한계',url='https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/learning-styles',scope='고정된 유형으로 학생을 분류하는 접근의 근거와 주의점'),
 'collab':dict(name='EEF · 협력 학습의 참여와 과제 설계',url='https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/collaborative-learning-approaches',scope='공동 과제의 역할·참여·개별 이해 확인을 위한 자료'),
 'suneung':dict(name='한국교육과정평가원 · 대학수학능력시험',url='https://www.suneung.re.kr/',scope='공개 기출·모의평가 및 시행 안내; 연도와 과목 확인'),
 'neis':dict(name='나이스 학부모서비스',url='https://parents.neis.go.kr/',scope='학교생활과 성적 정보 조회; 제공 범위와 학교 안내 확인'),
 'adiga':dict(name='대입정보포털 어디가',url='https://www.adiga.kr/',scope='대학·전형 정보 조회; 해당 모집 연도와 대학의 최종 모집요강 확인')})
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,data):
    raw=data if isinstance(data,bytes) else data.replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('utf-8')
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists() or p.read_bytes()!=raw:p.write_bytes(raw)
    CHANGED[name]=(sha(raw),None if isinstance(data,bytes) else sha(raw.replace(b'\r\n',b'\n')))
def figure(im):
    return f'<figure class="ui-figure"><img src="/{quote(im["path"],safe="/-")}" alt="{H.escape(im["alt"],quote=True)}" width="{im["width"]}" height="{im["height"]}" loading="lazy" decoding="async"><figcaption>학습 상황을 설명하기 위한 참고 이미지입니다.</figcaption></figure>'
ui.figure=figure
def static_places(a,places):
    picked=[places[(a['number']*7+k*53)%len(places)] for k in range(3)]
    links=''
    for p in picked:
        links+=f'<div class="ui-local-card"><h3>{H.escape(p["region"])} · {H.escape(p["name"])}</h3><div class="ui-buttons"><a href="{p["url"]}">지점 수업·상담 안내</a>'
        if p['localities']:
            local=p['localities'][0];links+=f'<a href="{local["url"]}">{H.escape(local["name"])} 동네 학습 안내</a>'
        links+='</div></div>'
    return '<section class="ui-static-local"><h2>지역별 지점 안내도 살펴보세요</h2><p>아래는 지역별 안내의 예시입니다. 다른 지역은 이어지는 지점 검색과 전국센터 목록에서 찾아보세요.</p>'+links+'</section>'
def context(name):
    if name=='index.html':keys=[34,46,58]
    elif '과학' in name:keys=[49,38]
    elif '수학' in name:keys=[54,43]
    elif '영어' in name:keys=[56,55]
    elif '고등' in name or '고1' in name or '고2' in name:keys=[33,60]
    elif '초등' in name:keys=[32,59]
    elif '국어' in name:keys=[44,50]
    elif name.startswith('선생님찾기/'):keys=[57,56]
    else:keys=[55,47]
    chosen=[next(a for a in NEW if a['number']==k) for k in keys]
    chosen=[a for a in chosen if a['path']+'/index.html'!=name]
    links=''.join(f'<a href="{ui.href(a["path"])}">{H.escape(a["title"])}</a>' for a in chosen)
    return '<!-- useful-links:start --><section class="useful-related" aria-labelledby="useful-related-title"><h2 id="useful-related-title">공부와 상담에 도움이 되는 정보</h2><p>평가 안내를 읽거나 과제가 막힐 때, 지금 필요한 질문에 맞는 글을 골라 보세요.</p><div class="useful-related-links"><a href="/유용한정보/" class="useful-related-all">유용한정보 전체 보기 →</a>'+links+'</div></section><!-- useful-links:end -->'
def main():
    p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);args=p.parse_args();out=args.report_dir
    current=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'))
    baseline=json.loads((out/'baseline/release-public-manifest.json').read_text(encoding='utf-8-sig'))
    selection=json.loads((out/'selection.json').read_text(encoding='utf-8'))
    places=json.loads((ROOT/'assets/useful-places.json').read_text(encoding='utf-8-sig'))
    header=re.search(r'<header class="site-header".*?</header>',(ROOT/'index.html').read_text(encoding='utf-8-sig'),re.S)[0]
    header=re.sub(r' class="active"| aria-current="page"','',header).replace('data-useful-navigation','data-useful-navigation class="active" aria-current="page"')
    bynum={r['number']:r for r in selection['selection']}
    for a in NEW:
        row=bynum[a['number']];a['images']=row['images'];a['sourceFolder']=row['folder']
        assert len(a['images'])==3
        for im in a['images']:
            raw=(ROOT/im['path']).read_bytes();assert sha(raw)==im['sha256'];CHANGED[im['path']]=(sha(raw),None)
        page=ui.new_article(a,header).replace(ui.places(),static_places(a,places)+ui.places())
        save(a['path']+'/index.html',page)
    hubdata,page=ui.hub(header)
    page=page.replace('30개 주제','60개 주제').replace('기존 글과 연결되는 주제는 같은 주소에서 이어 볼 수 있습니다.','새롭게 추가한 30개 글과 기존 30개 주제를 함께 찾아보세요. 각 글에서 관련 가이드와 지역 안내로 이어갈 수 있습니다.')
    page=page.replace('위 주제와 겹치는 글은 같은 주소에 모았습니다. 나머지 59개 가이드는 아래 분야에서 찾거나 학습가이드 메뉴에서 검색할 수 있습니다.','기존 게시글도 함께 보존했습니다. 아래 59개 학습가이드에서 다른 질문과 기록 양식을 찾아보세요.')
    for a in NEW:
        anchor=f'<h3><a href="{ui.href(a["path"])}">'
        page=page.replace(anchor,'<span class="ui-new-label">새 글</span>'+anchor)
    save('유용한정보/index.html',page)
    preserved=[];scope=Counter()
    def transform(name):
        if name=='유용한정보/index.html':return None
        raw=(ROOT/name).read_bytes();text=raw.decode('utf-8-sig');before=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',text,flags=re.S)
        block=context(name)
        if '<!-- useful-links:start -->' in text:updated=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->',lambda _:block,text,flags=re.S,count=1)
        else:
            assert text.count('</main>')==1,name
            updated=text.replace('</main>',block+'</main>',1)
        restored=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',updated,flags=re.S)
        assert restored==before,name
        target=updated.replace('\r\n','\n').replace('\r','\n').replace('\n','\r\n').encode('utf-8')
        if raw.startswith(b'\xef\xbb\xbf'):target=b'\xef\xbb\xbf'+target
        changed=target!=raw
        if changed:(ROOT/name).write_bytes(target)
        return name,sha(target),sha(target.replace(b'\r\n',b'\n')),sha(before.replace('\r\n','\n').replace('\r','\n').encode('utf-8')),changed or sha(target)!=baseline['files'][name]
    with ThreadPoolExecutor(max_workers=12) as pool:
        for result in pool.map(transform,[n for n in baseline['files'] if n.endswith('.html')]):
            if result:
                name,d,t,b,changed=result
                if changed:CHANGED[name]=(d,t)
                preserved.append(dict(path=name,bodyWithoutContextSha256=b));scope[name.split('/')[0] if '/' in name else 'root']+=1
    css=(ROOT/'assets/useful-info.css').read_text(encoding='utf-8-sig')
    if '/* October information expansion */' not in css:
        css+='\n/* October information expansion */\n.ui-new-label{display:inline-block;align-self:flex-start;padding:2px 8px;font-size:12px;border:1px solid #b8863b;border-radius:3px;color:#725021;background:#fff9ec;margin-top:8px}.ui-local-card{padding:12px 0;border-bottom:1px solid rgba(26,36,64,.14)}.ui-local-card h3{font-size:18px;margin:10px 0}.ui-static-local{margin-top:32px}.ui-static-local>p{font-size:14px;color:#4d5770}@media(min-width:901px) and (max-width:1399px){.ui-page .ui-wrap{width:calc(100% - 180px);margin-left:32px;margin-right:auto;padding:0}.ui-page .ui-paper{max-width:800px;width:calc(100% - 200px);margin-left:32px;margin-right:auto;padding:32px}}\n'
    save('assets/useful-info.css',css)
    headercss=(ROOT/'assets/header.css').read_text(encoding='utf-8-sig')
    if '/* Useful links fixed-control spacing */' not in headercss:headercss+='\n/* Useful links fixed-control spacing */\n@media(min-width:901px) and (max-width:1499px){.useful-related{width:calc(100% - 200px);margin-left:32px;margin-right:auto}}\n'
    save('assets/header.css',headercss)
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'};sm=etree.parse(str(ROOT/'sitemap.xml'));root=sm.getroot()
    nodes={unquote(urlparse(n.findtext('s:loc',namespaces=ns)).path).strip('/'):n for n in root.findall('s:url',ns)}
    for a in [hubdata,*NEW]:
        node=nodes.get(a['path'])
        if node is None:node=etree.SubElement(root,'{'+ns['s']+'}url');etree.SubElement(node,'{'+ns['s']+'}loc').text=BASE+ui.href(a['path'])
        lm=node.find('s:lastmod',ns)
        if lm is None:lm=etree.SubElement(node,'{'+ns['s']+'}lastmod')
        lm.text=DATE
    save('sitemap.xml','<?xml version="1.0" encoding="UTF-8"?>\n'+etree.tostring(sm,encoding='unicode'))
    config=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8-sig'))
    for a in [hubdata,*NEW]:config['pages']['/'+a['path']]=dict(description=a['description'],sources=[a['description']])
    (ROOT/'seo-descriptions.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rss=etree.parse(str(ROOT/'rss.xml'));channel=rss.getroot().find('channel');existing={unquote(urlparse(i.findtext('link')).path).strip('/') for i in channel.findall('item')}
    feeddate=format_datetime(datetime(2026,10,5,12,0).astimezone());channel.find('lastBuildDate').text=feeddate
    for a in NEW:
        if a['path'] in existing:continue
        item=etree.SubElement(channel,'item')
        for k,v in dict(title=a['title'],link=BASE+ui.href(a['path']),guid=BASE+ui.href(a['path']),pubDate=feeddate,description=a['description']).items():etree.SubElement(item,k).text=v
        item.find('guid').set('isPermaLink','true')
        doc=html.fromstring((ROOT/a['path']/'index.html').read_bytes());article=copy.deepcopy(doc.xpath('//article')[0])
        for n in article.xpath('.//*[@data-ui-places]|.//nav'):n.getparent().remove(n)
        for n in article.xpath('.//a[starts-with(@href,"/")]'):n.set('href',BASE+n.get('href'))
        for n in article.xpath('.//img[starts-with(@src,"/")]'):n.set('src',BASE+n.get('src'))
        etree.SubElement(item,'{http://purl.org/rss/1.0/modules/content/}encoded').text=etree.CDATA(html.tostring(article,encoding='unicode'))
    save('rss.xml','<?xml version="1.0" encoding="UTF-8"?>\n'+etree.tostring(rss,encoding='unicode'))
    llms=(ROOT/'llms.txt').read_text(encoding='utf-8-sig');marker='## 추가 유용한정보 2026-10-05'
    if marker not in llms:llms+='\n'+marker+'\n'+''.join(f'- [{a["title"]}]({BASE+ui.href(a["path"])}): {a["description"]}\n' for a in NEW)
    save('llms.txt',llms)
    for name,(d,t) in CHANGED.items():
        current['files'][name]=d
        if t:current.setdefault('textSha256',{})[name]=t
    current['sitemapPages']=len(root.findall('s:url',ns));current['updatedDate']=DATE
    (ROOT/'release-public-manifest.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,data in [('catalog.json',NEW),('changed-public-files.json',sorted(CHANGED)),('changed-html.json',sorted(n for n in CHANGED if n.endswith('.html'))),('preserved-html.json',preserved)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(newArticles=len(NEW),existingMenuTopics=len(OLD),hubTopics=len(ui.ARTICLES),linkedOldPages=len(preserved),scope=dict(scope),images=90,publicFiles=len(current['files']),sitemapPages=current['sitemapPages'])
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
