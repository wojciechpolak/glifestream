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

import datetime
from dataclasses import dataclass
from typing import Any

from django.utils import timezone

CRON_MONTH_NAMES = {
    'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'aug': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12,
}
CRON_DOW_NAMES = {
    'sun': 0,
    'mon': 1,
    'tue': 2,
    'wed': 3,
    'thu': 4,
    'fri': 5,
    'sat': 6,
}


@dataclass(frozen=True)
class CronField:
    values: frozenset[int]
    any_value: bool = False


@dataclass(frozen=True)
class CronSchedule:
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    @classmethod
    def parse(cls, expression: str) -> 'CronSchedule':
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError('Cron expression must have 5 fields.')

        return cls(
            minute=_parse_cron_field(parts[0], 0, 59),
            hour=_parse_cron_field(parts[1], 0, 23),
            day_of_month=_parse_cron_field(parts[2], 1, 31),
            month=_parse_cron_field(parts[3], 1, 12, names=CRON_MONTH_NAMES),
            day_of_week=_parse_cron_field(
                parts[4], 0, 7, names=CRON_DOW_NAMES, is_dow=True
            ),
        )

    def matches(self, when: datetime.datetime) -> bool:
        local_when = timezone.localtime(when)
        return (
            local_when.minute in self.minute.values
            and local_when.hour in self.hour.values
            and local_when.month in self.month.values
            and self._day_matches(local_when)
        )

    def _day_matches(self, local_when: datetime.datetime) -> bool:
        """Cron's day rule: when both day fields are restricted, either may match.

        A `*` field matches every day, so when either is `*` requiring both
        reduces to "the restricted one matches".
        """
        dom_matches = local_when.day in self.day_of_month.values
        dow_matches = (local_when.weekday() + 1) % 7 in self.day_of_week.values
        if self.day_of_month.any_value or self.day_of_week.any_value:
            return dom_matches and dow_matches
        return dom_matches or dow_matches

    def next_after(self, when: datetime.datetime) -> datetime.datetime:
        candidate = (when + datetime.timedelta(minutes=1)).replace(
            second=0, microsecond=0
        )
        limit = candidate + datetime.timedelta(days=366)
        while candidate <= limit:
            if self.matches(candidate):
                return candidate
            candidate += datetime.timedelta(minutes=1)
        raise ValueError('Unable to compute next cron occurrence within one year.')


@dataclass
class MaintenanceJob:
    name: str
    schedule: CronSchedule
    args: tuple[str, ...]
    next_run_at: datetime.datetime

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        now: datetime.datetime,
    ) -> 'MaintenanceJob':
        name = str(config.get('name') or config.get('schedule') or 'maintenance-job')
        schedule_expr = config.get('schedule')
        if not isinstance(schedule_expr, str) or not schedule_expr.strip():
            raise ValueError('Maintenance job schedule must be a non-empty string.')

        schedule = CronSchedule.parse(schedule_expr)
        return cls(
            name=name,
            schedule=schedule,
            args=_parse_job_args(config.get('args', [])),
            next_run_at=schedule.next_after(now),
        )

    def mark_next_run(self) -> None:
        self.next_run_at = self.schedule.next_after(self.next_run_at)


def _parse_job_args(value: Any) -> tuple[str, ...]:
    """Job args given either as a shell-like string or as a list."""
    if isinstance(value, str):
        return tuple(value.split())
    if isinstance(value, list):
        return tuple(str(arg) for arg in value)
    raise ValueError('Maintenance job args must be a list or string.')


def _parse_cron_value(value: str, *, names: dict[str, int] | None = None) -> int:
    normalized = value.strip().lower()
    if names and normalized in names:
        return names[normalized]
    return int(normalized)


def _parse_cron_part(
    token: str,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None = None,
) -> range:
    """One comma-separated piece of a field: `*`, `N`, `N-M`, each with `/step`."""
    step = 1
    if '/' in token:
        token, step_expr = token.split('/', 1)
        step = int(step_expr)
        if step <= 0:
            raise ValueError('Cron step must be positive.')

    if token == '*':
        start, end = minimum, maximum
    elif '-' in token:
        start_expr, end_expr = token.split('-', 1)
        start = _parse_cron_value(start_expr, names=names)
        end = _parse_cron_value(end_expr, names=names)
    else:
        start = end = _parse_cron_value(token, names=names)

    if start < minimum or end > maximum or start > end:
        raise ValueError('Cron value out of range.')
    return range(start, end + 1, step)


def _parse_cron_field(
    expression: str,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None = None,
    is_dow: bool = False,
) -> CronField:
    expression = expression.strip()
    if expression == '*':
        return CronField(frozenset(range(minimum, maximum + 1)), any_value=True)

    values: set[int] = set()
    for part in expression.split(','):
        token = part.strip()
        if token:
            values.update(_parse_cron_part(token, minimum, maximum, names=names))

    if not values:
        raise ValueError('Cron field cannot be empty.')
    if is_dow and 7 in values:
        # Sunday is both 0 and 7; fold only after ranges such as 5-7 expand.
        values = (values - {7}) | {0}
    return CronField(frozenset(values), any_value=False)
