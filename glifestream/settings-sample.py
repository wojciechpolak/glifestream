# Django settings for gLifestream project.

import os
SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
BASE_DIR = SITE_ROOT

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ALLOWED_HOSTS = [
    'localhost'
]

ADMINS = (
    ('Your Name', 'your@email'),
)
MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'glifestream',
        'USER': 'user',
        'PASSWORD': 'pass',
        'HOST': '',
        'PORT': '',
    },
    'sphinx': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '',
        'USER': '',
        'PASSWORD': '',
        'HOST': '127.0.0.1',
        'PORT': '9306',
    },
}

TIME_ZONE = 'UTC'
LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_L10N = False

# Directories where Django looks for translation files.
LOCALE_PATHS = (
    os.path.join(SITE_ROOT, '../locale'),
)

SESSION_COOKIE_NAME = 'glifestream_sid'
SESSION_ENGINE = 'django.contrib.sessions.backends.file'

# Caching, see http://docs.djangoproject.com/en/dev/topics/cache/#topics-cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
        'KEY_PREFIX': 'gls',
    },
}

# Site base URL (without a trailing slash).
# For example:
# BASE_URL = 'http://wojciechpolak.org/stream'
#
BASE_URL = 'http://localhost:8000'

# The URL where requests are redirected for login.
# For HTTPS use an absolute URL.
LOGIN_URL = '/login'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'YOUR-SECRET-KEY'

MIDDLEWARE_CLASSES = (
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
)

ROOT_URLCONF = 'glifestream.urls'

WSGI_APPLICATION = 'glifestream.wsgi.application'

TEMPLATE_DIRS = (
    os.path.join(SITE_ROOT, 'templates'),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'pipeline',
    'glifestream.gauth',
    'glifestream.apis',
    'glifestream.stream',
    'glifestream.usettings',
    'glifestream.bookmarklet',
)

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

STATICFILES_STORAGE = 'pipeline.storage.PipelineCachedStorage'
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'pipeline.finders.CachedFileFinder',
    'pipeline.finders.PipelineFinder',
)
STATICFILES_DIRS = (
    os.path.join(SITE_ROOT, 'static'),
)

PIPELINE_DISABLE_WRAPPER = True
PIPELINE_JS_COMPRESSOR = None
PIPELINE_CSS_COMPRESSOR = None

PIPELINE_JS = {
    'main': {
        'source_filenames': (
            'js/jquery.js',
            'js/glifestream.js',
        ),
        'output_filename': 'js/main.js',
    },
    'tinymce': {
        'source_filenames': (
            'js/tinymce/tinymce.min.js',
        ),
        'output_filename': 'js/tinymce.js',
    }
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
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

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

# Webfeed settings.
FEED_AUTHOR_NAME = 'YOUR NAME'
FEED_TAGURI = 'tag:SITE-ID,YEAR:ID'
FEED_ICON = 'http://URL-TO-ICON'

# Embedded maps
MAPS_ENGINE = 'google'

# Search functionality
SEARCH_ENABLE = True
SEARCH_ENGINE = 'sphinx'  # db, sphinx
SPHINX_INDEX_NAME = 'glifestream'

# PubSubHubbub - Hubs to ping (use empty tuple () to disable)
PSHB_HUBS = ('https://pubsubhubbub.appspot.com/',)
PSHB_HTTPS_CALLBACK = True

# Facebook Connect
FACEBOOK_APP_ID = 'YOUR-APP-ID'  # Leave empty to disable FB.
FACEBOOK_APP_SECRET = 'YOUR-APP-SECRET'
FACEBOOK_USER_ID = 'YOUR-FB-USERID'  # Number

# Email2Post settings
EMAIL2POST_CHECK = {
    'From': 'John Smith',
}
