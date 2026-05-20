"""
#  gLifestream Copyright (C) 2009-2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

from typing import Any

DEFAULT_WORKER_MAINTENANCE_JOBS: tuple[dict[str, Any], ...] = (
    {
        'name': 'delete-inactive-old-entries',
        'schedule': '5 9 * * 0',
        'args': ['--only-inactive', '--delete-old=80'],
    },
    {
        'name': 'delete-old-entries',
        'schedule': '6 9 1 * *',
        'args': ['--delete-old=365'],
    },
    {
        'name': 'delete-orphan-thumbnails',
        'schedule': '7 9 1 * *',
        'args': ['--thumbs-delete-orphans'],
    },
)
