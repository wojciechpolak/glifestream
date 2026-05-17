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
from django.utils.translation import gettext as _

from glifestream.stream import websub as gls_websub
from glifestream.stream.models import Service
from glifestream.usettings.common import (
    build_settings_page,
    get_staff_settings_user,
)


@login_required
def websub(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = build_settings_page(request, title=_('WebSub - Settings'), menu='websub')
    excluded_apis = (
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

    if request.POST.get('subscribe', False):
        service = Service.objects.get(id=request.POST['subscribe'])
        r = gls_websub.subscribe(service)
        if r['rc'] == 1:
            page['msg'] = r['error']
        elif r['rc'] == 2:
            page['msg'] = _('Hub not found.')
        elif r['rc'] == 202:
            page['msg'] = _('Hub %s: Accepted for verification.') % r['hub']
        elif r['rc'] == 204:
            page['msg'] = _('Hub %s: Subscription verified.') % r['hub']

    elif request.POST.get('unsubscribe', False):
        r = gls_websub.unsubscribe(request.POST['unsubscribe'])
        if r['rc'] == 1:
            page['msg'] = _('No subscription found.')
        elif r['rc'] == 202:
            page['msg'] = _('Hub %s: Accepted for verification.') % r['hub']
        elif r['rc'] == 204:
            page['msg'] = _('Hub %s: Unsubscribed.') % r['hub']
        else:
            page['msg'] = 'Hub %s: %s.' % (r['hub'], r['rc'])

    subs = gls_websub.list_subs(raw=True)
    services = (
        Service.objects.exclude(api__in=excluded_apis)
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
