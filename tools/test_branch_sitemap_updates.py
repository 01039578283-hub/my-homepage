"""Regression tests for adjacent generated sitemap sections."""

import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

import generate_branch_directory as directory
import generate_branch_topic_pages as topics


class SitemapUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wawa-sitemap-test-")
        self.root = Path(self.temp.name)
        self.sitemap = self.root / "sitemap.xml"
        self.original_root = directory.ROOT
        self.original_sitemap = topics.SITEMAP
        directory.ROOT = self.root
        topics.SITEMAP = self.sitemap
        self.sitemap.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://wawa-center.kr/original/</loc></url>\n'
            '</urlset>\n', encoding="utf-8"
        )

    def tearDown(self):
        directory.ROOT = self.original_root
        topics.SITEMAP = self.original_sitemap
        self.temp.cleanup()

    def locations(self):
        tree = ElementTree.parse(self.sitemap)
        return [node.text for node in tree.iter() if node.tag.endswith("}loc")]

    def test_adjacent_sections_preserve_indentation_and_are_idempotent(self):
        parent = "/지점안내/경기/화성태안점/"
        child = parent + "화성태안고등수학학원/"
        directory.update_sitemap([parent])
        topics.update_sitemap([child])
        initial = self.sitemap.read_text(encoding="utf-8")
        directory.update_sitemap([parent])
        self.assertIn("\n  <!-- branch-topic-pages:start -->", self.sitemap.read_text(encoding="utf-8"))
        topics.update_sitemap([child])
        self.assertEqual(initial, self.sitemap.read_text(encoding="utf-8"))
        self.assertEqual(self.locations(), [
            "https://wawa-center.kr/original/",
            directory.encoded_url(parent), topics.encoded_url(child)
        ])

    def test_topic_update_repairs_unindented_and_duplicate_blocks(self):
        child = "/지점안내/경기/화성태안점/화성태안초등영어학원/"
        old_block = (
            '<!-- branch-topic-pages:start -->\n'
            '  <url><loc>https://wawa-center.kr/obsolete/</loc></url>\n'
            '  <!-- branch-topic-pages:end -->\n'
        )
        text = self.sitemap.read_text(encoding="utf-8")
        self.sitemap.write_text(text.replace("</urlset>", old_block + "  " + old_block + "</urlset>"), encoding="utf-8")
        topics.update_sitemap([child])
        self.assertEqual(self.locations(), ["https://wawa-center.kr/original/", topics.encoded_url(child)])
        self.assertEqual(self.sitemap.read_text(encoding="utf-8").count("<!-- branch-topic-pages:start -->"), 1)

    def test_directory_update_repairs_an_unindented_block(self):
        parent = "/지점안내/경기/화성태안점/"
        directory.update_sitemap(["/old-branch/"])
        text = self.sitemap.read_text(encoding="utf-8").replace("  <!-- branch-directory:start -->", "<!-- branch-directory:start -->")
        self.sitemap.write_text(text, encoding="utf-8")
        directory.update_sitemap([parent])
        self.assertEqual(self.locations(), ["https://wawa-center.kr/original/", directory.encoded_url(parent)])


if __name__ == "__main__":
    unittest.main()
