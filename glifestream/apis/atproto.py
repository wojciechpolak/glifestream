"""
#  gLifestream Copyright (C) 2025, 2026 Wojciech Polak
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
            record_embed = getattr(record, 'embed', None)
            media_urls = collect_post_media_urls(record, post_embed)
            video_embed = _normalize_video_embed(post_embed, record_embed)
            e.mblob = _build_video_mblob(video_embed) if video_embed else None
            if post_embed:
                e.content += _render_image_thumbnails(
                    _extract_embed_images(post_embed), self.service.public
                )
            if video_embed:
                e.content += _render_video_thumbnail(
                    video_embed, e.link, guid, self.service.public
                )

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

    external = _extract_external_embed(post_embed)
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


def _extract_external_embed(embed: Any) -> Any:
    if not embed:
        return None
    external = getattr(embed, 'external', None)
    if external:
        return external
    media_embed = getattr(embed, 'media', None)
    if media_embed:
        return getattr(media_embed, 'external', None)
    return None


def _extract_embed_images(embed: Any) -> list[Any]:
    if not embed:
        return []
    for candidate in (getattr(embed, 'media', None), embed):
        if not candidate:
            continue
        images = getattr(candidate, 'images', None)
        if images:
            return cast(list[Any], images)
    return []


def _extract_video_embed(embed: Any) -> dict[str, Any] | None:
    if not embed:
        return None

    for candidate in (getattr(embed, 'media', None), embed):
        if not candidate:
            continue

        py_type = getattr(candidate, 'py_type', None)
        if not isinstance(py_type, str):
            py_type = None

        playlist = getattr(candidate, 'playlist', None)
        if not isinstance(playlist, str):
            playlist = None

        thumbnail = getattr(candidate, 'thumbnail', None)
        if not isinstance(thumbnail, str):
            thumbnail = None

        aspect_ratio = getattr(candidate, 'aspect_ratio', None)
        alt = getattr(candidate, 'alt', None)
        if not isinstance(alt, str):
            alt = None

        if playlist or thumbnail or (py_type and 'embed.video' in py_type):
            return {
                'playlist': playlist,
                'thumbnail': thumbnail,
                'aspect_ratio': aspect_ratio,
                'alt': alt,
            }

    return None


def _normalize_video_embed(post_embed: Any, record_embed: Any) -> dict[str, Any] | None:
    post_video = _extract_video_embed(post_embed)
    record_video = _extract_video_embed(record_embed)
    if not post_video and not record_video:
        return None

    video = {
        'playlist': None,
        'thumbnail': None,
        'aspect_ratio': None,
        'alt': None,
    }
    for source in (post_video, record_video):
        if not source:
            continue
        for key in video:
            if video[key] is None and source.get(key) is not None:
                video[key] = source[key]

    if video['playlist'] or video['thumbnail']:
        return video
    return None


def _aspect_ratio_attrs(aspect_ratio: Any) -> str:
    width = getattr(aspect_ratio, 'width', None)
    height = getattr(aspect_ratio, 'height', None)
    if isinstance(width, int) and isinstance(height, int):
        return ' width="%d" height="%d"' % (width, height)
    return ''


def _render_image_thumbnails(images: list[Any], is_public: bool) -> str:
    if not images:
        return ''

    content = ' <p class="thumbnails">'
    for view_image in images:
        image_url = view_image.thumb
        large_url = view_image.fullsize
        link = large_url
        if is_public:
            image_url = media.save_image(image_url)
        iwh = _aspect_ratio_attrs(getattr(view_image, 'aspect_ratio', None))
        content += (
            '<a href="%s" rel="nofollow" data-imgurl="%s"><img src="%s"%s alt="thumbnail" /></a> '
            % (link, large_url, image_url, iwh)
        )
    content += '</p>'
    return content


def _render_video_thumbnail(
    video: dict[str, Any], link: str, guid: str, is_public: bool
) -> str:
    thumbnail = cast(str | None, video.get('thumbnail'))
    playlist = cast(str | None, video.get('playlist'))
    if is_public:
        if thumbnail:
            thumbnail = media.save_image(thumbnail)

    alt = cast(str, video.get('alt') or 'video thumbnail')
    data_attrs = ' data-id="atproto-%s" data-link="%s"' % (escape(guid), escape(link))
    if playlist:
        data_attrs += ' data-playlist="%s"' % escape(playlist)
    if thumbnail:
        data_attrs += ' data-poster="%s"' % escape(thumbnail)

    width = getattr(video.get('aspect_ratio'), 'width', None)
    height = getattr(video.get('aspect_ratio'), 'height', None)
    if isinstance(width, int) and isinstance(height, int):
        data_attrs += ' data-width="%d" data-height="%d"' % (width, height)

    if thumbnail:
        thumb_markup = '<img src="%s" alt="%s" />' % (thumbnail, escape(alt))
    else:
        thumb_markup = escape(alt)

    return (
        ' <div%s class="play-video"><a href="%s" rel="nofollow">%s</a><div class="playbutton"></div></div>'
        % (data_attrs, escape(link), thumb_markup)
    )


def _build_video_mblob(video: dict[str, Any]) -> str | None:
    playlist = cast(str | None, video.get('playlist'))
    if not playlist:
        return None

    mblob = media.mrss_init()
    mblob['content'].append(
        [
            {
                'url': playlist,
                'medium': 'video',
                'type': 'application/x-mpegURL',
                'isdefault': 'true',
            }
        ]
    )
    return media.mrss_gen_json(mblob)
