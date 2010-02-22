#  gLifestream Copyright (C) 2010 Wojciech Polak
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

from django.utils.html import strip_entities, strip_tags
from glifestream.filters import expand, truncate
import webfeed

class API (webfeed.API):
    name = 'Google Buzz API'
    limit_sec = 180

    def run (self):
        self.fetch ('http://buzz.googleapis.com/feeds/%s/public/posted' % \
                    self.service.url)

    def custom_process (self, e, ent):
        e.title = truncate.smart_truncate (strip_tags (strip_entities (e.content)))
        e.content = expand.all (e.content)
