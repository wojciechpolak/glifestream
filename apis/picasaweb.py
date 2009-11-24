#  gLifestream Copyright (C) 2009 Wojciech Polak
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

from glifestream.filters import expand
import webfeed

class API (webfeed.API):
    name = 'PicasaWeb API'
    limit_sec = 600

    def run (self):
        self.fetch ('http://picasaweb.google.com/data/feed/base/user/%s?alt=rss&kind=album&access=public' % self.service.url)

    def custom_process (self, e, ent):
        if ent.has_key ('media_thumbnail') and len (ent['media_thumbnail']):
            tn = ent['media_thumbnail'][0]
            if self.service.public:
                tn['url'] = expand.save_image (tn['url'])
            e.content = """<div class="thumbnails"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="thumbnail" /></a></div>\n""" % (ent.link, tn['url'], tn['width'], tn['height'])
