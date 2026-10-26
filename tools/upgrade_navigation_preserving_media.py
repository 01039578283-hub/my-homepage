"""Improve discovery in place; existing routes, image markup and placement are invariant."""
import argparse, collections, hashlib, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from html import escape, unescape
from urllib.parse import unquote, urlsplit, quote, urljoin
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/navigation-upgrade-20261027'
DATE = '2026-10-27'
BASE = 'https://wawa-center.kr'
HEADER = re.compile(r'<header\b(?=[^>]*data-site-navigation="unified")[^>]*>.*?</header>', re.S)
MEDIA = re.compile(r'<(?:img|source|iframe|video)\b[^>]*>', re.I)
RAW = re.compile(r'<script\b[^>]*>[\s\S]*?</script>|<style\b[^>]*>[\s\S]*?</style>', re.I)

def digest(v):
    return hashlib.sha256(v if isinstance(v, bytes) else v.encode('utf-8')).hexdigest()

def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf-8')

def read(p):
    return p.read_text('utf-8-sig')

def public_pages(manifest):
    return [n for n in manifest['files'] if n.endswith('.html') and not n.startswith('assets/')]

def signature(s):
    d = html.fromstring(s)
    tree = d.getroottree()
    media = [(tree.getpath(e), sorted(e.attrib.items())) for e in d.xpath('//img|//picture/source|//iframe|//video')]
    main = d.xpath('//main')
    structure = [[e.tag, e.get('id'), e.get('class')] for e in main[0] if isinstance(e.tag,str)] if main else []
    return {'media': digest(json.dumps(media, ensure_ascii=False)),
            'mediaMarkup': digest('\n'.join(MEDIA.findall(RAW.sub('',s)))),
            'mediaCount': len(media), 'mainSections': structure,
            'canonical': d.xpath('//link[@rel="canonical"]/@href',smart_strings=False),
            'robots': d.xpath('//meta[@name="robots"]/@content',smart_strings=False),
            'ids': d.xpath('//@id',smart_strings=False),
            'title': d.xpath('string(//title)',smart_strings=False),
            'navURLs': [unquote(urlsplit(u).path) for u in d.xpath('//header//a/@href')]}

def baseline():
    if (REPORT/'baseline.json').exists():
        raise RuntimeError('Baseline already exists; never replace it with modified output')
    manifest = json.loads(read(ROOT/'release-public-manifest.json'))
    names = public_pages(manifest)
    def scan(name):
        return name, signature(read(ROOT/name))
    with ThreadPoolExecutor(max_workers=6) as pool:
        pages = dict(pool.map(scan, names))
    save(REPORT/'baseline.json', {'manifest': manifest, 'pages': pages,
         'vercel': json.loads(read(ROOT/'vercel.json')), 'robots': read(ROOT/'robots.txt'),
         'sitemap': digest(read(ROOT/'sitemap.xml'))})
    for n in ['index.html','assets/header.css','assets/branch-directory.js','assets/teacher-directory.js']:
        dest = REPORT/'originals'/n; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((ROOT/n).read_bytes())
    print(json.dumps({'baselinePages':len(pages),'mediaElements':sum(p['mediaCount'] for p in pages.values())}),flush=True)

GROUPS = [
 ('학원 안내', [('홈','/'),('학원소개','/overview/'),('학부모후기','/학부모후기/')]),
 ('지점 찾기', [('지점안내','/지점안내/'),('동네별 지점','/동네안내/'),('전국센터','/center/'),('선생님찾기','/선생님찾기/')]),
 ('수업·학년', [('과목별학원','/과목별학원/'),('학년별학원','/학년별학원/'),('커리큘럼','/커리큘럼/')]),
 ('학습자료', [('학습가이드 · 주제로 찾기','/guide/'),('교육정보 · 읽는 순서','/교육정보/'),('유용한정보 · 생활 속 질문','/유용한정보/')]),
]

def navigation(original, name):
    d = html.fromstring(original)
    links = {unquote(urlsplit(e.get('href')).path):e.get('href') for e in d.xpath('.//a[@href]')}
    logo = re.search(r'<a class="logo".*?</a>',original,re.S)[0]
    route = '/' + (name[:-10] if name.endswith('index.html') else name)
    items = []
    for label, entries in GROUPS:
        active = any((route==p if p=='/' else route.startswith(p)) for _,p in entries)
        children=[]
        for text,p in entries:
            href=links.get(p,quote(p,safe='/'))
            current = route==p if p=='/' else route.startswith(p)
            children.append('<a href="'+escape(href,quote=True)+'"'+(' aria-current="page" class="active"' if current else '')+'>'+text+'</a>')
        items.append('<details class="wn-group"'+(' data-section-current' if active else '')+'><summary>'+label+'</summary><div class="wn-panel">'+''.join(children)+'</div></details>')
    return '<header class="site-header" data-site-navigation="unified" data-navigation-upgrade="20261027"><nav class="nav" aria-label="주요 메뉴">'+logo+'<div class="wn-groups">'+''.join(items)+'<a class="wn-consult" href="/#consult">상담 안내</a></div></nav></header>'

def revision(s):
    # Header-only changes do not pretend that editorial information was updated.
    def update(m):
        graph=json.loads(m[2])
        def walk(n):
            if isinstance(n,list):
                for x in n:walk(x)
            elif isinstance(n,dict):
                if n.get('@type') in ['WebPage','CollectionPage','Article'] and 'dateModified' in n:n['dateModified']=DATE
                for v in n.values():
                    if isinstance(v,(list,dict)):walk(v)
        walk(graph)
        return m[1]+json.dumps(graph,ensure_ascii=False,separators=(',',':'))+m[3]
    return re.sub(r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)',update,s,flags=re.S)

def replace_block(s, selector, transform):
    # Serialize just an explicitly selected text-only container; never an image ancestor.
    d=html.fromstring(s); elements=d.xpath(selector)
    for e in reversed(elements):
        assert not e.xpath('.//img|.//source|.//iframe|.//video'),selector
        old=html.tostring(e,encoding='unicode',with_tail=False)
        # Source spans are found by exact start tag and balanced tag matching.
        tag=e.tag; ident=e.get('id')
        if ident:
            start=re.search(r'<'+tag+r'\b[^>]*\bid="'+re.escape(ident)+r'"[^>]*>',s)
        else:
            raise ValueError('Only stable-ID text blocks are editable')
        assert start,selector
        depth=1;end=None
        for m in re.finditer(r'</?'+tag+r'\b[^>]*>',s[start.end():]):
            depth += -1 if m[0].startswith('</') else 1
            if depth==0:end=start.end()+m.end();break
        assert end
        before=s[start.start():end];after=transform(before,e)
        s=s[:start.start()]+after+s[end:]
    return s

def apply():
    if (REPORT/'changes.json').exists():
        raise RuntimeError('Upgrade already applied; review the recorded changes instead of applying twice')
    base=json.loads(read(REPORT/'baseline.json'));manifest=json.loads(read(ROOT/'release-public-manifest.json'))
    sys.path.insert(0,str(ROOT/'tools'))
    from branch_course_guidance import course_guidance, GRADES
    centers=json.loads(read(ROOT/'tools/data/branch-directory/branches.json'))['centers']
    by_route={f'/지점안내/{c["region"]}/{c["routeName"]}/':c for c in centers}
    teacher=json.loads(read(ROOT/'tools/teacher-profiles-source.json'))
    from build_teacher_directory import EXCLUDED
    groups=collections.Counter(r['branch'] for r in teacher['records'] if r['branch'] not in EXCLUDED)
    matched=set(groups)&{c['sourceName'] for c in centers}
    missing=[c['sourceName'] for c in centers if c['sourceName'] not in groups]
    unmatched=sorted(set(groups)-matched)
    save(REPORT/'information-reconciliation.json',{'branchCount':len(centers),'teacherBranchGroups':len(groups),'matchedTeacherBranches':len(matched),'teacherOnlyNeedConfirmation':unmatched,'branchesWithoutTeacherProfiles':missing,'teacherRecords':sum(groups.values()),'factsUnchanged':True})
    assets={}
    for source in ['assets/navigation-upgrade.css','assets/navigation-upgrade.js','assets/branch-discovery.js','assets/teacher-discovery.js']:
        data=(ROOT/source).read_bytes();target=Path(source).with_name(Path(source).stem+'.'+digest(data)[:12]+Path(source).suffix).as_posix()
        (ROOT/target).write_bytes(data);assets[source]=target;manifest['files'][source]=digest(data);manifest['files'][target]=digest(data)
    style='<link rel="stylesheet" href="/'+assets['assets/navigation-upgrade.css']+'">'
    script='<script defer src="/'+assets['assets/navigation-upgrade.js']+'"></script>'
    changed=[];body_changed=[];counts=collections.Counter()
    for name in public_pages(manifest):
        s=read(ROOT/name);old=s
        assert len(HEADER.findall(s))==1,name
        s=HEADER.sub(lambda m:navigation(m[0],name),s,count=1)
        s=s.replace('</head>',style+script+'</head>',1)
        before_body=s
        if name=='index.html':
            replacements={
              '학원을 알아보고 있다면 지점·선생님 정보를, 공부 방법이 궁금하다면 학년과 상황에 맞는 글을 살펴보세요.':'가까운 지점의 수업 조건을 먼저 확인하거나, 학생의 고민에 맞는 학습자료부터 살펴보세요. 각 안내에서 다음에 확인할 내용으로 이어집니다.',
              '지점별 선생님 소개와 담당 분야를 살펴보고 상담할 지점과 연결해 보세요.':'지점별 선생님의 지도 방향을 읽어 보세요. 현재 담당 과목·학년과 배정은 지점 상담에서 확인합니다.',
              '과목별 공부법과 계획·시험·상담 주제를 검색하고, 기록 양식으로 직접 점검해 보세요.':'찾는 주제가 정해졌다면 검색·대상 선택으로 가이드를 찾고, 글에 연결된 기록 양식으로 실천해 보세요.',
              '수학 오답, 영어 독해, 공부 계획 등 지금의 어려움에 맞는 글을 순서대로 읽어 보세요.':'어디서 시작할지 고민된다면 오답·독해·계획 등 현재 어려움에 맞는 읽기 순서를 따라가 보세요.',
              '시험 준비, 방학 계획, 학습 도구와 상담 등 일상에서 필요한 정보를 골라 보세요.':'시험·방학·학습 도구·상담에서 생기는 구체적인 질문을 골라, 비교 기준과 실행 방법을 확인하세요.'}
            for a,b in replacements.items():
                assert a in s;s=s.replace(a,b)
            counts['homeClarity']+=1
        if name.startswith('지점안내/') and name.count('/')==3:
            route='/'+name[:-10];c=by_route[route]
            # Keep all image sections and facts in place; improve existing jump links.
            def contextual(block,e):
                links=e.xpath('.//*[@class="cf-links"]')
                if not links:return block
                oldlinks=re.search(r'<div class="cf-links">.*?</div>',block,re.S)
                if not oldlinks:return block
                extra='<a href="#branch-location">'+escape(c['routeName'])+' 지도 위치 →</a><a href="#consult">방문·상담 준비 확인 →</a>'
                return block[:oldlinks.end()-6]+extra+block[oldlinks.end()-6:]
            s=replace_block(s,'//*[@id="local-verified-info"]',contextual)
            # An actionable prompt, in the existing consultation paragraph.
            s=s.replace('현재 운영 과목과 시간표는 상담에서 최종 확인해 주세요.',escape(c['routeName'])+'과 학생의 학년·희망 과목을 함께 알려주세요. 현재 시간표·등록 가능 여부·교육비는 상담에서 확인합니다.')
            counts['branchConsultation']+=1
        if name.startswith('지점안내/') and name.count('/') in (1,2):
            # Explicit subject-grade pairs prevent independently matching different courses.
            def card(m):
                block=m[0];link=re.search(r'<a\b[^>]*href="([^"]+)"',block)
                if not link:return block
                route=unquote(urlsplit(unescape(link[1])).path);c=by_route.get(route)
                if not c:return block
                confirmed=[];pending=[]
                for subject in ['국어','영어','수학','과학','사회']:
                    scope=course_guidance(c,subject)
                    confirmed.extend(subject+':'+g for g in scope['grades'])
                    pending.extend(subject+':'+g for g in scope['pendingGrades'])
                data=' data-course-pairs="'+escape(' '.join(confirmed),quote=True)+'" data-pending-pairs="'+escape(' '.join(pending),quote=True)+'"'
                return block.replace(' data-branch-card',' data-branch-card'+data,1)
            s=re.sub(r'<article\b[^>]*data-branch-card[^>]*>.*?</article>',card,s,flags=re.S)
            gradeopts=''.join('<option value="'+g+'">'+g+'</option>' for g in GRADES)
            subopts=''.join('<option value="'+x+'">'+x+'</option>' for x in ['국어','영어','수학','과학','사회'])
            filters='<div class="wn-course-filters"><label for="branch-course-subject">과목<select id="branch-course-subject"><option value="">전체 과목</option>'+subopts+'</select></label><label for="branch-course-grade">학년<select id="branch-course-grade"><option value="">전체 학년</option>'+gradeopts+'</select></label></div><p class="wn-filter-note">센터 자료의 안내 범위로 찾습니다. 별도 확인이 필요한 학년은 검색 결과에 표시하며, 현재 개설·등록 가능 여부는 지점에 확인해 주세요.</p>'
            s=s.replace('<p class="branch-search-status"',filters+'<p class="branch-search-status"',1)
            s=re.sub(r'(?<=src=")/assets/branch-directory(?:\.[a-f0-9]+)?\.js(?:\?[^"]*)?', '/'+assets['assets/branch-discovery.js'],s)
            counts['branchFilters']+=1
        if name=='선생님찾기/index.html':
            oldcount=f'지점 {len(groups)}개 · 선생님 소개 {sum(groups.values())}개'
            newcount=f'소개 자료 {len(groups)}개 지점 · 선생님 소개 {sum(groups.values())}개'
            assert oldcount in s;s=s.replace(oldcount,newcount)
            note=f'<p class="wn-directory-note">지점안내와 연결된 소개는 {len(matched)}개 지점입니다. '+escape('·'.join(unmatched))+f'은 지점 정보 확인이 필요하며, '+escape('·'.join(missing))+'은 등록된 선생님 소개 자료가 없습니다. 아래 소개 자료 수는 지점안내의 전체 지점 수와 다릅니다.</p>'
            marker='<p class="td-results"';pos=s.index(marker);s=s[:pos]+note+s[pos:]
            s=re.sub(r'(?<=src=")/assets/teacher-directory(?:\.[a-f0-9]+)?\.js(?:\?[^"]*)?', '/'+assets['assets/teacher-discovery.js'],s)
            counts['teacherCountClarified']+=1
        if s!=before_body:
            s=revision(s);body_changed.append(name)
        sig=signature(s)
        assert sig['media']==base['pages'][name]['media'],name+': image placement changed'
        assert sig['mediaMarkup']==base['pages'][name]['mediaMarkup'],name+': media markup changed'
        if s!=old:
            (ROOT/name).write_text(s,'utf-8',newline='');manifest['files'][name]=digest(s);changed.append(name)
            if len(changed)%3000==0:print(json.dumps({'pagesUpdated':len(changed)}),flush=True)
    # Retain every URL and lastmod except pages whose actual main content changed.
    sm=read(ROOT/'sitemap.xml');body_paths={'/'+n[:-10] for n in body_changed}
    def lastmod(m):
        url=re.search(r'<loc>(.*?)</loc>',m[0]);route=unquote(urlsplit(unescape(url[1])).path)
        if route not in body_paths:return m[0]
        return re.sub(r'<lastmod>.*?</lastmod>','<lastmod>'+DATE+'</lastmod>',m[0])
    sm=re.sub(r'<url>.*?</url>',lastmod,sm,flags=re.S);(ROOT/'sitemap.xml').write_text(sm,'utf-8',newline='');manifest['files']['sitemap.xml']=digest(sm)
    # Hash new styles instead of altering an immutable cached asset.
    vc=json.loads(read(ROOT/'vercel.json'))
    for target in assets.values():
        vc['headers'].append({'source':'/'+target,'headers':[{'key':'Cache-Control','value':'public, max-age=31536000, immutable'}]})
    save(ROOT/'vercel.json',vc)
    for name in [*changed,'sitemap.xml',*assets.keys(),*assets.values()]:
        manifest.setdefault('textSha256',{})[name]=digest(read(ROOT/name).replace('\r\n','\n'))
    save(ROOT/'release-public-manifest.json',manifest)
    save(REPORT/'changes.json',{'pages':changed,'bodyPages':body_changed,'counts':dict(counts),'assets':assets})
    print(json.dumps({'changedPages':len(changed),'bodyPages':len(body_changed),'counts':dict(counts)},ensure_ascii=False),flush=True)

def verify(output):
    base=json.loads(read(REPORT/'baseline.json'));manifest=json.loads(read(ROOT/'release-public-manifest.json'))
    changes=json.loads(read(REPORT/'changes.json'));files=set(manifest['files']);errors=[]
    def check(ok,message):
        if not ok:errors.append(message)
    check(set(public_pages(manifest))==set(base['pages']),'public page set changed')
    config=json.loads(read(ROOT/'vercel.json'));oldconfig=base['vercel']
    check(config.get('redirects')==oldconfig.get('redirects'),'redirects changed')
    check(config.get('cleanUrls')==oldconfig.get('cleanUrls'),'URL normalization changed')
    check(read(ROOT/'robots.txt')==base['robots'],'robots changed')
    mediafiles=[n for n in base['manifest']['files'] if re.search(r'\.(?:png|jpe?g|gif|webp|avif|svg|ico|mp4)$',n,re.I)]
    check(all(manifest['files'].get(n)==base['manifest']['files'][n] for n in mediafiles),'image file manifest changed')
    for n in mediafiles:
        b=(ROOT/n).read_bytes()
        unchanged=digest(b)==base['manifest']['files'][n]
        if not unchanged and n.endswith('.svg'):
            unchanged=digest(b.replace(b'\r\n',b'\n'))==base['manifest'].get('textSha256',{}).get(n)
        if not unchanged:errors.append('image content changed: '+n)
    ids={};links=[];meta=[];total_media=0
    def scan(name):
        source=read(ROOT/name);sig=signature(source);d=html.fromstring(read(output/name));errs=[]
        for k in ['media','mediaMarkup','mediaCount','mainSections','canonical','robots']:
            if sig[k]!=base['pages'][name][k]:errs.append(name+': preservation '+k)
        if not set(base['pages'][name]['ids'])<=set(sig['ids']):errs.append(name+': existing anchors removed')
        if not set(base['pages'][name]['navURLs'])<=set(sig['navURLs']):errs.append(name+': previous navigation destination removed')
        if len(d.xpath('//h1'))!=1:errs.append(name+': h1')
        idlist=d.xpath('//@id',smart_strings=False)
        if len(idlist)!=len(set(idlist)):errs.append(name+': duplicate id')
        if len(d.xpath('//header//*[@class="wn-group"]'))!=4:errs.append(name+': grouped menu')
        if not d.xpath('//header//a[@href="/#consult"]'):errs.append(name+': consultation navigation')
        if len(d.xpath('//head/link[@href="/'+changes['assets']['assets/navigation-upgrade.css']+'"]'))!=1:errs.append(name+': navigation stylesheet is not in document head')
        if len(d.xpath('//head/script[@src="/'+changes['assets']['assets/navigation-upgrade.js']+'"]'))!=1:errs.append(name+': navigation script is not in document head')
        # Built HTML, rather than source-only links, is the deployed evidence.
        refs=d.xpath('//a/@href|//link/@href|//script/@src|//img/@src|//source/@src|//iframe/@src',smart_strings=False)
        for e in d.xpath('//img[@srcset]|//source[@srcset]'):
            refs.extend(x.strip().split()[0] for x in e.get('srcset').split(',') if x.strip())
        for e in d.xpath('//script[@type="application/ld+json"]'):
            try:json.loads(e.text or '{}')
            except Exception:errs.append(name+': structured data syntax')
        return name,errs,set(idlist),refs,d.xpath('string(//title)',smart_strings=False),sig['mediaCount']
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name,errs,idset,refs,title,num in pool.map(scan,public_pages(manifest)):
            errors.extend(errs);ids[name]=idset;links.extend((name,u) for u in refs);meta.append((name,title));total_media+=num
            if len(ids)%3000==0:print(json.dumps({'verifiedPages':len(ids)}),flush=True)
    resolved={}
    for name,ref in links:
        route='/' + name[:-10] if name.endswith('index.html') else '/'+name
        try:u=urlsplit(urljoin(BASE+route,ref))
        except Exception:errors.append(name+': invalid URL');continue
        if u.hostname!='wawa-center.kr':continue
        p=unquote(u.path).lstrip('/')
        if p not in resolved:
            candidates=[p,p.rstrip('/')+'/index.html' if p else 'index.html',p+'.html']
            resolved[p]=next((n for n in candidates if n in files),None)
        target=resolved[p]
        if not target:errors.append(name+': missing link '+ref)
        elif u.fragment and target in ids and unquote(u.fragment) not in ids[target]:errors.append(name+': missing anchor '+ref)
    oldpaths={tuple(p['canonical']) for p in base['pages'].values()}
    # XML parser is required for namespace-aware loc comparison.
    from lxml import etree
    sm=etree.fromstring((output/'sitemap.xml').read_bytes());locs=sm.xpath('//*[local-name()="loc"]/text()')
    check({unquote(u) for u in locs}=={unquote(x[0]) for x in oldpaths},'sitemap canonical inventory differs')
    check(len(locs)==len(set(locs))==len(base['pages']),'sitemap duplicates/count')
    summary={'pages':len(ids),'mediaElements':total_media,'imageFilesUnchanged':len(mediafiles),'linkAndResourceReferences':len(links),'changedBodyPages':len(changes['bodyPages']),'errors':len(errors),'examples':errors[:30]}
    save(REPORT/'verification.json',summary);save(REPORT/'verification-errors.json',errors)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if errors:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['baseline','apply','verify']);p.add_argument('--output',type=Path,default=ROOT/'.public-release');a=p.parse_args()
    {'baseline':baseline,'apply':apply,'verify':lambda:verify(a.output)}[a.mode]()
