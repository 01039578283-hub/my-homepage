"""Read-only release gate for the branch subject-hub URL migration."""
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote,urlsplit
from xml.etree import ElementTree as ET
from lxml import html
from branch_urls import hub_path,course_path,center_path,crumbs,canonical
from branch_seo import PageDates,finalize_page
from migrate_local_subject_hubs import ROOT,OUT,mapping_replacer,public_files


def run():
    hubs=json.loads((ROOT/'tools/data/local-subject-hubs/hubs.json').read_text(encoding='utf-8'))['pages']
    courses=json.loads((ROOT/'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']
    centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    mapping=json.loads((ROOT/'tools/data/local-subject-hubs/url-migration.json').read_text(encoding='utf-8'))
    byloc={loc:c for c in centers for loc in c['neighborhoods']}
    store=PageDates(ROOT); stats=Counter();errors=[];titles=[];descs=[];cache={}
    entries=ET.parse(ROOT/'sitemap.xml').getroot().findall('{*}url')
    sitemap={unquote(urlsplit(e.findtext('{*}loc')).path):e.findtext('{*}lastmod') for e in entries}
    assert len(entries)==len(sitemap)==21543
    assert len(hubs)==742 and len(courses)==2226 and len(mapping)==2226
    assert all(old not in sitemap and new in sitemap for old,new in mapping.items())
    assert all(not (ROOT/old.strip('/')/'index.html').exists() for old in mapping)
    def doc_for(path):
        if path not in cache:
            file=ROOT/path.lstrip('/')
            if not file.suffix or path.endswith('/'):file=file/'index.html'
            if not file.exists():return None
            cache[path]=html.fromstring(file.read_text(encoding='utf-8')) if file.suffix=='.html' else True
        return cache[path]
    for row in [*hubs,*courses]:
        path=row['path'];center=byloc[row['locality']];is_course='level' in row
        raw=(ROOT/path.strip('/')/'index.html').read_text(encoding='utf-8');doc=html.fromstring(raw)
        def check(condition,message):
            if not condition:errors.append({'path':path,'error':message})
        meta={m.get('name') or m.get('property'):m.get('content') for m in doc.xpath('//meta[@name or @property]')}
        title=doc.xpath('//title/text()');titles+=title;descs.append(meta.get('description'))
        check(len(title)==1 and len(doc.xpath('//h1'))==1,'One title / H1')
        check(doc.xpath('//link[@rel="canonical"]/@href')==[canonical(path)],'Canonical')
        check(meta.get('og:url')==canonical(path),'OG URL')
        check(meta.get('twitter:title')==meta.get('og:title')==title[0],'Social title')
        check(meta.get('twitter:description')==meta.get('og:description')==meta.get('description'),'Social description')
        check(meta.get('twitter:image')==meta.get('og:image'),'Social image')
        check('noindex' not in meta.get('robots',''),'Indexability')
        nodes=json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
        bc=next(n for n in nodes if n.get('@type')=='BreadcrumbList')['itemListElement']
        expected=crumbs(center,row['locality'],row['subject'],row.get('level'))
        check([i['item'] for i in bc]==[canonical(p) for n,p in expected],'Breadcrumb graph')
        check(doc.xpath('//nav[@class="branch-breadcrumb"]//a/@href')==[p for n,p in expected[:-1]],'Breadcrumb UI')
        page=next(n for n in nodes if n.get('@type')=='WebPage')
        parent=hub_path(center,row['locality'],row['subject']) if is_course else center_path(center)
        check(page['isPartOf']=={'@id':canonical(parent)+'#webpage'},'Page parent')
        for node in nodes:
            if node.get('@type') in ('WebPage','Article'):
                check(node.get('datePublished')==store.records[path]['datePublished'],'Publication date')
                check(node.get('dateModified')==sitemap[path],'Sitemap date')
            if node.get('@type')=='ItemList':
                check(node['numberOfItems']==len(node['itemListElement']),'ItemList count')
        visible=' '.join(doc.xpath('//main')[0].text_content().split())
        faq=next(n for n in nodes if n.get('@type')=='FAQPage')
        for q in faq['mainEntity']:
            check(q['name'] in visible and q['acceptedAnswer']['text'] in visible,'Visible FAQ/schema match')
        check(finalize_page(raw,path,store=store,today='2026-09-22')==raw,'No automatic date refresh')
        media=doc.xpath('//section[contains(@class,"branch-primary-media")]')[0]
        images=media.xpath('.//img');check(len(images)==3,'Media image count')
        check([im.get('src') for im in images]==[center['primaryMedia'][k]['src'] for k in ('representative','body','map')],'Media order/source')
        check('display:none' in images[0].get('style',''),'Representative hidden')
        check(images[1].get('alt')==row['title']+' 본문' and images[2].get('alt')==row['title']+' 지도','Image alt')
        if not is_course:
            check(center['address'] in visible,'Center address')
            check(row['concern'] in visible and row['habit'] in visible,'Manuscript-specific learning context')
            check(not re.search(r'SEO·AEO|(?<![가-힣])원고(?!등학교)|학원매출|후기 예시|후보 지역',visible),'No authoring/fake-review language')
            check(len(doc.xpath('//*[@id="child-pages"]//a'))==3,'Three school-stage links')
            check(store.records[path]['datePublished']=='2026-09-21','New hub publication')
        else:check(store.records[path]['datePublished']=='2026-09-20','Preserved original publication')
        for attr in ('href','src','poster'):
            for value in doc.xpath(f'//*[@{attr}]/@{attr}'):
                parsed=urlsplit(value)
                if parsed.scheme in ('tel','sms','mailto','data','javascript') or (parsed.netloc and parsed.netloc!='wawa-center.kr'):continue
                target=unquote(parsed.path) or path
                if not target.startswith('/'):continue
                destination=doc_for(target);check(destination is not None,f'Missing link/asset: {value}')
                if parsed.fragment and destination is not None and destination is not True:
                    check(bool(destination.xpath('//*[@id=$id]',id=unquote(parsed.fragment))),f'Missing fragment: {value}')
        stats['courses' if is_course else 'hubs']+=1
    check(len(set(titles))==len(titles),'Unique page titles')
    check(len(set(descs))==len(descs),'Unique meta descriptions')
    replace=mapping_replacer(mapping)
    for file in public_files():
        raw=file.read_text(encoding='utf-8')
        if replace(raw)!=raw:errors.append({'path':str(file.relative_to(ROOT)),'error':'Unmigrated incoming URL'})
        stats['publicFilesScanned']+=1
    for c in centers:
        if not c['neighborhoods']:continue
        doc=doc_for(center_path(c))
        actual=doc.xpath('//*[@id="learning-pages"]//a/@href')
        expected=[hub_path(c,loc,s) for loc in c['neighborhoods'] for s in ('수학','영어')]
        if actual!=expected:errors.append({'path':center_path(c),'error':'Center-to-hub links'})
    ET.parse(ROOT/'rss.xml')
    assert 'sitemap.xml' in (ROOT/'robots.txt').read_text(encoding='utf-8')
    result={'counts':dict(stats),'branchPages':len([p for p in sitemap if p.startswith('/지점안내/')]),'sitemapUrls':len(sitemap),'redirectMappings':len(mapping),'errors':errors}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({**result,'errors':errors[:25]},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)


if __name__=='__main__':run()
