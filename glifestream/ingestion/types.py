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
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any


class _Unset:
    def __repr__(self) -> str:
        return 'UNSET'


# Marks a field the provider left alone. An update keeps its stored value.
UNSET: Any = _Unset()


@dataclass(eq=False)
class NormalizedEntry:
    """One imported item, in `Entry` field names, before it is stored.

    Ingestion writes only the fields a provider assigns. The rest keep the
    stored value, or the model default for a new entry.
    """

    guid: str
    title: str = UNSET
    link: str = UNSET
    link_image: str = UNSET
    content: str = UNSET
    date_published: datetime.datetime = UNSET
    date_updated: datetime.datetime = UNSET
    author_name: str = UNSET
    author_email: str = UNSET
    author_uri: str = UNSET
    geolat: Decimal | str | None = UNSET
    geolng: Decimal | str | None = UNSET
    idata: str = UNSET
    mblob: str | None = UNSET
    reblog: bool = UNSET
    reblog_by: str = UNSET
    reblog_uri: str = UNSET
    register_media: bool = True

    def assigned_fields(self) -> dict[str, Any]:
        """The `Entry` fields to write, by name."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in ('guid', 'register_media')
            and getattr(self, f.name) is not UNSET
        }


@dataclass(frozen=True)
class Candidate:
    """An item a provider offers for import.

    Ingestion compares `freshness` with the stored entry's `date_updated` to
    decide whether the item changed. None skips that check. Ingestion calls
    `build` only for items it will write, so a skipped item downloads no media.
    """

    guid: str
    freshness: datetime.datetime | None
    build: Callable[[], NormalizedEntry]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    def __add__(self, other: ImportResult) -> ImportResult:
        return ImportResult(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            skipped=self.skipped + other.skipped,
            failed=self.failed + other.failed,
        )

    def count(self, outcome: str) -> None:
        """Add one to the `created`, `updated` or `skipped` counter."""
        if outcome not in ('created', 'updated', 'skipped'):
            raise ValueError('Unknown import outcome: %r' % outcome)
        setattr(self, outcome, getattr(self, outcome) + 1)

    def summary(self) -> str:
        return 'created=%d updated=%d skipped=%d failed=%d' % (
            self.created,
            self.updated,
            self.skipped,
            len(self.failed),
        )
