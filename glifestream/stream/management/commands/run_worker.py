"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
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

from django.conf import settings
from django.core.management.base import BaseCommand

from glifestream.worker.daemon import WorkerDaemon


class Command(BaseCommand):
    help = 'Run the long-lived background fetch and maintenance worker.'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--socket-path',
            default=settings.WORKER_SOCKET,
            help='Path to the Unix datagram socket used to wake the worker.',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=settings.WORKER_POOL_SIZE,
            help='Maximum number of concurrent fetches to run per batch.',
        )
        parser.add_argument(
            '--verbose-fetch',
            type=int,
            default=0,
            help='Pass-through verbosity level for service fetchers.',
        )

    def handle(self, *args, **options) -> None:
        daemon = WorkerDaemon(
            max_workers=options['workers'],
            verbose=options['verbose_fetch'],
            socket_path=options['socket_path'],
        )
        daemon.serve()
