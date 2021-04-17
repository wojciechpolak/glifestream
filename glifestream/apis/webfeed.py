#  gLifestream Copyright (C) 2009, 2010, 2014, 2015 Wojciech Polak
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
#  with this program.  If not, see <http://www.gnu.org/licenses/>.

import feedparser
from glifestream.utils import httpclient
from glifestream.utils.time import mtime, now
from glifestream.utils.html import strip_script
from glifestream.stream.models import Entry
from glifestream.stream import media


class API:
    name = 'Webfeed API'
    limit_sec = 3600
    fetch_only = False
    payload = None

    def __init__(self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_urls(self):
        return (self.service.url,)

    def run(self):
        for url in self.get_urls():
            try:
                self.fetch(url)
            except Exception:
                pass

    def fetch(self, url):
        self.fp_error = False
        if not self.payload:
            try:
                hs = httpclient.gen_auth(self.service)
                r = httpclient.get(url, auth=hs)
                alturl = httpclient.get_alturl_if_html(r)
                if alturl:
                    r = httpclient.get(alturl, auth=hs)
                self.fp = feedparser.parse(r.text)
                self.fp.etag = r.headers.get('etag')
                self.fp.modified = r.headers.get('last-modified')
            except (IOError, httpclient.HTTPError) as e:
                self.fp_error = True
                if self.verbose:
                    # pylint: disable=no-member
                    error = e.message if hasattr(e, 'message') else ''
                    print('%s (%d) HTTPError: %s' % (self.service.api,
                                                     self.service.id,
                                                     error))
                return
        else:
            self.fp = feedparser.parse(self.payload)

        if hasattr(self.fp, 'bozo') and self.fp.bozo:
            self.fp_error = True
            if isinstance(self.fp.bozo_exception,
                          feedparser.CharacterEncodingOverride):
                self.fp_error = False
            if self.verbose:
                print('%s (%d) Bozo: %s' % (self.service.api,
                                            self.service.id, self.fp))

        if not self.fp_error:
            self.service.etag = self.fp.get('etag', '')
            if self.service.etag is None:
                self.service.etag = ''
            try:
                self.service.last_modified = mtime(self.fp.modified)
            except Exception:
                pass
            self.service.last_checked = now()
            if not self.service.link:
                self.service.link = self.fp.feed.get('link', '')
            self.service.save()
            if not self.fetch_only:
                self.process()

    def process(self):
        for ent in self.fp.entries:
            guid = ent.id if 'id' in ent else ent.link
            if self.verbose:
                print('ID: %s' % guid)
            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if not self.force_overwrite and 'updated_parsed' in ent:
                    if e.date_updated and \
                       mtime(ent.updated_parsed) <= e.date_updated:
                        continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.title = ent.title
            e.link = ent.get('feedburner_origlink', ent.get('link', ''))

            if 'author_detail' in ent:
                e.author_name = ent.author_detail.get('name', '')
                e.author_email = ent.author_detail.get('email', '')
                e.author_uri = ent.author_detail.get('href', '')
            else:
                e.author_name = ent.get('author', ent.get('creator', ''))
                if not e.author_name and 'author_detail' in self.fp.feed:
                    e.author_name = self.fp.feed.author_detail.get('name', '')
                    e.author_email = self.fp.feed.author_detail.get(
                        'email', '')
                    e.author_uri = self.fp.feed.author_detail.get('href', '')

            try:
                e.content = ent.content[0].value
            except Exception:
                e.content = ent.get('summary', ent.get('description', ''))

            if 'published_parsed' in ent:
                e.date_published = mtime(ent.published_parsed)
            elif 'updated_parsed' in ent:
                e.date_published = mtime(ent.updated_parsed)

            if 'updated_parsed' in ent:
                e.date_updated = mtime(ent.updated_parsed)

            if 'geo_lat' in ent and 'geo_long' in ent:
                e.geolat = ent.geo_lat
                e.geolng = ent.geo_long
            elif 'georss_point' in ent:
                geo = ent['georss_point'].split(' ')
                e.geolat = geo[0]
                e.geolng = geo[1]

            if 'image' in self.fp.feed:
                e.link_image = media.save_image(self.fp.feed.image.url)
            else:
                for link in ent.links:
                    if link.rel == 'image' or link.rel == 'photo':
                        e.link_image = media.save_image(link.href)

            if hasattr(self, 'custom_process'):
                self.custom_process(e, ent)  # pylint: disable=no-member

            if hasattr(e, 'custom_mblob'):
                e.mblob = e.custom_mblob
            else:
                e.mblob = None

            mblob = media.mrss_init(e.mblob)
            if 'media_content' in ent:
                mblob['content'].append(ent.media_content)
            e.mblob = media.mrss_gen_json(mblob)

            e.content = strip_script(e.content)

            try:
                e.save()
                media.extract_and_register(e)
            except Exception:
                pass


def filter_title(entry):
    return entry.title


def filter_content(entry):
    return entry.content
