"""
#  gLifestream Copyright (C) 2009, 2010, 2012, 2015, 2024 Wojciech Polak
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

import ipaddress
import os
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, cast

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from urllib.parse import urljoin
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError

from django.conf import settings


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL
}
READ_RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}
READ_RETRY_BACKOFF_SEC = (1, 2)
MAX_RETRY_AFTER_SEC = 30
# The longest Retry-After the fetch scheduler honours.
MAX_SCHEDULED_RETRY_AFTER_SEC = 24 * 3600
AMBIGUOUS_MEDIA_CONTENT_TYPES = {
    '',
    'application/octet-stream',
    'binary/octet-stream',
}
HTML_CONTENT_TYPES = {'text/html', 'application/xhtml+xml'}
KNOWN_FEED_CONTENT_TYPES = {
    'application/rss+xml',
    'application/atom+xml',
    'application/rdf+xml',
    'application/xml',
    'text/xml',
}


class HTTPError(requests.exceptions.RequestException):
    pass


class FetchError(HTTPError):
    def __init__(
        self,
        *,
        category: str,
        retryable: bool,
        user_message: str,
        detail: str,
        status_code: int | None = None,
        url: str | None = None,
        retry_after_sec: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.retry_after_sec = retry_after_sec
        self.category = category
        self.retryable = retryable
        self.status_code = status_code
        self.url = url
        self.user_message = user_message
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True, frozen=True)
class BodyResponse:
    response: Response
    body: bytes


_NAT64_PREFIX = ipaddress.ip_network('64:ff9b::/96')


def is_public_address(address: str) -> bool:
    """Whether `address` lies outside loopback, private, link-local and other
    special-purpose ranges. An IPv6 address that embeds an IPv4 one is judged
    by the embedded address."""
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address
    ip = ipaddress.ip_address(address.split('%', 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
        elif ip in _NAT64_PREFIX:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


class BlockedAddressError(NewConnectionError):
    """A media download connected to an address it may not reach."""

    def __init__(self, conn: HTTPConnection, detail: str) -> None:
        super().__init__(conn, detail)
        self.detail = detail


def _require_public_peer(conn: HTTPConnection, sock: socket.socket) -> socket.socket:
    peer = sock.getpeername()[0]
    if not is_public_address(peer):
        sock.close()
        raise BlockedAddressError(
            conn,
            'Refused to fetch from %s at non-public address %s.' % (conn.host, peer),
        )
    return sock


class _PublicHTTPConnection(HTTPConnection):
    def _new_conn(self) -> socket.socket:
        return _require_public_peer(self, super()._new_conn())


class _PublicHTTPSConnection(HTTPSConnection):
    def _new_conn(self) -> socket.socket:
        return _require_public_peer(self, super()._new_conn())


class _PublicHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _PublicHTTPConnection


class _PublicHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PublicHTTPSConnection


class _PublicOnlyAdapter(HTTPAdapter):
    """Checks the address each new socket actually connected to, so neither a
    redirect nor a hostname that resolves differently on the second lookup
    gets past it. Through a proxy the proxy decides what may be reached."""

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            'http': _PublicHTTPConnectionPool,
            'https': _PublicHTTPSConnectionPool,
        }


def _get_media(url: str, **kwargs: Any) -> Response:
    """`requests.get` for a URL taken from remote content.

    Whoever wrote a feed entry or a post chooses its image URLs, so by default
    such a download may reach only public addresses: content must not make
    the worker fetch from localhost, the LAN or a cloud metadata service.
    FETCH_MEDIA_ALLOW_PRIVATE_ADDRESSES lifts the restriction.
    """
    if getattr(settings, 'FETCH_MEDIA_ALLOW_PRIVATE_ADDRESSES', False):
        return requests.get(url, **kwargs)
    session = requests.Session()
    adapter = _PublicOnlyAdapter()
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session.get(url, **kwargs)


def _blocked_address_reason(
    exc: requests.exceptions.RequestException,
) -> BlockedAddressError | None:
    # requests wraps it: ConnectionError(MaxRetryError(reason=...)).
    reason = getattr(exc.args[0], 'reason', None) if exc.args else None
    return reason if isinstance(reason, BlockedAddressError) else None


def _normalize_url(url: str) -> str:
    if not url.startswith('http'):
        return 'http://' + url
    return url


def _build_http_error_detail(response: Response) -> str:
    detail = 'HTTP %d' % response.status_code
    if response.reason:
        detail += ' %s' % response.reason
    detail += ' from %s' % response.url
    return detail


def _get_category_user_message(category: str) -> str:
    messages = {
        'timeout': 'Remote request timed out.',
        'connection': 'Remote host could not be reached.',
        'rate_limited': 'Remote service rate-limited the request.',
        'remote_4xx': 'Remote service rejected the request.',
        'remote_5xx': 'Remote service returned a temporary server error.',
        'auth': 'Stored credentials were rejected by the remote service.',
        'invalid_response': 'Remote service returned an invalid or unsupported response.',
        'parse_error': 'Remote response could not be parsed.',
        'blocked_address': 'Remote address is not allowed.',
        'unexpected': 'Unexpected fetch error.',
    }
    return messages.get(category, messages['unexpected'])


def build_fetch_error(
    *,
    category: str,
    detail: str,
    retryable: bool = False,
    status_code: int | None = None,
    url: str | None = None,
    user_message: str | None = None,
    retry_after_sec: int | None = None,
) -> FetchError:
    return FetchError(
        category=category,
        retryable=retryable,
        status_code=status_code,
        url=url,
        retry_after_sec=retry_after_sec,
        user_message=user_message or _get_category_user_message(category),
        detail=detail,
    )


def classify_status_code(status_code: int) -> tuple[str, bool]:
    """The failure category of an HTTP error status, and whether to retry."""
    if status_code in (401, 403):
        category = 'auth'
    elif status_code == 429:
        category = 'rate_limited'
    elif 400 <= status_code < 500:
        category = 'remote_4xx'
    elif 500 <= status_code < 600:
        category = 'remote_5xx'
    else:
        category = 'unexpected'
    return category, status_code in READ_RETRY_STATUS_CODES


def _classify_response_error(response: Response) -> FetchError:
    status_code = response.status_code
    category, retryable = classify_status_code(status_code)
    return build_fetch_error(
        category=category,
        detail=_build_http_error_detail(response),
        retryable=retryable,
        status_code=status_code,
        url=response.url,
        retry_after_sec=_get_retry_after_sec(response),
    )


def _classify_request_exception(
    exc: requests.exceptions.RequestException, url: str
) -> FetchError:
    blocked = _blocked_address_reason(exc)
    if blocked is not None:
        return build_fetch_error(
            category='blocked_address',
            detail=blocked.detail,
            retryable=False,
            url=url,
        )
    if isinstance(exc, requests.exceptions.Timeout):
        category = 'timeout'
        retryable = True
        detail = 'Request to %s timed out.' % url
    elif isinstance(exc, requests.exceptions.ConnectionError):
        category = 'connection'
        retryable = True
        detail = 'Unable to connect to %s.' % url
    else:
        category = 'unexpected'
        retryable = False
        detail = str(exc) or 'Unexpected request error while contacting %s.' % url
    return build_fetch_error(
        category=category,
        detail=detail,
        retryable=retryable,
        url=url,
    )


def _get_retry_after_sec(response: Response) -> int | None:
    retry_after = response.headers.get('Retry-After', '').strip()
    if not retry_after:
        return None
    try:
        seconds = int(retry_after)
    except ValueError:
        return None
    return max(0, min(seconds, MAX_SCHEDULED_RETRY_AFTER_SEC))


def _normalize_content_type(content_type: str) -> str:
    value = content_type.strip().lower()
    if ';' in value:
        value = value.split(';', 1)[0]
    return value


def _is_allowed_feed_content_type(content_type: str) -> bool:
    if not content_type:
        return True
    if content_type in KNOWN_FEED_CONTENT_TYPES:
        return True
    if content_type.endswith('+xml'):
        return True
    if content_type.startswith('text/') and content_type not in HTML_CONTENT_TYPES:
        return True
    return False


def _validate_content_length(
    response: Response,
    *,
    max_bytes: int,
    label: str,
) -> None:
    header = response.headers.get('content-length', '').strip()
    if not header:
        return
    try:
        content_length = int(header)
    except ValueError:
        return
    if content_length > max_bytes:
        raise build_fetch_error(
            category='invalid_response',
            detail='%s from %s exceeds %d bytes (Content-Length=%d).'
            % (label, response.url, max_bytes, content_length),
            retryable=False,
            status_code=response.status_code,
            url=response.url,
        )


def _read_limited_body(
    response: Response,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    _validate_content_length(response, max_bytes=max_bytes, label=label)
    total = 0
    chunks: list[bytes] = []
    try:
        for chunk in response.iter_content(4096):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise build_fetch_error(
                    category='invalid_response',
                    detail='%s from %s exceeds %d bytes while streaming.'
                    % (label, response.url, max_bytes),
                    retryable=False,
                    status_code=response.status_code,
                    url=response.url,
                )
            chunks.append(chunk)
    finally:
        close = getattr(response, 'close', None)
        if callable(close):
            close()
    return b''.join(chunks)


def _decode_response_text(response: Response, body: bytes) -> str:
    encoding = response.encoding or 'utf-8'
    return body.decode(encoding, errors='replace')


def _request_read(
    url: str,
    request_func: Callable[..., Response],
    *,
    timeout: int | float = 45,
    **kwargs: Any,
) -> Response:
    normalized_url = _normalize_url(url)
    attempts = len(READ_RETRY_BACKOFF_SEC) + 1
    last_error: FetchError | None = None

    for attempt in range(attempts):
        try:
            response = request_func(normalized_url, timeout=timeout, **kwargs)
        except FetchError as exc:
            last_error = exc
            if not last_error.retryable or attempt == attempts - 1:
                raise last_error
        except requests.exceptions.RequestException as exc:
            last_error = _classify_request_exception(exc, normalized_url)
            if not last_error.retryable or attempt == attempts - 1:
                raise last_error
        else:
            if response.status_code < 400:
                return response
            last_error = _classify_response_error(response)
            if not last_error.retryable or attempt == attempts - 1:
                raise last_error
            retry_after = last_error.retry_after_sec
            if retry_after is not None:
                # A longer wait is left to the fetch scheduler.
                if retry_after > MAX_RETRY_AFTER_SEC:
                    raise last_error
                time.sleep(retry_after)
                continue

        if attempt < len(READ_RETRY_BACKOFF_SEC):
            time.sleep(READ_RETRY_BACKOFF_SEC[attempt])

    if last_error is not None:
        raise last_error
    raise build_fetch_error(
        category='unexpected',
        detail='Unexpected retry state for %s.' % normalized_url,
        retryable=False,
        url=normalized_url,
    )


def read(url: str, request_func: Callable[..., Response], **kwargs: Any) -> Response:
    return _request_read(url, request_func, **kwargs)


def get_feed(
    url: str,
    *,
    auth=None,
    timeout=45,
    max_bytes: int | None = None,
    html_sniff_bytes: int | None = None,
) -> BodyResponse:
    if max_bytes is None:
        max_bytes = int(getattr(settings, 'FETCH_FEED_MAX_BYTES', 5 * 1024 * 1024))
    if html_sniff_bytes is None:
        html_sniff_bytes = int(
            getattr(
                settings,
                'FETCH_FEED_HTML_SNIFF_BYTES',
                64 * 1024,
            )
        )
    response = _request_read(
        url,
        requests.get,
        headers=HEADERS,
        auth=auth,
        timeout=timeout,
        stream=True,
    )
    content_type = _normalize_content_type(response.headers.get('content-type', ''))
    if content_type in HTML_CONTENT_TYPES:
        body = _read_limited_body(
            response,
            max_bytes=min(max_bytes, html_sniff_bytes),
            label='HTML feed discovery response',
        )
        alturl = get_alturl_if_html(
            response,
            html_text=_decode_response_text(response, body),
        )
        if alturl is None:
            raise build_fetch_error(
                category='invalid_response',
                detail='HTML feed discovery response from %s did not expose an alternate feed link.'
                % response.url,
                retryable=False,
                status_code=response.status_code,
                url=response.url,
            )
        response = _request_read(
            alturl,
            requests.get,
            headers=HEADERS,
            auth=auth,
            timeout=timeout,
            stream=True,
        )
        content_type = _normalize_content_type(response.headers.get('content-type', ''))

    if not _is_allowed_feed_content_type(content_type):
        raise build_fetch_error(
            category='invalid_response',
            detail='Feed response from %s used unsupported content type %s.'
            % (response.url, content_type),
            retryable=False,
            status_code=response.status_code,
            url=response.url,
        )

    body = _read_limited_body(response, max_bytes=max_bytes, label='Feed response')
    return BodyResponse(response=response, body=body)


def require_json(response: Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise build_fetch_error(
            category='invalid_response',
            detail='Invalid JSON response from %s: %s' % (response.url, exc),
            retryable=False,
            status_code=response.status_code,
            url=response.url,
        ) from exc


def head(url: str, timeout=15) -> Response:
    return _request_read(url, requests.head, headers=HEADERS, timeout=timeout)


def get(url: str, data=None, auth=None, timeout=45) -> Response:
    return _request_read(
        url,
        requests.get,
        params=data,
        headers=HEADERS,
        auth=auth,
        timeout=timeout,
    )


def post(url: str, data=None, auth=None, timeout=45) -> Response:
    url = _normalize_url(url)
    try:
        return requests.post(
            url, data=data, headers=HEADERS, auth=auth, timeout=timeout
        )
    except requests.exceptions.RequestException as e:
        raise _classify_request_exception(e, url) from e


def validate_media_response(response: Response) -> str:
    content_type = _normalize_content_type(response.headers.get('content-type', ''))
    if content_type and content_type not in AMBIGUOUS_MEDIA_CONTENT_TYPES:
        if not content_type.startswith('image/'):
            raise build_fetch_error(
                category='invalid_response',
                detail='Media download from %s used unsupported content type %s.'
                % (response.url, content_type),
                retryable=False,
                status_code=response.status_code,
                url=response.url,
            )
    return content_type


def retrieve(
    url: str, filename: str, timeout=15, max_bytes: int | None = None
) -> Response:
    if max_bytes is None:
        max_bytes = int(getattr(settings, 'FETCH_MEDIA_MAX_BYTES', 10 * 1024 * 1024))
    r = _request_read(
        url,
        _get_media,
        headers=HEADERS,
        timeout=timeout,
        stream=True,
    )
    _validate_content_length(r, max_bytes=max_bytes, label='Media download')
    with open(filename, 'wb') as fp:
        total = 0
        try:
            for chunk in r.iter_content(4096):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise build_fetch_error(
                        category='invalid_response',
                        detail='Media download from %s exceeds %d bytes while streaming.'
                        % (r.url, max_bytes),
                        retryable=False,
                        status_code=r.status_code,
                        url=r.url,
                    )
                fp.write(chunk)
                fp.flush()
                os.fsync(fp.fileno())
        finally:
            close = getattr(r, 'close', None)
            if callable(close):
                close()
    return r


def get_alturl_if_html(r: Response, html_text: str | None = None) -> str | None:
    """Return alternate URL (using feed autodiscovery mechanism)
    if urlopen's Content-Type response is HTML."""

    ct = _normalize_content_type(r.headers.get('content-type', ''))
    if ct in HTML_CONTENT_TYPES:
        shortdata = html_text if html_text is not None else r.text[:2048]
        for link in re.findall(r'<link(.*?)>', shortdata):
            if 'alternate' in link:
                rx = re.search('type=[\'"](.*?)[\'"]', link)
                if not rx:
                    continue
                alt_type = rx.groups()[0]
                if alt_type in (
                    'application/rss+xml',
                    'application/atom+xml',
                    'application/rdf+xml',
                    'application/xml',
                ):
                    rx = re.search('href=[\'"](.*?)[\'"]', link)
                    if rx:
                        alt_href = rx.groups()[0]
                        return cast(str | None, urljoin(r.url, alt_href))
    return None


def gen_auth(creds: str | None) -> list[str] | None:
    """Basic auth from a service's stored `user:password` credentials."""
    if creds and creds != 'oauth':
        return creds.split(':')
    return None
