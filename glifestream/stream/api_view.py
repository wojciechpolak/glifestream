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

import copy
import re
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
from django.template.loader import render_to_string
from django.urls import reverse

from glifestream.apis import selfposts
from glifestream.fetching import request_websub_publish
from glifestream.gauth.request_auth import get_request_auth_state
from glifestream.stream import media
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


def _post_args(request: HttpRequest) -> dict[str, Any]:
    """What the composer sends for a post, as `selfposts` takes it."""
    return {
        'content': request.POST.get('content', ''),
        'sid': request.POST.get('sid', None),
        'draft': request.POST.get('draft', False),
        'friends_only': request.POST.get('friends_only', False),
        'link': request.POST.get('link', None),
        'images': _shared_images(request),
        'files': request.FILES,
        'music': {
            name: request.POST.get('music_' + name, '')
            for name in ('artist', 'title', 'youtube', 'cover')
        },
        'source': request.POST.get('from', ''),
        'user': request.user,
    }


def _shown_to_owner(entry: Entry) -> None:
    """Lets the owner see the content of `entry`, and its lock if it is for
    friends only, as the stream shows them."""
    cast(Any, entry).only_for_friends = entry.friends_only
    entry.friends_only = False


def _entry_page() -> dict[str, Any]:
    """What the article of one entry needs of its page: the author it names."""
    return {
        'author_name': settings.FEED_AUTHOR_NAME,
        'author_uri': getattr(settings, 'FEED_AUTHOR_URI', False),
    }


def _cmd_share(ctx: ApiContext) -> HttpResponse | None:
    request = ctx.request
    entry = selfposts.SelfpostsService(Service()).share(_post_args(request))
    if not entry:
        return None

    if not entry.draft:
        request_websub_publish()
    _shown_to_owner(entry)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(
            request,
            'stream-pure.html',
            {'entries': (entry,), 'authed': ctx.authed, 'page': _entry_page()},
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

    request_websub_publish()
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
        # For the editor, which shows the pictures it is given.
        return HttpResponse(media.set_upload_url(media.set_thumbs_url(entry.content)))

    cast(Any, entry).friends_login_url = build_friends_login_url(
        ctx.request.build_absolute_uri(reverse('entry', args=[entry.pk]))
    )
    if ctx.authed or ctx.friend:
        entry.friends_only = False
    return HttpResponse(fix_ampersands(gls_content('', entry)))


def _cmd_editcontent(ctx: ApiContext) -> HttpResponse | None:
    """An entry as the composer edits it: its HTML with addresses a browser
    can load, its class, and whether it is a post, whose class may change."""
    entry = Entry.objects.select_related('service').filter(pk=ctx.entry_pk).first()
    if entry is None:
        return None
    return JsonResponse(
        {
            'content': media.set_upload_url(media.set_thumbs_url(entry.content)),
            # As its icon shows it (stream-pure.html).
            'cls': entry.service.cls or entry.service.api,
            'post': entry.service.api == 'selfposts',
            'draft': entry.draft,
            'friends_only': entry.friends_only,
        }
    )


def _edited_fields(entry: Entry, post: Any) -> dict[str, Any]:
    """The fields of `entry` once what the composer sends in `post` is saved:
    its HTML, and for a post the class the rich composer sends too."""
    # What getcontent gave the editor, back as entries store it.
    content = media.unset_media_urls(post.get('content', ''))
    fields: dict[str, Any] = {'content': content}
    # The rich composer's checkboxes; the raw editor has none.
    for flag in ('draft', 'friends_only'):
        if flag in post:
            fields[flag] = post.get(flag) in ('1', 'true', 'on')
    if entry.service.api == 'selfposts':
        fields['content'], fields['mblob'] = selfposts.edited_content(entry, content)
        service = selfposts.class_service(entry, post.get('sid'))
        if service is not None:
            fields['service'] = service
    return fields


def _cmd_putcontent(ctx: ApiContext) -> HttpResponse | None:
    try:
        entry = Entry.objects.select_related('service').get(pk=ctx.entry_pk)
    except Entry.DoesNotExist:
        return None
    post = ctx.request.POST
    if post.get('content', ''):
        Entry.objects.filter(pk=entry.pk).update(**_edited_fields(entry, post))
        entry.refresh_from_db()
    if post.get('article'):
        # The whole article, whose icon shows a new class too.
        _shown_to_owner(entry)
        return render(
            ctx.request,
            'stream-pure.html',
            {'entries': (entry,), 'authed': ctx.authed, 'page': _entry_page()},
        )
    return HttpResponse(fix_ampersands(gls_content('', entry)))


# The ids and the share link of the article a preview shows, which only
# the entries of the stream have.
_PREVIEW_IDS = re.compile(r' id="(?:entry|shareit)-\d*"')
_PREVIEW_SHARE = re.compile(r'<a href="#"[^>]*class="shareit[^"]*".*?</a>', re.S)


def _cmd_preview(ctx: ApiContext) -> HttpResponse | None:
    """The article of a post being written, or of an entry being edited, as
    the stream will show it. Nothing is saved."""
    request = ctx.request
    if ctx.entry_id is not None:
        stored = Entry.objects.select_related('service').filter(pk=ctx.entry_id).first()
        if stored is None:
            return None
        entry = copy.copy(stored)
        for name, value in _edited_fields(stored, request.POST).items():
            setattr(entry, name, value)
    else:
        args = _post_args(request)
        try:
            entry = selfposts.SelfpostsService(Service()).build(args)
        except (Service.DoesNotExist, IndexError, ValueError):
            return None
        # Its links need an id; the article loses it below.
        entry.pk = 0
    # The owner sees what friends will, and the lock of a friends-only post.
    _shown_to_owner(entry)
    html: str = render_to_string(
        'stream-pure.html',
        {'entries': (entry,), 'authed': False, 'preview': True, 'page': _entry_page()},
        request=request,
    )
    return HttpResponse(_PREVIEW_SHARE.sub('', _PREVIEW_IDS.sub('', html)))


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
    'editcontent': _cmd_editcontent,
    'preview': _cmd_preview,
}

# The only command an anonymous visitor may reach.
PUBLIC_COMMANDS = frozenset({'getcontent'})

# Commands that do nothing without an `entry` POST parameter. They answer with
# an empty 200 rather than a 404, which is what the chain always did.
ENTRY_COMMANDS = frozenset(API_COMMANDS) - {'gsc', 'share', 'preview'}


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
