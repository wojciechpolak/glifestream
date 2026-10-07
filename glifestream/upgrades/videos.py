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

# The video of an imported YouTube or Vimeo entry, as an upgrade gives it.
#
# A video one provider no longer has may live on at the other, so the
# upgrader of either provider may give its entry a video of both.

from __future__ import annotations

from urllib.parse import quote_plus

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from glifestream.apis import vimeo, youtube
from glifestream.stream.models import Entry
from glifestream.upgrades.types import (
    Link,
    Proposal,
    Unavailable,
    require_thumbnail,
    search_terms,
)
from glifestream.utils import oembed

# Twice the shown box, which `save_image` scales down as an import does.
_OEMBED_WIDTH = 640


def build(entry: Entry, provider: str, vid: str, src: str) -> Proposal:
    """The upgrade that shows video `vid` of `provider` with thumbnail
    `src`, in the markup that provider's import makes."""
    if provider == 'youtube':
        link = youtube.video_link(vid)
        width, height = youtube.THUMBNAIL_SIZE
        return Proposal(
            content=youtube.player_html(vid, link, src, width, height),
            link=link,
            # The Flash and RTSP media of the old GData API died with it.
            mblob=None,
        )
    link = vimeo.video_link(vid)
    return Proposal(
        content=vimeo.player_html(vid, link, entry.title, src),
        link=link,
        mblob=vimeo.player_mblob(vid),
    )


def fetch(entry: Entry, provider: str, vid: str) -> Proposal:
    """The upgrade that shows video `vid` of `provider` with a thumbnail
    fetched from that provider."""
    public = entry.service.public
    if provider == 'youtube':
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
        return build(entry, provider, vid, src)

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
    return build(entry, provider, vid, src)


def searches(entry: Entry, first: str) -> list[Link]:
    """Searches of YouTube and Vimeo for the video of `entry`, that of
    provider `first` first."""
    q = quote_plus(search_terms(entry))
    links = [
        Link(
            gettext_noop('Search YouTube'),
            'https://www.youtube.com/results?search_query=%s' % q,
        ),
        Link(gettext_noop('Search Vimeo'), 'https://vimeo.com/search?q=%s' % q),
    ]
    return links[::-1] if first == 'vimeo' else links
