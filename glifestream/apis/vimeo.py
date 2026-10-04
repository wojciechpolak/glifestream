"""
#  gLifestream Copyright (C) 2009-2023 Wojciech Polak
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
from functools import partial

from django.utils.html import escape
from django.utils.translation import gettext as _

from glifestream.apis.base import BaseService
from glifestream.ingestion import Candidate, NormalizedEntry
from glifestream.utils import httpclient
from glifestream.utils.time import now
from glifestream.stream.models import Entry
from glifestream.stream import media
from typing import Any


class VimeoService(BaseService):
    name = 'Vimeo Simple API v2'
    limit_sec = 3600

    def get_urls(self) -> list[str]:
        if '/' in self.service.url:
            url = self.service.url.replace('channel/', 'channels/')
            url = url.replace('group/', 'groups/')
            return ['https://vimeo.com/%s/videos/rss' % url]
        else:
            return [
                'https://vimeo.com/%s/likes/rss' % self.service.url,
                'https://vimeo.com/%s/videos/rss' % self.service.url,
            ]

    def run(self) -> None:
        if not self.service.link:
            self.service.link = 'https://vimeo.com/%s' % self.service.url
        if '/' in self.service.url:
            self.process = self.process_videos
            self.fetch('/api/v2/%s/videos.json' % self.service.url)
        else:
            self.process = self.process_likes
            self.fetch('/api/v2/%s/likes.json' % self.service.url)
            self.process = self.process_videos
            self.fetch('/api/v2/%s/videos.json' % self.service.url)

    def fetch(self, url: str) -> None:
        r = httpclient.get('https://vimeo.com' + url)
        self.json = httpclient.require_json(r)
        self.service.last_checked = now()
        self.service.save()
        self.process()

    def process_likes(self) -> None:
        """Process what user did like."""
        self._process_entries(date_key='liked_on', idata='liked')

    def process_videos(self) -> None:
        """Process videos uploaded by user."""
        self._process_entries(date_key='upload_date', register_media=True)

    def _process_entries(
        self,
        *,
        date_key: str,
        idata: str | None = None,
        register_media: bool = False,
    ) -> None:
        """Turn one Vimeo JSON listing into entries.

        Likes and uploads differ only in which timestamp field they carry and
        in whether the entry is tagged as a like, so they share this body.
        """
        self.ingest(
            self._candidates(
                idata=idata, register_media=register_media, date_key=date_key
            )
        )

    def _candidates(self, *, date_key: str, idata: str | None, register_media: bool):
        for ent in self.json:
            date = ent[date_key][:10]
            guid = 'tag:vimeo,%s:clip%s' % (date, ent['id'])
            if self.verbose:
                print('ID: %s' % guid)
            t = _parse_vimeo_date(ent[date_key])
            yield Candidate(
                guid,
                t if isinstance(t, datetime.datetime) else None,
                partial(self._normalize, guid, t, ent, idata, register_media),
            )

    def _normalize(
        self,
        guid: str,
        t: Any,
        ent: dict,
        idata: str | None,
        register_media: bool,
    ) -> NormalizedEntry:
        e = NormalizedEntry(guid=guid, register_media=register_media)
        e.title = ent['title']
        e.link = ent['url']
        e.date_published = t
        e.date_updated = t
        e.author_name = ent['user_name']

        if idata:
            e.idata = idata

        src = localize_thumbnail(ent['thumbnail_large'], public=self.service.public)
        e.content = player_html(ent['id'], e.link, ent['title'], src)
        e.mblob = player_mblob(ent['id'])
        return e


# The box every Vimeo thumbnail is stored at and shown in.
THUMBNAIL_SIZE = (320, 180)


def video_link(video_id: str | int) -> str:
    return 'https://vimeo.com/%s' % video_id


def player_html(video_id: str | int, link: str, title: str, src: str) -> str:
    """The stored markup of a video, its thumbnail already in place.

    Entries keep this markup in their content, so `glifestream.upgrades`
    compares old entries with it to find the ones a change here left behind.
    """
    return (
        """<div data-id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="%s" /></a><div class="playbutton"></div></div>"""
        % (video_id, link, src, *THUMBNAIL_SIZE, escape(title))
    )


def localize_thumbnail(url: str, *, public: bool) -> str:
    """Where a thumbnail is served from: a local copy for a public service,
    the remote image for a private one."""
    if not public:
        return url
    return media.save_image(url, downscale=True, size=THUMBNAIL_SIZE)


def player_mblob(video_id: str | int) -> str | None:
    """The Media RSS of a video: its player."""
    mblob = media.mrss_init()
    mblob['content'].append(
        [
            {
                'url': 'https://player.vimeo.com/video/%s' % video_id,
                'medium': 'video',
            }
        ]
    )
    return media.mrss_gen_json(mblob)


def _parse_vimeo_date(value: str) -> Any:
    """Vimeo's own timestamp format, or the raw string when it does not parse."""
    try:
        t = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return t.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return value


def filter_title(entry: Entry) -> str:
    if entry.idata == 'liked':
        return _('Liked %s') % ('<em>' + entry.title + '</em>')
    else:
        return _('Published %s') % ('<em>' + entry.title + '</em>')
