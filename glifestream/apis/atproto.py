"""
#  gLifestream Copyright (C) 2025 Wojciech Polak
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

import sys
import traceback
import datetime
import re
from typing import Any, Optional, cast
from atproto import Client
from atproto_client.models.app.bsky.feed.defs import FeedViewPost

from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.utils.translation import gettext as _

from glifestream.apis.base import BaseService
from glifestream.filters import expand, truncate
from glifestream.utils.html import strip_entities, urlize
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry, Service
from glifestream.stream import media
from glifestream.utils import httpclient

URL_RE = re.compile(r'https?://\S+')


def _replace_newlines(value: str) -> str:
    return value.replace('\n', '<br/>')


def _iter_text_urls(text: str) -> list[str]:
    urls = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip('.,:;!?)]}\'"')
        if url:
            urls.append(url)
    return urls


def _render_text_fallback(text: str) -> str:
    return _replace_newlines(urlize(text, nofollow=True, autoescape=True))


def _render_facet_text(text: str, facets: list[Any]) -> str:
    text_bytes = text.encode('utf-8')
    chunks: list[str] = []
    current = 0

    for facet in sorted(
        facets,
        key=lambda item: getattr(getattr(item, 'index', None), 'byte_start', -1),
    ):
        index = getattr(facet, 'index', None)
        start = getattr(index, 'byte_start', None)
        end = getattr(index, 'byte_end', None)
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < current or start >= end or end > len(text_bytes):
            continue

        target = None
        for feature in getattr(facet, 'features', []):
            uri = getattr(feature, 'uri', None)
            did = getattr(feature, 'did', None)
            tag = getattr(feature, 'tag', None)
            if uri:
                target = cast(str, uri)
                break
            if did:
                target = 'https://bsky.app/profile/%s' % did
                break
            if tag:
                target = 'https://bsky.app/hashtag/%s' % tag
                break
        if not target:
            continue

        try:
            raw_before = text_bytes[current:start].decode('utf-8')
            raw_slice = text_bytes[start:end].decode('utf-8')
        except UnicodeDecodeError:
            continue

        chunks.append(_replace_newlines(escape(raw_before)))
        chunks.append(
            '<a href="%s" rel="nofollow">%s</a>'
            % (escape(target), _replace_newlines(escape(raw_slice)))
        )
        current = end

    try:
        raw_tail = text_bytes[current:].decode('utf-8')
    except UnicodeDecodeError:
        raw_tail = text
    chunks.append(_replace_newlines(escape(raw_tail)))
    return ''.join(chunks)


def render_post_text(record: Any) -> str:
    text = cast(str, getattr(record, 'text', '') or '')
    facets = cast(list[Any], getattr(record, 'facets', None) or [])
    if facets:
        return _render_facet_text(text, facets)
    return _render_text_fallback(text)


def collect_post_media_urls(record: Any, post_embed: Any) -> list[str]:
    text = cast(str, getattr(record, 'text', '') or '')
    urls: list[str] = []

    for facet in cast(list[Any], getattr(record, 'facets', None) or []):
        for feature in getattr(facet, 'features', []):
            uri = getattr(feature, 'uri', None)
            if uri:
                urls.append(cast(str, uri))

    urls.extend(_iter_text_urls(text))

    external = getattr(post_embed, 'external', None) if post_embed else None
    external_uri = getattr(external, 'uri', None)
    if external_uri:
        urls.append(cast(str, external_uri))

    return list(dict.fromkeys(urls))


def _get_post_created_at(record: Any) -> str:
    created_at = getattr(record, 'created_at', None) or getattr(record, 'createdAt', None)
    if not created_at:
        raise ValueError('ATProto post record is missing created_at/createdAt.')
    return cast(str, created_at)


def _get_repost_reason(entry: FeedViewPost) -> Any:
    reason = getattr(entry, 'reason', None)
    if getattr(reason, 'py_type', None) == 'app.bsky.feed.defs#reasonRepost':
        return reason
    return None


class AtProtoService(BaseService):
    name = 'The AT Protocol API v1.0'
    limit_sec = 120
    count: Optional[int] = 50

    def __init__(self, service: Service, verbose=0, force_overwrite=False):
        super().__init__(service, verbose, force_overwrite)
        self.client = Client()
        if not self.service.last_checked:
            self.count = None

    def run(self) -> None:
        try:
            hs = httpclient.gen_auth(self.service)
            self.connect(hs)
        except Exception as e:
            if self.verbose:
                print(
                    '%s (%d) Exception: %s'
                    % (self.service.api, cast(int, self.service.pk), e)
                )
                traceback.print_exc(file=sys.stdout)

    def connect(self, hs) -> None:
        try:
            self.client.login(hs[0], hs[1])
            self.service.last_checked = timezone.now()
            self.service.save()
            if self.service.user_id:
                me = cast(Any, self.client.me)
                data = self.client.get_author_feed(
                    me.did, filter='posts_no_replies', limit=self.count
                )
            else:
                data = self.client.get_timeline(limit=self.count)
            self.process(data.feed)
        except Exception as e:
            if self.verbose:
                print(
                    '%s (%d) Exception: %s'
                    % (self.service.api, cast(int, self.service.pk), e)
                )
                traceback.print_exc(file=sys.stdout)

    def process(self, entries: list[FeedViewPost]) -> None:
        for ent in entries:
            repost_reason = _get_repost_reason(ent)
            if repost_reason and self.service.skip_reblogs:
                if self.verbose:
                    print('Skipping reposted ID: %s' % ent.post.cid)
                continue

            post = cast(Any, ent.post)
            author = post.author
            record = post.record
            guid = post.cid
            if self.verbose:
                print('ID: %s' % guid)

            created_at = cast(
                str, getattr(repost_reason, 'indexed_at', None) or _get_post_created_at(record)
            )
            t = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))

            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if (
                    not self.force_overwrite
                    and e.date_updated
                    and mtime(t.timetuple()) <= e.date_updated
                ):
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.guid = guid
            e.title = truncate.smart(
                strip_entities(strip_tags(cast(str, record.text))), max_length=40
            )
            e.title = e.title.replace('#', '').replace('@', '')

            e.link = self.convert_uri_to_web_link(author.handle, post.uri)
            if author.avatar:
                image_url = author.avatar
                e.link_image = media.save_image(image_url, direct_image=False)

            e.date_published = t
            e.date_updated = t
            e.author_name = author.display_name or author.handle

            e.content = render_post_text(record)
            e.reblog = False
            e.reblog_by = ''
            e.reblog_uri = ''
            if repost_reason:
                reposted_by = repost_reason.by
                e.reblog = True
                e.reblog_by = reposted_by.display_name or reposted_by.handle
                e.reblog_uri = cast(str, getattr(repost_reason, 'uri', '') or '')

            post_embed = post.embed
            media_urls = collect_post_media_urls(record, post_embed)
            if post_embed:
                content = ''
                images = getattr(post_embed, 'images', None)
                if images:
                    content += ' <p class="thumbnails">'
                    for view_image in images:
                        image_url = view_image.thumb
                        large_url = view_image.fullsize
                        link = large_url
                        if self.service.public:
                            image_url = media.save_image(image_url)
                        if getattr(view_image, 'aspect_ratio', None):
                            sizes = view_image.aspect_ratio
                            iwh = ' width="%d" height="%d"' % (
                                sizes.width,
                                sizes.height,
                            )
                        else:
                            iwh = ''
                        content += (
                            '<a href="%s" rel="nofollow" data-imgurl="%s"><img src="%s"%s alt="thumbnail" /></a> '
                            % (link, large_url, image_url, iwh)
                        )
                    content += '</p>'
                e.content += content

            for uri in media_urls:
                video = expand.videolinks(uri)
                if video != uri:
                    e.content += '\n' + video

            try:
                e.save()
                media.extract_and_register(e)
            except Exception:
                pass

    def convert_uri_to_web_link(self, profile: str, uri: str) -> str:
        # Example URI: "at://did:plc:abcdef/app.bsky.feed.post/123456"
        try:
            rkey = uri.split('/')[-1]
            return f'https://bsky.app/profile/{profile}/post/{rkey}'
        except IndexError:
            raise ValueError(
                'The provided URI does not appear to be in the expected format.'
            )


def filter_title(entry: Entry) -> str:
    return entry.title


def filter_content(entry: Entry) -> str:
    if entry.reblog:
        return _('%s reblogged') % entry.reblog_by + '\n\n' + entry.content
    return entry.content
