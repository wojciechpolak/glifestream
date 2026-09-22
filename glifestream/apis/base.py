"""
# gLifestream Copyright (C) 2025 Wojciech Polak
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
from abc import ABC, abstractmethod
from collections.abc import Iterable
import datetime
import warnings
from django.utils.html import strip_tags
from glifestream import ingestion
from glifestream.filters import truncate
from glifestream.ingestion import Candidate, ImportResult, NormalizedEntry
from glifestream.stream.models import Entry, Service
from glifestream.utils.html import strip_entities


class BaseService(ABC):
    """
    The base interface for all service strategies.
    Each concrete service defines its logic in `run(...)`.
    """

    name: str
    limit_sec: int
    payload: str | bytes | None = None

    def __init__(
        self, service: Service, verbose: int = 0, force_overwrite: bool = False
    ):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        # Totals across every `ingest()` call during this run.
        self.last_result = ImportResult()
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    @abstractmethod
    def run(self) -> None:
        pass

    def get_urls(self) -> list[str]:
        return []

    def ingest(self, candidates: Iterable[Candidate]) -> ImportResult:
        """Store `candidates` for this service and add them to `last_result`."""
        result = ingestion.ingest(
            self.service, candidates, force_overwrite=self.force_overwrite
        )
        self.last_result += result
        return result

    def resolve_entry(
        self, guid: str, updated: datetime.datetime | None
    ) -> Entry | None:
        """Deprecated. Yield `Candidate` objects to `ingest()` instead."""
        warnings.warn(
            'BaseService.resolve_entry() is deprecated; pass Candidate objects '
            'to BaseService.ingest() instead.',
            DeprecationWarning,
            stacklevel=2,
        )
        return ingestion.resolve_entry(
            self.service, guid, updated, force_overwrite=self.force_overwrite
        )

    def get_base_url(self) -> str | None:
        return None

    def get_authorize_url(self) -> str | None:
        return None

    def get_token_url(self) -> str | None:
        return None


def post_title(html: str) -> str:
    """A short plain-text title for a microblog post's HTML body."""
    title = truncate.smart(strip_entities(strip_tags(html)), max_length=40)
    return title.replace('#', '').replace('@', '')


def set_reblog(
    e: Entry | NormalizedEntry, reblog: bool, by: str = '', uri: str = ''
) -> None:
    """Mark `e` as reshared by `by`, or clear any earlier reshare."""
    e.reblog = reblog
    e.reblog_by = by if reblog else ''
    e.reblog_uri = uri if reblog else ''
