"""Deterministic migration and regenerated-hub contracts (no external writes)."""
import json
import re
import unittest
from pathlib import Path
from urllib.parse import quote,unquote
from lxml import html

from branch_urls import center_path,hub_path,course_path,legacy_path,canonical,crumbs
from branch_seo import PageDates
from local_subject_content import load_sources
from migrate_local_subject_hubs import ROOT,mapping_replacer,render_hub
from export_branch_subject_urls import ordered_paths


class LocalSubjectHubsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
        cls.center=next(c for c in cls.centers if c['routeName']=='풍동점')
        cls.sources=load_sources()

    def test_requested_url_hierarchy(self):
        self.assertEqual(hub_path(self.center,'풍동','수학'),'/지점안내/경기/풍동점/풍동수학학원/')
        self.assertEqual(course_path(self.center,'풍동','고등','수학'),'/지점안내/경기/풍동점/풍동수학학원/고등/')
        self.assertEqual(len(crumbs(self.center,'풍동','수학','고등')),6)

    def test_reject_unmapped_neighborhood_and_unsafe_level(self):
        for args in [('다른동','고등','수학'),('풍동','../고등','수학'),('풍동','고등','과학')]:
            with self.assertRaises(ValueError):course_path(self.center,*args)

    def test_encoded_plain_query_fragment_and_html_old_links(self):
        old=legacy_path(self.center,'풍동','고등','수학');new=course_path(self.center,'풍동','고등','수학')
        replace=mapping_replacer({old:new})
        for suffix in ['', '?from=guide', '#faq', '?x=1#faq']:
            with self.subTest(suffix=suffix):
                self.assertEqual(replace(canonical(old)+suffix),canonical(new)+suffix)
                self.assertEqual(replace(old+suffix),new+suffix)
        self.assertEqual(replace(old+'index.html'),new)
        self.assertEqual(replace(old.rstrip('/')),new)
        self.assertEqual(replace(new),new)
        self.assertEqual(replace('/other/'+quote('풍동고등수학학원')+'/'),'/other/'+quote('풍동고등수학학원')+'/')

    def test_manuscripts_distinct_and_complete(self):
        self.assertEqual(len(self.sources),742)
        self.assertEqual(len({r['title'] for r in self.sources}),742)
        self.assertEqual(len({(r['locality'],r['subject']) for r in self.sources}),742)
        self.assertTrue(all(r['concern'] and r['habit'] and r['practice'] for r in self.sources))

    def test_regenerated_hub_keeps_facts_images_and_children(self):
        for subject in ('수학','영어'):
            item=next(r for r in self.sources if r['locality']=='풍동' and r['subject']==subject)
            raw,path=render_hub(self.center,item,PageDates(ROOT));doc=html.fromstring(raw)
            self.assertEqual(doc.xpath('//link[@rel="canonical"]/@href'),[canonical(path)])
            self.assertIn('초3~고1',doc.xpath('//*[@id="overview"]')[0].text_content())
            self.assertEqual(doc.xpath('//*[@id="child-pages"]//a/@href'),[course_path(self.center,'풍동',g,subject) for g in ('초등','중등','고등')])
            self.assertEqual(len(doc.xpath('//section[contains(@class,"branch-primary-media")]//img')),3)
            self.assertNotIn('공책를',raw)
            self.assertEqual(raw,(ROOT/path.strip('/')/'index.html').read_text(encoding='utf-8'))

    def test_export_hubs_before_grouped_grade_pages(self):
        paths=ordered_paths();self.assertEqual(len(paths),3179)
        self.assertTrue(all(len(p.strip('/').split('/'))==4 for p in paths[211:953]))
        for i,p in enumerate(paths[211:953]):
            self.assertEqual(paths[953+3*i:956+3*i],[p+g+'/' for g in ('초등','중등','고등')])

    def test_redirect_patterns_cover_every_legacy_url_once(self):
        rules=json.loads((ROOT/'vercel.json').read_text(encoding='utf-8'))['redirects'][:18]
        mapping=json.loads((ROOT/'tools/data/local-subject-hubs/url-migration.json').read_text(encoding='utf-8'))
        for old,new in mapping.items():
            for source in (old,old.rstrip('/'),old+'index.html'):
                matches=[]
                for rule in rules:
                    pattern=rule['source'].replace(':region','(?P<region>[^/]+)').replace(':center','(?P<center>[^/]+)').replace(':locality([^/]+)','(?P<locality>[^/]+)')
                    match=re.fullmatch(pattern,quote(source,safe='/'))
                    if match:
                        destination=rule['destination']
                        for name,value in match.groupdict().items():destination=destination.replace(':'+name,value)
                        matches.append(unquote(destination))
                self.assertEqual(matches,[new],source)


if __name__=='__main__':unittest.main()
