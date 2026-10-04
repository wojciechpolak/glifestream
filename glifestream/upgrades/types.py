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

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings

from glifestream.stream import media
from glifestream.stream.models import Entry
from glifestream.utils import httpclient


class Unavailable(Exception):
    """The provider has nothing to upgrade an entry with, such as a thumbnail
    of a video it no longer has. The message says why, for the owner."""


@dataclass(frozen=True)
class Proposal:
    """The fields an upgrade gives an entry."""

    content: str
    link: str
    mblob: str | None

    def matches(self, entry: Entry) -> bool:
        return (
            entry.content == self.content
            and entry.link == self.link
            and entry.mblob == self.mblob
        )


class Upgrader(Protocol):
    """Brings the stored markup of one provider's entries up to date.

    `is_legacy` looks at the stored entry only, so a scan over many entries
    stays cheap. `propose` may ask the provider for a new thumbnail.
    """

    key: str
    api: str
    label: str

    def is_legacy(self, entry: Entry) -> bool: ...

    def propose(self, entry: Entry) -> Proposal: ...

    def propose_offline(self, entry: Entry) -> Proposal | None:
        """The upgrade that keeps the entry's thumbnail, when that thumbnail
        is current. It needs no request and leaves the entry looking as it
        does, so it may be applied to many entries at once."""
        ...

    def registers_media(self, entry: Entry) -> bool: ...


@dataclass(frozen=True)
class Player:
    """The video block of a stored entry, as far as an upgrade needs it."""

    video_id: str
    src: str
    width: str
    height: str


_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def find_player(content: str, provider: str) -> Player | None:
    """The first play-video block of `provider` in `content`, with either the
    old id or the data-id that replaced it, or None."""
    if 'play-video' not in content:
        return None
    m = re.search(r'\b(?:data-)?id="%s-([\w-]+)"' % re.escape(provider), content)
    if m is None:
        return None
    img = re.search(r'<img\b[^>]*>', content[m.end() :])
    attrs = dict(_ATTR.findall(img.group(0))) if img else {}
    return Player(
        video_id=m.group(1),
        src=attrs.get('src', ''),
        width=attrs.get('width', ''),
        height=attrs.get('height', ''),
    )


def thumbnail_is_current(
    player: Player, size: tuple[int, int], *, public: bool
) -> bool:
    """Whether the thumbnail is what a fresh import would show: the right
    box, and for a public service a local copy in today's format."""
    if (player.width, player.height) != (str(size[0]), str(size[1])):
        return False
    if not public:
        return player.src.startswith('https://')
    if not player.src.startswith('[GLS-THUMBS]/'):
        return False
    if not player.src.endswith(media.thumb_suffix()):
        return False
    return all(thumb_exists(rel) for rel in media.thumb_rels(player.src))


def thumb_exists(rel: str) -> bool:
    """Whether a MEDIA_ROOT-relative thumbnail is on disk."""
    return os.path.isfile(os.path.join(settings.MEDIA_ROOT, rel))


def require_thumbnail(src: str, url: str, *, public: bool, reason: str) -> str:
    """`src`, the thumbnail `localize_thumbnail` gave for `url`, once it is
    known to show. A public service needs a local copy: `save_image` hands
    back the remote URL when the download fails. A private one shows the
    remote image, so that has to answer."""
    if public:
        if not src.startswith('[GLS-THUMBS]/'):
            raise Unavailable(reason)
        return src
    try:
        r = httpclient.head(url)
    except Exception as exc:
        raise Unavailable(reason) from exc
    if r.status_code >= 400:
        raise Unavailable(reason)
    return src
