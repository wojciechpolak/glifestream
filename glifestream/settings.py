"""
# Django settings for gLifestream project.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from glifestream.settings_magic_sso import (
    apply_magic_sso_defaults,
    get_bool,
    get_env,
    get_int,
    get_list,
    load_env_defaults,
    validate_magic_sso_settings,
    validate_secret_value,
)
from glifestream.settings_csp import csp_settings
from glifestream.worker.config import DEFAULT_WORKER_MAINTENANCE_JOBS

SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
BASE_DIR = SITE_ROOT
PROJECT_ROOT = os.path.abspath(os.path.join(SITE_ROOT, '..'))

LOAD_DOTENV = get_bool(os.environ, 'GLIFESTREAM_LOAD_DOTENV', default=True)
if LOAD_DOTENV:
    load_env_defaults(os.path.join(PROJECT_ROOT, '.env'))
ENV = os.environ
VALIDATE_SETTINGS_SECRETS = get_bool(
    ENV,
    'GLIFESTREAM_VALIDATE_SETTINGS_SECRETS',
    default=True,
)


def _project_path(value: str) -> str:
    if os.path.isabs(value):
        return value

    return os.path.abspath(os.path.join(PROJECT_ROOT, value))


def _default_worker_maintenance_jobs() -> list[dict[str, Any]]:
    return [dict(job) for job in DEFAULT_WORKER_MAINTENANCE_JOBS]


def _load_worker_maintenance_jobs(environ: Mapping[str, str]) -> list[dict[str, Any]]:
    raw = get_env(environ, 'WORKER_MAINTENANCE_JOBS')
    if raw is None:
        return _default_worker_maintenance_jobs()

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('WORKER_MAINTENANCE_JOBS must be valid JSON.') from exc

    if not isinstance(value, list):
        raise ValueError('WORKER_MAINTENANCE_JOBS must be a JSON array.')

    jobs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Each WORKER_MAINTENANCE_JOBS item must be an object.')
        jobs.append(dict(item))
    return jobs


RUN_DIR = _project_path(get_env(ENV, 'RUN_DIR', default='run') or 'run')
RUN_TEMPLATES_DIR = os.path.join(RUN_DIR, 'templates')
RUN_STATIC_DIR = os.path.join(RUN_DIR, 'static')

DEBUG = get_bool(ENV, 'DEBUG', 'APP_DEBUG', default=True)

ALLOWED_HOSTS = get_list(
    ENV,
    'ALLOWED_HOSTS',
    default=['localhost', '127.0.0.1'],
)

ADMINS = (
    (
        get_env(ENV, 'ADMIN_NAME', default='Admin') or 'Admin',
        get_env(ENV, 'ADMIN_EMAIL', default='admin@example.com') or 'admin@example.com',
    ),
)
MANAGERS = ADMINS

DATABASE_ENGINE = (
    get_env(ENV, 'DATABASE_ENGINE', default='django.db.backends.sqlite3')
    or 'django.db.backends.sqlite3'
)
DEFAULT_DATABASE_NAME = (
    os.path.join(RUN_DIR, 'db', 'dev.sqlite3')
    if DATABASE_ENGINE == 'django.db.backends.sqlite3'
    else ''
)
DATABASE_NAME = get_env(ENV, 'DATABASE_NAME', default=DEFAULT_DATABASE_NAME) or ''
if DATABASE_ENGINE == 'django.db.backends.sqlite3':
    DATABASE_NAME = _project_path(DATABASE_NAME)

# Start every SQLite transaction by taking the write lock. SQLite otherwise
# starts in DEFERRED mode, takes a read lock and upgrades it on the first
# write, and when two transactions have both read it fails one of them at
# once with "database is locked" rather than waiting for `timeout`. The
# worker claiming jobs and a "Run now" click do exactly that.
SQLITE_OPTIONS: dict[str, Any] = {
    'transaction_mode': 'IMMEDIATE',
    'timeout': get_int(ENV, 'DATABASE_TIMEOUT_SEC', default=30),
}
DATABASE_OPTIONS: dict[str, Any] = {}

DATABASES: dict[str, dict[str, Any]] = {
    'default': {
        'ENGINE': DATABASE_ENGINE,
        'OPTIONS': DATABASE_OPTIONS,
        'NAME': DATABASE_NAME,
        'USER': get_env(ENV, 'DATABASE_USER', default='') or '',
        'PASSWORD': get_env(ENV, 'DATABASE_PASSWORD', default='') or '',
        'HOST': get_env(ENV, 'DATABASE_HOST', default='') or '',
        'PORT': get_env(ENV, 'DATABASE_PORT', default='') or '',
    }
}

database_charset = get_env(ENV, 'DATABASE_CHARSET')
if database_charset:
    DATABASE_OPTIONS['charset'] = database_charset


def apply_sqlite_options(
    databases: dict[str, dict[str, Any]], options: dict[str, Any]
) -> None:
    """Give every SQLite database `options` it has not set for itself.

    Applied again after a local settings file has run, so a deployment that
    replaces DATABASES still gets them.
    """
    for config in databases.values():
        if config.get('ENGINE') != 'django.db.backends.sqlite3':
            continue
        config.setdefault('OPTIONS', {})
        for name, value in options.items():
            config['OPTIONS'].setdefault(name, value)


apply_sqlite_options(DATABASES, SQLITE_OPTIONS)

if not DEBUG and not DATABASES['default']['NAME']:
    raise ValueError('DATABASE_NAME must be configured when DEBUG is false.')

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

TIME_ZONE = get_env(ENV, 'TIME_ZONE', default='UTC') or 'UTC'
USE_TZ = True

LANGUAGE_CODE = get_env(ENV, 'LANGUAGE_CODE', default='en-us') or 'en-us'
USE_I18N = True

# Directories where Django looks for translation files.
LOCALE_PATHS = (os.path.join(PROJECT_ROOT, 'locale'),)

SESSION_COOKIE_NAME = 'gls-sid'
SESSION_ENGINE = (
    get_env(
        ENV,
        'SESSION_ENGINE',
        default='django.contrib.sessions.backends.file',
    )
    or 'django.contrib.sessions.backends.file'
)
SESSION_COOKIE_SECURE = get_bool(ENV, 'SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = get_bool(ENV, 'CSRF_COOKIE_SECURE', default=not DEBUG)

apply_magic_sso_defaults(globals(), ENV)

# Caching, see https://docs.djangoproject.com/en/dev/topics/cache/#topics-cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        # 'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '127.0.0.1:11211',
        'KEY_PREFIX': 'gls',
    },
}

# Site base URL (without a trailing slash).
BASE_URL = (
    get_env(ENV, 'BASE_URL', default='http://localhost:8000') or 'http://localhost:8000'
).rstrip('/')

# The URL where requests are redirected for login.
# For HTTPS use an absolute URL.
LOGIN_URL = get_env(ENV, 'LOGIN_URL', default='/login') or '/login'

WORKER_SOCKET = (
    get_env(ENV, 'WORKER_SOCKET', default='/tmp/glifestream-worker.sock')
    or '/tmp/glifestream-worker.sock'
)
WORKER_POOL_SIZE = get_int(ENV, 'WORKER_POOL_SIZE', default=4) or 4
FETCH_DEFAULT_INTERVAL_SEC = (
    get_int(ENV, 'FETCH_DEFAULT_INTERVAL_SEC', default=7200) or 7200
)
# Retry a temporary fetch failure after this many seconds, doubling on each
# further failure up to the service's interval.
FETCH_RETRY_BASE_SEC = get_int(ENV, 'FETCH_RETRY_BASE_SEC', default=60) or 60
# After a failure that retrying cannot fix, wait at least this long.
FETCH_TERMINAL_DELAY_SEC = (
    get_int(ENV, 'FETCH_TERMINAL_DELAY_SEC', default=24 * 3600) or 24 * 3600
)
# Give up waiting for a single service's fetch after this many seconds.
FETCH_JOB_TIMEOUT_SEC = get_int(ENV, 'FETCH_JOB_TIMEOUT_SEC', default=900) or 900
FETCH_FEED_MAX_BYTES = get_int(ENV, 'FETCH_FEED_MAX_BYTES', default=5 * 1024 * 1024)
FETCH_FEED_HTML_SNIFF_BYTES = get_int(
    ENV,
    'FETCH_FEED_HTML_SNIFF_BYTES',
    default=64 * 1024,
)
FETCH_MEDIA_MAX_BYTES = get_int(ENV, 'FETCH_MEDIA_MAX_BYTES', default=10 * 1024 * 1024)
# Image URLs come from remote content, so by default a media download may not
# reach loopback, private or link-local addresses.
FETCH_MEDIA_ALLOW_PRIVATE_ADDRESSES = get_bool(
    ENV, 'FETCH_MEDIA_ALLOW_PRIVATE_ADDRESSES', default=False
)
WORKER_MAINTENANCE_JOBS = _load_worker_maintenance_jobs(ENV)

SECRET_KEY = (
    get_env(ENV, 'SECRET_KEY', 'APP_SECRET_KEY', default='dev-secret-key')
    or 'dev-secret-key'
)

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'
    },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    # Below the cache middleware, so that a cached page keeps the header with
    # the nonce its markup was rendered with.
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'magic_sso_django.middleware.MagicSsoMiddleware',
    'glifestream.gauth.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            RUN_TEMPLATES_DIR,
            os.path.join(SITE_ROOT, 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csp',
            ],
        },
    },
]

ROOT_URLCONF = 'glifestream.urls'

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.messages',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.admin',
    'django.contrib.sites',
    'magic_sso_django',
    'pipeline',
    'glifestream.gls_staticfiles.GlsStaticFilesConfig',
    'glifestream.gauth',
    'glifestream.apis',
    'glifestream.stream',
    'glifestream.usettings',
)

SITE_ID = 1

MEDIA_ROOT = _project_path(
    get_env(ENV, 'RUN_DIR_MEDIA', 'MEDIA_ROOT', default='media') or 'media',
)
MEDIA_URL = get_env(ENV, 'MEDIA_URL', default='/media/') or '/media/'
FILE_UPLOAD_PERMISSIONS = 0o644

STATIC_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, 'static'))
STATIC_URL = get_env(ENV, 'STATIC_URL', default='/static/') or '/static/'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'pipeline.storage.PipelineManifestStorage',
    },
}
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'pipeline.finders.PipelineFinder',
)
STATICFILES_DIRS = (
    RUN_STATIC_DIR,
    os.path.join(SITE_ROOT, 'static'),
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.server': {
            'handlers': ['console'],
            'level': 'ERROR',
        },
    },
}

PIPELINE = {
    'DISABLE_WRAPPER': True,
    'JS_COMPRESSOR': None,
    'CSS_COMPRESSOR': None,
    'COMPILERS': ('glifestream.gls_staticfiles.GlsSASSCompiler',),
    'SASS_BINARY': get_env(ENV, 'SASS_BINARY', default='pysassc') or 'pysassc',
    'JAVASCRIPT': {
        'main': {
            # Built from frontend/ by `npm run build`.
            'source_filenames': ('js/dist/glifestream.js',),
            'output_filename': 'js/main.js',
            'extra_context': {'defer': True},
        },
        'editor': {
            # The rich editor (Tiptap), built from frontend/ with the page script.
            'source_filenames': ('js/dist/editor.js',),
            'output_filename': 'js/editor.js',
            'extra_context': {'defer': True},
        },
    },
    'STYLESHEETS': {
        'editor': {
            'source_filenames': ('js/dist/editor.css',),
            'output_filename': 'css/editor.css',
        },
        'default': {
            'source_filenames': (
                # The stylesheets of frontend/, such as PhotoSwipe's.
                'js/dist/glifestream.css',
                'themes/default/style.scss',
            ),
            'output_filename': 'themes/default/style.css',
        },
    },
}

#
# PWA
#

PWA_APP_NAME = 'gLifestream'
PWA_APP_SHORT_NAME = 'GLS'
PWA_APP_DESCRIPTION = 'Personal Lifestream'
PWA_APP_DISPLAY = 'standalone'
# The icons below are static files, named relative to STATIC_URL and
# resolved when a page is rendered, so they follow a STATIC_URL that
# settings_local.py or another settings module sets later. An absolute path
# or a full URL is used as it is.
PWA_APP_ICONS = [
    {'src': 'icon-192.png', 'sizes': '192x192'},
    {'src': 'icon-512.png', 'sizes': '512x512'},
    {
        'src': 'icon-maskable-512.png',
        'sizes': '512x512',
        'purpose': 'maskable',
    },
]

# A shortcut icon (favicon).
FAVICON = 'favicon.ico'

# The icon iOS shows for a page added to the home screen.
APPLE_TOUCH_ICON = 'apple-touch-icon.png'

THEMES = ('default',)

STREAM_TITLE = get_env(ENV, 'STREAM_TITLE', default='Stream') or 'Stream'
STREAM_TITLE_SUFFIX = (
    get_env(ENV, 'STREAM_TITLE_SUFFIX', default=' | Stream') or ' | Stream'
)
STREAM_DESCRIPTION = (
    get_env(ENV, 'STREAM_DESCRIPTION', default='A short description')
    or 'A short description'
)

# How many entries to display on one page.
ENTRIES_ON_PAGE = get_int(ENV, 'ENTRIES_ON_PAGE', default=30)

# Thumbnails format: JPEG, WEBP
APP_THUMBNAIL_FORMAT = get_env(ENV, 'APP_THUMBNAIL_FORMAT', default='WEBP') or 'WEBP'

# Webfeed settings.
FEED_AUTHOR_NAME = get_env(ENV, 'FEED_AUTHOR_NAME', default='YOUR NAME') or 'YOUR NAME'
FEED_AUTHOR_URI = (
    get_env(ENV, 'FEED_AUTHOR_URI', default=f'{BASE_URL}/') or f'{BASE_URL}/'
)
FEED_TAGURI = (
    get_env(ENV, 'FEED_TAGURI', default='tag:SITE-ID,YEAR:ID') or 'tag:SITE-ID,YEAR:ID'
)
FEED_ICON = (
    get_env(ENV, 'FEED_ICON', default='http://URL-TO-ICON') or 'http://URL-TO-ICON'
)

MAPS_ENGINE = get_env(ENV, 'MAPS_ENGINE', default='osm') or 'osm'

# Search functionality
SEARCH_ENABLE = get_bool(ENV, 'SEARCH_ENABLE', default=True)

WEBSUB_HUBS = tuple(
    get_list(
        ENV,
        'WEBSUB_HUBS',
        default=[
            'https://pubsubhubbub.appspot.com/',
            'https://websubhub.com/hub',
        ],
    )
)
WEBSUB_HTTPS_CALLBACK = get_bool(
    ENV,
    'WEBSUB_HTTPS_CALLBACK',
    default=True,
)

EMAIL2POST_CHECK = {
    'From': get_env(ENV, 'EMAIL2POST_FROM', default='John Smith') or 'John Smith',
}

# Content Security Policy: enforce, report-only (the default, until
# deployments have added nonces to their inline scripts) or off. See
# settings_csp.py;
# a settings_local.py that moves STATIC_URL to another site sets SECURE_CSP
# again.
CONTENT_SECURITY_POLICY = (
    get_env(ENV, 'CONTENT_SECURITY_POLICY', default='report-only') or 'report-only'
)
SECURE_CSP, SECURE_CSP_REPORT_ONLY = csp_settings(
    CONTENT_SECURITY_POLICY, static_url=STATIC_URL
)

SETTINGS_LOCAL_PATH = Path(__file__).with_name('settings_local.py')
LOAD_SETTINGS_LOCAL = get_bool(
    ENV,
    'GLIFESTREAM_ENABLE_SETTINGS_LOCAL',
    default=not get_bool(ENV, 'VRT', default=False),
)
if LOAD_SETTINGS_LOCAL and SETTINGS_LOCAL_PATH.is_file():
    exec(
        compile(
            SETTINGS_LOCAL_PATH.read_text(),
            str(SETTINGS_LOCAL_PATH),
            'exec',
        ),
        globals(),
    )
    apply_sqlite_options(DATABASES, SQLITE_OPTIONS)

if VALIDATE_SETTINGS_SECRETS:
    validate_secret_value(
        'SECRET_KEY',
        SECRET_KEY,
        debug=DEBUG,
        placeholders={'dev-secret-key'},
    )
    validate_magic_sso_settings(globals(), debug=DEBUG)
