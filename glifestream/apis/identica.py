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
from glifestream.apis import webfeed


class API (webfeed.API):
    name = 'Identi.ca API'
    limit_sec = 180

    def get_urls(self):
        if not self.service.url and self.service.creds:
            return ('http://identi.ca/api/statuses/friends_timeline.rss?count=50',)
        else:
            if not self.service.last_checked:
                return ('http://identi.ca/api/statuses/user_timeline/%s.rss?count=200' %
                        self.service.url,)
            else:
                return ('http://identi.ca/api/statuses/user_timeline/%s.rss' %
                        self.service.url,)

    def custom_process(self, e, ent):
        e.title = 'Tweet: %s' % truncate.smart(ent.title)
        e.content = expand.all(ent.summary)
        e.custom_mblob = media.mrss_scan(e.content)


def filter_content(entry):
    return twyntax.parse(entry.content, type='identica')
