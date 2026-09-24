"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import os
import math
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Sequence

import pytest
from PIL import Image, ImageChops, ImageFilter
from playwright.sync_api import Locator, Page


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASELINE_ROOT = PROJECT_ROOT / '.visual-regression'
ARTIFACT_ROOT = PROJECT_ROOT / 'test-results' / 'vrt'
PIXEL_TOLERANCE = 3

# Playwright paints masked elements in this colour.
MASK_COLOR = (255, 0, 255)

# Playwright derives a mask rectangle from the element's bounding box and
# rounds it to whole pixels, while the browser paints the element's own border
# on its own rounding of the same fractional edge. When a masked element's
# height lands close enough to half a pixel the two disagree, and one row of
# its border falls outside the mask -- so the snapshot passes or fails
# depending on which side of the boundary a given machine's layout lands.
# Ignore a thin halo around every mask. The cost is that a mask moving by a
# pixel or two no longer registers, which is the intended trade: a masked
# element is one whose exact extent has already been declared volatile, and a
# real layout shift moves the unmasked content around it as well.
MASK_BLEED = 2


def env_flag(name: str) -> bool:
    value = os.environ.get(name, '')
    return value.lower() in {'1', 'true', 'yes', 'on'}


def _slugify(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', value).strip('-') or 'snapshot'


def _snapshot_slug(name: str) -> str:
    return _slugify(Path(name).stem)


def _load_image_bytes(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        return image.convert('RGB')


def _load_image_file(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert('RGB')


def _threshold_diff(diff: Image.Image, *, tolerance: int) -> Image.Image:
    return diff.point(lambda value: 0 if value <= tolerance else 255)


def _mask_map(image: Image.Image) -> Image.Image:
    """A single-channel map of the pixels Playwright painted as a mask."""
    channels = image.split()
    flags = [
        channel.point(lambda value, wanted=wanted: 255 if value == wanted else 0)
        for channel, wanted in zip(channels, MASK_COLOR)
    ]
    both = ImageChops.multiply(flags[0], flags[1])
    return ImageChops.multiply(both, flags[2])


def _mask_halo(
    expected: Image.Image, actual: Image.Image, *, bleed: int = MASK_BLEED
) -> Image.Image | None:
    """Pixels both images agree are mask, give or take `bleed`.

    Taking the intersection rather than the union is what keeps this honest:
    a mask that grew covers new ground in one image only, so the growth still
    reads as a difference. Only the shared edge is forgiven.
    """
    grow = ImageFilter.MaxFilter(2 * bleed + 1)
    halos = []
    for image in (expected, actual):
        found = _mask_map(image)
        if found.getbbox() is None:
            return None
        halos.append(found.filter(grow))
    shared = ImageChops.darker(halos[0], halos[1])
    return shared if shared.getbbox() is not None else None


def _ignore_mask_edges(
    visible_diff: Image.Image, halo: Image.Image | None
) -> Image.Image:
    if halo is not None:
        visible_diff.paste((0, 0, 0), mask=halo)
    return visible_diff


def _prepare_page_for_screenshot(page: Page) -> None:
    page.wait_for_load_state('networkidle')
    page.evaluate(
        """
        async () => {
            if (!('activeViewTransition' in document)) {
                return;
            }

            for (let attempt = 0; attempt < 5; attempt += 1) {
                const transition = document.activeViewTransition;
                if (!transition) {
                    return;
                }

                try {
                    await transition.finished;
                } catch {
                    return;
                }

                await new Promise((resolve) => {
                    requestAnimationFrame(() => requestAnimationFrame(resolve));
                });
            }
        }
        """
    )
    page.evaluate(
        """
        () => {
            if (document.fonts && document.fonts.ready) {
                return document.fonts.ready;
            }
            return null;
        }
        """
    )
    page.wait_for_function(
        """
        () => {
            // Spinners loop forever; wait only for effects that end.
            const running = document.getAnimations().filter(
                (a) =>
                    a.playState === 'running' &&
                    a.effect &&
                    a.effect.getComputedTiming().endTime !== Infinity
            );
            return running.length === 0;
        }
        """
    )
    page.evaluate(
        """
        () => {
            const active = document.activeElement;
            if (active && typeof active.blur === 'function') {
                active.blur();
            }
        }
        """
    )


def _screenshot_locator(
    target: Locator,
    *,
    mask: list[Locator] | None,
    style: str | None,
) -> bytes:
    page = target.page
    _prepare_page_for_screenshot(page)
    image_bytes = page.screenshot(
        full_page=True,
        animations='disabled',
        caret='hide',
        scale='css',
        mask=mask,
        style=style,
    )
    box = target.bounding_box()
    if box is None:
        return image_bytes

    left = math.floor(box['x'])
    top = math.floor(box['y'])
    right = math.ceil(box['x'] + box['width'])
    bottom = math.ceil(box['y'] + box['height'])
    with Image.open(BytesIO(image_bytes)) as image:
        cropped = image.crop((left, top, right, bottom)).convert('RGB')
        buffer = BytesIO()
        cropped.save(buffer, format='PNG')
        return buffer.getvalue()


@dataclass(frozen=True)
class VisualRegressionSession:
    root: Path
    enabled: bool
    update: bool
    dump: bool

    @classmethod
    def from_request(cls, request: pytest.FixtureRequest) -> VisualRegressionSession:
        relative_file = (
            request.node.path.resolve().relative_to(PROJECT_ROOT).with_suffix('')
        )
        root = relative_file / _slugify(request.node.name)
        return cls(
            root=root,
            enabled=env_flag('VRT'),
            update=env_flag('VRT_UPDATE') or env_flag('VRT_BASELINE'),
            dump=env_flag('VRT_DUMP'),
        )

    def baseline_path(self, name: str) -> Path:
        return BASELINE_ROOT / self.root / f'{_snapshot_slug(name)}.png'

    def artifact_dir(self, name: str) -> Path:
        return ARTIFACT_ROOT / self.root / _snapshot_slug(name)

    def screenshot(
        self,
        target: Page | Locator,
        name: str,
        *,
        full_page: bool = False,
        mask: Sequence[Locator] = (),
        style: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        mask_list = list(mask) if mask else None
        if isinstance(target, Page):
            _prepare_page_for_screenshot(target)
            image_bytes = target.screenshot(
                full_page=full_page,
                animations='disabled',
                caret='hide',
                scale='css',
                mask=mask_list,
                style=style,
            )
        else:
            image_bytes = _screenshot_locator(
                target,
                mask=mask_list,
                style=style,
            )
        baseline_path = self.baseline_path(name)

        if self.update:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_bytes(image_bytes)
            return

        if not baseline_path.exists():
            actual = _load_image_bytes(image_bytes)
            self._write_artifacts(
                name,
                actual=actual,
                expected=actual,
                mismatch_note='Baseline image is missing.',
            )
            raise AssertionError(self._failure_message(name, baseline_path))

        expected = _load_image_file(baseline_path)
        actual = _load_image_bytes(image_bytes)
        if expected.size != actual.size:
            self._write_artifacts(
                name,
                actual=actual,
                expected=expected,
                mismatch_note=(
                    f'Image sizes differ: expected {expected.size}, actual {actual.size}.'
                ),
            )
            raise AssertionError(self._failure_message(name, baseline_path))

        diff = ImageChops.difference(expected, actual)
        visible_diff = _ignore_mask_edges(
            _threshold_diff(diff, tolerance=PIXEL_TOLERANCE),
            _mask_halo(expected, actual),
        )
        if visible_diff.getbbox() is not None:
            self._write_artifacts(name, actual=actual, expected=expected, diff=diff)
            raise AssertionError(self._failure_message(name, baseline_path))

        if self.dump:
            self._write_artifacts(
                name,
                actual=actual,
                expected=expected,
                mismatch_note='Compare dump requested.',
            )

    def _write_artifacts(
        self,
        name: str,
        *,
        actual: Image.Image,
        expected: Image.Image,
        diff: Image.Image | None = None,
        mismatch_note: str | None = None,
    ) -> None:
        artifact_dir = self.artifact_dir(name)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        actual.save(artifact_dir / 'actual.png')
        expected.save(artifact_dir / 'expected.png')
        if diff is not None:
            diff.save(artifact_dir / 'diff.png')
        if mismatch_note is not None:
            (artifact_dir / 'note.txt').write_text(
                f'{mismatch_note}\n', encoding='utf-8'
            )

    def _failure_message(self, name: str, baseline_path: Path) -> str:
        artifact_dir = self.artifact_dir(name)
        compare_mode = 'VRT=1 VRT_UPDATE=1' if self.update else 'VRT=1'
        return (
            f'Visual regression mismatch for {self.root.as_posix()}/{_snapshot_slug(name)}.\n'
            f'Baseline: {baseline_path}\n'
            f'Artifacts: {artifact_dir}\n'
            f'Run {compare_mode} uv run pytest -m e2e to refresh baselines.'
        )
