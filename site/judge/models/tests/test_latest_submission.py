from django.test import TestCase

from judge.models import Language, Submission, SubmissionSource
from judge.models.LatestSubmission import LatestSubmission
from judge.models.tests.util import create_problem, create_user


class LatestSubmissionLanguageTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(username='latest-submission-user')
        cls.problem = create_problem(code='latestlang')
        cls.python, _ = Language.objects.update_or_create(
            key='PY3', defaults={
                'name': 'Python 3', 'common_name': 'Python', 'ace': 'python',
                'pygments': 'python3', 'extension': 'py',
            },
        )
        cls.cpp, _ = Language.objects.update_or_create(
            key='CPP14', defaults={
                'name': 'C++14', 'common_name': 'C++', 'ace': 'c_cpp',
                'pygments': 'cpp', 'extension': 'cpp',
            },
        )

    def create_graded_submission(self, language, source, points):
        submission = Submission.objects.create(
            user=self.user.profile,
            problem=self.problem,
            language=language,
        )
        SubmissionSource.objects.create(submission=submission, source=source)
        submission.status = 'D'
        submission.result = 'AC'
        submission.points = points
        submission.save()
        return submission

    def test_created_latest_submission_uses_submission_language(self):
        self.create_graded_submission(self.cpp, 'int main() {}', 1)

        latest = LatestSubmission.objects.get(user=self.user, problem=self.problem)
        self.assertEqual(latest.language, self.cpp)

    def test_higher_scoring_submission_updates_language(self):
        self.create_graded_submission(self.python, 'print(0)', 0)
        self.create_graded_submission(self.cpp, 'int main() {}', 1)

        latest = LatestSubmission.objects.get(user=self.user, problem=self.problem)
        self.assertEqual(latest.language, self.cpp)
        self.assertEqual(latest.source, 'int main() {}')
        self.assertEqual(latest.score, 1)
