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

import type { FetchNowResponse, ServiceForm, ServiceFormField } from '../api-types';
import { config } from '../config';
import { post_json, type Params } from '../http';
import { fade_in, fade_out, hide, show } from '../ui/fx';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { MDOM, h, listen } from '../util/dom';
import { scroll_to_element } from '../util/scroll';
import { maybe_start_fetch_status_polling, update_fetch_status } from './fetch-status';

/** Per controlling field: the value that shows each dependent row. */
type SettingsDeps = Record<string, [string, HTMLElement][]>;

const service_form = {
    deps: null as SettingsDeps | null,
};

/** Loads a service form and shows it after `dest`. */
export async function get_service_form(
    params: Record<string, string | undefined>,
    dest: string | HTMLElement,
): Promise<void> {
    const json = await post_json<ServiceForm>(
        config.baseurl + 'settings/api/service',
        params,
    );
    if (!json) {
        return;
    }
    hide_spinner();
    const f = prepare_service_form(json);
    const anchor = typeof dest === 'string' ? document.querySelector(dest) : dest;
    anchor?.after(f);
    await fade_in(f);
    scroll_to_element(f, 120);
    f.querySelector<HTMLInputElement>('input[type=text]')?.focus();
}

export function hide_settings_form(): void {
    const form = document.getElementById('service-form');
    if (form) {
        void fade_out(form);
    }
}

/** The fields a form submits, as the browser would send them. */
function form_fields(form: HTMLFormElement): [string, string][] {
    const fields: [string, string][] = [];
    for (const [name, value] of new FormData(form)) {
        if (typeof value === 'string') {
            fields.push([name, value]);
        }
    }
    return fields;
}

/**
 * Saves the form and shows the answer: the saved service, or the form
 * again with what is missing. `fetch_new` fetches a new service right away.
 */
async function submit_service_form(
    form: HTMLFormElement,
    fetch_new = true,
): Promise<ServiceForm | null> {
    const dest = form.nextElementSibling || form.parentElement;
    const submit = form.querySelector('input[type=submit]');
    if (submit) {
        show_spinner(submit);
    }
    const params: Params = [...form_fields(form), ['method', 'post']];
    const json = await post_json<ServiceForm>(
        form.getAttribute('action') || '',
        params,
    );
    if (!json) {
        return null;
    }
    hide_spinner();
    const f = prepare_service_form(json, fetch_new);
    dest?.append(f);
    show(f);
    return json;
}

function render_service_list_item(data: ServiceForm): HTMLLIElement {
    const item = h('li', null, [
        h('span', { className: 'service ' + data.api }),
        h('a', { href: '#', className: data.api, id: 'service-' + data.id }, [
            data.name,
        ]),
    ]);
    item.setAttribute('data-service-id', String(data.id));
    return item;
}

function upsert_service_list_item(data: ServiceForm): void {
    const item = document.getElementById('service-' + data.id)?.closest('li');
    const li = render_service_list_item(data);
    if (item) {
        item.replaceWith(li);
    } else {
        document.getElementById('edit-service')?.prepend(li);
    }
    if (data.fetch_status) {
        update_fetch_status(data.fetch_status);
    }
}

/** Shows the rows that depend on this field's value and hides the others. */
function settings_onchange_field(field: HTMLInputElement | HTMLSelectElement): void {
    const deps = (service_form.deps as SettingsDeps)[field.id];
    for (const [val, row] of deps || []) {
        const shown = field.value === val;
        for (const input of row.querySelectorAll('input')) {
            input.disabled = !shown;
        }
        row.style.display = shown ? 'block' : 'none';
    }
}

/** A field's value as the input shows it; null shows nothing. */
function field_value(f: ServiceFormField): string {
    return f.value === undefined || f.value === null ? '' : String(f.value);
}

function render_select(f: ServiceFormField): HTMLSelectElement {
    const select = h('select', { id: f.name, name: f.name });
    for (const [value, label] of f.options || []) {
        const selected = value === f.value;
        select.add(new Option(label, value, selected, selected));
    }
    return select;
}

/** The popup each link field opens, by field name: its page and its name. */
const LINK_POPUPS: Readonly<Record<string, string>> = {
    oauth_conf: 'oauth',
    oauth2_conf: 'oauth2',
};

function render_link(f: ServiceFormField, data: ServiceForm): HTMLAnchorElement {
    const link = h('a', { id: f.name, href: f.href || '' }, [field_value(f)]);
    const popup = Object.hasOwn(LINK_POPUPS, f.name) ? LINK_POPUPS[f.name] : undefined;
    if (popup) {
        listen(link, 'click', function () {
            void configure_access(link, popup, data.id);
            return false;
        });
    }
    return link;
}

/**
 * Opens the page that gives the service its access. A service not saved
 * yet has no page, so the form is saved first; the popup opens at once,
 * while the click still allows it, and gets its page when the save is done.
 */
async function configure_access(
    link: HTMLElement,
    name: string,
    id: number | null | undefined,
): Promise<void> {
    const features = popup_features(800, 480);
    const page = (service_id: number): string =>
        new URL(name + '/' + service_id, document.baseURI).href;
    if (id) {
        window.open(page(id), name, features);
        return;
    }
    const popup = window.open('', name, features);
    const form = link.closest('form');
    // Its fetch waits for the access, which the popup is about to give.
    const saved = form ? await submit_service_form(form, false) : null;
    if (popup && saved?.id && saved.method === 'post') {
        popup.location.href = page(saved.id);
    } else {
        popup?.close();
    }
}

function render_field(f: ServiceFormField, data: ServiceForm): HTMLElement {
    if (f.type === 'select') {
        return render_select(f);
    }
    if (f.type === 'checkbox') {
        return h('input', {
            type: f.type,
            id: f.name,
            name: f.name,
            value: '1',
            checked: !!f.checked,
        });
    }
    if (f.type === 'link') {
        return render_link(f, data);
    }
    return h('input', {
        type: f.type,
        id: f.name,
        name: f.name,
        value: field_value(f),
        size: 32,
        placeholder: f.placeholder || '',
        autocomplete: 'off',
    });
}

function render_buttons(data: ServiceForm): HTMLDivElement {
    const row = h('div', { className: 'form-row' }, [
        data.save ? h('input', { type: 'submit', id: 'save', value: data.save }) : null,
        h('input', { type: 'button', id: 'cancel', value: data.cancel }),
    ]);
    listen(row.querySelector<HTMLElement>('#cancel'), 'click', hide_settings_form);
    if (data.delete) {
        const link = h(
            'a',
            {
                href: config.baseurl + 'admin/stream/service/' + data.id + '/delete/',
                target: 'admin',
            },
            [data.delete],
        );
        listen(link, 'click', hide_settings_form);
        row.append(' ', link);
    }
    return row;
}

async function import_service(id: number | null | undefined): Promise<void> {
    const json = await post_json<FetchNowResponse>(
        config.baseurl + 'settings/api/import',
        {
            id,
        },
    );
    if (json) {
        if (json.state) {
            update_fetch_status(json.state);
        }
        maybe_start_fetch_status_polling(false);
    }
}

const bound_forms = new WeakSet<HTMLFormElement>();

/** The service form of the page, or a new one, that submits through the API. */
function get_form(): HTMLFormElement {
    let form = document.getElementById('service-form') as HTMLFormElement | null;
    if (!form) {
        form = h('form', { id: 'service-form', style: { display: 'none' } }, [
            h('fieldset', { className: 'aligned' }),
        ]);
    }
    if (!bound_forms.has(form)) {
        bound_forms.add(form);
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            void submit_service_form(this);
        });
    }
    return form;
}

/** A field's row: its label, hint and input; `deps` learns what shows it. */
function render_row(
    f: ServiceFormField,
    data: ServiceForm,
    deps: SettingsDeps,
): HTMLElement {
    const hint = f.hint ? h('span', { className: 'hint' }, [f.hint]) : null;
    const label = h('label', { htmlFor: f.name, className: f.miss ? 'missing' : '' }, [
        f.label,
    ]);
    const row = h('div', { className: 'form-row' }, [
        label,
        hint,
        render_field(f, data),
    ]);
    for (const [name, value] of Object.entries(f.deps || {})) {
        (deps[name] ||= []).push([value, row]);
    }
    return row;
}

/** Shows the dependent rows that match each controlling field, now and on change. */
function bind_deps(fs: HTMLFieldSetElement, deps: SettingsDeps): void {
    for (const name in deps) {
        const field = fs.querySelector<HTMLInputElement>('#' + CSS.escape(name));
        if (field) {
            field.addEventListener('change', () => settings_onchange_field(field));
            settings_onchange_field(field);
        }
    }
}

/** Builds the service form from the server's description of it. */
function prepare_service_form(data: ServiceForm, fetch_new = true): HTMLFormElement {
    const form = get_form();
    hide(form);

    const fs = form.querySelector('fieldset') as HTMLFieldSetElement;
    fs.replaceChildren();
    const deps: SettingsDeps = {};
    service_form.deps = deps;

    form.action = data.action;

    if (data.id) {
        fs.append(h('input', { type: 'hidden', name: 'id', value: String(data.id) }));
    }
    fs.append(h('input', { type: 'hidden', name: 'api', value: data.api }));
    for (const f of data.fields) {
        fs.append(render_row(f, data, deps));
    }
    bind_deps(fs, deps);
    if (data.notice) {
        fs.append(h('p', { className: 'form-notice', role: 'status' }, [data.notice]));
    }
    fs.append(render_buttons(data));

    if (data.id && data.method === 'post') {
        upsert_service_list_item(data);
    }
    if (data.need_import && fetch_new) {
        void import_service(data.id);
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
