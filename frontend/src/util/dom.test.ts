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

import { DCE, es } from './dom';

describe('DCE', () => {
    it('sets properties and styles', () => {
        const input = DCE('input', {
            type: 'hidden',
            name: 'id',
            value: 12,
            style: { display: 'none' },
        });

        expect(input.type).toBe('hidden');
        expect(input.name).toBe('id');
        expect(input.value).toBe('12');
        expect(input.style.display).toBe('none');
    });

    it('appends nodes and sets text as HTML, skipping false and undefined', () => {
        const hint = DCE('span', { className: 'hint' }, ['<b>x</b>']);
        const row = DCE('div', { className: 'form-row' }, [hint, false, undefined]);

        expect(row.className).toBe('form-row');
        expect(row.children).toHaveLength(1);
        expect(hint.innerHTML).toBe('<b>x</b>');
    });

    it('lets the last text replace the content', () => {
        const label = DCE('label', {}, ['first', 2]);

        expect(label.innerHTML).toBe('2');
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
