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

// The JSON the page script reads from the server, in responses and in the
// json_script elements of the page. Only the fields it uses are listed.
// glifestream/tests/test_frontend_contract.py checks that the server sends
// them; change both together.
//
// The other endpoints it calls (api/getcontent, putcontent, share and
// reshare) answer with HTML.

/** #gls-config, on every page (stream/templatetags/gls_page.py). */
export interface PageConfig {
    baseurl: string;
    /** 'google' for Google Maps, anything else for OpenStreetMap. */
    maps_engine: string;
    themes: string[];
    /** The language the messages are translated into, as a BCP 47 tag. */
    lang: string;
    /** English message to its translation, for every message _() is given. */
    messages: Record<string, string>;
}

/** #gls-stream-data, on stream pages, for the archive calendar. */
export interface StreamData {
    ctx: string;
    year_now: number;
    /** The month on view, as YYYY/MM. */
    view_date: string;
    /** Every month with entries, as YYYY/MM. */
    archives: string[];
    month_names: string[];
}

/** api/gsc: the first selfposts service of each class. */
export interface SelfpostsClass {
    id: number;
    cls: string;
}

/** A stream page requested with format=html-pure (stream/index_view.py). */
export interface StreamPage {
    /** The rendered entries. */
    stream: string;
    /** The value of start= or page= for the page after this one. */
    next: string | number;
}

/** fetching.serialize_fetch_state(). Timestamps are ISO 8601. */
export interface FetchState {
    service_id: number;
    /** idle, queued, running, succeeded or failed. */
    status: string;
    requested_at?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    last_succeeded_at?: string | null;
    last_failed_at?: string | null;
    next_fetch_at?: string | null;
    last_result?: string;
    last_error?: string;
    failure_note?: string;
}

/** settings/api/fetch-status: every service's state, by service id. */
export interface FetchStatusResponse {
    services: Record<string, FetchState>;
}

/**
 * settings/api/fetch-now and settings/api/import. An error answers with a
 * 4xx status and { error }.
 */
export interface FetchNowResponse {
    state?: FetchState;
}

export interface FetchNowError {
    error?: string;
}

/** One field of the service form (usettings/service_settings.py). */
export interface ServiceFormField {
    type: 'text' | 'number' | 'password' | 'select' | 'checkbox' | 'link';
    name: string;
    label: string;
    value?: string | number;
    placeholder?: string;
    hint?: string;
    /** A required field left empty. */
    miss?: boolean;
    checked?: boolean;
    href?: string;
    /** [value, label] pairs of a select. */
    options?: [string, string][];
    /** Shown only while the field named by the key has that value. */
    deps?: Record<string, string>;
}

/** settings/api/service: the form for a new or existing service. */
export interface ServiceForm {
    /** null for a service not saved yet. */
    id?: number | null;
    api: string;
    name: string;
    action: string;
    method: 'get' | 'post';
    fields: ServiceFormField[];
    save: string;
    cancel: string;
    /** The label of the delete link, for an existing service. */
    delete?: string;
    /** A new service to fetch right away. */
    need_import?: boolean;
    fetch_status?: FetchState;
}
