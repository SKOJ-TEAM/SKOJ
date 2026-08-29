from io import StringIO

from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from judge.management.commands.initialize_docker import Command, get_judge_credentials
from judge.models import Judge


class JudgeCredentialsTest(SimpleTestCase):
    def setUp(self):
        self.environ = {
            'JUDGE_NAME': 'skoj-judge-01',
            'JUDGE_KEY': 'first-secret',
            'JUDGE_NAME_2': 'skoj-judge-02',
            'JUDGE_KEY_2': 'second-secret',
        }

    def test_returns_both_trimmed_judge_credentials(self):
        environ = {
            key: f'  {value}  '
            for key, value in self.environ.items()
        }

        self.assertEqual([
            ('skoj-judge-01', 'first-secret'),
            ('skoj-judge-02', 'second-secret'),
        ], get_judge_credentials(environ))

    def test_requires_every_name_and_key(self):
        for variable in self.environ:
            with self.subTest(variable=variable):
                environ = self.environ.copy()
                environ[variable] = ''
                with self.assertRaisesMessage(CommandError, variable):
                    get_judge_credentials(environ)

    def test_rejects_default_keys(self):
        for variable in ('JUDGE_KEY', 'JUDGE_KEY_2'):
            with self.subTest(variable=variable):
                environ = self.environ.copy()
                environ[variable] = 'change-me'
                with self.assertRaisesMessage(CommandError, variable):
                    get_judge_credentials(environ)

    def test_rejects_duplicate_names(self):
        self.environ['JUDGE_NAME_2'] = self.environ['JUDGE_NAME']

        with self.assertRaisesMessage(CommandError, 'Judge names must be unique'):
            get_judge_credentials(self.environ)

    def test_rejects_duplicate_keys(self):
        self.environ['JUDGE_KEY_2'] = self.environ['JUDGE_KEY']

        with self.assertRaisesMessage(CommandError, 'Judge authentication keys must be unique'):
            get_judge_credentials(self.environ)

    def test_rejects_values_over_model_field_limits(self):
        cases = (
            ('JUDGE_NAME_2', Judge._meta.get_field('name').max_length + 1),
            ('JUDGE_KEY_2', Judge._meta.get_field('auth_key').max_length + 1),
        )
        for variable, length in cases:
            with self.subTest(variable=variable):
                environ = self.environ.copy()
                environ[variable] = 'x' * length
                with self.assertRaisesMessage(CommandError, variable):
                    get_judge_credentials(environ)


class JudgeRegistrationTest(TestCase):
    def test_registers_both_judges_and_updates_keys_idempotently(self):
        command = Command(stdout=StringIO())
        command._register_judges([
            ('skoj-judge-01', 'first-secret'),
            ('skoj-judge-02', 'second-secret'),
        ])

        self.assertEqual(2, Judge.objects.count())
        self.assertEqual('first-secret', Judge.objects.get(name='skoj-judge-01').auth_key)
        self.assertEqual('second-secret', Judge.objects.get(name='skoj-judge-02').auth_key)

        command._register_judges([
            ('skoj-judge-01', 'updated-first-secret'),
            ('skoj-judge-02', 'updated-second-secret'),
        ])

        self.assertEqual(2, Judge.objects.count())
        self.assertEqual('updated-first-secret', Judge.objects.get(name='skoj-judge-01').auth_key)
        self.assertEqual('updated-second-secret', Judge.objects.get(name='skoj-judge-02').auth_key)
