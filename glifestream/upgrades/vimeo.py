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

from glifestream.apis import vimeo
from glifestream.filters.expand import vimeo_video_id
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
from glifestream.utils import oembed

# Twice the shown box, which `save_image` scales down as an import does.
_OEMBED_WIDTH = 640


class VimeoUpgrader:
    key = 'vimeo'
    api = 'vimeo'
    label = 'Vimeo'
    markers: tuple[str, ...] = ('play-video',)
    # Another copy of a video Vimeo no longer has.
    fields: tuple[Field, ...] = (Field('video', gettext_noop('Vimeo video')),)

    def is_legacy(self, entry: Entry) -> bool:
        if find_player(entry.content, 'vimeo') is None:
            return False
        proposal = self.propose_offline(entry)
        return proposal is None or not proposal.matches(entry)

    def guess(self, entry: Entry) -> dict[str, str]:
        player = find_player(entry.content, 'vimeo')
        return {'video': vimeo.video_link(player.video_id)} if player else {}

    def field_help(self, entry: Entry, name: str, values: Mapping[str, str]) -> str:
        return 'https://vimeo.com/search?q=%s' % quote_plus(search_terms(entry))

    def propose_offline(self, entry: Entry) -> Proposal | None:
        player = find_player(entry.content, 'vimeo')
        if player is None or not thumbnail_is_current(
            player, vimeo.THUMBNAIL_SIZE, public=entry.service.public
        ):
            return None
        return self._build(entry, player.video_id, player.src)

    def propose(
        self, entry: Entry, values: Mapping[str, str] | None = None
    ) -> Proposal:
        player = find_player(entry.content, 'vimeo')
        if player is None:
            raise Unavailable(_('The entry shows no Vimeo video.'))
        vid = chosen_video(
            values, player, vimeo_video_id, _('That is not a Vimeo video address.')
        )
        if vid == player.video_id:
            proposal = self.propose_offline(entry)
            if proposal is not None:
                return proposal
        public = entry.service.public

        gone = _(
            'Vimeo has no thumbnail of this video any more. '
            'It may have been deleted or made private. '
            'Enter the address of another copy.'
        )
        data = oembed.discover(vimeo.video_link(vid), 'vimeo', maxwidth=_OEMBED_WIDTH)
        url = data.get('thumbnail_url') if isinstance(data, dict) else None
        if not url:
            raise Unavailable(gone)
        src = require_thumbnail(
            lambda: vimeo.localize_thumbnail(url, public=public, strict=True),
            url,
            public=public,
            gone=gone,
        )
        return self._build(entry, vid, src)

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
