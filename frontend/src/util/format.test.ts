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

import { pad } from './format';

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
