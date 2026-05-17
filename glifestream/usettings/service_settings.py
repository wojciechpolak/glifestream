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
from typing import Any, cast
import re

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from glifestream.apis import API_LIST
from glifestream.apis.factory import ServiceFactory
from glifestream.fetching import (
    enqueue_manual_fetch,
    get_fetch_status_payload,
    is_service_fetchable,
    serialize_fetch_state,
    sync_service_schedule,
)
from glifestream.stream.models import Service
from glifestream.usettings.common import (
    build_settings_page,
    get_staff_settings_user,
)


def decorate_services_with_fetch_state(services: list[Service]) -> list[Service]:
    for service in services:
        cast(Any, service).fetch_state_snapshot = serialize_fetch_state(service)
    return services


def get_fetchable_services(services: list[Service]) -> list[Service]:
    fetchable_services: list[Service] = []
    for service in decorate_services_with_fetch_state(services):
        if cast(Any, service).fetch_state_snapshot['can_fetch']:
            fetchable_services.append(service)
    return fetchable_services


@login_required
@never_cache
def services(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = build_settings_page(
        request, title=_('Services - Settings'), menu='services'
    )
    services_all = list(
        Service.objects.select_related('fetch_state').all().order_by('api', 'name')
    )
    decorate_services_with_fetch_state(services_all)
    return render(
        request,
        'services.html',
        {
            'page': page,
            'authed': True,
            'is_secure': request.is_secure(),
            'user': request.user,
            'services_supported': API_LIST,
            'services': services_all,
        },
    )


@login_required
@never_cache
def status(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = build_settings_page(request, title=_('Status - Settings'), menu='status')
    services_all = list(
        Service.objects.select_related('fetch_state').all().order_by('api', 'name')
    )

    return render(
        request,
        'status.html',
        {
            'page': page,
            'authed': True,
            'is_secure': request.is_secure(),
            'user': request.user,
            'services': get_fetchable_services(services_all),
        },
    )


def _build_service_payload(request: HttpRequest, id_service: Any) -> dict[str, Any]:
    fetch_interval_raw = request.POST.get('fetch_interval_sec', '').strip()
    return {
        'api': request.POST.get('api', ''),
        'name': request.POST.get('name', ''),
        'cls': request.POST.get('cls', ''),
        'url': request.POST.get('url', ''),
        'user_id': request.POST.get('user_id', ''),
        'fetch_interval_sec': fetch_interval_raw,
        'display': request.POST.get('display', 'content'),
        'public': bool(request.POST.get('public', False)),
        'home': bool(request.POST.get('home', False)),
        'active': bool(request.POST.get('active', False)),
        'id': id_service,
    }


def validate_service_payload(
    payload: dict[str, Any], request: HttpRequest, method: str
) -> tuple[str, dict[str, bool], int | None]:
    miss: dict[str, bool] = {}
    fetch_interval: int | None = None
    fetch_interval_raw = cast(str, payload['fetch_interval_sec'])

    if method == 'post':
        if not payload['name']:
            miss['name'] = True
            method = 'get'
        if fetch_interval_raw:
            try:
                fetch_interval = int(fetch_interval_raw)
                if fetch_interval < 0:
                    raise ValueError
            except ValueError:
                miss['fetch_interval_sec'] = True
                method = 'get'
        if (
            payload['api'] not in ('selfposts', 'pocket', 'webfeed')
            and not payload['user_id']
            and request.POST.get('timeline', 'user') == 'user'
        ):
            miss['user_id'] = True
            method = 'get'

    return method, miss, fetch_interval


def apply_service_payload_defaults(payload: dict[str, Any]) -> None:
    if payload['api'] in (
        'delicious',
        'digg',
        'greader',
        'lastfm',
        'stumbleupon',
        'yelp',
    ):
        payload['display'] = 'both'


def persist_service_payload(
    request: HttpRequest,
    payload: dict[str, Any],
    *,
    method: str,
    fetch_interval: int | None,
) -> tuple[Service | None, Any]:
    if method != 'post':
        return None, payload.get('id')

    try:
        try:
            id_service = payload.get('id')
            if not id_service:
                raise Service.DoesNotExist
            srv = Service.objects.get(id=id_service)
        except Service.DoesNotExist:
            srv = Service()
        for k, v in payload.items():
            if k != 'id':
                setattr(srv, k, v)
    except Exception as exc:
        print(exc)
        return None, payload.get('id')

    try:
        basic_user = request.POST.get('basic_user', None)
        basic_pass = request.POST.get('basic_pass', None)

        auth = request.POST.get('auth', 'none')
        if auth == 'basic' and basic_user and basic_pass:
            srv.creds = basic_user + ':' + basic_pass
        elif auth == 'oauth' or auth == 'oauth2':
            srv.creds = auth
        elif auth == 'none':
            srv.creds = ''

        payload['need_import'] = not srv.pk
        srv.fetch_interval_sec = fetch_interval
        srv.save()
        sync_service_schedule(srv)
        return srv, srv.pk
    except Exception as exc:
        print(exc)
        return srv, payload.get('id')


def load_service_payload_state(
    payload: dict[str, Any], id_service: Any, miss: dict[str, bool]
) -> None:
    if id_service:
        try:
            srv = Service.objects.get(id=id_service)
            if len(miss) == 0:
                payload.update(
                    {
                        'id': srv.pk,
                        'api': srv.api,
                        'name': srv.name,
                        'cls': srv.cls,
                        'url': srv.url,
                        'user_id': srv.user_id,
                        'fetch_interval_sec': srv.fetch_interval_sec or '',
                        'creds': srv.creds,
                        'display': srv.display,
                        'public': srv.public,
                        'home': srv.home,
                        'active': srv.active,
                    }
                )
            else:
                payload['id'] = srv.pk
            payload['delete'] = _('delete')
        except Service.DoesNotExist:
            pass
    else:
        payload['home'] = True
        payload['active'] = True

    if 'creds' not in payload:
        payload['creds'] = ''


def build_service_form_response(
    request: HttpRequest,
    payload: dict[str, Any],
    *,
    method: str,
    miss: dict[str, bool],
    id_service: Any,
) -> dict[str, Any]:
    s = cast(Any, payload)

    s['fields'] = [
        {
            'type': 'text',
            'name': 'name',
            'placeholder': s['api'].capitalize(),
            'value': s['name'],
            'label': _('Short name'),
            'miss': miss.get('name', False),
        },
        {
            'type': 'text',
            'name': 'cls',
            'value': s['cls'],
            'label': _('Class name'),
            'hint': _('Any name for the service classification; a category.'),
        },
    ]

    if s['api'] == 'webfeed':
        s['fields'].append(
            {
                'type': 'text',
                'name': 'url',
                'value': s['url'],
                'label': _('URL'),
                'miss': miss.get('url', False),
            }
        )

    elif s['api'] in (
        'atproto',
        'fb',
        'friendfeed',
        'mastodon',
        'pixelfed',
        'twitter',
    ):
        v = 'user' if s['user_id'] else 'home'
        s['fields'].append(
            {
                'type': 'select',
                'name': 'timeline',
                'options': (
                    ('user', _('User timeline')),
                    ('home', _('Home timeline')),
                ),
                'value': v,
                'label': _('Timeline'),
            }
        )
        s['fields'].append(
            {
                'type': 'text',
                'name': 'url',
                'value': s['url'],
                'label': _('URL'),
                'deps': {'timeline': 'user'},
            }
        )
        s['fields'].append(
            {
                'type': 'text',
                'name': 'user_id',
                'value': s['user_id'],
                'label': _('User ID'),
                'deps': {'timeline': 'user'},
            }
        )

    elif s['api'] in ('pocket',):
        s['fields'].append(
            {
                'type': 'text',
                'name': 'url',
                'value': s['url'],
                'label': _('Tag name'),
                'hint': _('Optional tag name.'),
            }
        )

    elif s['api'] != 'selfposts':
        s['fields'].append(
            {
                'type': 'text',
                'name': 'url',
                'value': s['url'],
                'label': _('ID/Username'),
                'miss': miss.get('url', False),
            }
        )

    if s['api'] != 'selfposts':
        s['fields'].append(
            {
                'type': 'number',
                'name': 'fetch_interval_sec',
                'value': s['fetch_interval_sec'],
                'label': _('Fetch interval (seconds)'),
                'hint': _(
                    'Leave empty to use the service default refresh interval.'
                ),
                'miss': miss.get('fetch_interval_sec', False),
            }
        )

    if s['api'] in (
        'webfeed',
        'atproto',
        'friendfeed',
        'mastodon',
        'pixelfed',
        'pocket',
        'twitter',
    ):
        basic_user = ''
        if s['creds'] == 'oauth':
            v = 'oauth'
        elif s['creds'] == 'oauth2':
            v = 'oauth2'
        elif s['creds']:
            v = 'basic'
            basic_user = s['creds'].split(':', 1)[0]
        else:
            v = 'none'

        s['fields'].append(
            {
                'type': 'select',
                'name': 'auth',
                'options': (
                    ('none', _('none')),
                    ('basic', _('Basic')),
                    ('oauth', _('OAuth 1.0')),
                    ('oauth2', _('OAuth 2.0')),
                ),
                'value': v,
                'label': _('Authorization'),
            }
        )

        if 'id' in s:
            s['fields'].append(
                {
                    'type': 'link',
                    'name': 'oauth_conf',
                    'value': _('configure access'),
                    'href': '#',
                    'label': '',
                    'deps': {'auth': 'oauth'},
                }
            )
            s['fields'].append(
                {
                    'type': 'link',
                    'name': 'oauth2_conf',
                    'value': _('configure access'),
                    'href': '#',
                    'label': '',
                    'deps': {'auth': 'oauth2'},
                }
            )

        s['fields'].append(
            {
                'type': 'text',
                'name': 'basic_user',
                'value': basic_user,
                'label': _('Basic username'),
                'deps': {'auth': 'basic'},
            }
        )
        s['fields'].append(
            {
                'type': 'password',
                'name': 'basic_pass',
                'value': '',
                'label': _('Basic password'),
                'deps': {'auth': 'basic'},
            }
        )

    if s['api'] in ('webfeed', 'flickr', 'pocket', 'youtube', 'vimeo'):
        s['fields'].append(
            {
                'type': 'select',
                'name': 'display',
                'options': (
                    ('both', _('Title and Contents')),
                    ('content', _('Contents only')),
                    ('title', _('Title only')),
                ),
                'value': s['display'],
                'label': _("Display entries'"),
            }
        )

    s['fields'].append(
        {
            'type': 'checkbox',
            'name': 'public',
            'checked': s['public'],
            'label': _('Public'),
            'hint': _('Public services are visible to anyone.'),
        }
    )

    s['fields'].append(
        {
            'type': 'checkbox',
            'name': 'home',
            'checked': s['home'],
            'label': _('Home'),
            'hint': _(
                'If unchecked, this stream will be still active, but hidden and thus visible '
                'only via custom lists.'
            ),
        }
    )

    if s['api'] != 'selfposts':
        s['fields'].append(
            {
                'type': 'checkbox',
                'name': 'active',
                'checked': s['active'],
                'label': _('Active'),
                'hint': _('If not active, this service will not be further updated.'),
            }
        )

    if 'creds' in s:
        del s['creds']

    s['action'] = request.build_absolute_uri()
    s['method'] = method
    s['save'] = _('Save')
    s['cancel'] = _('Cancel')
    s['can_fetch'] = bool(
        s['api'] and is_service_fetchable(Service(api=cast(str, s['api'])))
    )
    if id_service:
        srv = Service.objects.select_related('fetch_state').get(id=id_service)
        s['fetch_status'] = serialize_fetch_state(srv)
    return payload


def normalize_imported_service(url: str, title: str, cls: str = 'webfeed') -> None:
    api_name = 'webfeed'

    if 'flickr.com' in url:
        m = re.search(
            r'flickr.com/services/feeds/photos_public\.gne\?id=([0-9@A-Z]+)', url
        )
        if m:
            url = m.groups()[0]
        url = url.replace('format=atom', 'format=rss_200')
        api_name = 'flickr'
        cls = 'photos'
    elif 'twitter.com' in url:
        m = re.search(r'twitter.com/1/statuses/user_timeline/(\w+)\.', url)
        if m:
            url = m.groups()[0]
            api_name = 'twitter'
            cls = 'sms'
    elif 'vimeo.com' in url:
        m = re.search(r'vimeo.com/([\w/]+)/\w+/rss', url)
        if m:
            url = m.groups()[0]
            url = url.replace('channels/', 'channel/')
            url = url.replace('groups/', 'group/')
            api_name = 'vimeo'
            cls = 'videos'
    elif 'youtube.com' in url:
        m = re.search(r'gdata.youtube.com/feeds/api/users/(\w+)', url)
        if m:
            url = m.groups()[0]
        api_name = 'youtube'
        cls = 'videos'
    elif 'yelp.com/syndicate' in url:
        api_name = 'yelp'
        cls = 'reviews'

    try:
        try:
            Service.objects.get(api=api_name, url=url)
        except Service.DoesNotExist:
            if api_name in ('vimeo', 'webfeed', 'yelp', 'youtube'):
                display = 'both'
            else:
                display = 'content'
            service = Service(
                api=api_name, cls=cls, url=url, name=title, display=display
            )
            service.save()
    except Exception:
        pass


def handle_opml_import_file(xml: bytes) -> None:
    from xml.dom.minidom import parseString

    dom = parseString(xml)
    body = dom.getElementsByTagName('body')
    for e in body[0].childNodes:
        if e.nodeName == 'outline':
            tp = cast(Any, e).getAttribute('type')
            if tp == 'rss':
                xml_url = cast(Any, e).getAttribute('xmlUrl')
                title = cast(Any, e).getAttribute('text') or cast(Any, e).getAttribute(
                    'title'
                )
                normalize_imported_service(xml_url, title)
            elif not tp:
                cls = cast(Any, e).getAttribute('text') or cast(Any, e).getAttribute(
                    'title'
                )
                cls = cls.lower()
                for f in e.childNodes:
                    if (
                        f.nodeName == 'outline'
                        and cast(Any, f).getAttribute('type') == 'rss'
                    ):
                        xml_url = cast(Any, f).getAttribute('xmlUrl')
                        title = cast(Any, f).getAttribute('text') or cast(
                            Any, f
                        ).getAttribute('title')
                        normalize_imported_service(xml_url, title, cls)


@login_required
def opml(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    cmd = args.get('cmd', '')

    if cmd == 'import':
        if 'opml' in request.FILES:
            xml = cast(Any, request.FILES['opml']).read()
            handle_opml_import_file(xml)

        return HttpResponseRedirect(reverse('usettings-services'))

    if cmd == 'export':
        excluded_apis = ('selfposts', 'fb')
        services: Any = Service.objects.exclude(api__in=excluded_apis).order_by('name')

        srvs = []
        for service in services:
            try:
                service_instance = ServiceFactory.create_service(service)
                srvs.extend(
                    [{'name': service.name, 'url': u} for u in service_instance.get_urls()]
                )
            except Exception:
                pass

        res = render(request, 'opml.xml', {'services': srvs}, content_type='text/xml')
        res['Content-Disposition'] = 'attachment; filename="gls-services.xml"'
        return res

    return HttpResponse()


def handle_fetch_status_api(
    request: HttpRequest, user: Any, cmd: str, id_service: Any
) -> HttpResponse:
    ids_arg = request.GET.get('id', request.POST.get('id', ''))
    ids = None
    if ids_arg:
        ids = [int(item) for item in ids_arg.split(',') if item.strip()]
    return JsonResponse(get_fetch_status_payload(ids))


def handle_service_api(
    request: HttpRequest, user: Any, cmd: str, id_service: Any
) -> HttpResponse:
    method = request.POST.get('method', 'get')
    payload = _build_service_payload(request, id_service)
    method, miss, fetch_interval = validate_service_payload(payload, request, method)
    apply_service_payload_defaults(payload)
    _, id_service = persist_service_payload(
        request,
        payload,
        method=method,
        fetch_interval=fetch_interval,
    )
    load_service_payload_state(payload, id_service, miss)
    return JsonResponse(
        build_service_form_response(
            request,
            payload,
            method=method,
            miss=miss,
            id_service=id_service,
        )
    )


def handle_fetch_now_api(
    request: HttpRequest, user: Any, cmd: str, id_service: Any
) -> HttpResponse:
    if not id_service:
        return HttpResponse()
    try:
        service = Service.objects.select_related('fetch_state').get(id=id_service)
        if not is_service_fetchable(service):
            return JsonResponse(
                {'error': _('This service cannot be fetched.')}, status=400
            )
        result = enqueue_manual_fetch(service, triggered_by_user=user)
        service.refresh_from_db()
        return JsonResponse(
            {
                'queued': result.queued,
                'wake_sent': result.wake_sent,
                'state': serialize_fetch_state(service),
            }
        )
    except Service.DoesNotExist:
        return JsonResponse({'error': _('Service not found.')}, status=404)


def handle_import_api(
    request: HttpRequest, user: Any, cmd: str, id_service: Any
) -> HttpResponse:
    return handle_fetch_now_api(request, user, cmd, id_service)


ServiceApiHandler = Callable[[HttpRequest, Any, str, Any], HttpResponse]

SERVICE_API_HANDLERS: dict[str, ServiceApiHandler] = {
    'fetch-status': handle_fetch_status_api,
    'service': handle_service_api,
    'fetch-now': handle_fetch_now_api,
    'import': handle_import_api,
}


@never_cache
def api(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    cmd = args.get('cmd', '')
    handler = SERVICE_API_HANDLERS.get(cmd)
    if handler is None:
        return HttpResponse()

    return handler(request, user, cmd, request.POST.get('id', None))
