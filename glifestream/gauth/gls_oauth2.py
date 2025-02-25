"""
#  gLifestream Copyright (C) 2023 Wojciech Polak
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
    from oauthlib.oauth2 import BackendApplicationClient
    from requests_oauthlib import OAuth2Session
except ImportError:
    OAuth2Session = None

AGENT = 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL

PHASE_0 = 0
PHASE_1 = 1
PHASE_2 = 2
PHASE_3 = 3


class OAuth2Client:

    def __init__(self, service: Service, api: BaseService, identifier=None, secret=None,
                 callback_url=None):
        if not OAuth2Session:
            raise Exception('requests-oauthlib is required.')

        try:
            self.db = models.OAuthClient.objects.get(service=service)
            if not self.db.identifier and identifier:
                self.db.identifier = identifier
            if not self.db.secret and secret:
                self.db.secret = secret
        except models.OAuthClient.DoesNotExist:
            self.db = models.OAuthClient(service=service)
            if identifier and secret:
                self.db.identifier = identifier
                self.db.secret = secret

        self.callback_url = callback_url
        self.base_url = api.get_base_url()
        self.authorize_url = api.get_authorize_url()
        self.token_url = api.get_token_url()

        if self.db.identifier:
            self.consumer = OAuth2Session(
                client_id=self.db.identifier,
                redirect_uri=self.callback_url,
                scope=['read'],
                token={
                    'access_token': self.db.token,
                    'token_type': 'Bearer'
                } if self.db.token else None)
            self.consumer.headers['User-Agent'] = AGENT
        elif self.db.token:
            self.consumer = OAuth2Session(
                client_id='None',
                redirect_uri=self.callback_url,
                scope=['read'],
                token={
                    'access_token': self.db.token,
                    'token_type': 'Bearer'
                })
            self.consumer.headers['User-Agent'] = AGENT

    def save(self):
        self.db.save()

    def set_urls(self, authorize_url=None, token_url=None):
        self.db.authorize_url = authorize_url
        self.db.access_token_url = token_url
        self.authorize_url = authorize_url
        self.token_url = token_url

    def reset(self):
        self.db.phase = PHASE_0
        self.db.token = None
        self.db.token_secret = None

    def get_authorize_url(self):
        if self.db.phase != PHASE_0:
            raise Exception('Not ready to authorize.')
        url, state = self.consumer.authorization_url(self.authorize_url)
        return url

    def get_access_token(self, authorization_response):
        if self.db.phase != PHASE_2:
            raise Exception('Not ready to get access token.')

        res = self.consumer.fetch_token(
            token_url=self.token_url,
            code=authorization_response,
            client_secret=self.db.secret)

        if 'access_token' in res:
            self.db.phase = PHASE_3
            self.set_access_token(res['access_token'])
            self.content = res
        else:
            raise Exception(_('Invalid OAuth 2.0 response. No access token found.'))

    def set_access_token(self, access_token):
        self.db.token = access_token
