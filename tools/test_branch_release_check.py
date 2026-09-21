"""Feed synchronization contracts; never mutate the real site in tests."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from lxml import html

from branch_release_check import (
    CONTENT, ROOT, cdata, feed_body, file_for_url, normalized_url,
    refresh_rss, refresh_sitemap, scoped_paths,
)


class ReleaseFeedTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='wawa-feed-contract-')
        self.root = Path(self.directory.name)
        (self.root / '교육정보/예시').mkdir(parents=True)
        self.source = (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<link rel="canonical" href="https://wawa-center.kr/교육정보/예시/">'
            '<meta name="description" content="현재 페이지 요약 &amp; 확인"></head>'
            '<body><header>공통 메뉴</header><main><h1>실제 글 제목</h1>'
            '<p>첫 문단</p><section><h2>중간 제목</h2><p>전체 본문도 유지</p>'
            '<a href="/지점안내/서울/명일점/#center-info">지점 확인</a>'
            '<img src="/assets/body.webp" width="768" height="2500" alt="본문" onclick="bad()">'
            '<picture><source srcset="/assets/small.avif 480w, /assets/large.avif 768w" type="image/avif">'
            '<img src="/assets/fallback.webp" alt="그림"></picture>'
            '<script>not_feed()</script><form><input name="q"><button>찾기</button></form>'
            '<a href="javascript:bad()">잘못된 실행 링크</a></section><p>마지막 문단</p></main>'
            '<footer>공통 하단</footer></body></html>'
        )
        (self.root / '교육정보/예시/index.html').write_text(self.source, encoding='utf-8')
        self.url = 'https://wawa-center.kr/%EA%B5%90%EC%9C%A1%EC%A0%95%EB%B3%B4/%EC%98%88%EC%8B%9C/'
        self.rss = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>'
            '<title>기존 피드 제목</title><link>https://wawa-center.kr/</link>'
            '<description>기존 채널 설명</description>'
            '<lastBuildDate>Mon, 14 Sep 2026 09:30:31 +0900</lastBuildDate>\n'
            '<item><title>기존 글 제목</title><link>' + self.url + '</link>'
            '<guid isPermaLink="true">' + self.url + '</guid>'
            '<pubDate>Mon, 14 Sep 2026 09:30:31 +0900</pubDate>'
            '<description>기존 요약</description></item></channel></rss>'
        )
        self.now = datetime(2026, 9, 20, 14, 10, tzinfo=timezone(timedelta(hours=9)))
        self.sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\r\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\r\n'
            '  <!-- preserve this -->\r\n'
            '  <url><loc>https://wawa-center.kr/교육정보/예시/</loc><lastmod>2026-09-15</lastmod></url>\r\n'
            '  <url><loc>https://wawa-center.kr/other/</loc><lastmod>2026-07-01</lastmod></url>\r\n'
            '</urlset>\r\n'
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_current_scope_is_3920_unique_pages(self):
        scope = scoped_paths()
        self.assertEqual(len(scope), 3920)
        self.assertEqual(len(set(scope)), 3920)
        self.assertTrue(all(p.is_file() for p in scope))

    def test_korean_iri_is_same_canonical_not_false_mismatch(self):
        self.assertEqual(normalized_url(self.url), normalized_url('https://wawa-center.kr/교육정보/예시/'))

    def test_url_identity_preserves_query_fragment_and_trailing_slash(self):
        for suffix in ('?page=1', '#body'):
            self.assertNotEqual(normalized_url(self.url), normalized_url(self.url + suffix))
        self.assertNotEqual(normalized_url(self.url), normalized_url(self.url.rstrip('/')))

    def test_unsafe_paths_or_other_hosts_refused(self):
        for url in ('https://wawa-center.kr/a%2fb/', 'https://wawa-center.kr/a%5cb/', 'https://wawa-center.kr/../secret', 'https://wawa-center.kr/%2e%2e/secret', 'https://other.test/file', 'http://wawa-center.kr/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                file_for_url(url, self.root)

    def test_sitemap_changes_exact_reviewed_date_only(self):
        result, changes = refresh_sitemap(self.sitemap, {'/교육정보/예시/': '2026-09-20'})
        self.assertEqual(result, self.sitemap.replace('<lastmod>2026-09-15</lastmod>', '<lastmod>2026-09-20</lastmod>'))
        self.assertEqual(len(changes), 1)

    def test_sitemap_is_idempotent(self):
        first, _ = refresh_sitemap(self.sitemap, {'/교육정보/예시/': '2026-09-20'})
        second, changes = refresh_sitemap(first, {'/교육정보/예시/': '2026-09-20'})
        self.assertEqual(first, second)
        self.assertEqual(changes, [])

    def test_sitemap_missing_duplicate_or_absent_date_refused(self):
        bad = [self.sitemap.replace('/교육정보/예시/', '/wrong/'),
               self.sitemap.replace('/other/', '/교육정보/예시/'),
               self.sitemap.replace('<lastmod>2026-09-15</lastmod>', '')]
        for source in bad:
            with self.assertRaises(ValueError):
                refresh_sitemap(source, {'/교육정보/예시/': '2026-09-20'})

    def test_feed_retains_item_identity_order_and_publication(self):
        result, changes = refresh_rss(self.rss, self.now, self.root)
        before, after = ET.fromstring(self.rss), ET.fromstring(result)
        for field in ('title', 'link', 'guid', 'pubDate'):
            self.assertEqual(before.findtext('channel/item/' + field), after.findtext('channel/item/' + field))
        self.assertEqual(after.find('channel/item/guid').attrib, before.find('channel/item/guid').attrib)
        self.assertEqual(after.findtext('channel/title'), '기존 피드 제목')
        self.assertEqual(len(changes), 1)
        self.assertTrue(changes[0]['descriptionChanged'])

    def test_feed_description_and_full_body_match_actual_source(self):
        result, _ = refresh_rss(self.rss, self.now, self.root)
        item = ET.fromstring(result).find('channel/item')
        self.assertEqual(item.findtext('description'), '현재 페이지 요약 & 확인')
        body = item.findtext(CONTENT)
        for phrase in ('첫 문단', '중간 제목', '전체 본문도 유지', '마지막 문단'):
            self.assertIn(phrase, body)
        for phrase in ('공통 메뉴', '공통 하단', 'not_feed()', 'onclick', 'javascript:'):
            self.assertNotIn(phrase, body)

    def test_full_body_images_and_navigation_are_absolute(self):
        result, _ = refresh_rss(self.rss, self.now, self.root)
        body = html.fromstring(ET.fromstring(result).find('channel/item').findtext(CONTENT))
        self.assertIn(normalized_url('https://wawa-center.kr/지점안내/서울/명일점/#center-info'), [normalized_url(value) for value in body.xpath('//a/@href')])
        self.assertIn('https://wawa-center.kr/assets/body.webp', body.xpath('//img/@src'))
        self.assertEqual(body.xpath('//img[@alt="본문"]/@height'), ['2500'])
        self.assertIn('https://wawa-center.kr/assets/small.avif 480w', body.xpath('//source/@srcset')[0])

    def test_feed_refresh_does_not_touch_source_document(self):
        path = self.root / '교육정보/예시/index.html'
        before = path.read_bytes()
        document = html.fromstring(before)
        original = html.tostring(document)
        feed_body(document, self.url)
        self.assertEqual(original, html.tostring(document))
        refresh_rss(self.rss, self.now, self.root)
        self.assertEqual(before, path.read_bytes())

    def test_existing_content_is_replaced_once_and_no_duplicate_added(self):
        old = self.rss.replace('</description></item>', '</description><content:encoded><![CDATA[<p>old</p>]]></content:encoded></item>')
        result, _ = refresh_rss(old, self.now, self.root)
        self.assertEqual(result.count('<content:encoded>'), 1)
        self.assertNotIn('<p>old</p>', result)

    def test_feed_is_idempotent_even_at_a_later_time(self):
        result, _ = refresh_rss(self.rss, self.now, self.root)
        second, changes = refresh_rss(result, self.now + timedelta(days=1), self.root)
        self.assertEqual(result, second)
        self.assertEqual(changes, [])

    def test_feed_build_date_changes_not_publication_date(self):
        result, _ = refresh_rss(self.rss, self.now, self.root)
        root = ET.fromstring(result)
        self.assertEqual(root.findtext('channel/lastBuildDate'), 'Sun, 20 Sep 2026 14:10:00 +0900')
        self.assertEqual(root.findtext('channel/item/pubDate'), 'Mon, 14 Sep 2026 09:30:31 +0900')

    def test_mismatched_canonical_stops_feed_write(self):
        file = self.root / '교육정보/예시/index.html'
        file.write_text(self.source.replace('href="https://wawa-center.kr/교육정보/예시/"', 'href="https://wawa-center.kr/other/"'), encoding='utf-8')
        with self.assertRaises(ValueError):
            refresh_rss(self.rss, self.now, self.root)

    def test_cdata_terminator_round_trips(self):
        text = '<p>edge ]]> & 끝</p>'
        self.assertEqual(ET.fromstring('<x>' + cdata(text) + '</x>').text, text)

    def test_windows_html_newlines_round_trip_through_xml_cdata(self):
        file = self.root / '교육정보/예시/index.html'
        file.write_bytes(self.source.replace('</p>', '</p>\r\n').encode('utf-8'))
        result, _ = refresh_rss(self.rss, self.now, self.root)
        actual = ET.fromstring(result).find('channel/item').findtext(CONTENT)
        self.assertEqual(actual, feed_body(html.fromstring(file.read_bytes()), self.url))
        self.assertNotIn('\r', actual)

    def test_missing_main_or_multiple_main_is_rejected(self):
        for markup in ('<html><p>no main</p></html>', '<html><main>a</main><main>b</main></html>'):
            with self.assertRaises(ValueError):
                feed_body(html.fromstring(markup), self.url)

    def test_feed_blank_line_indents_removed_but_inline_and_pre_spaces_preserved(self):
        markup = '<main><p><b>앞</b> <b>뒤</b></p>\n     \n<section>끝</section><pre>code\n   \nend</pre></main>'
        body = feed_body(html.fromstring(markup), self.url)
        self.assertIn('</b> <b>', body)
        self.assertIn('<pre>code\n   \nend</pre>', body)
        self.assertNotIn('</p>\n     \n', body)


if __name__ == '__main__':
    unittest.main()
