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

import { afterEach, describe, expect, it, vi } from 'vitest';

import { read_cookie, write_cookie } from './cookies';

afterEach(() => {
    for (const name of ['gls-theme', 'gls-reblogs', 'other']) {
        document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    }
    vi.useRealTimers();
});

describe('read_cookie', () => {
    it('finds a cookie among others', () => {
        document.cookie = 'other=1; path=/';
        document.cookie = 'gls-theme=dark; path=/';

        expect(read_cookie('gls-theme')).toBe('dark');
        expect(read_cookie('other')).toBe('1');
    });

    it('does not take a cookie whose name only ends with the name', () => {
        document.cookie = 'other-gls-theme=dark; path=/';

        expect(read_cookie('gls-theme')).toBeNull();
    });

    it('is null for a missing cookie', () => {
        expect(read_cookie('gls-reblogs')).toBeNull();
    });
});

describe('write_cookie', () => {
    it('stores a cookie that read_cookie reads back', () => {
        write_cookie('gls-reblogs', '1', 365, '/');

        expect(read_cookie('gls-reblogs')).toBe('1');
    });

    it('sets the expiry and path', () => {
        vi.useFakeTimers({ now: new Date('2026-01-01T00:00:00Z'), toFake: ['Date'] });
        const cookie = vi.spyOn(document, 'cookie', 'set');

        write_cookie('gls-theme', 'dark', 2, '/stream/');

        expect(cookie).toHaveBeenCalledWith(
            'gls-theme=dark; expires=Sat, 03 Jan 2026 00:00:00 GMT; path=/stream/',
        );
    });
});
