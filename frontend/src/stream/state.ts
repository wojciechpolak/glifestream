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

/** What the stream page keeps between events, set up by init_stream(). */
export const stream_state = {
    /** Every entry on the page, continuous reading included. */
    articles: $(),
    /** The index in `articles` of the entry j and k moved to. */
    current_article: -1,
    /** The "next page" links. */
    nav_next: $() as JQuery<HTMLAnchorElement>,
    /** How many entries to load in place before "next" navigates. */
    continuous_reading: 300,
};
