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

# Provider-neutral entry persistence.
#
# Provider adapters in `glifestream.apis` map external payloads to
# `NormalizedEntry` values; `ingest()` decides whether each one is created,
# updated or skipped, stores it with its media, and reports an `ImportResult`.
#
# Imports are idempotent. `Entry(service, guid)` is unique, so a repeated or
# retried fetch updates or skips rows instead of adding them. If two imports
# of one service overlap and both try to insert a guid, the second one
# applies its data to the row the first one stored. Re-registering a
# thumbnail the entry already has does nothing.
#
# Each provider picks the guid. Changing how a provider builds it would
# duplicate every entry already stored, so these rules must stay stable:
#
# - webfeed: the feed item's `id`, or its `link` when it has no id.
# - flickr: built from the id of the first photo in a burst that shares one
#   timestamp. If a later fetch puts another photo first in that burst, the
#   burst becomes a second entry.
# - mastodon and pixelfed: the status URL. A reblog uses the original status
#   URL, so reblogging a post already imported updates that entry.
# - atproto: the post CID. A repost uses the original post's CID.
# - youtube: the video id, or the playlist item id for a favorite.
# - vimeo: the clip id plus the date of the like or upload. Liking a clip
#   again on a different day creates a second entry.

from glifestream.ingestion.service import ingest, resolve_entry
from glifestream.ingestion.types import (
    UNSET,
    Candidate,
    ImportResult,
    NormalizedEntry,
)

__all__ = [
    'UNSET',
    'Candidate',
    'ImportResult',
    'NormalizedEntry',
    'ingest',
    'resolve_entry',
]
