import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from judge.models import Judge, Language, LanguageLimit, Problem, Profile


DEFAULT_LANGUAGES = {
    'C': {
        'name': 'C', 'short_name': None, 'common_name': 'C',
        'ace': 'c_cpp', 'pygments': 'c', 'extension': 'c',
    },
    'CPP17': {
        'name': 'C++17', 'short_name': 'C++17', 'common_name': 'C++',
        'ace': 'c_cpp', 'pygments': 'cpp', 'extension': 'cpp',
    },
    'JAVA': {
        'name': 'Java 17', 'short_name': 'Java 17', 'common_name': 'Java',
        'ace': 'java', 'pygments': 'java', 'extension': 'java',
    },
    'PY3': {
        'name': 'Python 3', 'short_name': None, 'common_name': 'Python',
        'ace': 'python', 'pygments': 'python3', 'extension': 'py',
    },
}

LEGACY_LANGUAGE_REPLACEMENTS = {
    'CPP14': 'CPP17',
    'JAVA8': 'JAVA',
}


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

        for key, defaults in DEFAULT_LANGUAGES.items():
            Language.objects.update_or_create(key=key, defaults=defaults)
        self._replace_legacy_languages()
        self.stdout.write(self.style.SUCCESS('Default languages registered'))

        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Django superuser already exists; skipping creation')
        else:
            username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
            email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()

            if not username:
                raise CommandError('DJANGO_SUPERUSER_USERNAME must be set')
            if not password or password == 'change-me':
                raise CommandError('DJANGO_SUPERUSER_PASSWORD must be set to a non-default value')

            username_lookup = {User.USERNAME_FIELD: username}
            if User.objects.filter(**username_lookup).exists():
                raise CommandError(f'User {username!r} already exists but is not a superuser')

            User.objects.create_superuser(
                **username_lookup,
                email=email,
                password=password,
            )
            self.stdout.write(self.style.SUCCESS(f'Django superuser {username} created'))

        judge, created = Judge.objects.update_or_create(
            name=judge_name,
            defaults={'auth_key': judge_key},
        )
        action = 'registered' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'Judge {judge.name} {action}'))

    def _replace_legacy_languages(self):
        allowed_languages = Problem.allowed_languages.through
        for legacy_key, replacement_key in LEGACY_LANGUAGE_REPLACEMENTS.items():
            legacy = Language.objects.filter(key=legacy_key).first()
            if legacy is None:
                continue
            replacement = Language.objects.get(key=replacement_key)

            problem_ids = list(allowed_languages.objects.filter(
                language_id=legacy.id,
            ).values_list('problem_id', flat=True))
            allowed_languages.objects.bulk_create([
                allowed_languages(problem_id=problem_id, language_id=replacement.id)
                for problem_id in problem_ids
            ], ignore_conflicts=True)
            allowed_languages.objects.filter(language_id=legacy.id).delete()

            for limit in LanguageLimit.objects.filter(language=legacy):
                LanguageLimit.objects.update_or_create(
                    problem=limit.problem,
                    language=replacement,
                    defaults={
                        'time_limit': limit.time_limit,
                        'memory_limit': limit.memory_limit,
                    },
                )
            LanguageLimit.objects.filter(language=legacy).delete()
            Profile.objects.filter(language=legacy).update(language=replacement)
