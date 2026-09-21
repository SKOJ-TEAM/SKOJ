import json

from django.core import serializers
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ChallengeRenameMigrationTestCase(TransactionTestCase):
    old_migration = '0051_profile_avatar'
    new_migration = '0052_rename_promotion_to_challenge'

    def migrate(self, name):
        # Use the command to include Django's content-type rename hooks.
        call_command('migrate', 'judge', name, verbosity=0, interactive=False, skip_checks=True)
        loader = MigrationExecutor(connection).loader
        targets = [node for node in loader.graph.leaf_nodes() if node[0] != 'judge']
        return loader.project_state(targets + [('judge', name)]).apps

    def test_records_permissions_and_admin_history_survive_forward_and_reverse(self):
        self.addCleanup(self.migrate, self.new_migration)
        old = self.migrate(self.old_migration)
        user = old.get_model('auth', 'User').objects.create(username='challenge-migration-user', is_staff=True)
        profile = old.get_model('judge', 'Profile').objects.create(user_id=user.pk)
        group = old.get_model('judge', 'ProblemGroup').objects.create(name='migration', full_name='Migration')
        exam = old.get_model('judge', 'PromotionExam').objects.create(title='기존 승급전', source_tier='bronze')
        problem = old.get_model('judge', 'Problem').objects.create(
            code='migration-exam', name='기존 문제', group_id=group.pk, points=10,
            promotion_exam_id=exam.pk, promotion_order=7,
        )
        completed_at = timezone.now()
        attempt = old.get_model('judge', 'PromotionAttempt').objects.create(
            profile_id=profile.pk, exam_id=exam.pk, source_tier='bronze', target_tier='silver',
            completed_at=completed_at,
        )
        snapshot = old.get_model('judge', 'PromotionAttemptProblem').objects.create(
            attempt_id=attempt.pk, problem_id=problem.pk, order=7,
        )
        auth_group = old.get_model('auth', 'Group').objects.create(name='Challenge managers')
        user.groups.add(auth_group)
        permission_ids = {}
        for suffix in ('exam', 'attempt', 'attemptproblem'):
            permission = old.get_model('auth', 'Permission').objects.get(
                content_type__app_label='judge', codename='change_promotion' + suffix,
            )
            permission_ids[suffix] = (permission.pk, permission.content_type_id)
            user.user_permissions.add(permission)
            auth_group.permissions.add(permission)
        log = old.get_model('admin', 'LogEntry').objects.create(
            user_id=user.pk, content_type_id=permission_ids['exam'][1], object_id=str(exam.pk),
            object_repr=exam.title, action_flag=2,
        )
        revision = old.get_model('reversion', 'Revision').objects.create(date_created=timezone.now(), user_id=user.pk)
        problem_type = old.get_model('contenttypes', 'ContentType').objects.get(app_label='judge', model='problem')
        version = old.get_model('reversion', 'Version').objects.create(
            revision_id=revision.pk, object_id=str(problem.pk), content_type_id=problem_type.pk,
            db='default', format='json', serialized_data=serializers.serialize('json', [problem]),
            object_repr=problem.name,
        )

        for migration, prefix in ((self.new_migration, 'challenge'), (self.old_migration, 'promotion'),
                                  (self.new_migration, 'challenge')):
            with self.subTest(migration=migration):
                apps = self.migrate(migration)
                self.assertEqual(apps.get_model('judge', prefix + 'Exam').objects.get(pk=exam.pk).title, exam.title)
                migrated_problem = apps.get_model('judge', 'Problem').objects.get(pk=problem.pk)
                self.assertEqual(getattr(migrated_problem, prefix + '_exam_id'), exam.pk)
                self.assertEqual(getattr(migrated_problem, prefix + '_order'), 7)
                migrated_attempt = apps.get_model('judge', prefix + 'Attempt').objects.get(pk=attempt.pk)
                self.assertEqual(migrated_attempt.profile_id, profile.pk)
                self.assertEqual(migrated_attempt.exam_id, exam.pk)
                self.assertEqual(migrated_attempt.completed_at, completed_at)
                self.assertEqual(list(migrated_attempt.problems.values_list('pk', flat=True)), [problem.pk])
                migrated_snapshot = apps.get_model('judge', prefix + 'AttemptProblem').objects.get(pk=snapshot.pk)
                self.assertEqual(migrated_snapshot.order, 7)
                for suffix, (permission_id, content_type_id) in permission_ids.items():
                    permission = apps.get_model('auth', 'Permission').objects.get(pk=permission_id)
                    self.assertEqual(permission.codename, 'change_' + prefix + suffix)
                    self.assertEqual(permission.content_type_id, content_type_id)
                    self.assertEqual(permission.content_type.model, prefix + suffix)
                    self.assertTrue(user.user_permissions.filter(pk=permission.pk).exists())
                    self.assertTrue(auth_group.permissions.filter(pk=permission.pk).exists())
                self.assertEqual(apps.get_model('admin', 'LogEntry').objects.get(pk=log.pk).content_type_id,
                                 permission_ids['exam'][1])
                migrated_version = apps.get_model('reversion', 'Version').objects.get(pk=version.pk)
                version_fields = json.loads(migrated_version.serialized_data)[0]['fields']
                self.assertEqual(version_fields[prefix + '_exam'], exam.pk)
                self.assertEqual(version_fields[prefix + '_order'], 7)
                self.assertEqual(migrated_version.revision_id, revision.pk)
                if prefix == 'challenge':
                    from reversion.models import Version
                    self.assertEqual(Version.objects.get(pk=version.pk).field_dict['challenge_exam_id'], exam.pk)
