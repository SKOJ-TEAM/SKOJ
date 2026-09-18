from importlib import import_module
from urllib.parse import parse_qs, urlsplit

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import Campus, Cohort, Language, Submission, SubmissionSource, TrainingClass
from judge.models.tests.util import create_problem


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class CampusFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cohort = Cohort.objects.create(number=77)
        cls.members = {}
        cls.classes = {}
        for code in ('gwangju', 'pangyo', 'ulsan'):
            cls.classes[code] = TrainingClass.objects.create(
                cohort=cls.cohort, campus=Campus.objects.get(code=code), number=1,
            )
            user = get_user_model().objects.create_user(username='filter-' + code, first_name='교육생 ' + code)
            user.profile.training_class = cls.classes[code]
            user.profile.save(update_fields=('training_class',))
            cls.members[code] = user
        cls.viewer = cls.members['gwangju']
        cls.foreign = cls.members['pangyo']
        cls.unassigned = get_user_model().objects.create_user(username='filter-unassigned')
        cls.admin = get_user_model().objects.create_user(username='filter-admin', is_staff=True)
        cls.problem = create_problem(code='filterproblem', is_public=True, points=10,
                                     allowed_languages=('PY3',), summary='Shared', og_image='/static/test.png')
        cls.submissions = {}
        for user in cls.members.values():
            sub = Submission.objects.create(user=user.profile, problem=cls.problem, language=Language.get_python3(),
                                            status='D', result='AC', points=10, case_points=1, case_total=1)
            SubmissionSource.objects.create(submission=sub, source='code_for_' + user.username)
            cls.submissions[user.pk] = sub

    def setUp(self):
        self.client.force_login(self.viewer)

    def test_directory_and_ranking_default_to_all_campuses(self):
        response = self.client.get(reverse('user_list'))
        self.assertEqual({p.pk for _, p in response.context_data['users']},
                         {u.profile.pk for u in [*self.members.values(), self.unassigned, self.admin]})
        response = self.client.get(reverse('gamification_ranking'))
        self.assertEqual({row.profile_id for row in response.context_data['rankings']},
                         {u.profile.pk for u in [*self.members.values(), self.unassigned]})

    def test_everyone_can_filter_each_campus(self):
        for viewer in (self.viewer, self.admin, self.unassigned):
            self.client.force_login(viewer)
            for code, member in self.members.items():
                response = self.client.get(reverse('user_list'), {'campus': code})
                self.assertEqual({p.pk for _, p in response.context_data['users']}, {member.profile.pk})
                response = self.client.get(reverse('gamification_ranking'), {'campus': code})
                self.assertEqual({row.profile_id for row in response.context_data['rankings']}, {member.profile.pk})
                self.assertContains(response, 'aria-label="캠퍼스 필터"')
                self.assertContains(response, 'aria-current="page"', count=1)

    def test_unknown_campus_is_not_silently_ignored(self):
        for name in ('user_list', 'gamification_ranking'):
            self.assertEqual(self.client.get(reverse(name), {'campus': 'missing'}).status_code, 404)

    def test_old_admin_scope_session_does_not_restrict_any_page(self):
        for viewer in (self.viewer, self.admin):
            self.client.force_login(viewer)
            session = self.client.session
            session['campus_scope'] = self.classes['ulsan'].campus_id
            session.save()
            for name in ('user_list', 'gamification_ranking'):
                response = self.client.get(reverse(name))
                self.assertContains(response, self.foreign.username)
                self.assertNotContains(response, 'id="campus-scope"')
            self.assertContains(self.client.get('/api/v2/submissions'), self.foreign.username)

    def test_filter_is_local_to_page_and_url(self):
        self.client.get(reverse('user_list'), {'campus': 'ulsan'})
        self.assertContains(self.client.get(reverse('gamification_ranking')), self.foreign.username)
        self.assertContains(self.client.get(reverse('user_list')), self.foreign.username)
        self.assertEqual(self.client.get(reverse('user_page', args=[self.foreign.username])).status_code, 200)

    def test_search_and_filter_links_keep_query_but_reset_page(self):
        response = self.client.get(reverse('user_list'), {'campus': 'pangyo', 'search': '교육생', 'order': '-points'})
        self.assertEqual({p.pk for _, p in response.context_data['users']}, {self.foreign.profile.pk})
        for item in response.context_data['campus_filters']:
            query = parse_qs(urlsplit(item['url']).query)
            self.assertEqual(query['search'], ['교육생'])
            self.assertEqual(query['order'], ['-points'])
            self.assertNotIn('page', query)
        self.assertContains(response, 'name="campus" value="pangyo"')
        self.assertContains(response, 'name="search" value="교육생"')

    def test_pagination_keeps_campus_and_switch_resets_to_first_page(self):
        for index in range(23):
            user = get_user_model().objects.create_user(username='filter-extra-%02d' % index, first_name='교육생')
            user.profile.training_class = self.classes['pangyo']
            user.profile.save(update_fields=('training_class',))
        response = self.client.get(reverse('user_list'), {'campus': 'pangyo', 'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data['page_obj'].paginator.count, 24)
        self.assertEqual(len(response.context_data['users']), 4)
        self.assertEqual(response.context_data['first_page_href'], '/users/?campus=pangyo')
        self.assertEqual(response.context_data['page_prefix'], '/users/?campus=pangyo&page=')
        self.assertContains(response, 'campus=pangyo')
        self.assertTrue(all('page=' not in option['url'] for option in response.context_data['campus_filters']))

    def test_own_summary_is_only_highlight_and_original_row_remains(self):
        for name in ('user_list', 'gamification_ranking'):
            response = self.client.get(reverse(name), {'campus': 'gwangju'})
            self.assertContains(response, 'class="current-user-row"', count=1)
            rows = response.context_data['users' if name == 'user_list' else 'rankings']
            self.assertEqual(len(rows), 2)
            response = self.client.get(reverse(name), {'campus': 'pangyo'})
            self.assertNotContains(response, 'class="current-user-row"')

    def test_public_cross_campus_code_obeys_existing_sharing_permissions(self):
        sub = self.submissions[self.foreign.pk]
        for name in ('submission_status', 'submission_source', 'submission_source_raw'):
            self.assertEqual(self.client.get(reverse(name, args=[sub.pk])).status_code, 200)
        for name in ('submission_single_query', 'submission_testcases_query'):
            self.assertEqual(self.client.get(reverse(name), {'id': sub.pk}).status_code, 200)
        self.assertTrue(sub.can_see_source(self.viewer))
        self.client.force_login(self.unassigned)
        self.assertEqual(self.client.get(reverse('submission_source_raw', args=[sub.pk])).status_code, 403)
        sub.is_source_public = False
        sub.save(update_fields=('is_source_public',))
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('submission_source_raw', args=[sub.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('submission_source_raw', args=[sub.pk])).status_code, 200)

    def test_staff_code_stays_hidden_across_campuses(self):
        sub = self.submissions[self.foreign.pk]
        self.foreign.is_staff = True
        self.foreign.save(update_fields=('is_staff',))
        self.assertEqual(self.client.get(reverse('submission_source_raw', args=[sub.pk])).status_code, 403)

    def test_submission_list_ignores_campus_query(self):
        response = self.client.get(reverse('chronological_submissions', args=[self.problem.code]), {'campus': 'ulsan'})
        self.assertEqual({sub.user_id for sub in response.context_data['submissions']},
                         {u.profile.pk for u in self.members.values()})

    def test_profiles_search_and_api_can_cross_campuses(self):
        self.assertEqual(self.client.get(reverse('user_page', args=[self.foreign.username])).status_code, 200)
        sub = self.submissions[self.foreign.pk]
        for path in ('/api/user/list', '/api/v2/users', '/api/v2/submissions',
                     '/api/user/info/' + self.foreign.username, '/api/v2/user/' + self.foreign.username,
                     '/api/v2/submission/%s' % sub.pk):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            if not path.startswith('/api/user/info/'):
                self.assertContains(response, self.foreign.username, msg_prefix=path)
        response = self.client.get(reverse('user_search_select2_ajax'), {'term': 'filter-'})
        self.assertContains(response, self.foreign.username)

    def test_filter_does_not_show_outside_directory_and_ranking(self):
        for user in (self.viewer, self.admin):
            self.client.force_login(user)
            response = self.client.get(reverse('problem_detail', args=[self.problem.code]))
            self.assertNotContains(response, 'aria-label="캠퍼스 필터"')
            self.assertNotContains(response, 'id="campus-scope"')

    def test_registration_class_seed_is_still_idempotent(self):
        migration = import_module('judge.migrations.0054_enable_campus_classes')
        migration.create_campus_classes(apps, None)
        migration.create_campus_classes(apps, None)
        for code, number in (('pangyo', 6), ('ulsan', 4)):
            self.assertEqual(TrainingClass.objects.filter(cohort=self.cohort, campus__code=code).count(), number)
