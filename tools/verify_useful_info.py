"""Verify the complete published inventory and all additions for the useful-information release."""
import argparse,hashlib,json,re,sys,zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote,unquote,urlparse
from lxml import html,etree
from useful_info_content import ARTICLES
from build_useful_info import NAV,VERSION
ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,required=True);args=parser.parse_args();report=args.report_dir
    manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'));baseline=json.loads((report/'baseline-manifest.json').read_text(encoding='utf-8'))
    files=set(manifest['files']);errors=[];counts=Counter();catalog=json.loads((report/'catalog.json').read_text(encoding='utf-8'));articlepaths={a['path']+'/index.html' for a in catalog};reused={a['path']+'/index.html' for a in catalog if a['reuse']}
    descriptions=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8-sig'))['pages']
    def target(link):
        parsed=urlparse(link)
        if parsed.netloc and parsed.netloc!='wawa-center.kr':return None
        if not parsed.path.startswith('/'):return None
        path=unquote(parsed.path).lstrip('/')
        if path in files:return path
        index=path.rstrip('/')+'/index.html' if path else 'index.html'
        return index if index in files else 'MISSING:'+path
    def check(name):
        local=[];tally=Counter();p=ROOT/name
        if not p.is_file():return [f'missing file {name}'],tally
        raw=p.read_bytes()
        if sha(raw)!=manifest['files'][name]:local.append('manifest hash '+name)
        if not name.endswith('.html'):return local,tally
        tally['html']+=1;text=raw.decode('utf-8-sig')
        if text.count('data-useful-navigation')!=1:local.append('navigation '+name)
        if text.count('data-teacher-navigation')!=1:local.append('teacher menu '+name)
        tracker_count=text.count('wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js')
        # The release pipeline injects the tracker into older source HTML after copying verified files.
        if tracker_count>1 or (name not in baseline['files'] and tracker_count!=1):local.append('analytics '+name)
        if name in baseline['files'] and name not in reused:
            if text.count('<!-- useful-links:start -->')!=1:local.append('context section '+name)
            restored=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',text,flags=re.S).replace(NAV,'').replace('header.css?v='+VERSION,'header.css?v=20261002-teachers')
            normalized=restored.replace('\r\n','\n').replace('\r','\n').encode('utf-8')
            if baseline.get('textSha256',{}).get(name) not in {sha(normalized),sha(b'\xef\xbb\xbf'+normalized)}:local.append('original content changed '+name)
            tally['preservedOldHtml']+=1
            block=re.search(r'<!-- useful-links:start -->(.*?)<!-- useful-links:end -->',text,re.S)
            if block:
                for link in re.findall(r'href="([^"]+)"',block[1]):
                    if str(target(link)).startswith('MISSING:'):local.append('context target '+name+' '+link)
                    tally['contextLinks']+=1
        if name in articlepaths or name=='유용한정보/index.html':
            d=html.fromstring(raw);canonical=d.xpath('//link[@rel="canonical"]/@href')
            expected='https://wawa-center.kr/'+quote(name.removesuffix('/index.html'),safe='/-')+'/'
            if canonical!=[expected]:local.append('canonical '+name)
            if len(d.xpath('//h1'))!=1:local.append('h1 '+name)
            desc=d.xpath('//meta[@name="description"]/@content')
            key='/'+name.removesuffix('/index.html')
            if len(desc)!=1 or len(desc[0])>80 or not desc[0].endswith(('.', '!', '?')) or desc[0]!=descriptions[key]['description']:local.append('description '+name)
            for sel in ['//meta[@property="og:description"]/@content','//meta[@name="twitter:description"]/@content']:
                if d.xpath(sel)!=desc:local.append('social description '+name)
            ids=d.xpath('//@id')
            if len(ids)!=len(set(ids)):local.append('duplicate IDs '+name)
            for link in d.xpath('//a/@href|//img/@src|//script/@src|//link[@rel="stylesheet"]/@href'):
                resolved=target(link)
                if str(resolved).startswith('MISSING:'):local.append('link '+name+' '+link)
                if link.startswith('#') and link[1:] not in ids:local.append('anchor '+name+' '+link)
                tally['articleLinks']+=1
            if '편집 원칙' in d.text_content() or '편집원칙' in d.text_content():local.append('editorial mention '+name)
            graph=[]
            for script in d.xpath('//script[@type="application/ld+json"]'):
                try:
                    obj=json.loads(script.text);graph.extend(obj.get('@graph',[obj]))
                except Exception:local.append('schema JSON '+name)
            for item in graph:
                if item.get('@type')=='FAQPage':
                    for q in item.get('mainEntity',[]):
                        if q['name'] not in d.text_content() or q['acceptedAnswer']['text'] not in d.text_content():local.append('FAQ mismatch '+name)
            if name in articlepaths:
                a=next(a for a in catalog if a['path']+'/index.html'==name)
                imgs=d.xpath('//img[starts-with(@src,"/assets/useful-info/")]')
                if len(imgs)!=3 or len(set(i.get('src') for i in imgs))!=3:local.append('images '+name)
                for img in imgs:
                    if not img.get('width') or not img.get('height') or img.get('loading')!='lazy':local.append('image layout '+name)
                if len(d.xpath('//*[@data-ui-places]'))!=1:local.append('place finder '+name)
                for s in a['sections']:
                    for paragraph in s:
                        if paragraph not in d.text_content():local.append('missing reviewed passage '+name)
                tally['reviewedArticles']+=1;tally['assignedImages']+=len(imgs)
        return local,tally
    with ThreadPoolExecutor(max_workers=16) as pool:
        for local,tally in pool.map(check,sorted(files)):errors+=local;counts.update(tally)
    with zipfile.ZipFile(report/'reused-originals.zip') as z:
        for name in reused:
            old=html.fromstring(z.read(name));new=html.fromstring((ROOT/name).read_bytes())
            if not set(old.xpath('//img/@src'))<=set(new.xpath('//img/@src')):errors.append('lost original image '+name)
            if old.xpath('//form/@data-filename')!=new.xpath('//form/@data-filename'):errors.append('lost original record form '+name)
            if not set(old.xpath('//@id'))<=set(new.xpath('//@id')):errors.append('lost original anchor '+name)
    places=json.loads((ROOT/'assets/useful-places.json').read_text(encoding='utf-8'))
    for p in places:
        for link in [p['url'],*[n['url'] for n in p['localities']]]:
            if str(target(link)).startswith('MISSING:'):errors.append('place link '+link)
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'};sitemap=etree.parse(str(ROOT/'sitemap.xml'));urls=sitemap.xpath('//s:loc/text()',namespaces=ns)
    if len(urls)!=len(set(urls)) or len(urls)!=manifest['sitemapPages']:errors.append('sitemap count/duplicates')
    for a in catalog:
        url='https://wawa-center.kr/'+quote(a['path'],safe='/-')+'/'
        if url not in urls:errors.append('article absent from sitemap '+a['path'])
    oldurls=set(etree.parse(str(report/'baseline-sitemap.xml')).xpath('//s:loc/text()',namespaces=ns))
    if not oldurls<=set(urls):errors.append('lost original sitemap URL')
    rss=etree.parse(str(ROOT/'rss.xml'));rsspaths={unquote(urlparse(link).path).strip('/') for link in rss.xpath('//item/link/text()')}
    for a in catalog:
        if a['path'] not in rsspaths:errors.append('article absent from RSS '+a['path'])
    for a in catalog:
        for img in a['images']:
            if sha((ROOT/img['path']).read_bytes())!=img['sha256']:errors.append('changed supplied image '+img['path'])
    result=dict(counts=counts,publicFiles=len(files),sitemapUrls=len(urls),rssItems=len(rsspaths),branches=len(places),errors=errors)
    (report/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(result,errors=errors[:15],errorCount=len(errors)),ensure_ascii=False,indent=2));sys.exit(bool(errors))
if __name__=='__main__':main()
