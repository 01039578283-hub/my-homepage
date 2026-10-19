"""Reviewed, surgical cleanup. No URL, media, branch fact or page identity changes.

Only selected duplicate prose is consolidated. Matching school/branch facts and
FAQ answers are not treated as filler merely because they occur more than once.
The report stores every original changed file and a replayable change receipt.
"""
import argparse,collections,concurrent.futures,hashlib,json,re,zipfile
from pathlib import Path
from html import escape,unescape
from lxml import html

DATE='2026-10-19'
TOK=re.compile(r'<!--[\s\S]*?-->|<(script|style|title|textarea|iframe)\b[^>]*>[\s\S]*?</\1\s*>|</?(?:html|head|body)\b[^>]*>',re.I)
LD=re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',re.S|re.I)
COMMON_TEACHER='학생의 풀이 설명, 질문 해결 과정, 복습 기록 중 어떤 자료를 함께 보는지 상담에서 확인하세요. 실제 지도 방향은 연결된 지점 선생님 소개와 비교해 볼 수 있습니다.'
AREA_NOTE='동네명은 연결 지점을 찾는 참고 범위입니다. 각 지점의 실제 주소와 학생의 등원 동선을 함께 확인하세요.'
FIXES={'구체적인지 구체적으로':'학생의 자료와 일정에 맞는지','단계은':'단계는','오답를':'오답을','성남 금곡동 금곡동':'성남 금곡동','확인한 다음 다음':'확인하고 다음','보완한 다음 다음':'보완하고 다음'}
REPEATED=re.compile(r'(?<![가-힣])(실제|최근|먼저|기준|가장|구체적으로|지역|중등)\s+\1(?=[\s,.!?])')
GRADE_PARTICLE=re.compile(r'((?:초|중|고)[1-6](?:[·~](?:초|중|고)?[1-6])*)\s*(이|가|은|는|을|를)(?=\s)')
CSS='''.ed-record{margin:22px 0;padding:20px;border:1px solid #e5d7c8;border-radius:12px;background:#fffaf4;line-height:1.8;color:#302b25;box-sizing:border-box}.ed-record h3{font-size:1.1rem;margin:0 0 10px}.ed-record p{margin:8px 0}.ed-record table{width:100%;border-collapse:collapse;table-layout:fixed}.ed-record th,.ed-record td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #e5d7c8;overflow-wrap:anywhere}.ed-record th{font-weight:700}.ed-record caption{text-align:left;margin:8px 0;font-weight:700}.ed-common{margin:24px 0}.ed-common li{margin:10px 0}.ed-common strong{display:block}@media(max-width:600px){.ed-record{padding:14px}.ed-record table,.ed-record tbody,.ed-record tr,.ed-record td,.ed-record th{display:block;width:auto}.ed-record thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.ed-record td::before{content:attr(data-label) " · ";font-weight:700}.ed-record tr{border-bottom:1px solid #d7c4ad;padding:8px 0}.ed-record td,.ed-record th{border:0;padding:4px 0}.ed-record caption{display:block}}\n'''
STYLE='assets/editorial-records.'+hashlib.sha256(CSS.encode()).hexdigest()[:12]+'.css'

def grammar(s):
 for a,b in FIXES.items():s=s.replace(a,b)
 s=REPEATED.sub(r'\1',s)
 def particle(m):
  g,p=m.groups();closed=g[-1] in '136';pair=('이','가') if p in '이가' else ('은','는') if p in '은는' else ('을','를')
  return g+pair[0 if closed else 1]
 return GRADE_PARTICLE.sub(particle,s)

def structure(s):
 ts=[m for m in TOK.finditer(s) if re.match(r'</?(html|head|body)\b',m[0],re.I)]
 kind=lambda m:re.match(r'</?\w+',m[0])[0].lower()
 groups={k:[m for m in ts if kind(m)==k] for k in ['<html','</html','<head','</head','<body','</body']}
 if all(len(v)==1 for v in groups.values()):return s
 assert all(groups.values()) and len(groups['<body'])==len(groups['</body'])==1,'Unexpected document shape'
 # The known fragment defect occurs entirely before the real body. Refuse to
 # flatten a second embedded document elsewhere (for example in authored text).
 body=groups['<body'][0].start()
 keep={groups['<html'][0].start(),groups['</html'][-1].start(),groups['<head'][0].start(),groups['</head'][-1].start(),groups['<body'][0].start(),groups['</body'][0].start()}
 remove=[m for m in ts if m.start() not in keep]
 assert all(m.end()<=body for m in remove),'Nested body needs manual review'
 for m in reversed(remove):s=s[:m.start()]+s[m.end():]
 return s

def spans(s,tag):
 stack=[]
 for m in re.finditer(r'</?'+tag+r'\b[^>]*>',s,re.I):
  if not m[0].startswith('</'):stack.append(m)
  elif stack:
   a=stack.pop();yield a.start(),m.end(),s[a.start():m.end()]

def table(title,rows):
 return '<div class="ed-record"><h3>'+title+'</h3><p>아래는 학생이 직접 작성하는 기록 예시입니다. 실제 시험 일정과 배운 범위에 맞춰 바꾸세요.</p><table><caption>학습 내용 → 현재 기록 → 다음 확인</caption><thead><tr><th scope="col">학습 내용</th><th scope="col">현재 기록</th><th scope="col">다음 확인</th></tr></thead><tbody>'+''.join('<tr><th scope="row">'+a+'</th><td data-label="현재 기록">'+b+'</td><td data-label="다음 확인">'+c+'</td></tr>' for a,b,c in rows)+'</tbody></table></div>'

def visible_dates(s):
 return re.sub(r'(최종 수정\s*<time datetime=")[^"]+(">)[^<]+(</time>)',lambda m:m[1]+DATE+m[2]+DATE+m[3],s)

def transform(name,s):
 reasons=collections.Counter();old=s;s=structure(s)
 if s!=old:reasons['nestedDocument']=1
 # Three migrated guides closed the execution section twice, prematurely
 # closing the article body. Remove only the redundant closing pair.
 if name in {'guide/study-planner/index.html','guide/subject-study-plan/index.html','교육정보/오답노트-작성법/index.html'}:
  s,n=re.subn(r'(?<=</section>)</div></section>(\s*<section class="lg-section lg-example-box" id="lg-example">)',r'\1',s)
  if n:reasons['guideContainerNesting']=n
 # Edit actual text nodes, not href/src/IDs or executable code. Keep FAQ JSON
 # aligned with its visible answer when a reviewed grammar correction applies.
 token=re.compile(r'<!--[\s\S]*?-->|<(script|style|textarea|iframe)\b[^>]*>[\s\S]*?</\1\s*>|<[^>]*>|[^<]+',re.I)
 def textfix(m):
  x=m[0]
  if x.startswith('<'):return x
  y=grammar(x)
  if y!=x:reasons['wordingTextNodes']+=1
  return y
 s=token.sub(textfix,s)
 # Repeated teacher-feature paragraphs on worksheet pages become distinct,
 # actionable questions. Preserve the existing section and all non-text assets.
 patches=[]
 for a,b,block in spans(s,'section'):
  if 'article-local-feature-section' not in block.split('>',1)[0] or block.count(COMMON_TEACHER)<2:continue
  assert not re.search(r'<(?:a|img|iframe|script|input|textarea)\b',block),name
  heading='점검표를 바탕으로 선생님께 물어볼 질문' if 'data-page-role="worksheet' in s else '선생님 소개에서 확인할 질문'
  topic=name.split('/')[-2]
  if 'english' in topic and 'math' not in topic:
   q=['뜻을 아는 단어인데 문장이 이해되지 않을 때, 단어와 문장 구조 중 무엇부터 살펴볼까요?','답의 근거를 못 찾은 지문은 어떤 표시를 남겨 질문하면 좋을까요?','고쳐 쓴 문장을 며칠 뒤 혼자 다시 쓸 수 있는지는 어떻게 확인할까요?']
  elif 'math' in topic and 'english' not in topic:
   q=['풀이가 막힌 첫 줄을 보면 개념 부족과 조건 해석의 어려움을 어떻게 구분할까요?','맞힌 문제도 공식을 쓴 이유를 설명하지 못한다면 어떤 질문을 남기면 좋을까요?','해설을 본 풀이와 혼자 다시 푼 풀이를 비교할 때 무엇을 기록할까요?']
  else:q=['영어와 수학 중 혼자 시작하기 어려운 과제는 무엇이며, 어떤 자료로 보여 줄 수 있을까요?','설명을 듣고 끝낸 일과 도움 없이 다시 해낸 일을 어떻게 구분해 기록할까요?','다음 상담 전 학생이 직접 확인할 작은 목표는 무엇으로 정하면 좋을까요?']
  new=block[:block.index('>')+1]+'<h2>'+heading+'</h2><ul>'+''.join('<li>'+x+'</li>' for x in q)+'</ul></section>'
  patches.append((a,b,new));reasons['repeatedTeacherFeatureSections']+=1
 for a,b,new in sorted(patches,reverse=True):s=s[:a]+new+s[b:]
 # Put one explanation above the filter instead of repeating it in every area.
 if name.startswith('동네안내/') and s.count('<p>'+AREA_NOTE+'</p>')>1:
  count=s.count('<p>'+AREA_NOTE+'</p>');s=s.replace('<p>'+AREA_NOTE+'</p>','')
  marker='<section class="cf-section cf-search"'
  if marker in s:s=s.replace(marker,'<p class="cf-note">'+AREA_NOTE+'</p>'+marker,1)
  # A stable location before the first area remains visible when filtering.
  if AREA_NOTE not in s:
   m=re.search(r'<section\b[^>]*class="[^"]*cf-area',s);assert m,name
   s=s[:m.start()]+'<p class="cf-note">'+AREA_NOTE+'</p>'+s[m.start():]
  reasons['areaRepeatedNotesRemoved']=count-1
 # Individual teacher methods/questions remain; shared sentences are quoted
 # once with the names of the introductions in which they actually occur.
 intro=re.compile(r'(<p class="td-introduction">)(.*?)(</p>)',re.S)
 im=list(intro.finditer(s));replacements={}
 if len(im)>1:
  texts=[unescape(m[2]) for m in im];sentences=[re.split(r'(?<=[.!?])\s+',t.strip()) for t in texts];freq=collections.Counter(t for ss in sentences for t in set(ss) if len(t)>24)
  common={t for t,n in freq.items() if n>=2 and '선생님입니다' not in t}
  if common:
   notes=[]
   for t in sorted(common,key=lambda t:(next(i for i,ss in enumerate(sentences) if t in ss),t)):
    who=[ss[0].replace(' 선생님입니다.','') for ss in sentences if t in ss]
    notes.append('<li><strong>'+escape(' · '.join(who))+'</strong>'+escape(t)+'</li>')
   for m,oldtext,ss in reversed(list(zip(im,texts,sentences))):
    newtext=' '.join(t for t in ss if t not in common);assert len(newtext)>60
    replacements[oldtext]=newtext;s=s[:m.start()]+m[1]+escape(newtext)+m[3]+s[m.end():]
   s=s.replace('<div class="td-teacher-grid">','<section class="td-reading ed-common"><h2>소개글에서 함께 말하는 지도 방향</h2><ul>'+''.join(notes)+'</ul></section><div class="td-teacher-grid">',1)
   reasons['teacherSharedSentences']=sum(freq[t]-1 for t in common)
 # Exam planning and two-subject time allocation need different outputs. Do
 # not rewrite already useful selection criteria or existing worksheet forms.
 if re.match(r'과목별학원/(?:고등|중등)내신학원/[^/]+/index.html$',name):
  level=name.split('/')[1][:2]
  record=table('시험 범위와 오답을 한 장에 정리하기',[
   ('범위표 대조','교과서·학교 자료의 쪽수와 아직 확인하지 못한 범위를 따로 적습니다.','빠진 범위를 한 번 더 대조하고, 이미 익숙한 부분과 처음 볼 부분을 나눕니다.'),
   ('오답 원인','틀린 번호 옆에 개념·조건 누락·계산·표현 중 막힌 이유를 적습니다.','답을 가리고 다시 풀 날짜와 여전히 설명이 필요한 부분을 남깁니다.'),
   ('평가 조건' if level=='중등' else '과목별 남은 과제','학교가 안내한 제출일·준비물·답안 조건을 옮겨 적습니다.' if level=='중등' else '현재 이수 과목별로 남은 지문·문항·서술형 과제를 적습니다.','남은 날짜에 하루 분량을 배치하고 마지막 재확인 시간을 비워 둡니다.')])
  match=re.search(r'(<section id="section-04"[^>]*>\s*<h2>.*?</h2>)(.*?)(</section>)',s,re.S)
  if match and '<a ' not in match[2] and '<img' not in match[2]:
   s=s[:match.start()]+match[1]+record+match[3]+s[match.end():];reasons['examRoleRecord']=1
  lead=re.search(r'(<p class="math-hero-lead">)(.*?)(</p>)',s,re.S)
  if lead:
   h1=re.search(r'<h1[^>]*>(.*?)</h1>',s,re.S)[1];text=lead[2]
   text=re.sub(re.escape(h1)+r' 상담 전 .*?(?:확인해 보세요[.]?)$', '시험 범위·남은 과제·오답 재확인 날짜를 정리하는 데 활용하세요.',text)
   s=s[:lead.start()]+lead[1]+text+lead[3]+s[lead.end():]
 if 'data-page-role="time-allocation"' in s:
  level='초등' if '초등' in name else '중등' if '중등' in name else '고등'
  rows=[('영어','읽기·어휘·쓰기 중 오늘 끝낼 한 가지와 실제 걸린 시간을 적습니다.','모르는 단어와 설명이 필요한 문장을 구분해 다음 활동을 정합니다.'),('수학','연산·개념·풀이 중 막힌 단계와 도움받은 시간을 적습니다.','해설 없이 다시 풀 문항을 고르고 복습 시간을 별도로 남깁니다.'),('일정 조정','등하교·휴식·다른 과목을 뺀 시간을 확인합니다.','부모가 분량을 대신 늘리기보다 학생이 끝낼 수 있는 활동을 함께 고릅니다.' if level=='초등' else '마감이 가까운 과제와 누적된 약점을 나눠 이번 주 순서를 정합니다.')]
  marker='<nav class="overlap-role-links"'
  assert marker in s,name
  s=s.replace(marker,table(level+' 영어·수학 시간 배분 기록',rows)+marker,1);reasons['timeAllocationRecord']=1
 if reasons.get('examRoleRecord') or reasons.get('timeAllocationRecord') or reasons.get('teacherSharedSentences'):
  assert s.count('</head>')==1
  s=s.replace('</head>','<link rel="stylesheet" href="/'+STYLE+'"></head>',1)
 def schema(m):
  data=json.loads(m[2]);changed=False
  def walk(v):
   nonlocal changed
   if isinstance(v,dict):return {k:(DATE if k=='dateModified' and reasons else walk(x)) for k,x in v.items()}
   if isinstance(v,list):return [walk(x) for x in v]
   if isinstance(v,str):
    n=replacements.get(v,grammar(v));changed|=n!=v;return n
   return v
  new=walk(data)
  if new==data:return m[0]
  if changed:reasons['structuredTextAligned']+=1
  return m[1]+json.dumps(new,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+m[3]
 s=LD.sub(schema,s)
 if reasons:
  dated=visible_dates(s)
  if dated!=s:reasons['visibleModifiedDate']=1;s=dated
 return s,dict(reasons)

def run(root,out):
 m=json.loads((out/'before-manifest.json').read_text('utf-8'));inv=json.loads((out/'inventory.json').read_text('utf-8'));plan=[];totals=collections.Counter()
 def process(row):
  n=row['file'];b=(root/n).read_bytes();assert hashlib.sha256(b).hexdigest()==row['sha256'],n
  new,reasons=transform(n,b.decode('utf-8-sig'));nb=new.encode('utf-8')
  return n,b,nb,reasons
 with zipfile.ZipFile(out/'before-changed-html.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z,concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for i,(n,b,nb,reasons) in enumerate(pool.map(process,inv),1):
   if nb!=b:
    z.writestr(n,b);(root/n).write_bytes(nb);m['files'][n]=hashlib.sha256(nb).hexdigest()
    if 'textSha256' in m:m['textSha256'][n]=hashlib.sha256(nb.replace(b'\r\n',b'\n')).hexdigest()
    plan.append({'file':n,'sha256':m['files'][n],'reasons':reasons});totals.update(reasons)
   if i%3000==0:print('Processed',i,'changed',len(plan),flush=True)
 # Keep all old resources byte-for-byte. Add one content-addressed stylesheet.
 (root/STYLE).write_bytes(CSS.encode());m['files'][STYLE]=hashlib.sha256(CSS.encode()).hexdigest()
 if 'textSha256' in m:m['textSha256'][STYLE]=m['files'][STYLE]
 changed={r['file'] for r in plan};sm=(root/'sitemap.xml').read_text('utf-8')
 from urllib.parse import urlsplit,unquote
 def date(match):
  block=match[0];u=unquote(urlsplit(unescape(re.search(r'<loc>(.*?)</loc>',block)[1])).path);n=(u.strip('/')+'/index.html') if u!='/' else 'index.html'
  return re.sub(r'<lastmod>.*?</lastmod>','<lastmod>'+DATE+'</lastmod>',block) if n in changed else block
 sm=re.sub(r'<url>.*?</url>',date,sm,flags=re.S);(root/'sitemap.xml').write_bytes(sm.encode());m['files']['sitemap.xml']=hashlib.sha256(sm.encode()).hexdigest()
 if 'textSha256' in m:m['textSha256']['sitemap.xml']=m['files']['sitemap.xml']
 (root/'release-public-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8')
 (out/'review-plan.json').write_text(json.dumps({'pages':plan,'counts':dict(totals),'stylesheet':STYLE},ensure_ascii=False,indent=2),'utf-8')
 print(json.dumps({'changedPages':len(plan),'counts':dict(totals)},ensure_ascii=False),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args();run(args.root,args.report)
