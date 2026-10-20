"""Reviewed wording and role improvements; existing URLs and media are immutable.

Run against a baseline inventory, never against unreviewed authoring files.
The receipt and originals allow the exact edits to be independently replayed.
"""
import argparse,collections,concurrent.futures,hashlib,json,re,zipfile
from pathlib import Path
from urllib.parse import unquote,urlsplit,quote
from html import escape,unescape
from lxml import html
from editorial_html_cleanup import TOK,LD,spans,STYLE

DATE='2026-10-20'
TEXT=re.compile(r'<!--[\s\S]*?-->|<(script|style|textarea|iframe)\b[^>]*>[\s\S]*?</\1\s*>|<[^>]*>|[^<]+',re.I)
FIXES={'학원를':'학원을','학원와':'학원과','원고에서 살펴볼 학습 상황':'이런 학습 상황에 활용하세요','관련 원고 읽기:':'자세한 비교 질문:','아래 원고의 사례':'아래 학습 상황의 예시','제공된 원고를 바탕으로 상담에서 살펴볼 수 있는 상황을 정리한 사례형 예시':'상담 준비를 위해 구성한 가상 상황 예시','원고의 일반 학습 조언':'일반적인 학습 조언','동네별 원고에서':'동네별 학습 안내에서'}
def grammar(s):
 for a,b in FIXES.items():s=s.replace(a,b)
 for a,b in {'이 원고에서는':'아래 가상 상황에서는','원고의 취약 과목':'안내한 취약 과목','각 페이지는 제공된 동네별 원고와 센터·학교 자료를 사용합니다.':'동네별 학습 상황과 센터·학교 정보를 함께 살펴볼 수 있습니다.','지역별 원고와 제공된 센터 정보를 바탕으로':'지역별 학습 안내와 센터 정보를 함께 살펴보며','학원 원고를 보고':'학원 안내를 읽고','학교 정보가 없는 원고일수록':'학교 자료가 아직 준비되지 않았다면'}.items():s=s.replace(a,b)
 if '원고는 임의의 학교 사례' in s:
  s=re.sub(r'[^.!?]*페이지에는 학교명이 제공되지 않았기 때문에 (?:해당 수업|학원) 원고는 임의의 학교 사례를 사용하지 않습니다\.', '학교별 진도와 평가 방식은 학생이 가져온 자료로 확인해야 합니다.',s)
 s=re.sub(r'서술형 풀이과(?=\s)','서술형 풀이와',s)
 s=re.sub(r'[가-힣0-9·]+ 원고의 (최근 (?:풀이|학습 기록)·학교 자료·오답 회수 순서)를 읽고 학생의 실제 자료와 대조해 보세요\.',r'\1를 학생의 실제 학습 기록과 대조해 보세요.',s)
 return s

# Practical tasks, not promised branch classes or claims about student outcomes.
EXAMPLES={
 ('초6','수학'):('비율을 식과 그림으로 바꾸기','20개 중 5개를 고른 상황을 분수 5/20, 소수 0.25, 백분율 25%로 나타내고 세 표현이 같은 이유를 설명해 보세요.','분모를 전체로 잡았는지, 비율과 실제 개수를 구분했는지 확인합니다.'),
 ('중1','수학'):('문장 속 관계를 방정식으로 옮기기','한 개에 x원인 물건 3개와 500원짜리 물건을 샀더니 3,500원이 되었습니다. 3x+500=3500을 세우고 x=1000을 원래 상황에 대입해 보세요.','미지수의 뜻·단위와 등호 양쪽의 의미를 함께 설명합니다.'),
 ('중2','수학'):('표·식·그래프의 관계 확인하기','y=2x+1에서 x가 0, 1, 2일 때의 값을 표로 적고 좌표에 표시해 보세요. x가 1 증가할 때 y가 2 증가하는 것을 세 표현에서 찾아보세요.','계산한 점의 위치와 기울기를 혼동하지 않았는지 살펴봅니다.'),
 ('중3','수학'):('이차방정식의 해와 그래프 연결하기','x²−5x+6=0을 인수분해해 해를 구하고, y=x²−5x+6의 그래프가 x축과 만나는 x좌표가 2와 3인 이유를 설명해 보세요.','인수분해·영인수 법칙·함수값이 0인 조건 중 설명이 끊긴 단계를 표시합니다.'),
 ('고1','수학'):('조건에 맞는 풀이인지 대입해 보기','현재 교과서에서 이미 배운 방정식 한 문제를 골라 조건에 밑줄을 긋고 해를 구해 보세요. 구한 값을 원래 식과 문제 조건에 각각 대입해 보세요.','계산 결과가 맞아도 조건을 만족하지 않는 값이 없는지 확인합니다.'),
 ('고2','수학'):('선택과목에서 필요한 정의부터 확인하기','현재 이수하는 과목의 함수 문제 한 개를 고릅니다. 정의역과 주어진 조건을 먼저 적고, 그래프에서 읽은 정보가 식에서도 성립하는지 설명해 보세요.','과목명과 배운 단원을 적어 다른 선택과목의 내용을 섞지 않습니다.'),
 ('고3','수학'):('틀린 문제의 첫 접근 비교하기','최근 오답 한 문제의 해설을 가리고 첫 식이나 그림만 다시 적어 보세요. 처음 풀이와 비교해 놓친 조건을 표시한 뒤 비슷한 문제에서 같은 접근이 가능한지 확인합니다.','재풀이 정답 여부와 첫 접근에 걸린 시간을 따로 기록합니다.'),
 ('초6','영어'):('짧은 글의 순서 설명하기','이미 읽은 짧은 글에서 처음·다음·마지막에 일어난 일을 골라 그림이나 핵심 낱말로 정리한 뒤, 배운 표현으로 순서를 말해 보세요.','외운 문장을 그대로 반복했는지, 글의 순서를 이해해 말했는지 나누어 봅니다.'),
 ('중1','영어'):('교과서 대화의 상황 바꾸기','이미 배운 대화에서 사람·장소·시간 중 한 가지만 바꿔 질문과 답을 써 보세요. 원문을 가리고 소리 내어 읽은 뒤 뜻이 맞게 전달되는지 확인합니다.','바꾼 말에 따라 동사나 대명사도 달라지는지 교과서와 대조합니다.'),
 ('중2','영어'):('주장의 근거 문장 찾기','학교에서 읽은 짧은 지문을 한 문장으로 요약하고, 요약을 뒷받침하는 원문에 밑줄을 그어 보세요. 근거가 없는 내용을 요약에 넣지 않았는지 점검합니다.','문법을 아는 것과 글의 근거를 찾는 것을 별도로 기록합니다.'),
 ('중3','영어'):('배운 표현을 새 상황에 적용하기','교과서의 이유·비교 표현을 사용해 자신의 생활에 관한 문장 두 개를 써 보세요. 뜻을 먼저 정하고 교과서의 문장 구조와 비교해 고칩니다.','정답을 보고 고친 문장은 표시하고 다음 날 원문 없이 다시 써 봅니다.'),
 ('고1','영어'):('문단의 핵심과 근거 구분하기','현재 학교 지문에서 핵심 주장 한 문장과 이를 설명하는 예시를 구분해 표시하세요. 연결어를 가렸을 때 앞뒤 문장이 어떤 관계인지 말해 보세요.','낱말 뜻을 몰랐는지, 문단 사이의 논리를 놓쳤는지 나눠 기록합니다.'),
 ('고2','영어'):('긴 문장의 중심 구조 읽기','수업에서 읽은 긴 문장에서 주어·동사를 먼저 찾고 수식 부분을 괄호로 묶어 보세요. 문장 전체의 뜻을 정리한 뒤 앞뒤 문장과의 관계를 설명합니다.','아는 단어를 이어 붙인 해석과 문장 구조에 근거한 해석을 비교합니다.'),
 ('고3','영어'):('선택지마다 근거 대조하기','최근 틀린 독해 문제에서 선택지별로 지문의 근거를 적어 보세요. 근거가 없는 선택지와 지문의 내용을 반대로 바꾼 선택지를 나눕니다.','듣기 오답은 놓친 표현을 짧게 다시 듣고 대본 없이 확인한 결과를 남깁니다.')}

def context(root,inventory):
 names={r['file'] for r in inventory};curr=json.loads((root/'tools/curriculum-content.json').read_text('utf-8'))
 tasks={x['grade']+x['subject']:x for x in curr['subjects']};links={};grades=[]
 def read(row):
  n=row['file'];match=re.fullmatch(r'학년별학원/((?:초[1-6]|중[1-3]|고[1-3]))(수학|영어)학원/([^/]+)/index.html',n)
  if not match:return None
  d=html.fromstring((root/n).read_bytes());roots=[]
  for a in d.xpath('//*[@data-cf-branch]//a[@href]'):
   p=unquote(urlsplit(a.get('href')).path)
   if re.fullmatch(r'/지점안내/[^/]+/[^/]+/',p):roots.append(p)
  return n,match.groups(),sorted(set(roots))
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for row in pool.map(read,inventory):
   if not row:continue
   n,(g,sub,loc),roots=row;level={'초':'초등','중':'중등','고':'고등'}[g[0]]
   for base in roots:
    target=(base+loc+sub+'학원/'+level+'/').strip('/')+'/index.html'
    if target not in names:continue
    links.setdefault(target,[]).append({'file':n,'label':g+' '+sub+' 공부 방법','purpose':tasks[g+sub]['task']})
    links.setdefault(n,[]).append({'file':target,'label':base.split('/')[-2]+' '+level+' '+sub+' 수강 조건','purpose':'안내 학년·위치와 상담에서 확인할 수업 조건'})
 return {'tasks':tasks,'links':links}

def transform(name,s,ctx):
 reasons=collections.Counter();replacements={};old=s
 def tf(m):
  t=m[0]
  if t.startswith('<'):return t
  y=grammar(t)
  if y!=t:reasons['wordingTextNodes']+=1
  return y
 s=TEXT.sub(tf,s)
 match=re.fullmatch(r'(과목별학원|학년별학원)/([^/]+)/([^/]+)/index.html',name)
 if match:
  family,topic,loc=match.groups();d=html.fromstring(s);h1=d.xpath('//h1')[0].text_content();role=(d.xpath('//@data-page-role')or[''])[0]
  # Shorten repeated place-name prefixes only in prose headings, preserving
  # H1, title, location facts, existing anchors and matching TOC text.
  headingmap={}
  for el in d.xpath('//section[contains(@class,"math-prose-section")]/h2'):
   t=el.text_content();y=t
   if loc in t[:50]:
    y=re.sub(r'^.{0,45}?'+re.escape(loc)+r'(?:에서 |의 | )','',t,count=1)
    if y.startswith(('생활권에서 ','생활권의 ')):y=y.split(' ',1)[1]
   if y!=t and len(y)>=8:headingmap[t]=y
  if headingmap:
   s=TEXT.sub(lambda m:headingmap.get(unescape(m[0]),m[0]) if not m[0].startswith('<') else m[0],s);replacements.update(headingmap);reasons['specificHeadings']=len(headingmap)
  # Retain the first full keyword phrase in prose; subsequent repetitions
  # become a readable subject reference. Titles, labels and URLs stay intact.
  identity=h1.replace(' 선택 기준','');seen=0
  def para(m):
   nonlocal seen
   text=m[2]
   if '<' in text:return m[0]
   if identity in text:
    seen+=text.count(identity)
    if seen>1:
     subject='영어·수학' if '영수' in topic else '영어' if '영어' in topic else '수학' if '수학' in topic else '내신'
     text=text.replace(identity+'은',subject+' 수업은').replace(identity+'는',subject+' 수업은').replace(identity,subject+' 수업');reasons['repeatedKeywordParagraphs']+=1
     replacements[m[2]]=text
     if m[2].startswith('A. '):replacements[m[2][3:]]=text[3:]
   return m[1]+text+m[3]
  s=re.sub(r'(<p(?:\s[^>]*)?>)(.*?)(</p>)',para,s,flags=re.S)
  # Remove a second sentence repeating the same six-item checklist in a
  # different order, only within the six prose sections. Keep the first list.
  seenlists=set()
  def dedup(m):
   block=m[0]
   def pp(pm):
    kept=[]
    for sentence in re.split(r'(?<=[.!?])\s+',pm[2]):
     lists=re.findall(r'([가-힣A-Za-z0-9 ]+(?:·[가-힣A-Za-z0-9 ]+){4,}) 항목',sentence) if sentence.count('·')>=4 and ' 항목' in sentence else []
     key=None
     if lists:
      items=lists[0].split('·');items[0]=re.split(r'(?:때는 |에서 |다면 |려면 |는 )',items[0])[-1];key=tuple(sorted(x.strip() for x in items))
     if key and key in seenlists:reasons['duplicateChecklistSentences']+=1;continue
     if key:seenlists.add(key)
     kept.append(sentence)
    return pm[1]+' '.join(kept)+pm[3]
   return re.sub(r'(<p>)([^<]+)(</p>)',pp,block)
  s=re.sub(r'<section\b[^>]*class="math-prose-section"[^>]*>.*?</section>',dedup,s,flags=re.S)
  gm=re.fullmatch(r'((?:초[1-6]|중[1-3]|고[1-3]))(수학|영어)학원',topic)
  if family=='학년별학원' and gm and 'data-role-exercise' not in s:
   grade,subject=gm.groups();c=ctx['tasks'][grade+subject];ex=EXAMPLES.get((grade,subject))
   if ex:
    title,example,check=ex
    task='<div class="cf-card" data-role-exercise="'+grade+subject+'"><h3>'+escape(title)+'</h3><p>학교에서 이미 배운 범위에 맞춰 해 보는 '+grade+' '+subject+' 학습 예시입니다. 아직 배우지 않은 내용은 현재 단원의 문제로 바꾸세요.</p><p>'+escape(example)+'</p><ol><li>답이나 해설을 보기 전에 직접 해 봅니다.</li><li>'+escape(check)+'</li><li>막힌 부분 한 가지를 적고, 설명을 확인한 뒤 도움 없이 다시 해 봅니다.</li></ol><p>학습 과제: '+escape(c['task'])+'. 실제 교과서·학기 진도에 맞춰 적용하세요.</p></div>'
    # Replace only a generic two-sentence introduction; retain the page's
    # individual scenario and follow-up questions in the following paragraph.
    # A heading with attributes must never make the match scan into the next
    # section. Keep the first paragraph unless it is the reviewed boilerplate.
    sec=re.search(r'(<section id="section-02"[^>]*>\s*<h2(?:\s[^>]*)?>)([^<]*)(</h2>\s*)(<p(?:\s[^>]*)?>[^<]+</p>)',s,re.S) if grade.startswith('중') else None
    if sec:
     beforetitle=sec[2];newtitle=grade+' '+subject+'에서 직접 확인할 공부 과제';retained='' if '학원 선택은 반 이름보다' in sec[4] else sec[4];s=s[:sec.start()]+sec[1]+newtitle+sec[3]+retained+task+s[sec.end():]
     s=TEXT.sub(lambda m:newtitle if m[0]==beforetitle else m[0],s);replacements[beforetitle]=newtitle;reasons['gradePracticeRole']=1
    def grade_summary(mm):
     b=mm[0]
     return re.sub(r'(<h2[^>]*>).*?(</h2>)',r'\1'+grade+' '+subject+' 공부 전 확인할 내용'+r'\2',b,count=1)
    s=re.sub(r'<article class="math-summary-card">.*?</article>',grade_summary,s,flags=re.S)
    lead=re.search(r'(<p class="math-hero-lead">)([^<]*)(</p>)',s)
    if lead:
     sentences=re.split(r'(?<=[.!?])\s+',lead[2]);tail=' '.join(x for x in sentences if x.startswith('연결 지점은'))
     val=loc+' '+grade+' '+subject+' 공부에서 ‘'+c['task']+'’ 과제를 중심으로 최근 학습 기록을 점검합니다. '+tail+' 수업 대상과 일정은 연결 지점의 안내에서 별도로 확인하세요.'
     s=s[:lead.start()]+lead[1]+escape(val)+lead[3]+s[lead.end():];reasons['gradeStudyLead']=1
  if role=='selection-guide' and 'data-selection-scope' not in s:
   level='고등' if '고등' in topic else '중등';sub='영어' if '영어' in topic else '수학'
   intro=('고등학생은 현재 이수 과목·학교 평가 범위·혼자 공부할 시간을 기준으로 수업을 비교하세요. 아래의 특정 학년 사례는 비교 질문을 만드는 예시이며, 모든 학년의 상황을 대신하지 않습니다.' if level=='고등' else '중학생은 현재 학년·학교 진도·최근 답안을 함께 놓고 설명 방식과 복습 확인 방법을 비교하세요. 같은 학년이어도 먼저 보완할 부분은 다를 수 있습니다.')
   s=re.sub(r'(<p class="overlap-intro">.*?</p>)',lambda m:m[1]+'<p data-selection-scope>'+intro+'</p>',s,count=1,flags=re.S);reasons['selectionScope']=1
   # Clarify that the long-form summary describes a scenario, not an exclusive
   # service audience. Preserve all following address/school sentences.
   def summary(mm):
    b=mm[0];oldp=re.search(r'<p>(.*?)</p>',b,re.S);b,n=re.subn(r'(<p>).*?학생을 대상으로',r'\1'+loc+' '+level+' '+sub+' 수업을 비교하는 학부모를 위해 가상의 학습 상황을 예로 들어',b,count=1)
    if n and oldp:replacements[oldp[1]]=re.search(r'<p>(.*?)</p>',b,re.S)[1]
    if n:reasons['selectionScenarioScope']=1
    return b
   s=re.sub(r'<article class="math-summary-card">.*?</article>',summary,s,flags=re.S)
 bm=re.fullmatch(r'지점안내/([^/]+)/([^/]+)/([^/]+)(수학|영어)학원/(초등|중등|고등)/index.html',name)
 if bm:
  region,branch,loc,subject,level=bm.groups()
  lead=loc+'에서 '+branch+' '+level+' '+subject+' 수업을 알아볼 때 확인할 안내 학년·수업 조건·방문 정보를 정리했습니다. 학습 예시와 현재 개설 여부를 구분해 확인하고, 학생의 학교 자료와 희망 일정을 준비해 주세요.'
  s,n=re.subn(r'(<p class="branch-lead">)[^<]*(</p>)',lambda m:m[1]+lead+m[2],s,count=1)
  if n and s!=old:reasons['branchServiceRole']=1
 # Links are paired only when the existing factual card already points to the
 # same exact branch URL, as well as matching locality, subject and school level.
 additions=ctx['links'].get(name,[])
 if additions and 'data-role-followups' not in s:
  d=html.fromstring(s);existing={unquote(urlsplit(a).path).rstrip('/') for a in d.xpath('//a/@href')};chosen=[]
  for row in additions:
   p='/'+row['file'].removesuffix('index.html')
   if p.rstrip('/') not in existing:chosen.append((p,row));existing.add(p.rstrip('/'))
  if chosen:
   branch=name.startswith('지점안내/');lead='학생의 학년에 맞는 공부 방법을 이어서 확인하세요. 아래 글은 가정에서 활용할 학습 안내이며, 개설 수업이나 등록 가능 여부를 뜻하지 않습니다.' if branch else '학습 기록을 준비했다면 연결 지점의 안내 학년과 현재 수업 조건을 확인하세요.'
   block='<div data-role-followups><p>'+lead+'</p><div class="cf-links">'+''.join('<a href="'+quote(p,safe='/')+'">'+escape(row['label'])+'</a>' for p,row in chosen)+'</div></div>'
   marker='<div class="related-grid">' if branch else '<section class="teacher-related"'
   if marker in s:
    if branch:s=s.replace(marker,block+marker,1)
    else:s=s.replace(marker,'<section class="cf-section" aria-label="학습 기록 이후 수강 조건 확인">'+block+'</section>'+marker,1)
    reasons['relevantInternalLinks']=len(chosen)
 # Keep FAQ/Article wording aligned; never alter structured identifiers/URLs.
 def schema(m):
  data=json.loads(m[2])
  def walk(v,key=''):
   if isinstance(v,dict):return {k:walk(x,k) for k,x in v.items()}
   if isinstance(v,list):return [walk(x,key) for x in v]
   if isinstance(v,str):
    if key in ['@id','url','contentUrl','image','embedUrl']:return v
    if key=='dateModified' and reasons:return DATE
    return replacements.get(grammar(v),grammar(v))
   return v
  new=walk(data)
  if new==data:return m[0]
  reasons['structuredTextAligned']+=1
  return m[1]+json.dumps(new,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+m[3]
 s=LD.sub(schema,s)
 if reasons:s=re.sub(r'(최종 수정\s*<time datetime=")[^"]+(">)[^<]+(</time>)',lambda m:m[1]+DATE+m[2]+DATE+m[3],s)
 return s,dict(reasons)

def run(root,out):
 inv=json.loads((out/'inventory.json').read_text('utf-8'));m=json.loads((out/'before-manifest.json').read_text('utf-8'));ctx=context(root,inv);(out/'context.json').write_text(json.dumps(ctx,ensure_ascii=False),'utf-8');plan=[];counts=collections.Counter()
 def process(row):
  n=row['file'];b=(root/n).read_bytes();assert hashlib.sha256(b).hexdigest()==row['sha256'],n
  new,reasons=transform(n,b.decode('utf-8-sig'),ctx);return n,b,new.encode(),reasons
 with zipfile.ZipFile(out/'before-changed-html.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z,concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for i,(n,b,nb,reasons) in enumerate(pool.map(process,inv),1):
   if nb!=b:
    z.writestr(n,b);(root/n).write_bytes(nb);h=hashlib.sha256(nb).hexdigest();m['files'][n]=h;m['textSha256'][n]=hashlib.sha256(nb.replace(b'\r\n',b'\n')).hexdigest();plan.append({'file':n,'sha256':h,'reasons':reasons});counts.update(reasons)
   if i%3000==0:print('Reviewed',i,'changed',len(plan),flush=True)
 changed={r['file'] for r in plan};sm=(out/'before-sitemap.xml').read_text('utf-8')
 def date(mm):
  b=mm[0];p=unquote(urlsplit(unescape(re.search(r'<loc>(.*?)</loc>',b)[1])).path);n=p.strip('/')+'/index.html' if p!='/' else 'index.html'
  return re.sub(r'<lastmod>.*?</lastmod>','<lastmod>'+DATE+'</lastmod>',b) if n in changed else b
 sm=re.sub(r'<url>.*?</url>',date,sm,flags=re.S);(root/'sitemap.xml').write_bytes(sm.encode());m['files']['sitemap.xml']=hashlib.sha256(sm.encode()).hexdigest();m['textSha256']['sitemap.xml']=m['files']['sitemap.xml']
 (root/'release-public-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8');(out/'review-plan.json').write_text(json.dumps({'pages':plan,'counts':dict(counts)},ensure_ascii=False,indent=2),'utf-8');print(json.dumps({'changed':len(plan),'counts':dict(counts)},ensure_ascii=False),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();run(a.root,a.report)
