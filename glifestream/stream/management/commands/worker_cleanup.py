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

from django.core.management.base import BaseCommand

from glifestream.worker.maintenance import run_maintenance_args


class Command(BaseCommand):
    help = 'Run worker cleanup actions such as old-entry pruning and thumbnail cleanup.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('-i', '--id', help='Restrict cleanup to a service id or comma list.')
        parser.add_argument(
            '-a',
            '--api',
            help='Restrict cleanup to an API name or comma list.',
        )
        parser.add_argument('--list-old', type=int, help='List entries older than DAYS.')
        parser.add_argument('--delete-old', type=int, help='Delete entries older than DAYS.')
        parser.add_argument(
            '--only-inactive',
            action='store_true',
            help='Match only inactive entries for age-based cleanup.',
        )
        parser.add_argument(
            '--thumbs-list-orphans',
            action='store_true',
            help='List orphaned thumbnail files.',
        )
        parser.add_argument(
            '--thumbs-delete-orphans',
            action='store_true',
            help='Delete orphaned thumbnail files.',
        )

    def handle(self, *args, **options) -> None:
        maintenance_args: list[str] = []
        if options.get('id'):
            maintenance_args.append('--id=%s' % options['id'])
        if options.get('api'):
            maintenance_args.append('--api=%s' % options['api'])
        if options.get('list_old') is not None:
            maintenance_args.append('--list-old=%d' % options['list_old'])
        if options.get('delete_old') is not None:
            maintenance_args.append('--delete-old=%d' % options['delete_old'])
        if options.get('only_inactive'):
            maintenance_args.append('--only-inactive')
        if options.get('thumbs_list_orphans'):
            maintenance_args.append('--thumbs-list-orphans')
        if options.get('thumbs_delete_orphans'):
            maintenance_args.append('--thumbs-delete-orphans')

        run_maintenance_args(maintenance_args, verbose=int(options['verbosity']))
