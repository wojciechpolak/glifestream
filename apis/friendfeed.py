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

import re
import datetime
from django.utils.html import strip_tags, strip_entities
from glifestream.filters import truncate
from glifestream.utils import httpclient
from glifestream.utils.time import mtime, now
from glifestream.utils.html import bytes_to_human
from glifestream.stream.models import Entry
from glifestream.stream import media

try:
    import json
except ImportError:
    import simplejson as json

OAUTH_REQUEST_TOKEN_URL = 'https://friendfeed.com/account/oauth/request_token'
OAUTH_AUTHORIZE_URL     = 'https://friendfeed.com/account/oauth/authorize'
OAUTH_ACCESS_TOKEN_URL  = 'https://friendfeed.com/account/oauth/access_token'

class API:
    name = 'FriendFeed API v2'
    limit_sec = 180

    def __init__ (self, service, verbose = 0, force_overwrite = False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print '%s: %s' % (self.name, self.service)

    def run (self):
        if not self.service.url:
            self.service.link = 'http://friendfeed.com/'
            self.fetch ('/v2/feed/home?fof=1&num=50')
        elif not self.service.last_checked:
            self.service.link = 'http://friendfeed.com/%s' % self.service.url
            self.fetch ('/v2/feed/%s?num=250' % self.service.url)
        else:
            self.fetch ('/v2/feed/%s' % self.service.url)

    def fetch (self, url):
        try:
            hs = httpclient.gen_auth_hs (self.service,
                                         'http://friendfeed-api.com' + url)
            r = httpclient.get ('friendfeed-api.com', url, headers=hs)
            if r.status == 200:
                self.json = json.loads (r.data.decode ('utf_8'))
                self.service.last_checked = now ()
                self.service.save ()
                self.process ()
            elif self.verbose:
                print '%s (%d) HTTP: %s' % (self.service.api,
                                            self.service.id, r.reason)
        except Exception, e:
            if self.verbose:
                import sys, traceback
                print '%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e)
                traceback.print_exc (file=sys.stdout)

    def process (self):
        for ent in self.json['entries']:
            id = ent['id'][2:]
            uuid = '%s-%s-%s-%s-%s' % (id[0:8], id[8:12], id[12:16],
                                       id[16:20], id[20:])
            guid = 'tag:friendfeed.com,2007:%s' % uuid
            if self.verbose:
                print "ID: %s" % guid

            t = datetime.datetime.strptime (ent['date'], '%Y-%m-%dT%H:%M:%SZ')
            try:
                e = Entry.objects.get (service=self.service, guid=guid)
                if not self.force_overwrite and \
                   e.date_updated and mtime (t.timetuple ()) <= e.date_updated:
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry (service=self.service, guid=guid)

            e.guid = guid
            e.title = truncate.smart_truncate (strip_entities (strip_tags (ent['body'])), length=40)
            e.link  = ent['url']
            e.link_image = media.save_image ('http://friendfeed-api.com/v2/picture/%s' % ent['from']['id'])

            e.date_published = t
            e.date_updated = t
            e.author_name = ent['from']['name']

            content = ent['body']
            if 'thumbnails' in ent:
                content += '<p class="thumbnails">'
                for t in ent['thumbnails']:
                    if self.service.public:
                        t['url'] = media.save_image (t['url'])
                    if 'width' in t and 'height' in t:
                        iwh = ' width="%d" height="%d"' % (t['width'],
                                                           t['height'])
                    else:
                        iwh = ''

                    if 'friendfeed.com/e/' in t['link'] and \
                       ('youtube.com' in t['url'] or 'ytimg.com' in t['url']):
                        m = re.search (r'/vi/([\-\w]+)/', t['url'])
                        yid = m.groups ()[0] if m else None
                        if yid:
                            t['link'] = 'http://www.youtube.com/watch?v=%s' % yid

                    content += '<a href="%s" rel="nofollow"><img src="%s"%s alt="thumbnail" /></a> ' % (t['link'], t['url'], iwh)
                content += '</p>'

            if 'files' in ent:
                content += '<ul class="files">\n'
                for f in ent['files']:
                    if 'friendfeed-media' in f['url']:
                        content += '  <li><a href="%s" rel="nofollow">%s</a>' % (f['url'], f['name'])
                        if 'size' in f:
                            content += ' <span class="size">%s</span>' % bytes_to_human (f['size'])
                        content += '</li>\n'
                content += '</ul>\n'

            e.content = content

            try:
                e.save ()
                media.extract_and_register (e)
            except:
                pass
