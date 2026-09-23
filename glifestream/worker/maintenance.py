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
import json
import os
import re
import time
from dataclasses import dataclass, field
from collections.abc import Iterator
from typing import Any, Sequence, cast
from urllib.parse import quote

from django.conf import settings

from glifestream.stream import media
from glifestream.stream.models import Entry, Favorite, Media
from glifestream.utils.time import unixnow


@dataclass(frozen=True)
class MaintenanceCommand:
    filters: dict[str, Any] = field(default_factory=dict)
    list_old_days: int | None = None
    delete_old_days: int | None = None
    only_inactive: bool = False
    thumbs: str | None = None
    report_orphan_uploads: bool = False


def build_maintenance_command(
    *,
    filters: dict[str, Any] | None = None,
    list_old_days: int | None = None,
    delete_old_days: int | None = None,
    only_inactive: bool = False,
    thumbs: str | None = None,
    report_orphan_uploads: bool = False,
) -> MaintenanceCommand:
    return MaintenanceCommand(
        filters=dict(filters or {}),
        list_old_days=list_old_days,
        delete_old_days=delete_old_days,
        only_inactive=only_inactive,
        thumbs=thumbs,
        report_orphan_uploads=report_orphan_uploads,
    )


def parse_maintenance_args(args: Sequence[str]) -> MaintenanceCommand:
    list_old: int | None = None
    delete_old: int | None = None
    only_inactive = False
    thumbs: str | None = None
    uploads = False
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
            'uploads-list-orphans',
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
        elif option == '--uploads-list-orphans':
            uploads = True

    return build_maintenance_command(
        filters=filters,
        list_old_days=list_old,
        delete_old_days=delete_old,
        only_inactive=only_inactive,
        thumbs=thumbs,
        report_orphan_uploads=uploads,
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
    elif command.report_orphan_uploads:
        report_orphan_uploads()
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


# A file newer than this is never an orphan. An import saves each thumbnail,
# and a selfpost each upload, before it commits the rows that claim the file.
ORPHAN_MIN_AGE_SEC = 24 * 3600


def _thumb_rel(thumb_hash: str) -> str:
    return str(media.get_thumb_info(thumb_hash, append_suffix=False)['rel'])


def _collect_files(subdir: str, *, modified_before: float) -> set[str]:
    """Files under MEDIA_ROOT/`subdir` last written before `modified_before`,
    as MEDIA_ROOT-relative paths of where they actually are."""
    found: set[str] = set()
    for root, _dirs, files in os.walk(os.path.join(settings.MEDIA_ROOT, subdir)):
        for file in files:
            if file[0] == '.':
                continue
            path = os.path.join(root, file)
            try:
                if os.path.getmtime(path) >= modified_before:
                    continue
            except FileNotFoundError:
                continue
            found.add(os.path.relpath(path, settings.MEDIA_ROOT))
    return found


def _referenced_thumbs(content: str, link_image: str) -> set[str]:
    """The thumbnails one entry lays claim to, via link_image or its body."""
    referenced = {
        _thumb_rel(thumb_hash)
        for thumb_hash in re.findall(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', content)
    }
    link_hash = media.get_thumb_hash(link_image)
    if link_hash:
        referenced.add(_thumb_rel(link_hash))
    return referenced


def list_orphan_thumbs() -> list[str]:
    orphans = _collect_files('thumbs', modified_before=time.time() - ORPHAN_MIN_AGE_SEC)
    entries = Entry.objects.values_list('content', 'link_image')
    for content, link_image in entries.iterator(chunk_size=500):
        orphans -= _referenced_thumbs(content, link_image)
    return sorted(orphans)


def _upload_needles(file: str) -> tuple[str, ...]:
    """The ways a page can spell the path of `file` under upload/."""
    path = file.removeprefix('upload/')
    return tuple({path, quote(path)})


def _entry_texts(fields: tuple[str | None, ...]) -> Iterator[str]:
    for value in fields:
        if value:
            yield value
    mblob = fields[-1]
    if mblob:
        # json.dumps escapes non-ASCII, so match the decoded form too.
        try:
            yield json.dumps(json.loads(mblob), ensure_ascii=False)
        except ValueError:
            pass


def _template_texts() -> Iterator[str]:
    """The owner's own templates, such as user-about.html, which may link to
    an upload no entry mentions."""
    for engine in cast(list[dict[str, Any]], settings.TEMPLATES):
        for directory in engine.get('DIRS', ()):
            for root, _dirs, files in os.walk(directory):
                for file in files:
                    try:
                        with open(os.path.join(root, file), errors='ignore') as fp:
                            yield fp.read()
                    except OSError:
                        continue


def list_orphan_uploads() -> list[str]:
    """Uploaded files that nothing in this installation seems to use.

    Only a report: an upload is the owner's own file and the only copy of it,
    so nothing here moves or deletes one. The test errs towards keeping a
    file: it counts as used if a Media row names it, or if its path appears
    anywhere in any entry or in the owner's templates, whatever the markup
    around it. A reshared selfpost, for one, links to the original's uploads
    from its content without a Media row of its own. Links from outside
    gLifestream cannot be seen at all.
    """
    candidates = _collect_files(
        'upload', modified_before=time.time() - ORPHAN_MIN_AGE_SEC
    )
    candidates -= set(
        Media.objects.filter(file__startswith='upload/').values_list('file', flat=True)
    )
    if not candidates:
        return []
    needles = {file: _upload_needles(file) for file in candidates}

    def claim(text: str) -> None:
        for file in [
            f for f, spellings in needles.items() if any(n in text for n in spellings)
        ]:
            del needles[file]

    entries = Entry.objects.values_list(
        'title', 'content', 'link', 'link_image', 'mblob'
    )
    for fields in entries.iterator(chunk_size=500):
        for text in _entry_texts(fields):
            claim(text)
        if not needles:
            return []
    for text in _template_texts():
        claim(text)
    return sorted(needles)


def report_orphan_uploads() -> None:
    orphans = list_orphan_uploads()
    if not orphans:
        return
    print(
        '%d uploaded file(s) are not used by any entry or template. Nothing '
        'was changed. Check for links from outside gLifestream before '
        'removing any of them by hand:' % len(orphans)
    )
    total = len(_collect_files('upload', modified_before=float('inf')))
    if len(orphans) * 2 > total:
        print(
            'Warning: that is more than half of all %d uploads. Check that '
            'the database matches MEDIA_ROOT.' % total
        )
    for file in orphans:
        print(file)


def delete_thumb_files(files: Sequence[str]) -> None:
    """Delete thumbnails, which can always be fetched again. Refuses any
    other path, so an upload can never end up here."""
    for file in files:
        if os.path.normpath(file).split(os.sep)[0] != 'thumbs':
            raise ValueError('Refusing to delete %s: not a thumbnail.' % file)
    for file in files:
        try:
            os.remove(os.path.join(settings.MEDIA_ROOT, file))
        except FileNotFoundError:
            pass
