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

# The players of YouTube and Vimeo videos in posts.
#
# A post got a player for each video address it was written with, in the
# markup of its day: centred in a table, at 200×150. A post belongs to no
# provider, so the owner may give a video of either one for a video that
# is gone.

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote_plus

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from glifestream.filters import players
from glifestream.stream import media
from glifestream.stream.models import Entry
from glifestream.upgrades.types import (
    Field,
    Proposal,
    Unavailable,
    require_thumbnail,
    search_terms,
)


def _gone(provider: str) -> str:
    if provider == 'vimeo':
        return _(
            'Vimeo has no thumbnail of this video any more. '
            'It may have been deleted or made private. '
            'Enter the address of another copy.'
        )
    return _(
        'YouTube has no thumbnail of this video any more. '
        'It may have been deleted or made private. '
        'Enter the address of another copy.'
    )


def _strict_thumbnail(public: bool) -> players.Thumbnail:
    """The thumbnail of a video, or Unavailable saying why there is none."""

    def thumbnail(provider: str, vid: str) -> str:
        url = players.thumbnail_url(provider, vid)
        if not url:
            raise Unavailable(_gone(provider))
        return require_thumbnail(
            lambda: players.localize(url, public=public, strict=True),
            url,
            public=public,
            gone=_gone(provider),
        )

    return thumbnail


class PostVideosUpgrader:
    key = 'post-videos'
    api = 'selfposts'
    label = 'Videos in posts'
    markers: tuple[str, ...] = ('play-video',)
    # Another video for the first player, such as a copy of one now gone.
    fields: tuple[Field, ...] = (Field('video', gettext_noop('Video')),)

    def is_legacy(self, entry: Entry) -> bool:
        if not players.find_blocks(entry.content):
            return False
        proposal = self.propose_offline(entry)
        return proposal is None or not proposal.matches(entry)

    def guess(self, entry: Entry) -> dict[str, str]:
        blocks = players.find_blocks(entry.content)
        if not blocks:
            return {}
        return {'video': players.link_of(blocks[0].provider, blocks[0].video_id)}

    def field_help(self, entry: Entry, name: str, values: Mapping[str, str]) -> str:
        return 'https://www.youtube.com/results?search_query=%s' % quote_plus(
            search_terms(entry)
        )

    def propose_offline(self, entry: Entry) -> Proposal | None:
        content = players.canonical(entry.content, public=entry.service.public)
        if content is None:
            return None
        return self._proposal(entry, content)

    def propose(
        self, entry: Entry, values: Mapping[str, str] | None = None
    ) -> Proposal:
        blocks = players.find_blocks(entry.content)
        if not blocks:
            raise Unavailable(_('The entry shows no video.'))
        replace = None
        url = (values or {}).get('video', '').strip()
        if url:
            replace = players.video_of(url)
            if replace is None:
                raise Unavailable(_('That is not a YouTube or Vimeo video address.'))
        public = entry.service.public
        content = players.render(
            entry.content,
            public=public,
            thumbnail=_strict_thumbnail(public),
            replace=replace,
        )
        return self._proposal(entry, content)

    def registers_media(self, entry: Entry) -> bool:
        # As a post does: its pictures are its media.
        return True

    def _proposal(self, entry: Entry, content: str) -> Proposal:
        return Proposal(
            content=content,
            link=entry.link,
            mblob=media.mrss_with_videos(entry.mblob, content),
        )
