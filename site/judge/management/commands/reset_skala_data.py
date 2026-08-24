from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from judge.models import AlgorithmGuide, Contest, Problem


CONFIRMATION = 'DELETE-SKALA-DATA'


class Command(BaseCommand):
    help = ('Problem과 AlgorithmGuide 및 superuser를 보존하고 기존 대회와 일반 사용자 데이터를 정리합니다. '
            '기본 실행은 변경하지 않는 dry-run입니다.')

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='실제로 데이터를 삭제합니다.')
        parser.add_argument('--confirm', default='', help='실행 확인 문자열')

    def handle(self, *args, **options):
        before = self._counts()
        self._print_counts('정리 전', before)

        if not options['execute']:
            self.stdout.write(self.style.WARNING(
                'dry-run: 데이터가 변경되지 않았습니다. 실제 실행은 '
                '--execute --confirm %s 옵션이 필요합니다.' % CONFIRMATION,
            ))
            return

        if options['confirm'] != CONFIRMATION:
            raise CommandError('실행하려면 --confirm %s를 정확히 입력해야 합니다.' % CONFIRMATION)

        with transaction.atomic():
            Contest.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

            after = self._counts()
            if after['problems'] != before['problems'] or after['guides'] != before['guides']:
                raise CommandError('Problem 또는 AlgorithmGuide 개수가 변경되어 작업을 롤백합니다.')

        self._print_counts('정리 후', after)
        self.stdout.write(self.style.SUCCESS('기존 대회와 일반 사용자 데이터를 정리했습니다.'))

    @staticmethod
    def _counts():
        return {
            'problems': Problem.objects.count(),
            'guides': AlgorithmGuide.objects.count(),
            'contests': Contest.objects.count(),
            'regular_users': User.objects.filter(is_superuser=False).count(),
            'superusers': User.objects.filter(is_superuser=True).count(),
        }

    def _print_counts(self, label, counts):
        self.stdout.write('%s: Problem=%d, Guide=%d, Contest=%d, 일반 사용자=%d, superuser=%d' % (
            label,
            counts['problems'],
            counts['guides'],
            counts['contests'],
            counts['regular_users'],
            counts['superusers'],
        ))
