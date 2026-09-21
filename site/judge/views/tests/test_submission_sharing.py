from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from judge.admin.submission import SubmissionAdmin
from judge.forms import ProblemSubmitForm
from judge.models import (ChallengeAttempt, ChallengeAttemptProblem, ChallengeExam, Contest, Judge, Language,
                          Submission, SubmissionSource, SubmissionTestCase, Tier)
from judge.models.tests.util import create_contest_participation, create_problem, create_user
from judge.utils.submission_access import SubmissionAccess
from judge.views.submission import submission_related


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class SubmissionSharingTest(TestCase):
    def setUp(self):
        self.owner = create_user('sharing-owner')
        self.viewer = create_user('sharing-viewer')
        self.staff = create_user('sharing-staff', is_staff=True)
        self.problem = create_problem(code='sharing', is_public=True, points=10,
                                      allowed_languages=('PY3',), summary='sharing', og_image='/static/test.png')
        self.language = Language.get_python3()
        self.submission = self.make_submission(self.owner, result='WA')
        SubmissionSource.objects.create(submission=self.submission, source='private_source_marker = 123')
        patcher = patch('judge.views.submission.event.last', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.viewer)

    def make_submission(self, user, **kwargs):
        values = dict(user=user.profile, problem=self.problem, language=self.language, result='AC',
                      status='D', points=10, case_points=10, case_total=10)
        values.update(kwargs)
        return Submission.objects.create(**values)

    def make_contest(self):
        now = timezone.now()
        contest = Contest(name='Sharing contest', is_visible=True,
                          start_time=now - timezone.timedelta(days=1), end_time=now + timezone.timedelta(days=1))
        contest.save()
        return contest

    def source_url(self, raw=False):
        return reverse('submission_source_raw' if raw else 'submission_source', args=(self.submission.pk,))

    def test_unsolved_partial_and_pending_do_not_unlock_source(self):
        for values in ({'result': 'WA'}, {'points': 9}, {'status': 'G'}):
            solved = self.make_submission(self.viewer, **values)
            for raw in (False, True):
                self.assertEqual(self.client.get(self.source_url(raw)).status_code, 403)
            solved.delete()
        self.client.logout()
        self.assertEqual(self.client.get(self.source_url()).status_code, 302)
        self.assertFalse(self.submission.can_see_source(AnonymousUser()))

    def test_full_solve_unlocks_all_verdicts_and_rejudge_revokes(self):
        solved = self.make_submission(self.viewer)
        for result in ('AC', 'WA', 'TLE', 'CE'):
            Submission.objects.filter(pk=self.submission.pk).update(result=result)
            self.assertContains(self.client.get(self.source_url(True)), 'private_source_marker')
        solved.result = 'WA'
        solved.save(update_fields=['result'])
        self.assertEqual(self.client.get(self.source_url(True)).status_code, 403)

    def test_private_code_hides_source_and_diagnostics_but_keeps_results(self):
        self.make_submission(self.viewer)
        self.submission.is_source_public = False
        self.submission.error = 'private_compile_marker'
        self.submission.save()
        SubmissionTestCase.objects.create(
            submission=self.submission, case=1, status='WA', points=0, total=10,
            output='private_output_marker', feedback='private_feedback_marker',
            extended_feedback='private_extended_marker',
        )
        paths = [reverse('submission_status', args=(self.submission.pk,)),
                 reverse('submission_testcases_query') + '?id=' + str(self.submission.pk),
                 '/api/v2/submission/' + str(self.submission.pk)]
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            for secret in ('private_source_marker', 'private_compile_marker', 'private_output_marker',
                           'private_feedback_marker', 'private_extended_marker'):
                self.assertNotContains(response, secret)
            self.assertNotContains(response, self.source_url())
        for raw in (False, True):
            self.assertEqual(self.client.get(self.source_url(raw)).status_code, 403)
        response = self.client.get(reverse('chronological_submissions', args=(self.problem.code,)))
        self.assertContains(response, self.owner.username)
        self.assertContains(response, 'WA')
        self.assertEqual(self.client.get(reverse('submission_single_query'),
                                         {'id': self.submission.pk}).status_code, 200)

    def test_sharing_does_not_grant_resubmit_or_unsolved_api_access(self):
        api_url = '/api/v2/submission/' + str(self.submission.pk)
        self.assertEqual(self.client.get(api_url).status_code, 403)
        self.make_submission(self.viewer)
        resubmit_url = reverse('problem_submit', args=(self.problem.code, self.submission.pk))
        self.assertEqual(self.client.get(resubmit_url).status_code, 403)
        response = self.client.get(self.source_url(True))
        self.assertIn('no-store', response['Cache-Control'])

    def test_owner_and_staff_can_read_private_code_without_solving(self):
        self.submission.is_source_public = False
        self.submission.save()
        for user in (self.owner, self.staff):
            self.client.force_login(user)
            for raw in (False, True):
                self.assertContains(self.client.get(self.source_url(raw)), 'private_source_marker')

    def test_staff_authored_public_code_is_hidden_even_after_promotion(self):
        self.make_submission(self.viewer)
        self.owner.is_staff = True
        self.owner.save()
        self.assertEqual(self.client.get(self.source_url(True)).status_code, 403)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(self.source_url(True)), 'private_source_marker')

    def test_existing_problem_editor_and_view_all_keep_private_access(self):
        self.submission.is_source_public = False
        self.submission.save()
        editor = create_user('sharing-editor', user_permissions=('edit_own_problem',))
        self.problem.authors.add(editor.profile)
        manager = create_user('sharing-manager', user_permissions=('view_all_submission',))
        for user in (editor, manager):
            self.assertTrue(self.submission.can_see_source(user))

    def test_old_problem_modes_do_not_override_solved_only_sharing(self):
        for mode in ('O', 'A', 'F', 'S'):
            self.problem.submission_source_visibility_mode = mode
            self.problem.save()
            self.assertFalse(self.submission.can_see_source(self.viewer))
            solved = self.make_submission(self.viewer)
            self.assertTrue(self.submission.can_see_source(self.viewer))
            solved.delete()

    def test_hidden_problem_revokes_peer_access(self):
        self.make_submission(self.viewer)
        self.problem.is_public = False
        self.problem.save()
        self.assertFalse(self.submission.can_see_source(self.viewer))
        self.assertEqual(self.client.get(self.source_url(True)).status_code, 403)

    def test_challenge_requires_assignment_and_solve(self):
        exam = ChallengeExam.objects.create(title='Sharing challenge', source_tier=Tier.BRONZE)
        self.problem.challenge_exam = exam
        self.problem.is_public = False
        self.problem.save()
        self.make_submission(self.viewer)
        self.assertEqual(self.client.get(self.source_url(True)).status_code, 403)
        attempt = ChallengeAttempt.objects.create(profile=self.viewer.profile, exam=exam,
                                                   source_tier=Tier.BRONZE, target_tier=Tier.SILVER)
        ChallengeAttemptProblem.objects.create(attempt=attempt, problem=self.problem)
        self.assertContains(self.client.get(self.source_url(True)), 'private_source_marker')
        self.assertEqual(self.client.get(reverse('chronological_submissions', args=(self.problem.code,))).status_code,
                         200)

    def test_contest_policy_is_not_replaced_by_ordinary_sharing(self):
        self.make_submission(self.viewer)
        contest = self.make_contest()
        self.submission.contest_object = contest
        self.submission.save()
        self.problem.submission_source_visibility_mode = 'O'
        self.problem.save()
        self.assertFalse(self.submission.can_see_source(self.viewer))
        self.problem.submission_source_visibility_mode = 'S'
        self.problem.save()
        self.problem.__dict__.pop('submission_source_visibility', None)
        self.assertTrue(self.submission.can_see_source(self.viewer))
        self.submission.is_source_public = False
        self.submission.save()
        self.assertFalse(self.submission.can_see_source(self.viewer))
        contest.curators.add(self.viewer.profile)
        contest.__dict__.pop('editor_ids', None)
        contest.__dict__.pop('curator_ids', None)
        self.assertTrue(self.submission.can_see_source(self.viewer))

    def test_active_contest_does_not_unlock_ordinary_peer_sharing(self):
        self.make_submission(self.viewer)
        participation = create_contest_participation(contest=self.make_contest(),
                                                     user=self.viewer.profile)
        self.viewer.profile.current_contest = participation
        self.viewer.profile.save()
        self.assertFalse(self.submission.can_see_source(self.viewer))

    def test_problem_link_and_list_follow_eligibility(self):
        url = reverse('chronological_submissions', args=(self.problem.code,))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertFalse(self.client.get(reverse('problem_detail', args=(self.problem.code,))).context['can_list_submissions'])
        self.make_submission(self.viewer)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse('problem_detail', args=(self.problem.code,))), url)
        response = self.client.get(url)
        self.assertContains(response, self.owner.username)
        self.assertFalse(response.context['dynamic_update'])
        self.assertEqual(self.client.get(url, {'user': self.owner.pk}).status_code, 200)

    def test_plain_staff_can_read_but_not_edit(self):
        access = SubmissionAccess(self.staff)
        self.assertTrue(access.can_see_source(self.submission))
        self.assertFalse(access.can_edit(self.problem))
        self.client.force_login(self.staff)
        response = self.client.get(reverse('chronological_submissions', args=(self.problem.code,)))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['dynamic_update'])

    def test_list_access_queries_do_not_grow_per_row(self):
        self.make_submission(self.viewer)
        for _ in range(8):
            self.make_submission(self.owner)
        submissions = list(submission_related(Submission.objects.filter(problem=self.problem)))
        access = SubmissionAccess(self.viewer)
        access.can_see_source(submissions[0])
        access.can_edit(self.problem)
        with self.assertNumQueries(0):
            for submission in submissions:
                self.assertTrue(access.can_see_source(submission))
                self.assertFalse(access.can_edit(submission.problem))

    def test_form_public_default_and_private_save(self):
        self.assertTrue(ProblemSubmitForm(instance=Submission(user=self.owner.profile)).initial['is_source_public'])
        for checked in (False, True):
            data = {'language': self.language.pk, 'source': 'print(123)'}
            if checked:
                data['is_source_public'] = 'on'
            form = ProblemSubmitForm(data, instance=Submission(user=self.owner.profile, problem=self.problem))
            form.fields['language'].queryset = Language.objects.filter(pk=self.language.pk)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save().is_source_public, checked)

    def test_staff_form_ignores_forged_public_value(self):
        form = ProblemSubmitForm({'language': self.language.pk, 'source': 'print(123)', 'is_source_public': 'on'},
                                 instance=Submission(user=self.staff.profile, problem=self.problem))
        form.fields['language'].queryset = Language.objects.filter(pk=self.language.pk)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save().is_source_public)

    def test_submit_endpoint_saves_toggle_and_resubmit_inherits_it(self):
        judge = Judge.objects.create(name='sharing-judge', online=True)
        judge.runtimes.add(self.language)
        judge.problems.add(self.problem)
        self.client.force_login(self.owner)
        url = reverse('problem_submit', args=(self.problem.code,))
        self.assertContains(self.client.get(url), 'role="switch"')
        with patch('judge.models.submission.Submission.judge'):
            for checked in (False, True):
                data = {'language': self.language.pk, 'source': 'print(123)'}
                if checked:
                    data['is_source_public'] = 'on'
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 302, getattr(response, 'context_data', None))
                submission = Submission.objects.latest('id')
                self.assertEqual(submission.is_source_public, checked)
                response = self.client.get(reverse('problem_submit', args=(self.problem.code, submission.pk)))
                self.assertEqual(response.context['form']['is_source_public'].value(), checked)
                submission.status = 'D'
                submission.save(update_fields=['status'])
        response = self.client.post(url, {'language': self.language.pk, 'source': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form']['is_source_public'].value())

    def admin_request(self, user):
        request = RequestFactory().get('/')
        request.user, request.profile = user, user.profile
        return request

    def test_admin_permissions_and_staff_author_protection(self):
        model_admin = SubmissionAdmin(Submission, admin.site)
        plain = self.admin_request(self.staff)
        self.assertFalse(model_admin.has_change_permission(plain, self.submission))
        manager = create_user('sharing-admin', is_staff=True, user_permissions=('edit_own_problem', 'edit_all_problem'))
        request = self.admin_request(manager)
        self.assertTrue(model_admin.has_change_permission(request, self.submission))
        self.owner.is_staff = True
        self.owner.save()
        self.assertIn('is_source_public', model_admin.get_readonly_fields(request, self.submission))
        model_admin.save_model(request, self.submission, None, True)
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_source_public)

    def test_admin_can_change_both_directions_with_audit_log(self):
        model_admin = SubmissionAdmin(Submission, admin.site)
        manager = create_user('sharing-superuser', is_staff=True, is_superuser=True)
        for value in (False, True):
            request = self.admin_request(manager)
            form_class = model_admin.get_form(request, self.submission)
            form = form_class(instance=self.submission)
            form.changed_data = ['is_source_public']
            self.submission.is_source_public = value
            model_admin.save_model(request, self.submission, form, True)
            message = model_admin.construct_change_message(request, form, [], False)
            model_admin.log_change(request, self.submission, message)
            self.submission.refresh_from_db()
            self.assertEqual(self.submission.is_source_public, value)
            log = LogEntry.objects.latest('id')
            self.assertEqual(log.user_id, manager.pk)
            self.assertIn('→', log.get_change_message())
            self.make_submission(self.viewer)
            self.assertEqual(self.submission.can_see_source(self.viewer), value)

    def test_admin_detail_and_filter_render_and_unauthorized_post_fails(self):
        manager = create_user('sharing-superuser', is_staff=True, is_superuser=True)
        self.client.force_login(manager)
        url = reverse('admin:judge_submission_change', args=(self.submission.pk,))
        self.assertContains(self.client.get(url), 'name="is_source_public"')
        response = self.client.get(reverse('admin:judge_submission_changelist'), {'is_source_public__exact': '1'})
        self.assertContains(response, self.problem.code)
        self.client.force_login(self.staff)
        self.assertIn(self.client.post(url, {'is_source_public': ''}).status_code, (403, 404))
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.is_source_public)
