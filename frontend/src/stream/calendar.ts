/*
 *  gLifestream Copyright (C) 2009-2026 Wojciech Polak
 *
 *  This program is free software; you can redistribute it and/or modify it
 *  under the terms of the GNU General Public License as published by the
 *  Free Software Foundation; either version 3 of the License, or (at your
 *  option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

import { delegate, h } from '../util/dom';
import { _ } from '../util/i18n';
import { pad } from '../util/format';

/** A year arrow; one without `label` is disabled. */
function nav(side: 'prev' | 'next', label?: string): HTMLSpanElement {
    let arrow: HTMLElement;
    if (label) {
        arrow = h('a', { href: '#', className: side }, ['\u00a0']);
        arrow.setAttribute('aria-label', label);
    } else {
        arrow = h('span', { className: 'next-disabled' }, ['\u00a0']);
        arrow.setAttribute('aria-hidden', 'true');
    }
    return h('span', { className: 'nav-' + side }, [arrow]);
}

/** Renders the archive calendar of `year`, or of the month on view. */
export function gen_archive_calendar(year?: number | string): void {
    if (typeof stream_data === 'undefined') {
        return;
    }
    const data = stream_data;
    year = year || (data.view_date.split('/')[0] as string);
    const head = h('div', { className: 'calendar-head' }, [
        nav('prev', _('Previous year')),
        h('span', { className: 'nav-year' }, [
            h('span', { className: 'year' }, [year]),
        ]),
        parseInt(String(year), 10) < data.year_now
            ? nav('next', _('Next year'))
            : nav('next'),
    ]);
    const grid = h('div', { className: 'calendar-grid' });
    for (let month = 1; month <= 12; month++) {
        const d = year + '/' + pad(month, 2);
        const label = h('span', { className: 'month-label' }, [
            data.month_names[month - 1],
        ]);
        let item: HTMLElement;
        if (data.archives.includes(d)) {
            const ctx = data.ctx !== '' ? data.ctx + '/' : '';
            const current = d === data.view_date ? ' view-month' : '';
            item = h(
                'a',
                {
                    href: settings.baseurl + ctx + d + '/',
                    rel: 'nofollow',
                    className: 'month-item' + current,
                },
                [label],
            );
        } else {
            item = h('span', { className: 'month-item' }, [label]);
        }
        grid.append(h('span', { className: 'month-cell' }, [item]));
    }
    document.getElementById('calendar')?.replaceChildren(head, grid);
}

function shown_year(): number {
    return parseInt(document.querySelector('#calendar .year')?.textContent || '', 10);
}

/** Draws the calendar and moves it a year on the arrows. */
export function init_calendar(): void {
    gen_archive_calendar();
    delegate(document, 'click', '#calendar a.prev', function () {
        gen_archive_calendar(shown_year() - 1);
        return false;
    });
    delegate(document, 'click', '#calendar a.next', function () {
        gen_archive_calendar(shown_year() + 1);
        return false;
    });
}
