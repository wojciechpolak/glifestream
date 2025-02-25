"""
#  gLifestream Copyright (C) 2010, 2011, 2015 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from django.conf import settings
from django.utils.translation import gettext as _

from glifestream.apis.base import BaseService
from glifestream.gauth import models
from glifestream.stream.models import Service

try:
    from requests_oauthlib import OAuth1Session
except ImportError:
    OAuth1Session = None

AGENT = 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL


class OAuth1Client:

    def __init__(self, service: Service, api: BaseService, identifier=None,
                 secret=None, callback_url=None):
        if not OAuth1Session:
            raise Exception('requests-oauthlib is required.')

        try:
            self.db = models.OAuthClient.objects.get(service=service)
        except models.OAuthClient.DoesNotExist:
            self.db = models.OAuthClient(service=service)
            if identifier and secret:
                self.db.identifier = identifier
                self.db.secret = secret

        self.callback_url = callback_url
        self.request_token_url = getattr(api, 'OAUTH_REQUEST_TOKEN_URL', None)
        self.authorize_url = getattr(api, 'OAUTH_AUTHORIZE_URL', None)
        self.access_token_url = getattr(api, 'OAUTH_ACCESS_TOKEN_URL', None)
        self.verifier = None

        self.consumer = OAuth1Session(
            client_key=self.db.identifier,
            client_secret=self.db.secret,
            resource_owner_key=self.db.token or None,
            resource_owner_secret=self.db.token_secret or None,
            verifier=self.verifier,
            callback_uri=self.callback_url)
        self.consumer.headers['User-Agent'] = AGENT

    def save(self):
        self.db.save()

    def set_urls(self, request_token_url=None, authorize_url=None,
                 access_token_url=None):
        self.db.request_token_url = request_token_url
        self.db.authorize_url = authorize_url
        self.db.access_token_url = access_token_url
        self.request_token_url = request_token_url
        self.authorize_url = authorize_url
        self.access_token_url = access_token_url

    def reset(self):
        self.db.phase = 0
        self.db.token = None
        self.db.token_secret = None
        self.verifier = None

    def get_request_token(self):
        if not self.request_token_url:
            raise Exception(_('Request token URL not set.'))

        res = self.consumer.fetch_request_token(self.request_token_url)
        if 'oauth_token' in res and 'oauth_token_secret' in res:
            self.db.phase = 1
            self.db.token = res['oauth_token']
            self.db.token_secret = res['oauth_token_secret']
        else:
            raise Exception(_('Invalid OAuth response. No tokens found.'))

    def get_authorize_url(self):
        if self.db.phase != 1:
            raise Exception('Not ready to authorize.')
        return self.consumer.authorization_url(self.authorize_url)

    def get_access_token(self):
        if self.db.phase != 2:
            raise Exception('Not ready to get access token.')

        res = self.consumer.fetch_access_token(self.access_token_url)

        if 'oauth_token' in res and 'oauth_token_secret' in res:
            self.db.phase = 3
            self.db.token = res['oauth_token']
            self.db.token_secret = res['oauth_token_secret']
            self.content = res
            self.verifier = None
        else:
            raise Exception(_('Invalid OAuth response. No tokens found.'))
