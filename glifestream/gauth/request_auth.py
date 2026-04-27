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

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from magic_sso_django.auth_utils import is_authenticated as is_magic_sso_authenticated


@dataclass(frozen=True)
class RequestAuthState:
    authed: bool
    friend: bool
    friend_email: str | None


def _normalise_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalised = value.strip()
    return normalised or None


def get_request_auth_state(request: HttpRequest) -> RequestAuthState:
    user = getattr(request, 'user', None)
    authed = bool(
        getattr(user, 'is_authenticated', False) and getattr(user, 'is_staff', False)
    )

    magic_sso_enabled = bool(getattr(settings, 'MAGICSSO_ENABLED', False))
    magic_friend = False
    friend_email = None

    if magic_sso_enabled:
        magic_friend = bool(getattr(request, 'is_magic_sso_authenticated', False))
        friend_email = _normalise_identity(
            getattr(request, 'magic_sso_user_email', None)
        )

        if not magic_friend:
            magic_friend, payload = is_magic_sso_authenticated(request)
            if magic_friend and friend_email is None:
                friend_email = _normalise_identity(payload.get('email'))

    legacy_friend = bool(
        getattr(user, 'is_authenticated', False)
        and not getattr(user, 'is_staff', False)
    )
    if legacy_friend and friend_email is None:
        friend_email = _normalise_identity(getattr(user, 'email', None))
        if friend_email is None:
            friend_email = _normalise_identity(getattr(user, 'username', None))

    return RequestAuthState(
        authed=authed,
        friend=not authed and (magic_friend or legacy_friend),
        friend_email=friend_email,
    )
