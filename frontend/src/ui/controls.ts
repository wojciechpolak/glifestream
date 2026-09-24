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

// Controls any page can have. The markup marks them with data attributes,
// since the Content Security Policy runs no inline event handler.

import { delegate, submit_form } from '../util/dom';

export function init_page_controls(): void {
    // The logout link: submits the form it names.
    delegate(document, 'click', '[data-submit-form]', function (control) {
        const form = document.getElementById(control.dataset['submitForm'] ?? '');
        if (form instanceof HTMLFormElement) {
            submit_form(form);
        }
        return false;
    });
    // "Close" at the end of the OAuth setup, in the window it opened in.
    delegate(document, 'click', '[data-close-window]', function () {
        window.close();
        return false;
    });
    // The callback URL to copy on the OAuth setup page.
    delegate(document, 'focusin', 'input[data-select-on-focus]', function (input) {
        (input as HTMLInputElement).select();
    });
}
