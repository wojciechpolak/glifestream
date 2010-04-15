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

import httplib
import urllib
import urllib2
from email.utils import parsedate
from django.conf import settings

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

try:
    import gzip
except ImportError:
    gzip = None
try:
    import zlib
except ImportError:
    zlib = None

AGENT = 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL

class URLopener (urllib.FancyURLopener):
    version = AGENT

class HTTPError (urllib2.HTTPError):
    pass

def head (host, url='/', timeout=15):
    con = httplib.HTTPConnection (host, timeout=timeout)
    con.request ('HEAD', url)
    return con.getresponse ()

def get (host, url='/', headers={}, etag=None, timeout=45):
    _headers = {'User-Agent': AGENT}
    if gzip and zlib:
        _headers['Accept-Encoding'] = 'gzip, deflate'
    elif gzip:
        _headers['Accept-Encoding'] = 'gzip'
    elif zlib:
        _headers['Accept-Encoding'] = 'deflate'
    if etag:
        _headers['If-None-Match'] = etag
    _headers.update (headers)

    con = httplib.HTTPConnection (host, timeout=timeout)
    con.request ('GET', url, headers=_headers)
    r = con.getresponse ()
    r.code = r.status
    r.data = __decompress (r.read (),
                           r.getheader ('content-encoding', ''))
    modified = r.getheader ('last-modified')
    r.modified = parsedate (modified) if modified else None
    r.etag = r.getheader ('etag')
    return r

def retrieve (url, filename):
    opener = URLopener ()
    return opener.retrieve (url, filename)[1]

def urlopen (url, data=None, headers={}, etag=None, timeout=45):
    _headers = {'User-Agent': AGENT}
    if gzip and zlib:
        _headers['Accept-Encoding'] = 'gzip, deflate'
    elif gzip:
        _headers['Accept-Encoding'] = 'gzip'
    elif zlib:
        _headers['Accept-Encoding'] = 'deflate'
    if etag:
        _headers['If-None-Match'] = etag
    _headers.update (headers)

    if not url.startswith ('http'):
        url = 'http://' + url
    if data:
        data = urllib.urlencode (data)

    req = urllib2.Request (url, data, _headers)
    try:
        f = urllib2.urlopen (req, timeout=timeout)
        f.status = f.code
        f.data = __decompress (f.read (),
                               f.headers.get ('content-encoding', ''))
        modified = f.headers.get ('last-modified')
        f.modified = parsedate (modified) if modified else None
        f.etag = f.headers.get ('etag')
        return f
    except urllib2.HTTPError, e:
        raise HTTPError (e.url, e.code, e.msg, e.hdrs, e.fp)

def __decompress (data, encoding):
    if gzip and encoding == 'gzip':
        try:
            return gzip.GzipFile (fileobj=StringIO (data)).read ()
        except:
            pass
    elif zlib and encoding == 'deflate':
        try:
            return zlib.decompress (data, -zlib.MAX_WBITS)
        except:
            pass
    return data
