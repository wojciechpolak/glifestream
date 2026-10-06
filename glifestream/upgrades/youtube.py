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
from urllib.parse import quote_plus

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from glifestream.apis import youtube
from glifestream.filters.expand import youtube_video_id
from glifestream.stream.models import Entry
from glifestream.upgrades.types import (
    Field,
    Proposal,
    Unavailable,
    chosen_video,
    find_player,
    require_thumbnail,
    search_terms,
    thumbnail_is_current,
)


class YoutubeUpgrader:
    key = 'youtube'
    api = 'youtube'
    label = 'YouTube'
    markers: tuple[str, ...] = ('play-video',)
    # Another copy of a video YouTube no longer has.
    fields: tuple[Field, ...] = (Field('video', gettext_noop('YouTube video')),)

    def is_legacy(self, entry: Entry) -> bool:
        if find_player(entry.content, 'youtube') is None:
            return False
        proposal = self.propose_offline(entry)
        return proposal is None or not proposal.matches(entry)

    def guess(self, entry: Entry) -> dict[str, str]:
        player = find_player(entry.content, 'youtube')
        return {'video': youtube.video_link(player.video_id)} if player else {}

    def field_help(self, entry: Entry, name: str, values: Mapping[str, str]) -> str:
        return 'https://www.youtube.com/results?search_query=%s' % quote_plus(
            search_terms(entry)
        )

    def propose_offline(self, entry: Entry) -> Proposal | None:
        player = find_player(entry.content, 'youtube')
        if player is None or not thumbnail_is_current(
            player, youtube.THUMBNAIL_SIZE, public=entry.service.public
        ):
            return None
        return self._build(player.video_id, player.src)

    def propose(
        self, entry: Entry, values: Mapping[str, str] | None = None
    ) -> Proposal:
        player = find_player(entry.content, 'youtube')
        if player is None:
            raise Unavailable(_('The entry shows no YouTube video.'))
        vid = chosen_video(
            values,
            player,
            youtube_video_id,
            _('That is not a YouTube video address.'),
        )
        if vid == player.video_id:
            proposal = self.propose_offline(entry)
            if proposal is not None:
                return proposal
        public = entry.service.public

        tn = youtube.pick_thumbnail(youtube.thumbnails_of(vid))
        assert tn is not None
        src = require_thumbnail(
            lambda: youtube.localize_thumbnail(tn, public=public, strict=True),
            tn['url'],
            public=public,
            gone=_(
                'YouTube has no thumbnail of this video any more. '
                'It may have been deleted or made private. '
                'Enter the address of another copy.'
            ),
        )
        return self._build(vid, src)

    def registers_media(self, entry: Entry) -> bool:
        # A YouTube import never registers its thumbnail as Media.
        return False

    def _build(self, vid: str, src: str) -> Proposal:
        link = youtube.video_link(vid)
        width, height = youtube.THUMBNAIL_SIZE
        return Proposal(
            content=youtube.player_html(vid, link, src, width, height),
            link=link,
            # The Flash and RTSP media of the old GData API died with it.
            mblob=None,
        )
