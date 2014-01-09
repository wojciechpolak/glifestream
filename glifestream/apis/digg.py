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

import webfeed


class API (webfeed.API):
    name = 'Digg API'
    limit_sec = 300

    def get_urls(self):
        return ('http://digg.com/users/%s/history.rss' % self.service.url,)


def filter_title(entry):
    return '<a href="%s" rel="nofollow">%s</a>' % (entry.link, entry.title)
