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
import getopt
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from django.conf import settings

from glifestream.stream import media
from glifestream.stream.models import Entry, Favorite
from glifestream.utils.time import unixnow


@dataclass(frozen=True)
class MaintenanceCommand:
    filters: dict[str, Any] = field(default_factory=dict)
    list_old_days: int | None = None
    delete_old_days: int | None = None
    only_inactive: bool = False
    thumbs: str | None = None


def build_maintenance_command(
    *,
    filters: dict[str, Any] | None = None,
    list_old_days: int | None = None,
    delete_old_days: int | None = None,
    only_inactive: bool = False,
    thumbs: str | None = None,
) -> MaintenanceCommand:
    return MaintenanceCommand(
        filters=dict(filters or {}),
        list_old_days=list_old_days,
        delete_old_days=delete_old_days,
        only_inactive=only_inactive,
        thumbs=thumbs,
    )


def parse_maintenance_args(args: Sequence[str]) -> MaintenanceCommand:
    list_old: int | None = None
    delete_old: int | None = None
    only_inactive = False
    thumbs: str | None = None
    filters: dict[str, Any] = {}

    opts, extras = getopt.getopt(
        list(args),
        'i:a:',
        [
            'id=',
            'api=',
            'list-old=',
            'delete-old=',
            'only-inactive',
            'thumbs-list-orphans',
            'thumbs-delete-orphans',
        ],
    )
    if extras:
        raise ValueError('Unexpected maintenance args: %s' % ' '.join(extras))

    for option, arg in opts:
        if option in ('-a', '--api'):
            filters['api'] = arg
        elif option in ('-i', '--id'):
            filters['id'] = arg
        elif option == '--list-old':
            list_old = int(arg)
        elif option == '--delete-old':
            delete_old = int(arg)
        elif option == '--only-inactive':
            only_inactive = True
        elif option == '--thumbs-list-orphans':
            thumbs = 'list-orphans'
        elif option == '--thumbs-delete-orphans':
            thumbs = 'delete-orphans'

    return build_maintenance_command(
        filters=filters,
        list_old_days=list_old,
        delete_old_days=delete_old,
        only_inactive=only_inactive,
        thumbs=thumbs,
    )


def _run_thumbs_action(action: str, *, verbose: int) -> None:
    files = list_orphan_thumbs()
    if action == 'delete-orphans':
        if verbose:
            print('Files to remove: %d' % len(files))
        delete_thumb_files(files)
        return
    for file in files:
        print(file)


def _run_old_entries_action(command: MaintenanceCommand) -> None:
    listing = command.list_old_days is not None
    days = command.list_old_days if listing else command.delete_old_days
    assert days is not None
    queryset = get_old_entries_queryset(
        days,
        only_inactive=command.only_inactive,
        filters=command.filters,
    )
    if not listing:
        queryset.delete()
        return
    for entry in queryset:
        print('%4d "%s" by %s' % (entry.pk, entry.title, entry.author_name))


def execute_maintenance_command(
    command: MaintenanceCommand, *, verbose: int = 0
) -> None:
    if command.thumbs:
        _run_thumbs_action(command.thumbs, verbose=verbose)
    elif command.list_old_days or command.delete_old_days:
        _run_old_entries_action(command)
    else:
        raise ValueError('Maintenance job must specify a cleanup action.')


def run_maintenance_args(args: Sequence[str], *, verbose: int = 0) -> None:
    execute_maintenance_command(parse_maintenance_args(args), verbose=verbose)


def get_old_entries_queryset(
    days: int,
    *,
    only_inactive: bool = False,
    filters: dict[str, Any] | None = None,
):
    fs = dict(filters or {})
    n = time.mktime(unixnow()) - (86400 * days)
    rt = datetime.datetime.fromtimestamp(n, tz=datetime.timezone.utc)
    if 'id' in fs:
        lst = str(fs['id']).split(',')
        if len(lst) > 1:
            fs['service__id__in'] = lst
        else:
            fs['service__id'] = int(lst[0])
        del fs['id']
    elif 'api' in fs:
        lst = str(fs['api']).split(',')
        if len(lst) > 1:
            fs['service__api__in'] = lst
        else:
            fs['service__api'] = lst[0]
        del fs['api']
    fs['service__public'] = False
    fs['protected'] = False
    fs['date_published__lte'] = rt
    fs['date_inserted__lte'] = rt
    if only_inactive:
        fs['active'] = False
    favs = Favorite.objects.all().values('entry')
    return Entry.objects.filter(**fs).exclude(id__in=favs)


def _thumb_rel(thumb_hash: str) -> str:
    return str(media.get_thumb_info(thumb_hash, append_suffix=False)['rel'])


def _collect_thumb_files() -> set[str]:
    """Every thumbnail currently on disk, as a MEDIA_ROOT-relative path."""
    found: set[str] = set()
    for _root, _dirs, files in os.walk(os.path.join(settings.MEDIA_ROOT, 'thumbs')):
        found.update(_thumb_rel(file) for file in files if file[0] != '.')
    return found


def _referenced_thumbs(entry: Entry) -> set[str]:
    """The thumbnails one entry lays claim to, via link_image or its body."""
    referenced = {
        _thumb_rel(thumb_hash)
        for thumb_hash in re.findall(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', entry.content)
    }
    link_hash = media.get_thumb_hash(entry.link_image)
    if link_hash:
        referenced.add(_thumb_rel(link_hash))
    return referenced


def list_orphan_thumbs() -> list[str]:
    orphans = _collect_thumb_files()
    for entry in Entry.objects.all():
        orphans -= _referenced_thumbs(entry)
    return sorted(orphans)


def delete_thumb_files(files: Sequence[str]) -> None:
    for file in files:
        os.remove(os.path.join(settings.MEDIA_ROOT, file))
