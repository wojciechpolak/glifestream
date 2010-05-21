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

from django.template.defaultfilters import title
from django.utils.translation import ugettext as _
from glifestream.utils import httpclient
from glifestream.utils.time import mtime, now
from glifestream.stream.models import Entry
from glifestream.stream import media

try:
    import json
except ImportError:
    import simplejson as json

class API:
    name = 'Vimeo Simple API v2'
    limit_sec = 3600

    def __init__ (self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print '%s: %s' % (self.name, self.service)

    def get_urls (self):
        if '/' in self.service.url:
            url = self.service.url.replace ('channel/', 'channels/')
            url = url.replace ('group/', 'groups/')
            return ('http://vimeo.com/%s/videos/rss' % url,)
        else:
            return ('http://vimeo.com/%s/likes/rss' % self.service.url,
                    'http://vimeo.com/%s/videos/rss' % self.service.url)

    def run (self):
        if not self.service.link:
            self.service.link = 'http://vimeo.com/%s' % self.service.url
        if '/' in self.service.url:
            self.process = self.process_videos
            self.fetch ('/api/v2/%s/videos.json' % self.service.url)
        else:
            self.process = self.process_userdid
            self.fetch ('/api/v2/activity/%s/user_did.json' % self.service.url)
            self.process = self.process_videos
            self.fetch ('/api/v2/%s/videos.json' % self.service.url)

    def fetch (self, url):
        try:
            r = httpclient.get ('vimeo.com', url)
            if r.status == 200:
                self.json = json.loads (r.data)
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

    def process_userdid (self):
        """Process what user did."""
        for ent in self.json:
            if 'type' in ent and ent['type'] == 'like':
                date = ent['date'][:10]
                guid = 'tag:vimeo,%s:clip%s' % (date, ent['video_id'])
                if self.verbose:
                    print "ID: %s" % guid
                try:
                    e = Entry.objects.get (service=self.service, guid=guid)
                    if not self.force_overwrite and e.date_updated \
                       and mtime (ent['date']) <= e.date_updated:
                        continue
                    if e.protected:
                        continue
                except Entry.DoesNotExist:
                    e = Entry (service=self.service, guid=guid)

                e.title = ent['video_title']
                e.link  = ent['video_url']
                e.date_published = ent['date']
                e.date_updated = ent['date']
                e.author_name = ent['user_name']

                e.idata = 'liked'

                if self.service.public:
                    ent['video_thumbnail_medium'] = media.save_image (ent['video_thumbnail_medium'])

                e.content = """<table class="vc"><tr><td><div id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="200" height="150" alt="%s" /></a><div class="playbutton"></div></div></td></tr></table>""" % (ent['video_id'], e.link, ent['video_thumbnail_medium'], ent['video_title'])

                mblob = media.mrss_init ()
                mblob['content'].append ([{'url': 'http://vimeo.com/moogaloop.swf?clip_id=' + ent['video_id'],
                                           'type': 'application/x-shockwave-flash',
                                           'medium': 'video'}])
                e.mblob = media.mrss_gen_json (mblob)

                try:
                    e.save ()
                except:
                    pass

    def process_videos (self):
        """Process videos uploaded by user."""
        for ent in self.json:
            date = ent['upload_date'][:10]
            guid = 'tag:vimeo,%s:clip%s' % (date, ent['id'])
            if self.verbose:
                print "ID: %s" % guid
            try:
                e = Entry.objects.get (service=self.service, guid=guid)
                if not self.force_overwrite and e.date_updated \
                   and mtime (ent['upload_date']) <= e.date_updated:
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry (service=self.service, guid=guid)

            e.title = ent['title']
            e.link  = ent['url']
            e.date_published = ent['upload_date']
            e.date_updated = ent['upload_date']
            e.author_name = ent['user_name']

            if self.service.public:
                ent['thumbnail_medium'] = media.save_image (ent['thumbnail_medium'])

            e.content = """<table class="vc"><tr><td><div id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="200" height="150" alt="%s" /></a><div class="playbutton"></div></div></td></tr></table>""" % (ent['id'], e.link, ent['thumbnail_medium'], ent['title'])

            mblob = media.mrss_init ()
            mblob['content'].append ([{'url': 'http://vimeo.com/moogaloop.swf?clip_id=' + ent['id'],
                                       'type': 'application/x-shockwave-flash',
                                       'medium': 'video'}])
            e.mblob = media.mrss_gen_json (mblob)

            try:
                e.save ()
                media.extract_and_register (e)
            except:
                pass

def get_thumbnail_url (id):
    try:
        r = httpclient.urlopen ('vimeo.com/api/v2/video/%s.json' % id)
        if r.code == 200:
            jsn = json.loads (r.data)
            if 'thumbnail_medium' in jsn[0]:
                return jsn[0]['thumbnail_medium']
    except:
        pass
    return None

def filter_title (entry):
    if entry.idata == 'liked':
        return _('Liked %s') % ('<em>' + title (entry.title) + '</em>')
    else:
        return _('Published %s') % ('<em>' + title (entry.title) + '</em>')
