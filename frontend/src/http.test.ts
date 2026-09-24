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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { get_json, post_json, post_text, try_post_json } from './http';

const fetch_mock = vi.fn<typeof fetch>();
const alert_mock = vi.fn();

function sent(): {
    url: string;
    init: RequestInit;
    headers: Headers;
    body: string | undefined;
} {
    const [url, init] = fetch_mock.mock.calls[0] as [string, RequestInit];
    const body = init.body as URLSearchParams | undefined;
    return { url, init, headers: init.headers as Headers, body: body?.toString() };
}

beforeEach(() => {
    vi.stubGlobal('fetch', fetch_mock);
    vi.stubGlobal('alert', alert_mock);
    document.cookie = 'csrftoken=token123; path=/';
});

afterEach(() => {
    vi.unstubAllGlobals();
    fetch_mock.mockReset();
    alert_mock.mockReset();
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.body.innerHTML = '';
});

describe('post_text', () => {
    it('sends form fields with the CSRF token', async () => {
        fetch_mock.mockResolvedValue(new Response('<p>ok</p>'));

        const html = await post_text('/api/share', {
            content: 'a b&c',
            draft: 0,
            sid: undefined,
            none: null,
        });

        expect(html).toBe('<p>ok</p>');
        const { url, init, headers, body } = sent();
        expect(url).toBe('/api/share');
        expect(init.method).toBe('POST');
        expect(body).toBe('content=a+b%26c&draft=0&sid=&none=');
        expect(headers.get('X-CSRFToken')).toBe('token123');
        expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest');
    });

    it('keeps the order and repeats of listed fields', async () => {
        fetch_mock.mockResolvedValue(new Response(''));

        await post_text('/form', [
            ['tag', 'a'],
            ['tag', 'b'],
        ]);

        expect(sent().body).toBe('tag=a&tag=b');
    });

    it('alerts, clears the spinner and resolves to null on an error', async () => {
        document.body.innerHTML = '<span id="spinner"></span>';
        fetch_mock.mockResolvedValue(new Response('boom', { status: 500 }));

        expect(await post_text('/api/hide', { entry: 1 })).toBeNull();
        expect(alert_mock).toHaveBeenCalledWith('Communication Error. Try again.');
        expect(document.getElementById('spinner')).toBeNull();
    });

    it('treats a network failure as an error', async () => {
        fetch_mock.mockRejectedValue(new TypeError('offline'));

        expect(await post_text('/api/hide', { entry: 1 })).toBeNull();
        expect(alert_mock).toHaveBeenCalledOnce();
    });
});

describe('try_post_json', () => {
    it('hands a failed response to the caller without alerting', async () => {
        const response = Response.json({ error: 'Busy' }, { status: 400 });
        fetch_mock.mockResolvedValue(response);

        expect(await try_post_json('/settings/api/fetch-now', { id: 3 })).toEqual({
            ok: false,
            response,
        });
        expect(alert_mock).not.toHaveBeenCalled();
    });

    it('resolves to the JSON body', async () => {
        fetch_mock.mockResolvedValue(Response.json({ state: null }));

        expect(await try_post_json('/settings/api/fetch-now', { id: 3 })).toEqual({
            ok: true,
            data: { state: null },
        });
    });
});

describe('post_json', () => {
    it('reports a body that is not JSON', async () => {
        fetch_mock.mockResolvedValue(new Response('<html>'));

        expect(await post_json('/settings/api/service', {})).toBeNull();
        expect(alert_mock).toHaveBeenCalledOnce();
    });
});

describe('get_json', () => {
    it('sends no token and can skip the cache', async () => {
        fetch_mock.mockResolvedValue(Response.json({ services: {} }));

        expect(await get_json('/settings/api/fetch-status', true)).toEqual({
            services: {},
        });
        const { init, headers } = sent();
        expect(init.method).toBe('GET');
        expect(init.body).toBeUndefined();
        expect(init.cache).toBe('no-store');
        expect(headers.has('X-CSRFToken')).toBe(false);
    });
});
