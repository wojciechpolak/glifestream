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

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils import translation
from django.utils.translation import gettext as _

from glifestream.gauth.models import UserProfile
from glifestream.usettings.common import (
    build_settings_page,
    get_staff_settings_user,
)
from glifestream.usettings.forms import PreferencesForm


@login_required
def preferences(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    profile, _created = UserProfile.objects.get_or_create(user=user)
    saved = False
    if request.method == 'POST':
        form = PreferencesForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            # Answer in the language just picked, or in the browser's again.
            translation.activate(
                profile.language or translation.get_language_from_request(request)
            )
            request.LANGUAGE_CODE = translation.get_language()
            saved = True
    else:
        form = PreferencesForm(instance=profile)

    page = build_settings_page(
        request, title=_('Preferences - Settings'), menu='preferences'
    )
    if saved:
        page['msg'] = _('Preferences saved.')

    return render(
        request,
        'preferences.html',
        {
            'page': page,
            'authed': True,
            'is_secure': request.is_secure(),
            'user': request.user,
            'form': form,
        },
    )
