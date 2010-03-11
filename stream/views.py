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

import time
import datetime
from django.conf import settings
from django.core import urlresolvers
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.http import HttpResponseNotFound
from django.http import Http404
from django.shortcuts import render_to_response
from django.template.defaultfilters import fix_ampersands
from django.template.defaultfilters import truncatewords
from django.contrib.auth.decorators import login_required
from django.utils.translation import ugettext as _
from django.utils.html import escape
from django.views.decorators.cache import never_cache
from glifestream.stream.templatetags.gls_filters import gls_content
from glifestream.stream.templatetags.gls_filters import gls_slugify
from glifestream.stream.models import Service, Entry, Favorite, List
from glifestream.stream import media, pshb
from glifestream.utils.time import pn_month_start
from glifestream.utils.translate import translate
from glifestream.apis import selfposts

try:
    import json
except ImportError:
    import simplejson as json

def index (request, **args):
    site_url = '%s://%s' % (request.is_secure () and 'https' or 'http',
                            request.get_host ())
    page = {
        'backtime': True,
        'robots': 'index',
        'public': False,
        'site_url': site_url,
        'base_url': settings.BASE_URL,
        'login_url': settings.LOGIN_URL,
        'author_name': settings.FEED_AUTHOR_NAME,
        'taguri': settings.FEED_TAGURI,
        'icon': settings.FEED_ICON,
        'maps_engine': settings.MAPS_ENGINE,
        'maps_key': settings.MAPS_KEY,
        'fb_api_key': settings.FACEBOOK_API_KEY,
        'pshb_hubs': settings.PSHB_HUBS,
    }
    authed = request.user.is_authenticated () and request.user.is_staff
    friend = request.user.is_authenticated () and not request.user.is_staff
    urlparams = []
    entries_on_page = settings.ENTRIES_ON_PAGE
    entries_orderby = 'date_published'

    # Entries filter.
    fs = { 'active': True, 'service__home': True }

    # Filter by dates.
    year = int (args.get ('year', 0))
    month = int (args.get ('month', 0))
    day = int (args.get ('day', 0))
    if year: fs[entries_orderby + '__year'] = year
    if month: fs[entries_orderby + '__month'] = month
    if day: fs[entries_orderby + '__day'] = day
    if year and month and day:
        dt = datetime.date (year, month, day).strftime ('%Y/%m/%d')
    elif year and month:
        dt = datetime.date (year, month, 1)
        prev, next = pn_month_start (dt)
        page['month_nav']  = True
        page['month_prev'] = prev.strftime ('%Y/%m')
        page['month_next'] = next.strftime ('%Y/%m')
        dt = dt.strftime ('%Y/%m')
    elif year:
        dt = datetime.date (year, 1, 1).strftime ('%Y')

    if year:
        page['backtime'] = False
        page['title'] = dt
        page['subtitle'] = _('You are currently browsing the archive for %s') % ('<b>'+dt+'</b>')
        page['robots'] = 'noindex'

    if page['backtime']:
        entries = Entry.objects.order_by ('-' + entries_orderby)
    else:
        entries = Entry.objects.order_by (entries_orderby)

    if not authed:
        fs['draft'] = False
    if not authed or 'public' in args:
        fs['service__public'] = True
        page['public'] = True

    # Filter for favorites.
    if 'favorites' in args:
        if not authed:
            return HttpResponseRedirect (settings.BASE_URL + '/')
        favs = Favorite.objects.filter (user__id=request.user.id)
        page['favorites'] = True
        page['title'] = _('Favorites')
        page['subtitle'] = _('You are currently browsing your favorite entries')
        fs['id__in'] = favs.values ('entry')

    # Filter lists.
    elif 'list' in args:
        try:
            services = List.objects.get (user__id=request.user.id,
                                         slug=args['list']).services
            del fs['service__home']
            fs['service__id__in'] = services.values ('id')
            page['title'] = args['list']
            page['subtitle'] = _('You are currently browsing entries from %s list only.') % ('<b>'+ args['list'] +'</b>')
        except List.DoesNotExist:
            if authed:
                raise Http404

    # Filter for exactly one given entry.
    elif 'entry' in args:
        fs['id__exact'] = int (args['entry'])
        page['exactentry'] = True
        if authed:
            del fs['service__public']

    # Filter by class type.
    cls = request.GET.get ('class', 'all')
    if cls != 'all':
        fs['service__cls'] = cls
        urlparams.append ('class=' + cls)
        page['robots'] = 'noindex'
        if 'subtitle' in page:
            page['subtitle'] += ' <b>(%s)</b>' % escape (cls.capitalize ())
        else:
            page['subtitle'] = _('You are currently browsing %s entries only.') % ('<b>'+ escape (cls) +'</b>')

    # Filter by author name.
    author = request.GET.get ('author', 'all')
    if author != 'all':
        fs['author_name'] = author
        urlparams.append ('author=' + author)
        page['robots'] = 'noindex'

    # Filter by service type.
    srvapi = request.GET.get ('service', 'all')
    if srvapi != 'all':
        fs['service__api'] = srvapi
        urlparams.append ('service=' + srvapi)
        page['robots'] = 'noindex'
        if 'subtitle' in page:
            page['subtitle'] += ' <b>(%s)</b>' % escape (srvapi.capitalize ())
        else:
            page['subtitle'] = _('You are currently browsing entries from %s service only.') % ('<b>'+ escape (srvapi.capitalize ()) +'</b>')

    # Filter entries after specified timestamp 'start'.
    after = False
    start = request.GET.get ('start', False)
    if start:
        qs = fs.copy ()
        dt = datetime.datetime.fromtimestamp (float (start))

        if page['backtime']:
            fs[entries_orderby + '__lte'] = dt
            qs[entries_orderby + '__gt'] = fs[entries_orderby + '__lte']
            q = Entry.objects.order_by (entries_orderby)
        else:
            fs[entries_orderby + '__gte'] = dt
            qs[entries_orderby + '__lt'] = fs[entries_orderby + '__gte']
            q = Entry.objects.order_by ('-' + entries_orderby)

        q = q.filter (**qs)[0:entries_on_page].values (entries_orderby)
        if len (q):
            after = q[len (q) - 1][entries_orderby]
            after = int (time.mktime (after.timetuple ()))
        page['title'] = '%s' % str (dt)[0:-3]
        page['robots'] = 'noindex'

    # Search/Query entries.
    search_enable = getattr (settings, 'SEARCH_ENABLE', False)
    search_engine = getattr (settings, 'SEARCH_ENGINE', 'sphinx')
    search_query = request.GET.get ('s', '')

    if search_query != '' and search_enable and search_engine == 'sphinx' and \
       Entry.sphinx.query:
        page['search'] = search_query
        page['title'] = 'Search Results for %s' % escape (search_query)
        page['subtitle'] = _('Your search for %s returned the following results.') % ('<b>'+ escape (search_query) +'</b>')
        urlparams.append ('s=' + search_query)
        sfs = {}
        if page['public']: sfs['public'] = True
        if not authed and not friend: sfs['friends_only'] = False
        page_number = int (request.GET.get ('page', 1))
        offset = (page_number - 1) * entries_on_page

        try:
            entries = Entry.sphinx.query (search_query).filter (**sfs).select_related ()

            limit = offset + entries_on_page
            if offset >= entries_on_page:
                page['prevpage'] = page_number - 1
            if limit < entries.count ():
                page['nextpage'] = page_number + 1

            entries = entries[offset:limit]
        except:
            entries = []

        start = False

    # If not search, then normal query.
    else:
        entries = entries.filter (**fs)[0:entries_on_page + 1].select_related ()
        num = len (entries)

        if 'exactentry' in page and num:
            page['title'] = truncatewords (entries[0].title, 7)

        # Time-based pagination.
        if num > entries_on_page:
            start = entries[num - 1].__getattribute__ (entries_orderby)
            start = int (time.mktime (start.timetuple ()))
        else:
            start = False

        entries = entries[0:entries_on_page]

        if num:
            crymax = entries[0].date_published.year
            crymin = entries[len (entries) - 1].date_published.year
            if crymin != crymax:
                page['copyright_years'] = '%s-%s' % (crymin, crymax)
            else:
                page['copyright_years'] = crymin

    # Build URL params for links.
    if len (urlparams):
        urlparams = '?' + reduce (lambda x, y: unicode (x) +'&'+ unicode (y),
                                  urlparams, '')[1:] + '&'
    else:
        urlparams = '?'

    if len (entries):
        page['updated'] = entries[0].date_published
    else:
        page['updated'] = datetime.datetime.utcnow ()
    page['urlparams'] = urlparams
    page['start'] = start
    page['after'] = after

    if hasattr (settings, 'STREAM_TITLE'):
        page_title = settings.STREAM_TITLE
    else:
        page_title = None

    if hasattr (settings, 'STREAM_DESCRIPTION'):
        page['description'] = settings.STREAM_DESCRIPTION

    # Set page theme.
    page['themes'] = settings.THEMES
    page['themes_more'] = True if len (settings.THEMES) > 1 else False
    page['theme'] = __get_theme (request)

    # Setup links.
    page['need_fbc'] = False
    for entry in entries:
        entry.only_for_friends = entry.friends_only

        if authed or friend:
            entry.friends_only = False
        elif entry.friends_only:
            page['need_fbc'] = True

        if not entry.friends_only:
            entry.gls_link = '%s/%s' % (urlresolvers.reverse ('entry', args=[entry.id]),
                                        gls_slugify (truncatewords (entry.title, 7)))
        else:
            entry.gls_link = '%s/' % (urlresolvers.reverse ('entry', args=[entry.id]))
            if 'title' in page: del page['title']

        entry.gls_absolute_link = '%s%s' % (page['site_url'], entry.gls_link)

    # Check single-entry URL
    if 'exactentry' in page:
        if len (entries):
            if entries[0].gls_link != request.path:
                return HttpResponseRedirect (entries[0].gls_link)
        else:
            raise Http404

    if 'title' in page and page['title'] != '':
        if page_title:
            page['title'] += ': ' + page_title
        else:
            page['title'] += ': Lifestream'
    elif page_title:
        page['title'] = page_title

    # Pickup right output format and finish.
    format = request.GET.get ('format', 'html')
    if format == 'atom':
        return render_to_response ('stream.atom',
                                   { 'entries': entries,
                                     'page': page },
                                   mimetype='application/atom+xml')
    elif format == 'json':
        return render_to_response ('stream.json',
                                   { 'entries': entries,
                                     'page': page },
                                   mimetype='application/json')
    else:
        # Check which entry is already favorite.
        if authed and not 'favorites' in args:
            ents = [entry.id for entry in entries]
            favs = Favorite.objects.filter (user__id=request.user.id,
                                            entry__id__in=ents)
            favs = [f.entry_id for f in favs]
            for entry in entries:
                if entry.id in favs:
                    entry.fav = True
                if entry.service.api in ('twitter', 'identica'):
                    entry.sms = True

        # Get lists.
        lists = List.objects.filter (user__id=request.user.id).order_by ('name')

        # Get archives.
        archs = Entry.objects.dates ('date_published', 'month', order='DESC')

        # List available classes.
        fs = {}
        if not authed or 'public' in args:
            fs['public'] = True
        classes = Service.objects.filter (**fs).order_by ('id').values ('api', 'cls')
        classes.query.group_by = ['cls']

        accept_lang = request.META.get ('HTTP_ACCEPT_LANGUAGE', '').split (',')
        for i, lang in enumerate (accept_lang):
            accept_lang[i] = lang.split (';')[0]
        page['lang'] = accept_lang[0]

        request.user.fb_username = request.session.get ('fb_username', '')
        request.user.fb_profile_url = request.session.get ('fb_profile_url', '')

        res = render_to_response ('stream.html',
                                  { 'classes': classes,
                                    'entries': entries,
                                    'lists': lists,
                                    'archives': archs,
                                    'page': page,
                                    'authed': authed,
                                    'friend': friend,
                                    'has_search': search_enable,
                                    'is_secure': request.is_secure (),
                                    'user': request.user })
        res['X-XRDS-Location'] = request.build_absolute_uri (
            urlresolvers.reverse ('glifestream.auth.views.xrds'))
        return res

@never_cache
def pshb_dispatcher (request, **args):
    if request.method == 'GET':
        res = pshb.verify (args['id'], request.GET)
        if res:
            return HttpResponse (res)
    elif request.method == 'POST':
        pshb.accept_payload (args['id'], request.raw_post_data, request.META)
        return HttpResponse ()
    raise Http404

@login_required
def tools (request, **args):
    authed = request.user.is_authenticated () and request.user.is_staff
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'theme': __get_theme (request),
    }
    return render_to_response ('tools.html',{ 'page': page, 'authed': authed,
                                              'is_secure': request.is_secure (),
                                              'user': request.user })

def page_not_found (request, **args):
    from django.template import RequestContext, loader
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'theme': __get_theme (request),
    }
    t = loader.get_template ('404.html')
    return HttpResponseNotFound (t.render (RequestContext (request, {'page': page})))


def __get_theme (request):
    gl_theme = request.COOKIES.get ('glifestream_theme', settings.THEMES[0])
    if not gl_theme in settings.THEMES:
        gl_theme = settings.THEMES[0]
    return gl_theme

#
# XHR API
#

def api (request, **args):
    cmd = args.get ('cmd', '')
    entry = request.POST.get ('entry', None)

    authed = request.user.is_authenticated () and request.user.is_staff
    friend = request.user.is_authenticated () and not request.user.is_staff
    if not authed and cmd != 'getcontent':
        return HttpResponseForbidden ()

    if cmd == 'hide' and entry:
        Entry.objects.filter (id=int(entry)).update (active=False)

    elif cmd == 'unhide' and entry:
        Entry.objects.filter (id=int(entry)).update (active=True)

    elif cmd == 'gsc': # get selfposts classes
        srvs = Service.objects.filter (api='selfposts').order_by ('cls')
        srvs.query.group_by = ['cls']
        srvs = srvs.values ('id', 'cls')
        d = []
        for s in srvs:
            d.append ({ 'id': s['id'], 'cls': s['cls'] })
        return HttpResponse (json.dumps (d), mimetype='application/json')

    elif cmd == 'share':
        images = []
        for i in range (0, 5):
            img = request.POST.get ('image' + str (i), None)
            if img:
                images.append (img)
        source = request.POST.get ('from', '')
        entry = selfposts.API (False).share (
            { 'content': request.POST.get ('content', ''),
              'id': request.POST.get ('id', None),
              'draft': request.POST.get ('draft', False),
              'friends_only': request.POST.get ('friends_only', False),
              'link': request.POST.get ('link', None),
              'images': images,
              'files': request.FILES,
              'source': source,
              'user': request.user })
        if entry:
            if not entry.draft:
                pshb.publish ()
            if source == 'bookmarklet':
                d = {'close_msg': _("You've successfully shared this web page at your stream.")}
                return HttpResponse (json.dumps (d),
                                     mimetype='application/json')
            else:
                entry.friends_only = False
                if request.is_ajax ():
                    return render_to_response ('stream-pure.html',
                                               { 'entries': (entry,),
                                                 'authed': authed })
                else:
                    return HttpResponseRedirect (settings.BASE_URL + '/')

    elif cmd == 'reshare' and entry:
        try:
            entry = Entry.objects.get (id=int(entry))
            if entry:
                entry = selfposts.API (False).reshare (
                    entry, { 'as_me': request.POST.get ('as_me', False),
                             'user': request.user })
                if entry:
                    pshb.publish ()
                    return render_to_response ('stream-pure.html',
                                               { 'entries': (entry,),
                                                 'authed': authed })
        except Exception:
            pass

    elif cmd == 'favorite':
        try:
            entry = Entry.objects.get (id=int(entry))
            if entry:
                try:
                    fav = Favorite.objects.get (user=request.user, entry=entry)
                except Favorite.DoesNotExist:
                    fav = Favorite (user=request.user, entry=entry)
                    fav.save ()
                    media.transform_to_local (entry)
                    media.extract_and_register (entry)
                    entry.save ()
        except Exception:
            pass

    elif cmd == 'unfavorite':
        try:
            if entry:
                entry = Entry.objects.get (id=int(entry))
                if entry:
                    Favorite.objects.get (user=request.user,
                                          entry=entry).delete ()
        except Exception:
            pass

    elif cmd == 'getcontent':
        try:
            if entry:
                if not authed:
                    entry = Entry.objects.get (id=int(entry),
                                               service__public=True)
                else:
                    entry = Entry.objects.get (id=int(entry))
                if entry:
                    if authed or friend:
                        entry.friends_only = False
                    content = fix_ampersands (gls_content ('', entry))
                    return HttpResponse (content)
        except Exception:
            pass

    elif cmd == 'translate':
        try:
            if entry:
                entry = Entry.objects.get (id=int(entry))
                if entry:
                    accept_lang = request.META.get ('HTTP_ACCEPT_LANGUAGE',
                                                    '').split (',')
                    for i, lang in enumerate (accept_lang):
                        accept_lang[i] = lang.split (';')[0]

                    entry.content = translate (entry.content,
                                               target=accept_lang[0])
                    content = fix_ampersands (gls_content ('', entry))
                    return HttpResponse (content)
        except Exception:
            pass

    return HttpResponse ()
