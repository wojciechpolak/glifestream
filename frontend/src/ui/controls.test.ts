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

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { init_page_controls } from './controls';

beforeAll(() => {
    init_page_controls();
});

afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = '';
});

describe('init_page_controls', () => {
    it('submits the form a data-submit-form link names', () => {
        document.body.innerHTML = `
            <form id="logout-form" method="post"></form>
            <a href="#" data-submit-form="logout-form"><span>Logout</span></a>`;
        const submit = vi
            .spyOn(HTMLFormElement.prototype, 'submit')
            .mockImplementation(() => {});
        const event = new MouseEvent('click', { bubbles: true, cancelable: true });

        document.querySelector('span')?.dispatchEvent(event);

        expect(submit).toHaveBeenCalledOnce();
        expect(submit.mock.contexts[0]).toBe(document.getElementById('logout-form'));
        expect(event.defaultPrevented).toBe(true);
    });

    it('closes the window from a data-close-window button', () => {
        document.body.innerHTML =
            '<input type="button" value="Close" data-close-window>';
        const close = vi.spyOn(window, 'close').mockImplementation(() => {});

        document.querySelector('input')?.click();

        expect(close).toHaveBeenCalledOnce();
    });

    it('selects a data-select-on-focus field when it gets the focus', () => {
        document.body.innerHTML =
            '<input type="text" value="https://example.org/cb" readonly data-select-on-focus>';
        const input = document.querySelector('input') as HTMLInputElement;
        const select = vi.spyOn(input, 'select');

        input.focus();

        expect(select).toHaveBeenCalledOnce();
    });
});
