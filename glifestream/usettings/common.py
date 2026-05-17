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

from typing import Any, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponseForbidden
from glifestream.utils import common as utils_common


def get_staff_settings_user(request: HttpRequest) -> User | HttpResponseForbidden:
    user = cast(User, request.user)
    if user.is_authenticated and user.is_staff:
        return user
    return HttpResponseForbidden()


def build_settings_page(
    request: HttpRequest,
    *,
    title: str,
    menu: str | None = None,
    robots: str = 'noindex',
) -> dict[str, Any]:
    page = {
        'robots': robots,
        'base_url': settings.BASE_URL,
        'pwa': getattr(settings, 'PWA_APP_NAME', None),
        'favicon': settings.FAVICON,
        'theme': utils_common.get_theme(request),
        'title': title,
    }
    if menu is not None:
        page.update(
            {
                'themes': settings.THEMES,
                'themes_more': len(settings.THEMES) > 1,
                'menu': menu,
            }
        )
    return page

