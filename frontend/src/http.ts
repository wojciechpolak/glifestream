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

function ajax_error(): void {
    alert(_('Communication Error. Try again.'));
    hide_spinner();
}

/** Sends Django's CSRF token with every unsafe request, and reports errors. */
export function setup_ajax(): void {
    $.ajaxSetup({
        beforeSend: function (xhr, options) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(options.type || 'GET')) {
                const csrftoken = read_cookie('csrftoken');
                if (csrftoken) {
                    xhr.setRequestHeader('X-CSRFToken', csrftoken);
                }
            }
        },
        error: ajax_error,
    });
}
