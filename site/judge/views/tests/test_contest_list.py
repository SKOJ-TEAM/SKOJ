from django.test import TestCase, override_settings


@override_settings(COMPRESS_ENABLED=False)
class ContestListPageTestCase(TestCase):
    def setUp(self):
        self.contest_response = self.client.get('/contests/0/')
        self.practice_response = self.client.get('/contests/1/')

    def test_contest_list_renders(self):
        self.assertEqual(self.contest_response.status_code, 200)
        self.assertEqual(self.practice_response.status_code, 200)

    def test_page_intro_copy(self):
        contest_content = self.contest_response.content.decode()
        self.assertIn('<h1 class="contest-page-title">대회</h1>', contest_content)
        self.assertIn('진행 중이거나 예정된 대회를 확인하세요.', contest_content)

        practice_content = self.practice_response.content.decode()
        self.assertIn('<h1 class="contest-page-title">과제</h1>', practice_content)
        self.assertIn('진행 중이거나 예정된 과제를 확인하세요.', practice_content)

    def test_list_tab_label(self):
        self.assertIn('대회 목록', self.contest_response.content.decode())
        self.assertIn('과제 목록', self.practice_response.content.decode())

    def test_no_stray_litmus_primary_variable(self):
        content = self.contest_response.content.decode()
        self.assertNotIn('LITMUS-Primary', content)
        self.assertNotIn('LITMUS-primary', content)


@override_settings(COMPRESS_ENABLED=False)
class ContestPastListPageTestCase(TestCase):
    def setUp(self):
        self.contest_response = self.client.get('/contests/0/past')
        self.practice_response = self.client.get('/contests/1/past')

    def test_past_list_renders(self):
        self.assertEqual(self.contest_response.status_code, 200)
        self.assertEqual(self.practice_response.status_code, 200)

    def test_page_intro_copy(self):
        contest_content = self.contest_response.content.decode()
        self.assertIn('<h1 class="contest-page-title">대회</h1>', contest_content)
        self.assertIn('종료된 대회를 확인하세요.', contest_content)

        practice_content = self.practice_response.content.decode()
        self.assertIn('<h1 class="contest-page-title">과제</h1>', practice_content)
        self.assertIn('종료된 과제를 확인하세요.', practice_content)
