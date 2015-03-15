#  gLifestream Copyright (C) 2010 Wojciech Polak
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

from django.conf import settings
from django.utils.html import strip_tags, strip_entities
from django.template.defaultfilters import urlizetrunc
from glifestream.filters import expand, truncate
from glifestream.utils.time import from_rfc3339, mtime, now
from glifestream.stream.models import Entry
from glifestream.stream import media

try:
    import facebook
    if not hasattr(facebook, 'GraphAPI'):
        facebook = None
except ImportError:
    facebook = None


class API:
    name = 'Facebook API'
    limit_sec = 600

    def __init__(self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    def get_urls(self):
        return ()

    def run(self):
        if not facebook:
            print("ImportError: facebook. Install Facebook's python-sdk.")
            return

        try:
            args = {}
            if not self.service.last_checked:
                args['limit'] = 250

            graph = facebook.GraphAPI(self.service.creds)
            if not self.service.url:
                self.stream = graph.get_connections('me', 'home', **args)
            else:
                self.stream = graph.get_connections(self.service.url, 'feed',
                                                    **args)
            self.service.last_checked = now()
            self.service.save()
            self.process()
        except Exception as e:
            if self.verbose:
                import sys
                import traceback
                print('%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e))
                traceback.print_exc(file=sys.stdout)

    def process(self):
        for ent in self.stream['data']:
            guid = 'tag:facebook.com,2004:post/%s' % ent['id']
            if self.verbose:
                print("ID: %s" % guid)

            if 'updated_time' in ent:
                t = from_rfc3339(ent['updated_time'])
            else:
                t = from_rfc3339(ent['created_time'])

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
            e.link = ent['actions'][0]['link']

            if 'from' in ent:
                frm = ent['from']
                image_url = 'http://graph.facebook.com/%s/picture' % frm['id']
                e.link_image = media.save_image(image_url, direct_image=False)
                e.author_name = frm['name']

            e.date_published = from_rfc3339(ent['created_time'])
            e.date_updated = t

            content = ''
            if 'message' in ent:
                content = expand.shorts(ent['message'])
                content = '<p>' + urlizetrunc(content, 45) + '</p>'

            name = ''
            if 'name' in ent:
                name = ent['name']
                content += ' <p>' + ent['name'] + '</p>'

            if 'picture' in ent and 'link' in ent:
                content += '<p class="thumbnails">'
                content += '<a href="%s" rel="nofollow">' \
                    '<img src="%s" alt="thumbnail" /></a> ' \
                    % (ent['link'], media.save_image(ent['picture'],
                                                     downscale=True))

                if 'description' in ent:
                    content += '<div class="fb-description">%s</div>' % \
                        ent['description']
                elif 'caption' in ent and name != ent['caption']:
                    content += '<div class="fb-caption">%s</div>' % \
                        ent['caption']

                content += '</p>'
            else:
                if 'description' in ent:
                    content += '<div class="fb-description">%s</div>' % \
                        ent['description']
                elif 'caption' in ent and name != ent['caption']:
                    content += '<div class="fb-caption">%s</div>' % \
                        ent['caption']

            e.content = content
            if 'message' in ent:
                e.title = truncate.smart(strip_tags(ent['message']),
                                         max_length=48)
            if e.title == '':
                e.title = strip_entities(strip_tags(content))[0:128]

            try:
                e.save()
                media.extract_and_register(e)
            except:
                pass
