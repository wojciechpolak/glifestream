"""
#  gLifestream Copyright (C) 2009-2021 Wojciech Polak
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

import datetime
from django.utils.translation import gettext as _

from glifestream.apis.base import BaseService
from glifestream.stream import media
from glifestream.stream.models import Entry
from glifestream.utils import httpclient
from glifestream.utils.time import mtime, now


class YoutubeService(BaseService):
    name = 'YouTube API v3'
    limit_sec = 3600
    playlist_types: dict[str, str] = {}

    def get_urls(self) -> list[str]:
        if self.service.url.startswith('http://') or self.service.url.startswith(
            'https://'
        ):
            return [self.service.url]
        else:
            urls = []
            if ':' in self.service.url:
                apikey, playlists = self.service.url.split(':')
                for playlist in playlists.split(','):
                    if '#' in playlist:
                        playlist, kind = playlist.split('#')
                    else:
                        kind = 'video'
                    url = (
                        'https://www.googleapis.com/youtube/v3/'
                        'playlistItems?part=snippet,contentDetails,status&'
                        'playlistId=%s&'
                        'maxResults=25&'
                        'key=%s' % (playlist, apikey)
                    )
                    self.playlist_types[url] = kind
                    urls.append(url)
            return urls

    def run(self) -> None:
        for url in self.get_urls():
            self.fetch(url)

    def fetch(self, url: str) -> None:
        r = httpclient.get(url)
        self.json = httpclient.require_json(r)
        self.service.last_checked = now()
        self.service.save()
        self.process(url)

    def process(self, url: str) -> None:
        kind = self.playlist_types.get(url)
        for ent in self.json.get('items', ()):
            snippet = ent.get('snippet', {})
            vid = ent['contentDetails']['videoId']
            if kind == 'favorite':
                guid = 'tag:youtube.com,2008:favorite:%s' % ent.get('id')
            else:
                guid = 'tag:youtube.com,2008:video:%s' % vid

            t = _parse_published(snippet['publishedAt'])

            if self.verbose:
                print('ID: %s' % guid)
            e = self.resolve_entry(guid, mtime(t.timetuple()))
            if e is None:
                continue

            e.title = snippet['title']
            e.link = 'https://www.youtube.com/watch?v=%s' % vid
            e.date_published = t
            e.date_updated = t
            e.author_name = snippet['channelTitle']
            e.content = self._render_content(e, vid, snippet.get('thumbnails', {}))

            try:
                e.save()
            except Exception as exc:
                print(exc)

    def _render_content(self, e: Entry, vid: str, thumbnails: dict) -> str:
        tn = _pick_thumbnail(thumbnails) if vid else None
        if tn is None:
            return '<a href="%s">%s</a>' % (e.link, e.title)

        if self.service.public:
            tn['url'] = media.save_image(
                tn['url'], downscale=True, size=(tn['width'], tn['height'])
            )
        return (
            """<div id="youtube-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="YouTube Video" /></a><div class="playbutton"></div></div>"""
            % (vid, e.link, tn['url'], tn['width'], tn['height'])
        )


# Preferred thumbnail sizes, best first, with the box each is shown in.
_THUMBNAIL_SIZES = (
    ('medium', 320, 180),
    ('high', 200, 150),
    ('default', 200, 150),
)


def _pick_thumbnail(thumbnails: dict) -> dict | None:
    """The best available thumbnail, sized for display, or None.

    YouTube always lists a `default` thumbnail; without one the entry falls
    back to a plain link.
    """
    if 'default' not in thumbnails:
        return None
    for key, width, height in _THUMBNAIL_SIZES:
        if thumbnails.get(key):
            return {**thumbnails[key], 'width': width, 'height': height}
    return None


def _parse_published(value: str) -> datetime.datetime:
    """`publishedAt`, with or without milliseconds, as an aware UTC datetime."""
    try:
        t = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        t = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.000Z')
    return t.replace(tzinfo=datetime.timezone.utc)


def filter_title(entry: Entry) -> str:
    if 'favorite' in entry.guid:
        return _('Favorited %s') % ('<em>' + entry.title + '</em>')
    else:
        return _('Published %s') % ('<em>' + entry.title + '</em>')
