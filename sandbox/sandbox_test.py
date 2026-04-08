from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import xml.sax.saxutils as saxutils

import cv2
import numpy as np


# =============================
# Tunable OpenCV parameters
# =============================
BLUR_KERNEL_SIZE = 5
USE_ADAPTIVE_THRESHOLD = True
FIXED_THRESHOLD = 205
ADAPTIVE_BLOCK_SIZE = 31
ADAPTIVE_C = 7
MORPH_CLOSE_KERNEL = 5
MORPH_OPEN_KERNEL = 3
MORPH_CLOSE_ITERATIONS = 2
MORPH_OPEN_ITERATIONS = 1
CANNY_LOW = 50
CANNY_HIGH = 140
MIN_CONTOUR_AREA = 24.0
APPROX_EPSILON_RATIO = 0.015
SVG_STROKE_WIDTH = 1.2
CONTACT_SHEET_COLUMNS = 3
CONTACT_SHEET_PADDING = 16
LABEL_HEIGHT = 24
BACKGROUND_COLOR = (255, 255, 255)
DEBUG_PREFIXES = ('debug_', 'slice_result')
EXCLUDED_PREFIXES = ('test_',)
SUPPORTED_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_SVG = BASE_DIR / 'slice_result.svg'
DEBUG_GRAYSCALE = BASE_DIR / 'debug_01_grayscale.png'
DEBUG_BINARY = BASE_DIR / 'debug_02_binary_mask.png'
DEBUG_MORPH = BASE_DIR / 'debug_03_morphology.png'
DEBUG_CONTOURS = BASE_DIR / 'debug_04_contours.png'


@dataclass
class SliceArtifacts:
    name: str
    original_bgr: np.ndarray
    grayscale: np.ndarray
    binary_mask: np.ndarray
    morphology_mask: np.ndarray
    contour_preview: np.ndarray
    vector_shapes: list[dict[str, object]]


def list_slice_images() -> list[Path]:
    paths: list[Path] = []
    for path in sorted(BASE_DIR.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        lower_name = path.name.lower()
        if lower_name.startswith(DEBUG_PREFIXES):
            continue
        if lower_name.startswith(EXCLUDED_PREFIXES):
            continue
        paths.append(path)
    return paths


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f'Failed to load image: {path}')
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        bgr = image[:, :, :3].astype(np.float32)
        alpha = (image[:, :, 3:4].astype(np.float32) / 255.0)
        white = np.full_like(bgr, 255.0)
        composited = bgr * alpha + white * (1.0 - alpha)
        return np.clip(composited, 0, 255).astype(np.uint8)
    return image[:, :, :3]


def process_slice(path: Path) -> SliceArtifacts:
    original_bgr = load_image(path)
    grayscale = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)
    blur_kernel = ensure_odd(BLUR_KERNEL_SIZE)
    blurred = cv2.GaussianBlur(grayscale, (blur_kernel, blur_kernel), 0)

    if USE_ADAPTIVE_THRESHOLD:
        block_size = ensure_odd(ADAPTIVE_BLOCK_SIZE)
        binary_mask = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            ADAPTIVE_C,
        )
    else:
        _, binary_mask = cv2.threshold(blurred, FIXED_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    canny_edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ensure_odd(MORPH_CLOSE_KERNEL), ensure_odd(MORPH_CLOSE_KERNEL)))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ensure_odd(MORPH_OPEN_KERNEL), ensure_odd(MORPH_OPEN_KERNEL)))
    morphology = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, close_kernel, iterations=MORPH_CLOSE_ITERATIONS)
    morphology = cv2.morphologyEx(morphology, cv2.MORPH_OPEN, open_kernel, iterations=MORPH_OPEN_ITERATIONS)
    morphology = cv2.bitwise_or(morphology, canny_edges)

    contour_preview, vector_shapes = extract_contours(original_bgr, morphology)
    return SliceArtifacts(
        name=path.name,
        original_bgr=original_bgr,
        grayscale=grayscale,
        binary_mask=binary_mask,
        morphology_mask=morphology,
        contour_preview=contour_preview,
        vector_shapes=vector_shapes,
    )


def extract_contours(original_bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, object]]]:
    preview = original_bgr.copy()
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hierarchy = hierarchy[0] if hierarchy is not None and len(hierarchy) > 0 else None
    shapes: list[dict[str, object]] = []

    for index, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if area < MIN_CONTOUR_AREA:
            continue
        epsilon = max(cv2.arcLength(contour, True) * APPROX_EPSILON_RATIO, 1.0)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        points = [(int(pt[0][0]), int(pt[0][1])) for pt in approx]
        if len(points) < 2:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        mask_roi = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(mask_roi, [contour], -1, 255, -1)
        mean_bgr = cv2.mean(original_bgr, mask=mask_roi)[:3]
        fill = rgb_hex(int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0]))
        slender = max(w, h) / max(min(w, h), 1)
        is_line = area < 2.5 * max(w, h) or slender >= 8.0

        cv2.drawContours(preview, [contour], -1, (0, 180, 255), 1)
        cv2.putText(preview, str(index), (x, max(12, y + 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)

        shapes.append(
            {
                'points': points,
                'fill': fill,
                'is_line': is_line,
            }
        )

    return preview, shapes


def rgb_hex(r: int, g: int, b: int) -> str:
    return f'#{r:02x}{g:02x}{b:02x}'


def ensure_odd(value: int) -> int:
    value = max(int(value), 1)
    return value if value % 2 == 1 else value + 1


def build_contact_sheet(images: list[tuple[str, np.ndarray]], output_path: Path) -> None:
    if not images:
        raise RuntimeError('No images available for contact sheet generation')

    max_h = max(image.shape[0] for _name, image in images)
    max_w = max(image.shape[1] for _name, image in images)
    cell_w = max_w + CONTACT_SHEET_PADDING * 2
    cell_h = max_h + CONTACT_SHEET_PADDING * 2 + LABEL_HEIGHT
    cols = max(1, CONTACT_SHEET_COLUMNS)
    rows = int(math.ceil(len(images) / cols))
    canvas = np.full((rows * cell_h, cols * cell_w, 3), 255, dtype=np.uint8)

    for index, (name, image) in enumerate(images):
        row = index // cols
        col = index % cols
        x0 = col * cell_w
        y0 = row * cell_h
        if image.ndim == 2:
            image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            image_bgr = image
        offset_x = x0 + CONTACT_SHEET_PADDING + (max_w - image_bgr.shape[1]) // 2
        offset_y = y0 + CONTACT_SHEET_PADDING + LABEL_HEIGHT + (max_h - image_bgr.shape[0]) // 2
        canvas[offset_y:offset_y + image_bgr.shape[0], offset_x:offset_x + image_bgr.shape[1]] = image_bgr
        cv2.rectangle(canvas, (x0 + 4, y0 + 4), (x0 + cell_w - 4, y0 + cell_h - 4), (220, 220, 220), 1)
        cv2.putText(canvas, name, (x0 + 8, y0 + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (40, 40, 40), 1, cv2.LINE_AA)

    cv2.imwrite(str(output_path), canvas)


def render_svg(artifacts: list[SliceArtifacts], output_path: Path) -> None:
    if not artifacts:
        raise RuntimeError('No slice artifacts available for SVG export')

    max_h = max(item.original_bgr.shape[0] for item in artifacts)
    max_w = max(item.original_bgr.shape[1] for item in artifacts)
    cell_w = max_w + CONTACT_SHEET_PADDING * 2
    cell_h = max_h + CONTACT_SHEET_PADDING * 2 + LABEL_HEIGHT
    cols = max(1, CONTACT_SHEET_COLUMNS)
    rows = int(math.ceil(len(artifacts) / cols))
    width = cols * cell_w
    height = rows * cell_h

    parts: list[str] = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#ffffff' />",
    ]

    for index, item in enumerate(artifacts):
        row = index // cols
        col = index % cols
        x0 = col * cell_w
        y0 = row * cell_h
        ox = x0 + CONTACT_SHEET_PADDING + (max_w - item.original_bgr.shape[1]) // 2
        oy = y0 + CONTACT_SHEET_PADDING + LABEL_HEIGHT + (max_h - item.original_bgr.shape[0]) // 2

        parts.append(f"<g id='{safe_id(item.name)}'>")
        parts.append(f"<rect x='{x0 + 4}' y='{y0 + 4}' width='{cell_w - 8}' height='{cell_h - 8}' fill='#ffffff' stroke='#d0d0d0' />")
        parts.append(f"<text x='{x0 + 8}' y='{y0 + 18}' font-family='Arial' font-size='12' fill='#333333'>{escape_xml(item.name)}</text>")
        parts.append(f"<g transform='translate({ox},{oy})'>")
        parts.append(f"<rect x='0' y='0' width='{item.original_bgr.shape[1]}' height='{item.original_bgr.shape[0]}' fill='#ffffff' stroke='#e5e7eb' />")
        for shape in item.vector_shapes:
            points = shape['points']
            path = contour_to_path(points)
            if shape['is_line']:
                parts.append(f"<path d='{path}' fill='none' stroke='{shape['fill']}' stroke-width='{SVG_STROKE_WIDTH}' stroke-linecap='round' stroke-linejoin='round' />")
            else:
                parts.append(f"<path d='{path} Z' fill='{shape['fill']}' fill-opacity='0.88' stroke='#333333' stroke-width='0.8' stroke-linejoin='round' />")
        parts.append('</g>')
        parts.append('</g>')

    parts.append('</svg>')
    output_path.write_text('\n'.join(parts), encoding='utf-8')


def contour_to_path(points: list[tuple[int, int]]) -> str:
    head_x, head_y = points[0]
    segments = [f'M {head_x} {head_y}']
    for x, y in points[1:]:
        segments.append(f'L {x} {y}')
    return ' '.join(segments)


def safe_id(name: str) -> str:
    return ''.join(ch if ch.isalnum() else '-' for ch in name)


def escape_xml(text: str) -> str:
    return saxutils.escape(text, {'"': '&quot;', "'": '&apos;'})


def main() -> None:
    image_paths = list_slice_images()
    if not image_paths:
        raise RuntimeError(f'No slice images found in {BASE_DIR}')

    artifacts = [process_slice(path) for path in image_paths]
    build_contact_sheet([(item.name, item.grayscale) for item in artifacts], DEBUG_GRAYSCALE)
    build_contact_sheet([(item.name, item.binary_mask) for item in artifacts], DEBUG_BINARY)
    build_contact_sheet([(item.name, item.morphology_mask) for item in artifacts], DEBUG_MORPH)
    build_contact_sheet([(item.name, item.contour_preview) for item in artifacts], DEBUG_CONTOURS)
    render_svg(artifacts, OUTPUT_SVG)

    print(f'Processed {len(artifacts)} slices')
    print(f'Generated: {DEBUG_GRAYSCALE.name}, {DEBUG_BINARY.name}, {DEBUG_MORPH.name}, {DEBUG_CONTOURS.name}, {OUTPUT_SVG.name}')


if __name__ == '__main__':
    main()
