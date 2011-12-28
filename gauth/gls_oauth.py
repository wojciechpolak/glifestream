#  gLifestream Copyright (C) 2010, 2011 Wojciech Polak
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
#  with this program.  If not, see <http://www.gnu.org/licenses/>.

import urllib
import urlparse
from django.utils.translation import ugettext as _
from glifestream.gauth import models

try:
    import oauth2 as oauth
except ImportError:
    oauth = None

class Client:
    def __init__ (self, service, identifier=None, secret=None,
                  callback_url=None):
        if not oauth:
            raise Exception ('python-oauth2 is required.')

        try:
            self.db = models.OAuthClient.objects.get (service=service)
        except models.OAuthClient.DoesNotExist:
            self.db = models.OAuthClient (service=service)
            if identifier and secret:
                self.db.identifier = identifier
                self.db.secret = secret
        try:
            mod = __import__ ('glifestream.apis.%s' % self.db.service.api,
                              {}, {}, ['API'])
        except ImportError:
            raise Exception ('Unable to load %s API.' % self.db.service.api)

        self.callback_url = callback_url
        self.request_token_url = getattr (mod, 'OAUTH_REQUEST_TOKEN_URL', None)
        self.authorize_url = getattr (mod, 'OAUTH_AUTHORIZE_URL', None)
        self.access_token_url = getattr (mod, 'OAUTH_ACCESS_TOKEN_URL', None)
        self.scope = getattr (mod, 'OAUTH_SCOPE', None)

        self.verifier = None
        self.consumer = oauth.Consumer (self.db.identifier,
                                        self.db.secret)

    def save (self):
        self.db.save ()

    def set_urls (self, request_token_url=None, authorize_url=None,
                  access_token_url=None):
        self.db.request_token_url = request_token_url
        self.db.authorize_url = authorize_url
        self.db.access_token_url = access_token_url
        self.request_token_url = request_token_url
        self.authorize_url = authorize_url
        self.access_token_url = access_token_url

    def set_creds (self, identifier, secret):
        self.db.identifier = identifier
        self.db.secret = secret
        self.consumer = oauth.Consumer (self.db.identifier,
                                        self.db.secret)

    def reset (self):
        self.db.phase = 0
        self.db.token = None
        self.db.token_secret = None
        self.verifier = None

    def get_request_token (self):
        if not self.request_token_url:
            raise Exception (_('Request token URL not set.'))
        client = oauth.Client (self.consumer)

        body = {}
        if self.callback_url:
            body['oauth_callback'] = self.callback_url

        res, content = client.request (self.request_token_url, 'POST',
                                       body=urllib.urlencode (body))
        if res['status'] != '200':
            raise Exception (_('Invalid response %s.') % res['status'])

        content = dict (urlparse.parse_qsl (content))
        if 'oauth_token' in content and \
           'oauth_token_secret' in content:
            self.db.phase = 1
            self.db.token = content['oauth_token']
            self.db.token_secret = content['oauth_token_secret']
        else:
            raise Exception (_('Invalid OAuth response. No tokens found.'))

    def get_authorize_url (self):
        if self.db.phase != 1:
            raise Exception ('Not ready to authorize.')
        url = '%s?oauth_token=%s' % (self.authorize_url, self.db.token)
        return url

    def get_access_token (self):
        if self.db.phase != 2:
            raise Exception ('Not ready to get access token.')

        token = oauth.Token (self.db.token, self.db.token_secret)
        if self.verifier:
            token.set_verifier (self.verifier)

        client = oauth.Client (self.consumer, token)
        res, content = client.request (self.access_token_url, 'POST')
        if res['status'] != '200':
            raise Exception (_('Invalid response %s.') % res['status'])

        content = dict (urlparse.parse_qsl (content))
        if 'oauth_token' in content and \
           'oauth_token_secret' in content:
            self.db.phase = 3
            self.db.token = content['oauth_token']
            self.db.token_secret = content['oauth_token_secret']
            self.verifier = None
        else:
            raise Exception (_('Invalid OAuth response. No tokens found.'))

    def sign_request (self, url, postdata=None):
        if self.db.phase != 3:
            raise Exception ('Not ready to sign any request.')
        params = {
            'oauth_version': '1.0',
            'oauth_nonce': oauth.generate_nonce (),
            'oauth_timestamp': oauth.generate_timestamp (),
            'oauth_consumer_key': self.db.identifier,
            'oauth_token': self.db.token,
        }
        if postdata:
            params.update (postdata)

        token = oauth.Token (self.db.token, self.db.token_secret)
        req = oauth.Request (method='GET', url=url, parameters=params)
        req.sign_request (oauth.SignatureMethod_HMAC_SHA1 (),
                          self.consumer, token)
        return req
