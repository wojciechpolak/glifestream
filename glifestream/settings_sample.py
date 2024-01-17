"""
# Django settings for gLifestream project.
"""

import os
SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
BASE_DIR = SITE_ROOT

DEBUG = True

ALLOWED_HOSTS = [
    'localhost'
]

ADMINS = (
    ('Your Name', 'your@email'),
)
MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(SITE_ROOT, '../run/db/dev.sqlite3'),
    },
    # 'default': {
    #     'ENGINE': 'django.db.backends.mysql',
    #     'OPTIONS': {'charset': 'utf8mb4'},
    #     'NAME': 'glifestream',
    #     'USER': 'user',
    #     'PASSWORD': 'pass',
    #     'HOST': '',
    #     'PORT': '',
    # },
    # 'sphinx': {
    #     'ENGINE': 'django.db.backends.mysql',
    #     'NAME': '',
    #     'USER': '',
    #     'PASSWORD': '',
    #     'HOST': '127.0.0.1',
    #     'PORT': '9306',
    # },
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

TIME_ZONE = 'UTC'
USE_TZ = True

LANGUAGE_CODE = 'en-us'
USE_I18N = True

# Directories where Django looks for translation files.
LOCALE_PATHS = (
    os.path.join(SITE_ROOT, '../locale'),
)

SESSION_COOKIE_NAME = 'gls-sid'
SESSION_ENGINE = 'django.contrib.sessions.backends.file'

# Caching, see http://docs.djangoproject.com/en/dev/topics/cache/#topics-cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '127.0.0.1:11211',
        'KEY_PREFIX': 'gls',
    },
}

# Site base URL (without a trailing slash).
# For example:
# BASE_URL = 'https://wojciechpolak.org/stream'
#
BASE_URL = 'http://localhost:8000'

# The URL where requests are redirected for login.
# For HTTPS use an absolute URL.
LOGIN_URL = '/login'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'YOUR-SECRET-KEY'

assert SECRET_KEY != 'YOUR-SECRET-KEY', 'SECRET_KEY must be long and unique.'

MIDDLEWARE = [
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(SITE_ROOT, '../run/templates'),
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

WSGI_APPLICATION = 'glifestream.wsgi.application'

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.sites',
    'pipeline',
    'glifestream.gls_staticfiles.GlsStaticFilesConfig',
    'glifestream.gauth',
    'glifestream.apis',
    'glifestream.stream',
    'glifestream.usettings',
)

SITE_ID = 1

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = os.path.abspath(os.path.join(SITE_ROOT, '../media'))

# URL that handles the media served from MEDIA_ROOT.
# Make sure to use a trailing slash.
# Examples: "http://media.lawrence.com", "http://example.com/media/"
# Setting an absolute URL is recommended in a production use.
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT = os.path.abspath(os.path.join(SITE_ROOT, '../static'))

# URL prefix for admin media. Make sure to use a trailing slash.
# Examples: "http://foo.com/media/", "/media/".
STATIC_URL = '/static/'

STATICFILES_STORAGE = 'pipeline.storage.PipelineManifestStorage'
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'pipeline.finders.PipelineFinder',
)
STATICFILES_DIRS = (
    os.path.join(SITE_ROOT, '../run/static'),
    os.path.join(SITE_ROOT, 'static'),
)

PIPELINE = {
    'DISABLE_WRAPPER': True,
    'JS_COMPRESSOR': None,
    'CSS_COMPRESSOR': None,
    'COMPILERS': ('pipeline.compilers.sass.SASSCompiler',),
    'SASS_BINARY': 'pysassc',
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
            'source_filenames': (
                'quill/quill.min.js',
            ),
            'output_filename': 'js/quill.js',
        },
    },
    'STYLESHEETS': {
        'quill': {
            'source_filenames': (
                'quill/quill.snow.css',
            ),
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

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

#
# PWA
#

PWA_APP_NAME = 'gLifestream'
PWA_APP_SHORT_NAME = 'GLS'
PWA_APP_DESCRIPTION = "Personal Lifestream"
PWA_APP_DISPLAY = 'standalone'
PWA_APP_ICONS = [
    {
        'src': '/static/themes/default/icons/rss.png',
        'sizes': '512x512'
    },
    {
        'src': '/static/themes/default/icons/rss_maskable.png',
        'sizes': '512x512',
        'purpose': 'maskable'
    }
]

# A shortcut icon URL (favicon).
FAVICON = '/favicon.ico'

THEMES = (
    'default',
)

STREAM_TITLE = 'Stream title'
STREAM_TITLE_SUFFIX = ' | Lifestream'
STREAM_DESCRIPTION = "A short description"

# How many entries to display on one page.
ENTRIES_ON_PAGE = 30

# Thumbnails format: JPEG, WEBP
APP_THUMBNAIL_FORMAT = 'WEBP'

# Webfeed settings.
FEED_AUTHOR_NAME = 'YOUR NAME'
FEED_TAGURI = 'tag:SITE-ID,YEAR:ID'
FEED_ICON = 'http://URL-TO-ICON'

# Embedded maps
MAPS_ENGINE = 'osm'

# Search functionality
SEARCH_ENABLE = True
SEARCH_ENGINE = 'db'  # db, sphinx
SPHINX_INDEX_NAME = 'glifestream'

# WebSub - Hubs to ping (use empty tuple () to disable)
WEBSUB_HUBS = ('https://pubsubhubbub.appspot.com/',)
WEBSUB_HTTPS_CALLBACK = True

# Email2Post settings
EMAIL2POST_CHECK = {
    'From': 'John Smith',
}
