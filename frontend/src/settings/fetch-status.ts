/*
 *  gLifestream Copyright (C) 2009-2026 Wojciech Polak
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

import type {
    FetchNowError,
    FetchNowResponse,
    FetchState,
    FetchStatusResponse,
} from '../api-types';
import { config } from '../config';
import { get_json, try_post_json } from '../http';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { _ } from '../util/i18n';

const fetch_status_poll_interval_ms = 3000;

/** The polling of settings/api/fetch-status while a fetch is active. */
export const fetch_status = {
    poll_timer: null as number | null,
    request_in_flight: false,
};

/** Where the page stores each diagnostics field. */
const DIAGNOSTICS = {
    'data-requested-at': 'requested_at',
    'data-started-at': 'started_at',
    'data-finished-at': 'finished_at',
    'data-last-succeeded-at': 'last_succeeded_at',
    'data-last-failed-at': 'last_failed_at',
    'data-next-fetch-at': 'next_fetch_at',
    'data-last-result': 'last_result',
    'data-last-error': 'last_error',
    'data-failure-note': 'failure_note',
} as const;

function by_id(id: string): HTMLElement | null {
    return document.getElementById(id);
}

function set_text(id: string, text: string): void {
    const el = by_id(id);
    if (el) {
        el.textContent = text;
    }
}

function set_run_fetch_busy(serviceId: number | string, busy: boolean): void {
    const buttons = document.querySelectorAll(
        '.run-fetch[data-service-id="' + serviceId + '"]',
    );
    for (const btn of buttons) {
        btn.setAttribute('aria-busy', busy ? 'true' : 'false');
        btn.classList.toggle('busy', busy);
    }
}

function has_active_fetch_statuses(): boolean {
    return !!document.querySelector(
        '.fetch-status[data-status="queued"], .fetch-status[data-status="running"]',
    );
}

function stop_fetch_status_polling(): void {
    if (fetch_status.poll_timer !== null) {
        window.clearTimeout(fetch_status.poll_timer);
        fetch_status.poll_timer = null;
    }
}

/** An ISO timestamp in the reader's locale, or `emptyLabel` without one. */
export function format_fetch_timestamp(
    value: string | null | undefined,
    emptyLabel: string,
): string {
    if (!value) {
        return emptyLabel;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString();
}

/** A service's state as the page shows it now, from its data attributes. */
function get_fetch_diagnostics_state(serviceId: number | string): FetchState {
    const diagnostics = by_id('fetch-diagnostics-' + serviceId);
    const shown = by_id('fetch-status-' + serviceId)?.getAttribute('data-status');
    if (!diagnostics) {
        return { service_id: Number(serviceId), status: shown || 'idle' };
    }
    const attr = (name: string): string => diagnostics.getAttribute(name) || '';
    return {
        service_id: Number(serviceId),
        status: attr('data-status') || shown || 'idle',
        requested_at: attr('data-requested-at') || null,
        started_at: attr('data-started-at') || null,
        finished_at: attr('data-finished-at') || null,
        last_succeeded_at: attr('data-last-succeeded-at') || null,
        last_failed_at: attr('data-last-failed-at') || null,
        next_fetch_at: attr('data-next-fetch-at') || null,
        last_result: attr('data-last-result'),
        last_error: attr('data-last-error'),
        failure_note: attr('data-failure-note'),
    };
}

function store_fetch_diagnostics_state(state: FetchState): void {
    const diagnostics = by_id('fetch-diagnostics-' + state.service_id);
    if (!diagnostics) {
        return;
    }
    diagnostics.setAttribute('data-status', state.status || '');
    for (const [attr, field] of Object.entries(DIAGNOSTICS)) {
        diagnostics.setAttribute(attr, state[field] || '');
    }
}

function render_fetch_diagnostics(state: FetchState): void {
    if (!state || !state.service_id) {
        return;
    }
    const id = state.service_id;
    store_fetch_diagnostics_state(state);
    set_text('fetch-result-' + id, state.last_result || '—');
    set_text(
        'fetch-summary-last-succeeded-' + id,
        format_fetch_timestamp(state.last_succeeded_at, _('Never')),
    );
    set_text(
        'fetch-summary-finished-' + id,
        format_fetch_timestamp(state.finished_at, _('No completed runs')),
    );
    // The retry note sits inside the next fetch time, which the text replaces.
    const retryNote = by_id('fetch-retry-note-' + id);
    retryNote?.remove();
    set_text(
        'fetch-summary-next-fetch-' + id,
        format_fetch_timestamp(state.next_fetch_at, _('Not scheduled')),
    );
    if (retryNote) {
        retryNote.textContent = state.failure_note || '';
        by_id('fetch-summary-next-fetch-' + id)?.append(retryNote);
    }

    set_text('fetch-error-text-' + id, state.last_error || '—');
    by_id('fetch-error-' + id)?.classList.toggle('empty', !state.last_error);
}

function schedule_fetch_status_poll(delayMs: number): void {
    if (fetch_status.poll_timer !== null || fetch_status.request_in_flight) {
        return;
    }
    fetch_status.poll_timer = window.setTimeout(function () {
        fetch_status.poll_timer = null;
        void refresh_fetch_status();
    }, delayMs);
}

/** Polls while a fetch is queued or running; `immediate` asks right away. */
export function maybe_start_fetch_status_polling(immediate: boolean): void {
    if (!has_active_fetch_statuses()) {
        stop_fetch_status_polling();
        return;
    }
    if (immediate) {
        stop_fetch_status_polling();
        if (!fetch_status.request_in_flight) {
            void refresh_fetch_status();
        }
        return;
    }
    schedule_fetch_status_poll(fetch_status_poll_interval_ms);
}

export function initialize_fetch_diagnostics(): void {
    for (const diagnostics of document.querySelectorAll('[id^="fetch-diagnostics-"]')) {
        const serviceId = diagnostics.getAttribute('data-service-id');
        if (serviceId) {
            render_fetch_diagnostics(get_fetch_diagnostics_state(serviceId));
        }
    }
}

/** The translated name of a fetch status. */
export function fetch_status_label(
    state: Partial<FetchState> | null | undefined,
): string {
    if (!state || !state.status) {
        return _('idle');
    }
    if (state.status === 'queued') {
        return _('queued');
    }
    if (state.status === 'running') {
        return _('running');
    }
    if (state.status === 'succeeded') {
        return _('succeeded');
    }
    if (state.status === 'failed') {
        return _('failed');
    }
    return state.status;
}

/** `update` over `base`, leaving out what `update` has undefined. */
function merge_state(base: FetchState, update: FetchState): FetchState {
    const merged: Record<string, unknown> = { ...base };
    for (const [key, value] of Object.entries(update)) {
        if (value !== undefined) {
            merged[key] = value;
        }
    }
    return merged as unknown as FetchState;
}

/** Shows a service's new state, merged over what the page shows now. */
export function update_fetch_status(state: FetchState): void {
    if (!state || !state.service_id) {
        return;
    }
    state = merge_state(get_fetch_diagnostics_state(state.service_id), state);
    const el = by_id('fetch-status-' + state.service_id);
    if (!el) {
        return;
    }
    el.textContent = fetch_status_label(state);
    el.setAttribute('data-status', state.status || '');
    el.setAttribute('title', state.last_error || state.last_result || '');
    render_fetch_diagnostics(state);
    set_run_fetch_busy(
        state.service_id,
        state.status === 'queued' || state.status === 'running',
    );
    if (has_active_fetch_statuses()) {
        maybe_start_fetch_status_polling(false);
    } else {
        stop_fetch_status_polling();
    }
}

async function refresh_fetch_status(): Promise<void> {
    if (fetch_status.request_in_flight) {
        return;
    }
    fetch_status.request_in_flight = true;
    const json = await get_json<FetchStatusResponse>(
        config.baseurl + 'settings/api/fetch-status',
        true,
    );
    if (json && json.services) {
        for (const state of Object.values(json.services)) {
            update_fetch_status(state);
        }
    }
    fetch_status.request_in_flight = false;
    if (has_active_fetch_statuses()) {
        schedule_fetch_status_poll(fetch_status_poll_interval_ms);
    } else {
        stop_fetch_status_polling();
    }
}

/** The message a refused fetch-now sent, or a general one. */
async function error_message(response: Response | null): Promise<string> {
    try {
        const body = (await response?.json()) as FetchNowError | undefined;
        if (body && body.error) {
            return body.error;
        }
    } catch {
        // Not JSON, or already read.
    }
    return _('Unable to queue fetch.');
}

async function queue_fetch(serviceId: string): Promise<void> {
    const result = await try_post_json<FetchNowResponse>(
        config.baseurl + 'settings/api/fetch-now',
        { id: serviceId },
    );
    if (result.ok) {
        if (result.data.state) {
            update_fetch_status(result.data.state);
        }
        void refresh_fetch_status();
    } else {
        const message = await error_message(result.response);
        update_fetch_status({
            service_id: Number(serviceId),
            status: 'failed',
            last_result: message,
            last_error: message,
        });
    }
    hide_spinner();
    maybe_start_fetch_status_polling(false);
}

/** "Run now" on the status page: queues a fetch and follows it. */
export function run_fetch_service(trigger: HTMLElement): boolean {
    const serviceId = trigger.getAttribute('data-service-id');
    if (!serviceId) {
        return false;
    }
    show_spinner(trigger);
    set_run_fetch_busy(serviceId, true);
    update_fetch_status({
        service_id: Number(serviceId),
        status: 'queued',
        last_result: _('Fetch queued.'),
    });
    maybe_start_fetch_status_polling(true);
    void queue_fetch(serviceId);
    return false;
}
