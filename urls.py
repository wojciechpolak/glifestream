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
    (r'^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index),

    (r'^public/$', sv.index, {'ctx': 'public'}, 'public'),
    (r'^public/(?P<year>\d{4})/$', sv.index, {'ctx': 'public'}),
    (r'^public/(?P<year>\d{4})/(?P<month>\d{2})/$', sv.index,
     {'ctx': 'public'}),
    (r'^public/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index,
     {'ctx': 'public'}),

    (r'^entry/(?P<entry>\d+)(/.*)?$', sv.index, {}, 'entry'),
    (r'^api/(?P<cmd>[a-z]+)$', sv.api),

    (r'^favorites/$', sv.index, {'ctx': 'favorites'}, 'favorites'),
    (r'^favorites/(?P<year>\d{4})/$', sv.index, {'ctx': 'favorites'}),
    (r'^favorites/(?P<year>\d{4})/(?P<month>\d{2})/$',
     sv.index, {'ctx': 'favorites'}),
    (r'^favorites/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
     sv.index, {'ctx': 'favorites'}),

    (r'^list/(?P<list>[a-z0-9\-]+)/$', sv.index, {}, 'list'),
    (r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/$', sv.index),
    (r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/(?P<month>\d{2})/$',
     sv.index),
    (r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index),

    (r'^pshb/(?P<id>[a-f0-9]{20})$', sv.pshb_dispatcher, {}, 'pshb'),

    (r'^login/?$', 'glifestream.gauth.views.login'),
    (r'^logout/?$', 'django.contrib.auth.views.logout',
     {'next_page': './'}),

    (r'^auth/', include ('glifestream.gauth.urls')),
    (r'^bookmarklet/', include ('glifestream.bookmarklet.urls')),
    (r'^settings/', include ('glifestream.usettings.urls')),

    (r'^static/(?P<path>.*)$', 'django.views.static.serve',
     {'document_root': settings.MEDIA_ROOT}),
    (r'^admin/', include (admin.site.urls)),
)
