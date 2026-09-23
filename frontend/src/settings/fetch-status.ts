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
import { hide_spinner, show_spinner } from '../ui/spinner';
import { _ } from '../util/i18n';

const fetch_status_poll_interval_ms = 3000;

/** The polling of settings/api/fetch-status while a fetch is active. */
export const fetch_status = {
    poll_timer: null as number | null,
    request_in_flight: false,
};

function set_run_fetch_busy(serviceId: number | string, busy: boolean): void {
    const btn = $('.run-fetch[data-service-id="' + serviceId + '"]');
    if (!btn.length) {
        return;
    }
    btn.attr('aria-busy', busy ? 'true' : 'false');
    if (busy) {
        btn.addClass('busy');
    } else {
        btn.removeClass('busy');
    }
}

function has_active_fetch_statuses(): boolean {
    return (
        $(
            '.fetch-status[data-status="queued"], ' +
                '.fetch-status[data-status="running"]',
        ).length > 0
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
    const diagnostics = $('#fetch-diagnostics-' + serviceId);
    const statusEl = $('#fetch-status-' + serviceId);
    if (!diagnostics.length) {
        return {
            service_id: Number(serviceId),
            status: statusEl.attr('data-status') || 'idle',
        };
    }
    return {
        service_id: Number(serviceId),
        status:
            diagnostics.attr('data-status') || statusEl.attr('data-status') || 'idle',
        requested_at: diagnostics.attr('data-requested-at') || null,
        started_at: diagnostics.attr('data-started-at') || null,
        finished_at: diagnostics.attr('data-finished-at') || null,
        last_succeeded_at: diagnostics.attr('data-last-succeeded-at') || null,
        last_failed_at: diagnostics.attr('data-last-failed-at') || null,
        next_fetch_at: diagnostics.attr('data-next-fetch-at') || null,
        last_result: diagnostics.attr('data-last-result') || '',
        last_error: diagnostics.attr('data-last-error') || '',
        failure_note: diagnostics.attr('data-failure-note') || '',
    };
}

function store_fetch_diagnostics_state(state: FetchState): void {
    if (!state || !state.service_id) {
        return;
    }
    const diagnostics = $('#fetch-diagnostics-' + state.service_id);
    if (!diagnostics.length) {
        return;
    }
    diagnostics.attr('data-status', state.status || '');
    diagnostics.attr('data-requested-at', state.requested_at || '');
    diagnostics.attr('data-started-at', state.started_at || '');
    diagnostics.attr('data-finished-at', state.finished_at || '');
    diagnostics.attr('data-last-succeeded-at', state.last_succeeded_at || '');
    diagnostics.attr('data-last-failed-at', state.last_failed_at || '');
    diagnostics.attr('data-next-fetch-at', state.next_fetch_at || '');
    diagnostics.attr('data-last-result', state.last_result || '');
    diagnostics.attr('data-last-error', state.last_error || '');
    diagnostics.attr('data-failure-note', state.failure_note || '');
}

function render_fetch_diagnostics(state: FetchState): void {
    if (!state || !state.service_id) {
        return;
    }
    store_fetch_diagnostics_state(state);
    $('#fetch-result-' + state.service_id).text(state.last_result || '—');
    $('#fetch-summary-last-succeeded-' + state.service_id).text(
        format_fetch_timestamp(state.last_succeeded_at, _('Never')),
    );
    $('#fetch-summary-finished-' + state.service_id).text(
        format_fetch_timestamp(state.finished_at, _('No completed runs')),
    );
    const retryNote = $('#fetch-retry-note-' + state.service_id).detach();
    $('#fetch-summary-next-fetch-' + state.service_id)
        .text(format_fetch_timestamp(state.next_fetch_at, _('Not scheduled')))
        .append(retryNote.text(state.failure_note || ''));

    const errorWrap = $('#fetch-error-' + state.service_id);
    const errorText = $('#fetch-error-text-' + state.service_id);
    if (state.last_error) {
        errorText.text(state.last_error);
        errorWrap.removeClass('empty');
    } else {
        errorText.text('—');
        errorWrap.addClass('empty');
    }
}

function schedule_fetch_status_poll(delayMs: number): void {
    if (fetch_status.poll_timer !== null || fetch_status.request_in_flight) {
        return;
    }
    fetch_status.poll_timer = window.setTimeout(function () {
        fetch_status.poll_timer = null;
        refresh_fetch_status();
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
            refresh_fetch_status();
        }
        return;
    }
    schedule_fetch_status_poll(fetch_status_poll_interval_ms);
}

export function initialize_fetch_diagnostics(): void {
    $('[id^="fetch-diagnostics-"]').each(function () {
        const serviceId = $(this).attr('data-service-id');
        if (!serviceId) {
            return;
        }
        render_fetch_diagnostics(get_fetch_diagnostics_state(serviceId));
    });
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

/** Shows a service's new state, merged over what the page shows now. */
export function update_fetch_status(state: FetchState): void {
    if (!state || !state.service_id) {
        return;
    }
    state = $.extend({}, get_fetch_diagnostics_state(state.service_id), state);
    const el = $('#fetch-status-' + state.service_id);
    if (!el.length) {
        return;
    }
    el.text(fetch_status_label(state));
    el.attr('data-status', state.status || '');
    el.attr('title', state.last_error || state.last_result || '');
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

function refresh_fetch_status(): void {
    if (fetch_status.request_in_flight) {
        return;
    }
    fetch_status.request_in_flight = true;
    $.ajax({
        url: config.baseurl + 'settings/api/fetch-status',
        dataType: 'json',
        cache: false,
        success: function (json: FetchStatusResponse) {
            if (!json.services) {
                return;
            }
            $.each(json.services, function (_serviceId, state) {
                update_fetch_status(state);
            });
        },
    }).always(function () {
        fetch_status.request_in_flight = false;
        if (has_active_fetch_statuses()) {
            schedule_fetch_status_poll(fetch_status_poll_interval_ms);
        } else {
            stop_fetch_status_polling();
        }
    });
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
    $.ajax({
        url: config.baseurl + 'settings/api/fetch-now',
        data: $.param({ id: serviceId }),
        dataType: 'json',
        type: 'POST',
        success: function (json: FetchNowResponse) {
            if (json.state) {
                update_fetch_status(json.state);
            }
            refresh_fetch_status();
        },
        error: function (xhr) {
            const body = xhr.responseJSON as FetchNowError | undefined;
            const message =
                body && body.error ? body.error : _('Unable to queue fetch.');
            update_fetch_status({
                service_id: Number(serviceId),
                status: 'failed',
                last_result: message,
                last_error: message,
            });
        },
        complete: function () {
            hide_spinner();
            maybe_start_fetch_status_polling(false);
        },
    });
    return false;
}
