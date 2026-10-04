"""
# gLifestream Copyright (C) 2026 Wojciech Polak
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import copy
import difflib
import re
from typing import Any, cast
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.cache import never_cache

from glifestream import upgrades
from glifestream.stream.index_view import entry_link
from glifestream.stream.models import Entry, EntryUpgrade
from glifestream.usettings.common import build_settings_page, get_staff_settings_user


def _upgrader(key: str) -> upgrades.Upgrader:
    upgrader = upgrades.UPGRADERS.get(key)
    if upgrader is None:
        raise Http404
    return upgrader


def _review_url(key: str, **params: Any) -> str:
    url = reverse('usettings-upgrade-review', args=[key])
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return '%s?%s' % (url, query) if query else url


@login_required
@never_cache
def upgrades_overview(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = build_settings_page(request, title=_('Upgrades - Settings'), menu='upgrades')
    rows = [{'upgrader': u, **upgrades.counts(u)} for u in upgrades.UPGRADERS.values()]
    return render(
        request,
        'upgrades.html',
        {
            'page': page,
            'authed': True,
            'is_secure': request.is_secure(),
            'user': request.user,
            'rows': rows,
            'history': _history_rows(),
        },
    )


def _history_rows(limit: int = 20) -> list[dict[str, Any]]:
    """The latest upgrades, newest first, a batch folded into one row."""
    rows: list[dict[str, Any]] = []
    batches: dict[str, dict[str, Any]] = {}
    for upgrade in upgrades.history(limit=500):
        if not upgrade.batch:
            rows.append({'upgrade': upgrade})
        elif upgrade.batch not in batches:
            batches[upgrade.batch] = {'batch': upgrade.batch, 'first': upgrade}
            rows.append(batches[upgrade.batch])
    rows = rows[:limit]
    shown = [row['batch'] for row in rows if 'batch' in row]
    tallies = (
        EntryUpgrade.objects.filter(batch__in=shown)
        .values('batch')
        .annotate(
            count=Count('id'),
            applied=Count('id', filter=Q(status=EntryUpgrade.STATUS_APPLIED)),
        )
    )
    for tally in tallies:
        batches[tally['batch']].update(count=tally['count'], applied=tally['applied'])
    return rows


def _next_in_queue(queue: list[Entry], after: Entry | None) -> int | None:
    """The index of the first entry of `queue` that comes after `after` in
    its order, or of the first one at all."""
    if not queue:
        return None
    if after is None:
        return 0
    mark = (after.date_published, after.pk)
    for i, e in enumerate(queue):
        if (e.date_published, e.pk) > mark:
            return i
    return None


def _render_article(entry: Entry, page: dict[str, Any], *, copy_of: bool) -> SafeString:
    """`entry` as a visitor of the stream sees it.

    The proposed copy shares its pk with the stored entry, so its element
    ids are dropped to keep those of the page unique.
    """
    html: str = render_to_string(
        'stream-pure.html',
        {'entries': [entry], 'page': page, 'authed': False, 'friend': False},
    )
    if copy_of:
        html = re.sub(r' id="(?:entry|shareit)-\d+"', '', html)
    return mark_safe(html)


def _queue_index(queue: list[Entry], entry_id: str, after_id: str) -> int | None:
    """Where the review stands: at the entry asked for, or past the one
    decided last, or at the start."""
    if entry_id.isdigit():
        for i, e in enumerate(queue):
            if e.pk == int(entry_id):
                return i
    after = None
    if after_id.isdigit():
        after = Entry.objects.filter(pk=int(after_id)).first()
    return _next_in_queue(queue, after)


def _source_lines(html: str | None) -> list[str]:
    """`html` one tag per line, so a diff of it points at the tag."""
    if not html:
        return []
    return re.sub(r'(?<!^)<(?!/)', '\n<', html).split('\n')


_DIFF_CLASSES = {'-': 'del', '+': 'ins', '@': 'hunk'}


def _diff(label: str, old: str | None, new: str | None) -> list[tuple[str, str]]:
    """A unified diff of two sources, as (class, line) pairs to show."""
    if (old or '') == (new or ''):
        return []
    lines = difflib.unified_diff(
        _source_lines(old),
        _source_lines(new),
        fromfile='%s (A)' % label,
        tofile='%s (B)' % label,
        lineterm='',
    )
    return [
        (
            'file' if line[:3] in ('---', '+++') else _DIFF_CLASSES.get(line[:1], ''),
            line,
        )
        for line in lines
    ]


@login_required
@never_cache
def upgrade_review(request: HttpRequest, key: str, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user
    upgrader = _upgrader(key)

    queue = upgrades.pending(upgrader)
    index = _queue_index(
        queue, request.GET.get('entry', ''), request.GET.get('after', '')
    )

    page = _settings_page_with_author(
        request, _('%s upgrades - Settings') % upgrader.label
    )
    context: dict[str, Any] = {
        'page': page,
        'authed': True,
        'is_secure': request.is_secure(),
        'user': request.user,
        'upgrader': upgrader,
        'total': len(queue),
        'markup_only': len(upgrades.markup_only(upgrader, queue)),
        'entry': None,
    }

    done = request.GET.get('done', '')
    if done.isdigit():
        context['done'] = EntryUpgrade.objects.filter(pk=int(done)).first()

    if index is not None:
        entry = queue[index]
        context.update(
            {
                'entry': entry,
                'friends_only': entry.friends_only,
                'position': index + 1,
                'later_url': _review_url(key, after=entry.pk),
            }
        )
        values = None
        if upgrader.fields:
            values = _field_values(request, upgrader, entry)
            context['fields'] = [
                {
                    'name': f.name,
                    'label': f.label,
                    'value': values.get(f.name, ''),
                    'help': upgrader.field_help(f.name, values),
                }
                for f in upgrader.fields
            ]
        try:
            proposal = upgrader.propose(entry, values)
        except upgrades.Unavailable as exc:
            context.update(_compare(entry, None, page))
            context['unavailable'] = str(exc)
        else:
            context.update(_compare(entry, proposal, page))
            context['token'] = upgrades.make_token(entry, upgrader, proposal)
    return render(request, 'upgrade_review.html', context)


def _field_values(
    request: HttpRequest, upgrader: upgrades.Upgrader, entry: Entry
) -> dict[str, str]:
    """What the owner entered in the upgrader's fields, or else what the
    upgrader guesses from the entry."""
    names = [f.name for f in upgrader.fields]
    if any(name in request.GET for name in names):
        return {name: request.GET.get(name, '') for name in names}
    return upgrader.guess(entry)


def _settings_page_with_author(request: HttpRequest, title: str) -> dict[str, Any]:
    """A settings page that can show entries as the stream does."""
    page = build_settings_page(request, title=title, menu='upgrades')
    page['author_name'] = settings.FEED_AUTHOR_NAME
    page['author_uri'] = getattr(settings, 'FEED_AUTHOR_URI', False)
    return page


def _compare(
    entry: Entry, proposal: upgrades.Proposal | None, page: dict[str, Any]
) -> dict[str, Any]:
    """The A/B preview of an upgrade of `entry`, and the diff of its source."""
    cast(Any, entry).gls_link = entry_link(entry)
    # Shown to the owner, who sees what friends see.
    entry.friends_only = False
    compare: dict[str, Any] = {
        'before': _render_article(entry, page, copy_of=False),
    }
    if proposal is not None:
        proposed = copy.copy(entry)
        proposed.content = proposal.content
        proposed.link = proposal.link
        proposed.mblob = proposal.mblob
        compare['after'] = _render_article(proposed, page, copy_of=True)
        compare['diffs'] = [
            d
            for d in (
                _diff('content', entry.content, proposal.content),
                _diff('link', entry.link, proposal.link),
                _diff('mblob', entry.mblob, proposal.mblob),
            )
            if d
        ]
    return compare


def _changes(entry: Entry, proposal: upgrades.Proposal) -> list[str]:
    """Which of its fields an upgrade changes, in words for the owner."""
    changes = []
    if entry.content != proposal.content:
        changes.append(_('markup'))
    if entry.link != proposal.link:
        changes.append(_('link'))
    if entry.mblob != proposal.mblob:
        changes.append(_('media'))
    return changes


@login_required
@never_cache
def upgrade_markup_only(request: HttpRequest, key: str, **args: Any) -> HttpResponse:
    """The list of entries whose upgrade keeps their thumbnail, to approve
    all at once."""
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user
    upgrader = _upgrader(key)

    items = upgrades.markup_only(upgrader)
    if not items:
        messages.info(request, _('No waiting entry changes only its markup.'))
        return HttpResponseRedirect(reverse('usettings-upgrades'))

    page = _settings_page_with_author(
        request, _('%s upgrades - Settings') % upgrader.label
    )
    sample, sample_proposal = items[0]
    rows = [
        {'entry': entry, 'changes': _changes(entry, proposal)}
        for entry, proposal in items
    ]
    context = {
        'page': page,
        'authed': True,
        'is_secure': request.is_secure(),
        'user': request.user,
        'upgrader': upgrader,
        'rows': rows,
        'sample': sample,
        'token': upgrades.make_batch_token(upgrader, [e for e, _p in items]),
        **_compare(sample, sample_proposal, page),
    }
    return render(request, 'upgrade_markup_only.html', context)


def _staff_post(request: HttpRequest) -> HttpResponse | None:
    """The refusal of a request that is not a staff member's POST, if it is not."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    user = get_staff_settings_user(request)
    return user if isinstance(user, HttpResponseForbidden) else None


@login_required
def upgrade_apply(request: HttpRequest, key: str, **args: Any) -> HttpResponse:
    if forbidden := _staff_post(request):
        return forbidden
    _upgrader(key)
    entry_id = request.POST.get('entry', '')
    try:
        upgrade = upgrades.apply(request.POST.get('token', ''))
    except upgrades.UpgradeConflict as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(_review_url(key))
    return HttpResponseRedirect(_review_url(key, after=entry_id, done=upgrade.pk))


@login_required
def upgrade_skip(request: HttpRequest, key: str, **args: Any) -> HttpResponse:
    if forbidden := _staff_post(request):
        return forbidden
    upgrader = _upgrader(key)
    entry = Entry.objects.filter(pk=request.POST.get('entry') or 0).first()
    if entry is None:
        raise Http404
    upgrades.skip(entry, upgrader)
    messages.info(request, _('Skipped. The entry stays as it was.'))
    return HttpResponseRedirect(_review_url(key, after=entry.pk))


@login_required
def upgrade_requeue(request: HttpRequest, key: str, **args: Any) -> HttpResponse:
    if forbidden := _staff_post(request):
        return forbidden
    count = upgrades.requeue_skipped(_upgrader(key))
    messages.info(
        request,
        ngettext(
            '%d skipped entry is back in the queue.',
            '%d skipped entries are back in the queue.',
            count,
        )
        % count,
    )
    return HttpResponseRedirect(reverse('usettings-upgrades'))


@login_required
def upgrade_revert(request: HttpRequest, id: str, **args: Any) -> HttpResponse:
    if forbidden := _staff_post(request):
        return forbidden
    try:
        upgrade = upgrades.revert(int(id))
    except upgrades.UpgradeConflict as exc:
        messages.error(request, str(exc))
    else:
        messages.info(
            request,
            _('Reverted. The entry is as it was and back in the queue.'),
        )
        if request.POST.get('next') == 'review':
            return HttpResponseRedirect(
                _review_url(upgrade.upgrader, entry=upgrade.entry_id)
            )
    return HttpResponseRedirect(reverse('usettings-upgrades'))


@login_required
def upgrade_apply_markup_only(
    request: HttpRequest, key: str, **args: Any
) -> HttpResponse:
    if forbidden := _staff_post(request):
        return forbidden
    _upgrader(key)
    try:
        result = upgrades.apply_markup_only(request.POST.get('token', ''))
    except upgrades.UpgradeConflict as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(
            reverse('usettings-upgrade-markup-only', args=[key])
        )
    messages.info(
        request,
        ngettext(
            'Applied to %d entry. Recent upgrades below can revert the batch.',
            'Applied to %d entries. Recent upgrades below can revert the batch.',
            result.applied,
        )
        % result.applied,
    )
    if result.refused:
        messages.warning(
            request,
            ngettext(
                '%d entry changed after the list was shown and was left as it is.',
                '%d entries changed after the list was shown and were left as they are.',
                result.refused,
            )
            % result.refused,
        )
    return HttpResponseRedirect(reverse('usettings-upgrades'))


@login_required
def upgrade_revert_batch(request: HttpRequest, batch: str, **args: Any) -> HttpResponse:
    if forbidden := _staff_post(request):
        return forbidden
    reverted, refused = upgrades.revert_batch(batch)
    messages.info(
        request,
        ngettext(
            'Reverted %d entry. It is as it was and back in the queue.',
            'Reverted %d entries. They are as they were and back in the queue.',
            reverted,
        )
        % reverted,
    )
    if refused:
        messages.warning(
            request,
            ngettext(
                '%d entry changed after the upgrade and was not reverted.',
                '%d entries changed after the upgrade and were not reverted.',
                refused,
            )
            % refused,
        )
    return HttpResponseRedirect(reverse('usettings-upgrades'))
