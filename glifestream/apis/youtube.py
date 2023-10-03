#  gLifestream Copyright (C) 2009-2021 Wojciech Polak
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

import sys
import traceback
import datetime
from django.utils.translation import gettext as _
from glifestream.stream import media
from glifestream.stream.models import Entry
from glifestream.utils import httpclient
from glifestream.utils.time import mtime, now


class API:
    name = 'YouTube API v3'
    limit_sec = 3600
    playlist_types = {}

    def __init__(self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_urls(self):
        if self.service.url.startswith('http://') or \
           self.service.url.startswith('https://'):
            return (self.service.url,)
        else:
            urls = []
            if ':' in self.service.url:
                apikey, playlists = self.service.url.split(':')
                for playlist in playlists.split(','):
                    if '#' in playlist:
                        playlist, kind = playlist.split('#')
                    else:
                        kind = 'video'
                    url = ('https://www.googleapis.com/youtube/v3/'
                           'playlistItems?part=snippet,contentDetails,status&'
                           'playlistId=%s&'
                           'maxResults=25&'
                           'key=%s' % (playlist, apikey))
                    self.playlist_types[url] = kind
                    urls.append(url)
            return urls

    def run(self):
        for url in self.get_urls():
            try:
                self.fetch(url)
            except Exception:
                pass

    def fetch(self, url):
        try:
            r = httpclient.get(url)
            if r.status_code == 200:
                self.json = r.json()
                self.service.last_checked = now()
                self.service.save()
                self.process(url)
            elif self.verbose:
                print('%s (%d) HTTP: %s' % (self.service.api,
                                            self.service.id, r.reason))
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def process(self, url):
        for ent in self.json.get('items', ()):
            snippet = ent.get('snippet', {})

            vid = ent['contentDetails']['videoId']
            if self.playlist_types[url] == 'favorite':
                guid = 'tag:youtube.com,2008:favorite:%s' % ent.get('id')
            else:
                guid = 'tag:youtube.com,2008:video:%s' % vid

            try:
                t = datetime.datetime.strptime(snippet['publishedAt'],
                                               '%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                t = datetime.datetime.strptime(snippet['publishedAt'],
                                               '%Y-%m-%dT%H:%M:%S.000Z')

            if self.verbose:
                print("ID: %s" % guid)
            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if not self.force_overwrite and e.date_updated \
                   and mtime(t.timetuple()) <= e.date_updated:
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.title = snippet['title']
            e.link = 'https://www.youtube.com/watch?v=%s' % vid
            e.date_published = t
            e.date_updated = t
            e.author_name = snippet['channelTitle']

            if vid and 'thumbnails' in snippet and 'default' in snippet['thumbnails']:
                tn = None
                if 'medium' in snippet['thumbnails']:
                    tn = snippet['thumbnails']['medium']
                    tn['width'], tn['height'] = 320, 180
                elif 'high' in snippet['thumbnails']:
                    tn = snippet['thumbnails']['high']
                    tn['width'], tn['height'] = 200, 150
                if not tn:
                    tn = snippet['thumbnails']['default']
                    tn['width'], tn['height'] = 200, 150

                if self.service.public:
                    tn['url'] = media.save_image(tn['url'], downscale=True,
                                                 size=(tn['width'], tn['height']))

                e.content = """<table class="vc"><tr><td><div id="youtube-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="%s" height="%s" alt="YouTube Video" /></a><div class="playbutton"></div></div></td></tr></table>""" % (
                    vid, e.link, tn['url'], tn['width'], tn['height'])
            else:
                e.content = '<a href="%s">%s</a>' % (e.link, e.title)

            try:
                e.save()
            except Exception as exc:
                print(exc)


def filter_title(entry):
    if 'favorite' in entry.guid:
        return _('Favorited %s') % ('<em>' + entry.title + '</em>')
    else:
        return _('Published %s') % ('<em>' + entry.title + '</em>')
