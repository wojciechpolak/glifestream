#  gLifestream Copyright (C) 2009, 2011, 2015 Wojciech Polak
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

import calendar
import datetime
import json
import time
import math
import re
from django.template.defaultfilters import urlencode, stringfilter
from django.template.defaultfilters import date as ddate
from django.utils.translation import ungettext
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.utils.encoding import force_text
from django import template
from glifestream.stream import media
from glifestream.utils.slugify import slugify
from glifestream.utils.html import urlize as _urlize
from glifestream.apis import *  # pylint: disable=wildcard-import,unused-wildcard-import

register = template.Library()


@register.filter
def gls_date(date):
    ts = calendar.timegm(date.utctimetuple())
    if (time.time() - ts) > (7 * 86400):
        return ddate(datetime.datetime.fromtimestamp(ts), 'D, d-m-Y')
    return get_relative_time(date)


@register.filter
def gls_udate(date):
    return int(time.mktime(date.timetuple()))


@register.filter
def gls_hdate(date):
    ts = time.mktime(date.timetuple())
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ')


@register.filter
def gls_media(s):
    return media.set_upload_url(media.set_thumbs_url(s))


@register.filter
def gls_link(_, entry):
    if not entry.service.public:
        if entry.author_name:
            return '?class=%s&author=%s' % (entry.service.cls,
                                            urlencode(entry.author_name))
    else:
        return '?class=%s' % entry.service.cls
    return entry.service.link


@register.filter
def gls_title(_, entry):
    title = entry.title
    try:
        mod = eval(entry.service.api)
        if hasattr(mod, 'filter_title'):
            title = mod.filter_title(entry)
    except Exception:
        pass
    if entry.friends_only:
        title = ''
    if title == '':
        title = str(entry.date_published)[0:16]
    return mark_safe(title)


@register.filter
def gls_content(_, entry):
    if entry.friends_only:
        return mark_safe('<div class="friends-only-entry">' \
                         'The content of this entry is available only to my friends.</div>');
        # return mark_safe('<div class="friends-only-entry"><p>' +
        #                  _('The content of this entry is available only to my friends.') +
        #                  '</p></div>')
    try:
        mod = eval(entry.service.api)
        if hasattr(mod, 'filter_content'):
            s = mod.filter_content(entry)
            if entry.geolat and entry.geolng:
                s += '<div class="geo"><a href="#" class="show-map"><span class="latitude">%.10f</span> ' \
                     '<span class="longitude">%.10f</span>%s</a></div>' % (
                     entry.geolat, entry.geolng, ('show map'))
            return mark_safe(gls_media(s))
    except Exception as exc:
        print(exc)
    return mark_safe(gls_media(force_text(entry.content)))


@register.filter
def gls_mediarss(_, entry):
    if entry.friends_only:
        return ''
    return mark_safe(media.mrss_gen_xml(entry))


@register.filter
def gls_reply_url(_, entry):
    if entry.service.api == 'twitter':
        u = entry.link.split('/')
        return 'https://twitter.com/?status=@%s%%20&in_reply_to_status_id=%s&in_reply_to=%s' % (u[3], u[5], u[3])
    return '#'


@register.filter
def gls_slugify(value):
    s = slugify(value)
    if len(s) and s[-1] == '-':
        s = s[0:-1]
    a = s.split('-')
    if len(a) > 1 and a[-1].startswith('http'):
        a.pop()
        s = '-'.join(a)
    return s


@register.filter
def get_relative_time(t):
    t = time.mktime(t.utctimetuple())
    diff_seconds = (t - time.mktime(time.gmtime())) + 20
    diff_minutes = math.fabs(int(math.floor(diff_seconds / 60)))

    if diff_minutes > (60 * 24):
        rel = int(math.floor(diff_minutes / (60 * 24)))
        if rel == 1:
            rel = _('Yesterday')
        else:
            rel = _('%d days ago') % rel
    elif diff_minutes > 60:
        rel = int(math.floor(diff_minutes / 60))
        rel = ungettext('%(count)d hour ago', '%(count)d hours ago', rel) % \
            {'count': rel, }
    else:
        rel = int(diff_minutes)
        rel = ungettext('%(count)d minute ago', '%(count)d minutes ago', rel) % \
            {'count': rel, }
    return rel


@register.filter
def encode_json(content):
    enc = json.JSONEncoder()
    return mark_safe(enc.encode(content))


unencoded_ampersands_re = re.compile(r'&(?!([a-z]+|#\d+);)')


def fix_ampersands(value):
    return unencoded_ampersands_re.sub('&amp;', force_text(value))


@register.filter('gls_fix_ampersands', is_safe=True)
@stringfilter
def fix_ampersands_filter(value):
    """Replaces ampersands with ``&amp;`` entities."""
    return fix_ampersands(value)


@register.filter('gls_urlizetrunc', is_safe=True, needs_autoescape=True)
@stringfilter
def gls_urlizetrunc(value, limit, autoescape=None):
    """
    Converts URLs into clickable links, truncating URLs to the given character
    limit, and adding 'rel=nofollow' attribute to discourage spamming.

    Argument: Length to truncate URLs to.
    """
    return mark_safe(_urlize(value, trim_url_limit=int(limit), nofollow=True,
                             autoescape=autoescape))
