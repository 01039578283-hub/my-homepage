"""Stage/audit a narrow SEO release; writes the site only with --write.

No manuscript regeneration, media processing, URL change or network submission.
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from lxml import html

from branch_seo import ROOT, DATE_BLOCK, GRAPH, PageDates, finalize_page, fix_parts
from branch_page_summaries import center_summaries, validate_summaries
from branch_release_check import refresh_sitemap

OUT = Path(r'C:\Users\1992k\Desktop\CodexData\outputs\wawa-branch-seo-fix-2026-09-21')


def protected(raw, branch=False):
    document = html.fromstring(DATE_BLOCK.sub('', raw))
    nodes = json.loads(document.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
    fix_parts(nodes)
    for n in nodes:
        if n.get('@type') in ('WebPage','CollectionPage','Article'):
            n.pop('datePublished',None)
            n.pop('dateModified',None)
            if branch:
                n.pop('description',None)
    allowed = '//script[@type="application/ld+json"] | //meta[starts-with(@name,"twitter:")]'
    if branch:
        allowed += ' | //meta[@name="description" or @property="og:description"]'
    for n in document.xpath(allowed):
        n.getparent().remove(n)
    for n in document.xpath('//link[starts-with(@href,"/assets/branch-directory.css")]'):
        n.set('href','/assets/branch-directory.css')
    for n in document.iter():
        for field in ('text','tail'):
            val = getattr(n,field)
            if val is not None and not val.strip():
                setattr(n,field,None)
    return {'graph':nodes,'html':html.tostring(document,encoding='unicode')}


def validate(raw,path,dates):
    doc=html.fromstring(raw)
    meta={n.get('name') or n.get('property'):n.get('content') for n in doc.xpath('//meta[@name or @property]')}
    assert len(doc.xpath('//title'))==1 and len(doc.xpath('//h1'))==1,path
    assert meta['twitter:title']==meta['og:title']==doc.xpath('//title/text()')[0],path
    assert meta['twitter:description']==meta['og:description']==meta['description'],path
    assert meta['twitter:image']==meta['og:image'],path
    assert unquote(urlsplit(doc.xpath('//link[@rel="canonical"]/@href')[0]).path)==path,path
    nodes=json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
    byid={n['@id']:n for n in nodes if '@id' in n}
    for n in nodes:
        if n.get('@type') in ('Article','WebPage','CollectionPage'):
            assert n['datePublished']==dates['datePublished'] and n['dateModified']==dates['dateModified'],path
            assert n['datePublished']<=n['dateModified']<=date.today().isoformat(),path
            for part in n.get('hasPart',[]):
                assert byid.get(part.get('@id'),part).get('@type')!='ItemList',path
        if n.get('@type')=='ItemList':
            assert n['numberOfItems']==len(n['itemListElement']),path
    visible=re.sub(r'\s+',' ',' '.join(doc.xpath('//main')[0].itertext()))
    faq=next(n for n in nodes if n.get('@type')=='FAQPage')
    for q in faq['mainEntity']:
        assert q['name'] in visible and q['acceptedAnswer']['text'] in visible,path
    assert doc.xpath('//p[@class="branch-page-dates"]//time/@datetime')==[dates['datePublished'],dates['dateModified']],path


def run(write=False):
    OUT.mkdir(parents=True,exist_ok=True)
    store=PageDates(ROOT)
    sitemap=(ROOT/'sitemap.xml').read_text(encoding='utf-8')
    sm=ET.fromstring(sitemap)
    entries={unquote(urlsplit(n.findtext('{*}loc')).path):n.findtext('{*}lastmod') for n in sm.findall('{*}url')}
    targets={p:d for p,d in entries.items() if p.startswith('/지점안내/')}
    centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    bypath={f'/지점안내/{c["region"]}/{c["routeName"]}/':c for c in centers}
    assert len(targets)==2436 and len(bypath)==193
    stats=Counter();changes=[];dates={};descriptions=set();titles=set()
    before_feeds={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['rss.xml','robots.txt','llms.txt']}
    for path,old_date in sorted(targets.items()):
        relative=Path(path.strip('/'))/'index.html'
        file=ROOT/relative
        before=file.read_text(encoding='utf-8')
        # Initial branch launch and all current publication evidence is Sep 20;
        # never use a filesystem mtime or today's date to reconstruct history.
        if path not in store.records:
            assert old_date=='2026-09-20',f'Review historical publication date: {path}'
            store.seed(path,before,old_date)
        center=bypath.get(path)
        description=None
        if center:
            summary=center_summaries(center)
            validate_summaries(center,summary)
            description=summary['description']
        after=finalize_page(before,path,description=description,store=store)
        assert protected(before,bool(center))==protected(after,bool(center)),f'Out-of-scope content change: {path}'
        validate(after,path,store.records[path])
        assert finalize_page(after,path,description=description,store=store,today='2026-09-22')==after,f'Rebuild refreshes dates: {path}'
        doc=html.fromstring(after)
        descriptions.add(doc.xpath('//meta[@name="description"]/@content')[0])
        titles.add(doc.xpath('//title/text()')[0])
        nodes=json.loads(GRAPH.search(after)[2])['@graph']
        stats['withoutService']+=int(len(path.strip('/').split('/'))==4 and not any(n.get('@type')=='Service' for n in nodes))
        stats['fixedListSections']+=sum(n.get('@type')=='ItemList' and n.get('@id','').endswith('#learning-pages-list') for n in nodes)
        stats['pages']+=1
        stats['centerDescriptions']+=int(center is not None)
        dates[path]=store.records[path]['dateModified']
        if before!=after:
            dest=OUT/'staged'/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(after,encoding='utf-8')
            changes.append({'path':path,'file':relative.as_posix(),'before':hashlib.sha256(file.read_bytes()).hexdigest(),'after':hashlib.sha256(after.encode()).hexdigest(),'published':store.records[path]['datePublished'],'modified':dates[path]})
    assert len(descriptions)==len(titles)==2436
    assert stats['withoutService']==52 and stats['fixedListSections']==188
    new_sitemap,sm_changes=refresh_sitemap(sitemap,dates)
    assert len(ET.fromstring(new_sitemap).findall('{*}url'))==20801
    (OUT/'staged'/'sitemap.xml').write_text(new_sitemap,encoding='utf-8')
    if write:
        for change in changes:
            destination=(ROOT/change['file']).resolve()
            assert destination.is_relative_to(ROOT.resolve())
            assert hashlib.sha256(destination.read_bytes()).hexdigest()==change['before'],'Concurrent edit'
            destination.write_bytes((OUT/'staged'/change['file']).read_bytes())
        if new_sitemap!=sitemap:
            (ROOT/'sitemap.xml').write_text(new_sitemap,encoding='utf-8')
        store.save()
    for f,h in before_feeds.items():
        assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
    report={'applied':write,'counts':dict(stats),'changedPages':len(changes),'changedSitemapDates':len(sm_changes),'dateDistribution':dict(Counter(dates.values())),'publicationDates':dict(Counter(v['datePublished'] for v in store.records.values())),'unchangedFeeds':before_feeds,'futureRebuildIdempotent':True,'errors':[]}
    (OUT/('verification.json' if write else 'dry-run.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    run(parser.parse_args().write)
