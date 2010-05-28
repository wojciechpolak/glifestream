#  gLifestream Copyright (C) 2010 Wojciech Polak
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

from django.utils.html import strip_entities, strip_tags
from glifestream.filters import expand, truncate
from glifestream.utils.time import mtime
from glifestream.stream import media
import webfeed

OAUTH_REQUEST_TOKEN_URL = 'https://www.google.com/accounts/OAuthGetRequestToken'
OAUTH_AUTHORIZE_URL     = 'https://www.google.com/buzz/api/auth/OAuthAuthorizeToken'
OAUTH_ACCESS_TOKEN_URL  = 'https://www.google.com/accounts/OAuthGetAccessToken'
OAUTH_SCOPE             = 'https://www.googleapis.com/auth/buzz'

class API (webfeed.API):
    name = 'Google Buzz API'
    limit_sec = 180

    def get_urls (self):
        if not self.service.url and self.service.creds:
            return ('https://www.googleapis.com/buzz/v1/activities/@me/@consumption',)
        else:
            return ('http://buzz.googleapis.com/feeds/%s/public/posted' %
                    self.service.url,)

    def custom_process (self, e, ent):
        if 'updated_parsed' in ent:
            e.date_published = mtime (ent.updated_parsed)
        e.title = truncate.smart (strip_tags (strip_entities (e.content)))
        e.content = expand.all (e.content)

        links = []
        for link in ent.links:
            if link.rel == 'enclosure' and link.type.startswith ('image/'):
                links.append (link)
        if len (links):
            e.content += '<p class="thumbnails">'
            for l in links:
                url = media.save_image (l['href'], downscale=True)
                e.content += '<a href="%s" rel="nofollow"><img src="%s" alt="thumbnail" /></a> ' % (l['href'], url)
            e.content += '</p>'
