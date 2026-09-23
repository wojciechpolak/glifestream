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

import type { FetchNowResponse, ServiceForm } from '../api-types';
import { config } from '../config';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { DCE, MDOM } from '../util/dom';
import { scroll_to_element } from '../util/scroll';
import { maybe_start_fetch_status_polling, update_fetch_status } from './fetch-status';

/** Per controlling field: the value that shows each dependent row. */
type SettingsDeps = Record<string, [string, HTMLElement][]>;

export const service_form = {
    deps: null as SettingsDeps | null,
};

/** Loads a service form and shows it after `dest`. */
export function get_service_form(
    params: Record<string, string | undefined>,
    dest: string | HTMLElement,
): void {
    $.ajax({
        url: config.baseurl + 'settings/api/service',
        data: $.param(params),
        dataType: 'json',
        type: 'POST',
        success: function (json: ServiceForm) {
            hide_spinner();
            const f = prepare_service_form(json);
            const $dest = typeof dest === 'string' ? $(dest) : $(dest);
            $dest.after(f);
            $(f).fadeIn('normal', function () {
                scroll_to_element(f, 120);
                $('input[type=text]:first', f).focus();
            });
        },
    });
}

export function hide_settings_form(): void {
    $('#service-form').fadeOut();
}

function submit_service_form(this: GlobalEventHandlers): boolean {
    const that = this as HTMLFormElement;
    let dest = $(that).next();
    if (dest.length === 0) {
        dest = $(that).parent();
    }
    show_spinner($('input[type=submit]', that));

    const form = $<HTMLFormElement>('#service-form');
    const params = form.serializeArray();
    params.push({
        name: 'method',
        value: 'post',
    });

    $.ajax({
        url: form.attr('action'),
        data: $.param(params),
        dataType: 'json',
        type: 'POST',
        success: function (json: ServiceForm) {
            hide_spinner();
            const f = prepare_service_form(json);
            dest.append(f);
            $(f).show();
        },
    });
    return false;
}

function render_service_list_item(data: ServiceForm): string {
    let html = '<li data-service-id="' + data.id + '">';
    html += '<span class="service ' + data.api + '"></span>';
    html +=
        '<a href="#" class="' +
        data.api +
        '" id="service-' +
        data.id +
        '">' +
        data.name +
        '</a>';
    html += '</li>';
    return html;
}

function upsert_service_list_item(data: ServiceForm): void {
    const item = $('#service-' + data.id).closest('li');
    const html = render_service_list_item(data);
    if (item.length) {
        item.replaceWith(html);
    } else {
        $('#edit-service').prepend(html);
    }
    if (data.fetch_status) {
        update_fetch_status(data.fetch_status);
    }
}

/** Shows the rows that depend on this field's value and hides the others. */
function settings_onchange_field(this: HTMLInputElement | HTMLSelectElement): void {
    const deps_by_field = service_form.deps as SettingsDeps;
    if (this.id in deps_by_field) {
        const deps = deps_by_field[this.id] as [string, HTMLElement][];
        for (let i = 0; i < deps.length; i++) {
            const [val, row] = deps[i] as [string, HTMLElement];
            if (this.value === val) {
                $('input', row).removeAttr('disabled');
                row.style.display = 'block';
            } else {
                $('input', row).attr('disabled', 'disabled');
                row.style.display = 'none';
            }
        }
    }
}

/** Builds the service form from the server's description of it. */
function prepare_service_form(data: ServiceForm): HTMLFormElement {
    let form = document.getElementById('service-form') as HTMLFormElement | null;
    if (!form) {
        form = DCE(
            'form',
            {
                id: 'service-form',
                style: {
                    display: 'none',
                },
            },
            [
                DCE('fieldset', {
                    className: 'aligned',
                }),
            ],
        );
    }
    $(form).hide();

    const fs = $('fieldset:first', form);
    fs.empty();
    const deps: SettingsDeps = {};
    service_form.deps = deps;

    if (data) {
        form.action = data.action;
        form.onsubmit = submit_service_form;

        if (data.id) {
            fs.append(
                DCE('input', {
                    type: 'hidden',
                    name: 'id',
                    value: data.id,
                }),
            );
        }
        fs.append(
            DCE('input', {
                type: 'hidden',
                name: 'api',
                value: data.api,
            }),
        );

        let obj: HTMLElement;

        for (let i = 0; i < data.fields.length; i++) {
            const f = data.fields[i] as ServiceForm['fields'][number];

            if (f.type === 'select') {
                const select = DCE('select', {
                    id: f.name,
                    name: f.name,
                    value: f.value,
                });
                const options = f.options as [string, string][];
                for (let j = 0; j < options.length; j++) {
                    const opt = options[j] as [string, string];
                    const sel = opt[0] === f.value;
                    select.options[select.options.length] = new Option(
                        opt[1],
                        opt[0],
                        sel,
                        sel,
                    );
                }
                obj = select;
            } else if (f.type === 'checkbox') {
                obj = DCE('input', {
                    type: f.type,
                    id: f.name,
                    name: f.name,
                    value: '1',
                    checked: f.checked,
                });
            } else if (f.type === 'link') {
                obj = DCE(
                    'a',
                    {
                        id: f.name,
                        href: f.href,
                    },
                    [f.value],
                );
                if (f.name === 'oauth_conf') {
                    obj.onclick = function () {
                        oauth_configure(data.id as number);
                        return false;
                    };
                } else if (f.name === 'oauth2_conf') {
                    obj.onclick = function () {
                        oauth2_configure(data.id as number);
                        return false;
                    };
                }
            } else {
                obj = DCE('input', {
                    type: f.type,
                    id: f.name,
                    name: f.name,
                    value: f.value,
                    size: 32,
                    maxlength: 80,
                    placeholder: f.placeholder || '',
                    autocomplete: 'off',
                });
            }

            let hint: HTMLElement | false = false;
            if (f.hint) {
                hint = DCE(
                    'span',
                    {
                        className: 'hint',
                    },
                    [f.hint],
                );
            }

            const miss = f.miss ? 'missing' : '';
            const row = DCE(
                'div',
                {
                    className: 'form-row',
                },
                [
                    DCE(
                        'label',
                        {
                            htmlFor: f.name,
                            className: miss,
                        },
                        [f.label],
                    ),
                    hint,
                    obj,
                    false,
                ],
            );
            if (f.deps) {
                for (const name in f.deps) {
                    if (!deps[name]) {
                        deps[name] = [];
                    }
                    deps[name].push([f.deps[name] as string, row]);
                }
            }
            fs.append(row);
        }
        for (const name in deps) {
            $<HTMLInputElement>('#' + name)
                .change(settings_onchange_field)
                .change();
        }

        const row = DCE('div', {
            className: 'form-row',
        });
        if (data.save) {
            row.appendChild(
                DCE('input', {
                    type: 'submit',
                    id: 'save',
                    value: data.save,
                }),
            );
        }
        row.appendChild(
            DCE('input', {
                type: 'button',
                id: 'cancel',
                value: data.cancel,
                onclick: hide_settings_form,
            }),
        );
        if (data['delete']) {
            row.appendChild(document.createTextNode(' '));
            row.appendChild(
                DCE(
                    'a',
                    {
                        href:
                            config.baseurl +
                            'admin/stream/service/' +
                            data.id +
                            '/delete/',
                        target: 'admin',
                        onclick: hide_settings_form,
                    },
                    [data['delete']],
                ),
            );
        }
        fs.append(row);

        if (data.id && data.method === 'post') {
            upsert_service_list_item(data);
        }
        if (data['need_import']) {
            $.ajax({
                url: config.baseurl + 'settings/api/import',
                dataType: 'json',
                type: 'POST',
                data: {
                    id: data.id,
                },
                success: function (json: FetchNowResponse) {
                    if (json.state) {
                        update_fetch_status(json.state);
                    }
                    maybe_start_fetch_status_polling(false);
                },
            });
        }
    }
    return form;
}

function popup_features(width: number, height: number): string {
    const p = MDOM.get_win_center(width, height);
    return (
        'width=' +
        p.width +
        ',height=' +
        p.height +
        ',left=' +
        p.left +
        ',top=' +
        p.top +
        ',toolbar=no,status=yes,location=no,resizable=yes' +
        ',scrollbars=yes'
    );
}

function oauth_configure(id: number): void {
    window.open('oauth/' + id, 'oauth', popup_features(800, 480));
}

function oauth2_configure(id: number): void {
    window.open('oauth2/' + id, 'oauth2', popup_features(800, 480));
}
