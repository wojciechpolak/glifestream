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

// What the page script finds on the page before it runs: Quill for the
// signed-in owner, and the extension points a deployment sets in
// user-scripts.js. The templates' own data is JSON, read by config.ts.
//
// The extension points are a public contract, pinned by
// glifestream/tests/e2e/test_js_extension_points.py.

/** What a video provider puts in the player it opens under an entry. */
interface GlsVideoEmbed {
    html?: string;
    node?: Element;
    /** Inline style of the player, such as an aspect-ratio padding. */
    style?: string;
    onMount?: (player: HTMLElement) => void;
}

/** An embed template with {ID}, or a function that builds the embed. */
type GlsVideoProvider =
    | string
    | ((wrapper: HTMLElement, id: string) => GlsVideoEmbed | null);

/** A site in the share box. {URL} and {TITLE} in href are filled in. */
interface GlsSharingSite {
    name: string;
    href: string;
    /** Shows the icon of the CSS class share-<className>. */
    className?: string;
    /** Shows this image when there is no className. */
    icon?: string;
}

/** Functions the markup's inline handlers used to call, kept for user scripts. */
interface GlsNamespace {
    unhide_entry?: (this: HTMLElement) => boolean;
    run_fetch_service?: (trigger: HTMLElement) => boolean;
}

/** Stylesheets a module imports; esbuild bundles them into dist/glifestream.css. */
declare module '*.css';

interface Window {
    /**
     * Called with every batch of entries shown: the stream, or an array of the
     * entries continuous reading added.
     */
    user_alter_html?: (ctx: HTMLElement | HTMLElement[]) => void;
    /** Replaces the share box site list. */
    social_sharing_sites?: GlsSharingSite[];
    /** Adds audio providers: an embed template with {ID}. */
    audio_embeds?: Record<string, string>;
    /** Adds or replaces video providers. */
    video_embeds?: Record<string, GlsVideoProvider>;
    /** Entries to load in place before "next" navigates; 0 turns it off. */
    continuous_reading?: number | string;
    /** Replaces the page reload, for tests. */
    __glsReloadHandler?: () => void;
    gls?: GlsNamespace;
    /** Quill 2, from the `quill` bundle, loaded only for the signed-in owner. */
    Quill?: typeof import('quill').default;
}
