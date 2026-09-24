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

import { config } from '../config';
import { show_spinner } from '../ui/spinner';
import { delegate, h, listen, submit_form } from '../util/dom';
import { _ } from '../util/i18n';
import { parse_id } from '../util/ids';
import { change_theme } from '../stream/sidebar';
import {
    initialize_fetch_diagnostics,
    maybe_start_fetch_status_polling,
} from './fetch-status';
import { get_service_form, hide_settings_form } from './service-form';

/** Adds a hidden field to the form and submits it. */
function submit_with(form_id: string, name: string, value: string): void {
    const form = document.getElementById(form_id) as HTMLFormElement | null;
    if (form) {
        form.append(h('input', { type: 'hidden', name, value }));
        submit_form(form);
    }
}

/** Sets up the settings pages: services, lists, WebSub and fetch status. */
export function init_settings(): void {
    listen('#add-service a', 'click', function (link) {
        show_spinner(link);
        void get_service_form({ method: 'get', api: link.className }, '#add-service');
        return false;
    });
    delegate(document, 'click', '#edit-service a', function (link) {
        if (link.id && link.id.indexOf('service-') === 0) {
            show_spinner(link);
            void get_service_form({ method: 'get', id: parse_id(link.id)[1] }, link);
            return false;
        }
        return undefined;
    });
    listen('#select-list', 'change', function (select) {
        const value = (select as HTMLSelectElement).value;
        if (value !== '') {
            window.location.href = config.baseurl + 'settings/lists/' + value;
        } else {
            window.location.href = config.baseurl + 'settings/lists';
        }
    });
    listen('#settings input[name=cancel]', 'click', hide_settings_form);
    listen('#list-form a', 'click', function () {
        if (confirm(_('Are you sure?'))) {
            submit_with('list-form', 'delete', '1');
        }
        return false;
    });
    listen('#websub-subs a', 'click', function (link) {
        if (!confirm(_('Are you sure?'))) {
            return false;
        }
        show_spinner(link);
        const id = parse_id(link.id)[1] as string;
        for (const select of document.querySelectorAll('select')) {
            select.disabled = true;
        }
        submit_with('websub-form', 'unsubscribe', id);
        return false;
    });
    listen('#change-theme', 'click', change_theme);
    initialize_fetch_diagnostics();
    maybe_start_fetch_status_polling(true);
}
