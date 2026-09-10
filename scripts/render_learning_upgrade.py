"""Render only home/overview from reviewed fragments; never regenerate regional pages.

Baseline is the last public release. Re-running replaces our marked blocks only.
Images in assets/official-learning are byte-identical copies of official source assets.
"""
import html
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = '244617da8d01b424bce8e539e2191244b8e746dc'
ORIGIN = 'https://wawa-center.kr'
UPDATED = '2026-09-11'
DATA = ROOT / 'scripts/data/brand-upgrade-20260911'
START, END = '<!-- WAWA_LEARNING_START -->', '<!-- WAWA_LEARNING_END -->'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class FAQs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.results, self.current = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class','').split()
        if 'wu-faq' in classes or 'faq-item' in classes:
            self.current = {'depth':len(self.stack), 'question':[], 'answer':[]}
        if tag not in VOID:
            self.stack.append((tag, classes))

    def handle_data(self, text):
        if not self.current or not text.strip():
            return
        question = any(t == 'summary' or 'faq-question' in c for t,c in self.stack[self.current['depth']:])
        self.current['question' if question else 'answer'].append(text.strip())

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        if self.current and len(self.stack) == self.current['depth']:
            self.results.append({
                '@type':'Question',
                'name':' '.join(self.current['question']),
                'acceptedAnswer':{'@type':'Answer','text':' '.join(self.current['answer'])},
            })
            self.current = None


DESCRIPTIONS = {
    'index.html':'와와학습코칭센터의 초중고 맞춤 학습코칭, 플랜·학습·생활 관리와 AI 영어·수학·국어·독서 프로그램을 사진과 영상으로 확인하세요. 가까운 센터와 상담 안내를 연결합니다.',
    'overview/index.html':'와와학습코칭센터의 4C 진단·처방·지도·상담, 플래너와 오답 관리, AI 학습클래스 대상 학년을 소개합니다. 학습 자료와 프로그램 화면, 상담 전 질문을 확인하세요.',
}
SECTIONS = {
    'index.html': [('academy','플랜·학습·생활 관리'),('learning-space','둥지형 학습 공간'),('wawa-videos','와와 소개 영상'),('ai-learning','AI 학습클래스'),('fee','자주 묻는 질문과 수강료')],
    'overview/index.html': [('four-c','4C 맞춤 코칭'),('coaching-care','계획·학습·생활 관리'),('ai-programs','AI 학습클래스'),('learning-stages','학년별 상담 준비'),('overview-faq','학원소개 자주 묻는 질문')],
}


def baseline(path):
    return subprocess.check_output(['git','show',f'{BASE}:{path}'],cwd=ROOT).decode('utf-8').replace('\r\n','\n')


def update_metadata(source, path):
    desc = DESCRIPTIONS[path]
    for key in ('name="description"','property="og:description"','name="tagline"'):
        source = re.sub(r'(<meta '+re.escape(key)+r' content=")[^"]*(")',lambda m:m[1]+html.escape(desc,quote=True)+m[2],source)
    faq = FAQs()
    faq.feed(source)
    expected = 3 if path == 'index.html' else 6
    assert len(faq.results) == expected, (path,len(faq.results))
    url = ORIGIN + ('/' if path == 'index.html' else '/overview/')
    pattern = r'(<script type="application/ld\+json">)(.*?)(</script>)'
    match = re.search(pattern,source,re.S)
    graph = json.loads(match[2])
    for node in graph['@graph']:
        if node.get('@type') == 'WebPage':
            node['description'] = desc
            node['dateModified'] = UPDATED
            node['hasPart'] = [{'@type':'WebPageElement','@id':url+'#'+sid,'url':url+'#'+sid,'name':name} for sid,name in SECTIONS[path]]
            node['mentions'] = [{'@type':'Thing','name':name} for name in ['4C 학습코칭','플랜 관리','학습 관리','생활 관리','AI 영어','AI 수학','AI 국어','AI 독서']]
        elif node.get('@type') == 'FAQPage':
            node['mainEntity'] = faq.results
            node['isPartOf'] = {'@id':url+'#webpage'}
        elif node.get('@type') == 'BreadcrumbList':
            for item in node['itemListElement']:
                if item.get('item') in ('/','./'):
                    item['item'] = ORIGIN+'/'
    return source[:match.start(2)]+json.dumps(graph,ensure_ascii=False,separators=(',',':'))+source[match.end(2):]


def render(path, fragment):
    file = ROOT / path
    source = file.read_text(encoding='utf-8')
    content = (DATA / fragment).read_text(encoding='utf-8').rstrip()
    marked = f'{START}\n{content}\n    {END}'
    if START in source:
        assert source.count(START) == source.count(END) == 1
        source = re.sub(re.escape(START)+r'.*?'+re.escape(END),lambda _:marked,source,flags=re.S)
    else:
        # Abort instead of overwriting another person's changes to the scoped pages.
        assert source == baseline(path), f'{path}: unexpected changes before initial rendering'
        if path == 'index.html':
            begin = source.index('    <section class="hero">')
            finish = source.index('    <section class="section-band" id="fee">')
        else:
            begin = source.index('<main>') + len('<main>')
            finish = source.index('  </main>',begin)
        source = source[:begin] + '\n    '+marked+'\n\n' + source[finish:]
        source = source.replace('<body>','<body class="wawa-upgrade">',1)
        source = source.replace('</head>','  <link rel="stylesheet" href="/assets/learning-upgrade.css">\n  <script src="/assets/learning-upgrade.js" defer></script>\n</head>',1)
        # The new script handles home FAQ state with aria-controls/aria-expanded.
        if path == 'index.html':
            source = re.sub(r'  <script>\s*document\.querySelectorAll\("\.faq-question"\).*?</script>', '',source, count=1,flags=re.S)
    source = source.replace('수업 일지와 플래너 기록을 바탕으로 주간, 월간 단위 피드백을 제공합니다. 필요 시 전화 상담 또는 대면 상담으로 보호자님과 자세히 공유합니다.', '학습 기록과 학생·보호자와의 소통을 바탕으로 공부의 변화를 확인합니다. 피드백의 주기와 공유 방식은 상담할 센터에서 안내받아 주세요.')
    source = re.sub(r'본 페이지는 모바일 접근성과 가독성을 고려해 제작된 (?:메인 화면|학원소개 페이지)입니다\.', '학생의 이해도와 공부 습관을 함께 살피는 학습코칭 안내',source)
    source = update_metadata(source,path)
    file.write_text(source,encoding='utf-8',newline='\n')
    return file


def main():
    assert ROOT.name == 'wawa-hub-release-2026-09-10'
    for path,fragment in [('index.html','home.html'),('overview/index.html','overview.html')]:
        print('Rendered:',render(path,fragment).relative_to(ROOT))
    sitemap = ROOT / 'sitemap.xml'
    source = sitemap.read_text(encoding='utf-8')
    for url in (ORIGIN+'/', ORIGIN+'/overview/'):
        pattern = r'(<loc>'+re.escape(url)+r'</loc>\s*<lastmod>)[^<]+(</lastmod>)'
        source,count = re.subn(pattern,lambda m:m[1]+UPDATED+m[2],source)
        assert count == 1, ('sitemap',url,count)
    sitemap.write_text(source,encoding='utf-8',newline='\n')


if __name__ == '__main__':
    main()
