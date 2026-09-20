import json
import unittest

from center_course_names import rename, transform, json_names, DOMAIN

CENTER = DOMAIN + '/center/seoul/gangdonggu/myeongildong/highschoolmath/'
OTHER = DOMAIN + '/과목별학원/고등수학학원/명일동/'


class CourseNamesTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(rename('초등 영어학원 중등수학학원 고등 수학 학원'),
                         '초등학생 영어학원 중학생수학학원 고등학생 수학 학원')

    def test_school_facts_and_existing_names(self):
        text = '명일고등학교 초등반 중등반 고등반 초등학생 수학학원 중학생 영어학원 고등학생 수학학원'
        self.assertEqual(rename(text), text)

    def test_metadata_and_alt(self):
        raw = '<title>명일동 고등 수학학원</title><meta name="description" content="고등 수학학원"><img alt="고등수학학원" src="/고등수학학원.jpg"><p id="고등수학학원">고등 수학학원</p>'
        output = transform(raw, CENTER)
        self.assertIn('명일동 고등학생 수학학원', output)
        self.assertIn('content="고등학생 수학학원"', output)
        self.assertIn('alt="고등학생수학학원"', output)
        self.assertIn('src="/고등수학학원.jpg"', output)
        self.assertIn('id="고등수학학원"', output)
        self.assertEqual(transform(output, CENTER), output)

    def test_links_respect_destination(self):
        raw = '<p>고등 수학학원</p><a href="' + OTHER + '"><b>고등 수학학원</b></a><a href="' + CENTER + '">고등 수학학원</a>'
        output = transform(raw, CENTER)
        self.assertIn('<b>고등 수학학원</b>', output)
        self.assertIn(CENTER + '">고등학생 수학학원', output)
        other = transform(raw, OTHER)
        self.assertIn('<p>고등 수학학원</p>', other)
        self.assertIn(CENTER + '">고등학생 수학학원', other)

    def test_scripts_comments_and_style_untouched(self):
        raw = '<!-- 고등 수학학원 --><script>let x="고등 수학학원";</script><style>/* 고등 수학학원 */</style>'
        self.assertEqual(transform(raw, CENTER), raw)

    def test_json_destinations_and_ratings(self):
        data = {'@graph': [
            {'url': CENTER, 'name': '고등 수학학원', 'ratingValue': '4.8', 'reviewCount': 6},
            {'url': OTHER, 'name': '고등 수학학원'},
            {'@type': 'ListItem', 'name': '고등 수학학원', 'item': CENTER},
        ]}
        output = json_names(data, OTHER, False)
        self.assertEqual(output['@graph'][0]['name'], '고등학생 수학학원')
        self.assertEqual(output['@graph'][0]['ratingValue'], '4.8')
        self.assertEqual(output['@graph'][0]['reviewCount'], 6)
        self.assertEqual(output['@graph'][1], data['@graph'][1])
        self.assertEqual(output['@graph'][2]['name'], '고등학생 수학학원')
        raw = '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'
        self.assertEqual(transform(transform(raw, OTHER), OTHER), transform(raw, OTHER))

    def test_relative_links_entities_and_line_offsets(self):
        raw = '<p>고등 수학학원 &amp; 안내</p>\r\n<a href="../middleschoolmath/">중등 수학학원</a>'
        output = transform(raw, CENTER)
        self.assertIn('&amp;', output)
        self.assertIn('\r\n', output)
        self.assertIn('>중학생 수학학원<', output)


if __name__ == '__main__':
    unittest.main()
