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

import { config } from '../config';
import { _, gettext } from './i18n';

afterEach(() => {
    config.messages = {};
});

describe('gettext', () => {
    it('translates a message the page config lists', () => {
        config.messages = { Undo: 'Cofnij' };

        expect(gettext('Undo')).toBe('Cofnij');
        expect(_('Undo')).toBe('Cofnij');
    });

    it('keeps a message without a translation', () => {
        config.messages = { Undo: '' };

        expect(gettext('Undo')).toBe('Undo');
        expect(gettext('Loading...')).toBe('Loading...');
    });

    it('keeps every message on a page without a config', () => {
        expect(gettext('Undo')).toBe('Undo');
    });
});
