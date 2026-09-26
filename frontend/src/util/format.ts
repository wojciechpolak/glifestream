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

/** `number` as a string of at least `len` digits, padded with zeros. */
export function pad(number: number | string, len: number): string {
    let str = '' + number;
    while (str.length < len) {
        str = '0' + str;
    }
    return str;
}

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const YEAR = 365 * DAY;

/** Each unit, its length in seconds, and how many of it make the next one. */
const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number, number][] = [
    ['second', 1, 60],
    ['minute', MINUTE, 60],
    ['hour', HOUR, 24],
    ['day', DAY, 30],
    ['month', 30 * DAY, 12],
];

/**
 * `date` relative to `now`, as "5 minutes ago" or "in 3 hours" in `locale`.
 * With `past`, a date after `now` (the server's clock ahead of the reader's)
 * counts as now.
 */
export function format_relative_time(
    date: Date,
    now: Date,
    locale?: string,
    { past = false }: { past?: boolean } = {},
): string {
    let seconds = (date.getTime() - now.getTime()) / 1000;
    if (past && seconds > 0) {
        seconds = 0;
    }
    if (Math.abs(seconds) < 1) {
        return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(
            0,
            'second',
        );
    }
    const format = new Intl.RelativeTimeFormat(locale, { numeric: 'always' });
    // Rounded alike either side of now, as Math.round takes -1.5 up to -1.
    const sign = seconds < 0 ? -1 : 1;
    const abs = Math.abs(seconds);
    // The first unit whose rounded count stays below the next unit.
    for (const [unit, length, next] of RELATIVE_UNITS) {
        const count = Math.round(abs / length);
        if (count < next) {
            return format.format(sign * count, unit);
        }
    }
    return format.format(sign * Math.round(abs / YEAR), 'year');
}
