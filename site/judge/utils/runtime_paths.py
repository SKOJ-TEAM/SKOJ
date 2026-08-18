import os

from django.conf import settings


def problem_data_path(*parts):
    return os.path.join(settings.DMOJ_PROBLEM_DATA_ROOT, *parts)


def judge_debug_log_path(filename='log.ksl'):
    return os.path.join(settings.BASE_DIR, 'dummy', filename)
