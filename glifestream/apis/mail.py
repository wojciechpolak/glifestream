#  gLifestream Copyright (C) 2010, 2015 Wojciech Polak
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

import os
import re
import email
from email.header import decode_header, make_header
from django.conf import settings
from django.core.files.uploadedfile import TemporaryUploadedFile
from django.utils.datastructures import MultiValueDict
from django.utils import six
from glifestream.apis import selfposts
from glifestream.stream.models import Service


class API:
    name = 'Email API'

    def __init__(self):
        pass

    def get_urls(self):
        return ()

    def run(self):
        pass

    def share(self, msgfile):
        msg = email.message_from_file(msgfile)
        args = {}
        files = []

        check = getattr(settings, 'EMAIL2POST_CHECK', {})
        for lhs in check:
            v = six.text_type(make_header(decode_header(msg.get(lhs, ''))))
            if not check[lhs] in v:
                return 77  # EX_NOPERM

        if msg.is_multipart():
            for part in msg.walk():
                attach = False
                t = part.get_content_type()

                if t == 'text/plain':
                    if part.get_filename(None):
                        attach = True
                    else:
                        args['content'] = part.get_payload(decode=True)

                if attach or \
                   t.startswith ('image/') or \
                   t.startswith ('audio/') or \
                   t.startswith ('video/') or \
                   t.startswith('application/'):
                    payload = part.get_payload(decode=True)
                    os.umask(0)
                    tmp = TemporaryUploadedFile(
                        name=part.get_filename('attachment'),
                        content_type=t,
                        size=len(payload),
                        charset=None)
                    tmp.write(payload)
                    tmp.seek(0)
                    os.chmod(tmp.file.name, 0o644)
                    files.append(tmp)
        else:
            args['content'] = msg.get_payload(decode=True)

        subject = msg.get('Subject', None)
        if subject:
            hdr = make_header(decode_header(subject))
            args['title'] = six.text_type(hdr)

        # Mail subject may contain @foo, a selfposts' class name for which
        # this message is post to.
        m = re.search(r'(\A|\s)@(\w[\w\-]+)', args['title'])
        if m:
            cls = m.groups()[1]
            args['title'] = re.sub(r'(\A|\s)@(\w[\w\-]+)', '', args['title'])
            s = Service.objects.filter(cls=cls, api='selfposts').values('id')
            if len(s):
                args['id'] = s[0]['id']

        # Mail subject may contain "!draft" literal.
        if '!draft' in args['title']:
            args['title'] = args['title'].replace('!draft', '').strip()
            args['draft'] = True

        # Mail subject may contain "!friends-only" literal.
        if '!friends-only' in args['title']:
            args['title'] = args['title'].replace(
                '!friends-only', '').strip()
            args['friends_only'] = True

        if len(files):
            args['files'] = MultiValueDict()
            args['files'].setlist('docs', files)

        selfposts.API(None).share(args)
        return 0  # EX_OK
