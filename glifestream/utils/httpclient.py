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

import os
import re
import time
from typing import Any, Callable, cast

import requests
from requests import Response
from urllib.parse import urljoin

from django.conf import settings

from glifestream.stream.models import Service

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL
}
READ_RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}
READ_RETRY_BACKOFF_SEC = (1, 2)
MAX_RETRY_AFTER_SEC = 30


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
    ) -> None:
        super().__init__(detail)
        self.category = category
        self.retryable = retryable
        self.status_code = status_code
        self.url = url
        self.user_message = user_message
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


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
        'invalid_response': 'Remote service returned an invalid response.',
        'parse_error': 'Remote response could not be parsed.',
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
) -> FetchError:
    return FetchError(
        category=category,
        retryable=retryable,
        status_code=status_code,
        url=url,
        user_message=user_message or _get_category_user_message(category),
        detail=detail,
    )


def _classify_response_error(response: Response) -> FetchError:
    status_code = response.status_code
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
    return build_fetch_error(
        category=category,
        detail=_build_http_error_detail(response),
        retryable=status_code in READ_RETRY_STATUS_CODES,
        status_code=status_code,
        url=response.url,
    )


def _classify_request_exception(exc: requests.exceptions.RequestException, url: str) -> FetchError:
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


def _coerce_fetch_error(exc: Exception, url: str | None = None) -> FetchError:
    if isinstance(exc, FetchError):
        return exc
    if isinstance(exc, requests.exceptions.RequestException):
        return _classify_request_exception(exc, url or '')
    return build_fetch_error(
        category='unexpected',
        detail=str(exc) or 'Unexpected fetch error.',
        retryable=False,
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
    return max(0, min(seconds, MAX_RETRY_AFTER_SEC))


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
            retry_after = _get_retry_after_sec(response)
            if retry_after is not None:
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


def retrieve(url: str, filename: str, timeout=15) -> Response:
    url = _normalize_url(url)
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise _classify_request_exception(exc, url) from exc
    with open(filename, 'wb') as fp:
        for chunk in r.iter_content(4096):
            fp.write(chunk)
            fp.flush()
            os.fsync(fp.fileno())
    return r


def get_alturl_if_html(r: Response) -> str | None:
    """Return alternate URL (using feed autodiscovery mechanism)
    if urlopen's Content-Type response is HTML."""

    ct = r.headers.get('content-type', '')
    if ';' in ct:
        ct = ct.split(';', 1)[0]
    if ct in ('text/html', 'application/xhtml+xml'):
        shortdata = r.text[:2048]
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


def gen_auth(service: Service) -> list[str] | None:
    """Generate web authentication."""
    if service.creds and len(service.creds) and service.creds != 'oauth':
        return service.creds.split(':')
    return None
