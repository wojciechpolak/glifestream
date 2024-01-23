"""
#  gLifestream Copyright (C) 2024 Wojciech Polak
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
from glifestream.filters import expand, truncate
from glifestream.gauth import gls_oauth2
from glifestream.utils.html import strip_entities
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry, Service
from glifestream.stream import media


class API:
    name = 'Pocket API v3.0'
    base_url = 'https://getpocket.com'
    limit_sec = 120
    count = 20
    tag = None

    def __init__(self, service: Service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if not self.service.last_checked:
            self.count = None
        if self.service.url:
            self.tag = self.service.url
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_base_url(self) -> str:
        return self.base_url

    def get_authorize_url(self) -> str:
        return self.get_base_url() + '/v3/oauth/authorize'

    def get_token_url(self) -> str:
        return self.get_base_url() + '/404'

    def get_urls(self) -> tuple[str]:
        return ('/v3/get',)

    def run(self) -> None:
        for url in self.get_urls():
            try:
                self.fetch_oauth2(self.get_base_url() + url)
            except Exception as e:
                if self.verbose:
                    print('%s (%d) Exception: %s' % (self.service.api,
                                                     self.service.id, e))
                    traceback.print_exc(file=sys.stdout)

    def fetch_oauth2(self, url) -> None:
        try:
            oauth = gls_oauth2.OAuth2Client(self.service)
            payload = {
                'consumer_key': oauth.consumer.client_id,
                'access_token': oauth.consumer.token['access_token'],
                # 'detailType': 'complete',
            }
            if self.count:
                payload['count'] = self.count
            if self.tag:
                payload['tag'] = self.service.url

            r = oauth.consumer.post(url, payload)
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

    def process(self, pocket_response) -> None:
        if isinstance(pocket_response['list'], list) and not len(pocket_response['list']):
            return
        entries = pocket_response['list'].values()
        for ent in entries:
            guid = ent['item_id']
            if self.verbose:
                print('ID: %s' % guid)

            t = datetime.datetime.utcfromtimestamp(int(ent['time_added']))
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
                strip_entities(strip_tags(ent['given_title'])), max_length=40)

            e.link = ent['given_url']

            e.date_published = t
            e.date_updated = t

            # double expand
            content = f'<a href="{e.link}" rel="nofollow">{ent["given_title"]}</a>\n'
            if 'excerpt' in ent and ent['excerpt']:
                content += f'<p>{ent["excerpt"]}</p>'
            e.content = expand.run_all(expand.shorturls(content))

            if 'top_image_url' in ent:
                content = '\n<p class="thumbnails">'
                image_url = ent['top_image_url']
                link = e.link
                if self.service.public:
                    image_url = media.save_image(image_url)
                content += f'<a href="{link}" rel="nofollow"><img src="{image_url}" alt="thumbnail" /></a>'
                content += '</p>'
                e.content += content

            try:
                e.save()
                media.extract_and_register(e)
            except Exception:
                pass


def filter_title(entry: Entry) -> str:
    return entry.title


def filter_content(entry: Entry) -> str:
    return entry.content
