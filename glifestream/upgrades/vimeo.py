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

from collections.abc import Mapping

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from glifestream.apis import vimeo
from glifestream.stream.models import Entry
from glifestream.upgrades import videos
from glifestream.upgrades.types import (
    Field,
    Link,
    Proposal,
    Unavailable,
    chosen_video,
    find_player,
    thumbnail_is_current,
)


class VimeoUpgrader:
    key = 'vimeo'
    api = 'vimeo'
    label = 'Vimeo'
    markers: tuple[str, ...] = ('play-video',)
    # Another copy of a video Vimeo no longer has, there or elsewhere.
    fields: tuple[Field, ...] = (Field('video', gettext_noop('Video')),)

    def is_legacy(self, entry: Entry) -> bool:
        if find_player(entry.content, 'vimeo') is None:
            return False
        proposal = self.propose_offline(entry)
        return proposal is None or not proposal.matches(entry)

    def guess(self, entry: Entry) -> dict[str, str]:
        player = find_player(entry.content, 'vimeo')
        return {'video': vimeo.video_link(player.video_id)} if player else {}

    def field_help(
        self, entry: Entry, name: str, values: Mapping[str, str]
    ) -> list[Link]:
        return videos.searches(entry, first='vimeo')

    def propose_offline(self, entry: Entry) -> Proposal | None:
        player = find_player(entry.content, 'vimeo')
        if player is None or not thumbnail_is_current(
            player, vimeo.THUMBNAIL_SIZE, public=entry.service.public
        ):
            return None
        return videos.build(entry, 'vimeo', player.video_id, player.src)

    def propose(
        self, entry: Entry, values: Mapping[str, str] | None = None
    ) -> Proposal:
        player = find_player(entry.content, 'vimeo')
        if player is None:
            raise Unavailable(_('The entry shows no Vimeo video.'))
        provider, vid = chosen_video(values, player, 'vimeo')
        if (provider, vid) == ('vimeo', player.video_id):
            proposal = self.propose_offline(entry)
            if proposal is not None:
                return proposal
        return videos.fetch(entry, provider, vid)

    def registers_media(self, entry: Entry) -> bool:
        # As on import: an upload registers its thumbnail, a like does not.
        return entry.idata != 'liked'
