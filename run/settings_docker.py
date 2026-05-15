"""
# Django settings for gLifestream project (DOCKER VERSION).
"""

from __future__ import annotations

import os

from glifestream.settings import *  # noqa: F403
from glifestream.settings import _load_worker_maintenance_jobs
from glifestream.settings_magic_sso import (  # noqa: F401
    get_bool,
    get_env,
    get_int,
    validate_magic_sso_settings,
    validate_secret_value,
)

ENV = os.environ


def _docker_path_prefix() -> str:
    value = get_env(ENV, 'FORCE_SCRIPT_NAME', 'VIRTUAL_PATH', default='/') or '/'
    if value == '/':
        return value

    return value.rstrip('/') + '/'


DEBUG = get_bool(ENV, 'DEBUG', 'APP_DEBUG', default=False)

docker_host = get_env(ENV, 'VIRTUAL_HOST')
ALLOWED_HOSTS = list(  # noqa: F405
    dict.fromkeys(
        [
            *ALLOWED_HOSTS,  # noqa: F405
            *([docker_host] if docker_host else []),
            'localhost',
            'backend',
        ]
    )
)

SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_COOKIE_AGE = 30 * 86400  # 30 days
SESSION_COOKIE_SECURE = get_bool(ENV, 'SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = get_bool(ENV, 'CSRF_COOKIE_SECURE', default=True)

# Caching, see https://docs.djangoproject.com/en/dev/topics/cache/#topics-cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': 'memcached:11211',
        'KEY_PREFIX': 'gls',
    },
}

FORCE_SCRIPT_NAME = _docker_path_prefix().rstrip('/') or '/'
path_prefix = _docker_path_prefix()
default_base_url = (
    f'http://localhost:8080{path_prefix.rstrip("/")}'
    if path_prefix != '/'
    else 'http://localhost:8080'
)
BASE_URL = (
    get_env(ENV, 'BASE_URL', default=default_base_url) or default_base_url
).rstrip('/')
LOGIN_URL = BASE_URL + '/login'

MEDIA_URL = path_prefix + 'media/'
STATIC_URL = path_prefix + 'static/'
FAVICON = STATIC_URL + 'favicon.ico'

WORKER_SOCKET = (
    get_env(ENV, 'WORKER_SOCKET', default=WORKER_SOCKET)  # noqa: F405
    or WORKER_SOCKET  # noqa: F405
)
WORKER_POOL_SIZE = (
    get_int(ENV, 'WORKER_POOL_SIZE', default=WORKER_POOL_SIZE)  # noqa: F405
    or WORKER_POOL_SIZE  # noqa: F405
)
FETCH_DEFAULT_INTERVAL_SEC = (
    get_int(
        ENV,
        'FETCH_DEFAULT_INTERVAL_SEC',
        default=FETCH_DEFAULT_INTERVAL_SEC,  # noqa: F405
    )
    or FETCH_DEFAULT_INTERVAL_SEC  # noqa: F405
)
WORKER_MAINTENANCE_JOBS = _load_worker_maintenance_jobs(ENV)

SECRET_KEY = (
    get_env(ENV, 'SECRET_KEY', 'APP_SECRET_KEY', default='YOUR-SECRET-KEY')
    or 'YOUR-SECRET-KEY'
)
if VALIDATE_SETTINGS_SECRETS:  # noqa: F405
    validate_secret_value('SECRET_KEY', SECRET_KEY, debug=DEBUG)
    validate_magic_sso_settings(globals(), debug=DEBUG)
