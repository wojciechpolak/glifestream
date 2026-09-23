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

export interface LatLon {
    lat: number;
    lon: number;
}

export interface BoundingBox {
    southwest: LatLon;
    northeast: LatLon;
}

/** A square of `radiusKm` around a point, on a spherical Earth. */
export function calculateBoundingBox(
    lat: number,
    lon: number,
    radiusKm: number,
): BoundingBox {
    const earthRadiusKm = 6371;
    const latRad = (lat * Math.PI) / 180;
    const angularDistance = radiusKm / earthRadiusKm;
    const latDiff = (angularDistance * 180) / Math.PI;
    const lonDiff = (angularDistance * 180) / (Math.PI * Math.cos(latRad));
    const swLat = lat - latDiff;
    const swLon = lon - lonDiff;
    const neLat = lat + latDiff;
    const neLon = lon + lonDiff;
    return {
        southwest: { lat: swLat, lon: swLon },
        northeast: { lat: neLat, lon: neLon },
    };
}

/** The bbox parameter of an OpenStreetMap embed: W,S,E,N. */
export function convertToOSMBbox(boundingBox: BoundingBox): string {
    const { southwest, northeast } = boundingBox;
    return (
        `${southwest.lon.toFixed(7)},${southwest.lat.toFixed(7)},` +
        `${northeast.lon.toFixed(7)},${northeast.lat.toFixed(7)}`
    );
}

/** The map of a point, as the markup settings.maps_engine asks for. */
export function get_map_embed(lat: string, lng: string): string {
    if (settings.maps_engine === 'google') {
        return (
            '<img src="https://maps.googleapis.com/maps/api/staticmap?sensor=false&zoom=12&size=175x120&markers=' +
            lat +
            ',' +
            lng +
            '" alt="Map" width="175" height="120" />'
        );
    }
    const boundingBox = calculateBoundingBox(Number(lat), Number(lng), 10);
    const bbox = convertToOSMBbox(boundingBox);

    return (
        '<iframe width="100%" height="200" ' +
        'src="https://www.openstreetmap.org/export/embed.html?layer=mapnik' +
        '&bbox=' +
        bbox +
        '&marker=' +
        lat +
        ',' +
        lng +
        '" ' +
        'style="border: 1px solid black"></iframe>' +
        '<br/>' +
        '<small>' +
        '<a href="https://www.openstreetmap.org/?mlat=' +
        lat +
        '&mlon=' +
        lng +
        '#map=10/' +
        lat +
        '/' +
        lng +
        '" target="_blank">View Larger Map</a>' +
        '</small>'
    );
}

/** Replaces an inline a.map link with the map itself. */
export function render_map(this: HTMLElement): void {
    const link = this as HTMLAnchorElement;
    const lat = $('.latitude', link).html();
    const lng = $('.longitude', link).html();
    link.target = '_blank';
    const parent = link.parentNode as HTMLElement;
    parent.style.paddingLeft = '0';
    parent.style.background = 'none';
    $(link).html(get_map_embed(lat, lng));
}

/** Opens the map of an a.show-map link in place; a second click follows it. */
export function show_map(this: HTMLElement): boolean {
    const link = this as HTMLAnchorElement & { folded?: boolean };
    link.blur();
    if (link.folded) {
        return true;
    }
    const lat = $('.latitude', link).html();
    const lng = $('.longitude', link).html();
    link.target = '_blank';

    if (settings.maps_engine === 'google') {
        link.href = 'https://maps.google.com/?q=' + lat + ',' + lng;
    } else {
        link.href =
            'https://www.openstreetmap.org/?mlat=' +
            lat +
            '&mlon=' +
            lng +
            '#map=10/' +
            lat +
            '/' +
            lng;
    }

    const p = link.parentNode as HTMLElement;
    $('a', p).html(get_map_embed(lat, lng));
    $(p).css('paddingLeft', '0');
    link.folded = true;
    return false;
}
