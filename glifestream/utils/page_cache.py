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

# The site-wide page cache, emptied whenever what the pages show changes.
#
# Django's cache middleware keeps a page until it expires. These keep each
# page under the current generation, a number in the cache itself, so the
# web server and the worker share it. `invalidate()` moves to a new
# generation, and the pages cached under the old one are never read again;
# the cache drops them in time.

import time
from contextvars import ContextVar
from typing import TypeVar

from django.conf import settings
from django.core.cache import caches
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.middleware.cache import FetchFromCacheMiddleware, UpdateCacheMiddleware
from django.utils.cache import patch_cache_control

GENERATION_KEY = 'page-generation'

Response = TypeVar('Response', bound=HttpResponseBase)

# The key prefix of the page the current request reads and stores, read
# once per request, so a page is never stored under a newer generation than
# the data it shows.
_key_prefix: ContextVar[str] = ContextVar('page_cache_key_prefix', default='')


def _cache():  # type: ignore[no-untyped-def]
    return caches[settings.CACHE_MIDDLEWARE_ALIAS]


def generation() -> int | None:
    """The current generation, or None for a cache that keeps nothing."""
    cache = _cache()
    value = cache.get(GENERATION_KEY)
    if value is None:
        # A time, not 1: an evicted generation must not bring back the
        # pages cached under an earlier one.
        cache.add(GENERATION_KEY, time.time_ns(), None)
        value = cache.get(GENERATION_KEY)
    return int(value) if value is not None else None


def invalidate() -> None:
    """Moves the cached pages to a new generation, once the data is saved."""
    transaction.on_commit(_next_generation)


def _next_generation() -> None:
    cache = _cache()
    try:
        cache.incr(GENERATION_KEY)
    except ValueError:
        cache.set(GENERATION_KEY, time.time_ns(), None)


def _for_the_browser(response: Response) -> Response:
    """The browser asks again every time; only the server keeps the page."""
    patch_cache_control(response, max_age=0)
    if response.has_header('Expires'):
        del response['Expires']
    return response


class UpdatePageCacheMiddleware(UpdateCacheMiddleware):
    @property
    def key_prefix(self) -> str:  # type: ignore[override]
        return _key_prefix.get()

    @key_prefix.setter
    def key_prefix(self, value: str) -> None:
        pass

    def process_response(
        self, request: HttpRequest, response: HttpResponseBase | str
    ) -> HttpResponseBase | str:
        cached = getattr(request, '_cache_update_cache', False)
        response = super().process_response(request, response)
        # Expires tells that the server kept the page.
        if (
            cached
            and isinstance(response, HttpResponseBase)
            and response.has_header('Expires')
        ):
            _for_the_browser(response)
        return response


class FetchFromPageCacheMiddleware(FetchFromCacheMiddleware):
    @property
    def key_prefix(self) -> str:  # type: ignore[override]
        return _key_prefix.get()

    @key_prefix.setter
    def key_prefix(self, value: str) -> None:
        pass

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        _key_prefix.set('%s.%s' % (settings.CACHE_MIDDLEWARE_KEY_PREFIX, generation()))
        response = super().process_request(request)
        if response is not None:
            return _for_the_browser(response)
        return None
