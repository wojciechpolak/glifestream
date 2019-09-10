#  gLifestream Copyright (C) 2009, 2010, 2015 Wojciech Polak
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
from django.utils import six
from django.utils.encoding import force_text
from django.utils.functional import allow_lazy

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


def strip_script(s):
    try:
        if BeautifulSoup:
            soup = BeautifulSoup(s)
            to_extract = soup.findAll('script')
            for item in to_extract:
                item.extract()
            s = str(soup)
    except:
        pass
    return s


def bytes_to_human(bytes, precision=2):
    suffixes = ('B', 'kB', 'MB', 'GB')
    format = '%.*f %s'
    size = float(bytes)
    for suffix in suffixes:
        if size >= 1024:
            size /= 1024
        else:
            if suffix is suffixes[0]:
                precision = 0
            return format % (precision, size, suffix)
    return format % (precision, size, suffixes[-1])


def strip_entities(value):
    """Returns the given HTML with all entities (&something;) stripped."""
    return re.sub(r'&(?:\w+|#\d+);', '', force_text(value))


strip_entities = allow_lazy(strip_entities, six.text_type)
