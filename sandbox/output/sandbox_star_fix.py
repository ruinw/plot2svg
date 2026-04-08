from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / 'test_star.png'
DEBUG_PATH = BASE_DIR / 'debug_star_contour.png'
SVG_SNIPPET_PATH = BASE_DIR / 'debug_star_polygon.svg'


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f'Failed to read image: {path}')
    return image


def blue_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (90, 60, 40), (140, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    return mask


def build_star_template(size: int = 128) -> np.ndarray:
    canvas = np.zeros((size, size), dtype=np.uint8)
    center = np.array([size / 2.0, size / 2.0], dtype=np.float32)
    outer = size * 0.42
    inner = outer * 0.45
    points = []
    for index in range(10):
        angle = -np.pi / 2 + index * (np.pi / 5)
        radius = outer if index % 2 == 0 else inner
        x = center[0] + np.cos(angle) * radius
        y = center[1] + np.sin(angle) * radius
        points.append([int(round(x)), int(round(y))])
    polygon = np.array(points, dtype=np.int32)
    cv2.fillPoly(canvas, [polygon], 255)
    contours, _ = cv2.findContours(canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours[0]


def detect_star_polygon(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError('No contour found in star mask')
    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    template = build_star_template()
    score = cv2.matchShapes(contour, template, cv2.CONTOURS_MATCH_I1, 0.0)

    for epsilon_scale in (0.012, 0.015, 0.018, 0.02, 0.024, 0.028, 0.032):
        approx = cv2.approxPolyDP(contour, perimeter * epsilon_scale, True)
        if len(approx) == 10:
            return approx.reshape(-1, 2)

    if score > 0.25:
        raise RuntimeError(f'Contour is not star-like enough: score={score:.4f}')
    return canonical_star_from_contour(contour)


def canonical_star_from_contour(contour: np.ndarray) -> np.ndarray:
    x, y, w, h = cv2.boundingRect(contour)
    center = np.array([x + w / 2.0, y + h / 2.0], dtype=np.float32)
    outer = min(w, h) * 0.5
    inner = outer * 0.45
    points = []
    for index in range(10):
        angle = -np.pi / 2 + index * (np.pi / 5)
        radius = outer if index % 2 == 0 else inner
        px = center[0] + np.cos(angle) * radius
        py = center[1] + np.sin(angle) * radius
        points.append([int(round(px)), int(round(py))])
    return np.array(points, dtype=np.int32)


def save_debug(image: np.ndarray, points: np.ndarray) -> None:
    debug = image.copy()
    cv2.polylines(debug, [points.reshape(-1, 1, 2)], True, (0, 0, 255), 1, cv2.LINE_AA)
    for index, (x, y) in enumerate(points.tolist(), start=1):
        cv2.circle(debug, (int(x), int(y)), 2, (0, 255, 255), -1, cv2.LINE_AA)
        cv2.putText(debug, str(index), (int(x) + 2, int(y) - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(DEBUG_PATH), debug)


def polygon_svg(points: np.ndarray, fill: str = '#2f6df6', stroke: str = '#1d3f9e') -> str:
    point_text = ' '.join(f'{int(x)},{int(y)}' for x, y in points.tolist())
    return f"<polygon points=\"{point_text}\" fill=\"{fill}\" stroke=\"{stroke}\" stroke-width=\"1\" />"


def main() -> None:
    image = load_image(INPUT_PATH)
    mask = blue_mask(image)
    points = detect_star_polygon(mask)
    save_debug(image, points)
    svg = polygon_svg(points)
    SVG_SNIPPET_PATH.write_text(svg + '\n', encoding='utf-8')
    print(f'input={INPUT_PATH.name}')
    print(f'vertex_count={len(points)}')
    print(svg)


if __name__ == '__main__':
    main()
