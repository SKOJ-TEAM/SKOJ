from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from judge.models import Judge, Language, Submission
from judge.models.tests.util import create_problem, create_user


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class WaitForJudgeStateTest(TestCase):
    def run_command(self, state, **kwargs):
        output = StringIO()
        call_command('wait_for_judge_state', state, timeout=kwargs.pop('timeout', 0), stdout=output, **kwargs)
        return output.getvalue()

    def submission(self):
        language, _ = Language.objects.get_or_create(key='PY3', defaults={'name': 'Python 3'})
        return Submission.objects.create(
            problem=create_problem(code='drain-test'), language=language,
            user=create_user(username='drain-user').profile,
        )

    def test_empty_queue_is_ready_to_stop(self):
        self.assertIn('QU/P/G): 0', self.run_command('drained'))

    def test_each_unfinished_state_blocks_without_mutating_submission(self):
        submission = self.submission()
        for status in ('QU', 'P', 'G'):
            with self.subTest(status=status):
                Submission.objects.filter(pk=submission.pk).update(status=status)
                with self.assertRaisesMessage(CommandError, 'Timed out waiting for drained'):
                    self.run_command('drained')
                submission.refresh_from_db()
                self.assertEqual(submission.status, status)
        Submission.objects.filter(pk=submission.pk).update(status='D')
        self.assertIn('QU/P/G): 0', self.run_command('drained'))

    def test_waits_until_submission_finishes(self):
        submission = self.submission()
        with patch('judge.management.commands.wait_for_judge_state.time.sleep',
                   side_effect=lambda _: Submission.objects.filter(pk=submission.pk).update(status='D')) as sleep:
            self.assertIn('QU/P/G): 0', self.run_command('drained', timeout=10))
        sleep.assert_called_once()

    def test_new_database_without_submission_table_has_nothing_to_drain(self):
        with patch('judge.management.commands.wait_for_judge_state.connection.introspection.table_names', return_value=[]):
            self.assertIn('nothing to drain', self.run_command('drained'))

    @patch.dict('os.environ', {'JUDGE_NAME': 'wait-first', 'JUDGE_NAME_2': 'wait-second'})
    def test_ready_requires_both_fresh_connections(self):
        now = timezone.now()
        first = Judge.objects.create(name='wait-first', auth_key='test-first', online=True, start_time=now)
        second = Judge.objects.create(name='wait-second', auth_key='test-second', online=True,
                                      start_time=now - timedelta(hours=1))
        with self.assertRaisesMessage(CommandError, 'wait-second'):
            self.run_command('ready', since=now.timestamp())
        second.start_time = now
        second.online = False
        second.save()
        with self.assertRaisesMessage(CommandError, 'wait-second'):
            self.run_command('ready', since=now.timestamp())
        second.online = True
        second.save()
        self.assertIn('connections: none', self.run_command('ready', since=now.timestamp()))
        first.refresh_from_db()
        self.assertTrue(first.online)

    @patch.dict('os.environ', {'JUDGE_NAME': 'wait-first', 'JUDGE_NAME_2': 'wait-first'})
    def test_invalid_judge_configuration_is_rejected(self):
        with self.assertRaisesMessage(CommandError, 'distinct nonempty'):
            self.run_command('ready', since=timezone.now().timestamp())

    @patch.dict('os.environ', {'JUDGE_NAME': 'wait-first', 'JUDGE_NAME_2': 'wait-second'})
    def test_ready_cannot_accept_stale_online_flags_without_since(self):
        with self.assertRaisesMessage(CommandError, '--since'):
            self.run_command('ready')

    def test_invalid_wait_parameters_are_rejected(self):
        for kwargs in ({'timeout': -1}, {'timeout': float('nan')}, {'interval': 0}, {'interval': float('inf')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(CommandError):
                self.run_command('drained', **kwargs)
