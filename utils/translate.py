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

from django.conf import settings
from glifestream.utils import httpclient

try:
    import json
except ImportError:
    import simplejson as json

def translate (msg, src='', target='en'):
    target = target.split ('-')[0]
    params = {
        'v': '1.0',
        'q': msg.encode ('utf_8'),
        'langpair': src +'|'+ target,
    }
    headers = {
        'Referer': settings.BASE_URL,
    }

    try:
        r = httpclient.urlopen ('ajax.googleapis.com/ajax/services/language/translate',
                                params, headers, timeout=30)
        if r.code == 200:
            data = json.loads (r.read ())
            if data['responseStatus'] == 200:
                return data['responseData']['translatedText']
            else:
                return data['responseDetails']
    except Exception:
        pass
    return ''
