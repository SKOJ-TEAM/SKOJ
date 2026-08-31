from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import AlgorithmGuide, GuideCompletion, ProblemGroup
from judge.models.tests.util import CommonDataMixin


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class GuideViewTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sorting = ProblemGroup.objects.create(name='sorting-guide', full_name='정렬')
        cls.graph = ProblemGroup.objects.create(name='graph-guide', full_name='그래프')
        cls.empty = ProblemGroup.objects.create(name='empty-guide', full_name='빈 그룹')
        cls.published = AlgorithmGuide.objects.create(
            problem_group=cls.sorting,
            title='버블 정렬',
            summary='인접한 원소를 비교하는 정렬입니다.',
            content=(
                '## 동작 원리\n\n'
                '시간 복잡도는 $O(n^3)$입니다.\n\n'
                '$$\\sum_{i=1}^{n} i$$\n\n'
                '```python\nprint("sorted")\n```\n\n'
                '<script>alert("unsafe")</script>'
            ),
            is_published=True,
            order=2,
        )
        cls.first = AlgorithmGuide.objects.create(
            problem_group=cls.sorting,
            title='정렬 소개',
            summary='정렬을 시작합니다.',
            content='정렬 소개',
            is_published=True,
            order=1,
        )
        cls.draft = AlgorithmGuide.objects.create(
            problem_group=cls.sorting,
            title='작성 중',
            summary='아직 공개되지 않았습니다.',
            content='<script>alert(1)</script>',
            is_published=False,
        )
        cls.graph_draft = AlgorithmGuide.objects.create(
            problem_group=cls.graph,
            title='그래프 초안',
            summary='초안',
            content='초안',
            is_published=False,
        )

    def setUp(self):
        self.client.force_login(self.users['normal'])

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()

        for url in (
            reverse('guide_tag_list'),
            reverse('guide_list', args=(self.sorting.name,)),
            self.published.get_absolute_url(),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('auth_login'), response.url)

    def test_tag_list_only_shows_tags_with_published_guides(self):
        response = self.client.get(reverse('guide_tag_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '정렬')
        self.assertNotContains(response, '그래프')
        self.assertNotContains(response, '빈 그룹')

    def test_tag_list_uses_curriculum_order_and_shows_contiguous_numbers(self):
        fundamentals = ProblemGroup.objects.create(name='fundamentals', full_name='Fundamentals')
        AlgorithmGuide.objects.create(
            problem_group=fundamentals,
            title='기초',
            summary='기초 과정',
            content='기초',
            is_published=True,
            order=0,
        )

        response = self.client.get(reverse('guide_tag_list'))
        content = response.content.decode()

        self.assertLess(content.index('Fundamentals'), content.index('정렬'))
        self.assertContains(response, '<span class="guide-number">01</span>', html=True)
        self.assertContains(response, '<span class="guide-number">02</span>', html=True)

    def test_legacy_problem_group_urls_redirect_permanently_to_english_slug(self):
        greedy = ProblemGroup.objects.create(name='greedy', full_name='그리디')
        guide = AlgorithmGuide.objects.create(
            problem_group=greedy,
            title='그리디',
            summary='그리디 과정',
            content='그리디',
            is_published=True,
            order=21,
        )

        list_response = self.client.get(reverse('guide_list', args=('그리디',)))
        detail_response = self.client.get(reverse('guide_detail', args=('그리디', guide.pk)))

        self.assertRedirects(
            list_response,
            reverse('guide_list', args=('greedy',)),
            status_code=301,
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            detail_response,
            reverse('guide_detail', args=('greedy', guide.pk)),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_guide_ui_uses_problem_group_full_name(self):
        greedy = ProblemGroup.objects.create(name='greedy', full_name='그리디')
        guide = AlgorithmGuide.objects.create(
            problem_group=greedy,
            title='그리디 입문',
            summary='그리디 과정',
            content='그리디',
            is_published=True,
            order=21,
        )

        tag_response = self.client.get(reverse('guide_tag_list'))
        list_response = self.client.get(reverse('guide_list', args=('greedy',)))
        detail_response = self.client.get(guide.get_absolute_url())

        self.assertContains(tag_response, '<h2>그리디</h2>', html=True)
        self.assertContains(list_response, '<h1>그리디</h1>', html=True)
        self.assertContains(detail_response, '← 그리디')

    def test_guide_list_shows_published_guides_in_order(self):
        response = self.client.get(reverse('guide_list', args=(self.sorting.name,)))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertLess(content.index('정렬 소개'), content.index('버블 정렬'))
        self.assertContains(response, '인접한 원소를 비교하는 정렬입니다.')
        self.assertNotContains(response, '작성 중')

    def test_guide_detail_renders_markdown(self):
        response = self.client.get(self.published.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h2')
        self.assertContains(response, '동작 원리')
        self.assertContains(response, '<pre')
        self.assertContains(response, '<code')
        self.assertContains(response, 'sorted')
        self.assertNotContains(response, '<script>')
        self.assertContains(response, r'\(O(n^3)\)')
        self.assertContains(response, r'\[\sum_{i=1}^{n} i\]')
        self.assertContains(response, 'mathjax_config.js')
        self.assertContains(response, 'vendor/mathjax/3.2.0/es5/tex-chtml.min.js')
        self.assertContains(response, 'background: #f6f8fa;')
        self.assertContains(response, 'background: #161b22;')
        self.assertContains(response, '이 가이드를 읽었어요')
        self.assertFalse(response.context_data['guide_completed'])

    def test_guide_completion_can_be_checked_idempotently_and_unchecked(self):
        url = self.published.get_absolute_url()

        first_response = self.client.post(url, {'completed': '1'})
        second_response = self.client.post(url, {'completed': '1'})

        self.assertRedirects(
            first_response,
            url + '#guide-completion',
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            second_response,
            url + '#guide-completion',
            fetch_redirect_response=False,
        )
        self.assertEqual(GuideCompletion.objects.filter(
            profile=self.users['normal'].profile,
            guide=self.published,
        ).count(), 1)
        checked_response = self.client.get(url)
        self.assertTrue(checked_response.context_data['guide_completed'])
        self.assertContains(checked_response, 'name="completed" value="1"', html=False)
        self.assertContains(checked_response, 'checked', html=False)

        unchecked_response = self.client.post(url, {'completed': '0'})

        self.assertRedirects(
            unchecked_response,
            url + '#guide-completion',
            fetch_redirect_response=False,
        )
        self.assertFalse(GuideCompletion.objects.filter(
            profile=self.users['normal'].profile,
            guide=self.published,
        ).exists())

    def test_guide_completion_is_isolated_between_users(self):
        GuideCompletion.objects.create(
            profile=self.users['normal'].profile,
            guide=self.published,
        )

        self.client.force_login(self.users['superuser'])
        response = self.client.get(self.published.get_absolute_url())

        self.assertFalse(response.context_data['guide_completed'])

    def test_completion_post_rejects_hidden_mismatched_and_invalid_requests(self):
        hidden_response = self.client.post(self.draft.get_absolute_url(), {'completed': '1'})
        mismatched_response = self.client.post(reverse(
            'guide_detail', args=(self.graph.name, self.published.pk),
        ), {'completed': '1'})
        invalid_response = self.client.post(self.published.get_absolute_url(), {'completed': 'yes'})

        self.assertEqual(hidden_response.status_code, 404)
        self.assertEqual(mismatched_response.status_code, 404)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertFalse(GuideCompletion.objects.exists())

    def test_admin_edit_link_only_shows_to_users_with_change_permission(self):
        normal_response = self.client.get(self.published.get_absolute_url())
        self.client.force_login(self.users['superuser'])
        admin_response = self.client.get(self.published.get_absolute_url())

        edit_url = reverse('admin:judge_algorithmguide_change', args=(self.published.pk,))
        self.assertNotContains(normal_response, edit_url)
        self.assertContains(admin_response, edit_url)
        self.assertContains(admin_response, '관리자에서 편집')

    def test_hidden_or_mismatched_guide_returns_not_found(self):
        hidden_response = self.client.get(self.draft.get_absolute_url())
        mismatched_response = self.client.get(reverse(
            'guide_detail', args=(self.graph.name, self.published.pk),
        ))

        self.assertEqual(hidden_response.status_code, 404)
        self.assertEqual(mismatched_response.status_code, 404)

    def test_authenticated_navigation_uses_requested_order_without_contests(self):
        response = self.client.get('/')
        content = response.content.decode()

        labels = ('GUIDE', 'PROBLEMS', 'RANKING', 'USERS', 'STATUS', 'ABOUT')
        positions = [content.index('>%s</a>' % label) for label in labels]

        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('>CONTESTS</a>', content)

    def test_anonymous_navigation_hides_guide(self):
        self.client.logout()

        response = self.client.get('/')

        self.assertNotContains(response, '>GUIDE</a>', html=False)
