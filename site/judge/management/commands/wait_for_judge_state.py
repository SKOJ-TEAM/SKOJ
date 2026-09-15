import math
import os
import time
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from judge.models import Judge, Submission


class Command(BaseCommand):
    help = 'Wait read-only for submissions to drain or configured judges to reconnect.'

    def add_arguments(self, parser):
        parser.add_argument('state', choices=('drained', 'ready'))
        parser.add_argument('--timeout', type=float, default=600)
        parser.add_argument('--interval', type=float, default=2)
        parser.add_argument('--since', type=float, help='Earliest allowed judge connection time (Unix seconds).')

    def handle(self, *args, **options):
        timeout, interval = options['timeout'], options['interval']
        if not math.isfinite(timeout) or timeout < 0 or not math.isfinite(interval) or interval <= 0:
            raise CommandError('timeout must be finite and nonnegative; interval must be finite and positive')
        state = options['state']
        names, since = [], None
        if state == 'ready':
            names = [os.environ.get(key, '').strip() for key in ('JUDGE_NAME', 'JUDGE_NAME_2')]
            if not all(names) or len(set(names)) != len(names):
                raise CommandError('JUDGE_NAME and JUDGE_NAME_2 must be distinct nonempty names')
            timestamp = options['since']
            if timestamp is None or not math.isfinite(timestamp):
                raise CommandError('ready requires a finite --since timestamp')
            try:
                since = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (ValueError, OverflowError, OSError) as exc:
                raise CommandError('invalid --since timestamp') from exc
        elif Submission._meta.db_table not in connection.introspection.table_names():
            self.stdout.write('No submission table yet; nothing to drain.')
            return

        deadline = time.monotonic() + timeout
        while True:
            if state == 'drained':
                count = Submission.objects.filter(status__in=Submission.IN_PROGRESS_GRADING_STATUS).count()
                complete, detail = count == 0, f'Unfinished submissions (QU/P/G): {count}'
            else:
                connected = set(Judge.objects.filter(
                    name__in=names, online=True, start_time__gte=since,
                ).values_list('name', flat=True))
                missing = sorted(set(names) - connected)
                complete, detail = not missing, 'Waiting for judge connections: ' + (', '.join(missing) or 'none')
            self.stdout.write(detail)
            self.stdout.flush()
            if complete:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandError(f'Timed out waiting for {state}. {detail}')
            time.sleep(min(interval, remaining))
