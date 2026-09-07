import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerApplicationConfigurationTest(unittest.TestCase):
    @classmethod
    def compose_config(cls, extra_environment=None, include_development_override=False):
        environment = os.environ.copy()
        environment['SKOJ_ENV_FILE'] = str(ROOT / '.env.docker.example')
        environment.update(extra_environment or {})
        command = [
            'docker', 'compose',
            '--env-file', str(ROOT / '.env.docker.example'),
            '--profile', 'deployment',
            '--profile', 'tools',
            '-f', str(ROOT / 'compose.yaml'),
        ]
        if include_development_override:
            command.extend(['-f', str(ROOT / 'compose.override.yaml')])
        command.extend(['config', '--format', 'json'])
        result = subprocess.run(
            command,
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
        for entry in ('site/.env', 'site/dmoj/local_settings.py', 'dmojsite', 'data', 'logs', '.deployment',
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
            "'/app/site/tmp/static/releases'",
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

        services = self.compose_config(include_development_override=True)['services']
        web = services['web-blue']
        settings_mount = next(
            volume for volume in web['volumes']
            if volume['target'] == '/app/site/dmoj/settings.py'
        )
        self.assertTrue(settings_mount['source'].endswith('/site/dmoj/settings.example.py'))
        self.assertTrue(settings_mount['read_only'])

        production_web = self.compose_config()['services']['web-blue']
        self.assertNotIn('/app/site', {
            volume['target'] for volume in production_web.get('volumes', [])
        })

    def test_example_environment_contains_no_real_secret(self):
        example = (ROOT / '.env.docker.example').read_text()
        self.assertIn('JUDGE_KEY=change-me', example)
        self.assertIn('JUDGE_KEY_2=change-me', example)
        self.assertIn('EMAIL_HOST_PASSWORD=change-me', example)
        self.assertNotIn('/Users/', example)

    def test_gmail_smtp_configuration_is_environment_driven(self):
        settings = (ROOT / 'docker/django/local_settings.py').read_text()
        example = (ROOT / '.env.docker.example').read_text()

        for value in (
            "EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')",
            "EMAIL_PORT = env.int('EMAIL_PORT', default=587)",
            "EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)",
            "EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)",
            "EMAIL_HOST_PASSWORD = ''.join(env('EMAIL_HOST_PASSWORD', default='').split())",
            "EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)",
        ):
            with self.subTest(value=value):
                self.assertIn(value, settings)

        self.assertNotIn('EMAIL_ACTIVATION_BLOCKED', settings)
        self.assertIn('EMAIL_HOST=smtp.gmail.com', example)
        self.assertIn('EMAIL_PORT=587', example)
        self.assertIn('EMAIL_USE_TLS=True', example)
        self.assertIn('EMAIL_USE_SSL=False', example)

    def test_compose_defines_application_services(self):
        config = self.compose_config()
        self.assertEqual(
            {
                'db', 'redis', 'init', 'web-blue', 'web-green',
                'celery-blue', 'celery-green', 'bridge', 'judge', 'judge-02',
            },
            set(config['services']),
        )

        for service in config['services'].values():
            self.assertNotIn('platform', service)

        for service, published in (('web-blue', '8001'), ('web-green', '8002')):
            with self.subTest(service=service):
                self.assertTrue(any(
                    port.get('host_ip') == '127.0.0.1'
                    and str(port.get('published')) == published
                    and int(port.get('target')) == 8000
                    for port in config['services'][service]['ports']
                ))

        db_ports = config['services']['db']['ports']
        self.assertTrue(any(
            port.get('host_ip') == '127.0.0.1'
            and str(port.get('published')) == '3306'
            and int(port.get('target')) == 3306
            for port in db_ports
        ))

        for internal_service in ('redis', 'bridge'):
            with self.subTest(service=internal_service):
                self.assertNotIn('ports', config['services'][internal_service])

        for django_service in ('web-blue', 'web-green', 'celery-blue', 'celery-green', 'bridge'):
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
            config['services']['web-blue']['command'],
        )

        dockerfile = (ROOT / 'dockerfile').read_text()
        self.assertIn(
            'CMD ["gunicorn", "dmoj.wsgi:application", "--bind", '
            '"0.0.0.0:8000", "--workers", "5"]',
            dockerfile,
        )

    def test_development_ports_can_be_isolated_from_production(self):
        config = self.compose_config({
            'DB_HOST_PORT': '13306',
            'BLUE_WEB_HOST_PORT': '18000',
            'GREEN_WEB_HOST_PORT': '18002',
        })

        expected_ports = {
            'db': '13306',
            'web-blue': '18000',
            'web-green': '18002',
        }
        for service, published in expected_ports.items():
            with self.subTest(service=service):
                self.assertTrue(any(
                    port.get('host_ip') == '127.0.0.1'
                    and str(port.get('published')) == published
                    for port in config['services'][service]['ports']
                ))

    def test_initialization_is_explicit_and_not_a_web_dependency(self):
        services = self.compose_config()['services']
        init = services['init']

        self.assertEqual(['python', 'manage.py', 'initialize_docker'], init['command'])
        self.assertEqual('no', init['restart'])
        self.assertEqual('service_healthy', init['depends_on']['db']['condition'])
        self.assertEqual('service_healthy', init['depends_on']['redis']['condition'])

        for service in ('web-blue', 'web-green', 'celery-blue', 'celery-green', 'bridge'):
            with self.subTest(service=service):
                self.assertNotIn('init', services[service]['depends_on'])

        command = (ROOT / 'site/judge/management/commands/initialize_docker.py').read_text()
        self.assertIn("call_command('migrate', interactive=False)", command)
        self.assertIn("call_command('compilemessages', verbosity=0)", command)
        self.assertIn("call_command('compilejsi18n', verbosity=0)", command)
        self.assertIn("call_command('collectstatic', interactive=False", command)
        self.assertLess(command.index("call_command('compilemessages'"), command.index("call_command('compilejsi18n'"))
        self.assertLess(command.index("call_command('compilejsi18n'"), command.index("call_command('collectstatic'"))
        for key in ('C', 'CPP17', 'JAVA', 'PY3'):
            with self.subTest(language=key):
                self.assertIn(f"'{key}':", command)
        self.assertIn('Language.objects.update_or_create(key=key, defaults=defaults)', command)
        self.assertIn("'CPP14': 'CPP17'", command)
        self.assertIn("'JAVA8': 'JAVA'", command)
        self.assertIn('Profile.objects.filter(language=legacy).update(language=replacement)', command)
        self.assertIn('allowed_languages.objects.filter(language_id=legacy.id).delete()', command)
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

        for service in ('init', 'web-blue', 'web-green', 'celery-blue', 'celery-green', 'bridge'):
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

                targets = {volume['target'] for volume in services[service]['volumes']}
                self.assertNotIn('/app/site', targets)
                self.assertNotIn('/app/site/dmoj/settings.py', targets)
                self.assertNotIn('/app/site/dmoj/local_settings.py', targets)

    def test_development_override_restores_source_mounts(self):
        services = self.compose_config(include_development_override=True)['services']
        for service in ('init', 'web-blue', 'web-green', 'celery-blue', 'celery-green', 'bridge'):
            with self.subTest(service=service):
                targets = {volume['target'] for volume in services[service]['volumes']}
                self.assertIn('/app/site', targets)
                self.assertIn('/app/site/dmoj/settings.py', targets)
                self.assertIn('/app/site/dmoj/local_settings.py', targets)

        web_environment = services['web-blue']['environment']
        self.assertEqual('True', web_environment['DEBUG'])
        self.assertEqual('False', web_environment['SECURE_SSL_REDIRECT'])
        self.assertEqual(
            ['python', 'manage.py', 'runserver', '0.0.0.0:8000'],
            services['web-blue']['command'],
        )

    def test_development_script_isolated_project_and_preserves_data(self):
        script = (ROOT / 'dev.sh').read_text()

        self.assertIn('PROJECT_NAME=${SKOJ_DEV_PROJECT_NAME:-skoj-dev}', script)
        self.assertIn('BLUE_WEB_HOST_PORT=${SKOJ_DEV_WEB_PORT:-18000}', script)
        self.assertIn('DB_HOST_PORT=${SKOJ_DEV_DB_PORT:-13306}', script)
        self.assertIn('$SCRIPT_ROOT/.development', script)
        self.assertIn('--project-name "$PROJECT_NAME"', script)
        self.assertIn('-f "$SCRIPT_ROOT/compose.override.yaml"', script)
        self.assertIn('compose down --remove-orphans', script)
        self.assertNotIn('down --volumes', script)

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
        self.assertIn('ARG JAVA17_IMAGE=eclipse-temurin:17-jdk', dockerfile)
        self.assertIn('FROM ${JAVA17_IMAGE} AS java17', dockerfile)
        self.assertIn(
            'COPY --from=java17 /opt/java/openjdk /usr/lib/jvm/java-17-openjdk-amd64',
            dockerfile,
        )
        self.assertIn(
            'ln -sf /usr/lib/jvm/java-17-openjdk-amd64/bin/java /usr/local/bin/java',
            dockerfile,
        )
        self.assertIn(
            'ln -sf /usr/lib/jvm/java-17-openjdk-amd64/bin/javac /usr/local/bin/javac',
            dockerfile,
        )
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
        self.assertEqual(
            'eclipse-temurin:17-jdk',
            judge_build['args']['JAVA17_IMAGE'],
        )
        overridden_build = self.compose_config({
            'DMOJ_RUNTIMES_IMAGE': 'example.invalid/dmoj-runtimes:custom',
        })['services']['judge']['build']
        self.assertEqual(
            'example.invalid/dmoj-runtimes:custom',
            overridden_build['args']['DMOJ_RUNTIMES_IMAGE'],
        )

    def test_compose_judge_is_internal_and_has_only_ptrace_capability(self):
        services = self.compose_config()['services']

        for service_name in ('judge', 'judge-02'):
            with self.subTest(service=service_name):
                judge = services[service_name]
                self.assertEqual(['SYS_PTRACE'], judge['cap_add'])
                self.assertNotIn('ports', judge)
                self.assertEqual('run', judge['command'][0])
                self.assertNotIn('--no-watchdog', judge['command'])
                self.assertNotIn('-p15001', judge['command'])
                self.assertNotIn('-s', judge['command'])

                problems = next(volume for volume in judge['volumes'] if volume['target'] == '/problems')
                self.assertTrue(problems['read_only'])

        self.assertEqual('skoj-judge-01', services['judge']['command'][-2])
        self.assertEqual('skoj-judge-02', services['judge-02']['command'][-2])

    def test_compose_judges_use_independent_configurable_credentials(self):
        services = self.compose_config({
            'JUDGE_NAME': 'custom-judge-01',
            'JUDGE_KEY': 'custom-key-01',
            'JUDGE_NAME_2': 'custom-judge-02',
            'JUDGE_KEY_2': 'custom-key-02',
        })['services']

        self.assertEqual(['custom-judge-01', 'custom-key-01'], services['judge']['command'][-2:])
        self.assertEqual(['custom-judge-02', 'custom-key-02'], services['judge-02']['command'][-2:])

    def test_docker_guide_contains_complete_local_setup_sequence(self):
        guide = (ROOT / 'DOCKER.md').read_text()
        for command in (
            'cp .env.docker.example .env.docker',
            'mkdir -p data/mariadb data/static logs problems',
            'docker compose --env-file .env.docker --profile tools run --rm init',
            'initialize_docker',
            'python manage.py createsuperuser',
            'python manage.py changepassword admin',
        ):
            with self.subTest(command=command):
                self.assertIn(command, guide)

    def test_deployment_scripts_and_nginx_routes_are_documented_and_safe(self):
        # 배포 진입점과 Nginx 전환 도구가 실패 즉시 중단하는 엄격 모드를 유지하는지 확인합니다.
        deploy = (ROOT / 'deploy.sh').read_text()
        restart = (ROOT / 'restart.sh').read_text()
        setup = (ROOT / 'setup-deployment.sh').read_text()
        switch = (ROOT / 'deploy/skoj-nginx-switch').read_text()
        nginx = (ROOT / 'deploy/nginx/skoj.conf').read_text()

        for script in (deploy, restart, setup, switch):
            self.assertIn('set -Eeuo pipefail', script)
        # 일반 무중단 배포가 migration을 직접 적용하지 않고 명확히 거부하는지 확인합니다.
        self.assertIn('pending database migrations detected', deploy)
        self.assertIn('showmigrations --plan', deploy)
        self.assertIn('compilejsi18n --verbosity 0', deploy)
        self.assertIn('platform_preflight', deploy)
        self.assertIn('platform_preflight', restart)
        # SHA 인자를 생략해도 현재 HEAD를 사용하며 기존 명시 SHA와 rollback을 유지합니다.
        for script in (deploy, restart):
            self.assertIn('[[ $# -le 1 ]]', script)
            self.assertIn('${1:-$(git -C "$SCRIPT_ROOT" rev-parse HEAD)}', script)
            self.assertIn('validate_release "$requested"', script)
        self.assertIn('if [[ "$requested" == rollback ]]', deploy)
        library = (ROOT / 'deploy/lib.sh').read_text()
        self.assertIn('MIN_FREE_KB', library)
        self.assertIn('compose config --quiet', library)
        self.assertIn('for service in db redis', library)
        self.assertNotIn('manage.py migrate', deploy)
        # 중단 배포는 검증 가능한 DB 백업 후 cache DB 1만 비우며 전체 stack을 내리지 않습니다.
        self.assertIn('mariadb-dump --single-transaction', restart)
        self.assertIn('redis-cli -n 1 FLUSHDB', restart)
        self.assertNotIn('docker compose down', restart)
        # Nginx는 허용된 route만 검사 후 reload하고 Blue/Green 고정 포트를 사용해야 합니다.
        self.assertIn('nginx -t', switch)
        self.assertIn('systemctl reload nginx', switch)
        self.assertIn('blue|green|maintenance|legacy', switch)
        self.assertIn('include /etc/nginx/skoj/active.conf', nginx)
        self.assertIn('127.0.0.1:8001', (ROOT / 'deploy/nginx/routes/blue.conf').read_text())
        self.assertIn('127.0.0.1:8002', (ROOT / 'deploy/nginx/routes/green.conf').read_text())
