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
import { DCE } from '../util/dom';
import { _ } from '../util/i18n';
import { parse_id } from '../util/ids';
import { change_theme } from '../stream/sidebar';
import {
    initialize_fetch_diagnostics,
    maybe_start_fetch_status_polling,
} from './fetch-status';
import { get_service_form, hide_settings_form } from './service-form';

/** Sets up the settings pages: services, lists, WebSub and fetch status. */
export function init_settings(): void {
    $('#add-service a').click(function () {
        show_spinner(this);
        get_service_form(
            {
                method: 'get',
                api: this.className,
            },
            '#add-service',
        );
        return false;
    });
    $(document).on('click', '#edit-service a', function () {
        if (this.id && this.id.indexOf('service-') === 0) {
            show_spinner(this);
            get_service_form(
                {
                    method: 'get',
                    id: parse_id(this.id)[1],
                },
                this,
            );
            return false;
        }
        return undefined;
    });
    $<HTMLSelectElement>('#select-list').change(function () {
        if (this.value !== '') {
            window.location.href = config.baseurl + 'settings/lists/' + this.value;
        } else {
            window.location.href = config.baseurl + 'settings/lists';
        }
    });
    $('#settings input[name=cancel]').click(hide_settings_form);
    $('#list-form a').click(function () {
        if (!confirm(_('Are you sure?'))) {
            return false;
        }
        const form = $('#list-form');
        form.append(
            DCE('input', {
                type: 'hidden',
                name: 'delete',
                value: 1,
            }),
        );
        form.submit();
        return false;
    });
    $('#websub-subs a').click(function () {
        if (!confirm(_('Are you sure?'))) {
            return false;
        }
        show_spinner(this);
        const id = parse_id(this.id)[1];
        const form = $('#websub-form');
        $('select').attr('disabled', 'disabled');
        form.append(
            DCE('input', {
                type: 'hidden',
                name: 'unsubscribe',
                value: id,
            }),
        );
        form.submit();
        return false;
    });
    $('#change-theme').click(change_theme);
    initialize_fetch_diagnostics();
    maybe_start_fetch_status_polling(true);
}
