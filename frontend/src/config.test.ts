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

import { afterEach, describe, expect, it } from 'vitest';

import { config, load_config, stream_data } from './config';

const DEFAULTS = { ...config };

function json_script(id: string, value: unknown): void {
    const script = document.createElement('script');
    script.type = 'application/json';
    script.id = id;
    script.textContent = JSON.stringify(value);
    document.body.append(script);
}

afterEach(() => {
    Object.assign(config, DEFAULTS);
    document.body.innerHTML = '';
});

describe('load_config', () => {
    it('reads #gls-config', () => {
        const page = {
            baseurl: '/gls/',
            maps_engine: 'google',
            themes: ['default', 'dark'],
            lang: 'pl',
            messages: { Undo: 'Cofnij' },
        };
        json_script('gls-config', page);

        load_config();

        expect(config).toEqual(page);
    });

    it('keeps the defaults on a page without it', () => {
        load_config();

        expect(config).toEqual({
            baseurl: '/',
            maps_engine: '',
            themes: [],
            lang: '',
            messages: {},
        });
    });
});

describe('stream_data', () => {
    it('reads #gls-stream-data', () => {
        const data = {
            ctx: 'public',
            year_now: 2026,
            view_date: '2026/09',
            archives: ['2026/09'],
            month_names: ['Jan'],
        };
        json_script('gls-stream-data', data);

        expect(stream_data()).toEqual(data);
    });

    it('is null on a page that is not a stream', () => {
        expect(stream_data()).toBeNull();
    });
});
