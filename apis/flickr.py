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

from itertools import groupby
from django.utils.translation import ugettext as _
from glifestream.utils.time import mtime, now
from glifestream.stream.models import Entry
from glifestream.stream import media
import webfeed

class API (webfeed.API):
    name = 'Flickr API'
    limit_sec = 600

    def get_urls (self):
        if self.service.url.startswith ('http://'):
            return (self.service.url,)
        else:
            return ('http://api.flickr.com/services/feeds/photos_public.gne?id=%s&format=rss_200' %
                    self.service.url,)

    def process (self):
        for key, group in groupby (self.fp.entries, lambda x: x.updated[0:19]):
            mblob = media.mrss_init ()
            lgroup = 0
            content = '<p class="thumbnails">\n'
            first = True
            for ent in group:
                lgroup += 1
                if first:
                    firstent = ent
                    first = False
                if self.verbose:
                    print "ID: %s" % ent.id

                if 'media_thumbnail' in ent:
                    tn = ent.media_thumbnail[0]
                    if self.service.public:
                        tn['url'] = media.save_image (tn['url'])
                    content += """  <a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="thumbnail" /></a>\n""" % (ent.link, tn['url'], tn['width'], tn['height'])

                if 'media_content' in ent:
                    mblob['content'].append (ent.media_content)

            ent = firstent
            content += '</p>'
            guid = 'tag:flickr.com,2004:/photo/%s' % ent.id

            try:
                e = Entry.objects.get (service=self.service, guid=ent.id)
                if not self.force_overwrite and 'updated_parsed' in ent:
                    if e.date_updated and \
                       mtime (ent.updated_parsed) <= e.date_updated:
                        continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry (service=self.service, guid=ent.id)

            e.mblob = media.mrss_gen_json (mblob)
            if lgroup > 1:
                e.idata = 'grouped'

            e.link  = self.service.link
            e.title = 'Posted Photos'
            e.content = content

            if 'published_parsed' in ent:
                e.date_published = mtime (ent.published_parsed)
            elif 'updated_parsed' in ent:
                e.date_published = mtime (ent.updated_parsed)
            if 'updated_parsed' in ent:
                e.date_updated = mtime (ent.updated_parsed)

            if 'image' in self.fp.feed:
                e.link_image = media.save_image (self.fp.feed.image.href)
            else:
                for link in ent.links:
                    if link.rel == 'image':
                        e.link_image = media.save_image (link.href)
            try:
                e.save ()
            except:
                pass

def filter_title (entry):
    if entry.idata == 'grouped':
        return _('Posted Photos')
    else:
        return _('Posted a Photo')
