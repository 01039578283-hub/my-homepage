import copy
import json
import tempfile
import unittest
from pathlib import Path

from lxml import html

from branch_seo import ROOT, PageDates, GRAPH, finalize_page, content_hash, checked_source_date
from branch_page_summaries import center_summaries,validate_summaries
from branch_course_guidance import course_guidance
from refresh_branch_seo import protected


class BranchSEOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers=json.loads((ROOT/'tools/data/branch-directory/branches.json').read_text(encoding='utf-8'))['centers']
        cls.path='/지점안내/서울/명일점/'
        cls.raw=(ROOT/cls.path.strip('/')/'index.html').read_text(encoding='utf-8')

    def store(self,raw=None):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store=PageDates(Path(temp.name))
        store.seed(self.path,raw or self.raw,'2026-09-20')
        return store

    def test_titles_bodies_images_links_faq_unchanged(self):
        result=finalize_page(self.raw,self.path,store=self.store())
        self.assertEqual(protected(self.raw),protected(result))

    def test_social_tags_are_explicit_and_match_og(self):
        result=finalize_page(self.raw,self.path,store=self.store())
        doc=html.fromstring(result)
        for key in ('title','description','image'):
            self.assertEqual(doc.xpath(f'//meta[@name="twitter:{key}"]/@content'),doc.xpath(f'//meta[@property="og:{key}"]/@content'))

    def test_schema_section_not_an_itemlist(self):
        # Reconstruct the old invalid relationship, even after the site migration.
        old=json.loads(GRAPH.search(self.raw)[2])
        for node in old['@graph']:
            if node.get('@type')=='ItemList' and node['@id'].endswith('#learning-pages-list'):
                node['@id']=node['@id'].removesuffix('-list')
            if node.get('@type')=='WebPage':
                node['hasPart']=[{'@id':part['@id']} if part.get('@id','').endswith('#learning-pages') else part for part in node.get('hasPart',[])]
        match=GRAPH.search(self.raw)
        legacy=self.raw[:match.start(2)]+json.dumps(old,ensure_ascii=False)+self.raw[match.end(2):]
        result=finalize_page(legacy,self.path,store=self.store())
        graph=json.loads(GRAPH.search(result)[2])['@graph']
        listing=next(n for n in graph if n.get('@type')=='ItemList')
        self.assertTrue(listing['@id'].endswith('#learning-pages-list'))
        webpage=next(n for n in graph if n.get('@type')=='WebPage')
        part=next(n for n in webpage['hasPart'] if n.get('@id','').endswith('#learning-pages'))
        self.assertEqual(part['@type'],'WebPageElement')
        self.assertEqual(part['mainEntity']['@id'],listing['@id'])

    def test_future_build_does_not_refresh_dates(self):
        store=self.store()
        after=finalize_page(self.raw,self.path,store=store,today='2026-09-21')
        self.assertEqual(after,finalize_page(after,self.path,store=store,today='2030-01-01'))
        store.save()
        reloaded=PageDates(store.root)
        self.assertEqual(after,finalize_page(after,self.path,store=reloaded,today='2031-01-01'))

    def test_actual_content_change_preserves_original_publication(self):
        store=self.store()
        before=copy.deepcopy(store.records[self.path])
        result=finalize_page(self.raw,self.path,description='새로 검토한 실제 지점 안내입니다.',store=store,today='2026-09-22')
        self.assertEqual(store.records[self.path]['datePublished'],before['datePublished'])
        self.assertEqual(store.records[self.path]['dateModified'],'2026-09-22')
        self.assertEqual(result,finalize_page(result,self.path,store=store,today='2026-09-23'))

    def test_center_regeneration_retains_publication_history(self):
        from unittest.mock import patch
        import generate_branch_directory as directory
        center=next(c for c in self.centers if c['routeName']=='명일점')
        store=self.store()
        before=copy.deepcopy(store.records[self.path])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def finalize(raw,path):
                return finalize_page(raw,path,store=store,today='2030-01-01')
            with patch.object(directory,'OUTPUT_ROOT',root/'지점안내'), patch.object(directory,'finalize_page',finalize):
                path=directory.generate_branch_page(copy.deepcopy(center))
            rendered=(root/path.strip('/')/'index.html').read_text(encoding='utf-8')
        self.assertEqual(content_hash(self.raw),content_hash(rendered))
        self.assertEqual(store.records[self.path],before)

    def test_no_build_date_as_source_review_date(self):
        for center in self.centers:
            self.assertEqual(checked_source_date(center),center['informationReviewedAt'])
        self.assertEqual(checked_source_date({}),'2026-09-20')

    def test_unknown_existing_publication_requires_evidence(self):
        store=self.store()
        store.records.clear()
        target=store.root/self.path.strip('/')/'index.html'
        target.parent.mkdir(parents=True)
        target.write_text(self.raw,encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Missing publication history'):
            store.resolve(self.path,self.raw)

    def test_descriptions_use_only_verified_address_and_grade_ranges(self):
        descriptions=set()
        for center in self.centers:
            snapshot=copy.deepcopy(center)
            summary=center_summaries(center)
            validate_summaries(center,summary)
            self.assertIn(center['address'],summary['description'])
            self.assertIn(center['routeName'],summary['description'])
            for subject in ('영어','수학'):
                self.assertIn(course_guidance(center,subject)['label'],summary['description'])
            self.assertEqual(center,snapshot)
            descriptions.add(summary['description'])
        self.assertEqual(len(descriptions),193)


if __name__=='__main__':
    unittest.main()
