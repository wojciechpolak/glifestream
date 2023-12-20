#!/usr/bin/env python

"""
#  gLifestream Copyright (C) 2023 Wojciech Polak
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

import re
import os
import sys
import magic  # requires external libmagic
import django
from django.conf import settings

SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'glifestream.settings'

if hasattr(django, 'setup'):
    django.setup()

# pylint: disable=wrong-import-position
from glifestream.stream import media
from glifestream.stream.models import Entry, Media

dry_run = False


def get_file_suffix(filename):
    try:
        mimeinfo = magic.from_file(filename, mime=True)
        suffix = ''
        if mimeinfo == 'image/jpeg':
            suffix = '.jpg'
        elif mimeinfo == 'image/png':
            suffix = '.png'
        elif mimeinfo == 'image/gif':
            suffix = '.gif'
        elif mimeinfo == 'image/webp':
            suffix = '.webp'
        elif mimeinfo == 'image/avif':
            suffix = '.avif'
        else:
            print('Unrecognized mime type', mimeinfo)
        return suffix
    except Exception as exc:
        print('EXCEPTION', exc)
        return None


def file_lookup(filename):
    if os.path.exists(filename + '.jpg'):
        return filename + '.jpg'
    elif os.path.exists(filename + '.png'):
        return filename + '.png'
    elif os.path.exists(filename + '.gif'):
        return filename + '.gif'
    elif os.path.exists(filename + '.webp'):
        return filename + '.webp'
    return filename


def thumb_replace(tmatch, suffix):
    return f"[GLS-THUMBS]/{tmatch}{suffix}"


#
# ALTER FILES
#

ths = {}
for root, dirs, files in os.walk(os.path.join(settings.MEDIA_ROOT, 'thumbs')):
    for filename in files:
        if filename[0] != '.':
            t = media.get_thumb_info(filename, append_suffix=False)['rel']
            ths[t] = True

for filename in ths:
    if '.' not in filename:
        filename = os.path.join(settings.MEDIA_ROOT, filename)
        suffix = get_file_suffix(filename)
        if suffix and not dry_run:
            os.rename(filename, filename + suffix)

#
# ALTER DB
#

medias = Media.objects.all()

for md in medias:
    if '.' not in md.file.name:
        print('Fixing media', md.file.name)
        filename = os.path.join(settings.MEDIA_ROOT, md.file.name)
        suffix = get_file_suffix(file_lookup(filename))
        if suffix is None:
            md.delete()
        elif suffix:
            md.file.name = md.file.name + suffix
            try:
                md.save()
            except Exception as exc:
                print('EXCEPTION', exc)
        else:
            print(f'No media suffix for ID {md.id} (entry ID {md.entry.id})', md.file.name)


entries = Entry.objects.all()

for entry in entries:
    thumb_hash = media.get_thumb_hash(entry.link_image)
    t = media.get_thumb_info(thumb_hash, append_suffix=False)['rel'] if thumb_hash else ''
    if t and '.' not in thumb_hash:
        filename = os.path.join(settings.MEDIA_ROOT, t)
        suffix = get_file_suffix(file_lookup(filename))
        if suffix:
            try:
                print('Fixing link_image', entry.link_image)
                entry.link_image = entry.link_image + suffix
                entry.save()
            except Exception as exc:
                print('EXCEPTION', exc)

    matches = re.findall(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', entry.content)
    modified_content = entry.content
    for thumb_hash in matches:
        t = media.get_thumb_info(thumb_hash, append_suffix=False)['rel']
        if t and '.' not in thumb_hash:
            print(f'Fixing thumbnail {thumb_hash} (entry ID {entry.id})')
            filename = os.path.join(settings.MEDIA_ROOT, t)
            suffix = get_file_suffix(file_lookup(filename))
            if suffix:
                modified_content = re.sub(fr'\[GLS-THUMBS\]/{re.escape(thumb_hash)}',
                                          thumb_replace(thumb_hash, suffix), modified_content)
    if modified_content != entry.content:
        print('Saving entry', entry.id)
        entry.content = modified_content
        try:
            entry.save()
        except Exception as exc:
            print('EXCEPTION', exc)

sys.exit(0)
