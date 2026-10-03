"""Verify source coverage, every contextual target and preservation of the full public inventory."""
import argparse,hashlib,json,re,sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote,urlparse
from lxml import html,etree
from build_curriculum import DATA,ROOT,BASE,DATE,STYLE,START,END,href,label,subject_path,grade_path,level_records

def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,required=True);args=parser.parse_args();report=args.report_dir
    baseline=json.loads((report/'baseline-release-public-manifest.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'))
    catalog=json.loads((report/'catalog.json').read_text(encoding='utf-8'))
    linked=set(json.loads((report/'linked-existing.json').read_text(encoding='utf-8')))
    new={a['path']+'/index.html':a for a in catalog};files=set(manifest['files']);errors=[];counts=Counter()
    config=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8-sig'))['pages']
    ids_by_path={name:set(html.fromstring((ROOT/name).read_bytes()).xpath('//@id')) for name in new}
    def target(link,current=None):
        url=urlparse(link)
        if url.scheme and url.scheme not in ['http','https']:return None
        if url.netloc and url.netloc!='wawa-center.kr':return None
        if not url.path and url.fragment:name=current
        elif url.path.startswith('/'):
            path=unquote(url.path).lstrip('/')
            name=path if path in files else (path.rstrip('/')+'/index.html' if path else 'index.html')
        else:return 'relative URL '+link
        if name not in files:return 'missing target '+link
        if url.fragment and name in ids_by_path and unquote(url.fragment) not in ids_by_path[name]:return 'missing anchor '+link
        return None
    def check(name):
        local=[];tally=Counter();path=ROOT/name
        if not path.is_file():return ['missing file '+name],tally
        raw=path.read_bytes()
        if sha(raw)!=manifest['files'][name]:local.append('manifest hash '+name)
        if name in baseline['files'] and name not in linked and name!='sitemap.xml' and sha(raw)!=baseline['files'][name]:local.append('unexpected original file change '+name)
        if not name.endswith('.html'):return local,tally
        tally['html']+=1;text=raw.decode('utf-8-sig')
        if name in linked:
            tally['linkedExistingPages']+=1
            if text.count(START)!=1 or text.count(END)!=1 or text.count(STYLE)!=1:local.append('context section/style '+name)
            original=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',text,flags=re.S).replace(STYLE,'')
            normalized=original.replace('\r\n','\n').replace('\r','\n').encode('utf-8')
            expected=baseline.get('textSha256',{}).get(name)
            if expected not in {sha(normalized),sha(b'\xef\xbb\xbf'+normalized)}:local.append('original page content changed '+name)
            block=re.search(re.escape(START)+r'(.*?)'+re.escape(END),text,re.S)
            if block:
                node=html.fromstring(block[1])
                for link in node.xpath('.//a/@href'):
                    issue=target(link,name)
                    if issue:local.append(issue+' on '+name)
                    tally['contextLinks']+=1
            if text.count('id="cu-local-title"')!=1:local.append('duplicate context id '+name)
            # The inverse byte comparison above covers existing metadata, index rules, images and scripts.
            tally['preservedExistingHtml']+=1
        if name not in new:return local,tally
        a=new[name];doc=html.fromstring(raw);content=doc.xpath('//main')[0].text_content();canonical=BASE+href(a['path'])
        tally['newPages']+=1
        if doc.xpath('//link[@rel="canonical"]/@href')!=[canonical]:local.append('canonical '+name)
        if doc.xpath('//h1/text()')!=[a['title']]:local.append('heading '+name)
        if len(doc.xpath('//main'))!=1:local.append('main '+name)
        desc=doc.xpath('//meta[@name="description"]/@content')
        if desc!=[a['description']] or len(a['description'])>80 or not a['description'].endswith('.'):local.append('description '+name)
        if config.get('/'+a['path'],{}).get('description')!=a['description']:local.append('description config '+name)
        for sel in ['//meta[@property="og:description"]/@content','//meta[@name="twitter:description"]/@content']:
            if doc.xpath(sel)!=desc:local.append('social description '+name)
        ids=doc.xpath('//@id')
        if len(ids)!=len(set(ids)):local.append('duplicate IDs '+name)
        for link in doc.xpath('//a/@href|//script/@src|//link[@rel="stylesheet"]/@href'):
            if link.startswith('//'):local.append('protocol-relative link '+name+' '+link)
            issue=target(link,name)
            if issue:local.append(issue+' on '+name)
            tally['newPageLinks']+=1
        if len(doc.xpath('//*[@data-ui-places]'))!=1:local.append('branch finder '+name)
        if text.count('wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js')!=1:local.append('analytics '+name)
        if '편집 원칙' in content or '편집원칙' in content or 'C:\\Users' in content:local.append('private/editorial content '+name)
        graphs=[]
        for script in doc.xpath('//script[@type="application/ld+json"]'):
            try:graphs.extend(json.loads(script.text).get('@graph',[]))
            except Exception:local.append('schema JSON '+name)
        pages=[p for p in graphs if p.get('@type') in ['Article','CollectionPage']]
        if len(pages)!=1 or pages[0].get('url')!=canonical or pages[0].get('description')!=a['description']:local.append('page schema '+name)
        crumbs=[p for p in graphs if p.get('@type')=='BreadcrumbList']
        if len(crumbs)!=1 or crumbs[0]['itemListElement'][-1]['item']!=canonical:local.append('breadcrumb '+name)
        for c in crumbs:
            for item in c['itemListElement']:
                issue=target(item['item'])
                if issue:local.append('breadcrumb '+issue+' on '+name)
        row=next((r for r in DATA['subjects'] if subject_path(r)+'/index.html'==name),None)
        if row:
            tally['subjectPages']+=1
            for field in ['focus','task','scope','schoolCheck','summary']:
                if row[field] not in content:local.append('missing '+field+' '+name)
            for step in row['sequence'].split('→'):
                if step.strip() not in content:local.append('missing sequence '+name)
            if row['grade'] in ['초1','초2'] and row['subject']=='영어' and ('정규 교과가 아닌 선택 활동' not in content or '필수 선행 과정' not in content):local.append('early English distinction '+name)
            if row['grade'] in ['초1','초2'] and row['subject'] in ['사회','과학'] and '독립 정규 과목이 아닙니다' not in content:local.append('integrated subject distinction '+name)
            if row['grade'] in ['중3','고3'] and '2015 개정' not in content:local.append('2026 revision distinction '+name)
            if row['grade'] in ['중3','고3'] and '2027학년도 같은 학년' not in content:local.append('2027 distinction '+name)
            for level in level_records(row):
                for field in ['forWhom','task','next','materials']:
                    if level[field] not in content:local.append('missing level '+field+' '+name)
        if name=='커리큘럼/수준별-학습방법/index.html':
            for row in DATA['levels']:
                for field in ['forWhom','task','next','materials']:
                    if row[field] not in content:local.append('level source coverage '+row['stage']+' '+row['subject']+' '+field)
                for step in row['sequence'].split('→'):
                    if step.strip() not in content:local.append('level sequence source coverage')
                tally['levelMethods']+=1
        if name=='커리큘럼/고등-선택과목/index.html':
            for row in DATA['choices']:
                for field in ['name','category','scope','preparation','connection','schoolCheck']:
                    if row[field] not in content:local.append('choice source coverage '+row['name']+' '+field)
                tally['highCourseEntries']+=1
        if name=='커리큘럼/학교별-학습계획/index.html':
            for row in DATA['schoolChecks']:
                for field in ['item','where','action','caution']:
                    if row[field] not in content:local.append('school check source coverage '+row['item']+' '+field)
                tally['schoolChecks']+=1
        return local,tally
    print('Checking the full public inventory and every added context link.',flush=True)
    with ThreadPoolExecutor(max_workers=16) as pool:
        for i,(local,tally) in enumerate(pool.map(check,sorted(files)),1):
            errors.extend(local);counts.update(tally)
            if i%5000==0:print('Checked '+str(i)+' files.',flush=True)
    if not set(baseline['files'])<=files:errors.append('removed public files')
    expected_additions=set(new)|{'assets/curriculum.css','assets/curriculum.js'}
    if files-set(baseline['files'])!=expected_additions:errors.append('unexpected new public file scope')
    if len(new)!=85 or len(set(a['title'] for a in catalog))!=85 or len(set(a['description'] for a in catalog))!=85:errors.append('new page count/title/description uniqueness')
    expected_scope={n for n in baseline['files'] if n.endswith('.html') and (n.split('/')[0] in ['center','과목별학원','학년별학원','지점안내'] or n in ['index.html','guide/index.html','교육정보/index.html','유용한정보/index.html'])}
    if linked!=expected_scope:errors.append('incomplete neighborhood or branch-directory link scope')
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    def sitemap(path):
        return {n.findtext('s:loc',namespaces=ns):n.findtext('s:lastmod',namespaces=ns) for n in etree.parse(str(path)).xpath('//s:url',namespaces=ns)}
    oldsm=sitemap(report/'baseline-sitemap.xml');newsm=sitemap(ROOT/'sitemap.xml')
    if not oldsm.items()<=newsm.items():errors.append('existing sitemap URLs/dates changed')
    if len(newsm)!=manifest['sitemapPages'] or len(newsm)!=len(oldsm)+85:errors.append('sitemap count')
    if set(newsm)-set(oldsm)!={BASE+href(a['path']) for a in catalog}:errors.append('sitemap additions')
    if any(newsm.get(BASE+href(a['path']))!=DATE for a in catalog):errors.append('new sitemap dates')
    places=json.loads((ROOT/'assets/useful-places.json').read_text(encoding='utf-8'))
    for place in places:
        for link in [place['url'],*[n['url'] for n in place['localities']]]:
            issue=target(link)
            if issue:errors.append('finder '+issue)
            counts['branchFinderLinks']+=1
    result=dict(counts=counts,publicFiles=len(files),sitemapUrls=len(newsm),branches=len(places),errors=errors,errorCount=len(errors))
    (report/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(result,errors=errors[:15]),ensure_ascii=False,indent=2),flush=True);sys.exit(bool(errors))
if __name__=='__main__':main()
