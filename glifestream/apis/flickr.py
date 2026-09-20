"""
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
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from itertools import groupby
from django.utils.translation import gettext as _

from glifestream.apis.webfeed import WebfeedService
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry
from glifestream.stream import media


class FlickrService(WebfeedService):
    name = 'Flickr API'
    limit_sec = 600

    def get_urls(self):
        if self.service.url.startswith('http://'):
            return (self.service.url,)
        else:
            return (
                'http://api.flickr.com/services/feeds/photos_public.gne?id=%s&format=rss_200'
                % self.service.url,
            )

    def process(self, entries):
        # Flickr posts a burst of photos with the same timestamp; each burst
        # becomes one grouped entry.
        for _key, group in groupby(entries, lambda x: x.updated[0:19]):
            content, mblob, ent, count = self._render_group(group)
            guid = 'tag:flickr.com,2004:/photo/%s' % ent.id

            e = self._resolve_entry(guid, ent)
            if e is None:
                continue

            e.mblob = media.mrss_gen_json(mblob)
            if count > 1:
                e.idata = 'grouped'

            e.link = self.service.link
            e.title = 'Posted Photos'
            e.content = content

            self._apply_dates(e, ent)

            link_image = self._resolve_link_image(ent)
            if link_image is not None:
                e.link_image = link_image

            try:
                e.save()
            except Exception:
                pass

    def _render_group(self, group):
        """Fold one burst of photos into a thumbnail paragraph and an mblob."""
        mblob = media.mrss_init()
        content = '<p class="thumbnails">\n'
        first = None
        count = 0

        for ent in group:
            count += 1
            if first is None:
                first = ent
            if self.verbose:
                print('ID: %s' % ent.id)

            if 'media_thumbnail' in ent:
                tn = ent.media_thumbnail[0]
                if self.service.public:
                    tn['url'] = media.save_image(tn['url'])
                content += (
                    """  <a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="thumbnail" /></a>\n"""
                    % (ent.link, tn['url'], tn['width'], tn['height'])
                )

            if 'media_content' in ent:
                mblob['content'].append(ent.media_content)

        return content + '</p>', mblob, first, count

    def _resolve_entry(self, guid, ent):
        """The entry to write, or None when this group should be skipped."""
        try:
            e = Entry.objects.get(service=self.service, guid=guid)
        except Entry.DoesNotExist:
            return Entry(service=self.service, guid=guid)

        if not self.force_overwrite and 'updated_parsed' in ent:
            if e.date_updated and mtime(ent.updated_parsed) <= e.date_updated:
                return None
        if e.protected:
            return None
        return e

    @staticmethod
    def _apply_dates(e, ent):
        if 'published_parsed' in ent:
            e.date_published = mtime(ent.published_parsed)
        elif 'updated_parsed' in ent:
            e.date_published = mtime(ent.updated_parsed)
        if 'updated_parsed' in ent:
            e.date_updated = mtime(ent.updated_parsed)

    def _resolve_link_image(self, ent):
        """The feed's own image, else the last image the entry links to."""
        if 'image' in self.fp.feed:
            return media.save_image(self.fp.feed.image.href)
        found = None
        for link in ent.links:
            if link.rel == 'image':
                found = media.save_image(link.href)
        return found


def filter_title(entry):
    if entry.idata == 'grouped':
        return _('Posted Photos')
    else:
        return _('Posted a Photo')
