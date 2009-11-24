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

from django.conf import settings
from django.shortcuts import render_to_response
from glifestream.stream.models import Service

def js (request, **args):
    page = {
        'base_url': settings.BASE_URL,
    }
    return render_to_response ('bookmarklet.js', { 'page': page },
                               mimetype='application/javascript')

#from django.views.decorators.cache import cache_page
#@cache_page (0)
def frame (request, **args):
    page = {
        'base_url': settings.BASE_URL,
    }
    authed = request.user.is_authenticated ()
    if authed:
        srvs = Service.objects.filter (api='selfposts').order_by ('cls')
        srvs.query.group_by = ['cls']
        srvs = srvs.values ('id', 'cls')
    else:
        srvs = None

    return render_to_response ('frame.html',
                               { 'authed': authed,
                                 'page': page,
                                 'srvs': srvs })
