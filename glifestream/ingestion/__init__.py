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
