"""
#  gLifestream Copyright (C) 2009, 2010, 2023 Wojciech Polak
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

import logging

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.template.defaultfilters import urlizetrunc, title as df_title
from django.utils.html import strip_tags
from django.utils.datastructures import MultiValueDict
from glifestream.utils.time import utcnow
from glifestream.utils.html import strip_script, bytes_to_human
from glifestream.stream.models import Service, Entry, Media
from glifestream.stream import media
from glifestream.filters import expand, truncate

try:
    import markdown
except ImportError:
    markdown = None

logger = logging.getLogger(__name__)


class API:
    name = 'Selfposts API'

    def __init__(self, service, verbose=0, force_overwrite=False):
        self.service = service
        self.verbose = verbose

    def get_urls(self):
        return ()

    def run(self):
        pass

    def share(self, args=None):
        if args is None:
            args = {}
        content = args.get('content', '')
        sid = args.get('sid', None)
        title = args.get('title', None)
        link = args.get('link', None)
        images = args.get('images', None)
        files = args.get('files', MultiValueDict())
        source = args.get('source', '')
        user = args.get('user', None)

        un = utcnow()
        guid = '%s/entry/%s' % (settings.FEED_TAGURI,
                                un.strftime('%Y-%m-%dT%H:%M:%SZ'))
        if sid:
            s = Service.objects.get(id=sid, api='selfposts')
        else:
            s = Service.objects.filter(api='selfposts').order_by('id')[0]
        e = Entry(service=s, guid=guid)

        e.link = link if link else settings.BASE_URL + '/'
        e.date_published = un
        e.date_updated = un
        e.draft = int(args.get('draft', False))
        e.friends_only = int(args.get('friends_only', False))

        if user and user.first_name and user.last_name:
            e.author_name = user.first_name + ' ' + user.last_name

        # html, markdown
        editor_syntax = getattr(settings, 'EDITOR_SYNTAX', 'markdown')

        if editor_syntax == 'markdown' and markdown:
            e.content = expand.run_all(markdown.markdown(content))
        else:
            e.content = expand.run_all(content.replace('\n', '<br/>'))
            e.content = urlizetrunc(e.content, 45)

        e.content = strip_script(e.content)
        e.content = expand.imgloc(e.content)

        if images:
            thumbs = '\n<p class="thumbnails">\n'
            for img in images:
                img = media.save_image(img, force=True, downscale=True)
                thumbs += """  <a href="%s" rel="nofollow"><img src="%s" alt="thumbnail" /></a>\n""" % (
                    e.link, img)
            thumbs += '</p>\n'
            e.content += thumbs

        if title:
            e.title = title
        else:
            e.title = truncate.smart(strip_tags(e.content)).strip()
        if e.title == '':
            e.title = truncate.smart(strip_tags(content)).strip()

        mblob = media.mrss_scan(e.content)
        e.mblob = media.mrss_gen_json(mblob)

        try:
            e.save()

            pictures: list[tuple[Media, UploadedFile]] = []
            docs: list[tuple[Media, UploadedFile]] = []

            for f in files.getlist('docs'):
                md = Media(entry=e)
                md.file.save(f.name, f)
                md.save()
                if f.content_type.startswith('image/'):
                    pictures.append((md, f))
                else:
                    docs.append((md, f))

            if len(pictures) > 0:
                thumbs = '\n<p class="thumbnails">\n'
                for o in pictures:
                    thumb, orig = media.downsave_uploaded_image(o[0].file)
                    thumbs += '  <a href="%s"><img src="%s" alt="thumbnail" /></a>\n' % (
                        orig, thumb)
                    mrss = {
                        'url': orig,
                        'medium': 'image',
                        'fileSize': o[1].size
                    }
                    if orig.lower().endswith('.jpg') or orig.lower().endswith('.jpeg'):
                        mrss['type'] = 'image/jpeg'
                    elif orig.lower().endswith('.webp'):
                        mrss['type'] = 'image/webp'
                    mblob['content'].append([mrss])
                thumbs += '</p>\n'
                e.content += thumbs

            if len(docs) > 0:
                doc = '\n<ul class="files">\n'
                for o in docs:
                    target = '[GLS-UPLOAD]/%s' % o[
                        0].file.name.replace('upload/', '')
                    doc += '  <li><a href="%s">%s</a> ' % (target, o[1].name)
                    doc += '<span class="size">%s</span></li>\n' % \
                        bytes_to_human(o[1].size)

                    mrss = {'url': target, 'fileSize': o[1].size}
                    target = target.lower()
                    if target.endswith('.mp3'):
                        mrss['medium'] = 'audio'
                        mrss['type'] = 'audio/mpeg'
                    elif target.endswith('.ogg'):
                        mrss['medium'] = 'audio'
                        mrss['type'] = 'audio/ogg'
                    elif target.endswith('.mp4'):
                        mrss['medium'] = 'video'
                        mrss['type'] = 'video/mp4'
                    elif target.endswith('.webm'):
                        mrss['medium'] = 'video'
                        mrss['type'] = 'video/webm'
                    elif target.endswith('.avi'):
                        mrss['medium'] = 'video'
                        mrss['type'] = 'video/avi'
                    elif target.endswith('.pdf'):
                        mrss['medium'] = 'document'
                        mrss['type'] = 'application/pdf'
                    else:
                        mrss['medium'] = 'document'
                    mblob['content'].append([mrss])

                doc += '</ul>\n'
                e.content += doc

            e.mblob = media.mrss_gen_json(mblob)
            if len(pictures) > 0 or len(docs) > 0:
                e.save()

            media.extract_and_register(e)
            return e
        except Exception as exc:
            logger.error(exc)

    def reshare(self, entry, args=None):
        if args is None:
            args = {}
        sid = args.get('sid', None)
        as_me = int(args.get('as_me', False))
        user = args.get('user', None)

        un = utcnow()
        guid = '%s/entry/%s' % (settings.FEED_TAGURI,
                                un.strftime('%Y-%m-%dT%H:%M:%SZ'))
        if sid:
            s = Service.objects.get(id=sid, api='selfposts')
        else:
            s = Service.objects.filter(api='selfposts').order_by('id')[0]
        e = Entry(service=s, guid=guid)

        e.date_published = un
        e.date_updated = un

        if as_me:
            if user and user.first_name and user.last_name:
                e.author_name = user.first_name + ' ' + user.last_name
            else:
                e.author_name = ''
            e.author_email = ''
            e.author_uri = ''
            if entry.service.api == 'greader':
                e.link = entry.link
            else:
                e.link = settings.BASE_URL + '/'
            if entry.service.api == 'twitter':
                entry.content = entry.content.split(': ', 1)[1]
        else:
            e.author_name = entry.author_name
            e.author_email = entry.author_email
            e.author_uri = entry.author_uri
            e.link = entry.link

        e.geolat = entry.geolat
        e.geolng = entry.geolng
        e.mblob = entry.mblob

        e.title = entry.title
        if entry.service.api == 'greader':
            e.content = '<a href="%s" rel="nofollow">%s</a>' % (
                e.link, e.title)
        elif entry.service.api in ('youtube', 'vimeo'):
            e.content = '<p>%s</p>%s' % (df_title(e.title), entry.content)
        else:
            e.content = urlizetrunc(entry.content, 45)

        try:
            media.transform_to_local(e)
            media.extract_and_register(e)
            e.save()
            return e
        except Exception as exc:
            logger.error(exc)


def filter_title(entry):
    return entry.title


def filter_content(entry):
    return entry.content
