"""
# gLifestream Copyright (C) 2026 Wojciech Polak
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# The music card: a track's cover, title and artist, a YouTube player and
# links to search for the track on the music services.
#
# A post stores the card's finished HTML, so `card_html` is the one place
# that decides its markup: the composer renders new cards with it, and
# `glifestream.upgrades` compares stored cards with it. The service links
# are searches, which need no API and stay valid as long as the services do.

from __future__ import annotations

import html
import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

from PIL import Image
from django.utils.html import escape
from django.utils.translation import gettext as _

from glifestream.filters.expand import normalize_youtube_url
from glifestream.stream import media

logger = logging.getLogger(__name__)

# The services a card links to: their name, the address of a search, and
# whether the query goes in the path (quoted) or in the query string.
LISTEN_ON: tuple[tuple[str, str, bool], ...] = (
    ('Spotify', 'https://open.spotify.com/search/%s', True),
    ('Apple Music', 'https://music.apple.com/search?term=%s', False),
    ('YouTube Music', 'https://music.youtube.com/search?q=%s', False),
    ('Deezer', 'https://www.deezer.com/search/%s', True),
    ('Tidal', 'https://tidal.com/search?q=%s', False),
    ('Bandcamp', 'https://bandcamp.com/search?q=%s&item_type=t', False),
)

# The box a cover is scaled down into.
COVER_SIZE = (160, 160)

# A YouTube thumbnail stands in for a missing cover.
YOUTUBE_THUMBNAIL_URL = 'https://i.ytimg.com/vi/%s/mqdefault.jpg'
YOUTUBE_THUMBNAIL_SIZE = (320, 180)


class MusicError(ValueError):
    """A card that cannot be made as asked. The message says why, for the
    owner."""


@dataclass(frozen=True)
class Cover:
    src: str
    width: int
    height: int


@dataclass(frozen=True)
class Track:
    artist: str
    title: str
    cover: Cover | None = None
    youtube_id: str | None = None


def clean(text: str) -> str:
    """`text` on one line, without surrounding blanks."""
    return ' '.join(text.split())


def search_links(artist: str, title: str) -> list[tuple[str, str]]:
    """(service, address) of a search for the track on each service."""
    q = '%s %s' % (artist, title)
    return [
        (name, url % (quote(q, safe='') if in_path else quote_plus(q)))
        for name, url, in_path in LISTEN_ON
    ]


def youtube_link(video_id: str) -> str:
    return 'https://www.youtube.com/watch?v=%s' % video_id


def _cover_img(track: Track) -> str:
    assert track.cover is not None
    return '<img src="%s" width="%d" height="%d" alt="%s" />' % (
        escape(track.cover.src),
        track.cover.width,
        track.cover.height,
        escape('%s – %s' % (track.title, track.artist)),
    )


def card_html(track: Track) -> str:
    """The card of `track`, as a post stores it. Pure: no request, no file."""
    if track.youtube_id:
        inner = _cover_img(track) if track.cover else 'YouTube'
        cover = (
            '<div data-id="youtube-%s" class="play-video">'
            '<a href="%s" rel="nofollow">%s</a><div class="playbutton"></div></div>'
            % (track.youtube_id, youtube_link(track.youtube_id), inner)
        )
    elif track.cover:
        cover = '<span class="music-cover">%s</span>' % _cover_img(track)
    else:
        cover = ''
    links = ' · '.join(
        '<a href="%s" rel="nofollow">%s</a>' % (escape(url), escape(name))
        for name, url in search_links(track.artist, track.title)
    )
    return (
        '<div class="music-card">%s'
        '<p class="music-track"><span class="music-title">%s</span> '
        '<span class="music-artist">%s</span></p>'
        '<p class="music-links">%s</p></div>'
        % (cover, escape(track.title), escape(track.artist), links)
    )


_CARD_START = '<div class="music-card">'
_DIV_TAG = re.compile(r'<(/?)div\b[^>]*>')
_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def find_card(content: str, start: int = 0) -> tuple[int, int] | None:
    """Where the first card at or after `start` begins and ends in
    `content`, or None."""
    begin = content.find(_CARD_START, start)
    if begin == -1:
        return None
    depth = 0
    for m in _DIV_TAG.finditer(content, begin):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return begin, m.end()
    return None


def _span_text(fragment: str, cls: str) -> str:
    m = re.search(r'<span class="%s">(.*?)</span>' % cls, fragment, re.S)
    return clean(html.unescape(m.group(1))) if m else ''


def parse_card(fragment: str) -> Track | None:
    """The track a stored card shows: the inverse of `card_html`, also for
    cards an earlier renderer made."""
    if not fragment.startswith(_CARD_START):
        return None
    artist = _span_text(fragment, 'music-artist')
    title = _span_text(fragment, 'music-title')
    if not artist or not title:
        return None
    m = re.search(r'\bdata-id="youtube-([\w-]+)"', fragment)
    img = re.search(r'<img\b[^>]*>', fragment)
    cover = None
    if img:
        attrs = dict(_ATTR.findall(img.group(0)))
        width, height = attrs.get('width', ''), attrs.get('height', '')
        if attrs.get('src') and width.isdigit() and height.isdigit():
            cover = Cover(html.unescape(attrs['src']), int(width), int(height))
    return Track(artist, title, cover, m.group(1) if m else None)


def youtube_id(url: str) -> str | None:
    """The id of the YouTube video `url` shows, or None."""
    # A YouTube Music address plays the same video.
    url = re.sub(r'^(https?://)music\.youtube\.com/', r'\1www.youtube.com/', clean(url))
    canonical = normalize_youtube_url(url)
    return canonical.rsplit('=', 1)[1] if canonical else None


def _local_cover(src: str) -> Cover:
    """The cover a local thumbnail `src` ([GLS-THUMBS]/...) shows, with its
    size read from the file."""
    m = re.fullmatch(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', src)
    if m is None:
        raise MusicError(_('The cover is not a local thumbnail.'))
    local = media.get_thumb_info(m.group(1), append_suffix=False)['local']
    if not os.path.isfile(local):
        raise MusicError(_('The cover file is missing.'))
    with Image.open(local) as im:
        width, height = im.size
    return Cover(src, width, height)


def localize_cover(url: str, size: tuple[int, int] = COVER_SIZE) -> Cover:
    """A local copy of the cover at `url`, or the local thumbnail `url`
    already is."""
    url = clean(url)
    if url.startswith('[GLS-THUMBS]/'):
        return _local_cover(url)
    if not re.match(r'https?://', url):
        raise MusicError(_('The cover address is not a web address.'))
    src = media.save_image(url, downscale=True, size=size)
    if not src.startswith('[GLS-THUMBS]/'):
        raise MusicError(_('The cover could not be downloaded.'))
    return _local_cover(src)


def build_track(
    artist: str,
    title: str,
    youtube_url: str = '',
    cover_url: str = '',
    *,
    strict: bool = True,
) -> Track:
    """The track the owner described, with its cover saved locally.

    Strict, a YouTube address or a cover that does not work is an error.
    Otherwise it is logged and left out: the cover falls back to the
    video's thumbnail, and the player to none.
    """
    artist, title = clean(artist), clean(title)
    if not artist or not title:
        raise MusicError(_('Enter the artist and the title of the track.'))

    vid = None
    if clean(youtube_url):
        vid = youtube_id(youtube_url)
        if vid is None:
            if strict:
                raise MusicError(_('That is not a YouTube video address.'))
            logger.warning('Music card without its player: %r', youtube_url)

    cover = None
    if clean(cover_url):
        try:
            cover = localize_cover(cover_url)
        except MusicError as exc:
            if strict:
                raise
            logger.warning('Music card without its cover %r: %s', cover_url, exc)
    if cover is None and vid:
        try:
            cover = localize_cover(
                YOUTUBE_THUMBNAIL_URL % vid, size=YOUTUBE_THUMBNAIL_SIZE
            )
        except MusicError as exc:
            if strict:
                raise MusicError(
                    _('YouTube has no thumbnail of this video. Enter a cover.')
                ) from exc
    return Track(artist, title, cover, vid)
