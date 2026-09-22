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

import datetime
import logging
from collections.abc import Iterable

from django.db import transaction

from glifestream.ingestion.types import Candidate, ImportResult
from glifestream.stream import media
from glifestream.stream.models import Entry, Service

logger = logging.getLogger(__name__)


def resolve_entry(
    service: Service,
    guid: str,
    updated: datetime.datetime | None,
    *,
    force_overwrite: bool = False,
) -> Entry | None:
    """The entry to write for `guid`, or None when it should be skipped.

    An existing entry is skipped when it is protected, or when `updated`
    is no newer than what is stored (unless forcing an overwrite). Pass
    `updated=None` to skip the freshness check.
    """
    try:
        e = Entry.objects.get(service=service, guid=guid)
    except Entry.DoesNotExist:
        return Entry(service=service, guid=guid)

    if (
        not force_overwrite
        and updated is not None
        and e.date_updated
        and updated <= e.date_updated
    ):
        return None
    if e.protected:
        return None
    return e


def ingest(
    service: Service,
    candidates: Iterable[Candidate],
    *,
    force_overwrite: bool = False,
) -> ImportResult:
    """Store every candidate that is new or changed, with its media.

    If an entry cannot be stored, ingest() logs it, counts it as failed, and
    goes on with the remaining candidates.
    """
    result = ImportResult()
    for candidate in candidates:
        e = resolve_entry(
            service,
            candidate.guid,
            candidate.freshness,
            force_overwrite=force_overwrite,
        )
        if e is None:
            result.skipped += 1
            continue

        is_new = e.pk is None
        normalized = candidate.build()
        for name, value in normalized.assigned_fields().items():
            setattr(e, name, value)

        try:
            with transaction.atomic():
                e.save()
                if normalized.register_media:
                    media.extract_and_register(e)
        except Exception as exc:
            logger.exception(
                'Could not store entry %s for service %s (%s).',
                candidate.guid,
                service.pk,
                service.api,
            )
            result.failed.append((candidate.guid, str(exc)))
            continue

        if is_new:
            result.created += 1
        else:
            result.updated += 1
    return result
