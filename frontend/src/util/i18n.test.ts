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

import { _, gettext } from './i18n';

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('gettext', () => {
    it('translates a message i18n.html lists', () => {
        vi.stubGlobal('gettext_msg', { Undo: 'Cofnij' });

        expect(gettext('Undo')).toBe('Cofnij');
        expect(_('Undo')).toBe('Cofnij');
    });

    it('keeps a message without a translation', () => {
        vi.stubGlobal('gettext_msg', { Undo: '' });

        expect(gettext('Undo')).toBe('Undo');
        expect(gettext('Loading...')).toBe('Loading...');
    });

    it('keeps every message on a page without i18n.html', () => {
        expect(gettext('Undo')).toBe('Undo');
    });
});
