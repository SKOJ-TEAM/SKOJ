from django.urls import reverse


def problem_group_navigation(problem, *, in_contest=False, contest_submission=False):
    """Offer ordinary practice navigation without revealing restricted classifications."""
    if (in_contest or contest_submission or not problem.is_public or problem.is_encrypted
            or problem.is_contest_problem or problem.challenge_exam_id):
        return None
    return {
        'name': problem.group.full_name,
        'url': reverse('problem_group_list', args=(problem.group.name,)),
    }
