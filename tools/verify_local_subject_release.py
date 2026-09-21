"""Read-only, rate-limited HTTP check of the published branch migration."""
import argparse
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from urllib.parse import quote,unquote,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from xml.etree import ElementTree as ET

from lxml import html
from branch_urls import canonical
from export_branch_subject_urls import ordered_paths

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'C:\Users\1992k\Desktop\CodexData\outputs\wawa-local-subject-hubs-20260921')
THREAD=threading.local()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class Response:
    def __init__(self,response,method):
        self.status_code=response.code
        self.headers=response.headers
        self.content=b'' if method=='HEAD' else response.read()
        self.encoding='utf-8'

    @property
    def text(self):
        return self.content.decode(self.encoding)


class Session:
    def __init__(self):
        self.opener=build_opener(NoRedirect())

    def fetch(self,method,url,timeout):
        request=Request(url,method=method,headers={'User-Agent':'WawaSiteReleaseCheck/1.0'})
        try:response=self.opener.open(request,timeout=timeout)
        except HTTPError as error:response=error
        with response:return Response(response,method)

    def head(self,url,allow_redirects=False,timeout=25):
        return self.fetch('HEAD',url,timeout)

    def get(self,url,timeout=30):
        return self.fetch('GET',url,timeout)


def session():
    if not hasattr(THREAD,'session'):
        THREAD.session=Session()
    return THREAD.session


def check(origin,entry):
    kind,path,expected=entry
    for attempt in range(3):
        try:
            response=session().head(origin+quote(path,safe='/'),allow_redirects=False,timeout=25)
            status=response.status_code
            location=response.headers.get('Location','')
            if status in (429,500,502,503,504) and attempt<2:
                time.sleep(3*(attempt+1));continue
            if kind=='redirect':
                ok=status in (301,308) and unquote(urlsplit(location).path)==expected
            else:ok=status==200
            time.sleep(.18)
            return {'kind':kind,'path':path,'status':status,'ok':ok,**({'location':location} if kind=='redirect' else {})}
        except (URLError,TimeoutError,OSError) as error:
            if attempt==2:return {'kind':kind,'path':path,'ok':False,'error':str(error)}
            time.sleep(2*(attempt+1))


def run(origin,full=False):
    hubs=json.loads((ROOT/'tools/data/local-subject-hubs/hubs.json').read_text(encoding='utf-8'))['pages']
    courses=json.loads((ROOT/'tools/data/branch-topic-pages/pages.json').read_text(encoding='utf-8'))['pages']
    mapping=json.loads((ROOT/'tools/data/local-subject-hubs/url-migration.json').read_text(encoding='utf-8'))
    if full:
        targets=[('page',p,None) for p in ordered_paths()]+[('redirect',o,n) for o,n in mapping.items()]
    else:
        # Two subject hubs per region plus every level/subject redirect pattern.
        sample=[];seen=set()
        for row in hubs:
            key=row['region'],row['subject']
            if key not in seen:sample.append(row);seen.add(key)
        course_sample=[];seen=set()
        for row in courses:
            key=row['region'],row['level'],row['subject']
            if key not in seen:course_sample.append(row);seen.add(key)
        targets=[('page',r['path'],None) for r in [*sample,*course_sample]]+[('redirect',r['legacyPath'],r['path']) for r in course_sample]
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(check,origin,target) for target in targets]
        for future in as_completed(futures):
            rows.append(future.result())
            if len(rows)%400==0:print(f'Checked {len(rows)}/{len(targets)} URLs',flush=True)
    # Fetch actual page bodies for each region, checking deployment content.
    body_checks=[];seen=set()
    for row in hubs:
        if row['region'] in seen:continue
        seen.add(row['region'])
        response=session().get(origin+quote(row['path'],safe='/'),timeout=30)
        response.encoding='utf-8';doc=html.fromstring(response.text)
        body_checks.append({'path':row['path'],'status':response.status_code,'canonical':doc.xpath('//link[@rel="canonical"]/@href')==[canonical(row['path'])],'title':doc.xpath('//h1/text()')==[row['title']],'children':len(doc.xpath('//*[@id="child-pages"]//a'))==3,'tracker':len(doc.xpath('//script[@data-site="wawa-01"]'))==1})
        time.sleep(.2)
    sitemap=session().get(origin+'/sitemap.xml',timeout=40)
    urls={unquote(urlsplit(e.findtext('{*}loc')).path) for e in ET.fromstring(sitemap.content).findall('{*}url')}
    sitemap_ok=len(urls)==21543 and all(n in urls and o not in urls for o,n in mapping.items())
    errors=[r for r in rows if not r['ok']]
    errors.extend(r for r in body_checks if r['status']!=200 or not all(r[k] for k in ('canonical','title','children','tracker')))
    if not sitemap_ok:errors.append({'error':'Published sitemap mismatch'})
    report={'origin':origin,'mode':'full' if full else 'sample','checked':len(rows),'counts':dict(Counter((r['kind']+':'+str(r.get('status'))) for r in rows)),'bodyChecks':body_checks,'sitemapUrls':len(urls),'errors':errors,'results':sorted(rows,key=lambda r:(r['kind'],r['path']))}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/('http-full.json' if full else 'http-sample.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','bodyChecks')},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',default='https://wawa-center.kr')
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args();run(args.origin.rstrip('/'),args.full)
