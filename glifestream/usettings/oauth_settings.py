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
import os

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from glifestream.apis.factory import ServiceFactory
from glifestream.gauth import gls_oauth, gls_oauth2
from glifestream.stream.models import Service
from glifestream.usettings.common import (
    build_settings_page,
    get_staff_settings_user,
)


def _build_oauth_page(request: HttpRequest, title: str) -> dict[str, Any]:
    return build_settings_page(request, title=title, menu=None)


@login_required
@never_cache
def oauth(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = _build_oauth_page(request, _('OAuth - Settings'))
    apis_help = {
        'twitter': 'https://developer.twitter.com/en/docs/authentication/overview',
    }
    v: dict[str, Any] = {}
    id_service = args['id']

    callback_url = request.build_absolute_uri(
        reverse('usettings-oauth', args=[id_service])
    )

    service = Service.objects.get(id=id_service)
    c = gls_oauth.OAuth1Client(
        service=service,
        api=ServiceFactory.create_service(service),
        identifier=request.POST.get('identifier'),
        secret=request.POST.get('secret'),
        callback_url=callback_url,
    )

    if c.db.phase == 0 and (
        not c.request_token_url or not c.authorize_url or not c.access_token_url
    ):
        v['request_token_url'] = request.POST.get('request_token_url', '')
        v['authorize_url'] = request.POST.get('authorize_url', '')
        v['access_token_url'] = request.POST.get('access_token_url', '')
        page['need_custom_urls'] = True

    if 'reset' in request.POST:
        c.reset()
        c.save()
    elif request.method == 'POST':
        if c.db.phase == 0:
            if not c.request_token_url:
                c.set_urls(
                    v['request_token_url'], v['authorize_url'], v['access_token_url']
                )
            try:
                c.get_request_token()
            except Exception as e:
                page['msg'] = e
            c.save()
        if c.db.phase == 1:
            return HttpResponseRedirect(c.get_authorize_url())

    if request.method == 'GET':
        if c.db.phase == 1:
            if request.GET.get('oauth_token', '') == c.db.token:
                c.consumer.parse_authorization_response(request.get_full_path())
                cast(Any, c).verifier = request.GET.get('oauth_verifier', None)
                c.db.phase = 2

        if c.db.phase == 2:
            try:
                c.get_access_token()
                c.save()
                return HttpResponseRedirect(reverse('usettings-oauth', args=[id_service]))
            except Exception as e:
                page['msg'] = e

    api_help = apis_help.get(
        service.api, 'http://oauth.net/documentation/getting-started/'
    )

    return render(
        request,
        'oauth.html',
        {
            'page': page,
            'is_secure': request.is_secure(),
            'title': str(service),
            'api_help': api_help,
            'callback_url': callback_url,
            'phase': c.db.phase,
            'v': v,
        },
    )


@login_required
@never_cache
def oauth2(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = 'True'

    page = _build_oauth_page(request, _('OAuth 2.0 - Settings'))
    apis_help = {
        'mastodon': 'https://docs.joinmastodon.org/spec/oauth/',
    }
    v: dict[str, Any] = {}
    id_service = args['id']

    redirect_uri = request.build_absolute_uri(
        reverse('usettings-oauth2', args=[id_service])
    )

    service = Service.objects.get(id=id_service)
    c = gls_oauth2.OAuth2Client(
        service=service,
        api=ServiceFactory.create_service(service),
        identifier=request.POST.get('identifier'),
        secret=request.POST.get('secret'),
        callback_url=redirect_uri,
    )

    if c.db.phase == gls_oauth2.PHASE_0:
        v['base_url'] = c.base_url
        if not c.authorize_url or not c.token_url:
            v['authorize_url'] = request.POST.get('authorize_url', '')
            v['token_url'] = request.POST.get('token_url', '')
            page['need_custom_urls'] = True

    if 'reset' in request.POST:
        c.reset()
        c.save()
    elif request.method == 'POST':
        access_token = request.POST.get('access_token', None)
        if access_token:
            c.set_access_token(access_token)
            c.db.phase = gls_oauth2.PHASE_3
            c.save()
        elif c.db.phase == gls_oauth2.PHASE_0:
            auth_url = c.get_authorize_url()
            c.db.phase = gls_oauth2.PHASE_1
            c.save()
            return HttpResponseRedirect(auth_url)

    if request.method == 'GET':
        code: str | None = None
        if c.db.phase == gls_oauth2.PHASE_1:
            code = request.GET.get('code', None)
            c.db.phase = gls_oauth2.PHASE_2

        if c.db.phase == gls_oauth2.PHASE_2:
            try:
                c.get_access_token(code)
                c.save()
                return HttpResponseRedirect(
                    reverse('usettings-oauth2', args=[id_service])
                )
            except Exception as e:
                page['msg'] = e

    api_help = apis_help.get(service.api, 'https://oauth.net/2/')

    return render(
        request,
        'oauth2.html',
        {
            'page': page,
            'is_secure': request.is_secure(),
            'title': str(service),
            'api_help': api_help,
            'callback_url': redirect_uri,
            'phase': c.db.phase,
            'v': v,
        },
    )
