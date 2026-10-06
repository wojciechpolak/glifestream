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

import html
import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

from glifestream.stream import media
from glifestream.stream.models import Entry
from glifestream.utils import httpclient

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class Field:
    """Something the owner tells an upgrader that it cannot find out, such
    as which video plays a track. The review page asks for it."""

    name: str
    # The untranslated label; the review page translates it.
    label: str


class Upgrader(Protocol):
    """Brings the stored markup of one provider's entries up to date.

    `is_legacy` looks at the stored entry only, so a scan over many entries
    stays cheap. `propose` may ask the provider for a new thumbnail.
    """

    key: str
    api: str
    label: str
    # Text one of the entries it upgrades contains, to narrow the scan.
    markers: tuple[str, ...]
    # What the owner fills in for each entry; none for most upgraders.
    fields: tuple[Field, ...]

    def is_legacy(self, entry: Entry) -> bool: ...

    def guess(self, entry: Entry) -> dict[str, str]:
        """The values of `fields` the upgrader finds in the entry, to start
        the owner's form with."""
        ...

    def field_help(self, entry: Entry, name: str, values: Mapping[str, str]) -> str:
        """The address of a page that helps the owner fill in field `name`
        of `entry`, such as a search, or ''."""
        ...

    def propose(
        self, entry: Entry, values: Mapping[str, str] | None = None
    ) -> Proposal:
        """The upgrade of `entry`, made with the owner's `values` of
        `fields` when it has any."""
        ...

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


def chosen_video(
    values: Mapping[str, str] | None,
    player: Player,
    video_id: Callable[[str], str | None],
    invalid: str,
) -> str:
    """The id of the video the owner entered in the `video` field, or of
    the one `player` shows when the field is empty."""
    url = (values or {}).get('video', '').strip()
    if not url:
        return player.video_id
    vid = video_id(url)
    if vid is None:
        raise Unavailable(invalid)
    return vid


def search_terms(entry: Entry) -> str:
    """The title of `entry` as plain words, to search for it with."""
    return ' '.join(html.unescape(strip_tags(entry.title)).split())


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


# What a provider answers for an image it does not have.
_GONE = (404, 410)


def thumbnail_failure(exc: Exception, gone: str) -> str:
    """Why a thumbnail could not be had, for the owner: `gone` when the
    provider has no such image, else the failure itself, such as a
    thumbnail directory the web server cannot write to."""
    if isinstance(exc, httpclient.FetchError) and exc.status_code in _GONE:
        return gone
    logger.warning('Upgrade thumbnail failed: %s', exc)
    return _('The thumbnail could not be saved: %s') % exc


def require_thumbnail(
    localize: Callable[[], str], url: str, *, public: bool, gone: str
) -> str:
    """The thumbnail `localize` gives for `url`, once it is known to show.

    A public service needs a local copy, which `localize` makes or raises
    for. A private one shows the remote image, so that has to answer.
    """
    try:
        src = localize()
        if not public:
            r = httpclient.head(url)
            if r.status_code in _GONE:
                raise Unavailable(gone)
            if r.status_code >= 400:
                raise Unavailable(
                    _('The thumbnail could not be fetched: HTTP %d.') % r.status_code
                )
    except Unavailable:
        raise
    except Exception as exc:
        raise Unavailable(thumbnail_failure(exc, gone)) from exc
    if public and not src.startswith('[GLS-THUMBS]/'):
        raise Unavailable(_('The thumbnail could not be saved.'))
    return src
