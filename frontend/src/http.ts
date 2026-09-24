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

import { hide_spinner } from './ui/spinner';
import { read_cookie } from './util/cookies';
import { _ } from './util/i18n';

/** Form fields of a request; null and undefined are sent empty. */
export type Params =
    | Record<string, string | number | boolean | null | undefined>
    | [string, string][];

/** A request's answer: its body, or the response that failed, null if none came. */
export type Result<T> =
    | { ok: true; data: T }
    | { ok: false; response: Response | null };

interface RequestOptions {
    method?: 'GET' | 'POST';
    params?: Params | undefined;
    fresh?: boolean;
}

/** Tells the reader a request failed; what every request does by default. */
function report_error(): void {
    alert(_('Communication Error. Try again.'));
    hide_spinner();
}

function encode(params: Params): URLSearchParams {
    const entries = Array.isArray(params) ? params : Object.entries(params);
    const body = new URLSearchParams();
    for (const [name, value] of entries) {
        body.append(name, value === null || value === undefined ? '' : String(value));
    }
    return body;
}

/**
 * Sends a request as the page's XMLHttpRequests did: form-encoded, with
 * X-Requested-With, and with Django's CSRF token when it changes state.
 */
async function request(
    url: string,
    options: RequestOptions,
): Promise<Result<Response>> {
    const method = options.method || 'GET';
    const headers = new Headers({ 'X-Requested-With': 'XMLHttpRequest' });
    const init: RequestInit = { method, headers, credentials: 'same-origin' };
    if (options.fresh) {
        init.cache = 'no-store';
    }
    if (method === 'GET') {
        if (options.params) {
            url += (url.includes('?') ? '&' : '?') + encode(options.params).toString();
        }
    } else {
        init.body = encode(options.params || {});
        const csrftoken = read_cookie('csrftoken');
        if (csrftoken) {
            headers.set('X-CSRFToken', csrftoken);
        }
    }
    return send(url, init);
}

/** Fetches; a network error or an HTTP error status is a failed result. */
async function send(url: string, init: RequestInit): Promise<Result<Response>> {
    let response: Response;
    try {
        response = await fetch(url, init);
    } catch {
        return { ok: false, response: null };
    }
    if (!response.ok) {
        return { ok: false, response };
    }
    return { ok: true, data: response };
}

async function read_json<T>(result: Result<Response>): Promise<Result<T>> {
    if (!result.ok) {
        return result;
    }
    try {
        return { ok: true, data: (await result.data.json()) as T };
    } catch {
        return { ok: false, response: result.data };
    }
}

/** The body, or null after telling the reader the request failed. */
function or_report<T>(result: Result<T>): T | null {
    if (!result.ok) {
        report_error();
        return null;
    }
    return result.data;
}

/** POSTs `params` and resolves to the HTML the server answers with. */
export async function post_text(url: string, params: Params): Promise<string | null> {
    const result = await request(url, { method: 'POST', params });
    return result.ok ? result.data.text() : or_report(result);
}

/** POSTs `params` and resolves to the JSON answer, leaving failures to the caller. */
export async function try_post_json<T>(
    url: string,
    params: Params,
): Promise<Result<T>> {
    return read_json<T>(await request(url, { method: 'POST', params }));
}

/** POSTs `params` and resolves to the JSON the server answers with. */
export async function post_json<T>(url: string, params: Params): Promise<T | null> {
    return or_report(await try_post_json<T>(url, params));
}

/** GETs JSON; `fresh` bypasses the browser cache. */
export async function get_json<T>(url: string, fresh = false): Promise<T | null> {
    return or_report(await read_json<T>(await request(url, { fresh })));
}
