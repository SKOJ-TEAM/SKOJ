from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from judge.models import Contest, Language, PromotionExam, Submission, Tier
from judge.models.tests.util import create_contest_participation, create_problem, create_problem_group
from judge.utils.problem_navigation import problem_group_navigation


class ProblemNavigationPolicyTest(SimpleTestCase):
    def test_only_public_ordinary_practice_provides_navigation(self):
        defaults = dict(is_public=True, is_encrypted=False, is_contest_problem=False, promotion_exam_id=None,
                        group=SimpleNamespace(name='stack', full_name='스택'))
        self.assertEqual(problem_group_navigation(SimpleNamespace(**defaults)),
                         {'name': '스택', 'url': '/problems/stack/'})
        for changes in ({'is_public': False}, {'is_encrypted': True},
                        {'is_contest_problem': True}, {'promotion_exam_id': 1}):
            with self.subTest(changes=changes):
                self.assertIsNone(problem_group_navigation(SimpleNamespace(**dict(defaults, **changes))))
        for flags in ({'in_contest': True}, {'contest_submission': True}):
            with self.subTest(flags=flags):
                self.assertIsNone(problem_group_navigation(SimpleNamespace(**defaults), **flags))


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ProblemNavigationViewTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='navigation-user')
        self.client.force_login(self.user)
        self.group = create_problem_group(name='navigation-stack', full_name='스택')
        self.problem = create_problem(
            code='navigation-problem', name='탐색 테스트 문제', group=self.group, is_public=True,
            summary='탐색 테스트', og_image='/static/test.png', allowed_languages=('PY3',),
        )
        self.submission = Submission.objects.create(
            problem=self.problem, user=self.user.profile, language=Language.objects.get(key='PY3'),
        )
        self.problem_url = reverse('problem_detail', args=(self.problem.code,))
        self.submission_url = reverse('submission_status', args=(self.submission.pk,))
        self.group_url = reverse('problem_group_list', args=(self.group.name,))
        patcher = patch('judge.views.submission.event.last', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertNavigation(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data['problem_group_navigation'],
                         {'name': self.group.full_name, 'url': self.group_url})
        self.assertContains(response, 'class="problem-group-navigation"', count=1)
        self.assertContains(response, 'href="%s"' % self.group_url)

    def make_contest(self):
        # Contest.save assigns its numeric slug with a second save; avoid force_insert.
        now = timezone.now()
        contest = Contest(name='Navigation contest', is_visible=True, start_time=now - timezone.timedelta(days=1),
                          end_time=now + timezone.timedelta(days=1))
        contest.save()
        return contest

    def test_problem_link_is_before_title_and_discards_incoming_filters(self):
        response = self.client.get(self.problem_url + '?status=unsolved&page=2&search=old')
        self.assertNavigation(response)
        html = response.content.decode()
        self.assertLess(html.index('<nav class="problem-group-navigation"'), html.index('<h2 style='))
        self.assertIn('aria-hidden="true">‹</span>', html)
        self.assertContains(response, 'aria-label="스택 문제 목록으로"')
        target = self.client.get(response.context_data['problem_group_navigation']['url'])
        self.assertEqual(target.status_code, 200)
        self.assertEqual(target.context_data['problem_status'], 'all')
        self.assertContains(target, self.problem.name)

    def test_group_changes_are_reflected_on_both_pages(self):
        self.group = create_problem_group(name='navigation-queue', full_name='큐')
        self.problem.group = self.group
        self.problem.save()
        self.group_url = reverse('problem_group_list', args=(self.group.name,))
        for path in (self.problem_url, self.submission_url):
            self.assertNavigation(self.client.get(path))
        self.group.full_name = '긴 분류명 <script> 표시 테스트'
        self.group.save()
        response = self.client.get(self.problem_url)
        self.assertNavigation(response)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script> 표시 테스트')

    def test_result_link_remains_outside_live_update_region_for_all_verdicts(self):
        for status, result in (('QU', None), ('P', None), ('G', None), ('D', 'AC'),
                               ('D', 'WA'), ('D', 'TLE'), ('D', 'MLE'), ('CE', 'CE'), ('IE', 'IE')):
            with self.subTest(status=status, result=result):
                Submission.objects.filter(pk=self.submission.pk).update(status=status, result=result)
                response = self.client.get(self.submission_url)
                self.assertNavigation(response)
                self.assertContains(response, '스택 문제 더 풀기')
                html = response.content.decode()
                self.assertLess(html.index('<nav class="problem-group-navigation"'), html.index('<div id="test-cases">'))
        fragment = self.client.get(reverse('submission_testcases_query'), {'id': self.submission.pk})
        self.assertEqual(fragment.status_code, 200)
        self.assertNotContains(fragment, 'class="problem-group-navigation"')

    def test_restricted_problem_pages_hide_link_even_for_admin(self):
        self.user.is_superuser = self.user.is_staff = True
        self.user.save()
        for field, value in (('is_public', False), ('is_encrypted', True), ('is_contest_problem', True)):
            original = getattr(self.problem, field)
            setattr(self.problem, field, value)
            self.problem.save()
            for path in (self.problem_url, self.submission_url):
                with self.subTest(field=field, path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(response, 'class="problem-group-navigation"')
            setattr(self.problem, field, original)
            self.problem.save()

    def test_contest_submission_hides_link_after_contest_participation_ends(self):
        contest = self.make_contest()
        Submission.objects.filter(pk=self.submission.pk).update(contest_object=contest)
        response = self.client.get(self.submission_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="problem-group-navigation"')

    def test_active_contest_hides_navigation_on_both_pages(self):
        participation = create_contest_participation(contest=self.make_contest(), user=self.user.profile)
        profile = self.user.profile
        profile.current_contest = participation
        profile.save()
        for path in (self.problem_url, self.submission_url):
            response = self.client.get(path)
            self.assertTrue(response.wsgi_request.in_contest)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'class="problem-group-navigation"')

    def test_promotion_problem_hides_navigation_even_for_admin(self):
        self.user.is_superuser = self.user.is_staff = True
        self.user.save()
        self.problem.promotion_exam = PromotionExam.objects.create(title='Navigation exam', source_tier=Tier.BRONZE)
        self.problem.save()
        for path in (self.problem_url, self.submission_url):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'class="problem-group-navigation"')

    def test_existing_access_checks_are_preserved(self):
        self.problem.is_public = False
        self.problem.save()
        self.assertEqual(self.client.get(self.problem_url).status_code, 404)
        self.client.logout()
        self.assertRedirects(self.client.get(self.group_url), '/accounts/login/?next=' + self.group_url,
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get(self.submission_url), '/accounts/login/?next=' + self.submission_url,
                             fetch_redirect_response=False)
