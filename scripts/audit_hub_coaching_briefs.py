"""Read-only release audit for compact hub summaries; reports live outside the site."""
import copy
import hashlib
import json
import re
import subprocess
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from render_hub_coaching_briefs import ROOT, BASELINE, ORIGIN, NOTE, CSS_HREF, SCRIPT_RE, ASIDE_RE, OLD_FAQ, CORRECT_FAQ, baseline, copies, render_page, render_sitemap

OUTPUT = ROOT.parent / 'wawa-hub-brief-qa-20260911'
BRIEF_RE = re.compile(r'<!-- wawa-hub-coaching:start -->.*?<!-- wawa-hub-coaching:end -->', re.S)
RESULTS = []


def check(name, condition, detail=None):
    RESULTS.append({'check': name, 'pass': bool(condition), 'detail': detail})


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = []; self.images = []; self.links = []; self.meta = {}; self.canonical = []
        self.h1 = []; self.title = []; self.scripts = []; self.capture = None; self.parts = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a: self.ids.append(a['id'])
        if tag == 'img': self.images.append(a)
        if tag == 'a': self.links.append(a.get('href'))
        if tag == 'meta': self.meta[a.get('name', a.get('property'))] = a.get('content')
        if tag == 'link' and a.get('rel') == 'canonical': self.canonical.append(a.get('href'))
        if tag == 'script' and a.get('type') != 'application/ld+json': self.scripts.append(a)
        if tag in ('h1', 'title'): self.capture = tag; self.parts = []

    def handle_data(self, data):
        if self.capture: self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.capture:
            getattr(self, tag).append(' '.join(' '.join(self.parts).split()))
            self.capture = None


def visible(text):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', text)).split())


def normalized_docs(text):
    return [json.loads(m[2]) for m in SCRIPT_RE.finditer(text)]


def nodes(docs):
    return [node for doc in docs for node in doc.get('@graph', [doc])]


def stripped(text, route, after):
    text = SCRIPT_RE.sub('', text)
    if after:
        text = BRIEF_RE.sub('' if route == '/center/' else 'HUB_BRIEF_PLACEHOLDER', text)
        text = text.replace(f'<link rel="stylesheet" href="{CSS_HREF}">\n', '')
        if route == '/과목별학원/':
            text = text.replace('<p>'+CORRECT_FAQ+'</p>', '<p>'+OLD_FAQ+'</p>')
    elif route != '/center/':
        text = ASIDE_RE.sub('HUB_BRIEF_PLACEHOLDER', text)
    return text.replace('\r\n', '\n')


def main():
    items = copies()
    expected = {route.strip('/') + '/index.html' for route in items} | {
        'sitemap.xml', 'assets/hub-coaching-brief.css',
        'scripts/data/hub-coaching-briefs-20260911.json',
        'scripts/render_hub_coaching_briefs.py', 'scripts/audit_hub_coaching_briefs.py',
        'HUB_COACHING_BRIEFS_2026-09-11.md',
    }
    git = lambda args: subprocess.check_output(['git', '-c', 'core.quotepath=false', '-c', 'core.safecrlf=false', *args], cwd=ROOT).decode('utf-8')
    changed = set(git(['diff', '--name-only', '-z', BASELINE]).strip('\0').split('\0')) - {''}
    untracked = set(git(['ls-files', '--others', '--exclude-standard', '-z']).strip('\0').split('\0')) - {''}
    check('exact 41-file scope', changed | untracked == expected, sorted(changed | untracked))
    original_index = Path('C:/Users/1992k/Desktop/홈페이지 정리/홈페이지/.git/index')
    check('original dirty index protected', hashlib.sha256(original_index.read_bytes()).hexdigest() == 'f8d37ac356c00701d0a96a46a58288fed15e24b81f3752a0ffe6e9fab26661a3')
    html_tracked = [p for p in git(['ls-tree', '-r', '--name-only', '-z', BASELINE]).split('\0') if p.endswith('.html') and not p.startswith('scripts/')]
    check('all 18310 non-target page HTML files unchanged', len(html_tracked) - len(items) == 18310 and not (changed - expected) and {p for p in changed if p.endswith('.html')} == {r.strip('/')+'/index.html' for r in items}, len(html_tracked)-len(items))
    sums = []; faq_count = 0
    for route, item in items.items():
        path = route.strip('/')+'/index.html'
        text = (ROOT/path).read_text(encoding='utf-8-sig')
        old = baseline(path).replace('\r\n', '\n')
        doc = Document(text); prior = Document(old)
        prefix = route + ': '
        check(prefix+'only intended hero replacement and stylesheet', stripped(text, route, True) == stripped(old, route, False))
        check(prefix+'repeatable rendering', render_page(route, item)[1] == text)
        check(prefix+'exactly one brief', len(BRIEF_RE.findall(text)) == 1)
        check(prefix+'one preserved H1 and title', doc.h1 == prior.h1 and len(doc.h1) == 1 and doc.title == prior.title and len(doc.title) == 1)
        check(prefix+'canonical correct and preserved', doc.canonical == prior.canonical and [unquote(u) for u in doc.canonical] == [ORIGIN+route])
        check(prefix+'all metadata preserved', doc.meta == prior.meta)
        check(prefix+'correct og:url', unquote(doc.meta.get('og:url', '')) == ORIGIN+route)
        check(prefix+'no duplicate DOM IDs', len(doc.ids) == len(set(doc.ids)))
        check(prefix+'images unchanged', doc.images == prior.images)
        check(prefix+'scripts unchanged, no added iframe', doc.scripts == prior.scripts and text.count('<iframe') == old.count('<iframe'))
        check(prefix+'stylesheet included once', text.count(CSS_HREF) == 1)
        new_docs = normalized_docs(text); old_docs = normalized_docs(old)
        new_nodes = nodes(new_docs); old_nodes = nodes(old_docs)
        page = next(n for n in new_nodes if n.get('@type') == 'CollectionPage')
        old_page = next(n for n in old_nodes if n.get('@type') == 'CollectionPage')
        page_url = page.get('url', page['@id'].split('#')[0])
        element_id = page_url + '#hub-coaching'
        elements = [n for n in new_nodes if n.get('@id') == element_id]
        check(prefix+'one linked schema summary', len(elements) == 1 and page['hasPart'].count({'@id': element_id}) == 1)
        check(prefix+'schema equals visible summary', len(elements) == 1 and elements[0]['name'] == item['title'] and elements[0]['text'] == item['summary']+'\n'+NOTE and elements[0]['isPartOf'] == {'@id': page['@id']})
        reverted = copy.deepcopy(new_docs)
        for d in reverted:
            for n in d.get('@graph', [d]):
                if n.get('@type') == 'CollectionPage':
                    n['hasPart'] = old_page['hasPart']; n['dateModified'] = old_page['dateModified']
            if '@graph' in d: d['@graph'] = [n for n in d['@graph'] if n.get('@id') != element_id]
        check(prefix+'other JSON-LD content/relationships preserved', reverted == old_docs)
        schema_ids = [n['@id'] for n in new_nodes if '@id' in n]
        check(prefix+'no duplicate graph identities', len(schema_ids) == len(set(schema_ids)))
        main_text = visible(re.search(r'<main\b.*?</main>', text, re.S)[0])
        for faq in [n for n in new_nodes if n.get('@type') == 'FAQPage']:
            for q in faq.get('mainEntity', []):
                faq_count += 1
                check(prefix+'FAQ '+q['name'], visible(q['name']) in main_text and visible(q['acceptedAnswer']['text']) in main_text)
        block = BRIEF_RE.search(text)[0]
        brief_doc = Document(block)
        check(prefix+'three detail links', len(brief_doc.links) == 3)
        for link in brief_doc.links:
            parsed = urlsplit(urljoin(ORIGIN+route, link))
            target = ROOT / unquote(parsed.path).strip('/') / 'index.html'
            check(prefix+'detail anchor '+link, target.is_file() and parsed.fragment in Document(target.read_text(encoding='utf-8')).ids)
        check(prefix+'visible non-universal AI availability note', NOTE in visible(block))
        if '수학' in route and '영' not in route: check(prefix+'math AI specificity', 'AI 수학' in item['summary'] and '/overview/#ai-math' in brief_doc.links)
        if '영어' in route and '수학' not in route: check(prefix+'English AI specificity', 'AI 영어' in item['summary'] and '/overview/#ai-english' in brief_doc.links)
        sums.append(len(item['summary']))
        with urlopen('http://127.0.0.1:8795'+quote(route,safe='/'), timeout=20) as response:
            check(prefix+'local served exact source', response.status == 200 and response.read().decode('utf-8').replace('\r\n','\n') == text)
    sitemap = (ROOT/'sitemap.xml').read_text(encoding='utf-8')
    oldmap = baseline('sitemap.xml')
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    before = ET.fromstring(oldmap); after = ET.fromstring(sitemap)
    urls = lambda tree: [n.findtext('s:loc', namespaces=ns) for n in tree]
    check('sitemap 18345 URLs and order retained', urls(before) == urls(after) and len(urls(after)) == 18345)
    dates = {unquote(a.findtext('s:loc', namespaces=ns)).removeprefix(ORIGIN) for a,b in zip(after,before) if ET.tostring(a) != ET.tostring(b)}
    check('only 35 sitemap entries updated', dates == set(items), sorted(dates))
    check('sitemap repeatable', render_sitemap(items) == sitemap)
    for path in ['rss.xml', 'index.html', 'overview/index.html', 'vercel.json', 'assets/header.css', 'assets/fab.css', 'assets/learning-upgrade.css', 'assets/learning-upgrade.js']:
        check('protected file '+path, (ROOT/path).read_text(encoding='utf-8-sig') == baseline(path).replace('\r\n','\n'))
    check('new CSS below 5KB', (ROOT/'assets/hub-coaching-brief.css').stat().st_size < 5000)
    with urlopen('http://127.0.0.1:8795'+CSS_HREF, timeout=20) as response:
        check('stylesheet served correctly', response.status == 200 and 'css' in response.headers['Content-Type'])
    OUTPUT.mkdir(exist_ok=True)
    report = {'baseline': BASELINE, 'hubs': len(items), 'links': len(items)*3, 'faq_preserved': faq_count,
              'summary_characters': {'min':min(sums),'max':max(sums),'mean':round(sum(sums)/len(sums),1)},
              'checks':len(RESULTS),'passed':sum(r['pass'] for r in RESULTS), 'failed':[r for r in RESULTS if not r['pass']], 'results':RESULTS}
    (OUTPUT/'static-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))
    assert not report['failed'], 'See the scoped audit report'


if __name__ == '__main__': main()
