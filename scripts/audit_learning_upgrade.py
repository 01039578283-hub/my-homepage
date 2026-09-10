"""Read-only scoped QA (reports outside of deployable site tree)."""
import hashlib
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote,urljoin,urlsplit
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from render_learning_upgrade import BASE,ROOT,ORIGIN,FAQs,SECTIONS,baseline

OUTPUT = ROOT.parent / 'wawa-learning-qa-20260911'
SOURCE_IMAGES = Path('C:/Users/1992k/Desktop/홈페이지 정리/새 홈페이지3/assets/brand-upgrade-v1')
ORIGINAL_INDEX = Path('C:/Users/1992k/Desktop/홈페이지 정리/홈페이지/.git/index')
EXPECTED_ORIGINAL_INDEX_HASH = 'f8d37ac356c00701d0a96a46a58288fed15e24b81f3752a0ffe6e9fab26661a3'
results = []


def check(name, condition, detail=None):
    results.append({'check':name,'pass':bool(condition),'detail':detail})


class Document(HTMLParser):
    def __init__(self,text):
        super().__init__()
        self.ids=[]; self.images=[]; self.links=[]; self.meta={}; self.canonical=[]
        self.headings=[]; self.scripts=[]; self.graphs=[]; self.capture=None; self.parts=[]
        self.feed(text)

    def handle_starttag(self,tag,attrs):
        a = dict(attrs)
        if 'id' in a: self.ids.append(a['id'])
        if tag == 'img': self.images.append(a)
        if tag in ('a','link','script'):
            if a.get('href'): self.links.append(a['href'])
            if a.get('src'): self.links.append(a['src'])
        if tag == 'meta': self.meta[a.get('name',a.get('property',''))] = a.get('content')
        if tag == 'link' and a.get('rel') == 'canonical': self.canonical.append(a['href'])
        if tag in ('h1','title') or (tag == 'script' and a.get('type') == 'application/ld+json'):
            self.capture=tag; self.parts=[]
        if tag == 'script': self.scripts.append(a)

    def handle_data(self,data):
        if self.capture: self.parts.append(data)

    def handle_endtag(self,tag):
        if self.capture != tag: return
        text = ' '.join(' '.join(self.parts).split())
        if tag == 'script': self.graphs.append(json.loads(''.join(self.parts)))
        else: self.headings.append((tag,text))
        self.capture=None; self.parts=[]


def local_path(url):
    path = unquote(urlsplit(url).path).lstrip('/')
    target = ROOT / path
    if target.is_dir(): target /= 'index.html'
    return target


def audit_page(path):
    text = (ROOT / path).read_text(encoding='utf-8')
    doc = Document(text)
    before = Document(baseline(path))
    url = ORIGIN + ('/' if path == 'index.html' else '/overview/')
    check(path+': single H1',len([x for x in doc.headings if x[0]=='h1']) == 1)
    check(path+': title preserved',[v for t,v in doc.headings if t=='title'] == [v for t,v in before.headings if t=='title'])
    check(path+': canonical preserved',doc.canonical == before.canonical == [url])
    for key in ['naver-site-verification','google-site-verification','og:url','og:image']:
        check(path+': preserved '+key,doc.meta.get(key) == before.meta.get(key))
    check(path+': description consistent',doc.meta.get('description') == doc.meta.get('og:description'))
    check(path+': no noindex','noindex' not in doc.meta.get('robots',''))
    check(path+': no duplicate IDs',len(doc.ids) == len(set(doc.ids)))
    check(path+': source fragments once',text.count('<!-- WAWA_LEARNING_START -->') == text.count('<!-- WAWA_LEARNING_END -->') == 1)
    check(path+': no eager iframe','<iframe' not in text)
    check(path+': no placeholder',not re.search(r'Lorem ipsum|TODO|undefined|null\.png',text))
    for src in doc.images:
        image = local_path(urljoin(url,src['src']))
        check(path+': image '+image.name,image.is_file() and src.get('alt') and src.get('width') and src.get('height'))
        if src.get('fetchpriority') != 'high':
            check(path+': lazy '+image.name,src.get('loading') == 'lazy')
    for link in sorted(set(doc.links)):
        absolute = urljoin(url,link)
        parsed = urlsplit(absolute)
        if parsed.netloc != 'wawa-center.kr' or parsed.scheme not in ('https','http'): continue
        target = local_path(absolute)
        check(path+': link '+link,target.is_file())
        if target.is_file() and parsed.fragment and target.suffix == '.html':
            check(path+': anchor '+link,unquote(parsed.fragment) in Document(target.read_text(encoding='utf-8')).ids)
    # Same telephone, SMS destination and consultation form (including legacy variants).
    contact = lambda d:{l for l in d.links if l.startswith('tel:') or 'blogsms.net' in l or 'docs.google.com/forms' in l}
    check(path+': contact links preserved',contact(doc) == contact(before))
    faqs = FAQs(); faqs.feed(text)
    nodes=[n for g in doc.graphs for n in g.get('@graph',[])]
    faq_nodes=[n for n in nodes if n.get('@type')=='FAQPage']
    check(path+': visible FAQ matches schema',len(faq_nodes)==1 and faq_nodes[0]['mainEntity']==faqs.results)
    check(path+': FAQ count',len(faqs.results)==(3 if path=='index.html' else 6),len(faqs.results))
    for node in nodes:
        if node.get('@type') == 'WebPage':
            check(path+': schema description',node.get('description')==doc.meta.get('description'))
            check(path+': hasPart anchors',all(urlsplit(x['url']).fragment in doc.ids for x in node['hasPart']))
    if path=='index.html':
        get_fees=lambda s:re.findall(r'\b\d{3},\d{3}원',s[s.index('<section class="section-band" id="fee">'):s.index('<section class="section home-center-links"')])
        check(path+': fee figures/order retained',get_fees(text)==get_fees(baseline(path)))
        regions=lambda s:re.search(r'<div class="home-center-grid".*?</div>',s,re.S)[0]
        check(path+': all regional links retained',regions(text)==regions(baseline(path)))
        check(path+': 3 distinct video IDs',set(re.findall(r'data-video="([^"]+)"',text))=={'avpJfW7eIV0','f_skFu40U04','UIXUaBZdNXU'})
    return doc


def main():
    docs={p:audit_page(p) for p in ['index.html','overview/index.html']}
    images = list((ROOT/'assets/official-learning').glob('*'))
    check('13 official assets',len(images)==13)
    used={Path(i['src']).name for doc in docs.values() for i in doc.images}
    check('all copied assets used',used=={p.name for p in images})
    for image in images:
        check('original image bytes: '+image.name,image.read_bytes()==(SOURCE_IMAGES/image.name).read_bytes())
    changed=subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT).decode().splitlines()
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT).decode().splitlines()
    expected={'index.html','overview/index.html','sitemap.xml','.gitignore',
              'BRAND_UPGRADE_2026-09-11_WAWA.md',
              'assets/learning-upgrade.css','assets/learning-upgrade.js',
              'scripts/audit_learning_upgrade.py','scripts/render_learning_upgrade.py',
              'scripts/data/brand-upgrade-20260911/home.html',
              'scripts/data/brand-upgrade-20260911/overview.html'}
    expected.update('assets/official-learning/'+p.name for p in images)
    check('exact 24-file release scope',set(changed)|set(untracked)==expected,sorted(set(changed)|set(untracked)))
    check('original dirty index protected',hashlib.sha256(ORIGINAL_INDEX.read_bytes()).hexdigest()==EXPECTED_ORIGINAL_INDEX_HASH)
    sitemap=(ROOT/'sitemap.xml').read_text(encoding='utf-8')
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls=lambda s:[e.findtext('s:loc',namespaces=ns) for e in ET.fromstring(s)]
    check('sitemap URLs/order unchanged',urls(sitemap)==urls(baseline('sitemap.xml')),len(urls(sitemap)))
    a=ET.fromstring(sitemap); b=ET.fromstring(baseline('sitemap.xml'))
    changed_dates=[ea.findtext('s:loc',namespaces=ns) for ea,eb in zip(a,b) if ET.tostring(ea)!=ET.tostring(eb)]
    check('sitemap only two lastmods',set(changed_dates)=={ORIGIN+'/',ORIGIN+'/overview/'},changed_dates)
    check('RSS bytes retained', (ROOT/'rss.xml').read_text(encoding='utf-8')==baseline('rss.xml'))
    all_urls={'/','/overview/','/assets/learning-upgrade.css','/assets/learning-upgrade.js','/sitemap.xml','/rss.xml'}
    all_urls.update('/assets/official-learning/'+p.name for p in images)
    for doc in docs.values():
        all_urls.update(urlsplit(urljoin(ORIGIN+'/',link)).path for link in doc.links if link.startswith('/'))
    for path in sorted(all_urls):
        from urllib.parse import quote
        with urlopen('http://127.0.0.1:8795'+quote(path,safe='/'),timeout=15) as response:
            check('local HTTP '+path,response.status==200)
    OUTPUT.mkdir(exist_ok=True)
    report={'checks':len(results),'passed':sum(r['pass'] for r in results),'failed':[r for r in results if not r['pass']],'images':len(images),'imageBytes':sum(p.stat().st_size for p in images),'baseline':BASE,'results':results}
    (OUTPUT/'static-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))
    assert not report['failed']


if __name__=='__main__': main()
