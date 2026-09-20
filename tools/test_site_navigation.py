"""Shared menu, lossless search delivery and image/content preservation tests."""
import copy
import unittest
from collections import Counter

from lxml import html

from compact_center_search import pack, unpack, read_source, render
from site_navigation import active_section, unify_header, NAV, FONT_URL
from refresh_site_navigation import ROOT, attr, image_hints, transform, validate


class SiteNavigationTest(unittest.TestCase):
    def test_active_sections_with_encoded_or_nested_routes(self):
        cases = {'/': '/', '/index.html': '/', '/center/gangwon/': '/center/', '/지점안내/서울/명일점/': '/지점안내/',
                 '/교육정보/공부법/': '/교육정보/', '/과목별학원/수학학원/명일동/': '/과목별학원/',
                 '/학년별학원/고2수학학원/': '/학년별학원/', '/guide/example/': '/guide/', '/overview/': '/overview/'}
        for route, section in cases.items():
            self.assertEqual(active_section(route), section)
        self.assertEqual(active_section('/%EC%A7%80%EC%A0%90%EC%95%88%EB%82%B4/'), '/지점안내/')

    def test_all_template_families_roundtrip(self):
        paths = ['index.html', 'overview/index.html', 'guide/index.html', 'center/index.html',
                 'center/gangwon/index.html', 'center/gangwon/wonjusi/dangyedong/highschoolmath/index.html',
                 '과목별학원/고등수학학원/명일동/index.html', '학년별학원/고2수학학원/명일동/index.html',
                 '교육정보/수학-공부법/index.html', '학부모후기/index.html', '지점안내/서울/명일점/index.html',
                 '지점안내/서울/명일점/명일동고등수학학원/index.html']
        for relative in paths:
            before = (ROOT / relative).read_text(encoding='utf-8-sig')
            after = transform(before, relative)
            validate(before, after, relative)
            self.assertEqual(transform(after, relative), after)

    def test_relative_header_stylesheet_and_repeated_run(self):
        raw = '<html><head><link rel="stylesheet" href="../../assets/header.css"></head><body><header class="site-header"><nav>old</nav></header><main><h1>원문</h1></main></body></html>'
        result = unify_header(raw, '/center/gangwon/')
        self.assertEqual(unify_header(result, '/center/gangwon/'), result)
        doc = html.fromstring(result)
        self.assertEqual(len(doc.xpath('//header//div/a')), len(NAV))
        self.assertEqual(doc.xpath('//link[@rel="stylesheet" and contains(@href,"googleapis")]/@href'), [FONT_URL])

    def test_hidden_and_map_loading_without_changing_image(self):
        stats = Counter()
        hidden = '<img src="https://example.com/a.gif" style="display:none;" alt="대표">'
        updated = image_hints(hidden, 'https://wawa-center.kr/', stats)
        self.assertIn('loading="lazy"', updated)
        self.assertIn('style="display:none;"', updated)
        visible = '<img src="/assets/centers/common/local.webp" alt="본문" loading="eager" fetchpriority="high">'
        output = image_hints(visible, 'https://wawa-center.kr/', stats)
        self.assertIn('loading="eager"', output)
        self.assertIn('fetchpriority="high"', output)
        self.assertIn('height="16116"', output)
        map_tag = '<img src="/assets/maps/myeongildong.jpg" alt="지도" width="648" height="702">'
        self.assertIn('loading="lazy"', image_hints(map_tag, 'https://wawa-center.kr/', stats))

    def test_attribute_update_is_safe(self):
        self.assertEqual(attr('<img data-loading="x" loading=\'eager\'>', 'loading', 'lazy'), '<img data-loading="x" loading="lazy">')
        self.assertEqual(attr('<img src="a"/>', 'decoding', 'async'), '<img src="a" decoding="async"/>')

    def test_search_rows_preserved_losslessly(self):
        rows = read_source()
        self.assertEqual(len(rows), 6025)
        self.assertEqual(unpack(pack(rows)), rows)
        self.assertLess(len(render(rows).encode('utf-8')), 600_000)
        custom = copy.deepcopy(rows[:1])
        custom[0]['search'] += ' 별도 검색어'
        self.assertEqual(unpack(pack(custom)), custom)

    def test_protected_content_rejects_unrelated_change(self):
        raw = (ROOT / 'center/gangwon/index.html').read_text(encoding='utf-8-sig')
        updated = transform(raw, 'center/gangwon/index.html')
        with self.assertRaisesRegex(ValueError, 'Protected content'):
            validate(raw, updated.replace('<title>강원', '<title>서울'), 'center/gangwon/index.html')


if __name__ == '__main__':
    unittest.main()
