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


def _load_worker_maintenance_jobs(
    environ: Mapping[str, str]
) -> list[dict[str, Any]]:
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

DATABASES: dict[str, dict[str, Any]] = {
    'default': {
        'ENGINE': DATABASE_ENGINE,
        'NAME': DATABASE_NAME,
        'USER': get_env(ENV, 'DATABASE_USER', default='') or '',
        'PASSWORD': get_env(ENV, 'DATABASE_PASSWORD', default='') or '',
        'HOST': get_env(ENV, 'DATABASE_HOST', default='') or '',
        'PORT': get_env(ENV, 'DATABASE_PORT', default='') or '',
    }
}

database_charset = get_env(ENV, 'DATABASE_CHARSET')
if database_charset:
    DATABASES['default']['OPTIONS'] = {'charset': database_charset}

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
WORKER_MAINTENANCE_JOBS = _load_worker_maintenance_jobs(ENV)

SECRET_KEY = (
    get_env(ENV, 'SECRET_KEY', 'APP_SECRET_KEY', default='dev-secret-key')
    or 'dev-secret-key'
)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
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
    'COMPILERS': ('pipeline.compilers.sass.SASSCompiler',),
    'SASS_BINARY': get_env(ENV, 'SASS_BINARY', default='pysassc') or 'pysassc',
    'JAVASCRIPT': {
        'main': {
            'source_filenames': (
                'js/jquery.min.js',
                'js/jquery.fancybox.min.js',
                'js/glifestream.js',
            ),
            'output_filename': 'js/main.js',
        },
        'quill': {
            'source_filenames': ('quill/quill.min.js',),
            'output_filename': 'js/quill.js',
        },
    },
    'STYLESHEETS': {
        'quill': {
            'source_filenames': ('quill/quill.snow.css',),
            'output_filename': 'css/quill.css',
        },
        'default': {
            'source_filenames': (
                'themes/default/jquery.fancybox.min.css',
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
PWA_APP_ICONS = [
    {'src': '/static/themes/default/icons/rss.png', 'sizes': '512x512'},
    {
        'src': '/static/themes/default/icons/rss_maskable.png',
        'sizes': '512x512',
        'purpose': 'maskable',
    },
]

# A shortcut icon URL (favicon).
FAVICON = STATIC_URL + 'favicon.ico'

THEMES = (
    'default',
)

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
SEARCH_ENGINE = get_env(ENV, 'SEARCH_ENGINE', default='db') or 'db'
SPHINX_INDEX_NAME = (
    get_env(ENV, 'SPHINX_INDEX_NAME', default='glifestream') or 'glifestream'
)

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

if VALIDATE_SETTINGS_SECRETS:
    validate_secret_value(
        'SECRET_KEY',
        SECRET_KEY,
        debug=DEBUG,
        placeholders={'dev-secret-key'},
    )
    validate_magic_sso_settings(globals(), debug=DEBUG)
