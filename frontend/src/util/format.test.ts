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

import { describe, expect, it } from 'vitest';

import { format_relative_time, pad } from './format';

describe('pad', () => {
    it('pads with zeros to the length', () => {
        expect(pad(7, 2)).toBe('07');
        expect(pad('3', 4)).toBe('0003');
    });

    it('leaves a long enough number alone', () => {
        expect(pad(12, 2)).toBe('12');
        expect(pad(2026, 2)).toBe('2026');
    });
});

describe('format_relative_time', () => {
    const now = new Date('2026-09-26T12:00:00Z');
    const ago = (seconds: number, locale = 'en', past = false): string =>
        format_relative_time(new Date(now.getTime() - seconds * 1000), now, locale, {
            past,
        });

    it('picks the largest unit that fits', () => {
        expect(ago(59)).toBe('59 seconds ago');
        expect(ago(60)).toBe('1 minute ago');
        expect(ago(59 * 60)).toBe('59 minutes ago');
        expect(ago(23 * 3600)).toBe('23 hours ago');
        expect(ago(2 * 86400 + 5)).toBe('2 days ago');
        expect(ago(45 * 86400)).toBe('2 months ago');
        expect(ago(400 * 86400)).toBe('1 year ago');
    });

    it('rounds to the nearest count, moving up a unit when it fills one', () => {
        expect(ago(59.6)).toBe('1 minute ago');
        expect(ago(4 * 86400 - 2)).toBe('4 days ago');
        expect(ago(-(17 * 60 - 5))).toBe('in 17 minutes');
        expect(ago(59 * 60 + 40)).toBe('1 hour ago');
    });

    it('reads a future time forward', () => {
        expect(ago(-3 * 60)).toBe('in 3 minutes');
        expect(ago(-3 * 60, 'pl')).toBe('za 3 minuty');
    });

    it('speaks the locale', () => {
        expect(ago(5 * 60, 'pl')).toBe('5 minut temu');
        expect(ago(2 * 86400, 'pl')).toBe('2 dni temu');
    });

    it('is now under a second', () => {
        expect(ago(0.4)).toBe('now');
        expect(ago(0, 'pl')).toBe('teraz');
    });

    it('treats a future time as now when it must be past', () => {
        expect(ago(-5, 'en', true)).toBe('now');
        expect(ago(-5, 'en', false)).toBe('in 5 seconds');
    });
});
