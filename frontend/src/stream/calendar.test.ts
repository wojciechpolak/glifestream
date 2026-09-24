/*
 *  gLifestream Copyright (C) 2026 Wojciech Polak
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

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { config } from '../config';
import { gen_archive_calendar } from './calendar';

const MONTHS = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
];

beforeEach(() => {
    config.baseurl = '/gls/';
    const data = document.createElement('script');
    data.type = 'application/json';
    data.id = 'gls-stream-data';
    data.textContent = JSON.stringify({
        ctx: 'list/news',
        year_now: 2026,
        view_date: '2025/03',
        archives: ['2025/03', '2025/11'],
        month_names: MONTHS,
    });
    document.body.replaceChildren(data);
    document.body.insertAdjacentHTML('beforeend', '<div id="calendar"></div>');
});

afterEach(() => {
    config.baseurl = '/';
    document.body.innerHTML = '';
});

function links(): string[] {
    return Array.from(
        document.querySelectorAll<HTMLAnchorElement>('#calendar a.month-item'),
        (a) => a.getAttribute('href') as string,
    );
}

describe('gen_archive_calendar', () => {
    it('shows the year on view and links only months with entries', () => {
        gen_archive_calendar();

        expect(document.querySelector('#calendar .year')?.textContent).toBe('2025');
        expect(document.querySelectorAll('#calendar .month-cell')).toHaveLength(12);
        expect(links()).toEqual(['/gls/list/news/2025/03/', '/gls/list/news/2025/11/']);
        const current = document.querySelector('#calendar a.view-month');
        expect(current?.textContent).toBe('Mar');
        expect(current?.getAttribute('rel')).toBe('nofollow');
    });

    it('offers the next year only before the current one', () => {
        gen_archive_calendar(2025);
        expect(
            document.querySelector('#calendar a.next')?.getAttribute('aria-label'),
        ).toBe('Next year');

        gen_archive_calendar(2026);
        expect(document.querySelector('#calendar a.next')).toBeNull();
        const disabled = document.querySelector('#calendar .next-disabled');
        expect(disabled?.getAttribute('aria-hidden')).toBe('true');
        expect(links()).toEqual([]);
    });
});
