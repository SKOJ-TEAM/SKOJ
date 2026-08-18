import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from judge.models import Judge


class Command(BaseCommand):
    help = 'initialize the database, static files, and Docker judge registration'

    def handle(self, *args, **options):
        judge_name = os.environ.get('JUDGE_NAME', '').strip()
        judge_key = os.environ.get('JUDGE_KEY', '').strip()

        if not judge_name:
            raise CommandError('JUDGE_NAME must be set')
        if not judge_key or judge_key == 'change-me':
            raise CommandError('JUDGE_KEY must be set to a non-default value')
        if len(judge_name) > Judge._meta.get_field('name').max_length:
            raise CommandError('JUDGE_NAME must be at most 50 characters')
        if len(judge_key) > Judge._meta.get_field('auth_key').max_length:
            raise CommandError('JUDGE_KEY must be at most 100 characters')

        call_command('migrate', interactive=False)
        call_command('compilemessages', verbosity=0)
        call_command('compilejsi18n', verbosity=0)
        call_command('collectstatic', interactive=False, verbosity=0)

        judge, created = Judge.objects.update_or_create(
            name=judge_name,
            defaults={'auth_key': judge_key},
        )
        action = 'registered' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'Judge {judge.name} {action}'))
