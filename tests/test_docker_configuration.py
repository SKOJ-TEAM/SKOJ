import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerApplicationConfigurationTest(unittest.TestCase):
    @classmethod
    def compose_config(cls, extra_environment=None):
        environment = os.environ.copy()
        environment['SKOJ_ENV_FILE'] = str(ROOT / '.env.docker.example')
        environment.update(extra_environment or {})
        result = subprocess.run(
            [
                'docker', 'compose',
                '--env-file', str(ROOT / '.env.docker.example'),
                '-f', str(ROOT / 'compose.yaml'),
                'config', '--format', 'json',
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_application_image_is_ubuntu_2204(self):
        dockerfile = (ROOT / 'dockerfile').read_text()
        self.assertIn('FROM ubuntu:22.04', dockerfile)
        self.assertIn('python3.10', dockerfile)
        self.assertIn("-name '*.sources'", dockerfile)
        self.assertIn("sed -i 's|http://|https://|g' {} +", dockerfile)
        self.assertIn('Acquire::Retries=5', dockerfile)
        ca_install = 'apt-get install -y --no-install-recommends ca-certificates'
        self.assertIn(ca_install, dockerfile)
        self.assertLess(dockerfile.index(ca_install), dockerfile.index("sed -i 's|http://|https://|g'"))
        self.assertIn('pip install --no-cache-dir -r /tmp/requirements.txt', dockerfile)

    def test_build_context_excludes_local_secrets_and_virtualenv(self):
        dockerignore = (ROOT / '.dockerignore').read_text()
        for entry in ('site/.env', 'site/dmoj/local_settings.py', 'dmojsite', 'data', 'logs',
                      'site/judge/configs'):
            with self.subTest(entry=entry):
                self.assertIn(entry, dockerignore)

    def test_docker_settings_use_service_names_and_linux_paths(self):
        settings = (ROOT / 'docker/django/local_settings.py').read_text()
        for value in (
            "'HOST': 'db'",
            'redis://redis:6379/1',
            "('bridge', 9998)",
            "'/problems'",
            "'/app/site/tmp/static'",
        ):
            with self.subTest(value=value):
                self.assertIn(value, settings)
        self.assertNotIn('/Users/', settings)

    def test_docker_uses_tracked_example_as_base_settings(self):
        dockerfile = (ROOT / 'dockerfile').read_text()
        self.assertIn(
            'COPY site/dmoj/settings.example.py /app/site/dmoj/settings.py',
            dockerfile,
        )

        web = self.compose_config()['services']['web']
        settings_mount = next(
            volume for volume in web['volumes']
            if volume['target'] == '/app/site/dmoj/settings.py'
        )
        self.assertTrue(settings_mount['source'].endswith('/site/dmoj/settings.example.py'))
        self.assertTrue(settings_mount['read_only'])

    def test_example_environment_contains_no_real_secret(self):
        example = (ROOT / '.env.docker.example').read_text()
        self.assertIn('JUDGE_KEY=change-me', example)
        self.assertNotIn('/Users/', example)

    def test_compose_defines_application_services(self):
        config = self.compose_config()
        self.assertEqual({'db', 'redis', 'init', 'web', 'celery', 'bridge', 'judge'}, set(config['services']))

        for service in config['services'].values():
            self.assertNotIn('platform', service)

        web_ports = config['services']['web']['ports']
        self.assertTrue(any(
            port.get('host_ip') == '127.0.0.1'
            and str(port.get('published')) == '8000'
            and int(port.get('target')) == 8000
            for port in web_ports
        ))

        for internal_service in ('db', 'redis', 'bridge'):
            with self.subTest(service=internal_service):
                self.assertNotIn('ports', config['services'][internal_service])

        for django_service in ('web', 'celery', 'bridge'):
            with self.subTest(service=django_service):
                self.assertEqual(
                    'dmoj.settings',
                    config['services'][django_service]['environment']['DJANGO_SETTINGS_MODULE'],
                )

        self.assertEqual(
            [
                'gunicorn', 'dmoj.wsgi:application',
                '--bind', '0.0.0.0:8000',
                '--workers', '5',
            ],
            config['services']['web']['command'],
        )

        dockerfile = (ROOT / 'dockerfile').read_text()
        self.assertIn(
            'CMD ["gunicorn", "dmoj.wsgi:application", "--bind", '
            '"0.0.0.0:8000", "--workers", "5"]',
            dockerfile,
        )

    def test_application_services_wait_for_idempotent_initialization(self):
        services = self.compose_config()['services']
        init = services['init']

        self.assertEqual(['python', 'manage.py', 'initialize_docker'], init['command'])
        self.assertEqual('no', init['restart'])
        self.assertEqual('service_healthy', init['depends_on']['db']['condition'])
        self.assertEqual('service_healthy', init['depends_on']['redis']['condition'])

        for service in ('web', 'celery', 'bridge'):
            with self.subTest(service=service):
                self.assertEqual(
                    'service_completed_successfully',
                    services[service]['depends_on']['init']['condition'],
                )

        command = (ROOT / 'site/judge/management/commands/initialize_docker.py').read_text()
        self.assertIn("call_command('migrate', interactive=False)", command)
        self.assertIn("call_command('compilemessages', verbosity=0)", command)
        self.assertIn("call_command('compilejsi18n', verbosity=0)", command)
        self.assertIn("call_command('collectstatic', interactive=False", command)
        self.assertLess(command.index("call_command('compilemessages'"), command.index("call_command('compilejsi18n'"))
        self.assertLess(command.index("call_command('compilejsi18n'"), command.index("call_command('collectstatic'"))
        for key in ('C', 'CPP14', 'JAVA8', 'PY3'):
            with self.subTest(language=key):
                self.assertIn(f"'{key}':", command)
        self.assertIn('Language.objects.update_or_create(key=key, defaults=defaults)', command)
        self.assertIn('User.objects.filter(is_superuser=True).exists()', command)
        self.assertIn("DJANGO_SUPERUSER_USERNAME", command)
        self.assertIn("DJANGO_SUPERUSER_PASSWORD", command)
        self.assertIn('User.objects.create_superuser(', command)
        self.assertLess(
            command.index('User.objects.filter(is_superuser=True).exists()'),
            command.index("os.environ.get('DJANGO_SUPERUSER_PASSWORD'"),
        )
        self.assertIn('Judge.objects.update_or_create(', command)
        self.assertNotIn("f'{judge_key}'", command)

    def test_language_admin_preserves_executor_identifier(self):
        admin = (ROOT / 'site/judge/admin/runtime.py').read_text()
        self.assertNotIn('obj.key = obj.name', admin)

    def test_persistent_application_data_uses_host_bind_mounts(self):
        services = self.compose_config()['services']

        db_data = next(volume for volume in services['db']['volumes'] if volume['target'] == '/var/lib/mysql')
        self.assertEqual('bind', db_data['type'])
        self.assertTrue(db_data['source'].endswith('/data/mariadb'))

        for service in ('init', 'web', 'celery', 'bridge'):
            with self.subTest(service=service):
                static = next(
                    volume for volume in services[service]['volumes']
                    if volume['target'] == '/app/site/tmp/static'
                )
                self.assertEqual('bind', static['type'])
                self.assertTrue(static['source'].endswith('/data/static'))

                logs = next(
                    volume for volume in services[service]['volumes']
                    if volume['target'] == '/app/site/tmp/logs'
                )
                self.assertEqual('bind', logs['type'])
                self.assertTrue(logs['source'].endswith('/logs'))
                self.assertEqual('/app/site/tmp/logs', services[service]['environment']['LOGGING_ROOT'])

    def test_security_settings_are_configurable_from_environment(self):
        settings = (ROOT / 'docker/django/local_settings.py').read_text()
        example = (ROOT / '.env.docker.example').read_text()
        for name in (
            'DEBUG',
            'SECURE_SSL_REDIRECT',
            'SECURE_HSTS_INCLUDE_SUBDOMAINS',
            'SECURE_HSTS_PRELOAD',
            'SESSION_COOKIE_SECURE',
            'CSRF_COOKIE_SECURE',
        ):
            with self.subTest(name=name):
                self.assertIn(f"env.bool('{name}'", settings)
                self.assertIn(f'{name}=False', example)

    def test_example_environment_contains_superuser_bootstrap_values(self):
        example = (ROOT / '.env.docker.example').read_text()
        self.assertIn('DJANGO_SUPERUSER_USERNAME=admin', example)
        self.assertIn('DJANGO_SUPERUSER_PASSWORD=change-me', example)
        self.assertIn('DJANGO_SUPERUSER_EMAIL=admin@example.com', example)

    def test_judge_uses_configurable_multi_arch_runtime_without_embedded_secret(self):
        dockerfile = (ROOT / 'docker/judge/Dockerfile').read_text()
        config = (ROOT / 'docker/judge/judge.yml').read_text()
        self.assertIn('ARG DMOJ_RUNTIMES_IMAGE=dmoj/runtimes-tier1:latest', dockerfile)
        self.assertIn('FROM ${DMOJ_RUNTIMES_IMAGE}', dockerfile)
        self.assertIn("-name '*.sources'", dockerfile)
        self.assertIn("sed -i 's|http://|https://|g' {} +", dockerfile)
        self.assertIn('Acquire::Retries=5', dockerfile)
        self.assertIn('git fetch --depth 1 origin "${DMOJ_JUDGE_COMMIT}"', dockerfile)
        self.assertNotIn('github.com/DMOJ/judge-server/archive', dockerfile)
        self.assertIn('/problems/*', config)
        self.assertNotIn('key:', config)
        self.assertNotIn('aarch64', config)
        self.assertNotIn('arm64', config)
        self.assertNotIn('x86_64', config)

        judge_build = self.compose_config()['services']['judge']['build']
        self.assertEqual(
            'dmoj/runtimes-tier1:latest',
            judge_build['args']['DMOJ_RUNTIMES_IMAGE'],
        )
        overridden_build = self.compose_config({
            'DMOJ_RUNTIMES_IMAGE': 'example.invalid/dmoj-runtimes:custom',
        })['services']['judge']['build']
        self.assertEqual(
            'example.invalid/dmoj-runtimes:custom',
            overridden_build['args']['DMOJ_RUNTIMES_IMAGE'],
        )

    def test_compose_judge_is_internal_and_has_only_ptrace_capability(self):
        judge = self.compose_config()['services']['judge']
        self.assertEqual(['SYS_PTRACE'], judge['cap_add'])
        self.assertNotIn('ports', judge)
        self.assertEqual('run', judge['command'][0])
        self.assertNotIn('--no-watchdog', judge['command'])
        self.assertNotIn('-p15001', judge['command'])
        self.assertNotIn('-s', judge['command'])

    def test_docker_guide_contains_complete_local_setup_sequence(self):
        guide = (ROOT / 'DOCKER.md').read_text()
        for command in (
            'cp .env.docker.example .env.docker',
            'mkdir -p data/mariadb data/static logs problems',
            'docker compose --env-file .env.docker up -d --build',
            'initialize_docker',
            'python manage.py createsuperuser',
            'python manage.py changepassword admin',
        ):
            with self.subTest(command=command):
                self.assertIn(command, guide)
