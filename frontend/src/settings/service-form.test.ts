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

import type { ServiceForm } from '../api-types';
import { get_service_form, hide_settings_form } from './service-form';

const fetch_mock = vi.fn<typeof fetch>();
const open_mock = vi.fn();

/** new Option(), which happy-dom lacks. */
function option(
    text: string,
    value: string,
    default_selected: boolean,
    selected: boolean,
): HTMLOptionElement {
    const o = document.createElement('option');
    o.text = text;
    o.value = value;
    o.defaultSelected = default_selected;
    o.selected = selected;
    return o;
}

function form_data(overrides: Partial<ServiceForm> = {}): ServiceForm {
    return {
        id: null,
        api: 'feed',
        name: 'Feed',
        action: '/settings/api/service',
        method: 'get',
        save: 'Save',
        cancel: 'Cancel',
        fields: [
            { type: 'text', name: 'url', label: 'URL', hint: 'A feed' },
            {
                type: 'select',
                name: 'display',
                label: 'Display',
                value: 'both',
                options: [
                    ['content', 'Content'],
                    ['both', 'Both'],
                ],
            },
            {
                type: 'checkbox',
                name: 'public',
                label: 'Public',
                checked: true,
                miss: true,
            },
            {
                type: 'text',
                name: 'limit',
                label: 'Limit',
                value: 5,
                deps: { display: 'content' },
            },
        ],
        ...overrides,
    };
}

function answer(data: ServiceForm): void {
    fetch_mock.mockResolvedValueOnce(Response.json(data));
}

function form(): HTMLFormElement {
    return document.getElementById('service-form') as HTMLFormElement;
}

function field(id: string): HTMLInputElement {
    return document.getElementById(id) as HTMLInputElement;
}

function select(id: string): HTMLSelectElement {
    return document.getElementById(id) as HTMLSelectElement;
}

beforeEach(() => {
    vi.stubGlobal('fetch', fetch_mock);
    vi.stubGlobal('alert', vi.fn());
    vi.stubGlobal('Option', option);
    vi.spyOn(window, 'open').mockImplementation(open_mock);
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList);
    document.body.innerHTML = `
        <ul id="edit-service"></ul>
        <div id="add-service"><a class="feed">Feed</a><span id="spinner"></span></div>`;
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    fetch_mock.mockReset();
    open_mock.mockReset();
    document.body.innerHTML = '';
});

describe('get_service_form', () => {
    it('asks for the form and shows it after its anchor', async () => {
        answer(form_data());

        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');

        const [url, init] = fetch_mock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/settings/api/service');
        expect((init.body as URLSearchParams).toString()).toBe('method=get&api=feed');
        expect(document.getElementById('spinner')).toBeNull();
        expect(document.getElementById('add-service')?.nextElementSibling).toBe(form());
        expect(form().style.display).not.toBe('none');
        expect(form().getAttribute('action')).toBe('/settings/api/service');
        expect(document.activeElement).toBe(field('url'));
    });

    it('renders every kind of field', async () => {
        answer(form_data());

        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');

        expect(field('url').value).toBe('');
        expect(field('url').size).toBe(32);
        expect(form().querySelector('.hint')?.textContent).toBe('A feed');
        expect(select('display').value).toBe('both');
        expect(field('public').checked).toBe(true);
        expect(form().querySelector('label[for=public]')?.className).toBe('missing');
        expect(form().querySelector<HTMLInputElement>('[name=api]')?.value).toBe(
            'feed',
        );
        expect(form().querySelector('[name=id]')).toBeNull();
        expect(form().querySelector('#save')).not.toBeNull();
        expect(form().querySelector('a[target=admin]')).toBeNull();
    });

    it('shows a dependent row only while its field has the value', async () => {
        answer(form_data());

        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');

        const row = field('limit').parentElement as HTMLElement;
        expect(row.style.display).toBe('none');
        expect(field('limit').disabled).toBe(true);

        const display = select('display');
        display.value = 'content';
        display.dispatchEvent(new Event('change'));

        expect(row.style.display).toBe('block');
        expect(field('limit').disabled).toBe(false);
    });

    it('opens the OAuth pages from their links', async () => {
        answer(
            form_data({
                id: 7,
                fields: [
                    {
                        type: 'link',
                        name: 'oauth_conf',
                        label: 'OAuth',
                        value: 'Configure',
                    },
                    {
                        type: 'link',
                        name: 'oauth2_conf',
                        label: 'OAuth 2',
                        value: 'Set up',
                    },
                    {
                        type: 'link',
                        name: 'other',
                        label: 'Other',
                        href: '/x',
                        value: 'Go',
                    },
                ],
            }),
        );

        await get_service_form({ method: 'get', id: '7' }, '#add-service');

        field('oauth_conf').click();
        field('oauth2_conf').click();
        field('other').dispatchEvent(new MouseEvent('click', { cancelable: true }));

        expect(field('oauth_conf').textContent).toBe('Configure');
        expect(open_mock.mock.calls.map((call) => call.slice(0, 2))).toEqual([
            ['oauth/7', 'oauth'],
            ['oauth2/7', 'oauth2'],
        ]);
        expect(field('other').getAttribute('href')).toBe('/x');
    });

    it('adds a saved service to the list and fetches a new one', async () => {
        answer(
            form_data({ id: 7, method: 'post', delete: 'Delete', need_import: true }),
        );
        fetch_mock.mockResolvedValueOnce(Response.json({}));

        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');

        const item = document.querySelector('#edit-service li');
        expect(item?.getAttribute('data-service-id')).toBe('7');
        expect(item?.querySelector('a#service-7')?.textContent).toBe('Feed');
        expect(form().querySelector<HTMLInputElement>('[name=id]')?.value).toBe('7');
        expect(form().querySelector('a[target=admin]')?.getAttribute('href')).toBe(
            '/admin/stream/service/7/delete/',
        );
        expect(fetch_mock.mock.calls[1]?.[0]).toBe('/settings/api/import');
    });

    it('replaces the list item of a service already listed', async () => {
        document.getElementById('edit-service')!.innerHTML =
            '<li><a id="service-7">Old</a></li>';
        answer(form_data({ id: 7, method: 'post', name: 'New' }));

        await get_service_form({ method: 'get', id: '7' }, '#add-service');

        const items = document.querySelectorAll('#edit-service li');
        expect(items).toHaveLength(1);
        expect(items[0]?.textContent).toBe('New');
    });

    it('shows nothing when the request fails', async () => {
        fetch_mock.mockResolvedValueOnce(new Response('', { status: 500 }));

        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');

        expect(form()).toBeNull();
    });
});

describe('the service form', () => {
    it('submits its fields through the API and shows the answer', async () => {
        answer(form_data());
        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');
        field('url').value = 'https://example.org/feed';
        answer(form_data({ id: 7, method: 'post' }));

        form().dispatchEvent(new SubmitEvent('submit', { cancelable: true }));
        await vi.waitFor(() => expect(fetch_mock).toHaveBeenCalledTimes(2));
        await vi.waitFor(() =>
            expect(form().querySelector('[name=id]')).not.toBeNull(),
        );

        const body = fetch_mock.mock.calls[1]?.[1]?.body as URLSearchParams;
        expect(body.get('url')).toBe('https://example.org/feed');
        expect(body.get('api')).toBe('feed');
        expect(body.get('method')).toBe('post');
        expect(document.querySelector('#edit-service a#service-7')).not.toBeNull();
    });

    it('hides when cancelled', async () => {
        answer(form_data());
        await get_service_form({ method: 'get', api: 'feed' }, '#add-service');

        field('cancel').click();

        await vi.waitFor(() => expect(form().style.display).toBe('none'));
    });
});

describe('hide_settings_form', () => {
    it('does nothing without a form', () => {
        expect(() => hide_settings_form()).not.toThrow();
    });
});
