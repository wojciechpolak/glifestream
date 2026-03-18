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

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from glifestream.gauth.models import UserProfile


class Command(BaseCommand):
    help = 'Create an initial superuser with a forced password change on first login.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            default='admin',
            help='Username for the initial user (default: admin)',
        )
        parser.add_argument(
            '--password',
            default='admin',
            help='Password for the initial user (default: admin)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reset existing user password and re-enable forced password change.',
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        force = options['force']

        try:
            user = User.objects.get(username=username)
            if force:
                user.set_password(password)
                user.save()
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.must_change_password = True
                profile.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'User "{username}" password reset and forced password change re-enabled.'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'User "{username}" already exists. Use --force to reset.'
                    )
                )
        except User.DoesNotExist:
            user = User.objects.create_superuser(
                username=username,
                password=password,
                email='',
            )
            UserProfile.objects.create(
                user=user,
                must_change_password=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Initial superuser "{username}" created with forced password change.'
                )
            )
