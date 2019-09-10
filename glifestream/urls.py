#  gLifestream Copyright (C) 2009, 2010, 2013, 2014, 2015 Wojciech Polak
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
from django.conf.urls import url, include
from django.contrib import admin
from django.contrib.auth.views import logout
from django.views.static import serve as static_serve
admin.autodiscover()

from glifestream.stream import views as sv
from glifestream.gauth.views import login

handler404 = 'glifestream.stream.views.page_not_found'

urlpatterns = [
    url(r'^$', sv.index, name='index'),
    url(r'^(?P<year>\d{4})/$', sv.index),
    url(r'^(?P<year>\d{4})/(?P<month>\d{2})/$', sv.index),
    url(r'^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index),

    url(r'^public/$', sv.index, {'ctx': 'public'}, name='public'),
    url(r'^public/(?P<year>\d{4})/$', sv.index, {
        'ctx': 'public'}),
    url(r'^public/(?P<year>\d{4})/(?P<month>\d{2})/$', sv.index,
        {'ctx': 'public'}),
    url(r'^public/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index,
        {'ctx': 'public'}),

    url(r'^entry/(?P<entry>\d+)(/.*)?$', sv.index, {}, name='entry'),
    url(r'^api/(?P<cmd>[a-z]+)$', sv.api, name='api'),

    url(r'^favorites/$', sv.index, {
        'ctx': 'favorites'}, name='favorites'),
    url(r'^favorites/(?P<year>\d{4})/$', sv.index, {
        'ctx': 'favorites'}),
    url(r'^favorites/(?P<year>\d{4})/(?P<month>\d{2})/$',
        sv.index, {'ctx': 'favorites'}),
    url(r'^favorites/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
        sv.index, {'ctx': 'favorites'}),

    url(r'^list/(?P<list>[a-z0-9\-]+)/$', sv.index, {}, name='list'),
    url(r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/$', sv.index),
    url(r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/(?P<month>\d{2})/$',
        sv.index),
    url(r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
        sv.index),

    url(r'^pshb/(?P<id>[a-f0-9]{20})$',
        sv.pshb_dispatcher, {}, name='pshb'),

    url(r'^login/?$', login, name='login'),
    url(r'^logout/?$', logout, {'next_page': './'}, name='logout'),

    url(r'^auth/', include('glifestream.gauth.urls')),
    url(r'^bookmarklet/', include(
        'glifestream.bookmarklet.urls')),
    url(r'^settings/', include('glifestream.usettings.urls')),

    url(r'^admin/', include(admin.site.urls)),
]

urlpatterns += [
    url(r'^media/(?P<path>.*)$', static_serve,
        {'document_root': settings.MEDIA_ROOT})
]
