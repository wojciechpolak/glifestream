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

import os
import secrets

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from glifestream.gauth.models import UserProfile

# The password older releases gave the initial administrator.
LEGACY_PASSWORD = 'admin'


class Command(BaseCommand):
    help = (
        'Create an initial superuser with a forced password change on first '
        'login. Without a password given, one is generated and printed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            default='admin',
            help='Username for the initial user (default: admin)',
        )
        parser.add_argument(
            '--password',
            help='Initial password, else INITIAL_ADMIN_PASSWORD, else a generated one.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reset existing user password and re-enable forced password change.',
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password'] or os.environ.get('INITIAL_ADMIN_PASSWORD')

        user = User.objects.filter(username=username).first()
        if user is None:
            user = User(username=username, email='')
            password = self._password_for(password, user)
            user = User.objects.create_superuser(
                username=username,
                password=password,
                email='',
            )
            UserProfile.objects.create(user=user, must_change_password=True)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Initial superuser "{username}" created with forced password change.'
                )
            )
            return

        # An account still on the old default password is reset as if with
        # --force, so an upgrade does not leave it open to anyone.
        legacy = user.check_password(LEGACY_PASSWORD)
        if not (options['force'] or legacy):
            self.stdout.write(
                self.style.WARNING(
                    f'User "{username}" already exists. Use --force to reset.'
                )
            )
            return

        password = self._password_for(password, user)
        user.set_password(password)
        user.save(update_fields=['password'])
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.must_change_password = True
        profile.save(update_fields=['must_change_password'])
        reason = 'still had the old default password' if legacy else 'reset'
        self.stdout.write(
            self.style.SUCCESS(
                f'User "{username}" {reason}: password replaced and forced '
                'password change re-enabled.'
            )
        )

    def _password_for(self, password, user):
        """The given password once validated, else a generated one, printed."""
        if not password:
            password = secrets.token_urlsafe(18)
            self.stdout.write(
                self.style.WARNING(
                    f'Generated password for "{user.username}": {password}\n'
                    'It is shown only this once. Sign in with it and choose '
                    'a new one.'
                )
            )
            return password
        if password == LEGACY_PASSWORD or password.startswith('change-me-'):
            raise CommandError(
                'Initial administrator password is a known placeholder. '
                'Set a unique one, or leave it unset to have one generated.'
            )
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(
                'Initial administrator password: ' + ' '.join(exc.messages)
            )
        return password
