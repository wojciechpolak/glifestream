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

from django.utils.translation import gettext as _

from glifestream.apis import vimeo
from glifestream.stream.models import Entry
from glifestream.upgrades.types import (
    Proposal,
    Unavailable,
    find_player,
    require_thumbnail,
    thumbnail_is_current,
)
from glifestream.utils import oembed

# Twice the shown box, which `save_image` scales down as an import does.
_OEMBED_WIDTH = 640


class VimeoUpgrader:
    key = 'vimeo'
    api = 'vimeo'
    label = 'Vimeo'

    def is_legacy(self, entry: Entry) -> bool:
        if find_player(entry.content, 'vimeo') is None:
            return False
        proposal = self.propose_offline(entry)
        return proposal is None or not proposal.matches(entry)

    def propose_offline(self, entry: Entry) -> Proposal | None:
        player = find_player(entry.content, 'vimeo')
        if player is None or not thumbnail_is_current(
            player, vimeo.THUMBNAIL_SIZE, public=entry.service.public
        ):
            return None
        return self._build(entry, player.video_id, player.src)

    def propose(self, entry: Entry) -> Proposal:
        proposal = self.propose_offline(entry)
        if proposal is not None:
            return proposal
        player = find_player(entry.content, 'vimeo')
        if player is None:
            raise Unavailable(_('The entry shows no Vimeo video.'))
        public = entry.service.public

        gone = _(
            'Vimeo has no thumbnail of this video any more. '
            'It may have been deleted or made private.'
        )
        data = oembed.discover(
            vimeo.video_link(player.video_id), 'vimeo', maxwidth=_OEMBED_WIDTH
        )
        url = data.get('thumbnail_url') if isinstance(data, dict) else None
        if not url:
            raise Unavailable(gone)
        src = require_thumbnail(
            vimeo.localize_thumbnail(url, public=public),
            url,
            public=public,
            reason=gone,
        )
        return self._build(entry, player.video_id, src)

    def registers_media(self, entry: Entry) -> bool:
        # As on import: an upload registers its thumbnail, a like does not.
        return entry.idata != 'liked'

    def _build(self, entry: Entry, video_id: str, src: str) -> Proposal:
        link = vimeo.video_link(video_id)
        return Proposal(
            content=vimeo.player_html(video_id, link, entry.title, src),
            link=link,
            mblob=vimeo.player_mblob(video_id),
        )
