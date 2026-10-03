"""Check home navigation, visible/schema agreement, and the complete public inventory."""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen
from lxml import html
from build_home_resources import ROOT, BASE, DATE, DESCRIPTION, ACADEMY, LEARNING, ARTICLES, QUESTIONS, START, END, FEATURE_START, FEATURE_END, STYLE

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,required=True);parser.add_argument('--http-base',default='http://127.0.0.1:8765');parser.add_argument('--checked-manifest',type=Path);args=parser.parse_args();report=args.report_dir
    errors=[]
    def check(condition,message):
        if not condition:errors.append(message)
    baseline=json.loads((report/'baseline-release-public-manifest.json').read_text(encoding='utf-8-sig'))
    manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'))
    check(set(manifest['files'])==set(baseline['files'])|{'assets/home-resources.css'},'public file inventory changed beyond home stylesheet')
    check(manifest['sitemapPages']==baseline['sitemapPages'],'sitemap page count changed')
    for name,sha in baseline['files'].items():
        if name not in ['index.html','sitemap.xml']:check(manifest['files'].get(name)==sha,'unrelated public file changed: '+name)
    def verify_hash(row):
        name,expected=row;path=ROOT/name
        return name if not path.is_file() or digest(path.read_bytes())!=expected else None
    hashes_to_check=manifest['files']
    if args.checked_manifest:
        receipt=json.loads(args.checked_manifest.read_text(encoding='utf-8-sig'))
        check(set(receipt['files'])==set(manifest['files']),'checked inventory file set')
        changed={n for n,s in manifest['files'].items() if receipt['files'].get(n)!=s}
        check(changed<={'index.html','assets/home-resources.css'},'changes after full inventory verification')
        hashes_to_check={n:manifest['files'][n] for n in changed}
    with ThreadPoolExecutor(max_workers=6) as pool:
        errors.extend('manifest bytes: '+name for name in pool.map(verify_hash,hashes_to_check.items()) if name)
    text=(ROOT/'index.html').read_text(encoding='utf-8-sig');old=(report/'baseline-index.html').read_text(encoding='utf-8-sig')
    doc=html.fromstring(text)
    check(len(doc.xpath('//h1'))==1 and len(doc.xpath('//main'))==1,'main/h1 count')
    ids=doc.xpath('//@id');check(len(ids)==len(set(ids)),'duplicate IDs')
    check(doc.xpath('//link[@rel="canonical"]/@href')==[BASE+'/'],'canonical')
    check(doc.xpath('//meta[@name="robots"]/@content')==['index, follow'],'index policy')
    for attr in ['name="description"','property="og:description"','name="twitter:description"']:
        check(doc.xpath('//meta[@'+attr+']/@content')==[DESCRIPTION],'description field '+attr)
    check(len(DESCRIPTION)<=80 and DESCRIPTION.endswith('.'),'description format')
    graph=json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
    page=next(n for n in graph if n.get('@id')==BASE+'/#webpage')
    check(page['description']==DESCRIPTION and page['dateModified']==DATE,'page schema')
    for id_,rows in [('home-academy-list',ACADEMY),('home-study-list',LEARNING),('home-reading-list',ARTICLES)]:
        listing=next(n for n in graph if n.get('@id')==BASE+'/#'+id_)
        check(listing['numberOfItems']==len(rows),'item count '+id_)
        check([n['item']['url'] for n in listing['itemListElement']]==[BASE+r[0] for r in rows],'item URLs '+id_)
        for item in listing['itemListElement']:
            check(item['item']['name'] in doc.xpath('//main')[0].text_content(),'item name not in visible home')
            check(item['item']['description'] in doc.xpath('//main')[0].text_content(),'item description not in visible home')
    faq=next(n for n in graph if n.get('@id')==BASE+'/#faq')
    for q,a,_,_ in QUESTIONS:
        check(len([n for n in faq['mainEntity'] if n['name']==q and n['acceptedAnswer']['text']==a])==1,'FAQ schema '+q)
        check(q in doc.xpath('//main')[0].text_content() and a in doc.xpath('//main')[0].text_content(),'FAQ visible text '+q)
    check(len(doc.xpath('//*[@id="home-resources"]//article'))==7,'directory cards')
    check(len(doc.xpath('//*[@id="home-reading"]//article'))==6,'reading cards')
    check(len(doc.xpath('//*[@class="hr-faq"]//details'))==3,'questions')
    check(doc.xpath('//link[contains(@href,"home-resources.css")]/@href')==['/assets/home-resources.css?v=20261003'],'home stylesheet')
    check(text.index('id="home-resources"')<text.index('id="learning-paths"'),'directory location')
    check('편집 원칙' not in doc.xpath('//main')[0].text_content(),'editorial principles in body')
    def protected(value,is_new):
        # Compare all previous homepage sections, photos, scripts, contact details and index rules.
        value=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',value,flags=re.S)
        value=re.sub(re.escape(FEATURE_START)+r'.*?'+re.escape(FEATURE_END),'',value,flags=re.S)
        value=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',value,flags=re.S)
        value=value.replace(STYLE,'')
        value=re.sub(r'<a class="wu-button hr-hero-link".*?</a>','',value)
        value=re.sub(r'<a href="#home-reading">[^<]*</a>','',value)
        value=re.sub(r'(<meta (?:name="description"|property="og:description"|name="twitter:description") content=")[^"]*(")',r'\1DESCRIPTION\2',value)
        value=re.sub(r'(<script type="application/ld\+json">).*?(</script>)',r'\1SCHEMA\2',value,flags=re.S)
        value=re.sub(r'>\s+<','><',value)
        return re.sub(r'\s+',' ',value).strip()
    check(protected(text,True)==protected(old,False),'previous home HTML altered beyond approved additions')
    old_graph=json.loads(html.fromstring(old).xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
    preserved=json.loads(json.dumps(graph));preserved=[n for n in preserved if not n.get('@id','').split('#')[-1] in ['home-academy-list','home-study-list','home-reading-list']]
    p=next(n for n in preserved if n.get('@id')==BASE+'/#webpage');op=next(n for n in old_graph if n.get('@id')==BASE+'/#webpage')
    for field in ['description','dateModified','hasPart']:
        p[field]=op[field]
    p.pop('mainEntity',None)
    f=next(n for n in preserved if n.get('@id')==BASE+'/#faq');f['mainEntity']=[n for n in f['mainEntity'] if n['name'] not in {q[0] for q in QUESTIONS}]
    check(preserved==old_graph,'unrelated schema changed')
    old_seo=json.loads((report/'baseline-seo-descriptions.json').read_text(encoding='utf-8-sig'));seo=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8-sig'))
    check(seo['pages']['/']['description']==DESCRIPTION,'home description config')
    seo['pages']['/']=old_seo['pages']['/'];check(seo==old_seo,'other description config changed')
    old_site=(report/'baseline-sitemap.xml').read_bytes();new_site=(ROOT/'sitemap.xml').read_bytes()
    expected=re.sub(rb'(<loc>https://wawa-center\.kr/</loc>\s*<lastmod>)[^<]*(</lastmod>)',lambda m:m[1]+DATE.encode()+m[2],old_site)
    check(new_site==expected,'other sitemap date or URL changed')
    urls=set();link_count=0;asset_count=0
    targets={}
    for ref in doc.xpath('//a/@href|//script/@src|//link[@rel="stylesheet"]/@href|//img/@src'):
        u=urlparse(urljoin(BASE+'/',ref))
        if u.scheme not in ['http','https'] or u.netloc!='wawa-center.kr':continue
        file=unquote(u.path).lstrip('/')
        file=file if file in manifest['files'] else file.rstrip('/')+'/index.html' if file else 'index.html'
        check(file in manifest['files'],'missing link/asset '+ref)
        if file not in manifest['files']:continue
        if u.fragment:
            if file not in targets:targets[file]=set(html.fromstring((ROOT/file).read_bytes()).xpath('//@id'))
            check(unquote(u.fragment) in targets[file],'missing anchor '+ref)
        urls.add(u.path+('?' + u.query if u.query else ''))
        if file.endswith('.html'):link_count+=1
        else:asset_count+=1
    for n in doc.xpath('//*[@id="home-resources" or @id="home-reading"]//a'):
        check(n.get('href') and not n.get('onclick') and 'nofollow' not in (n.get('rel') or '').split(),'noncrawlable new link')
        check(bool(n.text_content().strip()),'empty anchor')
    for item in json.loads((report/'protected-source.json').read_text(encoding='utf-8-sig')):
        check(digest(Path(item['path']).read_bytes())==item['sha256'],'protected original/source changed '+item['path'])
    def request(path):
        from urllib.parse import quote
        url=args.http_base+quote(unquote(path),safe='/?=&%')
        try:
            with urlopen(Request(url,headers={'User-Agent':'WawaHomeVerification/1.0'}),timeout=25) as response:
                response.read();return {'path':path,'status':response.status}
        except Exception as exc:return {'path':path,'error':str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(request,sorted(urls)))
    errors.extend('HTTP '+r['path']+': '+r.get('error',str(r.get('status'))) for r in responses if r.get('status')!=200)
    result={'publicFilesInValidatedInventory':len(manifest['files']),'currentHashesChecked':len(hashes_to_check),'hashReceiptReused':bool(args.checked_manifest),'preservedPublicFiles':len(baseline['files'])-2,'htmlPages':manifest['sitemapPages'],'homeInternalLinkOccurrences':link_count,'homeAssetOccurrences':asset_count,'httpRequests':len(responses),'httpPassed':sum(r.get('status')==200 for r in responses),'directoryCards':7,'recommendedArticles':6,'visibleNavigationQuestions':3,'errors':errors,'errorCount':len(errors)}
    (report/'home-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (report/'home-http-validation.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(errors))

if __name__=='__main__':
    main()
