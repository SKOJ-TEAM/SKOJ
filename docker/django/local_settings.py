import os


DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME', default='dmoj'),
        'USER': env('DB_USER', default='dmoj'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': 'db',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
            'sql_mode': 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION',
        },
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    },
}

CELERY_BROKER_URL = 'redis://redis:6379/0'
CELERY_RESULT_BACKEND = 'redis://redis:6379/0'

BRIDGED_JUDGE_ADDRESS = [('0.0.0.0', 9999)]
BRIDGED_DJANGO_ADDRESS = [('0.0.0.0', 9998)]
BRIDGED_DJANGO_CONNECT = ('bridge', 9998)

DMOJ_PROBLEM_DATA_ROOT = '/problems'
STATIC_ROOT = '/app/site/tmp/static'
MEDIA_ROOT = '/app/site/tmp/media'
MEDIA_URL = '/media/'
STATICFILES_DIRS = [DMOJ_RESOURCES]
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
DMOJ_SSL = 0

LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
DEFAULT_USER_TIME_ZONE = 'Asia/Seoul'

MOSS_API_KEY = env('MOSS_API_KEY', default='')
EMAIL_ACTIVATION_BLOCKED = True

LOGGING_ROOT = env('LOGGING_ROOT', default=os.path.join(BASE_DIR, 'tmp', 'logs'))
os.makedirs(LOGGING_ROOT, exist_ok=True)

CSRF_TRUSTED_ORIGINS = env.list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    default=[],
)
