import warnings

from django.contrib.auth import get_user_model
from django.core.paginator import UnorderedObjectListWarning
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import Language, Submission
from judge.models.tests.util import create_problem, create_problem_group


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ProblemListAuthenticationTestCase(TestCase):
    def test_problem_list_redirects_anonymous_user_to_login(self):
        response = self.client.get('/problems/')

        self.assertRedirects(response, '/accounts/login/?next=/problems/', fetch_redirect_response=False)

    def test_problem_list_renders_for_authenticated_user(self):
        user = User.objects.create_user(username='problem-list-user', password='test-password')
        self.client.force_login(user)

        with warnings.catch_warnings():
            warnings.simplefilter('error', UnorderedObjectListWarning)
            response = self.client.get('/problems/')

        self.assertEqual(response.status_code, 200)

    def test_problem_group_list_redirects_anonymous_user_to_login(self):
        response = self.client.get('/problems/basic/')

        self.assertRedirects(response, '/accounts/login/?next=/problems/basic/', fetch_redirect_response=False)


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ProblemGroupNavigationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='problem-group-user', password='test-password')
        self.client.force_login(self.user)
        self.basic_group = create_problem_group(name='basic', full_name='기초')
        self.practice_group = create_problem_group(name='practice', full_name='연습')
        self.basic_problem = create_problem(
            code='basic-navigation',
            name='기초 탐색',
            group=self.basic_group,
            is_public=True,
        )
        self.practice_problem = create_problem(
            code='practice-navigation',
            name='실전 탐색',
            group=self.practice_group,
            is_public=True,
        )
        self.language = Language.objects.get(key='PY3')

    def test_problem_root_shows_all_problems_and_group_navigation(self):
        response = self.client.get(reverse('problem_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_problem.name)
        self.assertContains(response, self.practice_problem.name)
        self.assertContains(response, 'class="problem-group-card"', html=False)
        self.assertContains(response, 'class="problem-group-all active"', html=False)
        self.assertContains(response, '기초')
        self.assertContains(response, '연습')
        self.assertContains(response, reverse('problem_group_list', args=('basic',)))
        self.assertContains(response, reverse('problem_group_list', args=('practice',)))
        self.assertLess(response.content.index('전체 문제'.encode()), response.content.index('내가 푼 문제'.encode()))
        self.assertLess(response.content.index('내가 푼 문제'.encode()), response.content.index('내가 안 푼 문제'.encode()))
        self.assertLess(response.content.index('내가 안 푼 문제'.encode()), response.content.index('기초'.encode()))

    def test_basic_group_is_listed_before_alphabetically_earlier_groups(self):
        bfs_group = create_problem_group(name='bfs', full_name='BFS')
        create_problem(code='bfs-navigation', name='BFS 탐색', group=bfs_group, is_public=True)

        response = self.client.get(reverse('problem_list'))

        self.assertEqual(response.status_code, 200)
        group_slugs = [group['slug'] for group in response.context_data['problem_groups']]
        self.assertEqual(['basic', 'bfs', 'practice'], group_slugs)

    def test_problem_list_default_sort_is_stable_across_pages(self):
        created_codes = [self.basic_problem.code, self.practice_problem.code]
        for index in reversed(range(21)):
            code = 'page-%02d' % index
            create_problem(
                code=code,
                name='페이지 문제 %02d' % index,
                group=self.basic_group,
                is_public=True,
            )
            created_codes.append(code)

        first_response = self.client.get(reverse('problem_list'))
        second_response = self.client.get(reverse('problem_list'), {'page': 2})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        actual_codes = [problem.code for problem in first_response.context_data['problems']]
        actual_codes += [problem.code for problem in second_response.context_data['problems']]
        self.assertEqual(actual_codes, sorted(created_codes))

    def test_group_page_uses_admin_order_before_unordered_problems(self):
        ordered_last = create_problem(
            code='a-group-order', name='관리 순서 2', group=self.basic_group,
            is_public=True, group_order=2,
        )
        ordered_first = create_problem(
            code='z-group-order', name='관리 순서 1', group=self.basic_group,
            is_public=True, group_order=1,
        )

        response = self.client.get(reverse('problem_group_list', args=('basic',)))

        self.assertEqual(response.status_code, 200)
        codes = [problem.code for problem in response.context_data['problems']]
        self.assertEqual(codes[:2], [ordered_first.code, ordered_last.code])
        self.assertEqual(codes[2:], [self.basic_problem.code])

    def test_group_page_explicit_header_sort_overrides_admin_order(self):
        create_problem(
            code='z-explicit-sort', name='뒤 ID', group=self.basic_group,
            is_public=True, group_order=1,
        )
        create_problem(
            code='a-explicit-sort', name='앞 ID', group=self.basic_group,
            is_public=True, group_order=2,
        )

        response = self.client.get(
            reverse('problem_group_list', args=('basic',)),
            {'order': 'code'},
        )

        codes = [problem.code for problem in response.context_data['problems']]
        self.assertEqual(codes, sorted(codes))

    def test_group_order_is_stable_across_pages(self):
        expected_codes = []
        for order in range(1, 23):
            code = 'ordered-page-%02d' % order
            create_problem(
                code=code,
                name='순서 문제 %02d' % order,
                group=self.basic_group,
                is_public=True,
                group_order=order,
            )
            expected_codes.append(code)

        first_response = self.client.get(reverse('problem_group_list', args=('basic',)))
        second_response = self.client.get(
            reverse('problem_group_list', args=('basic',)),
            {'page': 2},
        )

        actual_codes = [problem.code for problem in first_response.context_data['problems']]
        actual_codes += [problem.code for problem in second_response.context_data['problems']]
        self.assertEqual(actual_codes[:22], expected_codes)
        self.assertEqual(actual_codes[22:], [self.basic_problem.code])

    def test_group_slug_is_used_in_url_and_korean_name_is_displayed(self):
        stack_group = create_problem_group(name='stack', full_name='스택')
        stack_problem = create_problem(
            code='stack-navigation', name='스택 탐색', group=stack_group, is_public=True,
        )

        catalog_response = self.client.get(reverse('problem_list'))
        self.assertEqual(catalog_response.status_code, 200)
        self.assertContains(catalog_response, '스택')
        self.assertContains(catalog_response, reverse('problem_group_list', args=('stack',)))

        group_response = self.client.get(reverse('problem_group_list', args=('stack',)))
        self.assertEqual(group_response.status_code, 200)
        self.assertContains(group_response, stack_problem.name)

    def test_group_page_only_shows_problems_in_selected_group(self):
        response = self.client.get(reverse('problem_group_list', args=('basic',)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_problem.name)
        self.assertNotContains(response, self.practice_problem.name)
        self.assertContains(response, '전체 문제')
        self.assertNotContains(response, 'id="problem-group"')

    def test_legacy_group_id_does_not_override_path_group(self):
        response = self.client.get(
            reverse('problem_group_list', args=('basic',)),
            {'groupId': 'bfs'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_problem.name)
        self.assertNotContains(response, self.practice_problem.name)

    def test_legacy_category_query_redirects_to_group_url(self):
        response = self.client.get(reverse('problem_list'), {
            'category': self.basic_problem.group_id,
            'search': '탐색',
        })

        self.assertRedirects(
            response,
            reverse('problem_group_list', args=('basic',)) + '?search=%ED%83%90%EC%83%89',
            fetch_redirect_response=False,
        )

    def test_unknown_problem_group_returns_not_found(self):
        response = self.client.get('/problems/not-a-group/')

        self.assertEqual(response.status_code, 404)

    def test_solved_filter_only_shows_fully_accepted_problems(self):
        Submission.objects.create(
            user=self.user.profile,
            problem=self.basic_problem,
            language=self.language,
            status='D',
            result='AC',
            points=self.basic_problem.points,
        )

        response = self.client.get(reverse('problem_list'), {'status': 'solved'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_problem.name)
        self.assertNotContains(response, self.practice_problem.name)
        self.assertEqual(response.context_data['problem_status'], 'solved')

    def test_unsolved_filter_excludes_fully_accepted_problems(self):
        Submission.objects.create(
            user=self.user.profile,
            problem=self.basic_problem,
            language=self.language,
            status='D',
            result='AC',
            points=self.basic_problem.points,
        )

        response = self.client.get(reverse('problem_list'), {'status': 'unsolved'})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.basic_problem.name)
        self.assertContains(response, self.practice_problem.name)
        self.assertEqual(response.context_data['problem_status'], 'unsolved')

    def test_partial_or_failed_submission_remains_unsolved(self):
        Submission.objects.create(
            user=self.user.profile,
            problem=self.basic_problem,
            language=self.language,
            status='D',
            result='AC',
            points=self.basic_problem.points / 2,
        )

        response = self.client.get(reverse('problem_list'), {'status': 'unsolved'})

        self.assertContains(response, self.basic_problem.name)

    def test_status_filter_is_preserved_in_search_and_group_links(self):
        response = self.client.get(reverse('problem_list'), {
            'status': 'unsolved',
            'search': '탐색',
        })

        self.assertContains(response, 'name="status" value="unsolved"', html=False)
        self.assertContains(
            response,
            reverse('problem_group_list', args=('basic',)) + '?status=unsolved&amp;search=',
            html=False,
        )
