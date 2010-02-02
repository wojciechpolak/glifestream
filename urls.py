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
from django.conf.urls.defaults import *
from django.contrib import admin
admin.autodiscover ()

from glifestream.stream import views as sv

handler404 = 'glifestream.stream.views.page_not_found'

urlpatterns = patterns ('',

    url (r'^$', sv.index, name='index'),
    (r'^(?P<year>\d{4})/$', sv.index),
    (r'^(?P<year>\d{4})/(?P<month>\d{2})/$', sv.index),
    (r'^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
     sv.index),

    (r'^public/$', sv.index, {'public': True}, 'public'),
    (r'^public/(?P<year>\d{4})/$', sv.index, {'public': True}),
    (r'^public/(?P<year>\d{4})/(?P<month>\d{2})/$',
     sv.index, {'public': True}),
    (r'^public/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
     sv.index, {'public': True}),

    (r'^entry/(?P<entry>\d+)(/.*)?$', sv.index,
     {'public': True}, 'entry'),
    (r'^api/(?P<cmd>[a-z]+)$', sv.api),

    (r'^favorites/$', sv.index, {'favorites': True}, 'favorites'),
    (r'^list/(?P<list>[a-z\-]+)/$', sv.index, {}, 'list'),

    (r'^login/?$', 'glifestream.login.views.login'),
    (r'^login-friend/?$', 'glifestream.login.views.login_friend'),
    (r'^logout/?$', 'django.contrib.auth.views.logout',
     {'next_page': './'}),

    (r'^bookmarklet/js$', 'glifestream.bookmarklet.views.js'),
    (r'^bookmarklet/frame$', 'glifestream.bookmarklet.views.frame'),

    (r'^tools/$', sv.tools, {}, 'tools'),

    (r'^static/(?P<path>.*)$', 'django.views.static.serve',
     {'document_root': settings.MEDIA_ROOT}),
    (r'^admin/', include (admin.site.urls)),
)
