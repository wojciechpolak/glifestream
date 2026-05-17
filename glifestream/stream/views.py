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
from typing import Any, cast
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    HttpResponseNotFound,
    Http404,
    JsonResponse,
)
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from glifestream.stream.templatetags.gls_filters import (
    gls_content,
    fix_ampersands,
)
from glifestream.stream.models import Service, Entry, Favorite
from glifestream.stream.typing import Page
from glifestream.stream.index_view import (
    build_friends_login_url as _build_friends_login_url,
    render_index,
)
from glifestream.stream import media, websub
from glifestream.gauth.request_auth import get_request_auth_state
from glifestream.utils import common
from glifestream.apis import selfposts


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
    user = cast(User, request.user)
    auth_state = get_request_auth_state(request)
    cmd = args.get('cmd', '')
    entry: Any = request.POST.get('entry', None)
    entry_id: int | None = int(cast(str, entry)) if entry else None

    authed = auth_state.authed
    friend = auth_state.friend
    if not authed and cmd != 'getcontent':
        return HttpResponseForbidden()

    if cmd == 'hide' and entry_id is not None:
        Entry.objects.filter(pk=entry_id).update(active=False)

    elif cmd == 'unhide' and entry_id is not None:
        Entry.objects.filter(pk=entry_id).update(active=True)

    elif cmd == 'gsc':  # get selfposts classes
        _srvs = (
            Service.objects.filter(api='selfposts').order_by('cls').values('id', 'cls')
        )
        srvs: Any = {}
        for item in _srvs:
            if item['cls'] not in srvs:
                srvs[item['cls']] = item
        srvs = list(srvs.values())

        d = []
        for s in srvs:
            d.append({'id': s['id'], 'cls': s['cls']})
        return JsonResponse(d, safe=False)

    elif cmd == 'share':
        images = []
        for i in range(0, 5):
            img = request.POST.get('image' + str(i), None)
            if img:
                images.append(img)
        source = request.POST.get('from', '')
        entry = selfposts.SelfpostsService(Service()).share(
            {
                'content': request.POST.get('content', ''),
                'sid': request.POST.get('sid', None),
                'draft': request.POST.get('draft', False),
                'friends_only': request.POST.get('friends_only', False),
                'link': request.POST.get('link', None),
                'images': images,
                'files': request.FILES,
                'source': source,
                'user': request.user,
            }
        )
        if entry:
            if not entry.draft:
                websub.publish()
            entry.friends_only = False
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return render(
                    request, 'stream-pure.html', {'entries': (entry,), 'authed': authed}
                )
            else:
                return HttpResponseRedirect(settings.BASE_URL + '/')

    elif cmd == 'reshare' and entry_id is not None:
        try:
            entry = Entry.objects.get(pk=entry_id)
            if entry:
                entry = selfposts.SelfpostsService(Service()).reshare(
                    entry,
                    {'as_me': request.POST.get('as_me', False), 'user': user},
                )
                if entry:
                    websub.publish()
                    return render(
                        request,
                        'stream-pure.html',
                        {'entries': (entry,), 'authed': authed},
                    )
        except Entry.DoesNotExist:
            pass

    elif cmd == 'favorite' and entry_id is not None:
        try:
            entry = Entry.objects.get(pk=entry_id)
            if entry:
                try:
                    Favorite.objects.get(user=user, entry=entry)
                except Favorite.DoesNotExist:
                    fav = Favorite(user=user, entry=entry)
                    fav.save()
                    media.transform_to_local(entry)
                    media.extract_and_register(entry)
                    entry.save()
        except Entry.DoesNotExist:
            pass

    elif cmd == 'unfavorite' and entry_id is not None:
        try:
            entry = Entry.objects.get(pk=entry_id)
            if entry:
                Favorite.objects.get(user=user, entry=entry).delete()
        except Entry.DoesNotExist:
            pass

    elif cmd == 'getcontent' and entry_id is not None:
        try:
            if authed:
                entry = Entry.objects.get(pk=entry_id)
            else:
                filters: dict[str, Any] = {
                    'pk': entry_id,
                    'active': True,
                    'draft': False,
                    'service__public': True,
                }
                entry = Entry.objects.get(**filters)
            if entry:
                if request.POST.get('raw', False) and authed:
                    return HttpResponse(entry.content)

                cast(Any, entry).friends_login_url = _build_friends_login_url(
                    request.build_absolute_uri(reverse('entry', args=[entry.pk]))
                )
                if authed or friend:
                    entry.friends_only = False
                content = fix_ampersands(gls_content('', entry))
                return HttpResponse(content)
        except Entry.DoesNotExist:
            pass

    elif cmd == 'putcontent' and entry_id is not None:
        try:
            if authed:
                content = request.POST.get('content', '')
                if content:
                    Entry.objects.filter(pk=entry_id).update(content=content)
                entry = Entry.objects.get(pk=entry_id)
                if entry:
                    content = fix_ampersands(gls_content('', entry))
                    return HttpResponse(content)
        except Entry.DoesNotExist:
            pass

    return HttpResponse()
