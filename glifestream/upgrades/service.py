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

import hashlib
import json
import uuid
from dataclasses import dataclass

from django.core import signing
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from glifestream.stream import media
from glifestream.stream.models import Entry, EntryUpgrade, Media
from glifestream.upgrades.music import MusicUpgrader
from glifestream.upgrades.post_videos import PostVideosUpgrader
from glifestream.upgrades.types import Proposal, Upgrader, thumb_exists
from glifestream.upgrades.vimeo import VimeoUpgrader
from glifestream.upgrades.youtube import YoutubeUpgrader

# Upgraders by key. Adding a provider means adding its upgrader here.
UPGRADERS: dict[str, Upgrader] = {
    u.key: u
    for u in (
        YoutubeUpgrader(),
        VimeoUpgrader(),
        MusicUpgrader(),
        PostVideosUpgrader(),
    )
}

_SALT = 'glifestream.upgrades'
_BATCH_SALT = 'glifestream.upgrades.markup-only'

# How long a preview can be applied after it was shown.
TOKEN_MAX_AGE_SEC = 24 * 3600


class UpgradeConflict(Exception):
    """An upgrade or revert that would not do what the owner saw, so it is
    refused. The message says why, for the owner."""


def candidates(upgrader: Upgrader) -> QuerySet[Entry]:
    """Entries of the upgrader's provider that might be legacy, oldest first,
    leaving out the ones the owner skipped."""
    skipped = EntryUpgrade.objects.filter(
        upgrader=upgrader.key, status=EntryUpgrade.STATUS_SKIPPED
    ).values('entry_id')
    marked = Q()
    for marker in upgrader.markers:
        marked |= Q(content__contains=marker)
    return (
        Entry.objects.filter(marked, service__api=upgrader.api)
        .exclude(pk__in=skipped)
        .select_related('service')
        .order_by('date_published', 'id')
    )


def pending(upgrader: Upgrader) -> list[Entry]:
    """The entries still waiting for the owner, oldest first."""
    return [
        e
        for e in candidates(upgrader).iterator(chunk_size=200)
        if upgrader.is_legacy(e)
    ]


def markup_only(
    upgrader: Upgrader, queue: list[Entry] | None = None
) -> list[tuple[Entry, Proposal]]:
    """The waiting entries whose upgrade keeps their thumbnail, each with
    that upgrade. They look as they do now, so the owner may apply them all
    at once."""
    found = []
    for entry in pending(upgrader) if queue is None else queue:
        proposal = upgrader.propose_offline(entry)
        if proposal is not None and not proposal.matches(entry):
            found.append((entry, proposal))
    return found


def counts(upgrader: Upgrader) -> dict[str, int]:
    decided = EntryUpgrade.objects.filter(upgrader=upgrader.key)
    queue = pending(upgrader)
    return {
        'pending': len(queue),
        'markup_only': len(markup_only(upgrader, queue)),
        'applied': decided.filter(status=EntryUpgrade.STATUS_APPLIED).count(),
        'skipped': decided.filter(status=EntryUpgrade.STATUS_SKIPPED).count(),
    }


def state_hash(entry: Entry) -> str:
    """A digest of the fields an upgrade replaces, to notice a change made
    between a preview and its approval."""
    state = json.dumps([entry.content, entry.link, entry.mblob])
    return hashlib.sha256(state.encode('utf-8')).hexdigest()


def make_token(entry: Entry, upgrader: Upgrader, proposal: Proposal) -> str:
    """The signed approval of exactly `proposal` for `entry` as it is now.

    The preview hands it to the owner's form, so applying stores what the
    owner saw without keeping the proposal anywhere in between.
    """
    return signing.dumps(
        {
            'e': entry.pk,
            'u': upgrader.key,
            'h': state_hash(entry),
            'c': proposal.content,
            'l': proposal.link,
            'm': proposal.mblob,
        },
        salt=_SALT,
        compress=True,
    )


def apply(token: str) -> EntryUpgrade:
    try:
        data = signing.loads(token, salt=_SALT, max_age=TOKEN_MAX_AGE_SEC)
    except signing.BadSignature as exc:
        raise UpgradeConflict(
            _('This preview has expired or is not valid. Review the entry again.')
        ) from exc
    upgrader = UPGRADERS.get(data.get('u'))
    if upgrader is None:
        raise UpgradeConflict(_('Unknown upgrader.'))
    proposal = Proposal(content=data['c'], link=data['l'], mblob=data['m'])

    with transaction.atomic():
        entry = Entry.objects.select_for_update().filter(pk=data['e']).first()
        if entry is None:
            raise UpgradeConflict(_('The entry no longer exists.'))
        if state_hash(entry) != data['h']:
            raise UpgradeConflict(
                _(
                    'The entry changed after its preview was shown. '
                    'Nothing was saved; review it again.'
                )
            )
        if not all(thumb_exists(rel) for rel in media.thumb_rels(proposal.content)):
            raise UpgradeConflict(
                _(
                    'The new thumbnail is missing. Nothing was saved; '
                    'review the entry again.'
                )
            )
        return _store(entry, upgrader, proposal)


def _store(
    entry: Entry, upgrader: Upgrader, proposal: Proposal, batch: str = ''
) -> EntryUpgrade:
    """Write `proposal` to the locked `entry`, keeping what it replaces.

    Only the fields an upgrade owns are written: the dates stay, and with
    them the entry's place in the stream.
    """
    upgrade = EntryUpgrade.objects.create(
        entry=entry,
        upgrader=upgrader.key,
        status=EntryUpgrade.STATUS_APPLIED,
        old_content=entry.content,
        old_link=entry.link,
        old_mblob=entry.mblob,
        new_content=proposal.content,
        new_link=proposal.link,
        new_mblob=proposal.mblob,
        batch=batch,
    )
    entry.content = proposal.content
    entry.link = proposal.link
    entry.mblob = proposal.mblob
    entry.save(update_fields=['content', 'link', 'mblob'])
    if upgrader.registers_media(entry):
        media.extract_and_register(entry)
    return upgrade


@dataclass(frozen=True)
class BatchResult:
    batch: str
    applied: int
    # Entries changed since the owner saw the list, left as they are.
    refused: int


def make_batch_token(upgrader: Upgrader, entries: list[Entry]) -> str:
    """The signed approval of the markup-only upgrade of `entries` as they
    are now."""
    return signing.dumps(
        {'u': upgrader.key, 'e': [[e.pk, state_hash(e)] for e in entries]},
        salt=_BATCH_SALT,
        compress=True,
    )


def apply_markup_only(token: str) -> BatchResult:
    """Apply the markup-only upgrade of every entry the owner approved.

    Each entry is checked and written on its own: one that changed since the
    list was shown, or whose upgrade would now need a new thumbnail, is left
    alone and counted as refused. The upgrades share a batch, so they can be
    reverted together.
    """
    try:
        data = signing.loads(token, salt=_BATCH_SALT, max_age=TOKEN_MAX_AGE_SEC)
    except signing.BadSignature as exc:
        raise UpgradeConflict(
            _('This list has expired or is not valid. Open it again.')
        ) from exc
    upgrader = UPGRADERS.get(data.get('u'))
    if upgrader is None:
        raise UpgradeConflict(_('Unknown upgrader.'))

    batch = uuid.uuid4().hex
    applied = refused = 0
    for pk, approved_hash in data['e']:
        with transaction.atomic():
            entry = Entry.objects.select_for_update().filter(pk=pk).first()
            proposal = (
                upgrader.propose_offline(entry)
                if entry is not None and state_hash(entry) == approved_hash
                else None
            )
            if entry is None or proposal is None or proposal.matches(entry):
                refused += 1
                continue
            _store(entry, upgrader, proposal, batch)
            applied += 1
    return BatchResult(batch=batch, applied=applied, refused=refused)


def skip(entry: Entry, upgrader: Upgrader) -> EntryUpgrade:
    """Keep the entry as it is and stop offering it."""
    return EntryUpgrade.objects.create(
        entry=entry,
        upgrader=upgrader.key,
        status=EntryUpgrade.STATUS_SKIPPED,
        old_content=entry.content,
        old_link=entry.link,
        old_mblob=entry.mblob,
    )


def requeue_skipped(upgrader: Upgrader) -> int:
    """Offer the skipped entries again."""
    deleted, _rows = EntryUpgrade.objects.filter(
        upgrader=upgrader.key, status=EntryUpgrade.STATUS_SKIPPED
    ).delete()
    return deleted


def revert(upgrade_id: int) -> EntryUpgrade:
    """Put back what an applied upgrade replaced. The entry then waits in
    the queue again.

    Refused once the entry changed after the upgrade, so a later edit is
    never lost.
    """
    with transaction.atomic():
        upgrade = (
            EntryUpgrade.objects.select_for_update()
            .filter(pk=upgrade_id, status=EntryUpgrade.STATUS_APPLIED)
            .first()
        )
        if upgrade is None:
            raise UpgradeConflict(_('There is no such upgrade to revert.'))
        entry = Entry.objects.select_for_update().get(pk=upgrade.entry_id)
        if (entry.content, entry.link, entry.mblob) != (
            upgrade.new_content,
            upgrade.new_link,
            upgrade.new_mblob,
        ):
            raise UpgradeConflict(
                _(
                    'The entry changed after the upgrade, so reverting it '
                    'would lose that change. Nothing was reverted.'
                )
            )
        added = media.thumb_rels(upgrade.new_content) - media.thumb_rels(
            upgrade.old_content
        )
        entry.content = upgrade.old_content
        entry.link = upgrade.old_link
        entry.mblob = upgrade.old_mblob
        entry.save(update_fields=['content', 'link', 'mblob'])
        if added:
            Media.objects.filter(entry=entry, file__in=added).delete()
        upgrade.status = EntryUpgrade.STATUS_REVERTED
        upgrade.reverted_at = timezone.now()
        upgrade.save(update_fields=['status', 'reverted_at'])
    return upgrade


def revert_batch(batch: str) -> tuple[int, int]:
    """Revert every upgrade of a batch that still stands. Returns how many
    were reverted and how many were refused because their entry changed."""
    if not batch:
        return 0, 0
    reverted = refused = 0
    ids = EntryUpgrade.objects.filter(
        batch=batch, status=EntryUpgrade.STATUS_APPLIED
    ).values_list('pk', flat=True)
    for pk in list(ids):
        try:
            revert(pk)
        except UpgradeConflict:
            refused += 1
        else:
            reverted += 1
    return reverted, refused


def history(limit: int = 20) -> QuerySet[EntryUpgrade]:
    """The latest upgrades applied or reverted, newest first."""
    return EntryUpgrade.objects.filter(
        status__in=(EntryUpgrade.STATUS_APPLIED, EntryUpgrade.STATUS_REVERTED)
    ).select_related('entry', 'entry__service')[:limit]
