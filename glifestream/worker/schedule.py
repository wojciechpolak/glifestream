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
            day_of_week=_parse_cron_field(parts[4], 0, 7, names=CRON_DOW_NAMES, is_dow=True),
        )

    def matches(self, when: datetime.datetime) -> bool:
        local_when = timezone.localtime(when)
        cron_dow = (local_when.weekday() + 1) % 7
        dom_matches = local_when.day in self.day_of_month.values
        dow_matches = cron_dow in self.day_of_week.values

        if self.day_of_month.any_value and self.day_of_week.any_value:
            day_matches = True
        elif self.day_of_month.any_value:
            day_matches = dow_matches
        elif self.day_of_week.any_value:
            day_matches = dom_matches
        else:
            day_matches = dom_matches or dow_matches

        return (
            local_when.minute in self.minute.values
            and local_when.hour in self.hour.values
            and local_when.month in self.month.values
            and day_matches
        )

    def next_after(self, when: datetime.datetime) -> datetime.datetime:
        candidate = (when + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
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

        args_value = config.get('args', [])
        if isinstance(args_value, str):
            args = tuple(arg for arg in args_value.split() if arg.strip())
        elif isinstance(args_value, list):
            args = tuple(str(arg) for arg in args_value)
        else:
            raise ValueError('Maintenance job args must be a list or string.')

        schedule = CronSchedule.parse(schedule_expr)
        return cls(
            name=name,
            schedule=schedule,
            args=args,
            next_run_at=schedule.next_after(now),
        )

    def mark_next_run(self) -> None:
        self.next_run_at = self.schedule.next_after(self.next_run_at)


def _parse_cron_value(
    value: str,
    *,
    names: dict[str, int] | None = None,
    is_dow: bool = False,
) -> int:
    normalized = value.strip().lower()
    if names and normalized in names:
        parsed = names[normalized]
    else:
        parsed = int(normalized)

    if is_dow and parsed == 7:
        return 0
    return parsed


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
        if not token:
            continue
        step = 1
        if '/' in token:
            token, step_expr = token.split('/', 1)
            step = int(step_expr)
            if step <= 0:
                raise ValueError('Cron step must be positive.')

        if token == '*':
            start = minimum
            end = maximum
        elif '-' in token:
            start_expr, end_expr = token.split('-', 1)
            start = _parse_cron_value(start_expr, names=names, is_dow=is_dow)
            end = _parse_cron_value(end_expr, names=names, is_dow=is_dow)
        else:
            start = _parse_cron_value(token, names=names, is_dow=is_dow)
            end = start

        if start < minimum or end > maximum or start > end:
            raise ValueError('Cron value out of range.')

        values.update(range(start, end + 1, step))

    if not values:
        raise ValueError('Cron field cannot be empty.')

    return CronField(frozenset(values), any_value=False)
