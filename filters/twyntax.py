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
from django.template.defaultfilters import urlizetrunc

def parse (s, type='twitter'):
    if type == 'twitter':
        s = s.split (': ', 1)[1]
    s = hash_tag (s, type)
    s = at_reply (s, type)
    s = urlizetrunc (s, 45)
    return s

def at_reply (tweet, type='twitter'):
    pattern = re.compile (r"(\A|\W)@(?P<user>\w+)(\Z|\W)")
    if type == 'identica':
        repl = (r'\1@<a href="http://identi.ca/\g<user>"'
                r' title="\g<user> on Identi.ca" rel="nofollow">\g<user></a>\3')
    else:
        repl = (r'\1@<a href="http://twitter.com/\g<user>"'
                r' title="\g<user> on Twitter" rel="nofollow">\g<user></a>\3')
    return pattern.sub (repl, tweet)

def hash_tag (tweet, type='twitter'):
    if type == 'identica':
        return re.sub (r'(\A|\s)#(\w[\w\-]+)',
                       r'\1#<a href="http://identi.ca/tag/\2" title="#\2 search Identi.ca" rel="nofollow">\2</a>',
                       tweet)
    return re.sub (r'(\A|\s)#(\w[\w\-]+)',
                   r'\1#<a href="http://search.twitter.com/search?q=%23\2" title="#\2 search Twitter" rel="nofollow">\2</a>',
                   tweet)
