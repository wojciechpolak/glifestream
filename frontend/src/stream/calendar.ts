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

import { _ } from '../util/i18n';
import { pad } from '../util/format';

/** Renders the archive calendar of `year`, or of the month on view. */
export function gen_archive_calendar(year?: number | string): void {
    if (typeof stream_data === 'undefined') {
        return;
    }
    year = year || stream_data.view_date.split('/')[0];
    let month = 1;
    let cal = '<div class="calendar-head">';
    cal +=
        '<span class="nav-prev"><a href="#" class="prev" aria-label="' +
        _('Previous year') +
        '">&nbsp;</a></span>';
    cal += '<span class="nav-year"><span class="year">' + year + '</span></span>';
    if (parseInt(String(year), 10) < stream_data.year_now) {
        cal +=
            '<span class="nav-next"><a href="#" class="next" aria-label="' +
            _('Next year') +
            '">&nbsp;</a></span>';
    } else {
        cal +=
            '<span class="nav-next"><span class="next-disabled" aria-hidden="true">&nbsp;</span></span>';
    }
    cal += '</div><div class="calendar-grid">';
    for (let row = 0; row < 4; row++) {
        for (let col = 0; col < 3; col++, month++) {
            const d = year + '/' + pad(month, 2);
            const u = d === stream_data.view_date ? ' view-month' : '';
            if ($.inArray(d, stream_data.archives) !== -1) {
                const ctx = stream_data.ctx !== '' ? stream_data.ctx + '/' : '';
                cal +=
                    '<span class="month-cell"><a href="' +
                    settings.baseurl +
                    ctx +
                    d +
                    '/" rel="nofollow" class="month-item' +
                    u +
                    '"><span class="month-label">' +
                    stream_data.month_names[month - 1] +
                    '</span></a></span>';
            } else {
                cal +=
                    '<span class="month-cell"><span class="month-item">' +
                    '<span class="month-label">' +
                    stream_data.month_names[month - 1] +
                    '</span></span></span>';
            }
        }
    }
    cal += '</div>';
    $('#calendar').html(cal);
}

/** Draws the calendar and moves it a year on the arrows. */
export function init_calendar(): void {
    gen_archive_calendar();
    $(document).on('click', '#calendar a.prev', function () {
        const year = parseInt($('#calendar .year').html(), 10);
        gen_archive_calendar(year - 1);
        return false;
    });
    $(document).on('click', '#calendar a.next', function () {
        const year = parseInt($('#calendar .year').html(), 10);
        gen_archive_calendar(year + 1);
        return false;
    });
}
