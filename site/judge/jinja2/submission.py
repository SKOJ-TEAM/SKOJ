from . import registry


@registry.function
def submission_layout(submission, access):
    return access.can_see_detail(submission), access.can_edit(submission.problem)
