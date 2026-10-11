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

from functools import partial
from itertools import groupby
from django.utils.html import format_html
from django.utils.translation import gettext as _

from glifestream.apis.webfeed import WebfeedService
from glifestream.ingestion import Candidate, NormalizedEntry
from glifestream.stream import media
from glifestream.utils.html import is_safe_http_url


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
        self.ingest(self._candidates(entries))

    def _candidates(self, entries):
        # Flickr posts a burst of photos with the same timestamp; each burst
        # becomes one grouped entry.
        for _key, group in groupby(entries, lambda x: x.updated[0:19]):
            content, mblob, ent, count = self._render_group(group)
            guid = 'tag:flickr.com,2004:/photo/%s' % ent.id
            yield Candidate(
                guid,
                self._freshness(ent),
                partial(self._normalize_group, guid, ent, content, mblob, count),
            )

    def _normalize_group(self, guid, ent, content, mblob, count) -> NormalizedEntry:
        e = NormalizedEntry(guid=guid, register_media=False)
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
        return e

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
                link = ent.get('link')
                thumbnail_url = tn.get('url')
                if (
                    isinstance(link, str)
                    and is_safe_http_url(link)
                    and isinstance(thumbnail_url, str)
                    and is_safe_http_url(thumbnail_url)
                ):
                    if self.service.public:
                        thumbnail_url = media.save_image(thumbnail_url)
                    dimensions = _thumbnail_dimensions(tn)
                    if dimensions:
                        thumbnail = format_html(
                            '<img src="{}" width="{}" height="{}" alt="thumbnail" />',
                            thumbnail_url,
                            dimensions[0],
                            dimensions[1],
                        )
                    else:
                        thumbnail = format_html(
                            '<img src="{}" alt="thumbnail" />', thumbnail_url
                        )
                    content += str(
                        format_html(
                            '  <a href="{}" rel="nofollow">{}</a>\n', link, thumbnail
                        )
                    )

            if 'media_content' in ent:
                safe_media = [
                    item
                    for item in ent.media_content
                    if isinstance(item, dict)
                    and isinstance(item.get('url'), str)
                    and is_safe_http_url(item['url'])
                ]
                if safe_media:
                    mblob['content'].append(safe_media)

        return content + '</p>', mblob, first, count

    def _resolve_link_image(self, ent):
        """The feed's own image, else the last image the entry links to."""
        if 'image' in self.fp.feed and is_safe_http_url(self.fp.feed.image.href):
            return media.save_image(self.fp.feed.image.href)
        found = None
        for link in ent.links:
            if link.rel == 'image' and is_safe_http_url(link.href):
                found = media.save_image(link.href)
        return found


def _thumbnail_dimensions(thumbnail) -> tuple[int, int] | None:
    try:
        width = int(thumbnail['width'])
        height = int(thumbnail['height'])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def filter_title(entry):
    if entry.idata == 'grouped':
        return _('Posted Photos')
    else:
        return _('Posted a Photo')
