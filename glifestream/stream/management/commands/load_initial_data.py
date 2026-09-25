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

from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand

from glifestream.stream.models import Service

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures'


class Command(BaseCommand):
    help = (
        'Load the starting services and a welcome entry into an empty database; '
        'a database that has any service is left as it is.'
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--no-welcome',
            action='store_true',
            help='Load only the services, so that your first own entry gets ID 1.',
        )

    def handle(self, *args, **options) -> None:
        del args
        if Service.objects.exists():
            self.stdout.write('Services exist, leaving the database as it is.')
            return
        fixtures = ['initial_data.json']
        if not options['no_welcome']:
            fixtures.append('welcome.json')
        call_command(
            'loaddata',
            *(str(FIXTURES / name) for name in fixtures),
            verbosity=options['verbosity'],
        )
