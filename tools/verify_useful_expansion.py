"""Full local inventory, link, preservation and new-article checks before release."""
import argparse,hashlib,json,re,sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote,unquote,urlparse,urljoin
from lxml import html,etree
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);args=p.parse_args();out=args.report_dir
    manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8-sig'));files=set(manifest['files'])
    baseline=json.loads((out/'baseline/release-public-manifest.json').read_text(encoding='utf-8-sig'))
    preserved={r['path']:r['bodyWithoutContextSha256'] for r in json.loads((out/'preserved-html.json').read_text(encoding='utf-8'))}
    catalog=json.loads((out/'catalog.json').read_text(encoding='utf-8'));new={a['path']+'/index.html':a for a in catalog}
    descriptions=json.loads((ROOT/'seo-descriptions.json').read_text(encoding='utf-8-sig'))['pages']
    errors=[];counts=Counter();ids={};cross=[]
    def target(url,source):
        u=urlparse(urljoin('https://wawa-center.kr/'+source,url))
        if u.scheme not in ['http','https'] or u.hostname not in ['wawa-center.kr','www.wawa-center.kr']:return None,None
        path=unquote(u.path).lstrip('/');dest=path if path in files else path.rstrip('/')+'/index.html' if path else 'index.html'
        if dest not in files and path+'.html' in files:dest=path+'.html'
        return dest,unquote(u.fragment)
    def inspect(name):
        err=[];tally=Counter();fragments=[];raw=(ROOT/name).read_bytes()
        if sha(raw)!=manifest['files'][name]:err.append('manifest hash '+name)
        if not name.endswith('.html'):return err,tally,None,fragments
        tally['html']+=1;text=raw.decode('utf-8-sig');doc=html.fromstring(raw);pageids=set(doc.xpath('//@id'))|set(doc.xpath('//a/@name'))
        if name in preserved:
            stripped=re.sub(r'<!-- useful-links:start -->.*?<!-- useful-links:end -->','',text,flags=re.S)
            if sha(stripped.replace('\r\n','\n').replace('\r','\n').encode('utf-8'))!=preserved[name]:err.append('preserved content '+name)
            if text.count('<!-- useful-links:start -->')!=1:err.append('context block '+name)
            tally['preservedHtml']+=1
        if text.count('data-useful-navigation')!=1:err.append('menu '+name)
        if text.count('data-teacher-navigation')!=1:err.append('teacher menu '+name)
        if len(doc.xpath('//h1'))!=1:err.append('h1 '+name)
        for s in doc.xpath('//script[@type="application/ld+json"]'):
            try:json.loads(s.text or '');tally['jsonLdBlocks']+=1
            except Exception:err.append('schema json '+name)
        if text.count('wawa-visit-collector.clean-peach-8202.chatgpt.site/tracker.js')>1:err.append('duplicate analytics '+name)
        # The release build injects this tracker where older sources do not already contain it.
        for link in doc.xpath('//a/@href|//img/@src|//script/@src|//link[@rel="stylesheet"]/@href'):
            dest,fragment=target(link,name)
            if dest is None:continue
            tally['internalLinks']+=1
            if dest not in files:err.append('missing target '+name+' '+link)
            elif fragment and not fragment.startswith(':~:text=') and dest.endswith('.html'):fragments.append((name,dest,fragment.split(':~:text=')[0],link))
        if name in new or name=='유용한정보/index.html':
            expected='https://wawa-center.kr/'+quote(name.removesuffix('/index.html'),safe='/-')+'/'
            if doc.xpath('//link[@rel="canonical"]/@href')!=[expected]:err.append('canonical '+name)
            desc=doc.xpath('//meta[@name="description"]/@content');key='/'+name.removesuffix('/index.html')
            if len(desc)!=1 or len(desc[0])>80 or not desc[0].endswith('.') or descriptions[key]['description']!=desc[0]:err.append('description '+name)
            for sel in ['//meta[@property="og:description"]/@content','//meta[@name="twitter:description"]/@content']:
                if doc.xpath(sel)!=desc:err.append('social metadata '+name)
            if len(doc.xpath('//@id'))!=len(pageids):err.append('duplicate ids '+name)
            if '편집 원칙' in doc.text_content() or '편집원칙' in doc.text_content():err.append('editorial mention '+name)
        if name in new:
            a=new[name];images=doc.xpath('//article//figure/img')
            if len(images)!=3:err.append('image count '+name)
            if len(doc.xpath('//section[contains(@class,"ui-chapter")]'))!=4:err.append('chapters '+name)
            if len(doc.xpath('//article')[0].text_content())<1300:err.append('short article '+name)
            local=doc.xpath('//section[@class="ui-static-local"]//a/@href')
            if not any('/%EC%A7%80%EC%A0%90%EC%95%88%EB%82%B4/' in l for l in local):err.append('static branch links '+name)
            if len(local)<4:err.append('static neighborhood links '+name)
            schemas=[json.loads(s.text) for s in doc.xpath('//script[@type="application/ld+json"]')]
            graph=schemas[0]['@graph'];faq=next(n for n in graph if n['@type']=='FAQPage')['mainEntity'][0]
            if faq['name']!=a['faq'][0] or faq['acceptedAnswer']['text']!=a['faq'][1]:err.append('faq visible/schema '+name)
            for image,row in zip(images,a['images']):
                path=ROOT/row['path']
                with Image.open(path) as im:
                    if im.size!=(row['width'],row['height']):err.append('image dimensions '+name)
                if image.get('loading')!='lazy' or not image.get('alt') or path.stat().st_size>150000:err.append('image attributes/size '+name)
            tally['newArticles']+=1;tally['newImages']+=len(images)
        return err,tally,(name,pageids),fragments
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i,(err,tally,page,fragments) in enumerate(pool.map(inspect,sorted(files)),1):
            errors+=err;counts.update(tally);cross+=fragments
            if page:ids[page[0]]=page[1]
            if i%4000==0:print(json.dumps({'checkedFiles':i,'total':len(files),'errors':len(errors)}),flush=True)
    for src,dest,fragment,link in cross:
        if fragment not in ids.get(dest,set()):errors.append('missing anchor '+src+' '+link)
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    def sitemap(path):return [unquote(urlparse(n.text).path).strip('/') for n in etree.parse(str(path)).findall('.//s:loc',ns)]
    paths=sitemap(ROOT/'sitemap.xml');oldpaths=sitemap(out/'baseline/sitemap.xml')
    if len(paths)!=len(set(paths)):errors.append('duplicate sitemap routes')
    if set(paths)-set(oldpaths)!={a['path'] for a in catalog} or set(oldpaths)-set(paths):errors.append('sitemap delta')
    if len(paths)!=manifest['sitemapPages']:errors.append('sitemap count')
    hub=html.fromstring((ROOT/'유용한정보/index.html').read_bytes());cards=hub.xpath('//*[@data-ui-card]')
    if len(cards)!=60 or len(hub.xpath('//*[@class="ui-new-label"]'))!=30:errors.append('hub inventory')
    oldselection=json.loads(Path(r'C:\Users\1992k\Desktop\CodexData\outputs\wawa-useful-info-20261002\selection.json').read_text(encoding='utf-8-sig'))
    selection=json.loads((out/'selection.json').read_text(encoding='utf-8'))
    if {r['folder'] for r in oldselection['selection']}&{r['folder'] for r in selection['selection']}:errors.append('duplicate source folder')
    if len({a['title'] for a in catalog})!=30 or len({a['role'] for a in catalog})!=30:errors.append('duplicate content intent')
    if any(n.startswith('tools/') for n in files):errors.append('private source exposed')
    source=Path(r'C:\Users\1992k\Desktop\홈페이지 작업 폴더\홈페이지 정리\홈페이지')
    for name,digest in json.loads((out/'authoring-protection.json').read_text(encoding='utf-8')).items():
        if sha((source/name).read_bytes())!=digest:errors.append('authoring changed '+name)
    report=dict(status='PASS' if not errors else 'FAIL',checkedFiles=len(files),**counts,sitemapPages=len(paths),newSitemapRoutes=len(set(paths)-set(oldpaths)),fragmentLinks=len(cross),hubCards=len(cards),authoringPreserved=True,errors=errors)
    (out/'full-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v if k!='errors' else v[:30] for k,v in report.items()},ensure_ascii=False),flush=True)
    sys.exit(bool(errors))
if __name__=='__main__':main()
