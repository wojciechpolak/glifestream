"""
#  gLifestream Copyright (C) 2010, 2015, 2024, 2025 Wojciech Polak
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

import os
import hmac
import hashlib
from urllib.parse import urlsplit
from datetime import timedelta
from typing import cast
from django.conf import settings
from django.urls import reverse

from glifestream.apis.factory import ServiceFactory
from glifestream.apis.webfeed import WebfeedService
from glifestream.utils import httpclient
from glifestream.utils.time import now
from glifestream.stream.models import WebSub, Service


def _describe_http_error(e: Exception) -> str:
    """Whatever the transport managed to say about a failed hub request."""
    message = getattr(e, 'message', None)
    if message:
        return cast(str, message)
    read_fn = getattr(e, 'read', None)
    if callable(read_fn):
        return cast(str, read_fn())
    return ''


def _find_hub(feed) -> str | None:
    for link in feed.get('links', ()):
        if link.rel == 'hub':
            return cast(str, link.href)
    return None


def _subscription_secret(hub: str, service: Service) -> str:
    return hashlib.md5(
        (
            '%s:%d/%s/%s'
            % (hub, cast(int, service.pk), service.url, settings.SECRET_KEY)
        ).encode('utf-8')
    ).hexdigest()


def _hub_form_data(
    mode: str, hash_sub: str, *, verify: str, secret: str | None = None
) -> dict[str, str]:
    """The hub.* form both subscribe and unsubscribe POST."""
    callback = __get_absolute_url(reverse('websub', args=[hash_sub]))
    if settings.WEBSUB_HTTPS_CALLBACK:
        callback = callback.replace('http://', 'https://')

    data = {
        'hub.mode': mode,
        'hub.topic': __get_absolute_url(reverse('index')) + '?format=atom',
        'hub.callback': callback,
        'hub.verify': verify,
    }
    if secret:
        data['hub.secret'] = secret
    return data


def subscribe(service: Service, verbose=False):
    api = ServiceFactory.create_service(service)
    if not isinstance(api, WebfeedService):
        return {'rc': 1, 'error': 'WebSub is not supported by this API.'}

    api.fetch_only = True
    api.run()
    if api.fp_error:
        return {'rc': 1, 'error': api.fp.bozo_exception}

    hub = _find_hub(api.fp.feed)
    if not hub:
        return {'rc': 2}

    secret = _subscription_secret(hub, service)
    hash_sub = hashlib.sha1(secret.encode('utf-8')).hexdigest()[0:20]

    save_db = False
    try:
        db = WebSub.objects.get(hash=hash_sub, service=service)
    except WebSub.DoesNotExist:
        db = WebSub(hash=hash_sub, service=service, hub=hub, secret=secret)
        save_db = True

    data = _hub_form_data(
        'subscribe',
        hash_sub,
        verify='async',
        secret=secret[0:8] if 'https://' in hub else None,
    )

    try:
        r = httpclient.post(hub, data=data)
        if verbose:
            print('Response code: %d' % r.status_code)
        if save_db:
            db.save()
        return {'hub': hub, 'rc': r.status_code}
    except (IOError, httpclient.HTTPError) as e:
        error = _describe_http_error(e)
        if verbose:
            print('%s, Response: "%s"' % (e, error))
        return {'hub': hub, 'rc': error}


def unsubscribe(id_sub, verbose=False):
    try:
        db = WebSub.objects.get(id=id_sub)
    except WebSub.DoesNotExist:
        return {'rc': 1}

    data = _hub_form_data('unsubscribe', db.hash, verify='sync')

    try:
        r = httpclient.post(db.hub, data=data)
        if verbose:
            print('Response code: %d' % r.status_code)
        return {'hub': db.hub, 'rc': r.status_code}
    except (IOError, httpclient.HTTPError) as e:
        error = _describe_http_error(e)
        if verbose:
            print('%s, Response: "%s"' % (e, error))
        return {'hub': db.hub, 'rc': error}


def verify(id_sub, req_get):
    mode = req_get.get('hub.mode', None)
    lease_seconds = req_get.get('hub.lease_seconds', None)

    if mode == 'subscribe':
        try:
            db = WebSub.objects.get(hash=id_sub)
            db.verified = True
            if lease_seconds:
                db.expire = now() + timedelta(seconds=int(lease_seconds))
            db.save()
        except WebSub.DoesNotExist:
            return False
    elif mode == 'unsubscribe':
        try:
            WebSub.objects.get(hash=id_sub).delete()
        except WebSub.DoesNotExist:
            return False

    return req_get.get('hub.challenge', '')


def publish(hubs=None, verbose=False):
    hubs = hubs or settings.WEBSUB_HUBS
    url = __get_absolute_url(reverse('index')) + '?format=atom'
    if 'localhost' in url:
        return
    for hub in hubs:
        data = {'hub.mode': 'publish', 'hub.url': url}
        try:
            r = httpclient.post(hub, data=data, timeout=7)
            if verbose:
                if r.status_code == 204:
                    print('%s: Successfully pinged.' % hub)
                else:
                    print('%s: Pinged and got %d (URL: %s)' % (hub, r.status_code, url))
                    print('Response content:\n', r.content)
        except (IOError, httpclient.HTTPError) as e:
            if getattr(e, 'status_code', None) == 204:
                continue
            if verbose:
                print('%s, Response: "%s"' % (e, _describe_http_error(e)))


def accept_payload(id_sub, payload, meta=None):
    if meta is None:
        meta = {}
    try:
        db = WebSub.objects.get(hash=id_sub)
    except WebSub.DoesNotExist:
        return False
    if db.secret:
        s = hmac.new(str(db.secret).encode('utf-8'), payload, hashlib.sha1).hexdigest()
        signature = meta.get('HTTP_X_HUB_SIGNATURE', None)
        if signature and 'sha1=' in signature:
            signature = signature[5:]
        if s != signature:
            return False  # signature mismatch
    api = ServiceFactory.create_service(db.service)
    api.payload = payload
    api.run()
    return True


def renew_subscriptions(force=False, verbose=False):
    subscriptions = WebSub.objects.all().order_by('id')
    for s in subscriptions:
        if s.expire:
            d = s.expire - timedelta(days=7)
            if now() > d or force:
                subscribe(s.service, verbose)


def list_subs(raw=False):
    subscriptions = WebSub.objects.all().order_by('id')
    if raw:
        return subscriptions
    for s in subscriptions:
        print(
            '%4d V=%d hash=%s, hub=%s, topic=%s, expire=%s'
            % (cast(int, s.pk), s.verified, s.hash, s.hub, s.service.url, s.expire)
        )


def __get_absolute_url(path=''):
    if 'http' not in settings.BASE_URL:
        host = os.getenv('VIRTUAL_HOST', '')
        scheme = 'https://' if settings.WEBSUB_HTTPS_CALLBACK else 'http://'
    else:
        host = ''
        scheme = ''
    url = urlsplit('%s%s%s' % (scheme, host, settings.BASE_URL))
    return '%s://%s%s' % (url.scheme, url.netloc, path)
