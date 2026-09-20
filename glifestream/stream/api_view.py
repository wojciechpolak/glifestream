"""
#  gLifestream Copyright (C) 2009, 2010, 2011, 2014, 2015, 2024, 2026 Wojciech Polak
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

The XHR API behind /api/<cmd>. `stream.views.api` is a thin delegate over
`dispatch` here, the way `stream.views.index` delegates to `index_view`.

Every handler returns either a response or None; None means "nothing to say",
which the dispatcher turns into an empty 200. That is what the original
if/elif chain did by falling off its end, and several callers in the
JavaScript rely on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse

from glifestream.apis import selfposts
from glifestream.gauth.request_auth import get_request_auth_state
from glifestream.stream import media, websub
from glifestream.stream.index_view import build_friends_login_url
from glifestream.stream.models import Entry, Favorite, Service
from glifestream.stream.templatetags.gls_filters import fix_ampersands, gls_content

MAX_SHARED_IMAGES = 5


@dataclass(frozen=True)
class ApiContext:
    request: HttpRequest
    user: User
    authed: bool
    friend: bool
    entry_id: int | None

    @property
    def entry_pk(self) -> int:
        """The entry id. Only read by handlers the dispatcher gates on one."""
        return cast(int, self.entry_id)


ApiHandler = Callable[[ApiContext], HttpResponse | None]


def _cmd_hide(ctx: ApiContext) -> None:
    Entry.objects.filter(pk=ctx.entry_pk).update(active=False)
    return None


def _cmd_unhide(ctx: ApiContext) -> None:
    Entry.objects.filter(pk=ctx.entry_pk).update(active=True)
    return None


def _cmd_gsc(ctx: ApiContext) -> HttpResponse:
    """Get selfposts classes -- the first service id for each distinct class."""
    del ctx
    services = (
        Service.objects.filter(api='selfposts').order_by('cls').values('id', 'cls')
    )
    by_cls: dict[Any, dict[str, Any]] = {}
    for item in services:
        by_cls.setdefault(item['cls'], {'id': item['id'], 'cls': item['cls']})
    return JsonResponse(list(by_cls.values()), safe=False)


def _shared_images(request: HttpRequest) -> list[str]:
    images = []
    for i in range(0, MAX_SHARED_IMAGES):
        img = request.POST.get('image%d' % i, None)
        if img:
            images.append(img)
    return images


def _cmd_share(ctx: ApiContext) -> HttpResponse | None:
    request = ctx.request
    entry = selfposts.SelfpostsService(Service()).share(
        {
            'content': request.POST.get('content', ''),
            'sid': request.POST.get('sid', None),
            'draft': request.POST.get('draft', False),
            'friends_only': request.POST.get('friends_only', False),
            'link': request.POST.get('link', None),
            'images': _shared_images(request),
            'files': request.FILES,
            'source': request.POST.get('from', ''),
            'user': request.user,
        }
    )
    if not entry:
        return None

    if not entry.draft:
        websub.publish()
    entry.friends_only = False
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(
            request, 'stream-pure.html', {'entries': (entry,), 'authed': ctx.authed}
        )
    return HttpResponseRedirect(settings.BASE_URL + '/')


def _cmd_reshare(ctx: ApiContext) -> HttpResponse | None:
    try:
        source = Entry.objects.get(pk=ctx.entry_pk)
    except Entry.DoesNotExist:
        return None

    entry = selfposts.SelfpostsService(Service()).reshare(
        source,
        {'as_me': ctx.request.POST.get('as_me', False), 'user': ctx.user},
    )
    if not entry:
        return None

    websub.publish()
    return render(
        ctx.request, 'stream-pure.html', {'entries': (entry,), 'authed': ctx.authed}
    )


def _cmd_favorite(ctx: ApiContext) -> None:
    try:
        entry = Entry.objects.get(pk=ctx.entry_pk)
    except Entry.DoesNotExist:
        return None

    try:
        Favorite.objects.get(user=ctx.user, entry=entry)
    except Favorite.DoesNotExist:
        Favorite(user=ctx.user, entry=entry).save()
        media.transform_to_local(entry)
        media.extract_and_register(entry)
        entry.save()
    return None


def _cmd_unfavorite(ctx: ApiContext) -> None:
    try:
        entry = Entry.objects.get(pk=ctx.entry_pk)
    except Entry.DoesNotExist:
        return None

    Favorite.objects.get(user=ctx.user, entry=entry).delete()
    return None


def _cmd_getcontent(ctx: ApiContext) -> HttpResponse | None:
    filters: dict[str, Any] = {'pk': ctx.entry_pk}
    if not ctx.authed:
        filters.update({'active': True, 'draft': False, 'service__public': True})
    try:
        entry = Entry.objects.get(**filters)
    except Entry.DoesNotExist:
        return None

    if ctx.authed and ctx.request.POST.get('raw', False):
        return HttpResponse(entry.content)

    cast(Any, entry).friends_login_url = build_friends_login_url(
        ctx.request.build_absolute_uri(reverse('entry', args=[entry.pk]))
    )
    if ctx.authed or ctx.friend:
        entry.friends_only = False
    return HttpResponse(fix_ampersands(gls_content('', entry)))


def _cmd_putcontent(ctx: ApiContext) -> HttpResponse | None:
    content = ctx.request.POST.get('content', '')
    if content:
        Entry.objects.filter(pk=ctx.entry_pk).update(content=content)
    try:
        entry = Entry.objects.get(pk=ctx.entry_pk)
    except Entry.DoesNotExist:
        return None
    return HttpResponse(fix_ampersands(gls_content('', entry)))


API_COMMANDS: dict[str, ApiHandler] = {
    'hide': _cmd_hide,
    'unhide': _cmd_unhide,
    'gsc': _cmd_gsc,
    'share': _cmd_share,
    'reshare': _cmd_reshare,
    'favorite': _cmd_favorite,
    'unfavorite': _cmd_unfavorite,
    'getcontent': _cmd_getcontent,
    'putcontent': _cmd_putcontent,
}

# The only command an anonymous visitor may reach.
PUBLIC_COMMANDS = frozenset({'getcontent'})

# Commands that do nothing without an `entry` POST parameter. They answer with
# an empty 200 rather than a 404, which is what the chain always did.
ENTRY_COMMANDS = frozenset(API_COMMANDS) - {'gsc', 'share'}


def dispatch(request: HttpRequest, **args: Any) -> HttpResponse:
    auth_state = get_request_auth_state(request)
    cmd = args.get('cmd', '')
    entry = request.POST.get('entry', None)
    entry_id: int | None = int(cast(str, entry)) if entry else None

    if not auth_state.authed and cmd not in PUBLIC_COMMANDS:
        return HttpResponseForbidden()

    handler = API_COMMANDS.get(cmd)
    if handler is None or (cmd in ENTRY_COMMANDS and entry_id is None):
        return HttpResponse()

    ctx = ApiContext(
        request=request,
        user=cast(User, request.user),
        authed=auth_state.authed,
        friend=auth_state.friend,
        entry_id=entry_id,
    )
    return handler(ctx) or HttpResponse()
