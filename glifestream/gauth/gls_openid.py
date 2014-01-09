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

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.translation import ugettext as _

try:
    import openid
    from openid.consumer import consumer
    from openid import oidutil
    oidutil.log = lambda *args: None
except ImportError:
    openid = None


def start(request, identifier):
    if not openid:
        return {}

    oidconsumer = consumer.Consumer(request.session, __get_store())
    try:
        auth_request = oidconsumer.begin(identifier)
    except consumer.DiscoveryFailure, exc:
        return {'msg': _('OpenID authentication failed')}
    else:
        if auth_request is None:
            return {'msg': _('No OpenID services found for %s') % identifier}
        else:
            trust_root = settings.BASE_URL + '/'
            if request.is_secure():
                trust_root = trust_root.replace('http://', 'https://')

            return_to = request.build_absolute_uri()
            if auth_request.shouldSendRedirect():
                redirect_url = auth_request.redirectURL(
                    trust_root, return_to, immediate=False)
                return {'res': HttpResponseRedirect(redirect_url)}
            else:
                form_html = auth_request.htmlMarkup(
                    trust_root, return_to,
                    form_tag_attrs={'id': 'openid_message'},
                    immediate=False)
                return {'res': HttpResponse(form_html)}


def finish(request):
    oidconsumer = consumer.Consumer(request.session, __get_store())
    return_to = request.build_absolute_uri()
    auth_response = oidconsumer.complete(request.GET, return_to)

    if auth_response.status == consumer.CANCEL:
        return {'status': 'cancel', 'msg': _('Verification cancelled')}
    elif auth_response.status == consumer.FAILURE:
        return {'status': 'failure', 'msg': _('OpenID authentication failed: %s') % auth_response.message}
    elif auth_response.status == consumer.SUCCESS:
        return {'status': 'success', 'identity_url': auth_response.identity_url}
    return {}


def __get_store():
    mstore = getattr(settings, 'OPENID_STORE',
                     'openid.store.filestore.FileOpenIDStore')
    i = mstore.rfind('.')
    module, attr = mstore[:i], mstore[i+1:]
    mod = __import__(module, {}, {}, [attr])
    cls = getattr(mod, attr)

    if module.endswith('filestore'):
        arg = getattr(settings, 'OPENID_STORE_FILEPATH', '/tmp/gls_openid')
    else:
        from django.db import connection
        c = connection.cursor()
        arg = c.db.connection
    return cls(arg)
