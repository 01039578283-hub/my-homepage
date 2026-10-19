"""Review/apply bounded prose edits without serializing documents or changing URLs.

Only text spans in reviewed prose blocks and existing center fact cards change.
The default command emits a review plan; --apply requires that plan's SHA-256.
"""
from __future__ import annotations
import argparse, ast, collections, hashlib, html as esc, json, re, sys, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from lxml import html

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from branch_course_guidance import course_guidance

def sha(b):return hashlib.sha256(b).hexdigest()
def norm(s):return ' '.join(s.split())
def literal_constants(path,names):
    found={}
    for n in ast.parse(path.read_text('utf-8')).body:
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name) and t.id in names:found[t.id]=ast.literal_eval(n.value)
    if set(found)!=set(names):raise ValueError(('Missing reviewed opener banks',path,names))
    return found

def opener_pattern():
    a=literal_constants(ROOT/'tmp/generate_subject_combined_pages.py',['CONTEXT_OBJECTS','CONTEXT_ACTIONS'])
    b=literal_constants(ROOT/'tmp/generate_subject_professional_pages.py',['SUBJECT_CONTEXT_BANKS','SUBJECT_ACTION_BANK'])
    # The old generator also rewrote these same openers by subject. Extract
    # its literal replacement dictionaries, without executing the generator.
    variants=[{}]
    tree=ast.parse((ROOT/'tmp/generate_subject_professional_pages.py').read_text('utf-8'))
    func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='reader_facing_text')
    for n in ast.walk(func):
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='replacements' for t in n.targets) and isinstance(n.value,ast.Dict):
            value=ast.literal_eval(n.value)
            if value:variants.append(value)
    groups=[]
    for objects,actions in [(a['CONTEXT_OBJECTS'],a['CONTEXT_ACTIONS']),([x for g in b['SUBJECT_CONTEXT_BANKS'].values() for x in g],b['SUBJECT_ACTION_BANK'])]:
        for pairs in variants:
            def variant(s):
                for old,new in pairs.items():s=s.replace(old,new)
                return s
            os={variant(x) for x in objects};acts={variant(x) for x in actions}
            groups.append('(?:'+'|'.join(re.escape(x) for x in sorted(os,key=len,reverse=True))+') (?:'+'|'.join(re.escape(x) for x in acts)+')')
    # Only exact, source-proven generated openers at a sentence boundary.
    return re.compile(r'(^|(?<=[.!?])\s+)(?:'+'|'.join(groups)+r')\s*')

def text_edit(value,h1,opener,counts,keyword):
    value,n=opener.subn(lambda m:m[1],value);counts['generated_openers_removed']+=n
    if keyword and h1:
        # Preserve the first literal keyword use in the prose; headings, links,
        # image attributes, structured data and FAQ answers are untouched.
        def shorter(m):
            counts['_keyword_seen']+=1
            if counts['_keyword_seen']<=1:return m[0]
            counts['repeated_full_heading_removed']+=1
            return '__CONTEXT_ACADEMY__'
        value=re.sub(re.escape(h1),shorter,value)
        value=value.replace('__CONTEXT_ACADEMY__ 상담','상담').replace('__CONTEXT_ACADEMY__의 제공 주소','연결 지점의 안내 주소')
        value=value.replace('__CONTEXT_ACADEMY__ 수업에서는','수업 계획을 세울 때는').replace('__CONTEXT_ACADEMY__','학원')
    # Remove internal keyword-generation terminology, retaining its actual question.
    value,n=re.subn(r'참고 키워드 [‘“][^’”]+[’”](?:을|를) [^.!?]{1,35}학부모의 질문으로 바꾸면', '수업 방식에 관해 확인할 질문은',value)
    counts['internal_keyword_labels_removed']+=n
    for old,new in [('준비을','준비를'),('준비은','준비는'),('안내을','안내를'),('안내은','안내는'),('기준를','기준을'),('더 덜 흔들릴','덜 흔들릴')]:
        if old in value:counts['grammar_corrected']+=value.count(old);value=value.replace(old,new)
    value,n=re.subn(r'^[^.!?]{1,35}에서 살펴볼 학생은 ', '다음은 학습 점검을 위한 가상 상황입니다. 예시의 학생은 ',value)
    counts['hypothetical_case_label']+=n
    value,n=re.subn(r'지역별 (?:초등|중등|고등) 학습 기준 선택의 기준','학원 선택의 기준',value)
    counts['redundant_selection_label']+=n
    # Exact remnants observed in the pre-edit all-page audit. These replacements
    # keep the surrounding practical advice, school list and factual conditions.
    for old,new in [('학원매출관리','학습 지원 체계'),('학원미납관리','비용·납부 안내'),('학원출입관리','출입·안전 관리'),('청결 관리 상담','학습 상담'),('학생이 가져온 실제 학교 자료를 바탕으로, 학생이 가져온','학생이 가져온')]:
        if old in value:counts['irrelevant_or_duplicate_labels_removed']+=value.count(old);value=value.replace(old,new)
    value,n=re.subn(r'^[^.!?:]{1,80} 본문에서 학교명은 제공 자료에 있는 다음 내용만 사용합니다:', '연결 지점 자료에 기재된 학교:',value)
    counts['editorial_school_instruction_rewritten']+=n
    sentences=re.split(r'(?<=[.!?])\s+',value)
    for i,sentence in enumerate(sentences):
        if '지역명만 바꾼 홍보가 아니라 제공된 지역·학교·주소 자료와 학생 유형을 바탕으로' in sentence and sentence.endswith('목적이 있습니다.'):
            sentences[i]='학교명이나 지역명만으로 수업 내용을 판단하지 말고, 학생이 받은 시험 범위표와 최근 답안을 기준으로 상담하세요.'
            counts['editorial_promotion_instruction_rewritten']+=1
    value=' '.join(sentences)
    return value

def facts_intro(center,role,old):
    # Material beneath this paragraph already supplies address/course facts.
    # Clarify use of those facts instead of adding another generic sales block.
    if role.startswith('worksheet'):
        return '점검표에 적은 학년·과목을 아래 지점의 안내 범위와 대조하세요. 상담할 때는 작성한 기록과 실제 답안을 함께 준비하면 됩니다.'
    if role=='selection-guide':
        return '비교한 수업 조건을 아래 지점 자료와 대조하세요. 안내 학년과 현재 등록 가능 여부는 다를 수 있으므로, 학생의 학교 자료와 희망 일정을 함께 확인하세요.'
    return old

def plan_page(row,centers,teachers,opener):
    path=ROOT/row['file'];raw=path.read_bytes();s=raw.decode('utf-8-sig');d=html.fromstring(s)
    counts=collections.Counter();replacements=[]
    def replace_exact(old,new,reason):
        nonlocal s
        if old==new:return
        # Callers supply the exact original tag; never replace unseen instances.
        if s.count(old)!=1:raise ValueError(('Non-unique edit',row['file'],reason,old[:100]))
        s=s.replace(old,new,1);replacements.append({'reason':reason,'before':old,'after':new})
    # Plain-text paragraph edits preserve every original element and attribute.
    # Match by exact DOM text, then require a unique source tag match.
    prose=d.xpath('//main//*[contains(concat(" ",normalize-space(@class)," ")," math-prose-section ") or contains(concat(" ",normalize-space(@class)," ")," branch-topic-article ") or contains(concat(" ",normalize-space(@class)," ")," english-review-item ") or contains(concat(" ",normalize-space(@class)," ")," math-case-item ")]//p')
    by_text=collections.defaultdict(list)
    for m in re.finditer(r'<p\b[^>]*>([^<]*)</p>',s,re.I):by_text[esc.unescape(m[1])].append(m[0])
    seen=set()
    for el in prose:
        if len(el) or el.get('id'):continue
        text=el.text or ''
        if text in seen:continue
        seen.add(text)
        tags=by_text.get(text,[])
        if len(tags)!=1:continue
        keyword=re.sub(r'\s+(?:선택 기준|상담 점검표|학습 점검표)$','',row['h1'])
        is_example=any(set(a.get('class','').split()) & {'english-review-item','math-case-item'} for a in el.iterancestors())
        edited=text_edit(text,keyword,opener,counts,not is_example)
        # Keep the substantive learning advice while marking hypothetical cases.
        if '이번 학생 유형' in edited:
            edited=edited.replace('이번 학생 유형','이 학습 상황 예시');counts['example_label_clarified']+=1
        if edited!=text:
            old=tags[0];new=re.sub(r'(?<=>)[^<]*(?=</p>$)',lambda _:esc.escape(edited),old)
            replace_exact(old,new,'prose_clarity')
    # A branch summary often starts by copying the hero lead verbatim. Retain
    # that sentence in the hero and the distinct advice in the summary.
    leads=d.xpath('//section[contains(@class,"branch-topic-hero")]/p[contains(@class,"branch-lead")]')
    if leads:
        lead=norm(leads[0].text_content())
        for el in d.xpath('//*[@id="article"]/section[1]/p'):
            text=el.text or ''
            if len(el)==0 and lead and text.startswith(lead) and len(text)>len(lead)+45:
                tags=by_text.get(text,[])
                if len(tags)==1 and tags[0] in s:
                    newtext=text[len(lead):].lstrip()
                    replace_exact(tags[0],re.sub(r'(?<=>)[^<]*(?=</p>$)',lambda _:esc.escape(newtext),tags[0]),'duplicate_lead_removed')
                    counts['duplicate_lead_removed']+=1
    # Existing verified cards receive actual, already-published teacher approach
    # information. No assignment of a subject/grade to a teacher is inferred.
    cards=d.xpath('//article[@data-cf-branch]')
    for card in cards:
        key=card.get('data-cf-branch');c=centers.get(key)
        if not c:raise ValueError(('Unknown fact card',row['file'],key))
        ps=card.xpath('./p[not(@class)]')
        intro=next((el for el in ps if norm(el.text_content()).startswith('소개 자료에서 ')),None)
        if intro is not None and not len(intro):
            text=intro.text or '';selected=[]
            for t in teachers.get(key,[]):
                if t['name']+' 선생님' in text:selected.append(t)
            if selected:
                newtext='소개 자료의 지도 방향: '+' · '.join(f"{t['name']} 선생님 — {t['approach'].split(' / ')[0]}" for t in selected)+'. 현재 담당 과목·학년과 배정은 상담에서 확인하세요.'
                tags=by_text.get(text,[])
                if len(tags)==1:
                    replace_exact(tags[0],re.sub(r'(?<=>)[^<]*(?=</p>$)',lambda _:esc.escape(newtext),tags[0]),'source_backed_teacher_approach')
                    counts['source_backed_teacher_approach']+=1
        # Display the precise selected grade when a grade page currently only
        # shows a broad school-level range; retain the full range and holds.
        exact=re.search(r'(초[1-6]|중[1-3]|고[1-3])\s*(영어|수학|국어|과학|사회)',row['h1'])
        if exact and row['path'].startswith('/학년별학원/'):
            grade,subject=exact.groups();view=course_guidance(c,subject,grade[0])
            for tr in card.xpath('./table/tbody/tr'):
                th=tr.find('th');td=tr.find('td')
                if th is None or td is None or norm(th.text_content())!=subject or len(td):continue
                topic=grade+('은' if grade[-1] in '136' else '는')
                if grade in view['grades']:prefix=f'{topic} 안내 범위에 포함됩니다. '
                elif grade in view['pendingGrades']:prefix=f'{topic} 현재 개설 여부 확인이 필요합니다. '
                else:prefix=f'{topic} 제공 자료에서 개설이 확인되지 않았습니다. '
                oldtext=td.text or ''
                if oldtext.startswith(prefix):continue
                # Scoped by the exact complete card block, including its branch.
                cm=re.search(r'<article\b[^>]*data-cf-branch="'+re.escape(esc.escape(key,quote=True))+r'"[^>]*>[\s\S]*?</article>',s)
                if not cm:raise ValueError(('Card source missing',row['file'],key))
                old=cm[0];needle='<td>'+esc.escape(oldtext)+'</td>'
                if old.count(needle)==1:
                    new=old.replace(needle,'<td>'+esc.escape(prefix+'지점의 해당 학교급 안내: '+oldtext)+'</td>',1)
                    replace_exact(old,new,'exact_grade_scope');counts['exact_grade_scope']+=1
    if len(cards)==1:
        c=centers[cards[0].get('data-cf-branch')]
        for el in d.xpath('//section[contains(concat(" ",normalize-space(@class)," ")," cf-section ")]/p'):
            # Keep the short visual kicker distinct from the explanatory text.
            if 'cf-kicker' in (el.get('class') or '').split():continue
            if len(el):continue
            text=el.text or '';newtext=facts_intro(c,row.get('role',''),text);tags=by_text.get(text,[])
            if newtext!=text and len(tags)==1 and tags[0] in s:
                replace_exact(tags[0],re.sub(r'(?<=>)[^<]*(?=</p>$)',lambda _:esc.escape(newtext),tags[0]),'role_specific_fact_guidance');counts['role_specific_fact_guidance']+=1
    # Clarify that region pages are connected to a particular real branch, not
    # a separately operating academy named after each search phrase.
    if len(cards)==1 and row['path'].startswith(('/학년별학원/','/과목별학원/')):
        c=centers[cards[0].get('data-cf-branch')]
        leads=d.xpath('//p[@class="math-hero-lead"]')
        if len(leads)==1 and len(leads[0])==0:
            oldtext=leads[0].text or '';tags=by_text.get(oldtext,[])
            if len(tags)==1 and tags[0] in s and '연결 지점은' not in oldtext:
                # Keep the page's existing purpose and append a short real identity.
                first,sep,rest=oldtext.partition('. ')
                if sep:
                    suffix=f"연결 지점은 {c['routeName']}({c['district']})입니다. "
                    # Replace the generic trailing operational disclaimer; the
                    # fact card and FAQ still retain the actual conditions.
                    newtext=first+'. '+suffix+rest
                    replace_exact(tags[0],re.sub(r'(?<=>)[^<]*(?=</p>$)',lambda _:esc.escape(newtext),tags[0]),'branch_identity_in_lead');counts['branch_identity_in_lead']+=1
    counts.pop('_keyword_seen',None)
    return {'file':row['file'],'path':row['path'],'beforeSha256':sha(raw),'afterSha256':sha(s.encode('utf-8')),'counts':dict(counts),'edits':replacements},s

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--audit-dir',type=Path,required=True);ap.add_argument('--apply',metavar='PLAN_SHA256');args=ap.parse_args();out=args.audit_dir
    if args.apply:
        pb=(out/'review-plan.json').read_bytes()
        if sha(pb)!=args.apply:raise ValueError('Review plan hash differs')
        plan=json.loads(pb);manifest=json.loads((ROOT/'release-public-manifest.json').read_text('utf-8'))
        with zipfile.ZipFile(out/'before-changed-html.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as backup:
            for i,row in enumerate(plan['pages']):
                p=ROOT/row['file'];b=p.read_bytes()
                if sha(b)!=row['beforeSha256']:raise ValueError(('Source drift',row['file']))
                s=b.decode('utf-8-sig')
                for e in row['edits']:
                    if s.count(e['before'])!=1:raise ValueError(('Edit drift',row['file'],e['reason']))
                    s=s.replace(e['before'],e['after'],1)
                b2=s.encode('utf-8')
                if sha(b2)!=row['afterSha256']:raise ValueError(('Output drift',row['file']))
                backup.writestr(row['file'],b);p.write_bytes(b2)
                manifest['files'][row['file']]=sha(b2);manifest['textSha256'][row['file']]=sha(b2.replace(b'\r\n',b'\n'))
                if i%3000==0:print('Applied',i,flush=True)
        # Edit only lastmod values for pages whose visible content changed.
        from lxml import etree
        from urllib.parse import unquote,urlsplit
        changed={r['path'] for r in plan['pages']};ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'};tree=etree.parse(str(ROOT/'sitemap.xml'))
        for e in tree.findall('s:url',ns):
            if unquote(urlsplit(e.find('s:loc',ns).text).path) in changed:
                lm=e.find('s:lastmod',ns)
                if lm is not None:lm.text='2026-10-19'
        tree.write(str(ROOT/'sitemap.xml'),encoding='utf-8',xml_declaration=True)
        b=(ROOT/'sitemap.xml').read_bytes();manifest['files']['sitemap.xml']=sha(b);manifest['textSha256']['sitemap.xml']=sha(b.replace(b'\r\n',b'\n'));manifest['updatedDate']='2026-10-19'
        (ROOT/'release-public-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'applied':len(plan['pages']),'counts':plan['counts']},ensure_ascii=False),flush=True);return
    inv=json.loads((out/'before-inventory.json').read_text('utf-8'))
    centers={c['routeName']:c for c in json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text('utf-8'))['centers']}
    teachers=collections.defaultdict(list)
    for t in json.loads((ROOT/'tools/teacher-profiles-source.json').read_text('utf-8'))['records']:teachers[t['branch']].append(t)
    opener=opener_pattern();pages=[];counts=collections.Counter();unchanged=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        def one(row):return plan_page(row,centers,teachers,opener)[0]
        for i,result in enumerate(pool.map(one,inv)):
            if result['edits']:pages.append(result);counts.update(result['counts'])
            else:unchanged.append(result['path'])
            if i%3000==0:print('Reviewed',i,flush=True)
    plan={'auditedPages':len(inv),'pages':pages,'unchanged':unchanged,'counts':dict(counts)}
    pb=json.dumps(plan,ensure_ascii=False,indent=2).encode('utf-8');(out/'review-plan.json').write_bytes(pb)
    print(json.dumps({'audited':len(inv),'changes':len(pages),'counts':dict(counts),'planSha256':sha(pb)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
