from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Input / output
INPUT_NAME = 'slice_B_icon.png'
TEXT_MASK_NAME = 'debug_06_text_mask.png'
INPAINT_NAME = 'debug_07_inpainted.png'
SVG_NAME = 'slice_B_cleaned.svg'

# Text masking parameters
GAUSSIAN_BLUR = 3
BINARY_MODE = 'otsu'  # otsu | adaptive
ADAPTIVE_BLOCK_SIZE = 21
ADAPTIVE_C = 7
MIN_TEXT_AREA = 6
MAX_TEXT_AREA = 800
MIN_TEXT_W = 2
MAX_TEXT_W = 70
MIN_TEXT_H = 2
MAX_TEXT_H = 26
MAX_TEXT_FILL_RATIO = 0.72
TEXT_MASK_DILATE_X = 3
TEXT_MASK_DILATE_Y = 3
BOTTOM_BAND_BONUS = 0.72  # keep more text candidates in the lower caption band
BOTTOM_CAPTION_START = 0.74
BOTTOM_CAPTION_BLOCK_SIZE = 17
BOTTOM_CAPTION_C = 5
BOTTOM_CAPTION_CLOSE_X = 13
BOTTOM_CAPTION_CLOSE_Y = 5
BOTTOM_CAPTION_DILATE_X = 9
BOTTOM_CAPTION_DILATE_Y = 5
BOTTOM_CAPTION_MIN_AREA = 8
BOTTOM_CAPTION_INPAINT_RADIUS = 5

# Inpainting parameters
INPAINT_RADIUS = 3

# Clean vectorization parameters
VECTOR_BLUR = 1
VECTOR_CLOSE_KERNEL = 0
VECTOR_EPSILON_RATIO = 0.005
MIN_VECTOR_AREA = 20.0
MIN_INNER_VECTOR_AREA = 5.0
MAX_VECTOR_OBJECTS = 12
MAX_INNER_OBJECTS = 64
INNER_VECTOR_EPSILON_RATIO = 0.005


@dataclass(slots=True)
class ComponentStat:
    label: int
    x: int
    y: int
    w: int
    h: int
    area: int

    @property
    def fill_ratio(self) -> float:
        return self.area / max(self.w * self.h, 1)


def ensure_odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'Failed to load image: {path}')
    return image


def threshold_text_candidates(gray: np.ndarray) -> np.ndarray:
    blur_size = max(1, ensure_odd(GAUSSIAN_BLUR))
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0) if blur_size > 1 else gray.copy()
    if BINARY_MODE == 'adaptive':
        return cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            ensure_odd(max(3, ADAPTIVE_BLOCK_SIZE)),
            ADAPTIVE_C,
        )
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask



def build_bottom_caption_mask(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    start_y = int(h * BOTTOM_CAPTION_START)
    roi = gray[start_y:, :]
    caption_binary = cv2.adaptiveThreshold(
        roi,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        ensure_odd(max(3, BOTTOM_CAPTION_BLOCK_SIZE)),
        BOTTOM_CAPTION_C,
    )
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(1, BOTTOM_CAPTION_CLOSE_X), max(1, BOTTOM_CAPTION_CLOSE_Y)),
    )
    caption_binary = cv2.morphologyEx(caption_binary, cv2.MORPH_CLOSE, close_kernel)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(caption_binary, connectivity=8)
    filtered = np.zeros_like(caption_binary)
    for label in range(1, num_labels):
        x, y, comp_w, comp_h, area = stats[label]
        if area < BOTTOM_CAPTION_MIN_AREA:
            continue
        if comp_h > max(18, roi.shape[0] - 2):
            continue
        filtered[labels == label] = 255

    dilate_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(1, BOTTOM_CAPTION_DILATE_X), max(1, BOTTOM_CAPTION_DILATE_Y)),
    )
    filtered = cv2.dilate(filtered, dilate_kernel, iterations=1)
    full_mask = np.zeros_like(gray)
    full_mask[start_y:, :] = filtered
    return full_mask


def build_text_mask(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = threshold_text_candidates(gray)
    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    text_mask = np.zeros_like(binary)
    h, w = binary.shape
    bottom_bonus_start = int(h * BOTTOM_BAND_BONUS)

    for label in range(1, num_labels):
        x, y, comp_w, comp_h, area = stats[label]
        stat = ComponentStat(label=label, x=int(x), y=int(y), w=int(comp_w), h=int(comp_h), area=int(area))

        if stat.area < MIN_TEXT_AREA or stat.w < MIN_TEXT_W or stat.h < MIN_TEXT_H:
            continue

        lower_band = stat.y >= bottom_bonus_start
        max_area = MAX_TEXT_AREA * (2 if lower_band else 1)
        max_w = MAX_TEXT_W * (2 if lower_band else 1)
        max_h = MAX_TEXT_H * (2 if lower_band else 1)

        if stat.area > max_area or stat.w > max_w or stat.h > max_h:
            continue

        # Keep compact letter-like / punctuation-like blobs, but reject large border strokes.
        if stat.fill_ratio > MAX_TEXT_FILL_RATIO and not lower_band:
            continue
        if stat.w >= 18 and stat.h >= 18 and stat.fill_ratio < 0.12:
            continue

        text_mask[labels == label] = 255

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(1, TEXT_MASK_DILATE_X), max(1, TEXT_MASK_DILATE_Y)),
    )
    text_mask = cv2.dilate(text_mask, kernel, iterations=1)
    caption_mask = build_bottom_caption_mask(gray)
    return cv2.bitwise_or(text_mask, caption_mask)


def inpaint_text(image: np.ndarray, text_mask: np.ndarray) -> np.ndarray:
    inpainted = cv2.inpaint(image, text_mask, INPAINT_RADIUS, cv2.INPAINT_TELEA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    caption_mask = build_bottom_caption_mask(gray)
    if np.any(caption_mask):
        inpainted = cv2.inpaint(inpainted, caption_mask, BOTTOM_CAPTION_INPAINT_RADIUS, cv2.INPAINT_TELEA)
    return inpainted


def approximate_contour(contour: np.ndarray, epsilon_ratio: float = VECTOR_EPSILON_RATIO) -> np.ndarray:
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(1.0, perimeter * epsilon_ratio)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = approx.reshape(-1, 2) if len(approx) >= 3 else contour.reshape(-1, 2)
    return points


def points_to_path(points: np.ndarray) -> str:
    coords = [f'{int(x)},{int(y)}' for x, y in points]
    if not coords:
        return ''
    return 'M ' + ' L '.join(coords) + ' Z'


def contour_depth(index: int, hierarchy: np.ndarray) -> int:
    depth = 0
    parent = hierarchy[index][3]
    while parent != -1:
        depth += 1
        parent = hierarchy[parent][3]
    return depth


def bbox_contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int], margin: int = 2) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ox - margin <= ix and oy - margin <= iy and ox + ow + margin >= ix + iw and oy + oh + margin >= iy + ih


def vectorize_clean_image(image: np.ndarray) -> tuple[list[str], list[str]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_size = max(1, ensure_odd(VECTOR_BLUR))
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0) if blur_size > 1 else gray.copy()

    # Use Otsu directly and only apply morphology when explicitly enabled.
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if VECTOR_CLOSE_KERNEL > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (ensure_odd(VECTOR_CLOSE_KERNEL), ensure_odd(VECTOR_CLOSE_KERNEL)),
        )
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, raw_hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if raw_hierarchy is None or not contours:
        raise RuntimeError('No clean vector contours found after inpainting')
    hierarchy = raw_hierarchy[0]

    outer_indices = [idx for idx, h in enumerate(hierarchy) if h[3] == -1 and cv2.contourArea(contours[idx]) >= MIN_VECTOR_AREA]
    outer_indices.sort(key=lambda idx: cv2.contourArea(contours[idx]), reverse=True)
    outer_indices = outer_indices[:MAX_VECTOR_OBJECTS]

    if not outer_indices:
        raise RuntimeError('No outer contours found after inpainting')

    outer_paths: list[str] = []
    outer_bboxes: list[tuple[int, int, int, int]] = []
    for idx in outer_indices:
        outer_paths.append(points_to_path(approximate_contour(contours[idx], VECTOR_EPSILON_RATIO)))
        outer_bboxes.append(tuple(int(v) for v in cv2.boundingRect(contours[idx])))

    inner_candidates: list[tuple[float, str]] = []
    for idx, contour in enumerate(contours):
        if idx in outer_indices:
            continue
        area = cv2.contourArea(contour)
        if area < MIN_INNER_VECTOR_AREA:
            continue
        bbox = tuple(int(v) for v in cv2.boundingRect(contour))
        if not any(bbox_contains(outer_bbox, bbox) for outer_bbox in outer_bboxes):
            continue
        depth = contour_depth(idx, hierarchy)
        if depth <= 0:
            continue
        path_data = points_to_path(approximate_contour(contour, INNER_VECTOR_EPSILON_RATIO))
        if not path_data:
            continue
        inner_candidates.append((area, path_data))

    inner_candidates.sort(key=lambda item: item[0], reverse=True)
    inner_paths = [path for _area, path in inner_candidates[:MAX_INNER_OBJECTS]]
    return outer_paths, inner_paths


def write_svg(path: Path, width: int, height: int, outer_paths: list[str], inner_paths: list[str]) -> None:
    compound_d = ' '.join(path_data for path_data in [*outer_paths, *inner_paths] if path_data)
    fragments = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "  <rect width='100%' height='100%' fill='#ffffff' />",
    ]
    if compound_d:
        fragments.append(f"  <path d='{compound_d}' fill='#111111' fill-rule='evenodd' stroke='none' />")
    fragments.append('</svg>')
    path.write_text('\n'.join(fragments), encoding='utf-8')


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    input_path = base_dir / INPUT_NAME
    image = load_image(input_path)

    text_mask = build_text_mask(image)
    inpainted = inpaint_text(image, text_mask)
    outer_paths, inner_paths = vectorize_clean_image(inpainted)

    cv2.imwrite(str(base_dir / TEXT_MASK_NAME), text_mask)
    cv2.imwrite(str(base_dir / INPAINT_NAME), inpainted)
    write_svg(base_dir / SVG_NAME, image.shape[1], image.shape[0], outer_paths, inner_paths)

    print(f'input={input_path}')
    print(f'text_mask={base_dir / TEXT_MASK_NAME}')
    print(f'inpainted={base_dir / INPAINT_NAME}')
    print(f'outer_paths={len(outer_paths)} inner_paths={len(inner_paths)}')
    print(f'svg={base_dir / SVG_NAME}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
