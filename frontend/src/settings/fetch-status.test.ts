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

import {
    fetch_status,
    fetch_status_label,
    format_fetch_timestamp,
    update_fetch_status,
} from './fetch-status';

afterEach(() => {
    vi.unstubAllGlobals();
    if (fetch_status.poll_timer !== null) {
        window.clearTimeout(fetch_status.poll_timer);
        fetch_status.poll_timer = null;
    }
    document.body.innerHTML = '';
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

// The rows of one service on the status page, as status.html renders them.
function status_rows(): void {
    document.body.innerHTML = `
        <table>
        <tr id="fetch-diagnostics-7" data-service-id="7" data-status="idle"
            data-last-result="Imported 3" data-failure-note="">
          <td><a href="#" class="run-fetch" data-service-id="7">Run now</a>
            <span class="fetch-status" id="fetch-status-7" data-status="idle">idle</span>
            <span id="fetch-result-7">Imported 3</span></td>
          <td id="fetch-summary-last-succeeded-7">Never</td>
          <td id="fetch-summary-finished-7">No completed runs</td>
          <td id="fetch-summary-next-fetch-7">Not scheduled
            <span class="retry-note" id="fetch-retry-note-7"></span></td>
          <td id="fetch-error-7" class="error-text empty">
            <span id="fetch-error-text-7">—</span></td>
        </tr>
        </table>`;
}

function text(id: string): string {
    return (document.getElementById(id) as HTMLElement).textContent.trim();
}

describe('update_fetch_status', () => {
    it('shows a failure with its error, and keeps the retry note', () => {
        status_rows();

        update_fetch_status({
            service_id: 7,
            status: 'failed',
            last_error: 'Timed out',
            failure_note: 'Retrying soon',
        });

        const status = document.getElementById('fetch-status-7') as HTMLElement;
        expect(status.textContent).toBe('failed');
        expect(status.getAttribute('data-status')).toBe('failed');
        expect(status.title).toBe('Timed out');
        expect(text('fetch-result-7')).toBe('Imported 3');
        expect(text('fetch-error-text-7')).toBe('Timed out');
        expect(document.getElementById('fetch-error-7')?.classList).not.toContain(
            'empty',
        );
        expect(text('fetch-summary-next-fetch-7')).toBe('Not scheduledRetrying soon');
        expect(text('fetch-retry-note-7')).toBe('Retrying soon');
        const row = document.getElementById('fetch-diagnostics-7') as HTMLElement;
        expect(row.getAttribute('data-last-error')).toBe('Timed out');
    });

    it('marks the run button busy while a fetch is active, and polls', () => {
        status_rows();

        update_fetch_status({ service_id: 7, status: 'running' });

        const run = document.querySelector('.run-fetch') as HTMLElement;
        expect(run.getAttribute('aria-busy')).toBe('true');
        expect(run.classList).toContain('busy');
        expect(fetch_status.poll_timer).not.toBeNull();

        update_fetch_status({ service_id: 7, status: 'succeeded' });

        expect(run.getAttribute('aria-busy')).toBe('false');
        expect(fetch_status.poll_timer).toBeNull();
    });
});
