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
from atproto import Client
from atproto_client.models.app.bsky.feed.defs import FeedViewPost

from django.utils import timezone
from django.utils.html import strip_tags
from glifestream.filters import expand, truncate
from glifestream.utils.html import strip_entities
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry, Service
from glifestream.stream import media
from glifestream.utils import httpclient


class API:
    name = 'The AT Protocol API v1.0'
    limit_sec = 120
    count = 50

    def __init__(self, service: Service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        self.client = Client()
        if not self.service.last_checked:
            self.count = None
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def run(self) -> None:
        try:
            hs = httpclient.gen_auth(self.service)
            self.connect(hs)
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def connect(self, hs) -> None:
        try:
            self.client.login(hs[0], hs[1])
            self.service.last_checked = timezone.now()
            self.service.save()
            if self.service.user_id:
                data = self.client.get_author_feed(self.client.me.did,
                                                   filter='posts_no_replies',
                                                   limit=self.count)
            else:
                data = self.client.get_timeline(limit=self.count)
            self.process(data.feed)
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def process(self, entries: list[FeedViewPost]) -> None:
        for ent in entries:
            post = ent.post
            author = post.author
            record = post.record
            guid = post.cid
            if self.verbose:
                print('ID: %s' % guid)

            t = datetime.datetime.strptime(record.created_at[:-6],
                                           "%Y-%m-%dT%H:%M:%S")
            t = t.replace(tzinfo=datetime.timezone.utc)

            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if not self.force_overwrite and \
                   e.date_updated and mtime(t.timetuple()) <= e.date_updated:
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.guid = guid
            e.title = truncate.smart(
                strip_entities(strip_tags(record.text)), max_length=40)
            e.title = e.title.replace('#', '').replace('@', '')

            e.link = self.convert_uri_to_web_link(author.handle, post.uri)
            if author.avatar:
                image_url = author.avatar
                e.link_image = media.save_image(image_url, direct_image=False)

            e.date_published = t
            e.date_updated = t
            e.author_name = author.display_name

            # double expand
            e.content = expand.run_all(expand.shorturls(record.text))

            if post.embed:
                content = ' <p class="thumbnails">'
                if hasattr(post.embed, 'images') and post.embed.images:
                    for view_image in post.embed.images:
                        image_url = view_image.thumb
                        large_url = view_image.fullsize
                        link = large_url
                        if self.service.public:
                            image_url = media.save_image(image_url)
                        if 'aspect_ratio' in view_image:
                            sizes = view_image.aspect_ratio
                            iwh = ' width="%d" height="%d"' % (sizes.width,
                                                               sizes.height)
                        else:
                            iwh = ''
                        content += '<a href="%s" rel="nofollow" data-imgurl="%s"><img src="%s"%s alt="thumbnail" /></a> ' % (
                            link, large_url, image_url, iwh)
                    content += '</p>'
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
            return f"https://bsky.app/profile/{profile}/post/{rkey}"
        except IndexError:
            raise ValueError("The provided URI does not appear to be in the expected format.")


def filter_title(entry: Entry) -> str:
    return entry.title


def filter_content(entry: Entry) -> str:
    return entry.content
