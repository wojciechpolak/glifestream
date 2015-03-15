#  gLifestream Copyright (C) 2009-2015 Wojciech Polak
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

import datetime
from django.utils.encoding import force_text
from django.utils.html import strip_tags, strip_entities
from glifestream.filters import expand, truncate, twyntax
from glifestream.gauth import gls_oauth
from glifestream.utils.time import mtime, now
from glifestream.stream.models import Entry
from glifestream.stream import media

try:
    import json
except ImportError:
    import simplejson as json

OAUTH_REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
OAUTH_AUTHORIZE_URL = 'https://api.twitter.com/oauth/authorize'
OAUTH_ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'


class API:
    name = 'Twitter API v1.1'
    limit_sec = 120

    def __init__(self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_urls(self):
        if not self.service.creds:
            return ()
        if not self.service.url:
            return ('/1.1/statuses/home_timeline.json?count=50',)
        else:
            if not self.service.last_checked:
                return ('/1.1/statuses/user_timeline.json?screen_name=%s&count=200' %
                        self.service.url,)
            else:
                return ('/1.1/statuses/user_timeline.json?screen_name=%s' %
                        self.service.url,)

    def run(self):
        for url in self.get_urls():
            try:
                self.fetch(url)
            except:
                pass

    def fetch(self, url):
        try:
            oauth = gls_oauth.OAuth1Client(self.service)
            r = oauth.consumer.get('https://api.twitter.com' + url)
            if r.status_code == 200:
                self.json = r.json()
                self.service.last_checked = now()
                self.service.save()
                self.process()
            elif self.verbose:
                print('%s (%d) HTTP: %s' % (self.service.api,
                                            self.service.id, r.reason))
        except Exception as e:
            if self.verbose:
                import sys
                import traceback
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def process(self):
        for ent in self.json:
            guid = 'tag:twitter.com,2007:http://twitter.com/%s/statuses/%s' % \
                (ent['user']['screen_name'], ent['id'])
            if self.verbose:
                print("ID: %s" % guid)

            t = datetime.datetime.strptime(ent['created_at'],
                                           '%a %b %d %H:%M:%S +0000 %Y')
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
            e.title = 'Tweet: %s' % truncate.smart(
                strip_entities(strip_tags(ent['text'])), max_length=40)
            e.title = e.title.replace('#', '').replace('@', '')

            e.link  = 'https://twitter.com/%s/status/%s' % \
                (ent['user']['screen_name'], ent['id'])
            image_url = ent['user']['profile_image_url_https']
            e.link_image = media.save_image(image_url, direct_image=False)

            e.date_published = t
            e.date_updated = t
            e.author_name = ent['user']['name']

            # double expand
            e.content = 'Tweet: %s' % expand.all(expand.shorturls(ent['text']))

            if 'entities' in ent and 'media' in ent['entities']:
                content = ' <p class="thumbnails">'
                for t in ent['entities']['media']:
                    if t['type'] == 'photo':
                        tsize = 'thumb'
                        if 'media_url_https' in t:
                            image_url = '%s:%s' % (t['media_url_https'], tsize)
                            large_url = '%s:large' % t['media_url_https']
                        else:
                            image_url = '%s:%s' % (t['media_url'], tsize)
                            large_url = t['media_url']
                        link = t['expanded_url']
                        if self.service.public:
                            image_url = media.save_image(image_url)
                        if 'sizes' in t and tsize in t['sizes']:
                            sizes = t['sizes'][tsize]
                            iwh = ' width="%d" height="%d"' % (sizes['w'],
                                                               sizes['h'])
                        else:
                            iwh = ''
                        content += '<a href="%s" rel="nofollow" data-imgurl="%s"><img src="%s"%s alt="thumbnail" /></a> ' % (
                            link, large_url, image_url, iwh)
                content += '</p>'
                e.content += content

            try:
                e.save()
                media.extract_and_register(e)
            except:
                pass


def filter_content(entry):
    return twyntax.parse(force_text(entry.content))
