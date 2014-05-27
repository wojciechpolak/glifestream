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
from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AdminFileWidget
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
from models import Service, Entry, Media, Favorite, List
from glifestream.stream import media


def deactivate(modeladmin, request, queryset):
    queryset.update(active=False)
deactivate.short_description = _("Deactivate item")


def activate(modeladmin, request, queryset):
    queryset.update(active=True)
activate.short_description = _("Activate item")


def truncate_title(self):
    return self.title[0:70]


class ServiceAdmin (admin.ModelAdmin):
    list_display = ('name', 'api', 'url', 'last_modified', 'public',
                    'active', 'home')
    fieldsets = (
        (None, {'fields': ('api', 'name', 'url', 'creds', 'display', 'public',
                           'active', 'home')}),
        (_('Additional, optional fields'),
         {'classes': ('collapse',), 'fields': ('link', 'cls'),
          }),
        (_('Fields updated automatically by gLifestream'),
         {'classes': ('collapse',),
          'fields': ('etag', 'last_modified', 'last_checked'),
          })
    )
    search_fields = ['url', 'name']
    actions = [deactivate, activate]


class EntryAdmin (admin.ModelAdmin):
    list_display = (truncate_title, 'service', 'active',)
    list_filter = ('service',)
    search_fields = ['title', 'content']
    actions = [deactivate, activate]


class AdminImageWidget (AdminFileWidget):

    def render(self, name, value, attrs=None):
        output = []
        file_name = str(value)
        if file_name:
            file_path = '%s/%s' % (settings.MEDIA_URL, file_name)
            if 'thumbs/' in file_name:
                thumbnail = '<img src="%s" alt="[thumbnail]" />' % file_path
            else:
                thumbnail = ''
            output.append('<p><a target="_blank" href="%s">%s</a></p>%s <a target="_blank" href="%s">%s</a><br />%s ' %
                         (file_path, thumbnail, _('Currently:'), file_path, file_path, _('Change:')))
        output.append(super(
            AdminFileWidget, self).render(name, value, attrs))
        return mark_safe(''.join(output))


class MediaForm (forms.ModelForm):
    file = forms.FileField(widget=AdminImageWidget)

    class Meta:
        model = Media


class MediaAdmin (admin.ModelAdmin):
    list_display = ('entry', 'file',)
    raw_id_fields = ('entry',)
    form = MediaForm


class FavoriteAdmin (admin.ModelAdmin):
    list_display = ('user', 'entry',)
    list_filter = ('user',)
    raw_id_fields = ('entry',)


class ListAdmin (admin.ModelAdmin):
    list_display = ('user', 'name',)
    list_filter = ('user',)

admin.site.register(Service, ServiceAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Media, MediaAdmin)
admin.site.register(Favorite, FavoriteAdmin)
admin.site.register(List, ListAdmin)
