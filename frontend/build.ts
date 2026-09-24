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

// Bundles frontend/src into glifestream/static/js/dist, where django-pipeline
// picks the result up for its `main` bundle (see PIPELINE in settings.py).
// esbuild only strips the types; `npm run typecheck` is what checks them.
//
//   node frontend/build.ts               one minified build, for production
//   node frontend/build.ts --no-minify   one readable build, which
//                                        GLS_E2E_JS_COVERAGE=1 needs
//   node frontend/build.ts --watch       rebuild on every change, readable

import * as esbuild from 'esbuild';

const watch = process.argv.includes('--watch');
const minify = !watch && !process.argv.includes('--no-minify');

const options: esbuild.BuildOptions = {
    absWorkingDir: import.meta.dirname,
    entryPoints: { glifestream: 'src/main.ts' },
    outdir: '../glifestream/static/js/dist',
    bundle: true,
    format: 'iife',
    target: 'es2024',
    charset: 'utf8',
    logLevel: 'info',
    // Pipeline serves this file as js/main.js, a directory above its map,
    // where a linked map would not be found. So the map is written next to
    // the bundle but not linked, except in watch mode: the development
    // server, with DEBUG on, serves this file where it is.
    sourcemap: watch ? 'linked' : 'external',
    minify,
};

// The rich editor is a bundle of its own, which only the signed-in owner
// loads. It is Quill and little else, so it is minified, as the copy of Quill
// it replaced was.
const quill: esbuild.BuildOptions = {
    ...options,
    entryPoints: { quill: 'src/quill.ts' },
    minify: true,
};

if (watch) {
    for (const build of [options, quill]) {
        const context = await esbuild.context(build);
        await context.watch();
    }
} else {
    await Promise.all([esbuild.build(options), esbuild.build(quill)]);
}
