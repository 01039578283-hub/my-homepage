"""Source-bounded crawl/content upgrade. Only reviewed release checkout is edited.

Original media is retained. Display strips keep the source width and all rows;
original-size zoom is available without scripting. Public manifests are updated
only for the exact changed files. Private audit records stay outside the site.
"""
import json, re, hashlib, shutil, sys
from pathlib import Path
from html import escape
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urlsplit, urljoin
from lxml import html, etree

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'C:\Users\1992k\Desktop\CodexData\outputs\wawa-crawl-content-20261005')
BASE='https://wawa-center.kr'; DATE='2026-10-06'
sys.path.insert(0,str(ROOT/'tools'))
from branch_course_guidance import course_guidance, format_grades
manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8'))
baseline=json.loads((OUT/'baseline-manifest.json').read_text(encoding='utf-8'))
pages=json.loads((OUT/'before-pages.json').read_text(encoding='utf-8'))
centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
teachers=json.loads((ROOT/'tools/teacher-profiles-source.json').read_text(encoding='utf-8'))['records']
curriculum=json.loads((ROOT/'tools/curriculum-content.json').read_text(encoding='utf-8'))
REGIONS=['서울','경기','인천','부산','대구','광주','대전','울산','세종','강원','충북','충남','전북','전남','경북','경남','제주']
by_teacher=defaultdict(list)
for t in teachers:by_teacher[t['branch']].append(t)
by_branch={(c['region'],c['routeName']):c for c in centers}
by_teacher_path={f'/선생님찾기/{c["region"]}/{c["routeName"]}/':c for c in centers}
by_local=defaultdict(list)
for c in centers:
 for n in c['neighborhoods']:by_local[n].append(c)
media={m['file']:m for m in json.loads((OUT/'before-media.json').read_text(encoding='utf-8'))}
changed={}; receipts=[]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,raw):
 if isinstance(raw,str):raw=raw.replace('\r\n','\n').replace('\r','\n').encode('utf-8')
 p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()==raw:return
 p.write_bytes(raw);changed[name]=sha(raw)
def esc(x):return escape(str(x),quote=True)
def href(p):return quote(p,safe='/#-')
def link(p,label):return '<a href="'+href(p)+'">'+esc(label)+' →</a>'
def node(markup):return html.fromstring(markup)
def cpath(c):return f'/지점안내/{c["region"]}/{c["routeName"]}/'
def regionpath(c):return '/동네안내/'+c['region']+'/'
def locality_id(c,n):return 'area-'+sha((c['district']+'/'+n).encode())[:12]

CSS='''/* Full-width source strips and factual local information. */
.cf-section{max-width:1120px;margin:28px auto;padding:26px 28px;background:#fff;border:1px solid #eadfd4;border-radius:16px;color:#2b2824;box-sizing:border-box;line-height:1.85}
.cf-section h2{font-size:clamp(1.25rem,2vw,1.65rem);line-height:1.45;margin:0 0 12px}.cf-section h3{font-size:1.1rem;margin:18px 0 8px}.cf-section p{margin:8px 0}.cf-kicker{color:#8d4b24;font-weight:700;font-size:.85rem}.cf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:18px}.cf-card{padding:20px;border:1px solid #e8ddd1;border-radius:12px;background:#fffcf8;min-width:0}.cf-card dl{margin:12px 0}.cf-card dt{font-size:.88rem;color:#6a5948;font-weight:700}.cf-card dd{margin:0 0 10px;overflow-wrap:anywhere}.cf-links{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.cf-links a{display:inline-block;border:1px solid #e0c6aa;border-radius:8px;padding:8px 12px;text-decoration:none;color:#57381c;background:#fff}.cf-links a:hover,.cf-links a:focus-visible{background:#fff0dd;outline:2px solid #915a25;outline-offset:2px}.cf-section table{width:100%;border-collapse:collapse;font-size:.95rem}.cf-section th,.cf-section td{text-align:left;vertical-align:top;border-bottom:1px solid #eadfd4;padding:7px 8px}.cf-section th{width:58px}.cf-note{color:#655a50;font-size:.9rem}.cf-section summary{cursor:pointer;font-weight:700}.cf-directory{max-width:1180px;margin:auto;padding:24px 20px}.cf-directory>header{padding:28px 0}.cf-directory h1{font-size:clamp(1.6rem,3vw,2.2rem);line-height:1.4}.cf-area{scroll-margin-top:95px}.cf-search label{display:block;font-weight:700}.cf-search input{width:min(100%,480px);padding:12px;border:1px solid #c9b4a0;border-radius:8px;font:inherit;box-sizing:border-box}.cf-search button{padding:12px;border:1px solid #c9b4a0;border-radius:8px;font:inherit;background:white;margin:6px}.cf-area[hidden]{display:none}
.cf-poster{width:100%;margin:0;line-height:0}.cf-poster>a{display:block;line-height:0}.cf-poster img{display:block!important;max-width:100%!important;width:100%!important;height:auto!important;margin:0!important;border:0!important;border-radius:0!important}.cf-image-note{display:block;line-height:1.65;font-size:.9rem;margin:10px 0;color:#665444}.cf-zoom-link{display:block;cursor:zoom-in}.cf-dialog{max-width:calc(100vw - 20px);width:1100px;max-height:90vh;padding:0;border:1px solid #b6a18c;border-radius:10px;background:#fff;color:#222}.cf-dialog::backdrop{background:rgba(0,0,0,.72)}.cf-dialog-header{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;gap:12px}.cf-dialog-header button{font:inherit;padding:8px 14px;background:#fff;border:1px solid #8e7560;border-radius:6px;cursor:pointer}.cf-dialog-scroll{max-height:76vh;overflow:auto;padding:8px;overscroll-behavior:contain}.cf-dialog-scroll img{display:block;max-width:none;height:auto}.cf-dialog-scroll[data-fit] img{max-width:100%;width:auto}.cf-dialog-header span{font-size:.88rem;line-height:1.4}.cf-dialog-footer{padding:8px 14px;font-size:.88rem}.cf-links a:focus-visible,.cf-zoom-link:focus-visible{outline:3px solid #b45d18}
@media(max-width:760px){.cf-section{margin:22px 16px;padding:20px 16px}.cf-card{padding:16px}.cf-links a{width:100%;box-sizing:border-box}.cf-dialog-header{flex-wrap:wrap}.cf-dialog-header button{font-size:.88rem}.cf-directory{padding:20px 16px}.cf-directory .cf-section{margin:20px 0}.cf-dialog-scroll img{max-width:none}.cf-section table{font-size:.88rem}}
@media(min-width:901px) and (max-width:1499px){.cf-section{width:calc(100% - 210px);margin-left:32px;margin-right:auto}.cf-directory .cf-section{width:calc(100% - 160px);margin-left:0}.cf-poster{max-width:100%}}
'''
JS='''/* Zoom enhances real original-image links; directory links exist in HTML. */
(()=>{let dialog,previous;function close(){if(!dialog)return;dialog.close();dialog.querySelector('img').removeAttribute('src');previous?.focus();}document.addEventListener('click',e=>{const a=e.target.closest('a[data-cf-zoom]');if(!a||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;if(typeof HTMLDialogElement==='undefined')return;e.preventDefault();previous=a;if(!dialog){dialog=document.createElement('dialog');dialog.className='cf-dialog';dialog.setAttribute('aria-label','안내 이미지 확대');dialog.innerHTML='<div class="cf-dialog-header"><span>원본 크기 · 좌우와 아래로 움직여 글씨를 읽으세요.</span><div><button type="button" data-fit-toggle>화면에 맞추기</button> <button type="button" data-close>닫기</button></div></div><div class="cf-dialog-scroll"><img alt=""></div><div class="cf-dialog-footer"><a target="_blank" rel="noopener">원본 파일 열기</a></div>';document.body.append(dialog);dialog.querySelector('[data-close]').addEventListener('click',close);dialog.querySelector('[data-fit-toggle]').addEventListener('click',()=>{const s=dialog.querySelector('.cf-dialog-scroll');s.toggleAttribute('data-fit');dialog.querySelector('[data-fit-toggle]').textContent=s.hasAttribute('data-fit')?'원본 크기로 보기':'화면에 맞추기';});dialog.addEventListener('cancel',e=>{e.preventDefault();close();});dialog.addEventListener('click',e=>{if(e.target===dialog)close();});}const im=dialog.querySelector('img');im.alt=a.getAttribute('aria-label')||'안내 이미지 원본';im.src=a.href;im.style.width=(a.dataset.originalWidth||918)+'px';dialog.querySelector('.cf-dialog-scroll').removeAttribute('data-fit');dialog.querySelector('[data-fit-toggle]').textContent='화면에 맞추기';dialog.querySelector('.cf-dialog-footer a').href=a.dataset.fullOriginal||a.href;dialog.showModal();});const input=document.querySelector('[data-cf-search]');if(input){const cards=[...document.querySelectorAll('[data-cf-area]')],count=document.querySelector('[data-cf-count]');const filter=()=>{const term=input.value.trim().toLowerCase();let n=0;cards.forEach(c=>{c.hidden=Boolean(term&&!c.textContent.toLowerCase().includes(term));if(!c.hidden)n++;});count.textContent=n+'개 동네 안내';};input.addEventListener('input',filter);document.querySelector('[data-cf-reset]')?.addEventListener('click',()=>{input.value='';filter();input.focus();});filter();}})();
'''
CSS+='\n@media(min-width:901px) and (max-width:1499px){.branch-answer{width:calc(100% - 160px);margin-right:auto;box-sizing:border-box}}\n'
style='assets/crawl-support.'+sha(CSS.encode())[:12]+'.css'
script='assets/crawl-support.'+sha(JS.encode())[:12]+'.js'
save(style,CSS);save(script,JS)

# Four shared posters only. Lossless whole-image conversion was measured and
# rejected because it enlarged files 3.4-3.7x. Full-width high-quality strips
# were separately measured; original bytes remain available on demand.
strips={}
for trial in json.loads((OUT/'segmentation-q92.json').read_text(encoding='utf-8')):
 original=trial['original'];assert trial['totalBytes']<original['bytes']
 parts=[]
 for p in trial['parts']:
  raw=Path(p['trial']).read_bytes();name='assets/crawl-support/'+sha(raw)[:20]+'.webp';save(name,raw);parts.append({**p,'src':'/'+name})
 assert parts[0]['start']==0 and parts[-1]['end']==original['height'] and all(a['end']==b['start'] for a,b in zip(parts,parts[1:]))
 strips[original['file']]={'original':original,'parts':parts,'totalBytes':trial['totalBytes']}
save('tools/crawl-poster-manifest.json',json.dumps(strips,ensure_ascii=False,indent=2)+'\n')

def local_name(row,d):
 if row['file'].startswith(('과목별학원/','학년별학원/')) and len(row['file'].split('/'))==4:return row['file'].split('/')[-2]
 for c in centers:
  for n in c['neighborhoods']:
   if row['h1'].startswith(n+' '):return n
 return ''
def match_centers(row,d):
 seg=row['file'].split('/')
 if seg[0]=='지점안내' and len(seg)>=4:return [by_branch[(seg[1],seg[2])]] if (seg[1],seg[2]) in by_branch else []
 matched=[]
 for a in d.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," teacher-related ")]//a[@href]'):
  path=unquote(urlsplit(urljoin(row['url'],a.get('href'))).path)
  if path in by_teacher_path and by_teacher_path[path] not in matched:matched.append(by_teacher_path[path])
 n=local_name(row,d)
 if not matched and n:
  matched=by_local.get(n,[])
 # A shared neighborhood name must not silently choose an unrelated city.
 if len(matched)>1:
  text=d.text_content();address_matched=[c for c in matched if c['address'] in text]
  if address_matched:matched=address_matched
 return matched
def context(row):
 s=unquote(row['file'])+row['h1']
 grade=re.search(r'(초[1-6]|중[1-3]|고[1-3])',s)
 level=next((x for x in ['초등','중등','고등'] if x in s),'')
 subject='영어' if '영어' in s and '수학' not in s else '수학' if '수학' in s and '영어' not in s else ''
 return grade.group() if grade else '',level,subject
def fact_card(c,row):
 grade,level,subject=context(row);selected=[subject] if subject else list(c['subjects'])
 prefix=grade[0] if grade else {'초등':'초','중등':'중','고등':'고'}.get(level)
 rows=''
 for s in selected:
  if s not in ['국어','영어','수학','과학','사회']:continue
  g=course_guidance(c,s,prefix)
  scope=format_grades(g['grades']) if g['grades'] else '개설 여부 문의'
  notes=' '.join(g.get('notes',[]))
  rows+=f'<tr><th scope="row">{esc(s)}</th><td>{esc(scope)}'+(f'<br><small>{esc(notes)}</small>' if notes else '')+'</td></tr>'
 route=cpath(c);t=by_teacher[c['sourceName']]
 teacher_text=' · '.join(x['name']+' 선생님' for x in t[:2])
 teacher_line=f'<p>소개 자료에서 {esc(teacher_text)}의 지도 방향을 살펴볼 수 있습니다. 담당 배정은 상담에서 확인하세요.</p>' if t else ''
 links=link(route+'#center-info',c['routeName']+' 위치·수강 조건')
 if t:links+=link('/선생님찾기/'+c['region']+'/'+c['routeName']+'/',c['routeName']+' 선생님 소개')
 links+=link(regionpath(c),c['region']+' 동네·지점 비교')
 current=[x for x in curriculum['subjects'] if x['subject']==(subject or '수학') and (x['grade']==grade if grade else (x['grade'].startswith(prefix) if prefix else x['grade'] in ['초6','중3','고1']))]
 current=[x for x in current if x['grade'] in c['subjects'].get(subject or '수학',[])][:2]
 curriculum_note=''
 if current:
  curriculum_note='<p><strong>학습 참고:</strong> '+esc(' / '.join(x['grade']+' '+x['subject']+' — '+x['focus'] for x in current))+' 학교 교과서와 평가 범위에 맞춰 확인하세요.</p>'
  for x in current:links+=link('/커리큘럼/'+x['grade']+'/'+x['subject']+'/',x['grade']+' '+x['subject']+' 공부 내용')
 return f'<article class="cf-card" data-cf-branch="{esc(c["routeName"])}"><h3>{esc(c["routeName"])} · {esc(c["district"])}</h3><dl><dt>주소</dt><dd data-cf-address>{esc(c["address"])}</dd><dt>방문할 때 확인할 위치</dt><dd>{esc(c["locationGuide"] or "방문 전 건물 출입구·호수와 귀가 동선을 확인해 주세요.")}</dd><dt>공통 상담 연락처</dt><dd><a href="tel:01039578283">010-3957-8283</a> · 희망 지점을 알려주세요.</dd></dl><table><caption>자료에 기재된 과목·학년과 확인 조건</caption><tbody>{rows}</tbody></table>{teacher_line}{curriculum_note}<div class="cf-links">{links}</div><p class="cf-note">자료의 안내 범위와 현재 시간표·담당 교사·등록 가능 여부는 구분해 확인하세요.</p></article>'
def facts(cs,row,d):
 role=(d.xpath('//*[@data-page-role]/@data-page-role') or [''])[0]
 heading='작성한 기록을 가져갈 지점의 확인 정보' if role.startswith('worksheet') else '수업을 비교하기 전에 확인할 위치·대상' if role=='comparison' else '방문 전 확인할 지점 정보'
 text='학교명만으로 수업이나 시험 대비 방식을 판단하지 마세요. 현재 교과서의 과목명·학교 범위표·프린트와 최근 답안을 함께 가져오면, 안내 학년과 필요한 학습 범위를 구체적으로 비교할 수 있습니다.'
 return node('<section class="cf-section" id="local-verified-info" aria-labelledby="local-verified-title" data-crawl-upgrade="20261005"><p class="cf-kicker">위치 · 수강 범위 · 상담 준비</p><h2 id="local-verified-title">'+heading+'</h2><p>'+text+'</p><div class="cf-grid">'+''.join(fact_card(c,row) for c in cs)+'</div></section>')

def strip_markup(data,alt):
 full='/'+data['original']['file'];parts=data['parts'];content='<div class="cf-poster" data-cf-original="'+full+'" data-cf-height="'+str(data['original']['height'])+'">'
 for i,p in enumerate(parts,1):
  content+=f'<a class="cf-zoom-link" href="{p["src"]}" data-cf-zoom data-original-width="{p["width"]}" data-full-original="{full}" aria-label="{esc(alt)} {i}구간 확대"><img src="{p["src"]}" width="{p["width"]}" height="{p["height"]}" alt="{esc(alt)} · {i}/{len(parts)} 구간" loading="lazy" decoding="async" data-cf-strip-start="{p["start"]}" data-cf-strip-end="{p["end"]}"></a>'
 content+='</div><span class="cf-image-note">각 구간을 누르면 글씨를 크게 볼 수 있습니다. '+f'<a href="{full}" data-cf-zoom data-original-width="918">전체 원본 안내 이미지 확대</a></span>'
 return content

def upgrade(row):
 name=row['file'];p=ROOT/name;raw=p.read_bytes();d=html.fromstring(raw)
 if d.xpath('//*[@data-crawl-upgrade="20261005"]'):return None
 family=name.split('/')[0];main=d.xpath('//main')[0];changed_body=False;receipt={'file':name,'originalImages':[],'posterCount':0,'maps':0,'facts':[],'rewordedParagraphs':0,'roleBefore':d.xpath('//*[@data-page-role]/@data-page-role')}
 cs=match_centers(row,d) if family in ['center','과목별학원','학년별학원','지점안내'] else []
 # Preserve source references and every map, while providing zoom and dimensions.
 for im in list(d.xpath('//img')):
  src=im.get('src','');absolute=unquote(urlsplit(urljoin(row['url'],src)).path).strip('/')
  receipt['originalImages'].append(absolute)
  if absolute in strips:
   parent=im.getparent();target=parent if parent.tag=='picture' else im
   fragment=html.fragments_fromstring(strip_markup(strips[absolute],im.get('alt') or row['h1']+' 본문 안내'))
   par=target.getparent();idx=par.index(target);tail=target.tail;par.remove(target)
   for el in fragment:par.insert(idx,el);idx+=1
   fragment[-1].tail=tail;receipt['posterCount']+=1;changed_body=True
  else:
   m=media.get(absolute)
   if m and not (im.get('width') and im.get('height')):
    im.set('width',str(m['width']));im.set('height',str(m['height']));changed_body=True
   ismap=('/maps/' in '/'+absolute or '지도' in im.get('alt','') or im.get('data-image-role')=='map')
   if ismap and im.getparent().tag!='a':
    a=node(f'<a class="cf-zoom-link" href="/{esc(absolute)}" data-cf-zoom data-original-width="{im.get("width","648")}" aria-label="{esc(im.get("alt") or row["h1"]+" 지도")} 원본 확대"></a>')
    im.addprevious(a);im.getparent().remove(im);a.append(im);receipt['maps']+=1;changed_body=True
   if ismap:im.set('loading','lazy')
 if cs:
  fact=facts(cs,row,d);images=main.xpath('.//*[contains(@class,"media-section") or contains(@class,"bulk-image-section") or contains(@class,"branch-primary-media")]')
  if images:images[0].addprevious(fact)
  else:main.insert(min(1,len(main)),fact)
  receipt['facts']=[c['routeName'] for c in cs];changed_body=True
  # Grade landing introductions must not imply verified school-specific teaching.
  if family=='학년별학원':
   for lead in main.xpath('.//p[contains(concat(" ",normalize-space(@class)," ")," math-hero-lead ")]'):
    for el in list(lead):lead.remove(el)
    lead.text=f'{row["h1"]}을 알아볼 때 현재 배우는 과목과 학교 평가 범위를 함께 확인하세요. 이 페이지의 학습 방법과 연결 지점의 과목·학년 자료를 대조하고, 시간표와 담당 배정은 상담에서 확인할 수 있습니다.'
  for label in main.xpath('//*[@data-source-field="high-schools"]//dt'):
   if label.text=='수업 가능 학교 자료':label.text='주변 학교 참고 자료'
 # Keep existing role forms, source manuscript and navigation; qualify generic claims.
 if family=='center' and d.xpath('//*[@data-page-role]'):
  for sec in main.xpath('./section[contains(@class,"article-local-feature-section")]'):
   heading=sec.xpath('./h2/text()') or sec.xpath('.//h2/text()')
   isteacher=any('선생님' in t for t in heading)
   for pnode in sec.xpath('.//article//p'):
    text=pnode.text_content().strip()
    if isteacher and text and not text.endswith('확인하세요.'):
     pnode.text='학생의 풀이 설명, 질문 해결 과정, 복습 기록 중 어떤 자료를 함께 보는지 상담에서 확인하세요. 실제 지도 방향은 연결된 지점 선생님 소개와 비교해 볼 수 있습니다.'
     for child in list(pnode):pnode.remove(child)
     receipt['rewordedParagraphs']+=1
 # Repetitive locality keywords add no additional factual information.
 n=local_name(row,d)
 if n and family in ['과목별학원','학년별학원']:
  for e in main.xpath('.//article[contains(concat(" ",normalize-space(@class)," ")," math-article ")]//p'):
   if e.get('data-source-paragraph') is not None:continue # workbook verbatim manuscripts are protected
   for t in [e,*list(e.iterdescendants())]:
    if not t.text or t.tag=='a':continue
    old=t.text;new=old
    for key in [f'{n} 고등 수학학원',f'{n} 고등 영어학원',f'{n} 초등 수학학원',f'{n} 중등 수학학원',f'{n} 영수 전문학원']:
     new=new.replace(key,'해당 수업')
    new=new.replace(f'{n}의 학부모','학부모').replace(f'{n} 학생','학생')
    if new!=old:t.text=new;receipt['rewordedParagraphs']+=1
 for case in main.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," math-case-item ")]'):
  if '가상' not in case.text_content() and '실제 수강 후기' not in case.text_content():
   note=node('<p class="cf-note">가상 상담 준비 예시입니다. 실제 수강 후기나 성적 향상 사례를 뜻하지 않습니다.</p>');case.insert(0,note);changed_body=True
 # Home retains every existing module, and gains a compact discovery route.
 if name=='index.html':
  block=node('<section class="cf-section" id="home-neighborhoods" data-crawl-upgrade="20261005"><p class="cf-kicker">동네에서 수업 찾기</p><h2>위치와 학습 자료를 함께 비교하세요</h2><p>지역을 고르면 동네별 연결 지점과 주소, 수강 범위, 선생님 소개를 확인할 수 있습니다. 수업 조건을 읽은 뒤 학생의 학습 기록과 공부 방법을 함께 살펴보세요.</p><div class="cf-links">'+link('/동네안내/','지역·동네별 지점 찾기')+link('/지점안내/','전체 지점 수강 안내')+link('/guide/','학습가이드')+link('/커리큘럼/','학년·과목별 공부 내용')+'</div></section>')
  resource=main.xpath('.//*[@id="home-resources"]');resource[0].addnext(block) if resource else main.insert(1,block);changed_body=True
 elif family in ['center','지점안내'] and not cs:
  block=node('<nav class="cf-section" data-crawl-upgrade="20261005" aria-label="동네와 지점 상세 안내"><h2>주소와 수강 범위로 지점 살펴보기</h2><p>지역별 동네 목록에서 연결된 지점의 위치와 과목·학년 자료를 함께 확인할 수 있습니다.</p><div class="cf-links">'+link('/동네안내/','동네별 지점 목록')+link('/지점안내/','지점 수강 안내 목록')+'</div></nav>');main.insert(min(1,len(main)),block);changed_body=True
 if changed_body or receipt['rewordedParagraphs']:
  if not d.xpath('//*[@data-crawl-upgrade]'):main.set('data-crawl-upgrade','20261005')
  # Only actual modified pages get the new date in matching schema fields.
  for el in d.xpath('//script[@type="application/ld+json"]'):
   data=json.loads(el.text or '{}')
   def dated(obj):
    if isinstance(obj,dict):
     if 'dateModified' in obj:obj['dateModified']=DATE
     for val in obj.values():dated(val)
    elif isinstance(obj,list):
     for val in obj:dated(val)
   dated(data);el.text=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
  for el in d.xpath('//*[@class="branch-page-dates"]//time'):
   if '최종 수정' in el.getparent().text_content() or '업데이트' in el.getparent().text_content():el.set('datetime',DATE);el.text=DATE
  head=d.xpath('//head')[0];head.append(node(f'<link rel="stylesheet" href="/{style}">'));head.append(node(f'<script defer src="/{script}"></script>'))
  out=b'<!doctype html>\n'+html.tostring(d,encoding='utf-8',method='html');save(name,out)
  receipt['roleAfter']=d.xpath('//*[@data-page-role]/@data-page-role')
  assert receipt['roleBefore']==receipt['roleAfter']
  return receipt
 return None

with ThreadPoolExecutor(max_workers=8) as pool:
 for i,result in enumerate(pool.map(upgrade,pages),1):
  if result:receipts.append(result)
  if i%3000==0:print(json.dumps({'processed':i,'changedPages':len(receipts)}),flush=True)

# Plain HTML region and neighborhood directory. Filtering is optional enhancement.
home_doc=html.fromstring((ROOT/'index.html').read_bytes());header=html.tostring(home_doc.xpath('//header[@data-site-navigation]')[0],encoding='unicode');footers=home_doc.xpath('//footer');footer=html.tostring(footers[0],encoding='unicode') if footers else ''
def shell(path,title,description,body,items):
 canonical=BASE+href(path);graph={'@context':'https://schema.org','@graph':[{'@type':'CollectionPage','@id':canonical+'#page','url':canonical,'name':title,'description':description,'inLanguage':'ko-KR','datePublished':DATE,'dateModified':DATE},{'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'홈','item':BASE+'/'},{'@type':'ListItem','position':2,'name':'동네안내','item':BASE+href('/동네안내/')}]+([{'@type':'ListItem','position':3,'name':title,'item':canonical}] if path!='/동네안내/' else [])},{'@type':'ItemList','numberOfItems':len(items),'itemListElement':[{'@type':'ListItem','position':i+1,'name':n,'url':BASE+href(p)} for i,(p,n) in enumerate(items)]}]}
 page='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(title)+' | 와와학습코칭센터</title><meta name="description" content="'+esc(description)+'"><meta name="robots" content="index, follow"><link rel="canonical" href="'+canonical+'"><meta property="og:url" content="'+canonical+'"><meta property="og:title" content="'+esc(title)+'"><meta property="og:description" content="'+esc(description)+'"><link rel="stylesheet" href="/assets/header.css"><link rel="stylesheet" href="/'+style+'"><script defer src="/'+script+'"></script><script type="application/ld+json">'+json.dumps(graph,ensure_ascii=False).replace('<','\\u003c')+'</script></head><body><a href="#main-content">본문으로 건너뛰기</a>'+header+'<main class="cf-directory" id="main-content" data-crawl-upgrade="20261005"><header><nav aria-label="현재 위치">'+link('/','홈')+' '+(link('/동네안내/','동네안내') if path!='/동네안내/' else '')+'</nav><p class="cf-kicker">위치와 학습 자료로 찾는 수업</p><h1>'+esc(title)+'</h1><p>'+esc(description)+'</p></header>'+body+'</main>'+footer+'</body></html>'
 save(path.strip('/')+'/index.html',page)
 return canonical
new_urls=[];region_items=[]
for region in REGIONS:
 cs=[c for c in centers if c['region']==region]
 if not cs:continue
 groups=defaultdict(list)
 for c in cs:
  for n in c['neighborhoods']:
   if c not in groups[(c['district'],n)]:groups[(c['district'],n)].append(c)
 body='<section class="cf-section"><h2>주소·동네·지점으로 찾기</h2><div class="cf-search"><label for="cf-search">동네명, 주소 또는 지점명</label><input id="cf-search" type="search" data-cf-search placeholder="예: 동네명 또는 지점명"><button type="button" data-cf-reset>전체 보기</button><p data-cf-count aria-live="polite">'+str(len(groups))+'개 동네 안내</p></div><p class="cf-note">검색하지 않아도 아래의 모든 동네와 지점 링크를 확인할 수 있습니다.</p></section>'
 items=[]
 for (district,n),local_centers in sorted(groups.items()):
  content='<section class="cf-section cf-area" id="'+locality_id(local_centers[0],n)+'" data-cf-area><h2>'+esc(district+' '+n)+'</h2><p>동네명은 연결 지점을 찾는 참고 범위입니다. 각 지점의 실제 주소와 학생의 등원 동선을 함께 확인하세요.</p><div class="cf-grid">'
  for c in local_centers:
   enrollment=next((p for p in [f'{cpath(c)}{n}수학학원/',f'{cpath(c)}{n}영어학원/'] if (ROOT/p.strip('/')/'index.html').exists()),cpath(c))
   items.append((enrollment,n+' '+c['routeName']+' 수강 안내'))
   links=link(enrollment,n+' 수강 대상·과목 안내')+link(cpath(c),c['routeName']+' 위치·방문 정보')
   selection='/과목별학원/고등수학학원/'+n+'/'
   if (ROOT/selection.strip('/')/'index.html').exists():links+=link(selection,'고등 수학 수업 선택 기준')
   content+='<article class="cf-card"><h3>'+esc(c['routeName'])+'</h3><p>'+esc(c['address'])+'</p><p>'+esc(c['locationGuide'] or '방문 전 건물 출입구와 호수를 확인하세요.')+'</p><div class="cf-links">'+links+'</div></article>'
  body+=content+'</div></section>'
 body+='<section class="cf-section"><h2>상담할 자료를 준비해 보세요</h2><p>학교 범위표, 최근 답안, 사용하는 교재와 가능한 공부 시간을 먼저 정리하세요. 안내 자료의 학년·과목이 학생의 현재 학교 과목과 같은지 확인하고, 수업 개설·담당 배정은 지점에서 확인해 주세요.</p><div class="cf-links">'+link('/guide/','상담과 복습에 쓸 학습가이드')+link('/커리큘럼/','학년·과목별 학습 내용')+'</div></section>'
 path='/동네안내/'+region+'/';new_urls.append(shell(path,region+' 동네별 학원·지점 안내',region+' 동네별 연결 지점의 주소와 수강 범위를 살펴보고 학생의 학습 자료로 상담을 준비하세요.',body,items));region_items.append((path,region+' 동네·지점 안내'))
body='<section class="cf-section"><h2>지역별 동네와 연결 지점</h2><p>수강 안내, 수업 선택 기준, 상담 점검표는 서로 다른 목적으로 활용할 수 있습니다. 먼저 실제 위치와 대상 학년을 확인한 뒤 학생에게 필요한 학습 정보를 선택하세요.</p><div class="cf-links">'+''.join(link(p,n) for p,n in region_items)+'</div></section><section class="cf-section"><h2>무엇부터 확인하면 좋을까요?</h2><ol><li>실제 지점 주소와 등원·귀가 동선을 확인하세요.</li><li>자료의 과목·안내 학년과 현재 학교 과목을 대조하세요.</li><li>최근 답안·교재·범위표로 필요한 복습과 상담 질문을 정리하세요.</li><li>수업 시간·비용·담당 교사·등록 가능 여부는 최신 상담에서 확인하세요.</li></ol><div class="cf-links">'+link('/지점안내/','전체 지점 안내')+link('/선생님찾기/','선생님 소개')+link('/guide/','공부 방법과 상담 준비')+'</div></section>'
new_urls.insert(0,shell('/동네안내/','지역·동네별 학원과 지점 찾기','동네별 연결 지점의 실제 주소와 과목·학년 자료, 수업 선택 기준을 함께 확인하세요.',body,region_items))

# Fingerprint CSS/JS referenced by HTML while retaining their directory. Every
# unchanged asset is reusable, and a changed file gets a different URL. This is
# a fixed content hash, not a per-request timestamp.
asset_versions={}
for name in list(manifest['files'])+[style,script]:
 if name.startswith('assets/') and name.endswith(('.css','.js')) and not re.search(r'\.[a-f0-9]{12}\.(css|js)$',name):
  raw=(ROOT/name).read_bytes();p=Path(name);version=p.with_name(p.stem+'.'+sha(raw.replace(b'\r\n',b'\n'))[:12]+p.suffix).as_posix();save(version,raw);asset_versions['/'+name]='/'+version
allhtml=[r['file'] for r in pages]+[unquote(urlsplit(u).path).strip('/')+'/index.html' for u in new_urls]
def fingerprint(name):
 p=ROOT/name;raw=p.read_text(encoding='utf-8');new=raw
 def update(m):
  q=urlsplit(m.group(2));path=unquote(q.path)
  return m.group(1)+asset_versions[path]+m.group(3) if path in asset_versions else m.group(0)
 new=re.sub(r'((?:src|href)=["\'])(/assets/[^"\']+)(["\'])',update,new)
 if new!=raw:save(name,new)
with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(fingerprint,allhtml))

# Only changed sitemap entries receive an actual modification date. Keep the
# 21,889 existing canonical URLs and their order. No unnecessary sitemap split.
ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
tree=etree.parse(str(ROOT/'sitemap.xml'));urlset=tree.getroot()
modified=[]
for entry in urlset:
 loc_el=entry.find('{'+ns['s']+'}loc')
 if loc_el is None:continue
 loc=loc_el.text;filename=unquote(urlsplit(loc).path).strip('/');filename=filename+'/index.html' if filename else 'index.html'
 if filename in changed:
  modified.append(loc);last=entry.find('{'+ns['s']+'}lastmod')
  if last is None:last=etree.SubElement(entry,'{'+ns['s']+'}lastmod')
  last.text=DATE
for u in new_urls:
 e=etree.SubElement(urlset,'{'+ns['s']+'}url');etree.SubElement(e,'{'+ns['s']+'}loc').text=u;etree.SubElement(e,'{'+ns['s']+'}lastmod').text=DATE
save('sitemap.xml',etree.tostring(tree,encoding='utf-8',xml_declaration=True,pretty_print=True))
conf=json.loads((ROOT/'vercel.json').read_text(encoding='utf-8'))
cache_files=sorted(set(asset_versions.values())|{'/'+style,'/'+script})
conf['headers']=[{'source':p,'headers':[{'key':'Cache-Control','value':'public, max-age=31536000, immutable'}]} for p in cache_files]+[{'source':'/assets/crawl-support/:path*','headers':[{'key':'Cache-Control','value':'public, max-age=31536000, immutable'}]}]
save('vercel.json',json.dumps(conf,ensure_ascii=False,indent=2)+'\n')
for name,hash in changed.items():
 if name.startswith('tools/') or name=='vercel.json':continue
 manifest['files'][name]=hash
 if re.search(r'\.(html|css|js|json|xml|txt|svg|webmanifest)$',name):manifest.setdefault('textSha256',{})[name]=sha((ROOT/name).read_bytes().replace(b'\r\n',b'\n'))
manifest['sitemapPages']=len(pages)+len(new_urls);manifest['generatedAt']=DATE
save('release-public-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
report={'date':DATE,'originalPublicPages':len(pages),'newPages':len(new_urls),'publicPages':manifest['sitemapPages'],'changedFiles':len(changed),'contentAndMediaPages':len(receipts),'factsPages':sum(bool(x['facts']) for x in receipts),'posterOccurrences':sum(x['posterCount'] for x in receipts),'mapZoomOccurrences':sum(x['maps'] for x in receipts),'rewordedParagraphs':sum(x['rewordedParagraphs'] for x in receipts),'originalMediaPreserved':all((ROOT/x['file']).stat().st_size==x['bytes'] for x in media.values()),'cacheAssets':len(cache_files),'modifiedUrls':modified+new_urls,'newUrls':new_urls}
(OUT/'change-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False),encoding='utf-8');(OUT/'implementation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'changed-files.json').write_text(json.dumps(sorted(changed),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if not k.endswith('Urls')},ensure_ascii=False,indent=2))
