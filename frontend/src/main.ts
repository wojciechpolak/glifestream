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

// The page script: every page loads it, and it sets up either the stream or
// the settings pages once the document is ready.

import { config } from './config';
import { run_fetch_service } from './settings/fetch-status';
import { init_settings } from './settings/init';
import { unhide_entry } from './stream/entry-actions';
import { init_stream } from './stream/init';
import { es } from './util/dom';

// Called by inline handlers in the markup: the "Undo" link of a hidden entry
// and "Run now" on the settings status page.
es('gls.unhide_entry', function (this: HTMLElement): boolean {
    return unhide_entry(this);
});
es('gls.run_fetch_service', run_fetch_service);

function start(): void {
    config.baseurl = settings.baseurl;

    if (document.getElementById('settings')) {
        init_settings();
        return;
    }
    init_stream();
}

// The script loads in <head>, so it waits for the document.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
} else {
    start();
}
