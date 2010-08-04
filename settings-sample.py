# Django settings for gLifestream project.

import os
SITE_ROOT = os.path.dirname (os.path.realpath (__file__))

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    ('Your Name', 'your@email'),
)
MANAGERS = ADMINS

DATABASE_ENGINE   = 'mysql'
DATABASE_NAME     = 'glifestream'
DATABASE_USER     = 'USER'
DATABASE_PASSWORD = 'PASS'
DATABASE_HOST     = ''
DATABASE_PORT     = ''

TIME_ZONE = 'Europe/Warsaw'
LANGUAGE_CODE = 'en-us'
SITE_ID = 1
USE_I18N = True

SESSION_COOKIE_NAME = 'glifestream_sid'
SESSION_ENGINE = 'django.contrib.sessions.backends.file'

# Caching, see http://docs.djangoproject.com/en/dev/topics/cache/#topics-cache
CACHE_BACKEND = 'memcached://127.0.0.1:11211/'
CACHE_MIDDLEWARE_ANONYMOUS_ONLY = True

# Site base URL (without a trailing slash).
# For example:
# BASE_URL = 'http://wojciechpolak.org/stream'
#
BASE_URL = 'http://localhost:8000'

# The URL where requests are redirected for login.
# For HTTPS use an absolute URL.
LOGIN_URL = '/login'

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = os.path.join (SITE_ROOT, 'static')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
# Setting an absolute URL is recommended in a production use.
MEDIA_URL = '/static'

# URL prefix for admin media. Make sure to use a trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/admin_static/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'YOUR-SECRET-KEY'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
)

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

TEMPLATE_DIRS = (
    os.path.join (SITE_ROOT, 'templates'),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.admin',
    'glifestream.gauth',
    'glifestream.apis',
    'glifestream.stream',
    'glifestream.usettings',
    'glifestream.bookmarklet',
)

# A shortcut icon URL (favicon).
FAVICON = '/favicon.ico'

THEMES = (
    'default',
)

STREAM_TITLE = 'Stream title'
STREAM_DESCRIPTION = "A short description"

# How many entries to display on one page.
ENTRIES_ON_PAGE = 30

# Webfeed settings.
FEED_AUTHOR_NAME = 'YOUR NAME'
FEED_TAGURI = 'tag:SITE-ID,YEAR:ID'
FEED_ICON   = 'http://URL-TO-ICON'

# Embedded maps
MAPS_ENGINE = 'google'

# Search functionality
SEARCH_ENABLE = True
SEARCH_ENGINE = 'sphinx' # db, sphinx

SPHINX_API_VERSION = 0x116 # version 0.9.9
SPHINX_SERVER = 'localhost'
SPHINX_PORT = 9312
SPHINX_INDEX_NAME = 'glifestream'

# PubSubHubbub - Hubs to ping (use empty tuple () to disable)
PSHB_HUBS = ('https://pubsubhubbub.appspot.com/',)
PSHB_HTTPS_CALLBACK = True

# Facebook Connect
FACEBOOK_APP_ID = 'YOUR-APP-ID' # Leave empty to disable FB.
FACEBOOK_APP_SECRET = 'YOUR-APP-SECRET'
FACEBOOK_USER_ID = 'YOUR-FB-USERID' # Number

# Email2Post settings
EMAIL2POST_CHECK = {
    'From': 'John Smith',
}
