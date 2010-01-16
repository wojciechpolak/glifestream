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

from django.template.defaultfilters import title
from django.utils.translation import ugettext as _
from glifestream.stream import media
import webfeed

class API (webfeed.API):
    name = 'YouTube API v2'
    limit_sec = 3600

    def run (self):
        host = 'http://gdata.youtube.com'
        self.fetch ('%s/feeds/api/users/%s/favorites?v=2' % (host,
                                                             self.service.url))
        self.fetch ('%s/feeds/api/users/%s/uploads?v=2' % (host,
                                                           self.service.url))

    def custom_process (self, e, ent):
        if ent.has_key ('media_thumbnail') and len (ent['media_thumbnail']):
            tn = ent['media_thumbnail'][0]
            if self.service.public:
                tn['url'] = media.save_image (tn['url'])

            e.link = e.link.replace ('&feature=youtube_gdata', '')
            e.content = """<table class="vc"><tr><td><div id="youtube-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="YouTube Video" /></a><div class="playbutton"></div></div></td></tr></table>""" % (ent['yt_videoid'], e.link, tn['url'], tn['width'], tn['height'])
        else:
            e.content = ent.get ('yt_state', _('NO VIDEO'));

def filter_title (entry):
    if 'favorite' in entry.guid:
        return _('Favorited %s') % ('<em>' + title (entry.title) + '</em>')
    else:
        return _('Published %s') % ('<em>' + title (entry.title) + '</em>')
