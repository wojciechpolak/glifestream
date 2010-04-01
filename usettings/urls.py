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

from django.conf.urls.defaults import *
from glifestream.usettings import views

urlpatterns = patterns ('',
    (r'^$', 'django.views.generic.simple.redirect_to',
     {'url': 'services'}, 'settings'),
    (r'api/(?P<cmd>[a-z\-]+)$', views.api),
    (r'services$', views.services),
    (r'lists$', views.lists),
    (r'lists/(?P<list>[a-z0-9\-]+)$', views.lists),
    (r'pshb$', views.pshb),
    (r'openid$', views.openid),
)
