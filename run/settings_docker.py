"""
# Django settings for gLifestream project (DOCKER VERSION).
"""

import os
SITE_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), '../glifestream/')
BASE_DIR = SITE_ROOT

DEBUG = os.getenv('APP_DEBUG') or False

ALLOWED_HOSTS = [
    os.getenv('VIRTUAL_HOST', ''),
    'localhost',
    'backend',
]

ADMINS = (
    ('Admin', 'example@example.org'),
)
MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(SITE_ROOT, '../run/db/dev.sqlite3'),
    }
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

# SESSION_ENGINE = 'django.contrib.sessions.backends.file'
# SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
# SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_COOKIE_NAME = 'glifestream_sid'
SESSION_COOKIE_AGE = 2419200

# Caching, see https://docs.djangoproject.com/en/dev/topics/cache/#topics-cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': 'memcached:11211',
        'KEY_PREFIX': 'gls',
    },
}

# Site base URL.
BASE_URL = os.getenv('VIRTUAL_PATH', 'http://localhost:8080').rstrip('/')
FORCE_SCRIPT_NAME = os.getenv('VIRTUAL_PATH', '/')

# The URL where requests are redirected for login.
# For HTTPS use an absolute URL.
LOGIN_URL = BASE_URL + '/login'

# Make this unique, and don't share it with anybody.
SECRET_KEY = os.getenv('APP_SECRET_KEY', 'YOUR-SECRET-KEY')

if SECRET_KEY == 'YOUR-SECRET-KEY':
    print('settings.SECRET_KEY must be long and unique!')

MIDDLEWARE = [
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
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

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.messages',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.admin',
    'django.contrib.sites',
    'pipeline',
    'glifestream.gls_staticfiles.GlsStaticFilesConfig',
    'glifestream.gauth',
    'glifestream.apis',
    'glifestream.stream',
    'glifestream.usettings',
    'glifestream.bookmarklet',
)

SITE_ID = 1

MEDIA_ROOT = os.path.join(SITE_ROOT, '../media')
MEDIA_URL = os.getenv('VIRTUAL_PATH', '/') + 'media/'

STATIC_ROOT = os.path.abspath(os.path.join(SITE_ROOT, '../static'))
STATIC_URL = os.getenv('VIRTUAL_PATH', '/') + 'static/'

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
            'level': 'ERROR'
        },
    }
}

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
        # 'custom': {
        #     'source_filenames': (
        #         'themes/default/jquery.fancybox.min.css',
        #         'themes/custom/style.scss',
        #     ),
        #     'output_filename': 'themes/custom/style.css',
        # },
    },
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
FAVICON = STATIC_URL + 'favicon.ico'

THEMES = (
    'default',
    # 'custom',
)

STREAM_TITLE = 'Stream'
STREAM_TITLE_SUFFIX = ' | Stream'
STREAM_DESCRIPTION = "Lifestream"

# How many entries to display on one page.
ENTRIES_ON_PAGE = 30

# Webfeed settings.
FEED_AUTHOR_NAME = 'Your Name'
FEED_AUTHOR_URI = 'http://localhost:8080/'
FEED_TAGURI = 'tag:glifestream,2022:stream'
FEED_ICON = 'http://localhost:8080/icon.jpg'

MAPS_ENGINE = 'osm'

# Search functionality
SEARCH_ENABLE = True
SEARCH_ENGINE = 'db'  # db, sphinx
SPHINX_INDEX_NAME = 'glifestream'

PSHB_HUBS = (BASE_URL,)
PSHB_HTTPS_CALLBACK = False

EMAIL2POST_CHECK = {
    'From': 'John Smith',
}
