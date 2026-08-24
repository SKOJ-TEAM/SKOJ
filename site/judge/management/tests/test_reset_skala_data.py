from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from judge.management.commands.reset_skala_data import CONFIRMATION
from judge.models import AlgorithmGuide, Contest, Problem, ProblemType
from judge.models.tests.util import CommonDataMixin, create_problem


class ResetSkalaDataCommandTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem = create_problem(code='preserved-problem')
        problem_type = ProblemType.objects.create(name='preserved-guide', full_name='보존 가이드')
        cls.guide = AlgorithmGuide.objects.create(
            problem_type=problem_type,
            title='보존할 가이드',
            summary='요약',
            content='본문',
            created_by=cls.users['normal'],
        )
        now = timezone.now()
        cls.contest = Contest(key='discarded-contest', name='삭제할 대회',
                              start_time=now - timezone.timedelta(days=1),
                              end_time=now + timezone.timedelta(days=1))
        cls.contest.save()

    def test_default_is_dry_run(self):
        output = StringIO()

        call_command('reset_skala_data', stdout=output)

        self.assertTrue(Problem.objects.filter(pk=self.problem.pk).exists())
        self.assertTrue(AlgorithmGuide.objects.filter(pk=self.guide.pk).exists())
        self.assertTrue(Contest.objects.filter(pk=self.contest.pk).exists())
        self.assertIn('dry-run', output.getvalue())

    def test_execute_requires_exact_confirmation(self):
        with self.assertRaises(CommandError):
            call_command('reset_skala_data', execute=True, confirm='wrong')

    def test_execute_preserves_problem_guide_and_superuser(self):
        call_command('reset_skala_data', execute=True, confirm=CONFIRMATION, stdout=StringIO())

        self.assertTrue(Problem.objects.filter(pk=self.problem.pk).exists())
        guide = AlgorithmGuide.objects.get(pk=self.guide.pk)
        self.assertIsNone(guide.created_by)
        self.assertFalse(Contest.objects.exists())
        self.assertFalse(type(self.users['normal']).objects.filter(pk=self.users['normal'].pk).exists())
        self.assertTrue(type(self.users['superuser']).objects.filter(pk=self.users['superuser'].pk).exists())
