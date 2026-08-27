from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class AboutPageTestCase(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse('about'))
        self.content = self.response.content.decode()

    def test_about_describes_skoj(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertContains(self.response, 'SKOJ : SKALA Online Judge')
        self.assertContains(self.response, 'SKALA 교육생을 위한 알고리즘 학습·연습·자동 채점 사이트')
        self.assertContains(self.response, '실제 기업 코딩 테스트 유형과 유사한 문제')

    def test_project_information_uses_skoj_links(self):
        self.assertContains(self.response, 'https://github.com/SKOJ-TEAM/SKOJ')
        self.assertContains(self.response, 'mailto:skojteam@gmail.com')
        self.assertNotContains(self.response, '>Docs<')

    def test_development_team_only_lists_current_members(self):
        self.assertContains(self.response, 'SKOJ DEVELOPMENT TEAM')
        self.assertContains(self.response, '송정규ㆍ이인우')

    def test_old_project_content_is_not_rendered(self):
        old_terms = (
            'Litmus', 'JBNU', 'ALPS', '전북대학교', 'JHelper', 'Special Thanks To', 'Patch Note',
        )
        for term in old_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, self.content)
