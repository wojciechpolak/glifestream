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
from typing import Any

from django.conf import settings
from django.db import transaction
from django.core.files.uploadedfile import UploadedFile
from django.template.defaultfilters import urlizetrunc, title as df_title
from django.utils.html import strip_tags
from django.utils.datastructures import MultiValueDict

from glifestream.apis.base import BaseService
from glifestream.utils.time import utcnow
from glifestream.utils.html import strip_script, bytes_to_human
from glifestream.stream.models import Service, Entry, Media
from glifestream.stream import media
from glifestream.filters import expand, truncate

try:
    import markdown
except ImportError:
    markdown = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _parse_form_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'on', 'yes'}
    return bool(value)


# Extension tables for uploaded files. Anything unlisted keeps the fallbacks
# below: pictures get no media type, other files are plain documents.
_UPLOAD_IMAGE_TYPES: dict[str, str] = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
    '.heif': 'image/heif',
}

_UPLOAD_MEDIA_TYPES: dict[str, tuple[str, str]] = {
    '.mp3': ('audio', 'audio/mpeg'),
    '.ogg': ('audio', 'audio/ogg'),
    '.mp4': ('video', 'video/mp4'),
    '.webm': ('video', 'video/webm'),
    '.avi': ('video', 'video/avi'),
    '.pdf': ('document', 'application/pdf'),
}


def _lookup_by_extension(name: str, table: dict[str, Any]) -> Any:
    lowered = name.lower()
    for extension, value in table.items():
        if lowered.endswith(extension):
            return value
    return None


def _render_body(content: str, editor_syntax: str) -> str:
    """Turn the editor's raw input into the entry's HTML."""
    if editor_syntax == 'markdown' and markdown:
        return expand.run_all(markdown.markdown(content))
    return urlizetrunc(expand.run_all(content.replace('\n', '<br/>')), 45)


def _render_remote_thumbs(images: list[str], link: str) -> str:
    """Thumbnails for images shared by URL rather than uploaded."""
    thumbs = '\n<p class="thumbnails">\n'
    for img in images:
        saved = media.save_image(img, force=True, downscale=True)
        thumbs += (
            """  <a href="%s" rel="nofollow"><img src="%s" alt="thumbnail" /></a>\n"""
            % (link, saved)
        )
    return thumbs + '</p>\n'


def _store_uploads(
    entry: Entry, files: MultiValueDict
) -> tuple[list[tuple[Media, UploadedFile]], list[tuple[Media, UploadedFile]]]:
    """Save every uploaded file, split into pictures and everything else."""
    pictures: list[tuple[Media, UploadedFile]] = []
    docs: list[tuple[Media, UploadedFile]] = []
    for f in files.getlist('docs'):
        md = Media(entry=entry)
        md.file.save(f.name, f)
        md.save()
        if f.content_type.startswith('image/'):
            pictures.append((md, f))
        else:
            docs.append((md, f))
    return pictures, docs


def _render_uploaded_pictures(
    pictures: list[tuple[Media, UploadedFile]], mblob: dict[str, Any]
) -> str:
    thumbs = '\n<p class="thumbnails">\n'
    for md, upload in pictures:
        thumb, orig = media.downsave_uploaded_image(md.file)
        thumbs += '  <a href="%s"><img src="%s" alt="thumbnail" /></a>\n' % (
            orig,
            thumb,
        )
        mrss: dict[str, Any] = {
            'url': orig,
            'medium': 'image',
            'fileSize': upload.size,
        }
        media_type = _lookup_by_extension(orig, _UPLOAD_IMAGE_TYPES)
        if media_type:
            mrss['type'] = media_type
        mblob['content'].append([mrss])
    return thumbs + '</p>\n'


def _render_uploaded_docs(
    docs: list[tuple[Media, UploadedFile]], mblob: dict[str, Any]
) -> str:
    doc = '\n<ul class="files">\n'
    for md, upload in docs:
        file_name = md.file.name
        if not file_name:
            continue
        target = '[GLS-UPLOAD]/%s' % file_name.replace('upload/', '')
        doc += '  <li><a href="%s">%s</a> ' % (target, upload.name)
        doc += '<span class="size">%s</span></li>\n' % bytes_to_human(upload.size)

        mrss: dict[str, Any] = {'url': target, 'fileSize': upload.size}
        medium, media_type = _lookup_by_extension(target, _UPLOAD_MEDIA_TYPES) or (
            'document',
            None,
        )
        mrss['medium'] = medium
        if media_type:
            mrss['type'] = media_type
        mblob['content'].append([mrss])
    return doc + '</ul>\n'


class SelfpostsService(BaseService):
    name = 'Selfposts API'

    def __init__(
        self, service: Service, verbose: int = 0, force_overwrite: bool = False
    ):
        super().__init__(service, verbose, force_overwrite)

    def get_urls(self) -> list[str]:
        return []

    def run(self):
        pass

    def share(self, args: dict[str, Any] | None = None) -> Entry | None:
        if args is None:
            args = {}
        content = args.get('content', '')
        sid = args.get('sid', None)
        title = args.get('title', None)
        link = args.get('link', None)
        images = args.get('images', None)
        files = args.get('files', MultiValueDict())
        user = args.get('user', None)

        un = utcnow()
        guid = '%s/entry/%s' % (settings.FEED_TAGURI, un.strftime('%Y-%m-%dT%H:%M:%SZ'))
        if sid:
            s = Service.objects.get(id=sid, api='selfposts')
        else:
            s = Service.objects.filter(api='selfposts').order_by('id')[0]
        e = Entry(service=s, guid=guid)

        e.link = link if link else settings.BASE_URL + '/'
        e.date_published = un
        e.date_updated = un
        e.draft = _parse_form_bool(args.get('draft', False))
        e.friends_only = _parse_form_bool(args.get('friends_only', False))

        if user and user.first_name and user.last_name:
            e.author_name = user.first_name + ' ' + user.last_name

        # html, markdown
        e.content = _render_body(
            content, getattr(settings, 'EDITOR_SYNTAX', 'markdown')
        )
        e.content = strip_script(e.content)
        e.content = expand.imgloc(e.content)

        if images:
            e.content += _render_remote_thumbs(images, e.link)

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

            pictures, docs = _store_uploads(e, files)
            if pictures:
                e.content += _render_uploaded_pictures(pictures, mblob)
            if docs:
                e.content += _render_uploaded_docs(docs, mblob)

            e.mblob = media.mrss_gen_json(mblob)
            if pictures or docs:
                e.save()

            media.extract_and_register(e)
            return e
        except Exception as exc:
            logger.error(exc)
        return None

    def reshare(self, entry, args=None):
        if args is None:
            args = {}
        sid = args.get('sid', None)
        as_me = _parse_form_bool(args.get('as_me', False))
        user = args.get('user', None)

        un = utcnow()
        guid = '%s/entry/%s' % (settings.FEED_TAGURI, un.strftime('%Y-%m-%dT%H:%M:%SZ'))
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
            e.content = '<a href="%s" rel="nofollow">%s</a>' % (e.link, e.title)
        elif entry.service.api in ('youtube', 'vimeo'):
            e.content = '<p>%s</p>%s' % (df_title(e.title), entry.content)
        else:
            e.content = urlizetrunc(entry.content, 45)

        try:
            media.transform_to_local(e)
            # Media rows reference the entry, so save it first.
            with transaction.atomic():
                e.save()
                media.extract_and_register(e)
            return e
        except Exception as exc:
            logger.error(exc)


def filter_title(entry):
    return entry.title


def filter_content(entry):
    return entry.content
