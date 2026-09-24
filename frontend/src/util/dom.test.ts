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

import { MDOM, es, h } from './dom';

describe('h', () => {
    it('sets properties and merges the style', () => {
        const input = h('input', {
            type: 'hidden',
            name: 'id',
            value: '12',
            style: { display: 'none' },
        });

        expect(input.type).toBe('hidden');
        expect(input.name).toBe('id');
        expect(input.value).toBe('12');
        expect(input.style.display).toBe('none');
    });

    it('appends strings as text, skipping false, null and undefined', () => {
        const hint = h('span', { className: 'hint' }, ['<b>x</b>']);
        const row = h('div', null, [hint, ' ', 3, false, null, undefined]);

        expect(hint.innerHTML).toBe('&lt;b&gt;x&lt;/b&gt;');
        expect(row.childNodes).toHaveLength(3);
        expect(row.textContent).toBe('<b>x</b> 3');
    });
});

describe('MDOM', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('centres an element in the scrolled viewport', () => {
        vi.stubGlobal('innerWidth', 1000);
        vi.stubGlobal('innerHeight', 600);
        vi.stubGlobal('scrollY', 250);
        const box = document.createElement('div');

        MDOM.center(box, 400, 200);

        expect(box.style.left).toBe('300px');
        expect(box.style.top).toBe('450px');
    });

    it('keeps a box larger than the viewport on it', () => {
        vi.stubGlobal('innerWidth', 300);
        vi.stubGlobal('innerHeight', 200);
        vi.stubGlobal('scrollY', 0);
        const box = document.createElement('div');

        MDOM.center(box, 400, 500);

        expect(box.style.left).toBe('0px');
        expect(box.style.top).toBe('1px');
    });

    it('places a popup in the middle of this window', () => {
        vi.stubGlobal('screenX', 100);
        vi.stubGlobal('screenY', 50);
        vi.stubGlobal('outerWidth', 1200);
        vi.stubGlobal('outerHeight', 900);

        expect(MDOM.get_win_center(800, 480)).toEqual({
            width: 800,
            height: 480,
            left: 300,
            top: 218,
        });
    });
});

describe('es', () => {
    afterEach(() => {
        delete (window as { gls?: unknown }).gls;
    });

    it('creates the namespace on the way', () => {
        const run = vi.fn();

        es('gls.run_fetch_service', run);

        expect(window.gls?.run_fetch_service).toBe(run);
    });

    it('keeps what the namespace holds', () => {
        const unhide = vi.fn();
        const run = vi.fn();

        es('gls.unhide_entry', unhide);
        es('gls.run_fetch_service', run);

        expect(window.gls).toEqual({ unhide_entry: unhide, run_fetch_service: run });
    });
});
