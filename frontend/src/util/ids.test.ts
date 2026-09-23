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

import { parse_id } from './ids';

describe('parse_id', () => {
    it('splits at the first dash', () => {
        expect(parse_id('entry-12')).toEqual(['entry', '12']);
        expect(parse_id('youtube-a-b_c')).toEqual(['youtube', 'a-b_c']);
    });

    it('keeps an id without a dash whole', () => {
        expect(parse_id('stream')).toEqual(['stream']);
    });

    it('gives an empty part around a leading or trailing dash', () => {
        expect(parse_id('-12')).toEqual(['', '12']);
        expect(parse_id('entry-')).toEqual(['entry', '']);
    });
});
