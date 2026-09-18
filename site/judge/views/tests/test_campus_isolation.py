from importlib import import_module
from io import BytesIO
from zipfile import ZipFile

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from judge.models import AlgorithmGuide, Campus, Cohort, Comment, Contest, Language, Profile, Submission, SubmissionSource, TrainingClass
from judge.models.LatestSubmission import LatestSubmission
from judge.models.tests.util import create_problem, create_contest_participation
from judge.utils.campus import can_access_profile


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class CampusIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cohort = Cohort.objects.create(number=77)
        cls.classes = {}
        for code in ('gwangju', 'pangyo', 'ulsan'):
            cls.classes[code] = TrainingClass.objects.create(
                campus=Campus.objects.get(code=code), cohort=cls.cohort, number=1,
            )
        cls.viewer = cls.make_user('campus-viewer', 'gwangju')
        cls.peer = cls.make_user('campus-peer', 'gwangju')
        # Different classes in the same campus share their campus's user directory.
        cls.peer.profile.training_class = TrainingClass.objects.create(
            campus=cls.classes['gwangju'].campus, cohort=cls.cohort, number=2,
        )
        cls.peer.profile.save(update_fields=('training_class',))
        cls.foreign = cls.make_user('campus-foreign', 'pangyo')
        cls.ulsan = cls.make_user('campus-ulsan', 'ulsan')
        cls.unassigned = cls.make_user('campus-unassigned')
        cls.admin = cls.make_user('campus-admin', is_staff=True)
        cls.problem = create_problem(code='campusproblem', is_public=True, points=10,
                                     allowed_languages=('PY3',), summary='shared', og_image='/static/test.png')
        cls.language = Language.get_python3()
        cls.submissions = {}
        for user in (cls.viewer, cls.peer, cls.foreign, cls.ulsan):
            sub = Submission.objects.create(user=user.profile, problem=cls.problem, language=cls.language,
                                            status='D', result='AC', points=10, case_points=1, case_total=1)
            SubmissionSource.objects.create(submission=sub, source='code_for_' + user.username)
            cls.submissions[user.pk] = sub
        cls.local_comment = Comment.objects.create(author=cls.peer.profile, page='p:campusproblem',
                                                    body='local_comment_marker')
        cls.foreign_comment = Comment.objects.create(author=cls.foreign.profile, page='p:campusproblem',
                                                      body='foreign_comment_marker')

    @classmethod
    def make_user(cls, name, campus=None, **kwargs):
        user = get_user_model().objects.create_user(username=name, first_name=name, **kwargs)
        if campus:
            user.profile.training_class = cls.classes[campus]
            user.profile.save(update_fields=('training_class',))
        return user

    def setUp(self):
        self.client.force_login(self.viewer)

    def test_user_directory_is_campus_wide_and_ignores_forged_scope(self):
        session = self.client.session
        session['campus_scope'] = self.classes['pangyo'].campus_id
        session.save()
        response = self.client.get(reverse('user_list'), {'campus': self.classes['pangyo'].campus_id})
        self.assertEqual(response.status_code, 200)
        ids = {profile.pk for _, profile in response.context_data['users']}
        self.assertEqual(ids, {self.viewer.profile.pk, self.peer.profile.pk})
        self.assertNotContains(response, 'id="campus-scope"')
        self.assertNotContains(response, 'campus-foreign')

    def test_ranking_is_local_and_numbered_from_one(self):
        response = self.client.get(reverse('gamification_ranking'))
        rows = response.context_data['rankings']
        self.assertEqual({row.profile_id for row in rows}, {self.viewer.profile.pk, self.peer.profile.pk})
        self.assertEqual([row.rank for row in rows[1:]], [1, 2])
        self.assertContains(response, 'class="current-user-row"', count=1)

    def test_profile_direct_urls_are_scoped(self):
        for suffix in ('', '/'):
            response = self.client.get('/user/campus-foreign' + suffix, follow=True)
            self.assertEqual(response.status_code, 404, suffix)
        self.assertEqual(self.client.get(reverse('user_page', args=[self.peer.username])).status_code, 200)
        for suffix in ('/solved', '/solved/ajax'):
            self.assertEqual(self.client.get('/user/campus-foreign' + suffix).status_code, 403)

    def test_submission_list_and_filter_options_are_scoped(self):
        response = self.client.get(reverse('chronological_submissions', args=[self.problem.code]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual({sub.user_id for sub in response.context_data['submissions']},
                         {self.viewer.profile.pk, self.peer.profile.pk})
        self.assertNotContains(response, 'campus-foreign')
        self.assertEqual(self.client.get(reverse('all_user_submissions', args=[self.foreign.username])).status_code, 404)

    def test_other_campus_submission_cannot_be_accessed_even_after_solving(self):
        sub = self.submissions[self.foreign.pk]
        for name in ('submission_status', 'submission_source', 'submission_source_raw'):
            self.assertEqual(self.client.get(reverse(name, args=[sub.pk])).status_code, 404, name)
        for name in ('submission_single_query', 'submission_testcases_query'):
            self.assertEqual(self.client.get(reverse(name), {'id': sub.pk}).status_code, 404, name)
        self.assertFalse(sub.can_see_detail(self.viewer))
        self.assertFalse(sub.can_see_source(self.viewer))
        local = self.submissions[self.peer.pk]
        self.assertContains(self.client.get(reverse('submission_source_raw', args=[local.pk])), 'code_for_campus-peer')

    def test_nonstaff_management_permission_does_not_cross_campuses(self):
        self.viewer.user_permissions.add(Permission.objects.get(codename='view_all_submission'))
        self.problem.authors.add(self.viewer.profile)
        sub = self.submissions[self.foreign.pk]
        self.assertEqual(self.client.get(reverse('submission_source_raw', args=[sub.pk])).status_code, 404)

    def test_apis_hide_foreign_users_and_submissions(self):
        for path in ('/api/user/list', '/api/user/ratings/1', '/api/v2/users', '/api/v2/submissions'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertNotContains(response, 'campus-foreign')
            self.assertNotContains(response, 'campus-ulsan')
        sub = self.submissions[self.foreign.pk]
        for path in ('/api/user/info/campus-foreign', '/api/user/submissions/campus-foreign',
                     '/api/v2/user/campus-foreign', '/api/v2/submission/%s' % sub.pk):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_search_and_redirect_do_not_reveal_foreign_user(self):
        for name in ('user_search_select2_ajax', 'profile_select2'):
            response = self.client.get(reverse(name), {'term': 'campus-'})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'campus-foreign')
            self.assertContains(response, 'campus-peer')
        response = self.client.get(reverse('martor_search_user'), {'username': 'campus-'})
        self.assertNotContains(response, 'campus-foreign')
        self.assertContains(response, 'campus-peer')
        self.assertEqual(self.client.get(reverse('user_ranking_redirect'), {'handle': self.foreign.username}).status_code, 404)

    def test_comments_are_local_including_direct_requests_and_reply(self):
        response = self.client.get(reverse('problem_detail', args=[self.problem.code]))
        self.assertContains(response, 'local_comment_marker')
        self.assertNotContains(response, 'foreign_comment_marker')
        for name in ('comment_content', 'comment_revision_ajax'):
            self.assertEqual(self.client.get(reverse(name, args=[self.foreign_comment.pk])).status_code, 404)
        count = Comment.objects.count()
        response = self.client.post(reverse('problem_detail', args=[self.problem.code]),
                                    {'parent': self.foreign_comment.pk, 'body': 'cross-campus-reply'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.count(), count)
        response = self.client.post(reverse('comment_upvote'), {'id': self.foreign_comment.pk})
        self.assertEqual(response.status_code, 404)

    def test_unassigned_account_sees_only_self(self):
        self.client.force_login(self.unassigned)
        response = self.client.get(reverse('user_list'))
        self.assertEqual({profile.pk for _, profile in response.context_data['users']}, {self.unassigned.profile.pk})
        self.assertFalse(can_access_profile(self.unassigned, self.viewer.profile))
        self.assertEqual(self.client.get('/api/v2/submissions').json()['data']['objects'], [])

    def test_anonymous_user_cannot_bypass_scope(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/user/list').json(), {})
        self.assertEqual(self.client.get('/api/v2/users').json()['data']['objects'], [])
        self.assertEqual(self.client.get(reverse('user_page', args=[self.viewer.username])).status_code, 404)
        self.assertEqual(self.client.get(reverse('user_search_select2_ajax')).json()['results'], [])

    def test_admin_selector_filters_lists_and_persists(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('user_list')), 'id="campus-scope"')
        for code in ('pangyo', 'ulsan', 'gwangju'):
            response = self.client.post(reverse('campus_select'),
                                        {'campus': self.classes[code].campus_id, 'next': '/ranking/'})
            self.assertRedirects(response, '/ranking/', fetch_redirect_response=False)
            rows = self.client.get(reverse('gamification_ranking')).context_data['rankings']
            self.assertTrue(rows)
            self.assertTrue(all(row.profile.training_class.campus_id == self.classes[code].campus_id for row in rows))
            rows = self.client.get(reverse('user_list')).context_data['users']
            self.assertTrue(all(user.training_class.campus_id == self.classes[code].campus_id for _, user in rows))
            data = self.client.get('/api/v2/submissions').json()['data']['objects']
            self.assertTrue(data)
            usernames = {user.user.username for user in Profile.objects.filter(training_class__campus_id=self.classes[code].campus_id)}
            self.assertTrue(all(row['user'] in usernames for row in data))
        self.client.post(reverse('campus_select'), {'campus': ''})
        ids = {row.profile_id for row in self.client.get(reverse('gamification_ranking')).context_data['rankings']}
        self.assertIn(self.foreign.profile.pk, ids)
        self.assertIn(self.ulsan.profile.pk, ids)
        self.assertNotIn('campus_scope', self.client.session)

    def test_admin_can_still_open_any_profile_and_private_code(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('campus_select'), {'campus': self.classes['ulsan'].campus_id})
        sub = self.submissions[self.foreign.pk]
        sub.is_source_public = False
        sub.save(update_fields=('is_source_public',))
        self.assertEqual(self.client.get(reverse('user_page', args=[self.foreign.username])).status_code, 200)
        self.assertContains(self.client.get(reverse('submission_source_raw', args=[sub.pk])), 'code_for_campus-foreign')

    def test_selector_rejects_student_invalid_campus_and_external_redirect(self):
        self.assertEqual(self.client.post(reverse('campus_select'), {'campus': self.classes['pangyo'].campus_id}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('campus_select'), {'campus': '999999'}).status_code, 400)
        response = self.client.post(reverse('campus_select'), {'campus': '', 'next': 'https://example.com/'})
        self.assertRedirects(response, reverse('user_list'), fetch_redirect_response=False)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse('campus_select'), {'campus': ''}).status_code, 403)

    def test_shared_problem_is_available_to_each_campus(self):
        for user in (self.viewer, self.foreign, self.ulsan):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('problem_detail', args=[self.problem.code])).status_code, 200)

    def test_class_seed_is_idempotent_and_preserves_existing_inactive_class(self):
        migration = import_module('judge.migrations.0054_enable_campus_classes')
        self.classes['pangyo'].is_active = False
        self.classes['pangyo'].save(update_fields=('is_active',))
        migration.create_campus_classes(apps, None)
        migration.create_campus_classes(apps, None)
        self.assertEqual(TrainingClass.objects.filter(cohort=self.cohort, campus__code='pangyo').count(), 6)
        self.assertEqual(TrainingClass.objects.filter(cohort=self.cohort, campus__code='ulsan').count(), 4)
        self.classes['pangyo'].refresh_from_db()
        self.assertFalse(self.classes['pangyo'].is_active)

    def test_contest_rankings_and_apis_are_scoped(self):
        contest = Contest(name='Campus contest', is_visible=True,
                          start_time=timezone.now() - timezone.timedelta(days=2),
                          end_time=timezone.now() - timezone.timedelta(days=1))
        contest.save()
        for user in (self.viewer, self.foreign):
            create_contest_participation(contest=contest, user=user.profile)
        for path in (reverse('contest_ranking', args=[contest.key]),
                     reverse('contest_ranking_ajax', args=[contest.key]),
                     '/api/contest/info/' + contest.key, '/api/v2/contest/' + contest.key,
                     '/api/v2/participations'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, 'campus-viewer')
            self.assertNotContains(response, 'campus-foreign')
        self.client.force_login(self.admin)
        self.client.post(reverse('campus_select'), {'campus': self.classes['pangyo'].campus_id})
        response = self.client.get('/api/v2/contest/' + contest.key)
        self.assertContains(response, 'campus-foreign')
        self.assertNotContains(response, 'campus-viewer')

    def test_home_recent_comments_follow_campus_selection(self):
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'campus-foreign')
        self.client.force_login(self.admin)
        self.client.post(reverse('campus_select'), {'campus': self.classes['pangyo'].campus_id})
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'campus-peer')

    def test_superuser_without_staff_flag_has_global_campus_access(self):
        self.viewer.is_superuser = True
        self.viewer.save(update_fields=('is_superuser',))
        self.assertContains(self.client.get(reverse('user_list')), 'id="campus-scope"')
        self.assertEqual(self.client.get(reverse('user_page', args=[self.foreign.username])).status_code, 200)

    def test_submission_statistics_do_not_include_other_campuses(self):
        response = self.client.get(reverse('stats_data_status'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(response.json()['datasets'][0]['data']), 2)
        self.client.force_login(self.admin)
        self.assertEqual(sum(self.client.get(reverse('stats_data_status')).json()['datasets'][0]['data']), 4)
        self.client.post(reverse('campus_select'), {'campus': self.classes['pangyo'].campus_id})
        self.assertEqual(sum(self.client.get(reverse('stats_data_status')).json()['datasets'][0]['data']), 1)

    def test_shared_guide_is_available_to_each_campus(self):
        guide = AlgorithmGuide.objects.create(problem_group=self.problem.group, title='Shared guide',
                                              summary='Shared', content='shared_guide_marker', is_published=True)
        for user in (self.viewer, self.foreign, self.ulsan):
            self.client.force_login(user)
            self.assertContains(self.client.get(guide.get_absolute_url()), 'shared_guide_marker')

    def test_contest_source_download_does_not_cross_campuses(self):
        contest = Contest(name='Campus download', is_visible=True,
                          start_time=timezone.now() - timezone.timedelta(days=2),
                          end_time=timezone.now() - timezone.timedelta(days=1))
        contest.save()
        contest.authors.add(self.viewer.profile)
        self.viewer.user_permissions.add(Permission.objects.get(codename='edit_own_contest'))
        for user in (self.viewer, self.foreign):
            LatestSubmission.objects.create(user=user, problem=self.problem, contest_object=contest,
                                             language=self.language, source='code_for_' + user.username)
        url = reverse('contest_detail_code_download', args=[contest.key])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(len(archive.namelist()), 1)
            self.assertEqual(archive.read(archive.namelist()[0]).decode(), 'code_for_' + self.viewer.username)
        self.client.force_login(self.admin)
        self.client.post(reverse('campus_select'), {'campus': self.classes['pangyo'].campus_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(len(archive.namelist()), 1)
            self.assertEqual(archive.read(archive.namelist()[0]).decode(), 'code_for_' + self.foreign.username)

    def test_problem_editor_cannot_compare_other_campus_submissions(self):
        self.viewer.user_permissions.add(Permission.objects.get(codename='edit_own_problem'))
        self.problem.authors.add(self.viewer.profile)
        url = reverse('problem_submission_diff', args=[self.problem.code])
        self.assertEqual(self.client.get(url, {'id': self.submissions[self.foreign.pk].pk}).status_code, 404)

    def test_language_statistics_follow_campus(self):
        for route in ('language_stats_data_all', 'language_stats_data_ac'):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(sum(response.json()['datasets'][0]['data']), 2)
        self.assertEqual(self.client.get(reverse('language_stats_data_ac_rate')).status_code, 200)
