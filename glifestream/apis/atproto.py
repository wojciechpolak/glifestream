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
from typing import Any, Optional, cast
from atproto import Client
from atproto_client.models.app.bsky.feed.defs import FeedViewPost

from django.utils import timezone
from django.utils.html import strip_tags

from glifestream.apis.base import BaseService
from glifestream.filters import expand, truncate
from glifestream.utils.html import strip_entities
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry, Service
from glifestream.stream import media
from glifestream.utils import httpclient


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
            post = cast(Any, ent.post)
            author = post.author
            record = post.record
            guid = post.cid
            if self.verbose:
                print('ID: %s' % guid)

            created_at = cast(str, record.created_at)
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
            e.author_name = author.display_name

            # double expand
            e.content = expand.run_all(expand.shorturls(cast(str, record.text)))

            post_embed = post.embed
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
                else:
                    external = getattr(post_embed, 'external', None)
                    uri = getattr(external, 'uri', None)
                    if uri and (
                        uri.startswith('https://www.youtube.com/')
                        or uri.startswith('https://www.vimeo.com/')
                    ):
                        content += '\n' + expand.videolinks(uri)
                e.content += content

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
    return entry.content
