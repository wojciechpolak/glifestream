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

# 1. Give your application access to your account:
#    http://www.facebook.com/connect/prompt_permissions.php?v=1.0&ext_perm=offline_access,read_stream&api_key=FACEBOOK_API_KEY
# 2. Generate a one-time auth token:
#    http://www.facebook.com/code_gen.php?v=1.0&api_key=FACEBOOK_API_KEY
# 3. Get an infinite session key:
#    ./worker.py --fb-get-inf-session-key AUTH_TOKEN
# 4. Save the session key and use it as the Facebook's service
#    credentials.

import time
import datetime
from django.conf import settings
from django.utils.html import strip_tags, strip_entities
from django.template.defaultfilters import urlizetrunc
from glifestream.filters import expand
from glifestream.utils.time import mtime, now
from glifestream.stream.models import Entry
from glifestream.stream import media

try:
    import facebook
except ImportError:
    facebook = None

def get_inf_session_key (auth_token):
    if not facebook:
        print 'ImportError: facebook. Install pyfacebook.'
        return 1
    fb = facebook.Facebook (settings.FACEBOOK_API_KEY,
                            settings.FACEBOOK_SECRET_KEY,
                            auth_token)
    session = fb.auth.getSession ()
    if session:
        print 'session_key: %s' % session['session_key']
        print 'uid: %s' % session['uid']
        print 'expires: %s' % session['expires']
    return 0

class API:
    name = 'Facebook API'
    limit_sec = 600

    def __init__ (self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print '%s: %s' % (self.name, self.service)

    def run (self):
        if not facebook:
            print 'ImportError: facebook. Install pyfacebook.'
            return

        self.fb = facebook.Facebook (settings.FACEBOOK_API_KEY,
                                     settings.FACEBOOK_SECRET_KEY)
        self.fb.session_key = self.service.creds
        if self.service.url == 'home':
            self.fb.uid = settings.FACEBOOK_USER_ID
        else:
            self.fb.uid = self.service.url
        self.get_stream ()

    def get_stream (self):
        try:
            args = {}
            if not self.service.last_checked:
                if self.service.url == 'home':
                    days = 14
                else:
                    days = 180
                    args['limit'] = 250
                start_time = now () - datetime.timedelta (days=days)
                start_time = int (time.mktime (start_time.timetuple ()))
                args['start_time'] = start_time
            if self.service.url != 'home':
                args['source_ids'] = [int(self.service.url)]

            self.stream = self.fb.stream.get (**args)
            self.service.last_checked = now ()
            self.service.save ()
            self.process ()
        except Exception, e:
            if self.verbose:
                import sys, traceback
                print '%s (%d) Exception: %s' % (self.service.api,
                                                 self.service.id, e)
                traceback.print_exc (file=sys.stdout)

    def process (self):
        for ent in self.stream['posts']:
            guid = 'tag:facebook.com,2004:post/%s' % ent['post_id']
            if self.verbose:
                print "ID: %s" % guid

            if 'updated_time' in ent:
                t = datetime.datetime.utcfromtimestamp (ent['updated_time'])
            else:
                t = datetime.datetime.utcfromtimestamp (ent['created_time'])

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
            e.link  = ent['permalink']

            profile = None
            for p in self.stream['profiles']:
                if p['id'] == ent['actor_id']:
                    profile = p
                    break
            if profile:
                e.link_image = media.save_image (profile['pic_square'])
                e.author_name = profile['name']
                e.author_url = profile['url']

            e.date_published = datetime.datetime.utcfromtimestamp (ent['created_time'])
            e.date_updated = t

            content = ent['message']
            content = expand.shorts (content)
            content = urlizetrunc (content, 45)

            if 'attachment' in ent and 'media' in ent['attachment']:
                if 'name' in ent['attachment']:
                    content += ' <p>' + ent['attachment']['name'] + '</p>'
                content += '<p class="thumbnails">'
                for t in ent['attachment']['media']:
                    if self.service.public:
                        t['src'] = media.save_image (t['src'])
                    if t.has_key ('width') and t.has_key ('height'):
                        iwh = ' width="%d" height="%d"' % (t['width'],
                                                           t['height'])
                    else:
                        iwh = ''
                    if 'video' in t and 'display_url' in t['video']:
                        href = t['video']['display_url']
                    else:
                        href = t['href']
                    content += '<a href="%s" rel="nofollow"><img src="%s"%s alt="thumbnail" /></a> ' % (href, t['src'], iwh)
                if ent['message'] == '' and 'description' in ent['attachment']:
                    content += ent['attachment']['description']
                content += '</p>'

            e.content = content
            e.title = ent['message']
            if e.title == '':
                e.title = strip_entities (strip_tags (content))[0:128]

            try:
                e.save ()
                media.extract_and_register (e)
            except:
                pass
