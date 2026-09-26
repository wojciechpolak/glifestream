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

import { config } from '../config';
import {
    fetch_status,
    fetch_status_label,
    fetch_timestamp,
    refresh_relative_times,
    run_fetch_service,
    update_fetch_status,
} from './fetch-status';

afterEach(() => {
    vi.unstubAllGlobals();
    config.messages = {};
    fetch_status.refused_after.clear();
    if (fetch_status.poll_timer !== null) {
        window.clearTimeout(fetch_status.poll_timer);
        fetch_status.poll_timer = null;
    }
    document.body.innerHTML = '';
    config.lang = '';
});

describe('fetch_timestamp', () => {
    const now = new Date('2026-09-23T10:20:00+00:00');

    it('shows the empty label without a timestamp', () => {
        expect(fetch_timestamp(null, 'Never', true, now)).toBe('Never');
        expect(fetch_timestamp('', 'Never', true, now)).toBe('Never');
        expect(fetch_timestamp(undefined, 'Never', true, now)).toBe('Never');
    });

    it('reads relative to now, with the absolute time in its tooltip', () => {
        config.lang = 'en';
        const value = '2026-09-23T10:15:00+00:00';

        const time = fetch_timestamp(value, 'Never', true, now) as HTMLTimeElement;

        expect(time.tagName).toBe('TIME');
        expect(time.className).toBe('fetch-time');
        expect(time.dateTime).toBe(value);
        expect(time.textContent).toBe('5 minutes ago');
        expect(time.dataset['tooltip']).toBe(new Date(value).toLocaleString('en'));
        expect(time.hasAttribute('data-past')).toBe(true);
        expect(time.tabIndex).toBe(0);
        expect(time.title).toBe('');
    });

    it('reads in the page language', () => {
        config.lang = 'pl';

        const time = fetch_timestamp(
            '2026-09-23T10:23:00+00:00',
            'Nigdy',
            false,
            now,
        ) as HTMLTimeElement;

        expect(time.textContent).toBe('za 3 minuty');
        expect(time.hasAttribute('data-past')).toBe(false);
    });

    it('keeps a value it cannot read as a date', () => {
        expect(fetch_timestamp('soon', 'Never', true, now)).toBe('soon');
    });
});

describe('refresh_relative_times', () => {
    it('brings the relative times up to now', () => {
        config.lang = 'en';
        const cell = document.createElement('td');
        document.body.append(cell);
        cell.append(
            fetch_timestamp(
                '2026-09-23T10:15:00+00:00',
                'Never',
                true,
                new Date('2026-09-23T10:15:10+00:00'),
            ),
        );
        expect(cell.textContent).toBe('10 seconds ago');

        refresh_relative_times(new Date('2026-09-23T10:16:05+00:00'));

        expect(cell.textContent).toBe('1 minute ago');
    });
});

describe('fetch_status_label', () => {
    it('translates the known statuses', () => {
        config.messages = { running: 'trwa', failed: 'błąd' };

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
    it('shows the import times as relative <time> elements', () => {
        status_rows();
        const value = '2026-03-01T10:00:00+00:00';

        update_fetch_status({
            service_id: 7,
            status: 'succeeded',
            last_succeeded_at: value,
            next_fetch_at: value,
            failure_note: 'Retrying soon',
        });

        const cell = document.getElementById('fetch-summary-last-succeeded-7');
        const time = cell?.querySelector('time.fetch-time') as HTMLTimeElement;
        expect(time.dateTime).toBe(value);
        expect(time.dataset['tooltip']).toBe(new Date(value).toLocaleString());
        expect(time.textContent).toMatch(/ ago$/);
        expect(text('fetch-summary-finished-7')).toBe('No completed runs');
        const next = document.getElementById('fetch-summary-next-fetch-7');
        expect(next?.querySelector('time.fetch-time')?.nextElementSibling?.id).toBe(
            'fetch-retry-note-7',
        );
        expect(text('fetch-retry-note-7')).toBe('Retrying soon');
    });

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

describe('run_fetch_service', () => {
    it('keeps a refused fetch failed when an earlier status reply comes after', async () => {
        status_rows();
        const status_reply = Promise.withResolvers<Response>();
        vi.stubGlobal(
            'fetch',
            vi.fn<typeof fetch>(async (url) =>
                url === config.baseurl + 'settings/api/fetch-now'
                    ? Response.json(
                          { error: 'This service cannot be fetched.' },
                          { status: 400 },
                      )
                    : status_reply.promise,
            ),
        );

        run_fetch_service(document.querySelector('.run-fetch') as HTMLElement);
        await vi.waitFor(() => expect(text('fetch-status-7')).toBe('failed'));
        status_reply.resolve(
            Response.json({ services: { '7': { service_id: 7, status: 'idle' } } }),
        );
        await vi.waitFor(() => expect(fetch_status.request_in_flight).toBe(false));

        expect(text('fetch-status-7')).toBe('failed');
        expect(text('fetch-error-text-7')).toBe('This service cannot be fetched.');
    });
});
