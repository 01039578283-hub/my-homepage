"""Whole-inventory scope audit plus technical checks on every changed page."""
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlsplit
from html import unescape
import argparse, hashlib, json, re, zipfile
from lxml import html

ROOT=Path(__file__).resolve().parents[1]
def norm(s):return unquote(urlsplit(s).path).rstrip('/') or '/'
def plain(s):return ' '.join(s.split())
def walk(value):
    if isinstance(value,list):
        for child in value:yield from walk(child)
    elif isinstance(value,dict):
        yield value
        for child in value.values():yield from walk(child)
def digest(value):return hashlib.sha256(value).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report-dir',type=Path,required=True);args=ap.parse_args()
    inventory=json.loads((args.report_dir/'inventory.json').read_text(encoding='utf-8'))
    state=json.loads((args.report_dir/'applied-state.json').read_text(encoding='utf-8'))
    plan=json.loads((ROOT/'tools/page-overlap-plan.json').read_text(encoding='utf-8'))
    target_set={t['path'] for g in plan['groups'] for t in g['targets']}
    assert target_set==set(state),'Not all reviewed targets were applied'
    paths={norm(p['path']) for p in inventory}
    config=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8'))['pages']
    errors=[];results=[]
    def inspect(p):
        b=(ROOT/p['file']).read_bytes();sha=digest(b)
        if p['path'] not in state:
            return {'path':p['path'],'untouched':sha==p['sha256'],'error':[] if sha==p['sha256'] else ['Unrelated or keeper page changed']}
        expected=state[p['path']];raw=b.decode('utf-8-sig');doc=html.fromstring(raw);err=[]
        def check(ok,msg):
            if not ok:err.append(msg)
        check(sha==expected['sha256'],'Changed after application')
        check(doc.xpath('//title/text()')==[expected['title']],'Title mismatch')
        check([plain(n.text_content()) for n in doc.xpath('//h1')]==[expected['h1']],'H1 mismatch/count')
        for selector in ['//meta[@name="description"]/@content','//meta[@property="og:description"]/@content','//meta[@name="twitter:description"]/@content']:
            check(doc.xpath(selector)==[expected['description']],selector)
        for selector in ['//meta[@property="og:title"]/@content','//meta[@name="twitter:title"]/@content']:
            check(doc.xpath(selector)==[expected['title']],selector)
        check(0<len(expected['description'])<=80 and expected['description'].endswith('.'),'Description completeness/length')
        check(config[norm(p['path'])]['description']==expected['description'],'Build description config differs')
        canon=doc.xpath('//link[@rel="canonical"]/@href')
        check(len(canon)==1 and norm(canon[0])==norm(p['path']),'Canonical path/count')
        check(len(doc.xpath('//*[@id="overlap-role"]'))==1,'Role block missing/duplicated')
        check(doc.xpath('//*[@id="overlap-role"]/@data-page-role')==[expected['kind']],'Role mismatch')
        check(doc.xpath('//span[@aria-current="page"]/text()')==[expected['h1']],'Visible last breadcrumb')
        ids=Counter(doc.xpath('//*[@id]/@id'))
        check(not any(n>1 for k,n in ids.items() if k.startswith(('overlap-','work-'))),'New duplicate IDs')
        new=doc.xpath('//*[@id="overlap-role"]')[0]
        for url in new.xpath('.//a/@href'):
            dest=norm(url)
            check((url.startswith('#') and url[1:] in ids) or dest in paths,'Missing new link: '+url)
        if expected['kind']=='worksheet':
            fields=new.xpath('.//textarea')
            check(len(fields)==5,'Worksheet field coverage')
            check(all(len(new.xpath('.//label[@for="'+f.get('id')+'"]'))==1 for f in fields),'Field accessible labels')
            check(all(not (f.text or '').strip() for f in fields),'Test data accidentally saved')
            check(len(doc.xpath('//script[contains(@src,"page-overlap-roles.js")]'))==1,'Worksheet script count')
        if expected['kind'] in ('selection-guide','feedback-comparison','time-allocation'):
            check(len(new.xpath('.//article[contains(@class,"overlap-criterion")]'))==3,'Comparison coverage')
        page_nodes=0;crumbs=0
        for script in doc.xpath('//script[@type="application/ld+json"]'):
            for n in walk(json.loads(script.text)):
                ts=n.get('@type',[]);ts=set(ts if isinstance(ts,list) else [ts])
                references=[n.get('url'),n.get('@id'),n.get('mainEntityOfPage')]
                references=[v.get('@id') if isinstance(v,dict) else v for v in references]
                if ts.intersection({'WebPage','CollectionPage','Article'}) and any(isinstance(v,str) and norm(v)==norm(p['path']) for v in references):
                    page_nodes+=1;check(n.get('description')==expected['description'],'Page JSON-LD description')
                    check(n.get('dateModified')=='2026-09-28','Page JSON-LD modified date')
                    check(n.get('headline')==expected['h1'] if 'Article' in ts else n.get('name')==expected['title'],'Page JSON-LD title')
                if 'BreadcrumbList' in ts:
                    last=n.get('itemListElement',[])[-1];check(last.get('name')==expected['h1'],'JSON-LD last breadcrumb');crumbs+=1
        check(page_nodes>0 and crumbs>0,'Page/breadcrumb schema missing')
        return {'path':p['path'],'error':err,'title':expected['title'],'h1':expected['h1'],'description':expected['description'],'kind':expected['kind'],'pageNodes':page_nodes}
    with ThreadPoolExecutor(max_workers=10) as pool:
        for i,r in enumerate(pool.map(inspect,inventory)):
            results.append(r)
            if r['error']:errors.append(r)
            if (i+1)%5000==0:print('audited',i+1,flush=True)
    for field in ['title','h1','description']:
        counts=Counter(r[field] for r in results if field in r)
        if any(n>1 for n in counts.values()):errors.append({'error':['Duplicate new '+field],'values':[k for k,n in counts.items() if n>1][:20]})
    # Every group keeps exactly one original, not merely at least one.
    for g in plan['groups']:
        members=[g['keeper'],*g['targets']]
        changed=sum(t['path'] in state for t in members)
        if changed!=len(members)-1:errors.append({'error':['Group scope violation'],'topic':g['topic']})
    report={'inventoryPages':len(inventory),'overlapGroups':len(plan['groups']),'changedPages':len(state),'unchangedPages':sum(r.get('untouched',False) for r in results),'roles':dict(Counter(r.get('kind') for r in results if r.get('kind'))),'descriptionMax':max(len(v['description']) for v in state.values()),'pageSchemaNodes':sum(r.get('pageNodes',0) for r in results),'errors':errors}
    (args.report_dir/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={k:v for k,v in report.items() if k!='errors'}
    summary['errorCount']=len(errors)
    summary['errorTypes']=dict(Counter(msg for e in errors for msg in e['error']))
    summary['errorSamples']=errors[:3]
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
