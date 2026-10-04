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

# Bringing old entries up to their provider's current markup.
#
# Entries store finished HTML, so a change to a provider's renderer only
# reaches entries imported afterwards. Each upgrader compares the entries of
# one provider with what its renderer produces now, and proposes the
# difference. Nothing is written until the owner approves the proposal on
# the settings page; every applied upgrade keeps what it replaced and can be
# reverted.

from glifestream.upgrades.service import (
    UPGRADERS,
    BatchResult,
    UpgradeConflict,
    apply,
    apply_markup_only,
    candidates,
    counts,
    history,
    make_batch_token,
    make_token,
    markup_only,
    pending,
    requeue_skipped,
    revert,
    revert_batch,
    skip,
)
from glifestream.upgrades.types import Proposal, Unavailable, Upgrader

__all__ = [
    'UPGRADERS',
    'BatchResult',
    'Proposal',
    'Unavailable',
    'UpgradeConflict',
    'Upgrader',
    'apply',
    'apply_markup_only',
    'candidates',
    'counts',
    'history',
    'make_batch_token',
    'make_token',
    'markup_only',
    'pending',
    'requeue_skipped',
    'revert',
    'revert_batch',
    'skip',
]
