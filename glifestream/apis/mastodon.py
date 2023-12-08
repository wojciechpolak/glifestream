"""
#  gLifestream Copyright (C) 2023 Wojciech Polak
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
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import gettext as _
from glifestream.filters import expand, truncate
from glifestream.gauth import gls_oauth2
from glifestream.utils import httpclient
from glifestream.utils.html import strip_entities
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry, Service
from glifestream.stream import media

BASE_URL = 'https://mastodon.social'


class API:
    name = 'Mastodon API v1.0'
    limit_sec = 120

    def __init__(self, service: Service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_base_url(self) -> str:
        return self.service.url or BASE_URL

    def get_authorize_url(self) -> str:
        return self.get_base_url() + '/oauth/authorize'

    def get_token_url(self) -> str:
        return self.get_base_url() + '/oauth/token'

    def get_urls(self) -> tuple[str]:
        if not self.service.user_id:
            return ('/api/v1/timelines/home?limit=40',)
        if not self.service.last_checked:
            return ('/api/v1/accounts/%s/statuses?limit=40' % self.service.user_id,)
        return ('/api/v1/accounts/%s/statuses' % self.service.user_id,)

    def run(self) -> None:
        for url in self.get_urls():
            try:
                if not self.service.user_id:
                    self.fetch_oauth2(self.get_base_url() + url)
                else:
                    self.fetch(self.get_base_url() + url)
            except Exception as e:
                if self.verbose:
                    print('%s (%d) Exception: %s' % (self.service.api,
                                                     self.service.id, e))
                    traceback.print_exc(file=sys.stdout)

    def fetch(self, url) -> None:
        try:
            r = httpclient.get(url)
            self.process(r.json())
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def fetch_oauth2(self, url) -> None:
        try:
            oauth = gls_oauth2.OAuth2Client(self.service)
            r = oauth.consumer.get(url)
            if r.status_code == 200:
                self.json = r.json()
                self.service.last_checked = timezone.now()
                self.service.save()
                self.process(self.json)
            elif self.verbose:
                print('%s (%d) HTTP: %s' % (self.service.api,
                                            self.service.id, r.reason))
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def process(self, entries) -> None:
        for ent in entries:
            reblog = False
            entry = ent
            if ent['reblog']:
                reblog = True
                entry = ent['reblog']

            guid = entry['url']
            if self.verbose:
                print("ID: %s" % guid)

            t = datetime.datetime.strptime(ent['created_at'][:-5],
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
                strip_entities(strip_tags(entry['content'])), max_length=40)
            e.title = e.title.replace('#', '').replace('@', '')

            e.link = entry['url']
            image_url = entry['account']['avatar_static']
            e.link_image = media.save_image(image_url, direct_image=False)

            e.date_published = t
            e.date_updated = t
            e.author_name = entry['account']['display_name']

            # double expand
            e.content = expand.run_all(expand.shorturls(entry['content']))
            if reblog:
                e.reblog = True
                e.reblog_by = ent['account']['display_name']
                e.reblog_uri = ent['uri']

            if 'media_attachments' in entry:
                content = ' <p class="thumbnails">'
                for t in entry['media_attachments']:
                    if t['type'] == 'image':
                        image_url = t['preview_url']
                        large_url = t['url']
                        link = t['remote_url']
                        if self.service.public:
                            image_url = media.save_image(image_url)
                        if 'meta' in t and 'small' in t['meta']:
                            sizes = t['meta']['small']
                            iwh = ' width="%d" height="%d"' % (sizes['width'],
                                                               sizes['height'])
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


def filter_content(entry: Entry) -> str:
    if entry.reblog:
        return _('%s reblogged') % entry.reblog_by + '\n\n' + entry.content
    return entry.content
