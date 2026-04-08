"""Geometric shape classification and SVG primitive generation."""

from __future__ import annotations

import math

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Shape type constants
# ---------------------------------------------------------------------------

SHAPE_CIRCLE = "circle"
SHAPE_ELLIPSE = "ellipse"
SHAPE_RECTANGLE = "rectangle"
SHAPE_TRIANGLE = "triangle"
SHAPE_STAR = "star"
SHAPE_POLYGON = "polygon"
SHAPE_IRREGULAR = "irregular"

# ---------------------------------------------------------------------------
# Contour classification
# ---------------------------------------------------------------------------

_CIRCULARITY_CIRCLE = 0.82
_CIRCULARITY_ELLIPSE = 0.65
_ECCENTRICITY_CIRCLE = 0.85
_ECCENTRICITY_ELLIPSE_LO = 0.50
_RECT_FILL_MIN = 0.88
_SOLIDITY_RECT = 0.90
_SOLIDITY_TRIANGLE = 0.45
_SOLIDITY_STAR_MAX = 0.55
_SOLIDITY_POLYGON = 0.80


def classify_contour(contour: np.ndarray) -> str:
    """Classify a contour into a geometric shape type."""

    area = cv2.contourArea(contour)
    if area < 16:
        return SHAPE_IRREGULAR

    perimeter = cv2.arcLength(contour, True)
    if perimeter < 1e-6:
        return SHAPE_IRREGULAR

    circularity = 4.0 * math.pi * area / (perimeter * perimeter)

    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / max(hull_area, 1.0)

    epsilon = 0.02 * perimeter
    approx = cv2.approxPolyDP(contour, epsilon, True)
    vertex_count = len(approx)

    eccentricity = _compute_eccentricity(contour)

    rect = cv2.minAreaRect(contour)
    rect_w, rect_h = rect[1]
    rect_area = max(rect_w * rect_h, 1.0)
    rect_fill = area / rect_area

    # Decision tree — ordered by priority
    if circularity >= _CIRCULARITY_CIRCLE and eccentricity >= _ECCENTRICITY_CIRCLE and vertex_count >= 6:
        return SHAPE_CIRCLE
    if circularity >= _CIRCULARITY_ELLIPSE and _ECCENTRICITY_ELLIPSE_LO <= eccentricity < _ECCENTRICITY_CIRCLE and vertex_count >= 5:
        return SHAPE_ELLIPSE
    if vertex_count == 4 and rect_fill >= _RECT_FILL_MIN and solidity >= _SOLIDITY_RECT:
        return SHAPE_RECTANGLE
    if vertex_count == 3 and solidity >= _SOLIDITY_TRIANGLE:
        return SHAPE_TRIANGLE
    if solidity < _SOLIDITY_STAR_MAX and vertex_count >= 8:
        return SHAPE_STAR
    if 5 <= vertex_count <= 8 and solidity >= _SOLIDITY_POLYGON:
        return SHAPE_POLYGON
    return SHAPE_IRREGULAR


def _compute_eccentricity(contour: np.ndarray) -> float:
    """Return min_axis / max_axis from fitEllipse (1.0 = perfect circle)."""

    if len(contour) < 5:
        return 1.0
    try:
        (_cx, _cy), (axis_a, axis_b), _angle = cv2.fitEllipse(contour)
    except cv2.error:
        return 1.0
    if max(axis_a, axis_b) < 1e-6:
        return 1.0
    return min(axis_a, axis_b) / max(axis_a, axis_b)


# ---------------------------------------------------------------------------
# SVG element generators
# ---------------------------------------------------------------------------


def svg_circle(
    element_id: str,
    cx: float,
    cy: float,
    r: float,
    fill: str,
    stroke: str,
    fill_opacity: float | None = None,
) -> str:
    fill_attr = f" fill-opacity='{fill_opacity:.3f}'" if fill_opacity is not None and fill_opacity < 0.999 else ""
    return (
        f"<circle id='{element_id}' cx='{cx:.1f}' cy='{cy:.1f}' r='{r:.1f}' "
        f"fill='{fill}' stroke='{stroke}'{fill_attr} />"
    )


def svg_ellipse(
    element_id: str, cx: float, cy: float, rx: float, ry: float, angle: float,
    fill: str, stroke: str, fill_opacity: float | None = None,
) -> str:
    fill_attr = f" fill-opacity='{fill_opacity:.3f}'" if fill_opacity is not None and fill_opacity < 0.999 else ""
    if abs(angle) < 0.5:
        return (
            f"<ellipse id='{element_id}' cx='{cx:.1f}' cy='{cy:.1f}' "
            f"rx='{rx:.1f}' ry='{ry:.1f}' fill='{fill}' stroke='{stroke}'{fill_attr} />"
        )
    return (
        f"<ellipse id='{element_id}' cx='{cx:.1f}' cy='{cy:.1f}' "
        f"rx='{rx:.1f}' ry='{ry:.1f}' "
        f"transform='rotate({angle:.1f} {cx:.1f} {cy:.1f})' "
        f"fill='{fill}' stroke='{stroke}'{fill_attr} />"
    )


def svg_rect(
    element_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    stroke: str,
    fill_opacity: float | None = None,
) -> str:
    fill_attr = f" fill-opacity='{fill_opacity:.3f}'" if fill_opacity is not None and fill_opacity < 0.999 else ""
    return (
        f"<rect id='{element_id}' x='{x:.1f}' y='{y:.1f}' "
        f"width='{w:.1f}' height='{h:.1f}' fill='{fill}' stroke='{stroke}'{fill_attr} />"
    )


def svg_polygon(
    element_id: str,
    points: list[tuple[float, float]],
    fill: str,
    stroke: str,
    fill_opacity: float | None = None,
) -> str:
    pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    fill_attr = f" fill-opacity='{fill_opacity:.3f}'" if fill_opacity is not None and fill_opacity < 0.999 else ""
    return f"<polygon id='{element_id}' points='{pts_str}' fill='{fill}' stroke='{stroke}'{fill_attr} />"


# ---------------------------------------------------------------------------
# Contour → SVG element dispatch
# ---------------------------------------------------------------------------


def contour_to_svg_element(
    contour: np.ndarray,
    element_id: str,
    offset_x: int,
    offset_y: int,
    fill: str,
    stroke: str,
    shape_hint: str | None = None,
    fill_opacity: float | None = None,
) -> tuple[str, str]:
    """Convert a contour to an SVG element, returning (svg_fragment, shape_type)."""

    shape = shape_hint if shape_hint else classify_contour(contour)

    if shape == SHAPE_CIRCLE:
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        return svg_circle(element_id, cx + offset_x, cy + offset_y, radius, fill, stroke, fill_opacity), shape

    if shape == SHAPE_ELLIPSE:
        if len(contour) >= 5:
            (cx, cy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
            rx, ry = axis_a / 2.0, axis_b / 2.0
            return svg_ellipse(element_id, cx + offset_x, cy + offset_y, rx, ry, angle, fill, stroke, fill_opacity), shape
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        return svg_circle(element_id, cx + offset_x, cy + offset_y, radius, fill, stroke, fill_opacity), SHAPE_CIRCLE

    if shape == SHAPE_RECTANGLE:
        rect = cv2.minAreaRect(contour)
        (cx, cy), (w, h), angle = rect
        if abs(angle) < 2.0 or abs(angle - 90) < 2.0 or abs(angle + 90) < 2.0:
            if abs(angle - 90) < 2.0 or abs(angle + 90) < 2.0:
                w, h = h, w
            x = cx + offset_x - w / 2.0
            y = cy + offset_y - h / 2.0
            return svg_rect(element_id, x, y, w, h, fill, stroke, fill_opacity), shape
        box = cv2.boxPoints(rect)
        points = [(pt[0] + offset_x, pt[1] + offset_y) for pt in box]
        return svg_polygon(element_id, points, fill, stroke, fill_opacity), shape

    if shape in (SHAPE_TRIANGLE, SHAPE_POLYGON):
        perimeter = cv2.arcLength(contour, True)
        epsilon = 0.02 * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, True)
        points = [(pt[0][0] + offset_x, pt[0][1] + offset_y) for pt in approx]
        return svg_polygon(element_id, points, fill, stroke, fill_opacity), shape

    # star / irregular → path fallback
    return _contour_to_path(contour, element_id, offset_x, offset_y, fill, stroke, fill_opacity), shape


def _contour_to_path(
    contour: np.ndarray, element_id: str, offset_x: int, offset_y: int,
    fill: str, stroke: str, fill_opacity: float | None = None,
) -> str:
    """Fallback: render contour as an SVG <path> element."""

    epsilon = max(1.5, 0.01 * cv2.arcLength(contour, True))
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 3:
        approx = contour
    points = approx[:, 0, :]
    commands = [f"M {int(points[0][0] + offset_x)} {int(points[0][1] + offset_y)}"]
    for pt in points[1:]:
        commands.append(f"L {int(pt[0] + offset_x)} {int(pt[1] + offset_y)}")
    commands.append("Z")
    d = " ".join(commands)
    fill_attr = f" fill-opacity='{fill_opacity:.3f}'" if fill_opacity is not None and fill_opacity < 0.999 else ""
    return f"<path id='{element_id}' d='{d}' fill='{fill}' stroke='{stroke}'{fill_attr} />"


# ---------------------------------------------------------------------------
# Hough circle detection
# ---------------------------------------------------------------------------


def detect_circles_hough(
    gray: np.ndarray,
    min_radius: int = 6,
    max_radius: int = 80,
) -> list[tuple[int, int, int]]:
    """Detect circles via HoughCircles, returning list of (cx, cy, radius)."""

    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(min_radius * 2, 20),
        param1=100,
        param2=40,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return []
    return [(int(round(x)), int(round(y)), int(round(r))) for x, y, r in circles[0]]
