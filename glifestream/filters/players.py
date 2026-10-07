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

# The players of YouTube and Vimeo videos that entries store.
#
# A player is a play-video block: the video's thumbnail, linked to its page,
# which the page script turns into the video. Imports, posts, the editor and
# the upgrades all store it in the markup made here.

from __future__ import annotations

import html
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlparse

from django.conf import settings
from django.utils.html import escape

from glifestream.stream import media
from glifestream.utils import oembed

PROVIDERS = ('youtube', 'vimeo')

# The box every thumbnail of a post's video is stored at and shown in.
THUMBNAIL_SIZE = (320, 180)
YOUTUBE_THUMBNAIL_URL = 'https://i.ytimg.com/vi/%s/mqdefault.jpg'
# Twice the shown box, which `save_image` scales down.
_VIMEO_OEMBED_WIDTH = 640
# The alt text of a post's player, which has no title of its own.
_ALT = {'youtube': 'YouTube Video', 'vimeo': 'Vimeo Video'}


def youtube_link(vid: str) -> str:
    return 'https://www.youtube.com/watch?v=%s' % vid


def vimeo_link(vid: str | int) -> str:
    return 'https://vimeo.com/%s' % vid


def youtube_html(vid: str, link: str, src: str, width: int, height: int) -> str:
    """The stored markup of a YouTube video, its thumbnail already in place."""
    return (
        """<div data-id="youtube-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="YouTube Video" /></a><div class="playbutton"></div></div>"""
        % (vid, link, src, width, height)
    )


def vimeo_html(vid: str | int, link: str, title: str, src: str) -> str:
    """The stored markup of a Vimeo video, its thumbnail already in place."""
    return (
        """<div data-id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="%s" /></a><div class="playbutton"></div></div>"""
        % (vid, link, src, *THUMBNAIL_SIZE, escape(title))
    )


def link_of(provider: str, vid: str) -> str:
    return youtube_link(vid) if provider == 'youtube' else vimeo_link(vid)


def player_html(provider: str, vid: str, src: str, title: str = '') -> str:
    """The player of a video in a post. A Vimeo player names its video
    with `title`, as an import does, when the post did."""
    link = link_of(provider, vid)
    if provider == 'youtube':
        return youtube_html(vid, link, src, *THUMBNAIL_SIZE)
    return vimeo_html(vid, link, title or _ALT[provider], src)


def _youtube_path_id(parts: list[str], query: dict[str, str], path: str) -> str | None:
    if path == '/watch':
        return query.get('v')
    if len(parts) >= 2 and parts[0] in ('shorts', 'live', 'embed'):
        return parts[1]
    return None


def _youtu_be_id(parts: list[str], query: dict[str, str], path: str) -> str | None:
    return parts[0] if parts else None


def _nocookie_id(parts: list[str], query: dict[str, str], path: str) -> str | None:
    if len(parts) >= 2 and parts[0] == 'embed':
        return parts[1]
    return None


# Host (without "www.") -> how that host carries the video id.
_YOUTUBE_ID_EXTRACTORS = {
    'youtube.com': _youtube_path_id,
    'm.youtube.com': _youtube_path_id,
    'youtu.be': _youtu_be_id,
    'youtube-nocookie.com': _nocookie_id,
}


def normalize_youtube_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return None

    host = parsed.netloc.lower().removeprefix('www.')
    extract = _YOUTUBE_ID_EXTRACTORS.get(host)
    if extract is None:
        return None

    path = parsed.path.rstrip('/')
    parts = [part for part in path.split('/') if part]
    video_id = extract(parts, dict(parse_qsl(parsed.query)), path)
    if not video_id or not re.fullmatch(r'[\-\w]+', video_id):
        return None
    return 'https://www.youtube.com/watch?v=%s' % video_id


def youtube_video_id(url: str) -> str | None:
    """The id of the YouTube video `url` shows, or None."""
    # A YouTube Music address plays the same video.
    url = re.sub(
        r'^(https?://)music\.youtube\.com/', r'\1www.youtube.com/', url.strip()
    )
    canonical = normalize_youtube_url(url)
    return canonical.rsplit('=', 1)[1] if canonical else None


_VIMEO_VIDEO = re.compile(
    r'https?://(?:www\.|player\.)?vimeo\.com/(?:[^?#]*/)?(\d+)/?(?:[?#].*)?'
)


def vimeo_video_id(url: str) -> str | None:
    """The id of the Vimeo video `url` shows, or None."""
    m = _VIMEO_VIDEO.fullmatch(url.strip())
    return m.group(1) if m else None


def video_of(url: str) -> tuple[str, str] | None:
    """The provider and the id of the video `url` shows, or None."""
    vid = youtube_video_id(url)
    if vid:
        return 'youtube', vid
    vid = vimeo_video_id(url)
    return ('vimeo', vid) if vid else None


@dataclass(frozen=True)
class Block:
    """A player in an entry's content, with what wraps only it."""

    start: int
    end: int
    provider: str
    video_id: str
    src: str
    width: str
    height: str
    alt: str


_ATTR = re.compile(r'([\w-]+)="([^"]*)"')
_BLOCK_START = re.compile(r'<(div|span)\b[^>]*\bclass="play-video"[^>]*>')
_BLOCK_ID = re.compile(r'(?:data-)?id="(%s)-([\w-]+)"' % '|'.join(PROVIDERS))
# The table old posts centred a player in, and a paragraph around it all.
_WRAP_BEFORE = (
    re.compile(r'<table class="vc">\s*<tr>\s*<td>\s*$'),
    re.compile(r'<p>\s*$'),
)
_WRAP_AFTER = (
    re.compile(r'^\s*</td>\s*</tr>\s*</table>'),
    re.compile(r'^\s*</p>'),
)


def _element_end(content: str, start: int, tag: str) -> int | None:
    """Where the <tag> element opening at `start` ends."""
    depth = 0
    for m in re.finditer(r'<(/?)%s\b[^>]*>' % tag, content[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return start + m.end()
    return None


def _cards(content: str) -> list[tuple[int, int]]:
    """Where the music cards of `content` are (`filters/music.py`)."""
    spans = []
    for m in re.finditer(r'<div class="music-card">', content):
        end = _element_end(content, m.start(), 'div')
        spans.append((m.start(), end if end is not None else len(content)))
    return spans


def find_blocks(content: str) -> list[Block]:
    """The players of `content`, except those in a music card, which the
    card owns."""
    if 'play-video' not in content:
        return []
    cards = _cards(content)
    blocks = []
    for m in _BLOCK_START.finditer(content):
        ident = _BLOCK_ID.search(m.group(0))
        end = _element_end(content, m.start(), m.group(1))
        if ident is None or end is None:
            continue
        if any(a <= m.start() < b for a, b in cards):
            continue
        img = re.search(r'<img\b[^>]*>', content[m.end() : end])
        attrs = dict(_ATTR.findall(img.group(0))) if img else {}
        start = m.start()
        for before, after in zip(_WRAP_BEFORE, _WRAP_AFTER):
            opening = before.search(content, 0, start)
            closing = after.match(content[end:])
            if opening is None or closing is None:
                break
            start = opening.start()
            end += closing.end()
        blocks.append(
            Block(
                start=start,
                end=end,
                provider=ident.group(1),
                video_id=ident.group(2),
                src=attrs.get('src', ''),
                width=attrs.get('width', ''),
                height=attrs.get('height', ''),
                alt=html.unescape(attrs.get('alt', '')),
            )
        )
    return blocks


def thumb_exists(rel: str) -> bool:
    """Whether a MEDIA_ROOT-relative thumbnail is on disk."""
    return os.path.isfile(os.path.join(settings.MEDIA_ROOT, rel))


def thumbnail_is_current(
    src: str, width: str, height: str, size: tuple[int, int], *, public: bool
) -> bool:
    """Whether a thumbnail is what a fresh import would show: the right
    box, and for a public service a local copy in today's format."""
    if (width, height) != (str(size[0]), str(size[1])):
        return False
    if not public:
        return src.startswith('https://')
    if not src.startswith('[GLS-THUMBS]/'):
        return False
    if not src.endswith(media.thumb_suffix()):
        return False
    return all(thumb_exists(rel) for rel in media.thumb_rels(src))


def thumbnail_url(provider: str, vid: str) -> str | None:
    """The address of the provider's thumbnail of a video, or None when
    the provider does not say."""
    if provider == 'youtube':
        return YOUTUBE_THUMBNAIL_URL % vid
    data = oembed.discover(vimeo_link(vid), 'vimeo', maxwidth=_VIMEO_OEMBED_WIDTH)
    url = data.get('thumbnail_url') if isinstance(data, dict) else None
    return url if isinstance(url, str) and url else None


def localize(url: str, *, public: bool, strict: bool = False) -> str:
    """Where a thumbnail is served from: a local copy for a public service,
    the remote image for a private one. `strict` raises when the local copy
    cannot be made, which otherwise leaves the remote image."""
    if not public:
        return url
    return media.save_image(url, downscale=True, size=THUMBNAIL_SIZE, strict=strict)


def fetch_thumbnail(provider: str, vid: str, *, public: bool) -> str | None:
    url = thumbnail_url(provider, vid)
    return localize(url, public=public) if url else None


# Gives the thumbnail of a video to show: (provider, video id) -> src.
Thumbnail = Callable[[str, str], 'str | None']


def _rewrite(
    content: str,
    src_of: Callable[[Block, str, str], str | None],
    replace: tuple[str, str] | None = None,
) -> str | None:
    """`content` with each player made again; `src_of` gives the thumbnail
    of each, and None stops it."""
    out = []
    pos = 0
    for i, block in enumerate(find_blocks(content)):
        provider, vid = (
            replace if i == 0 and replace else (block.provider, block.video_id)
        )
        src = src_of(block, provider, vid)
        if src is None:
            return None
        same = (provider, vid) == (block.provider, block.video_id)
        title = block.alt if same and block.alt not in _ALT.values() else ''
        out.append(content[pos : block.start])
        out.append(
            player_html(provider, vid, src, title) if src else _plain(provider, vid)
        )
        pos = block.end
    out.append(content[pos:])
    return ''.join(out)


def _plain(provider: str, vid: str) -> str:
    link = link_of(provider, vid)
    return '<a href="%s" rel="nofollow">%s</a>' % (link, link)


def _current(block: Block, provider: str, vid: str, *, public: bool) -> bool:
    return (provider, vid) == (block.provider, block.video_id) and (
        thumbnail_is_current(
            block.src, block.width, block.height, THUMBNAIL_SIZE, public=public
        )
    )


def canonical(content: str, *, public: bool) -> str | None:
    """`content` with its players in today's markup, keeping their
    thumbnails, or None when one of them needs a new thumbnail."""
    return _rewrite(
        content,
        lambda block, p, v: block.src if _current(block, p, v, public=public) else None,
    )


def render(
    content: str,
    *,
    public: bool,
    thumbnail: Thumbnail | None = None,
    replace: tuple[str, str] | None = None,
) -> str:
    """`content` with its players in today's markup, each with a current
    thumbnail. `replace` is the provider and the id of another video for
    the first player. A thumbnail `thumbnail` cannot give keeps the one the
    player shows, or leaves a link to the video instead."""
    if thumbnail is None:

        def thumbnail(provider: str, vid: str) -> str | None:
            return fetch_thumbnail(provider, vid, public=public)

    def src_of(block: Block, provider: str, vid: str) -> str:
        if _current(block, provider, vid, public=public):
            return block.src
        assert thumbnail is not None
        src = thumbnail(provider, vid)
        if src:
            return src
        same = (provider, vid) == (block.provider, block.video_id)
        return block.src if same else ''

    result = _rewrite(content, src_of, replace)
    assert result is not None
    return result
