from celery import shared_task

from judge.gamification import sync_profile_gamification
from judge.models import Profile

__all__ = ('rebuild_all_gamification',)


@shared_task
def rebuild_all_gamification():
    rebuilt = 0
    for profile in Profile.objects.order_by('id').iterator(chunk_size=200):
        sync_profile_gamification(profile)
        rebuilt += 1
    return rebuilt
