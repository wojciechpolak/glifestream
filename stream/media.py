#  gLifestream Copyright (C) 2009 Wojciech Polak
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

import re
from django.conf import settings
from glifestream.stream.models import Media
from glifestream.filters.expand import save_image

def extract_and_register (entry):
    for hash in re.findall ('<img src="thumbs/([a-z0-9]{40})"', entry.content):
        md = Media (entry=entry, type='image')
        md.file.name = 'thumbs/%s' % hash
        try:
            md.save ()
        except:
            pass

def __img_subs (m):
    newurl = save_image (m.group (1), force=True)
    return '<img src="%s"' % newurl

def transform_to_local (entry):
    entry.content = re.sub (r'<img src="(http://.*?)"', __img_subs,
                            entry.content)
