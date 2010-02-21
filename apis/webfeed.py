#  gLifestream Copyright (C) 2009, 2010 Wojciech Polak
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
import socket
import urlparse
from django.conf import settings
from glifestream.utils.time import mtime, now
from glifestream.utils.html import strip_script
from glifestream.stream.models import Entry
from glifestream.stream import media

class API:
    name = 'Webfeed API'
    limit_sec = 3600
    fetch_only = False
    payload = None

    def __init__ (self, service, verbose = 0, force_overwrite = False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print '%s: %s' % (self.name, self.service)

    def run (self):
        try:
            self.fetch (self.service.url)
        except:
            pass

    def fetch (self, url):
        url = urlparse.urlsplit (url)
        if self.service.creds:
            if url.query:
                url = '%s://%s@%s%s?%s' % (url.scheme, self.service.creds,
                                           url.netloc, url.path, url.query)
            else:
                url = '%s://%s@%s%s' % (url.scheme, self.service.creds,
                                        url.netloc, url.path)
        else:
            if url.query:
                url = '%s://%s%s?%s' % (url.scheme, url.netloc, url.path,
                                        url.query)
            else:
                url = '%s://%s%s' % (url.scheme, url.netloc, url.path)
        self.url = url

        socket.setdefaulttimeout (45)
        agent = 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL
        self.fp = feedparser.parse (self.payload or url, agent=agent)
        self.fp_error = False

        if hasattr (self.fp, 'bozo') and self.fp.bozo:
            self.fp_error = True
            if isinstance (self.fp.bozo_exception,
                           feedparser.CharacterEncodingOverride):
                self.fp_error = False
            if self.verbose:
                print '%s (%d) Bozo: %s' % (self.service.api,
                                            self.service.id, self.fp)

        if not self.fp_error:
            self.service.etag = self.fp.get ('etag', '')
            if self.service.etag is None:
                self.service.etag = ''
            try:
                self.service.last_modified = mtime (self.fp.modified)
            except:
                pass
            self.service.last_checked = now ()
            if not self.service.link:
                self.service.link = self.fp.feed.get ('link', '')
            self.service.save ()
            if not self.fetch_only:
                self.process ()

    def process (self):
        for ent in self.fp.entries:
            guid = ent.id if 'id' in ent else ent.link
            if self.verbose:
                print 'ID: %s' % guid
            try:
                e = Entry.objects.get (service=self.service, guid=guid)
                if not self.force_overwrite and ent.has_key ('updated_parsed'):
                    if e.date_updated and \
                       mtime (ent.updated_parsed) <= e.date_updated:
                        continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry (service=self.service, guid=guid)

            e.title = ent.title
            e.link = ent.get ('feedburner_origlink', ent.get ('link', ''))

            if ent.has_key ('author_detail'):
                e.author_name = ent.author_detail.get ('name', '')
                e.author_email = ent.author_detail.get ('email', '')
                e.author_uri = ent.author_detail.get ('href', '')
            else:
                e.author_name = ent.get ('author', ent.get ('creator', ''))
                if not e.author_name and self.fp.feed.has_key ('author_detail'):
                    e.author_name = self.fp.feed.author_detail.get ('name', '')
                    e.author_email = self.fp.feed.author_detail.get ('email', '')
                    e.author_uri = self.fp.feed.author_detail.get ('href', '')

            try:
                e.content = ent.content[0].value
            except:
                e.content = ent.get ('summary', ent.get ('description', ''))

            if ent.has_key ('published_parsed'):
                e.date_published = mtime (ent.published_parsed)
            elif ent.has_key ('updated_parsed'):
                e.date_published = mtime (ent.updated_parsed)

            if ent.has_key ('updated_parsed'):
                e.date_updated = mtime (ent.updated_parsed)

            if ent.has_key ('geo_lat') and ent.has_key ('geo_long'):
                e.geolat = ent.geo_lat
                e.geolng = ent.geo_long

            if self.fp.feed.has_key ('image'):
                e.link_image = media.save_image (self.fp.feed.image.url)
            else:
                for link in ent.links:
                    if link.rel == 'image':
                        e.link_image = media.save_image (link.href)

            if hasattr (self, 'custom_process'):
                self.custom_process (e, ent)

            if hasattr (e, 'custom_mblob'):
                e.mblob = e.custom_mblob
            else:
                e.mblob = None

            mblob = media.mrss_init (e.mblob)
            if 'media_content' in ent:
                mblob['content'].append (ent.media_content)
            e.mblob = media.mrss_gen_json (mblob)

            e.content = strip_script (e.content)

            try:
                e.save ()
                media.extract_and_register (e)
            except:
                pass

def filter_title (entry):
    return entry.title

def filter_content (entry):
    return entry.content
