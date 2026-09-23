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

import { is_quill_empty } from './composer';

describe('is_quill_empty', () => {
    it('is empty with only markup and whitespace', () => {
        expect(is_quill_empty('<div><br></div>')).toBe(true);
        expect(is_quill_empty('<div>  </div>\n<p></p>')).toBe(true);
    });

    it('is not empty with text', () => {
        expect(is_quill_empty('<div>Hello</div>')).toBe(false);
    });

    it('is not empty with a picture and no text', () => {
        expect(is_quill_empty('<div><img src="a.png"></div>')).toBe(false);
    });
});
