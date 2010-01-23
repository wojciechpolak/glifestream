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

import os.path
import re
import urllib
import hashlib
import tempfile
import shutil
from django.conf import settings
from glifestream.stream.models import Media

try:
    import Image
except ImportError:
    Image = None

def set_upload_url (s):
    return s.replace ('[GLS-UPLOAD]/', settings.MEDIA_URL + '/upload/')

def set_thumbs_url (s):
    return re.sub (r'\[GLS-THUMBS\]/([a-f0-9])',
                   settings.MEDIA_URL + '/thumbs/\\1/\\1', s)

def get_thumb_hash (s):
    m = re.search (r'\[GLS-THUMBS\]/([a-f0-9]{40})', s)
    return m.groups ()[0] if m else None

def get_thumb_info (hash):
    prefix = hash[0] + '/'
    return { 'local': '%s/thumbs/%s%s' % (settings.MEDIA_ROOT, prefix, hash),
             'url': '%s/thumbs/%s%s' % (settings.MEDIA_URL, prefix, hash),
             'rel': 'thumbs/%s%s' % (prefix, hash),
             'internal': '[GLS-THUMBS]/%s' % hash, }

def save_image (url, force=False, downscale=False):
    if settings.BASE_URL in url:
        return url
    thumb = get_thumb_info (hashlib.sha1 (url).hexdigest ())
    if not os.path.isfile (thumb['local']):
        tmp = tempfile.mktemp ('_gls')
        try:
            image = urllib.FancyURLopener ()
            resp = image.retrieve (url, tmp)[1]
            if not force and not 'image/' in resp.getheader ('Content-Type',''):
                return url
            if downscale:
                downscale_image (tmp)
            shutil.move (tmp, thumb['local'])
        except:
            return url
    return thumb['internal']

def downscale_image (filename):
    if not Image:
        return
    size = 400, 175
    try:
        im = Image.open (filename)
        w, h = im.size
        if w > size[0] or h > size[1]:
            im.thumbnail (size, Image.ANTIALIAS)
            im.save (filename, 'JPEG', quality=95)
    except:
        pass

def downsave_uploaded_image (file):
    url = '[GLS-UPLOAD]/%s' % file.url.replace ('/upload/', '')
    try:
        thumb = get_thumb_info (hashlib.sha1 (file.name).hexdigest ())
        if not os.path.isfile (thumb['local']):
            shutil.copy (file.path, thumb['local'])
            downscale_image (thumb['local'])
        return (thumb['internal'], url)
    except:
        pass
    return (url, url)

def extract_and_register (entry):
    for hash in re.findall ('\[GLS-THUMBS\]/([a-f0-9]{40})', entry.content):
        md = Media (entry=entry)
        md.file.name = get_thumb_info (hash)['rel']
        try:
            md.save ()
        except:
            pass

def __img_subs (m):
    return '<img src="%s"' % save_image (m.group (1), force=True)

def transform_to_local (entry):
    entry.content = re.sub (r'<img src="(http://.*?)"', __img_subs,
                            entry.content)
