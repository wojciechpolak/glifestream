#  gLifestream Copyright (C) 2010, 2013, 2015 Wojciech Polak
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

from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _
from django.utils.encoding import python_2_unicode_compatible
from glifestream.stream.models import Service


@python_2_unicode_compatible
class OAuthClient (models.Model):
    service = models.ForeignKey(Service, verbose_name=_('Service'),
                                null=False, blank=False, unique=True)
    identifier = models.CharField('Identifier', max_length=64, null=False,
                                  blank=False)
    secret = models.CharField('Secret', max_length=128, null=False,
                              blank=False)
    phase = models.PositiveSmallIntegerField('Phase', default=0)
    token = models.CharField('Token', max_length=64, null=True, blank=True)
    token_secret = models.CharField('Token secret', max_length=128,
                                    null=True, blank=True)
    request_token_url = models.URLField('Request Token URL', null=True,
                                        blank=True)
    access_token_url = models.URLField('Access Token URL', null=True,
                                       blank=True)
    authorize_url = models.URLField('Authorize URL', null=True, blank=True)

    class Meta:
        verbose_name = 'OAuth'
        verbose_name_plural = 'OAuth'
        ordering = 'service',

    def __str__(self):
        return u'%s: %s' % (self.service, self.identifier)


@python_2_unicode_compatible
class OpenId (models.Model):
    user = models.ForeignKey(User, db_index=True)
    identity = models.CharField(_('Identity'), max_length=128, null=False,
                                blank=False)

    class Meta:
        verbose_name = 'OpenID'
        verbose_name_plural = 'OpenID'
        ordering = 'user',
        unique_together = (('user', 'identity'),)

    def __str__(self):
        return u'%s: %s' % (self.user, self.identity)
