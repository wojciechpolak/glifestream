"""
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
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import sys
import traceback
from django.utils.translation import gettext as _
from glifestream.utils import httpclient
from glifestream.utils.time import mtime, now
from glifestream.stream.models import Entry, Service
from glifestream.stream import media


class API:
    name = 'Vimeo Simple API v2'
    limit_sec = 3600

    def __init__(self, service: Service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_urls(self) -> tuple[str]:
        if '/' in self.service.url:
            url = self.service.url.replace('channel/', 'channels/')
            url = url.replace('group/', 'groups/')
            return ('https://vimeo.com/%s/videos/rss' % url,)
        else:
            return ('https://vimeo.com/%s/likes/rss' % self.service.url,
                    'https://vimeo.com/%s/videos/rss' % self.service.url)

    def run(self) -> None:
        if not self.service.link:
            self.service.link = 'https://vimeo.com/%s' % self.service.url
        if '/' in self.service.url:
            self.process = self.process_videos
            self.fetch('/api/v2/%s/videos.json' % self.service.url)
        else:
            self.process = self.process_likes
            self.fetch('/api/v2/%s/likes.json' % self.service.url)
            self.process = self.process_videos
            self.fetch('/api/v2/%s/videos.json' % self.service.url)

    def fetch(self, url: str) -> None:
        try:
            r = httpclient.get('https://vimeo.com' + url)
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
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def process_likes(self) -> None:
        """Process what user did like."""
        for ent in self.json:
            date = ent['liked_on'][:10]
            guid = 'tag:vimeo,%s:clip%s' % (date, ent['id'])
            if self.verbose:
                print("ID: %s" % guid)
            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if not self.force_overwrite and e.date_updated \
                        and mtime(ent['liked_on']) <= e.date_updated:
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.title = ent['title']
            e.link = ent['url']
            e.date_published = ent['liked_on']
            e.date_updated = ent['liked_on']
            e.author_name = ent['user_name']

            e.idata = 'liked'

            if self.service.public:
                ent['thumbnail_large'] = media.save_image(
                    ent['thumbnail_large'], downscale=True, size=(320, 180))

            e.content = """<table class="vc"><tr><td><div id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="320" height="180" alt="%s" /></a><div class="playbutton"></div></div></td></tr></table>""" % (
                ent['id'], e.link, ent['thumbnail_large'], ent['title'])

            mblob = media.mrss_init()
            mblob[
                'content'].append([{'url': 'https://player.vimeo.com/video/%s' % ent['id'],
                                    'medium': 'video'}])
            e.mblob = media.mrss_gen_json(mblob)

            try:
                e.save()
            except Exception:
                pass

    def process_videos(self) -> None:
        """Process videos uploaded by user."""
        for ent in self.json:
            date = ent['upload_date'][:10]
            guid = 'tag:vimeo,%s:clip%s' % (date, ent['id'])
            if self.verbose:
                print("ID: %s" % guid)
            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if not self.force_overwrite and e.date_updated \
                   and mtime(ent['upload_date']) <= e.date_updated:
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.title = ent['title']
            e.link = ent['url']
            e.date_published = ent['upload_date']
            e.date_updated = ent['upload_date']
            e.author_name = ent['user_name']

            if self.service.public:
                ent['thumbnail_large'] = media.save_image(
                    ent['thumbnail_large'], downscale=True, size=(320, 180))

            e.content = """<table class="vc"><tr><td><div id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow"><img src="%s" width="320" height="180" alt="%s" /></a><div class="playbutton"></div></div></td></tr></table>""" % (
                ent['id'], e.link, ent['thumbnail_large'], ent['title'])

            mblob = media.mrss_init()
            mblob['content'].append([{'url': 'https://player.vimeo.com/video/%s' % ent['id'],
                                     'medium': 'video'}])
            e.mblob = media.mrss_gen_json(mblob)

            try:
                e.save()
                media.extract_and_register(e)
            except Exception:
                pass


def get_thumbnail_url(id_video: str) -> str | None:
    try:
        r = httpclient.get('https://vimeo.com/api/v2/video/%s.json' % id_video)
        if r.status_code == 200:
            jsn = r.json()
            if 'thumbnail_large' in jsn[0]:
                return jsn[0]['thumbnail_large']
            elif 'thumbnail_medium' in jsn[0]:
                return jsn[0]['thumbnail_medium']
    except Exception:
        pass
    return None


def filter_title(entry: Entry) -> str:
    if entry.idata == 'liked':
        return _('Liked %s') % ('<em>' + entry.title + '</em>')
    else:
        return _('Published %s') % ('<em>' + entry.title + '</em>')
