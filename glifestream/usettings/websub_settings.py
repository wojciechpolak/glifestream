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

from collections.abc import Callable
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils.translation import gettext as _

from glifestream.stream import websub as gls_websub
from glifestream.stream.models import Service
from glifestream.usettings.common import (
    build_settings_page,
    get_staff_settings_user,
)


# WebSub hub result codes, as returned by glifestream.stream.websub, mapped to
# the notice the settings page shows. An unlisted code says nothing.
_SUBSCRIBE_MESSAGES: dict[Any, Callable[[dict], str]] = {
    1: lambda r: str(r['error']),
    2: lambda r: _('Hub not found.'),
    202: lambda r: _('Hub %s: Accepted for verification.') % r['hub'],
    204: lambda r: _('Hub %s: Subscription verified.') % r['hub'],
}

_UNSUBSCRIBE_MESSAGES: dict[Any, Callable[[dict], str]] = {
    1: lambda r: _('No subscription found.'),
    202: lambda r: _('Hub %s: Accepted for verification.') % r['hub'],
    204: lambda r: _('Hub %s: Unsubscribed.') % r['hub'],
}

EXCLUDED_APIS = (
    'selfposts',
    'atproto',
    'fb',
    'flickr',
    'friendfeed',
    'mastodon',
    'pixelfed',
    'pocket',
    'twitter',
    'vimeo',
    'youtube',
)


def _handle_subscribe(request: HttpRequest) -> str | None:
    service = Service.objects.get(id=request.POST['subscribe'])
    result = gls_websub.subscribe(service)
    render_message = _SUBSCRIBE_MESSAGES.get(result['rc'])
    return render_message(result) if render_message else None


def _handle_unsubscribe(request: HttpRequest) -> str | None:
    result = gls_websub.unsubscribe(request.POST['unsubscribe'])
    render_message = _UNSUBSCRIBE_MESSAGES.get(result['rc'])
    if render_message:
        return render_message(result)
    # Anything else is a transport-level complaint worth showing verbatim.
    return 'Hub %s: %s.' % (result['hub'], result['rc'])


@login_required
def websub(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = build_settings_page(request, title=_('WebSub - Settings'), menu='websub')

    if request.POST.get('subscribe', False):
        message = _handle_subscribe(request)
    elif request.POST.get('unsubscribe', False):
        message = _handle_unsubscribe(request)
    else:
        message = None
    if message is not None:
        page['msg'] = message

    subs = gls_websub.list_subs(raw=True)
    services = (
        Service.objects.exclude(api__in=EXCLUDED_APIS)
        .exclude(id__in=subs.values('service__id'))
        .order_by('name')
    )

    return render(
        request,
        'websub.html',
        {
            'page': page,
            'authed': True,
            'is_secure': request.is_secure(),
            'user': request.user,
            'services': services,
            'subs': subs,
        },
    )
