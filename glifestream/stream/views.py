"""
#  gLifestream Copyright (C) 2009, 2010, 2011, 2014, 2015, 2024 Wojciech Polak
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
from django.conf import settings
from django.urls import reverse
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotFound,
    Http404,
    JsonResponse,
)
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from glifestream.stream.typing import Page
from glifestream.stream.index_view import render_index
from glifestream.stream import api_view, websub
from glifestream.utils import common


def index(request: HttpRequest, **args: Any) -> HttpResponse:
    return render_index(request, **args)


@never_cache
def websub_dispatcher(request: HttpRequest, **args: Any) -> HttpResponse:
    if request.method == 'GET':
        res = websub.verify(args['id'], request.GET)
        if res:
            return HttpResponse(res)
    elif request.method == 'POST':
        websub.accept_payload(args['id'], request.body, request.META)
        return HttpResponse()
    raise Http404


def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponseNotFound:
    page: Page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'theme': common.get_theme(request),
    }
    t = render(request, '404.html', {'page': page})
    return HttpResponseNotFound(t.content)


def page_internal_error(request: HttpRequest) -> HttpResponseNotFound:
    page: Page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'theme': 'default',
    }
    t = render(request, '500.html', {'page': page})
    return HttpResponseNotFound(t.content)


def webmanifest(request: HttpRequest) -> JsonResponse:
    d = {
        'id': reverse('index'),
        'name': settings.PWA_APP_NAME,
        'short_name': settings.PWA_APP_SHORT_NAME,
        'description': settings.PWA_APP_DESCRIPTION,
        'display': settings.PWA_APP_DISPLAY,
        'scope': reverse('index'),
        'start_url': reverse('index'),
        'icons': settings.PWA_APP_ICONS,
        'share_target': {
            'action': reverse('share'),
            'method': 'GET',
            'params': {'title': 'title', 'text': 'text', 'url': 'url'},
        },
    }
    return JsonResponse(d, content_type='application/manifest+json')


#
# XHR API
#


def api(request: HttpRequest, **args: Any) -> HttpResponse:
    return api_view.dispatch(request, **args)
