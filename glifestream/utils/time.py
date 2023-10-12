#  gLifestream Copyright (C) 2009, 2010, 2015, 2023 Wojciech Polak
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
#  with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import calendar
from django.utils import timezone


def mtime(t) -> datetime.datetime:
    if isinstance(t, str):
        t = datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
        t = t.replace(tzinfo=timezone.utc)
        t = t.timetuple()
    d = datetime.datetime.utcfromtimestamp(calendar.timegm(t))
    d = d.replace(tzinfo=timezone.utc)
    return d


def from_rfc3339(t) -> datetime.datetime:
    t = datetime.datetime.strptime(t[0:19], '%Y-%m-%dT%H:%M:%S')
    t = t.replace(tzinfo=timezone.utc)
    t = t.timetuple()
    d = datetime.datetime.utcfromtimestamp(calendar.timegm(t))
    d = d.replace(tzinfo=timezone.utc)
    return d


def now() -> datetime.datetime:
    return timezone.now()


def utcnow() -> datetime.datetime:
    return timezone.now()


def utcnow_iso() -> str:
    return timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ')


def unixnow() -> tuple:
    return timezone.now().timetuple()


def pn_month_start(dt=None) -> tuple:
    if not dt:
        dt = datetime.datetime.today()
    dt_first = datetime.date(dt.year, dt.month, 1)

    if dt.month == 12:
        dt_last = dt.replace(day=31)
    else:
        dt_last = dt.replace(
            month=dt.month + 1, day=1) - datetime.timedelta(days=1)

    prev_last = dt_first - datetime.timedelta(days=1)
    prev_first = datetime.date(prev_last.year, prev_last.month, 1)
    next_first = dt_last + datetime.timedelta(days=1)
    return prev_first, next_first
