from django.core.management.base import BaseCommand, CommandError

from judge.gamification import sync_profile_gamification
from judge.models import Profile


class Command(BaseCommand):
    help = 'Recalculate tier progress, challenge eligibility, and weighted scores from accepted submissions.'

    def add_arguments(self, parser):
        parser.add_argument('--profile', type=int, help='Rebuild only the specified profile ID.')
        parser.add_argument('--all', action='store_true', dest='all_profiles', help='Rebuild every profile.')

    def handle(self, *args, **options):
        profile_id = options['profile']
        if bool(profile_id) == bool(options['all_profiles']):
            raise CommandError('Specify exactly one of --profile or --all.')

        profiles = Profile.objects.select_related('user').order_by('id')
        if profile_id:
            profiles = profiles.filter(pk=profile_id)
            if not profiles.exists():
                raise CommandError('Profile %d does not exist.' % profile_id)

        rebuilt = 0
        for profile in profiles.iterator(chunk_size=200):
            sync_profile_gamification(profile)
            rebuilt += 1
        self.stdout.write(self.style.SUCCESS('Rebuilt gamification state for %d profile(s).' % rebuilt))
