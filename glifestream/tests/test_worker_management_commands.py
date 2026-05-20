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
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from glifestream.stream.models import Entry


def test_run_worker_command_uses_extracted_worker_daemon():
    with patch('glifestream.stream.management.commands.run_worker.WorkerDaemon') as daemon_cls:
        daemon = daemon_cls.return_value
        call_command(
            'run_worker',
            '--socket-path=.test-worker.sock',
            '--workers=2',
            '--verbose-fetch=3',
        )

    daemon_cls.assert_called_once_with(
        max_workers=2,
        verbose=3,
        socket_path='.test-worker.sock',
    )
    daemon.serve.assert_called_once_with()


def test_worker_cleanup_command_deletes_old_inactive_entries(service):
    service.api = 'webfeed'
    service.public = False
    service.save()
    old_entry = Entry.objects.create(
        service=service,
        title='old',
        link='http://example.com/old',
        guid='old-guid',
        active=False,
    )
    old_entry.date_published = timezone.now() - datetime.timedelta(days=120)
    old_entry.date_inserted = timezone.now() - datetime.timedelta(days=120)
    old_entry.save(update_fields=['date_published', 'date_inserted'])

    call_command('worker_cleanup', '--delete-old=80', '--only-inactive')

    assert not Entry.objects.filter(pk=old_entry.pk).exists()


def test_worker_init_files_command_creates_runtime_paths(tmp_path):
    media_root = tmp_path / 'media'
    templates_dir = tmp_path / 'templates'
    media_root.mkdir()
    templates_dir.mkdir()

    with override_settings(
        MEDIA_ROOT=str(media_root),
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': [str(templates_dir)],
                'APP_DIRS': True,
                'OPTIONS': {'context_processors': []},
            }
        ],
    ):
        call_command('worker_init_files', stdout=StringIO())

    assert (media_root / 'upload').is_dir()
    assert (media_root / 'thumbs').is_dir()
    assert (media_root / 'thumbs' / '0').is_dir()
    assert (media_root / 'thumbs' / 'a').is_dir()
    assert (templates_dir / 'user-about.html').is_file()
    assert (templates_dir / 'user-copyright.html').is_file()
    assert (templates_dir / 'user-scripts.js').is_file()
