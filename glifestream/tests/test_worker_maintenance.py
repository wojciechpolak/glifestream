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
import itertools
import os
import time

import pytest
from django.utils import timezone

from glifestream.stream.models import Entry, Favorite, Service
from glifestream.worker import maintenance


@pytest.fixture
def media_root(tmp_path, settings):
    """A throwaway MEDIA_ROOT with a thumbs/ tree the tests can populate."""
    settings.MEDIA_ROOT = str(tmp_path)
    (tmp_path / 'thumbs').mkdir()
    return tmp_path


def make_thumb(media_root, thumb_hash: str) -> str:
    """Write a thumbnail file and hand back its MEDIA_ROOT-relative path."""
    rel = maintenance._thumb_rel(thumb_hash)
    path = media_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'thumb')
    # Old enough that the cleanup no longer treats it as mid-import.
    then = time.time() - maintenance.ORPHAN_MIN_AGE_SEC - 60
    os.utime(path, (then, then))
    return rel


@pytest.fixture
def private_service(db):
    return Service.objects.create(
        name='Private', api='webfeed', url='http://example.com/feed', public=False
    )


_guid_counter = itertools.count(1)


def make_entry(service, *, days_old: int = 0, **kwargs) -> Entry:
    fields = {
        'title': 'Entry',
        'link': 'http://example.com/1',
        'content': '',
        'author_name': 'Someone',
        'link_image': '',
    }
    fields.update(kwargs)
    entry = Entry(service=service, guid='guid-%d' % next(_guid_counter))
    for name, value in fields.items():
        setattr(entry, name, value)
    entry.save()
    if days_old:
        stamp = timezone.now() - datetime.timedelta(days=days_old)
        Entry.objects.filter(pk=entry.pk).update(
            date_published=stamp, date_inserted=stamp
        )
        entry.refresh_from_db()
    return entry


# ---------------------------------------------------------------- thumbnails


@pytest.mark.django_db
def test_list_orphan_thumbs_reports_files_no_entry_claims(media_root):
    orphan = make_thumb(media_root, 'abc123')

    assert maintenance.list_orphan_thumbs() == [orphan]


@pytest.mark.django_db
def test_list_orphan_thumbs_ignores_dotfiles(media_root):
    (media_root / 'thumbs' / '.DS_Store').write_bytes(b'')

    assert maintenance.list_orphan_thumbs() == []


@pytest.mark.django_db
def test_list_orphan_thumbs_spares_a_thumb_used_as_a_link_image(
    media_root, private_service
):
    kept = make_thumb(media_root, 'aaa111')
    orphan = make_thumb(media_root, 'bbb222')
    make_entry(private_service, link_image='[GLS-THUMBS]/aaa111')

    assert maintenance.list_orphan_thumbs() == [orphan]
    assert (media_root / kept).exists()


@pytest.mark.django_db
def test_list_orphan_thumbs_spares_thumbs_embedded_in_entry_content(
    media_root, private_service
):
    make_thumb(media_root, 'ccc333')
    make_thumb(media_root, 'ddd444')
    orphan = make_thumb(media_root, 'eee555')
    make_entry(
        private_service,
        content='<img src="[GLS-THUMBS]/ccc333" /><img src="[GLS-THUMBS]/ddd444" />',
    )

    assert maintenance.list_orphan_thumbs() == [orphan]


@pytest.mark.django_db
def test_delete_thumb_files_removes_each_path(media_root):
    rel = make_thumb(media_root, 'fff666')

    maintenance.delete_thumb_files([rel])

    assert not (media_root / rel).exists()


@pytest.mark.django_db
def test_thumbs_delete_orphans_reports_the_count_when_verbose(media_root, capsys):
    rel = make_thumb(media_root, 'aaa777')

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(thumbs='delete-orphans'), verbose=1
    )

    assert 'Files to remove: 1' in capsys.readouterr().out
    assert not os.path.exists(str(media_root / rel))


@pytest.mark.django_db
def test_thumbs_delete_orphans_stays_quiet_without_verbose(media_root, capsys):
    make_thumb(media_root, 'aaa888')

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(thumbs='delete-orphans')
    )

    assert capsys.readouterr().out == ''


@pytest.mark.django_db
def test_thumbs_list_orphans_prints_each_path(media_root, capsys):
    rel = make_thumb(media_root, 'aaa999')

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(thumbs='list-orphans')
    )

    assert capsys.readouterr().out.strip() == rel
    assert (media_root / rel).exists()


# -------------------------------------------------------------- old entries


@pytest.mark.django_db
def test_list_old_prints_without_deleting(private_service, capsys):
    entry = make_entry(private_service, days_old=100, title='Ancient')

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(list_old_days=30)
    )

    assert 'Ancient' in capsys.readouterr().out
    assert Entry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_delete_old_removes_the_entry(private_service):
    entry = make_entry(private_service, days_old=100)

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(delete_old_days=30)
    )

    assert not Entry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_delete_old_spares_a_favorited_entry(private_service, user):
    entry = make_entry(private_service, days_old=100)
    Favorite.objects.create(user=user, entry=entry)

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(delete_old_days=30)
    )

    assert Entry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_delete_old_spares_a_protected_entry(private_service):
    entry = make_entry(private_service, days_old=100, protected=True)

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(delete_old_days=30)
    )

    assert Entry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_delete_old_never_touches_a_public_service(db):
    public = Service.objects.create(
        name='Public', api='webfeed', url='http://p/f', public=True
    )
    entry = make_entry(public, days_old=100)

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(delete_old_days=30)
    )

    assert Entry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_only_inactive_keeps_active_entries(private_service):
    active = make_entry(private_service, days_old=100, active=True)
    inactive = make_entry(private_service, days_old=100, active=False)

    maintenance.execute_maintenance_command(
        maintenance.build_maintenance_command(delete_old_days=30, only_inactive=True)
    )

    assert Entry.objects.filter(pk=active.pk).exists()
    assert not Entry.objects.filter(pk=inactive.pk).exists()


@pytest.mark.django_db
def test_execute_without_an_action_is_an_error():
    with pytest.raises(ValueError, match='must specify a cleanup action'):
        maintenance.execute_maintenance_command(maintenance.build_maintenance_command())


# ------------------------------------------------------------------ filters


@pytest.mark.django_db
def test_queryset_filters_by_a_single_service_id(private_service):
    other = Service.objects.create(name='Other', api='webfeed', url='http://o/f')
    mine = make_entry(private_service, days_old=100)
    theirs = make_entry(other, days_old=100)

    pks = {
        e.pk
        for e in maintenance.get_old_entries_queryset(
            30, filters={'id': str(private_service.pk)}
        )
    }

    assert mine.pk in pks
    assert theirs.pk not in pks


@pytest.mark.django_db
def test_queryset_filters_by_several_service_ids(private_service):
    other = Service.objects.create(name='Other', api='webfeed', url='http://o/f')
    make_entry(private_service, days_old=100)
    make_entry(other, days_old=100)

    ids = '%d,%d' % (private_service.pk, other.pk)
    queryset = maintenance.get_old_entries_queryset(30, filters={'id': ids})

    assert queryset.count() == 2


@pytest.mark.django_db
def test_queryset_filters_by_a_single_api(private_service):
    make_entry(private_service, days_old=100)

    assert (
        maintenance.get_old_entries_queryset(30, filters={'api': 'webfeed'}).count()
        == 1
    )
    assert (
        maintenance.get_old_entries_queryset(30, filters={'api': 'mastodon'}).count()
        == 0
    )


@pytest.mark.django_db
def test_queryset_filters_by_several_apis(private_service):
    make_entry(private_service, days_old=100)

    queryset = maintenance.get_old_entries_queryset(
        30, filters={'api': 'webfeed,mastodon'}
    )

    assert queryset.count() == 1


# ----------------------------------------------------------- argument parsing


def test_parse_collects_every_supported_option():
    command = maintenance.parse_maintenance_args(
        ['--api=webfeed', '--id=3', '--delete-old=90', '--only-inactive']
    )

    assert command.filters == {'api': 'webfeed', 'id': '3'}
    assert command.delete_old_days == 90
    assert command.only_inactive is True


def test_parse_accepts_the_short_filter_spellings():
    command = maintenance.parse_maintenance_args(['-a', 'flickr', '-i', '9'])

    assert command.filters == {'api': 'flickr', 'id': '9'}


@pytest.mark.parametrize(
    'option,expected',
    [
        ('--thumbs-list-orphans', 'list-orphans'),
        ('--thumbs-delete-orphans', 'delete-orphans'),
    ],
)
def test_parse_maps_both_thumbs_options(option, expected):
    assert maintenance.parse_maintenance_args([option]).thumbs == expected


def test_parse_list_old_days():
    assert maintenance.parse_maintenance_args(['--list-old=7']).list_old_days == 7


def test_parse_rejects_a_stray_positional_argument():
    with pytest.raises(ValueError, match='Unexpected maintenance args: junk'):
        maintenance.parse_maintenance_args(['--list-old=7', 'junk'])


@pytest.mark.django_db
def test_run_maintenance_args_parses_then_executes(private_service):
    entry = make_entry(private_service, days_old=100)

    maintenance.run_maintenance_args(['--delete-old=30'])

    assert not Entry.objects.filter(pk=entry.pk).exists()
