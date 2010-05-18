#  gLifestream Copyright (C) 2009, 2010 Wojciech Polak
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

from glifestream.filters import expand, truncate, twyntax
from glifestream.stream import media
import webfeed

OAUTH_REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
OAUTH_AUTHORIZE_URL     = 'https://api.twitter.com/oauth/authorize'
OAUTH_ACCESS_TOKEN_URL  = 'https://api.twitter.com/oauth/access_token'

class API (webfeed.API):
    name = 'Twitter API'
    limit_sec = 120

    def run (self):
        if not self.service.url and self.service.creds:
            self.fetch ('http://api.twitter.com/1/statuses/home_timeline.atom?count=50')
        else:
            if not self.service.last_checked:
                self.fetch ('http://api.twitter.com/1/statuses/user_timeline/%s.atom?count=200' % \
                            self.service.url)
            else:
                self.fetch ('http://api.twitter.com/1/statuses/user_timeline/%s.atom' % \
                            self.service.url)

    def custom_process (self, e, ent):
        e.title = 'Tweet: %s' % truncate.smart (ent.title.split (': ', 1)[1])
        e.content = expand.all (e.content)
        e.custom_mblob = media.mrss_scan (e.content)

def filter_content (entry):
    return twyntax.parse (entry.content)
