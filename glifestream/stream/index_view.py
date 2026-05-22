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

from dataclasses import dataclass, field
import datetime
from typing import Any, cast
from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connections
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.template.defaultfilters import truncatewords
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape, strip_spaces_between_tags
from django.utils.translation import gettext as _

from glifestream import REVISION, VERSION
from glifestream.apis import API_LIST
from glifestream.gauth.request_auth import RequestAuthState, get_request_auth_state
from glifestream.stream.models import Entry, Favorite, List, Service
from glifestream.stream.templatetags.gls_filters import gls_slugify
from glifestream.stream.typing import Page
from glifestream.utils import common
from glifestream.utils.time import pn_month_start


@dataclass
class IndexRequestState:
    request: HttpRequest
    user: User
    auth_state: RequestAuthState
    authed: bool
    friend: bool
    site_url: str
    args: dict[str, Any]
    entries_on_page: int
    entries_orderby: str
    search_enable: bool
    search_engine: str


@dataclass
class IndexQueryState:
    page: Page
    filters: dict[str, Any]
    urlparams: list[str]
    entries: Any
    year: int
    month: int
    day: int
    search_query: str = ''


@dataclass
class IndexResult:
    entries: Any
    start: int | bool = False
    after: int | bool = False
    extra_page: dict[str, Any] = field(default_factory=dict)


def build_friends_login_url(return_url: str) -> str | None:
    if not getattr(settings, 'MAGICSSO_ENABLED', False):
        return None

    return '%s?%s' % (
        reverse('magic_sso:login'),
        urlencode({'returnUrl': return_url}),
    )


def render_index(request: HttpRequest, **args: Any) -> HttpResponse:
    state = build_index_request_state(request, args)
    query = build_index_query_state(state)

    apply_archive_filters(query)
    response = apply_context_filters(state, query)
    if response is not None:
        return response

    apply_query_string_filters(state, query)
    result = run_index_query(state, query)
    if 'prevpage' in result.extra_page:
        query.page['prevpage'] = result.extra_page['prevpage']
    if 'nextpage' in result.extra_page:
        query.page['nextpage'] = result.extra_page['nextpage']

    finalize_page(state, query, result)
    decorate_entries(state, query, result.entries)

    response = validate_exact_entry_request(state, query, result.entries)
    if response is not None:
        return response

    return dispatch_index_format(state, query, result)


def build_index_request_state(
    request: HttpRequest, args: dict[str, Any]
) -> IndexRequestState:
    user = cast(User, request.user)
    auth_state = get_request_auth_state(request)
    site_url = '%s://%s' % (
        request.is_secure() and 'https' or 'http',
        request.get_host(),
    )
    return IndexRequestState(
        request=request,
        user=user,
        auth_state=auth_state,
        authed=auth_state.authed,
        friend=auth_state.friend,
        site_url=site_url,
        args=args,
        entries_on_page=settings.ENTRIES_ON_PAGE,
        entries_orderby='date_published',
        search_enable=getattr(settings, 'SEARCH_ENABLE', False),
        search_engine=getattr(settings, 'SEARCH_ENGINE', 'sphinx'),
    )


def build_index_page(state: IndexRequestState) -> Page:
    return {
        'ctx': state.args.get('ctx', ''),
        'version': VERSION,
        'revision': REVISION,
        'backtime': True,
        'robots': 'index',
        'public': False,
        'pwa': getattr(settings, 'PWA_APP_NAME', None),
        'site_url': state.site_url,
        'base_url': settings.BASE_URL,
        'login_url': settings.LOGIN_URL,
        'favicon': settings.FAVICON,
        'author_name': settings.FEED_AUTHOR_NAME,
        'author_uri': getattr(settings, 'FEED_AUTHOR_URI', False),
        'taguri': settings.FEED_TAGURI,
        'icon': settings.FEED_ICON,
        'maps_engine': settings.MAPS_ENGINE,
        'websub_hubs': settings.WEBSUB_HUBS,
        'reblogs': True,
    }


def build_index_query_state(state: IndexRequestState) -> IndexQueryState:
    return IndexQueryState(
        page=build_index_page(state),
        filters={'active': True, 'service__home': True},
        urlparams=[],
        entries=Entry.objects.none(),
        year=int(state.args.get('year', 0)),
        month=int(state.args.get('month', 0)),
        day=int(state.args.get('day', 0)),
        search_query=state.request.GET.get('s', ''),
    )


def apply_archive_filters(query: IndexQueryState) -> None:
    if query.year:
        query.filters['date_published__year'] = query.year
    if query.month:
        query.filters['date_published__month'] = query.month
    if query.day:
        query.filters['date_published__day'] = query.day

    if query.year and query.month and query.day:
        dt = datetime.date(query.year, query.month, query.day).strftime('%Y/%m/%d')
    elif query.year and query.month:
        month_date = datetime.date(query.year, query.month, 1)
        month_prev, month_next = pn_month_start(month_date)
        query.page['month_nav'] = True
        query.page['month_prev'] = month_prev.strftime('%Y/%m')
        query.page['month_next'] = month_next.strftime('%Y/%m')
        dt = month_date.strftime('%Y/%m')
    elif query.year:
        dt = datetime.date(query.year, 1, 1).strftime('%Y')
    else:
        dt = ''

    if query.year:
        query.page['backtime'] = False
        query.page['title'] = dt
        query.page['subtitle'] = _('You are currently browsing the archive for %s') % (
            '<b>' + dt + '</b>'
        )
        query.page['robots'] = 'noindex'

    if query.page['backtime']:
        query.entries = Entry.objects.order_by('-date_published')
    else:
        query.entries = Entry.objects.order_by('date_published')


def apply_context_filters(
    state: IndexRequestState, query: IndexQueryState
) -> HttpResponse | None:
    if not state.authed:
        query.filters['draft'] = False
    if not state.authed or query.page['ctx'] == 'public':
        query.filters['service__public'] = True
        query.page['public'] = True

    if query.page['ctx'] == 'favorites':
        if not state.authed:
            return HttpResponseRedirect(settings.BASE_URL + '/')
        favs = Favorite.objects.filter(user=state.user)
        query.page['favorites'] = True
        query.page['title'] = _('Favorites')
        query.page['subtitle'] = _('You are currently browsing your favorite entries')
        query.filters['id__in'] = favs.values('entry')
    elif 'list' in state.args:
        try:
            services = List.objects.get(user=state.user, slug=state.args['list']).services
            del query.filters['service__home']
            query.filters['service__id__in'] = services.values('id')
            query.page['ctx'] = 'list/' + state.args['list']
            query.page['title'] = state.args['list']
            query.page['subtitle'] = _(
                'You are currently browsing entries from %s list only.'
            ) % ('<b>' + state.args['list'] + '</b>')
        except List.DoesNotExist:
            if state.authed:
                raise Http404
    elif 'entry' in state.args:
        query.filters['id__exact'] = int(state.args['entry'])
        query.page['exactentry'] = True
        if state.authed and 'service__public' in query.filters:
            del query.filters['service__public']

    if not state.authed:
        query.page['ctx'] = ''

    return None


def apply_query_string_filters(state: IndexRequestState, query: IndexQueryState) -> None:
    request = state.request

    cls = request.GET.get('class', 'all')
    if cls != 'all':
        query.filters['service__cls'] = cls
        query.urlparams.append('class=' + cls)
        query.page['robots'] = 'noindex'
        if 'subtitle' in query.page:
            query.page['subtitle'] += ' <b>(%s)</b>' % escape(cls.capitalize())
        else:
            query.page['subtitle'] = _('You are currently browsing %s entries only.') % (
                '<b>' + escape(cls) + '</b>'
            )

    author = request.GET.get('author', 'all')
    if author != 'all':
        query.filters['author_name'] = author
        query.urlparams.append('author=' + author)
        query.page['robots'] = 'noindex'

    srvapi = request.GET.get('service', 'all')
    if srvapi != 'all':
        query.filters['service__api'] = srvapi
        query.urlparams.append('service=' + srvapi)
        query.page['robots'] = 'noindex'
        srvapi_name = dict(API_LIST).get(srvapi, srvapi.capitalize())
        if 'subtitle' in query.page:
            query.page['subtitle'] += ' <b>(%s)</b>' % escape(srvapi_name)
        else:
            query.page['subtitle'] = _(
                'You are currently browsing entries from %s service only.'
            ) % ('<b>' + escape(srvapi_name) + '</b>')

    if (
        state.authed
        and state.request.GET.get('reblogs', state.request.COOKIES.get('gls-reblogs', '1'))
        == '0'
    ):
        query.filters['reblog'] = False
        query.page['reblogs'] = False


def run_index_query(state: IndexRequestState, query: IndexQueryState) -> IndexResult:
    after = apply_start_pagination(state, query)
    if query.search_query != '' and state.search_enable:
        return run_search_query(state, query, after)
    return run_normal_query(state, query, after)


def apply_start_pagination(state: IndexRequestState, query: IndexQueryState) -> int | bool:
    start = state.request.GET.get('start', False)
    if not start:
        return False

    qs = query.filters.copy()
    try:
        dt = datetime.datetime.fromtimestamp(
            float(start), tz=datetime.timezone.utc
        )
    except (OverflowError, ValueError):
        raise Http404

    if query.page['backtime']:
        query.filters[state.entries_orderby + '__lte'] = dt
        qs[state.entries_orderby + '__gt'] = query.filters[state.entries_orderby + '__lte']
        entries = Entry.objects.order_by(state.entries_orderby)
    else:
        query.filters[state.entries_orderby + '__gte'] = dt
        qs[state.entries_orderby + '__lt'] = query.filters[state.entries_orderby + '__gte']
        entries = Entry.objects.order_by('-' + state.entries_orderby)

    older_entries = entries.filter(**qs)[0 : state.entries_on_page].values(
        state.entries_orderby
    )
    after: int | bool = False
    if len(older_entries):
        next_dt = older_entries[len(older_entries) - 1][state.entries_orderby]
        after = int(next_dt.timestamp())

    query.page['title'] = '%s' % str(dt)[0:-3]
    query.page['robots'] = 'noindex'
    return after


def run_search_query(
    state: IndexRequestState, query: IndexQueryState, after: int | bool
) -> IndexResult:
    query.page['search'] = query.search_query
    query.page['title'] = 'Search Results for %s' % escape(query.search_query)
    query.page['subtitle'] = _('Your search for %s returned the following results.') % (
        '<b>' + escape(query.search_query) + '</b>'
    )
    query.urlparams.append('s=' + query.search_query)

    search_filters: dict[str, Any] = {}
    if not state.authed and not state.friend:
        search_filters['friends_only'] = False

    page_number = int(state.request.GET.get('page', 1))
    offset = (page_number - 1) * state.entries_on_page

    try:
        entries = build_search_queryset(state, query, search_filters)
        limit = offset + state.entries_on_page
        extra_page: dict[str, Any] = {}
        if offset >= state.entries_on_page:
            extra_page['prevpage'] = page_number - 1
        if limit < entries.count():
            extra_page['nextpage'] = page_number + 1
        return IndexResult(entries=entries[offset:limit], start=False, after=after, extra_page=extra_page)
    except Exception:
        return IndexResult(entries=cast(Any, []), start=False, after=after)


def build_search_queryset(
    state: IndexRequestState, query: IndexQueryState, search_filters: dict[str, Any]
) -> Any:
    if state.search_engine == 'sphinx':
        select = "SELECT * FROM %s WHERE MATCH('%s')"
        if query.page['public']:
            select += ' AND public=1'
        if 'friends_only' in search_filters and search_filters['friends_only'] is False:
            select += ' AND friends_only=0'
        select += ' LIMIT 1000'

        cursor = connections['sphinx'].cursor()
        cursor.execute(select % (settings.SPHINX_INDEX_NAME, query.search_query))
        results = dictfetchall(cursor)
        uids = [entry['id'] for entry in results]
        return query.entries.filter(id__in=uids).select_related()

    if query.page['public']:
        search_filters['service__public'] = True
    search_filters['content__icontains'] = query.search_query
    return query.entries.filter(**search_filters).select_related()


def run_normal_query(
    state: IndexRequestState, query: IndexQueryState, after: int | bool
) -> IndexResult:
    entries = query.entries.filter(**query.filters)[0 : state.entries_on_page + 1].select_related()
    num_entries = len(entries)

    if 'exactentry' in query.page and num_entries:
        query.page['title'] = truncatewords(entries[0].title, 7)

    if num_entries > state.entries_on_page:
        last_entry_dt = getattr(entries[num_entries - 1], state.entries_orderby)
        start = int(last_entry_dt.timestamp())
    else:
        start = False

    entries = entries[0 : state.entries_on_page]

    if num_entries:
        earliest_year = entries[len(entries) - 1].date_published.year
        latest_year = entries[0].date_published.year
        if earliest_year != latest_year:
            query.page['copyright_years'] = '%s-%s' % (earliest_year, latest_year)
        else:
            query.page['copyright_years'] = earliest_year

    return IndexResult(entries=entries, start=start, after=after)


def finalize_page(
    state: IndexRequestState, query: IndexQueryState, result: IndexResult
) -> None:
    if query.urlparams:
        urlparams_str = '?' + '&'.join(query.urlparams) + '&'
    else:
        urlparams_str = '?'

    if len(result.entries):
        query.page['updated'] = result.entries[0].date_published
    else:
        query.page['updated'] = datetime.datetime.now(datetime.timezone.utc)
    query.page['urlparams'] = urlparams_str
    query.page['start'] = result.start
    query.page['after'] = result.after

    page_title = getattr(settings, 'STREAM_TITLE', None)
    if hasattr(settings, 'STREAM_DESCRIPTION'):
        query.page['description'] = settings.STREAM_DESCRIPTION

    query.page['themes'] = settings.THEMES
    query.page['themes_more'] = len(settings.THEMES) > 1
    query.page['theme'] = common.get_theme(state.request)

    if 'title' in query.page and query.page['title'] != '':
        if page_title:
            query.page['title'] += getattr(
                settings, 'STREAM_TITLE_SUFFIX', ' | ' + page_title
            )
    elif page_title:
        query.page['title'] = page_title


def decorate_entries(
    state: IndexRequestState, query: IndexQueryState, entries: Any
) -> None:
    for entry in entries:
        entry_obj = entry
        entry_obj.only_for_friends = entry.friends_only

        if state.authed or state.friend:
            entry.friends_only = False
        elif entry.friends_only:
            pass

        if not entry.friends_only:
            entry_obj.gls_link = '%s/%s' % (
                reverse('entry', args=[cast(int, entry.pk)]),
                gls_slugify(truncatewords(entry.title, 7)),
            )
        else:
            entry_obj.gls_link = '%s/' % (
                reverse('entry', args=[cast(int, entry.pk)])
            )
            if 'title' in query.page:
                del query.page['title']

        entry_obj.gls_absolute_link = '%s%s' % (
            query.page['site_url'],
            entry_obj.gls_link,
        )
        entry_obj.friends_login_url = build_friends_login_url(entry_obj.gls_absolute_link)


def validate_exact_entry_request(
    state: IndexRequestState, query: IndexQueryState, entries: Any
) -> HttpResponse | None:
    if 'exactentry' not in query.page:
        return None

    if not len(entries):
        raise Http404

    gls_link = entries[0].gls_link
    if gls_link != state.request.path:
        return HttpResponsePermanentRedirect(gls_link)

    query.page['canonical_link'] = urljoin(settings.BASE_URL, gls_link)
    return None


def dispatch_index_format(
    state: IndexRequestState, query: IndexQueryState, result: IndexResult
) -> HttpResponse:
    output_format = state.request.GET.get('format', 'html')

    if output_format == 'atom':
        return render(
            state.request,
            'stream.atom',
            {'entries': result.entries, 'page': query.page},
            content_type='application/atom+xml; charset=UTF-8',
        )

    if output_format == 'json':
        callback = state.request.GET.get('callback', False)
        return render(
            state.request,
            'stream.json',
            {'entries': result.entries, 'page': query.page, 'callback': callback},
            content_type='application/json',
        )

    if (
        output_format == 'html-pure'
        and state.request.headers.get('x-requested-with') == 'XMLHttpRequest'
    ):
        prepare_entry_actions(state, query.page, result.entries)
        payload: dict[str, Any] = {
            'next': query.page['start'],
            'stream': strip_spaces_between_tags(
                render_to_string(
                    'stream-pure.html',
                    {
                        'entries': result.entries,
                        'page': query.page,
                        'authed': state.authed,
                        'friend': state.friend,
                    },
                )
            ),
        }
        if 'nextpage' in query.page:
            payload['next'] = query.page['nextpage']
        return JsonResponse(payload)

    if output_format != 'html':
        raise Http404

    prepare_entry_actions(state, query.page, result.entries)
    context = build_full_html_context(state, query, result.entries)
    return render(state.request, 'stream.html', context)


def prepare_entry_actions(
    state: IndexRequestState, page: Page, entries: Any
) -> None:
    if not state.authed or page['ctx'] == 'favorites':
        return

    entry_ids = [cast(int, entry.pk) for entry in entries]
    favorite_ids = list(
        Favorite.objects.filter(user=state.user, entry_id__in=entry_ids).values_list(
            'entry_id', flat=True
        )
    )
    for entry in entries:
        entry_obj = entry
        entry_pk = cast(int, entry.pk)
        if entry_pk in favorite_ids:
            entry_obj.fav = True
        if entry.service.api in ('twitter', 'identica'):
            entry_obj.sms = True


def build_full_html_context(
    state: IndexRequestState, query: IndexQueryState, entries: Any
) -> dict[str, Any]:
    page = query.page
    lists = List.objects.filter(user_id=cast(int, state.user.pk)).order_by('name')
    archives = build_archive_dates(query)
    page['months12'] = [datetime.date(2010, month, 1) for month in range(1, 13)]
    page['lang'] = get_preferred_language(state.request)

    return {
        'classes': build_available_classes(state, page),
        'entries': entries,
        'lists': lists,
        'archives': archives,
        'page': page,
        'authed': state.authed,
        'friend': state.friend,
        'friend_email': state.auth_state.friend_email,
        'has_search': state.search_enable,
        'is_secure': state.request.is_secure(),
        'user': state.request.user,
    }


def build_archive_dates(query: IndexQueryState) -> Any:
    if 'exactentry' in query.page:
        archive_filters: dict[str, Any] = {}
    else:
        archive_filters = query.filters.copy()
        if query.year:
            del archive_filters['date_published__year']
        if query.month:
            del archive_filters['date_published__month']
        if query.day:
            del archive_filters['date_published__day']
    return Entry.objects.filter(**archive_filters).dates(
        'date_published', 'month', order='DESC'
    )


def build_available_classes(state: IndexRequestState, page: Page) -> list[dict[str, Any]]:
    service_filters: dict[str, Any] = {}
    if not state.authed or page['ctx'] == 'public':
        service_filters['public'] = True

    service_rows = Service.objects.filter(**service_filters).order_by('id').values(
        'api', 'cls'
    )
    classes: dict[str, dict[str, Any]] = {}
    for item in service_rows:
        cls_key = item['cls'] or item['api']
        if cls_key not in classes:
            classes[cls_key] = {'api': item['api'], 'cls': item['cls']}
    return list(classes.values())


def get_preferred_language(request: HttpRequest) -> str:
    accepted = request.META.get('HTTP_ACCEPT_LANGUAGE', '').split(',')
    for index, lang in enumerate(accepted):
        accepted[index] = lang.split(';')[0]
    return cast(str, accepted[0])


def dictfetchall(cursor: Any) -> list[dict[str, Any]]:
    desc = cursor.description
    return [dict(list(zip([col[0] for col in desc], row))) for row in cursor.fetchall()]
