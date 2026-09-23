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

import { fetch_status_label, format_fetch_timestamp } from './fetch-status';

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('format_fetch_timestamp', () => {
    it('shows the empty label without a timestamp', () => {
        expect(format_fetch_timestamp(null, 'Never')).toBe('Never');
        expect(format_fetch_timestamp('', 'Never')).toBe('Never');
        expect(format_fetch_timestamp(undefined, 'Never')).toBe('Never');
    });

    it('shows a timestamp in the reader locale', () => {
        const value = '2026-09-23T10:15:00+00:00';

        expect(format_fetch_timestamp(value, 'Never')).toBe(
            new Date(value).toLocaleString(),
        );
    });

    it('keeps a value it cannot read as a date', () => {
        expect(format_fetch_timestamp('soon', 'Never')).toBe('soon');
    });
});

describe('fetch_status_label', () => {
    it('translates the known statuses', () => {
        vi.stubGlobal('gettext_msg', { running: 'trwa', failed: 'błąd' });

        expect(fetch_status_label({ status: 'running' })).toBe('trwa');
        expect(fetch_status_label({ status: 'failed' })).toBe('błąd');
        expect(fetch_status_label({ status: 'queued' })).toBe('queued');
        expect(fetch_status_label({ status: 'succeeded' })).toBe('succeeded');
    });

    it('is idle without a status', () => {
        expect(fetch_status_label(null)).toBe('idle');
        expect(fetch_status_label({ status: '' })).toBe('idle');
    });

    it('shows an unknown status as it is', () => {
        expect(fetch_status_label({ status: 'paused' })).toBe('paused');
    });
});
