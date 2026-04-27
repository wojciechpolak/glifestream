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

import datetime

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, override_settings

from glifestream.gauth.request_auth import get_request_auth_state
from glifestream.testsupport.magic_sso import make_magic_sso_token


MAGIC_SSO_COOKIE_NAME = getattr(settings, 'MAGICSSO_COOKIE_NAME', 'magic-sso')


def test_request_auth_state_for_anonymous_request() -> None:
    request = RequestFactory().get('/')
    request.user = AnonymousUser()

    state = get_request_auth_state(request)

    assert state.authed is False
    assert state.friend is False
    assert state.friend_email is None


@pytest.mark.django_db
def test_request_auth_state_for_admin_user() -> None:
    request = RequestFactory().get('/')
    request.user = User.objects.create_user(
        username='admin',
        password='password',
        email='admin@example.com',
        is_staff=True,
    )

    state = get_request_auth_state(request)

    assert state.authed is True
    assert state.friend is False
    assert state.friend_email is None


@override_settings(MAGICSSO_ENABLED=True)
def test_request_auth_state_for_magic_sso_cookie() -> None:
    request = RequestFactory().get(
        '/',
        HTTP_COOKIE=f'{MAGIC_SSO_COOKIE_NAME}={make_magic_sso_token()}',
    )
    request.user = AnonymousUser()

    state = get_request_auth_state(request)

    assert state.authed is False
    assert state.friend is True
    assert state.friend_email == 'friend@example.com'


@override_settings(MAGICSSO_ENABLED=True)
def test_request_auth_state_for_invalid_magic_sso_cookie() -> None:
    request = RequestFactory().get(
        '/',
        HTTP_COOKIE=f'{MAGIC_SSO_COOKIE_NAME}=not-a-jwt',
    )
    request.user = AnonymousUser()

    state = get_request_auth_state(request)

    assert state.authed is False
    assert state.friend is False
    assert state.friend_email is None


@override_settings(MAGICSSO_ENABLED=True)
def test_request_auth_state_for_expired_magic_sso_cookie() -> None:
    request = RequestFactory().get(
        '/',
        HTTP_COOKIE=(
            f'{MAGIC_SSO_COOKIE_NAME}='
            f'{make_magic_sso_token(expires_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5))}'
        ),
    )
    request.user = AnonymousUser()

    state = get_request_auth_state(request)

    assert state.authed is False
    assert state.friend is False
    assert state.friend_email is None


@override_settings(MAGICSSO_ENABLED=False)
def test_request_auth_state_ignores_magic_sso_cookie_when_disabled() -> None:
    request = RequestFactory().get(
        '/',
        HTTP_COOKIE=f'{MAGIC_SSO_COOKIE_NAME}={make_magic_sso_token()}',
    )
    request.user = AnonymousUser()

    state = get_request_auth_state(request)

    assert state.authed is False
    assert state.friend is False
    assert state.friend_email is None


@pytest.mark.django_db
def test_request_auth_state_for_legacy_non_staff_user() -> None:
    request = RequestFactory().get('/')
    request.user = User.objects.create_user(
        username='friend',
        password='password',
        email='legacy-friend@example.com',
        is_staff=False,
    )

    state = get_request_auth_state(request)

    assert state.authed is False
    assert state.friend is True
    assert state.friend_email == 'legacy-friend@example.com'
