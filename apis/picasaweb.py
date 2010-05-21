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

from glifestream.stream import media
import webfeed

class API (webfeed.API):
    name = 'PicasaWeb API'
    limit_sec = 600

    def get_urls (self):
        return ('http://picasaweb.google.com/data/feed/base/user/%s?alt=rss&kind=album&access=public' %
                self.service.url,)

    def custom_process (self, e, ent):
        if 'media_thumbnail' in ent and len (ent.media_thumbnail):
            tn = ent.media_thumbnail[0]
            if self.service.public:
                tn['url'] = media.save_image (tn['url'])
            e.content = """<p class="thumbnails"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="thumbnail" /></a></p>\n""" % (ent.link, tn['url'], tn['width'], tn['height'])
