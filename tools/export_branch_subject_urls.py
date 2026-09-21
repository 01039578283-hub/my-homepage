"""Export the current branch tree as Korean URLs, with hubs before children."""
import json
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from branch_urls import DOMAIN, LEVELS, SUBJECTS, center_path, hub_path, course_path
from generate_branch_directory import REGIONS

ROOT=Path(__file__).resolve().parents[1]
DEST=Path(r'C:\Users\1992k\Desktop\wawa-center.kr_지점안내_전체URL_허브순_2026-09-21.txt')


def ordered_paths():
    centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
    regions=[r for r in REGIONS if any(c['region']==r for c in centers)]
    centers=sorted(centers,key=lambda c:(regions.index(c['region']),c['routeName']))
    tuples=[(c,locality,subject) for c in centers for locality in sorted(c['neighborhoods']) for subject in SUBJECTS]
    paths=['/','/지점안내/']
    paths.extend(f'/지점안내/{r}/' for r in regions)
    paths.extend(center_path(c) for c in centers)
    paths.extend(hub_path(c,l,s) for c,l,s in tuples)
    paths.extend(course_path(c,l,g,s) for c,l,s in tuples for g in LEVELS)
    assert len(paths)==len(set(paths))==3179
    assert Counter(len(p.strip('/').split('/')) for p in paths[1:])=={1:1,2:16,3:193,4:742,5:2226}
    sitemap={unquote(urlsplit(e.findtext('{*}loc')).path) for e in ET.parse(ROOT/'sitemap.xml').getroot().findall('{*}url')}
    assert set(paths[1:])=={p for p in sitemap if p.startswith('/지점안내/')}
    assert all((ROOT/p.strip('/')/'index.html').is_file() for p in paths)
    return paths


def main():
    lines=[DOMAIN+p for p in ordered_paths()]
    content='\n'.join(lines)+'\n'
    if DEST.exists() and DEST.read_text(encoding='utf-8-sig')!=content:
        raise FileExistsError('Refusing to overwrite a different existing URL inventory: '+str(DEST))
    DEST.write_text(content,encoding='utf-8-sig',newline='\r\n')
    readback=DEST.read_text(encoding='utf-8-sig').splitlines()
    assert readback==lines and len(set(readback))==3179
    assert not any('%' in value or 'xn--' in value or '#' in value for value in readback)
    print(json.dumps({'file':str(DEST),'lines':len(lines),'branchUrls':len(lines)-1,'mainIncluded':True},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
