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

// The sidebar's height, for the theme. A theme that pins the sidebar as the
// stream scrolls can pin one taller than the window by its bottom instead
// of its top, so that all of it can be scrolled to; CSS cannot know how
// tall it is, so this tells it, as --sidebar-height on the sidebar.

/** Sets --sidebar-height on `sidebar`, now and whenever its size changes. */
export function init_sidebar_height(
    sidebar: HTMLElement | null = document.getElementById('sidebar'),
): void {
    if (!sidebar) {
        return;
    }
    const update = (): void => {
        sidebar.style.setProperty('--sidebar-height', sidebar.offsetHeight + 'px');
    };
    update();
    // It grows as the calendar renders and as the drawer opens; a browser
    // without ResizeObserver keeps the first height.
    if (typeof ResizeObserver === 'function') {
        new ResizeObserver(update).observe(sidebar);
    }
}
