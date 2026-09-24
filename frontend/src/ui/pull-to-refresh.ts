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

import { _ } from '../util/i18n';
import { reload_page } from '../util/navigation';
import { jump_to_top } from '../util/scroll';

function is_at_top(): boolean {
    const bodyScrollTop = document.body ? document.body.scrollTop : 0;
    const docScrollTop = document.documentElement
        ? document.documentElement.scrollTop
        : 0;
    return window.scrollY <= 0 && bodyScrollTop <= 0 && docScrollTop <= 0;
}

function is_sidebar_expanded(): boolean {
    return !!document.getElementById('sidebar')?.classList.contains('expanded');
}

function should_ignore_target(target: EventTarget | null): boolean {
    const el = target as Partial<Element> | null;
    return !!(
        el &&
        el.closest &&
        el.closest(
            '#sidebar.expanded, input, textarea, select, button, [contenteditable="true"]',
        )
    );
}

/** On a phone-sized screen, pulling the top of the stream down reloads it. */
export function init_pull_to_refresh(): void {
    if (
        !(window as Partial<Window>).matchMedia ||
        !window.matchMedia('(max-width: 640px)').matches ||
        !document.getElementById('stream')
    ) {
        return;
    }

    const threshold = 72;
    const maxOffset = 84;
    const indicator = document.createElement('div');
    indicator.id = 'pull-to-refresh';
    indicator.textContent = _('Pull to refresh');
    document.body.appendChild(indicator);

    const state = {
        active: false,
        armed: false,
        refreshing: false,
        startX: 0,
        startY: 0,
    };

    function set_pull_offset(offset: number): void {
        document.body.style.setProperty(
            '--pull-refresh-offset',
            Math.min(maxOffset, offset * 0.45) + 'px',
        );
    }

    function reset_pull_state(): void {
        if (state.refreshing) {
            return;
        }
        state.active = false;
        state.armed = false;
        document.body.classList.remove(
            'pull-refresh-active',
            'pull-refresh-armed',
            'pull-refresh-refreshing',
        );
        indicator.textContent = _('Pull to refresh');
        set_pull_offset(0);
    }

    document.addEventListener(
        'touchstart',
        function (event) {
            if (
                state.refreshing ||
                event.touches.length !== 1 ||
                !is_at_top() ||
                is_sidebar_expanded() ||
                should_ignore_target(event.target)
            ) {
                state.active = false;
                return;
            }

            const touch = event.touches[0] as Touch;
            state.active = true;
            state.armed = false;
            state.startX = touch.clientX;
            state.startY = touch.clientY;
            document.body.classList.remove(
                'pull-refresh-active',
                'pull-refresh-armed',
                'pull-refresh-refreshing',
            );
            indicator.textContent = _('Pull to refresh');
            set_pull_offset(0);
        },
        { passive: true },
    );

    document.addEventListener(
        'touchmove',
        function (event) {
            if (state.refreshing || !state.active || event.touches.length !== 1) {
                return;
            }

            const touch = event.touches[0] as Touch;
            const deltaY = touch.clientY - state.startY;
            const deltaX = Math.abs(touch.clientX - state.startX);
            if (deltaY <= 0 || deltaX > 48 || !is_at_top() || is_sidebar_expanded()) {
                reset_pull_state();
                return;
            }

            if (event.cancelable) {
                event.preventDefault();
            }

            state.armed = deltaY >= threshold;
            indicator.textContent = state.armed
                ? _('Release to refresh')
                : _('Pull to refresh');
            document.body.classList.add('pull-refresh-active');
            document.body.classList.toggle('pull-refresh-armed', state.armed);
            set_pull_offset(deltaY);
        },
        { passive: false },
    );

    document.addEventListener(
        'touchend',
        function () {
            if (!state.active) {
                return;
            }

            state.active = false;
            if (!state.armed || state.refreshing) {
                reset_pull_state();
                return;
            }

            state.refreshing = true;
            state.armed = false;
            indicator.textContent = _('Refreshing...');
            document.body.classList.remove('pull-refresh-armed');
            document.body.classList.add(
                'pull-refresh-active',
                'pull-refresh-refreshing',
            );
            set_pull_offset(0);
            jump_to_top();
            window.setTimeout(function () {
                reload_page();
            }, 40);
        },
        { passive: true },
    );

    document.addEventListener(
        'touchcancel',
        function () {
            if (!state.refreshing) {
                reset_pull_state();
            }
        },
        { passive: true },
    );
}
