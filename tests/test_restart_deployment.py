import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RestartDeploymentTest(unittest.TestCase):
    def run_restart(self, failure='', first=False):
        # Stub all external mutations, but execute the real Bash deployment control flow.
        with tempfile.TemporaryDirectory(prefix='skoj-restart-test-') as directory:
            trace_file = Path(directory) / 'trace'
            script = 'source ' + shlex.quote(str(ROOT / 'restart.sh')) + '\n' + r'''
trace() { printf '%s\n' "$*" >> "$TEST_TRACE"; }
log() { trace "log $*"; }
prepare_runtime() { trace prepare; }
require_command() { :; }
platform_preflight() { trace preflight; }
validate_release() { printf '%s\n' "$1"; }
build_release_image() { printf 'skoj-app:%s\n' "$1"; }
load_state() {
    [[ "$TEST_FIRST" == 0 ]] || return 1
    ACTIVE_COLOR=green; PREVIOUS_COLOR=blue
    SKOJ_BLUE_IMAGE=old-blue; SKOJ_BLUE_RELEASE=old-blue
    SKOJ_GREEN_IMAGE=old-green; SKOJ_GREEN_RELEASE=old-green
    SKOJ_TOOL_IMAGE=old-tool; SKOJ_BRIDGE_IMAGE=old-bridge
}
switch_nginx() { trace "route $*"; }
stop_legacy_application() { trace stop-legacy; }
backup_database() { trace backup; DATABASE_BACKUP=test-backup; }
compose() {
    trace "compose $*"
    if [[ "$*" == *"wait_for_judge_state drained"* && "$TEST_FAILURE" == drained ]]; then return 1; fi
    if [[ "$*" == *"wait_for_judge_state ready"* && "$TEST_FAILURE" == ready ]]; then return 1; fi
    if [[ "$*" == 'run --rm init' && "$TEST_FAILURE" == init ]]; then return 1; fi
    if [[ "$*" == 'up -d --no-deps --force-recreate bridge' ]]; then
        [[ "$SKOJ_BRIDGE_IMAGE" == skoj-app:test-release ]] || return 1
    fi
}
wait_for_web() { trace web-ready; }
smoke_candidate() { trace smoke; }
wait_for_service_health() { trace celery-ready; }
smoke_public() { trace public-ready; }
persist_loaded_state() { trace "persist $ACTIVE_COLOR $SKOJ_BRIDGE_IMAGE"; }
main test-release
'''
            env = dict(os.environ, SKOJ_DEPLOYMENT_DIR=directory, TEST_TRACE=str(trace_file),
                       TEST_FAILURE=failure, TEST_FIRST='1' if first else '0',
                       SKOJ_JUDGE_DRAIN_TIMEOUT='600', SKOJ_JUDGE_READY_TIMEOUT='120')
            result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
            return result, trace_file.read_text().splitlines()

    def test_waits_before_stopping_bridge_and_opens_only_after_reconnection(self):
        result, lines = self.run_restart()
        self.assertEqual(result.returncode, 0, result.stderr)
        prefixes = (
            'route maintenance', 'compose stop --timeout 600 web-',
            'compose stop --timeout 600 celery-', 'compose run --rm --no-deps init python manage.py wait_for_judge_state drained',
            'compose stop --timeout 60 bridge', 'backup', 'compose run --rm init',
            'compose up -d --no-deps --force-recreate bridge',
            'compose run --rm --no-deps init python manage.py wait_for_judge_state ready --since ',
            'compose up -d --no-deps web-blue celery-blue', 'route blue',
            'persist blue skoj-app:test-release',
        )
        indices = [next(i for i, line in enumerate(lines) if line.startswith(prefix)) for prefix in prefixes]
        self.assertEqual(indices, sorted(indices))
        self.assertNotIn('compose up -d --no-deps judge judge-02', lines)

    def test_drain_timeout_keeps_old_bridge_and_maintenance(self):
        result, lines = self.run_restart(failure='drained')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('compose stop --timeout 60 bridge', lines)
        self.assertNotIn('backup', lines)
        self.assertNotIn('route blue', lines)
        self.assertFalse(any(line.startswith('persist ') for line in lines))
        self.assertGreaterEqual(lines.count('route maintenance'), 2)

    def test_reconnection_failure_does_not_open_site_or_persist_success(self):
        result, lines = self.run_restart(failure='ready')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('route blue', lines)
        self.assertFalse(any(line.startswith('persist ') for line in lines))
        self.assertGreaterEqual(lines.count('route maintenance'), 2)

    def test_failed_init_does_not_restart_bridge(self):
        result, lines = self.run_restart(failure='init')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('compose up -d --no-deps --force-recreate bridge', lines)
        self.assertNotIn('route blue', lines)

    def test_first_deployment_starts_judges_before_checking_connections(self):
        result, lines = self.run_restart(first=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('stop-legacy', lines)
        self.assertIn('compose up -d --no-deps judge judge-02', lines)
        self.assertIn('persist blue skoj-app:test-release', lines)
