from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SubmissionSharingMigrationTest(TransactionTestCase):
    def migrate(self, name):
        executor = MigrationExecutor(connection)
        executor.migrate([('judge', name)])
        return executor.loader.project_state([('judge', name)]).apps

    def test_existing_sources_and_verdicts_survive_with_staff_private(self):
        old = self.migrate('0052_rename_promotion_to_challenge')
        self.addCleanup(self.migrate, '0053_submission_source_public')
        User = old.get_model('auth', 'User')
        Profile = old.get_model('judge', 'Profile')
        Submission = old.get_model('judge', 'Submission')
        Source = old.get_model('judge', 'SubmissionSource')
        language = old.get_model('judge', 'Language').objects.create(
            key='SHRPY3', name='Sharing', short_name='Sharing', common_name='Sharing', ace='python',
            pygments='python', extension='py',
        )
        group = old.get_model('judge', 'ProblemGroup').objects.create(name='sharing-migration', full_name='Migration')
        problem = old.get_model('judge', 'Problem').objects.create(
            code='sharing-migration', name='Migration', group_id=group.pk, points=10,
            submission_source_visibility_mode='O', is_public=True,
        )
        records = []
        for is_staff in (False, True):
            user = User.objects.create(username='sharing-migration-' + str(is_staff), is_staff=is_staff)
            profile = Profile.objects.create(user_id=user.pk)
            submission = Submission.objects.create(user_id=profile.pk, problem_id=problem.pk, language_id=language.pk,
                                                   result='WA', status='D', points=0)
            Source.objects.create(submission_id=submission.pk, source='migration source')
            records.append((submission.pk, profile.pk, not is_staff))
        new = self.migrate('0053_submission_source_public')
        for pk, profile_id, is_public in records:
            submission = new.get_model('judge', 'Submission').objects.get(pk=pk)
            self.assertEqual(submission.user_id, profile_id)
            self.assertEqual(submission.problem_id, problem.pk)
            self.assertEqual(submission.is_source_public, is_public)
            self.assertEqual((submission.status, submission.result, submission.points), ('D', 'WA', 0))
            self.assertEqual(new.get_model('judge', 'SubmissionSource').objects.get(submission_id=pk).source,
                             'migration source')
