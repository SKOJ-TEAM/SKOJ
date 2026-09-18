"""Request-scoped submission access, shared by views and list rendering."""
from django.db.models import F
from django.utils.functional import cached_property

from judge.models import Problem, Submission, SubmissionSourceAccess


class SubmissionAccess:
    def __init__(self, user):
        self.user = user
        self.authenticated = user.is_authenticated
        self.profile = user.profile if self.authenticated else None
        self._contest_permissions = {}

    @cached_property
    def solved_ids(self):
        return set(Submission.objects.filter(
            user=self.profile, status='D', result='AC', points__gte=F('problem__points'),
        ).values_list('problem_id', flat=True)) if self.authenticated else set()

    @cached_property
    def legacy_solved_ids(self):
        # Contest policy historically accepts full AC without the status constraint.
        return set(Submission.objects.filter(
            user=self.profile, result='AC', points__gte=F('problem__points'),
        ).values_list('problem_id', flat=True))

    @cached_property
    def visible_ids(self):
        return set(Problem.get_visible_problems(self.user).values_list('id', flat=True))

    @cached_property
    def editable_ids(self):
        return set(Problem.get_editable_problems(self.user).values_list('id', flat=True))

    @cached_property
    def tester_ids(self):
        return set(Problem.testers.through.objects.filter(profile=self.profile).values_list('problem_id', flat=True))

    def can_edit(self, problem):
        return self.authenticated and problem.id in self.editable_ids

    def can_manage_problem(self, problem):
        return self.authenticated and (
            self.user.is_staff or self.user.has_perm('judge.view_all_submission') or self.can_edit(problem)
        )

    def can_share_problem(self, problem):
        # Sharing must not bypass an active contest or a locked Challenge assignment.
        return self.authenticated and not self.profile.current_contest_id and not problem.is_contest_problem and (
            problem.id in self.solved_ids and problem.id in self.visible_ids
        )

    def can_list_problem(self, problem):
        return self.can_manage_problem(problem) or self.can_share_problem(problem)

    def is_privileged(self, submission):
        if not self.authenticated:
            return False
        if submission.user_id == self.profile.id or self.can_manage_problem(submission.problem):
            return True
        problem = submission.problem
        if problem.id in self.tester_ids and (
            problem.submission_source_visibility == SubmissionSourceAccess.ONLY_OWN or
            problem.submission_source_visibility == SubmissionSourceAccess.SOLVED and problem.id in self.solved_ids
        ):
            return True
        contest = submission.contest_object
        if contest is not None:
            if contest.id not in self._contest_permissions:
                self._contest_permissions[contest.id] = (
                    self.profile.id in contest.editor_ids or
                    contest.view_contest_submissions.filter(id=self.profile.id).exists() or
                    contest.tester_see_submissions and self.profile.id in contest.tester_ids
                )
            return self._contest_permissions[contest.id]
        return False

    def can_see_detail(self, submission):
        if self.is_privileged(submission):
            return True
        if not self.authenticated:
            return False
        if submission.contest_object_id or submission.problem.is_contest_problem:
            # Keep the pre-existing contest source policy; ordinary sharing adds no contest access.
            problem = submission.problem
            visibility = problem.submission_source_visibility
            return visibility == SubmissionSourceAccess.ALWAYS or (
                visibility == SubmissionSourceAccess.SOLVED and
                (problem.is_public or problem.id in self.tester_ids) and problem.id in self.legacy_solved_ids
            )
        return self.can_share_problem(submission.problem)

    def can_see_source(self, submission):
        if self.is_privileged(submission):
            return True
        return (self.authenticated and submission.is_source_public and not submission.user.user.is_staff and
                self.can_see_detail(submission))


def submission_access(request):
    if not hasattr(request, '_submission_access'):
        request._submission_access = SubmissionAccess(request.user)
    return request._submission_access
