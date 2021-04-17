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
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from django.utils.html import escape
from django.utils.encoding import force_str, force_text
from django.utils.safestring import mark_safe, SafeData

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
    except Exception:
        pass
    return s


def bytes_to_human(num_bytes, precision=2):
    suffixes = ('B', 'kB', 'MB', 'GB')
    str_format = '%.*f %s'
    size = float(num_bytes)
    for suffix in suffixes:
        if size >= 1024:
            size /= 1024
        else:
            if suffix is suffixes[0]:
                precision = 0
            return str_format % (precision, size, suffix)
    return str_format % (precision, size, suffixes[-1])


def strip_entities(value):
    """Returns the given HTML with all entities (&something;) stripped."""
    return re.sub(r'&(?:\w+|#\d+);', '', force_text(value))

#
# Code taken from Django 1.7
#


TRAILING_PUNCTUATION = ['.', ',', ':', ';', '.)', '"', '\'']
WRAPPING_PUNCTUATION = [('(', ')'), ('<', '>'), ('[', ']'),
                        ('&lt;', '&gt;'), ('"', '"'), ('\'', '\'')]
word_split_re = re.compile(r'(\s+)')
simple_url_re = re.compile(r'^https?://\[?\w', re.IGNORECASE)
simple_url_2_re = re.compile(
    r'^www\.|^(?!http)\w[^@]+\.(com|edu|gov|int|mil|net|org)$', re.IGNORECASE)
simple_email_re = re.compile(r'^\S+@\S+\.\S+$')


def smart_urlquote(url):
    """Quotes a URL if it isn't already quoted."""
    # Handle IDN before quoting.
    try:
        scheme, netloc, path, query, fragment = urlsplit(url)
        try:
            netloc = netloc.encode('idna').decode('ascii')  # IDN -> ACE
        except UnicodeError:  # invalid domain part
            pass
        else:
            url = urlunsplit((scheme, netloc, path, query, fragment))
    except ValueError:
        # invalid IPv6 URL (normally square brackets in hostname part).
        pass

    url = unquote(force_str(url))
    url = quote(url, safe=b'!*\'();:@&=+$,/?#[]~')

    return force_text(url)


def urlize(text, trim_url_limit=None, nofollow=False, autoescape=False):
    """
    Converts any URLs in text into clickable links.

    Works on http://, https://, www. links, and also on links ending in one of
    the original seven gTLDs (.com, .edu, .gov, .int, .mil, .net, and .org).
    Links can have trailing punctuation (periods, commas, close-parens) and
    leading punctuation (opening parens) and it'll still do the right thing.

    If trim_url_limit is not None, the URLs in the link text longer than this
    limit will be truncated to trim_url_limit-3 characters and appended with
    an ellipsis.

    If nofollow is True, the links will get a rel="nofollow" attribute.

    If autoescape is True, the link text and URLs will be autoescaped.
    """
    def trim_url(x, limit=trim_url_limit):
        if limit is None or len(x) <= limit:
            return x
        return '%s...' % x[:max(0, limit - 3)]
    safe_input = isinstance(text, SafeData)
    words = word_split_re.split(force_text(text))
    for i, word in enumerate(words):
        if '.' in word or '@' in word or ':' in word:
            # Deal with punctuation.
            lead, middle, trail = '', word, ''
            for punctuation in TRAILING_PUNCTUATION:
                if middle.endswith(punctuation):
                    middle = middle[:-len(punctuation)]
                    trail = punctuation + trail
            for opening, closing in WRAPPING_PUNCTUATION:
                if middle.startswith(opening):
                    middle = middle[len(opening):]
                    lead = lead + opening
                # Keep parentheses at the end only if they're balanced.
                if (middle.endswith(closing)
                        and middle.count(closing) == middle.count(opening) + 1):
                    middle = middle[:-len(closing)]
                    trail = closing + trail

            # Make URL we want to point to.
            url = None
            nofollow_attr = ' rel="nofollow"' if nofollow else ''
            if simple_url_re.match(middle):
                url = smart_urlquote(middle)
            elif simple_url_2_re.match(middle):
                url = smart_urlquote('http://%s' % middle)
            elif ':' not in middle and simple_email_re.match(middle):
                local, domain = middle.rsplit('@', 1)
                try:
                    domain = domain.encode('idna').decode('ascii')
                except UnicodeError:
                    continue
                url = 'mailto:%s@%s' % (local, domain)
                nofollow_attr = ''

            # Make link.
            if url:
                trimmed = trim_url(middle)
                if autoescape and not safe_input:
                    lead, trail = escape(lead), escape(trail)
                    url, trimmed = escape(url), escape(trimmed)
                middle = '<a href="%s"%s>%s</a>' % (url,
                                                    nofollow_attr, trimmed)
                words[i] = mark_safe('%s%s%s' % (lead, middle, trail))
            else:
                if safe_input:
                    words[i] = mark_safe(word)
                elif autoescape:
                    words[i] = escape(word)
        elif safe_input:
            words[i] = mark_safe(word)
        elif autoescape:
            words[i] = escape(word)
    return ''.join(words)
