"""Refresh only changed sitemap records and the reviewed public-file hashes."""
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote, urlsplit
import argparse, hashlib, json, re

ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report-dir',type=Path,required=True);args=ap.parse_args()
    audit=json.loads((args.report_dir/'audit.json').read_text(encoding='utf-8'))
    assert not audit['errors'] and audit['changedPages']==8533 and audit['unchangedPages']==13010,'Scope audit must pass first'
    state=json.loads((args.report_dir/'applied-state.json').read_text(encoding='utf-8'))
    raw=(ROOT/'sitemap.xml').read_bytes().decode('utf-8');seen=set()
    def update(match):
        item=match[0];url=re.search(r'<loc>(.*?)</loc>',item)[1]
        path=unquote(urlsplit(url).path)
        if path in state:
            seen.add(path)
            return re.sub(r'<lastmod>[^<]+</lastmod>','<lastmod>2026-09-28</lastmod>',item,count=1)
        return item
    revised=re.sub(r'<url>.*?</url>',update,raw,flags=re.S)
    assert seen==set(state),'Sitemap coverage mismatch'
    (ROOT/'sitemap.xml').write_bytes(revised.encode('utf-8'))
    manifest=json.loads((ROOT/'release-public-manifest.json').read_text(encoding='utf-8'))
    assert manifest['domain']=='wawa-center.kr' and manifest['sitemapPages']==21543
    changed=[v['file'] for v in state.values()]+['assets/page-overlap-roles.css','assets/page-overlap-roles.js','sitemap.xml']
    for f in changed:
        data=(ROOT/f).read_bytes()
        manifest['files'][f]=hashlib.sha256(data).hexdigest()
        manifest['textSha256'][f]=hashlib.sha256(data.decode('utf-8').replace('\r\n','\n').encode('utf-8')).hexdigest()
    manifest['createdAt']=datetime.now().astimezone().isoformat()
    (ROOT/'release-public-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'sitemapChangedEntries':len(seen),'sitemapURLCount':21543,'publicFiles':len(manifest['files']),'refreshedHashes':len(changed),'rssChanged':False}
    (args.report_dir/'release-finalization.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
