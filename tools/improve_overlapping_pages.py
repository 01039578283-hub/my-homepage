"""Apply reviewed page roles without changing any keeper or unrelated HTML page.

Run after legacy generators and before refreshing the release manifest. The
reviewed plan fixes the scope; this tool never infers more targets from keywords.
Only Python + lxml are required for authoring. Production serves static output.
"""
from __future__ import annotations
import argparse, hashlib, json, re, zipfile
from collections import Counter
from html import escape, unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit
from lxml import html as lh
from page_overlap_content import COMPARISONS, WORKSHEETS, worksheet_intro

ROOT=Path(__file__).resolve().parents[1]
VERSION='20260928'
DATE='2026-09-28'
STYLE=f'/assets/page-overlap-roles.css?v={VERSION}'
SCRIPT=f'/assets/page-overlap-roles.js?v={VERSION}'
OLD_LABELS={'collection':'영어수학학원','math':'수학학원','english':'영어학원','highschoolmath':'고등학생수학학원','highschoolenglish':'고등학생영어학원','middleschoolmath':'중학생수학학원','middleschoolenglish':'중학생영어학원','elementarymath':'초등학생수학학원','elementaryenglish':'초등학생영어학원','elementaryschool':'초등학생학원','middleschool':'중학생학원','highschool':'고등학생학원','mathenglish':'영수학원','wawaacademy':'와와학습코칭학원'}
ATTR=re.compile(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2',re.S)
LD=re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',re.S|re.I)
def attrs(tag):return {k.lower():unescape(v) for k,_,v in ATTR.findall(tag)}
def text(s):return ' '.join(unescape(re.sub('<[^>]*>','',s)).split())
def digest(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def norm(url):return unquote(urlsplit(url).path).rstrip('/') or '/'
def obj(s):return '을' if (ord(s[-1])-0xAC00)%28 else '를'

def spans(raw, tag, attr=None, value=None, token=False):
    for m in re.finditer(r'<'+tag+r'\b[^>]*>',raw,re.I):
        if attr is not None:
            found=attrs(m[0]).get(attr,'')
            if (value not in found.split()) if token else (found!=value):continue
        depth=1
        for end in re.finditer(r'</?'+tag+r'\b[^>]*>',raw[m.end():],re.I):
            depth+=-1 if end[0].startswith('</') else 1
            if depth==0:
                yield m.start(),m.end()+end.end(),m.end(),m.end()+end.start()
                break
        else:raise ValueError('Unclosed '+tag)

def block(raw,tag,attr,value,token=False):
    found=list(spans(raw,tag,attr,value,token))
    if len(found)!=1:raise ValueError(f'Expected one {tag}[{attr}={value}], got {len(found)}')
    a,b,c,d=found[0]
    return raw[a:b]

def update_inner(raw,tag,value,attr=None,match=None,token=False,optional=False):
    found=list(spans(raw,tag,attr,match,token))
    if optional and not found:return raw
    if len(found)!=1:raise ValueError(f'Expected one {tag}[{attr}={match}], got {len(found)}')
    _,_,a,b=found[0]
    return raw[:a]+value+raw[b:]

def replace_block(raw,tag,attr,value,replacement,token=False):
    old=block(raw,tag,attr,value,token)
    return raw.replace(old,replacement,1)

def model(target):
    parts=target['path'].strip('/').split('/')
    profile=target['profile']
    if parts[0]=='과목별학원':local=parts[2]
    else:
        match=re.fullmatch(r'(.*?)\s+'+r'\s*'.join(map(re.escape,OLD_LABELS[profile])),target['h1'])
        if not match:raise ValueError('Unrecognized locality/course title: '+target['h1'])
        local=match[1]
    if profile=='collection':
        h1=f'{local} 영어·수학 학습 점검표 모음'
        focus='학생의 학년과 기록할 내용에 맞는 양식 선택'
        lead=f'{local}에서 상담을 준비할 때 사용할 수 있는 학습 기록 양식입니다. 영어 답안, 수학 풀이, 공부 습관 중 먼저 정리할 내용을 골라 직접 작성해 보세요.'
        desc=f'{local}에서 영어·수학 상담을 준비할 때 학년별 점검표와 공부 기록 양식을 골라 작성하세요.'
        kind='worksheet-index'
    elif target['role']=='worksheet':
        label,focus,_=WORKSHEETS[profile]
        h1=f'{local} {label}'
        lead=worksheet_intro(local,profile)
        desc=f'{h1}에 {focus}{obj(focus)} 적고 상담 질문을 준비하세요.'
        kind='worksheet'
    else:
        p=COMPARISONS[profile]
        h1=f"{target['h1']} {p['suffix']}"
        focus=p['focus']
        lead=p['intro']
        desc=f"{target['h1']}의 {focus}{obj(focus)} 비교하고 상담에서 확인할 질문을 정리하세요."
        kind='feedback-comparison' if '전문' in profile else ('time-allocation' if '영수' in profile else 'selection-guide')
    if not 0<len(desc)<=80:raise ValueError(f'Description length {len(desc)}: {desc}')
    return dict(locality=local,h1=h1,title=h1+' | 와와학습코칭센터',description=desc,lead=lead,focus=focus,kind=kind)

def links_html(group, target, meta):
    keeper=group['keeper']
    parts=keeper['path'].strip('/').split('/')
    label=f'{parts[2]} 수강 대상·위치 안내' if parts[0]=='지점안내' else keeper['h1']+' 기본 안내'
    links=[(keeper['path'],label)]
    # At most one companion, with a genuinely different purpose.
    companions=[t for t in group['targets'] if t['path']!=target['path'] and t['role']!=target['role']]
    if companions:
        other=next((t for t in companions if t['profile'] not in ('수학전문학원','영어전문학원')),companions[0])
        links.append((other['path'],model(other)['h1']))
    return '<nav class="overlap-role-links" aria-label="목적에 맞는 다음 안내">'+''.join(f'<a href="{escape(url,quote=True)}">{escape(label)}</a>' for url,label in links)+'</nav>'

def module(raw,group,target,m):
    head=f'<section class="overlap-role" id="overlap-role" data-overlap-version="{VERSION}" data-page-role="{m["kind"]}" aria-labelledby="overlap-role-title">'
    kicker={'selection-guide':'수업을 고르기 전에','feedback-comparison':'수업 피드백 비교','time-allocation':'두 과목의 시간 배분','worksheet':'상담 준비 · 직접 작성','worksheet-index':'상담 준비 양식 모음'}[m['kind']]
    heading={'selection-guide':'학생 기록으로 선택 기준 정리하기','feedback-comparison':'수업 뒤 피드백을 비교하는 세 가지 기준','time-allocation':'영어와 수학에 쓸 시간을 나누는 기준','worksheet':'최근 학습 자료를 보며 직접 적어 보세요','worksheet-index':'지금 정리할 내용을 고르세요'}[m['kind']]
    module_intro={'selection-guide':'최근 기록과 맞는 항목부터 살펴보고, 상담에서 확인한 내용과 아직 남은 질문을 구분해 보세요.','feedback-comparison':'상담에서 들은 설명과 학생의 자료에서 직접 확인한 내용을 나란히 비교해 보세요.','time-allocation':'과목별로 남은 일과 실제 걸린 시간을 함께 보면, 이번 주에 먼저 할 공부와 복습할 시간을 정하기 쉽습니다.','worksheet':'모든 칸을 채울 필요는 없습니다. 학생이 직접 보여 줄 수 있는 기록부터 적어 보세요.','worksheet-index':'학년과 과목을 고르거나, 공부 습관·일정·상담 질문처럼 정리할 내용에 맞춰 시작해 보세요.'}[m['kind']]
    content=f'<p class="overlap-kicker">{kicker}</p><h2 id="overlap-role-title">{heading}</h2><p class="overlap-intro">{escape(module_intro)}</p>'
    if target['profile']=='collection':
        base=target['path']
        chosen=['elementaryenglish','elementarymath','middleschoolenglish','middleschoolmath','highschoolenglish','highschoolmath','elementaryschool','middleschool','highschool','mathenglish','wawaacademy']
        content+='<ul class="overlap-sheet-list">'+''.join(f'<li><a href="{escape(base+p+"/",quote=True)}">{escape(WORKSHEETS[p][0])}</a></li>' for p in chosen)+'</ul>'
    elif target['role']=='worksheet':
        content+=f'<form data-overlap-worksheet data-work-title="{escape(m["h1"],quote=True)}" autocomplete="off">'
        content+='<div class="overlap-work-grid">'
        for i,(label,helptext) in enumerate(WORKSHEETS[target['profile']][2],1):
            content+=f'<label class="overlap-work-field" for="work-field-{i}">{escape(label)}<small id="work-hint-{i}">{escape(helptext)}</small><textarea id="work-field-{i}" name="work-{i}" rows="3" aria-describedby="work-hint-{i}" data-work-label="{escape(label,quote=True)}"></textarea></label>'
        content+='</div><div class="overlap-work-actions"><button type="button" data-work-save>점검표 텍스트 저장</button><button type="reset">작성 내용 비우기</button></div><p class="overlap-work-note">작성 내용은 이 화면에서만 사용합니다. 보관하려면 텍스트로 저장하세요.</p><p class="overlap-work-status" data-work-status role="status" aria-live="polite"></p><noscript><p>항목을 종이나 메모 앱에 옮겨 작성할 수 있습니다. 텍스트 저장 버튼은 자바스크립트를 켜면 사용할 수 있습니다.</p></noscript></form>'
    else:
        content+='<div class="overlap-criteria">'
        for label,proof,question in COMPARISONS[target['profile']]['rows']:
            content+=f'<article class="overlap-criterion"><h3>{escape(label)}</h3><p><strong>학생 자료에서 볼 내용</strong>{escape(proof)}</p><p><strong>상담에서 확인할 내용</strong>{escape(question)}</p></article>'
        content+='</div>'
        doc=lh.fromstring(raw)
        sections=doc.xpath('//section[starts-with(@id,"section-")]/h2')
        if sections:
            node=sections[0]
            content+=f'<p><a class="overlap-manuscript-link" href="#{escape(node.getparent().get("id"),quote=True)}">관련 원고 읽기: {escape(text(node.text_content()))}</a></p>'
    content+=links_html(group,target,m)
    return '<!-- overlap-page-role:start -->\n'+head+content+'</section>\n<!-- overlap-page-role:end -->'

def preserved(raw):
    doc=lh.fromstring(raw)
    protected=doc.xpath('//article[contains(concat(" ",normalize-space(@class)," ")," math-article ")] | //section[contains(concat(" ",normalize-space(@class)," ")," article-local-feature-section ")] | //section[contains(concat(" ",normalize-space(@class)," ")," wawa-center-snippet ")]')
    return {'manuscripts':[digest(lh.tostring(n,encoding='unicode')) for n in protected],
            'images':[dict(n.attrib) for n in doc.xpath('//img')],
            'canonical':doc.xpath('//link[@rel="canonical"]/@href'),
            'robots':[(n.get('name'),n.get('content')) for n in doc.xpath('//meta[@name="robots" or @name="yeti" or @name="naverbot" or @name="googlebot"]')]}

def ensure_social_titles(raw,m):
    existing={a.get('name',a.get('property','')).lower() for a in (attrs(t) for t in re.findall(r'<meta\b[^>]*>',raw,re.I))}
    extra=''
    for key in ('og:title','twitter:title'):
        if key not in existing:extra+=f'<meta {"property" if key=="og:title" else "name"}="{key}" content="{escape(m["title"],quote=True)}">\n'
    return raw.replace('</head>',extra+'</head>',1) if extra else raw

def transform(raw,group,target):
    m=model(target)
    if f'data-overlap-version="{VERSION}"' in raw:return ensure_social_titles(raw,m),m
    original=preserved(raw)
    doc=lh.fromstring(raw)
    if len(doc.xpath('//h1'))!=1 or text(doc.xpath('//h1')[0].text_content())!=target['h1']:
        raise ValueError('Source H1 changed: '+target['path'])
    canonical=original['canonical'][0]
    raw=update_inner(raw,'title',escape(m['title']))
    raw=update_inner(raw,'h1',escape(m['h1']))
    def metadata(match):
        tag=match[0];a=attrs(tag);key=a.get('name',a.get('property','')).lower()
        value=m['description'] if key in ('description','og:description','twitter:description') else (m['title'] if key in ('og:title','twitter:title') else (DATE if key=='article:modified_time' else None))
        if value is not None:
            return re.sub(r'\bcontent\s*=\s*(["\']).*?\1','content="'+escape(value,quote=True)+'"',tag,count=1,flags=re.S)
        return tag
    raw=re.sub(r'<meta\b[^>]*>',metadata,raw,flags=re.I)
    raw=update_inner(raw,'span',escape(m['h1']),'aria-current','page')
    if target['role']=='comparison':
        raw=update_inner(raw,'p',escape(m['lead']),'class','math-hero-lead')
        hero=block(raw,'section','class','math-hero')
        hero=update_inner(hero,'p',escape({'selection-guide':'학습 선택 기준','feedback-comparison':'수업 피드백 비교','time-allocation':'영어·수학 시간 배분'}[m['kind']]),'class','math-eyebrow')
        raw=replace_block(raw,'section','class','math-hero',hero)
        # Supersede the older duplicate route panels with one purposeful panel.
        raw=re.sub(r'<!-- learning-routes:(top|bottom):start -->.*?<!-- learning-routes:\1:end -->\s*','',raw,flags=re.S)
        old=block(raw,'article','class','math-summary-card')
        revised=update_inner(old,'h2','원고에서 살펴볼 학습 상황')
        raw=raw.replace(old,revised,1)
        insertion=module(raw,group,target,m)
        raw=raw.replace(hero,hero+'\n'+insertion,1)
    else:
        # These legacy pages placed a very tall image before their H1. Keep
        # the same image bytes and ordering, but let the worksheet be usable
        # before readers scroll through the existing location media.
        media=[]
        for a,b,_,_ in spans(raw,'section','class','bulk-image-section',True):
            if a<raw.index('<main'):media.append(raw[a:b])
        for fragment in media:raw=raw.replace(fragment,'',1)
        hero=block(raw,'section','class','article-hero')
        revised=update_inner(hero,'p','상담 준비 · '+('양식 모음' if target['profile']=='collection' else '직접 작성'),'class','article-eyebrow')
        revised=revised.replace('</section>',f'<p class="overlap-hero-lead">{escape(m["lead"])}</p></section>')
        raw=raw.replace(hero,revised+'\n'+module(raw,group,target,m)+'\n'+'\n'.join(media),1)
        answer=block(raw,'section','class','article-search-answer')
        answer_title='작성할 양식을 고른 다음 확인하세요' if target['profile']=='collection' else '점검표를 작성하는 순서'
        replacement=f'<section class="article-search-answer" aria-label="상담 준비 기록 방법"><p class="article-answer-kicker">기록 활용 안내</p><h2>{answer_title}</h2><p class="article-answer-lead">최근 자료에서 실제로 확인한 내용과 아직 확인하지 못한 내용을 구분해 적어 보세요. 아래 학습 안내는 상담 질문을 구체화할 때 함께 참고할 수 있습니다.</p><ul class="article-answer-points"><li><span>1. 최근 자료 펼치기</span><p>지금 사용하는 교재, 학교에서 받은 자료, 최근 답안 중 현재 상황을 보여 주는 자료를 고릅니다.</p></li><li><span>2. 도움을 받은 부분 구분하기</span><p>혼자 해낸 내용과 설명 뒤 해결한 내용을 따로 적어 다음에 확인할 지점을 찾습니다.</p></li><li><span>3. 질문으로 정리하기</span><p>막힌 지점과 가능한 공부 시간을 바탕으로 상담에서 확인할 질문을 정리합니다.</p></li></ul></section>'
        raw=raw.replace(answer,replacement,1)
        summary=block(raw,'section','class','article-ai-summary',True)
        revised=update_inner(summary,'h2','학습 안내를 읽을 때 함께 볼 항목')
        revised=update_inner(revised,'p','작성한 기록과 아래 학습 안내를 함께 살펴보고, 상담에서 확인할 내용과 학생이 다시 시도할 내용을 구분해 보세요.','class','article-ai-lead')
        raw=raw.replace(summary,revised,1)
    def jsonld(match):
        payload=json.loads(match[2]);changed=False
        def visit(node):
            nonlocal changed
            if isinstance(node,list):
                for n in node:visit(n)
            elif isinstance(node,dict):
                typ=node.get('@type',[]);types=set(typ if isinstance(typ,list) else [typ])
                ids=[node.get('url'),node.get('@id'),node.get('mainEntityOfPage')]
                ids=[v.get('@id') if isinstance(v,dict) else v for v in ids]
                if types.intersection({'WebPage','CollectionPage','Article'}) and any(isinstance(v,str) and norm(v)==norm(canonical) for v in ids):
                    if 'Article' in types:node['headline']=m['h1']
                    else:node['name']=m['title']
                    node['description']=m['description'];node['dateModified']=DATE
                    if 'abstract' in node:node['abstract']=m['lead']
                    if 'WebPage' in types or 'CollectionPage' in types:
                        node['genre']={'worksheet':'학습 점검표','worksheet-index':'학습 점검표 모음','selection-guide':'학습 선택 기준','feedback-comparison':'수업 피드백 비교','time-allocation':'학습 시간 배분'}[m['kind']]
                        parts=node.setdefault('hasPart',[])
                        if not isinstance(parts,list):parts=[parts];node['hasPart']=parts
                        parts.append({'@type':'WebPageElement','@id':canonical+'#overlap-role','name':m['h1']})
                    changed=True
                if 'BreadcrumbList' in types:
                    for item in node.get('itemListElement',[]):
                        dest=item.get('item',item.get('url'))
                        url=dest.get('@id',dest.get('url','')) if isinstance(dest,dict) else dest
                        if isinstance(url,str) and norm(url)==norm(canonical):
                            item['name']=m['h1']
                            if isinstance(dest,dict) and 'name' in dest:dest['name']=m['h1']
                            changed=True
                for value in list(node.values()):visit(value)
        visit(payload)
        return match[1]+json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+match[3] if changed else match[0]
    raw=LD.sub(jsonld,raw)
    asset=f'<link rel="stylesheet" href="{STYLE}">'
    if target['role']=='worksheet' and target['profile']!='collection':asset+=f'\n<script defer src="{SCRIPT}"></script>'
    raw=raw.replace('</head>',asset+'\n</head>',1)
    raw=ensure_social_titles(raw,m)
    if preserved(raw)!=original:raise ValueError('Protected manuscript, image or index policy changed: '+target['path'])
    return raw,m

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--backup',type=Path,required=True)
    ap.add_argument('--report-dir',type=Path,required=True)
    ap.add_argument('--sample',action='store_true')
    ap.add_argument('--repair',action='store_true',help='Repair missing social titles or revised locality models without rewriting other applied pages')
    args=ap.parse_args()
    plan=json.loads((ROOT/'tools/page-overlap-plan.json').read_text(encoding='utf-8'))
    config=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8'))
    state_path=args.report_dir/'applied-state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    targets=[(g,t) for g in plan['groups'] for t in g['targets']]
    if args.sample:
        picked={}
        for g,t in targets:
            if model(t)['locality']=='하계동':picked[t['profile']]=(g,t)
        targets=list(picked.values())
    changed=0
    with zipfile.ZipFile(args.backup) as backup:
        try:
            for group,target in targets:
                file=ROOT/target['file'];current=file.read_bytes()
                m=model(target)
                if args.repair and all(state.get(target['path'],{}).get(k)==v for k,v in m.items()):
                    result=ensure_social_titles(current.decode('utf-8-sig'),m)
                else:
                    original=backup.read(target['file']).decode('utf-8-sig')
                    result,m=transform(original,group,target)
                sha=hashlib.sha256(current).hexdigest();next_bytes=result.encode('utf-8')
                if sha not in (target['sha256'],state.get(target['path'],{}).get('sha256'),hashlib.sha256(next_bytes).hexdigest()):
                    raise ValueError('Concurrent change; preserve it: '+target['path'])
                if current!=next_bytes:
                    file.write_bytes(next_bytes);changed+=1
                entry=config['pages'][target['path'].rstrip('/')]
                entry['sources']=list(dict.fromkeys([*entry['sources'],entry['description'],m['description']]))
                entry['description']=m['description']
                state[target['path']]={**m,'file':target['file'],'sha256':hashlib.sha256(next_bytes).hexdigest(),'keeper':group['keeper']['path']}
                if len(state)%1000==0:print('processed',len(state),flush=True)
        finally:
            state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            (ROOT/'seo-descriptions.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'processed':len(targets),'changed':changed,'totalApplied':len(state),'sample':args.sample},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
