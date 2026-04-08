"""SVG template library and lightweight semantic template matching."""

from __future__ import annotations

import cv2
import numpy as np

from .icon_processor import IconComplexity

_TEMPLATE_ROLE_PREFIX = 'svg_template:'

_TEXT_TEMPLATE_KEYWORDS = (
    ('database', ('database', 'data sources', 'sources', 'source data', 'source', 'omics data', 'input data', 'data')),
    ('clock', ('time', 'times', 'timeline', 'year', 'years', 'yr', 'yrs', 'month', 'months')),
    ('cohort', ('cohort', 'cohorts', 'patient', 'patients', 'population', 'group', 'groups', 'multi-cohort')),
    ('document', ('document', 'documents', 'report', 'reports', 'paper', 'papers', 'record', 'records', 'file', 'files')),
    ('radial_icon', ('fan', 'radial', 'spoke', 'hub')),
)

SVG_TEMPLATES = {
    'database': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="none">
    <path d="M10,25 v50 a40,15 0 0,0 80,0 v-50" fill="{fill}" opacity="0.8" stroke="#333333" stroke-width="2"/>
    <ellipse cx="50" cy="25" rx="40" ry="15" fill="{fill}" stroke="#333333" stroke-width="2"/>
    <ellipse cx="50" cy="50" rx="40" ry="15" fill="none" stroke="#333333" stroke-width="2" stroke-dasharray="4,4"/>
</svg>
''',
    'clock': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <circle cx="50" cy="50" r="45" fill="{fill}" opacity="0.2" stroke="#333333" stroke-width="4"/>
    <circle cx="50" cy="50" r="45" fill="none" stroke="#333333" stroke-width="4"/>
    <polyline points="50,20 50,50 70,65" fill="none" stroke="#333333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="50" cy="50" r="5" fill="#333333"/>
</svg>
''',
    'cohort': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <circle cx="65" cy="30" r="18" fill="{fill}" opacity="0.4" stroke="#333333" stroke-width="2"/>
    <path d="M40,90 A25,25 0 0,1 90,90" fill="{fill}" opacity="0.4" stroke="#333333" stroke-width="2"/>
    <circle cx="35" cy="38" r="20" fill="{fill}" stroke="#333333" stroke-width="2"/>
    <path d="M5,95 A30,30 0 0,1 65,95" fill="{fill}" stroke="#333333" stroke-width="2"/>
</svg>
''',
    'document': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <path d="M20,10 L60,10 L80,30 L80,90 L20,90 Z" fill="{fill}" opacity="0.8" stroke="#333333" stroke-width="3"/>
    <path d="M60,10 L60,30 L80,30" fill="none" stroke="#333333" stroke-width="3" stroke-linejoin="round"/>
    <line x1="35" y1="45" x2="65" y2="45" stroke="#333333" stroke-width="3" stroke-linecap="round"/>
    <line x1="35" y1="60" x2="65" y2="60" stroke="#333333" stroke-width="3" stroke-linecap="round"/>
    <line x1="35" y1="75" x2="50" y2="75" stroke="#333333" stroke-width="3" stroke-linecap="round"/>
</svg>
''',
    'hetero_graph': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <rect x="8" y="12" width="84" height="76" rx="10" fill="{fill}" opacity="0.18" stroke="#334155" stroke-width="2"/>
    <line x1="24" y1="28" x2="48" y2="46" stroke="#64748b" stroke-width="2.5"/>
    <line x1="48" y1="46" x2="74" y2="30" stroke="#64748b" stroke-width="2.5"/>
    <line x1="48" y1="46" x2="72" y2="68" stroke="#64748b" stroke-width="2.5"/>
    <circle cx="24" cy="28" r="9" fill="#5b8def" stroke="#334155" stroke-width="2"/>
    <circle cx="48" cy="46" r="10" fill="#d98b3f" stroke="#334155" stroke-width="2"/>
    <circle cx="74" cy="30" r="9" fill="#c06c84" stroke="#334155" stroke-width="2"/>
    <circle cx="72" cy="68" r="9" fill="#7abf6a" stroke="#334155" stroke-width="2"/>
    <rect x="18" y="74" width="64" height="8" rx="4" fill="#ffffff" opacity="0.65"/>
</svg>
''',
    'heatmap': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <rect x="10" y="12" width="62" height="62" rx="6" fill="#fffaf2" stroke="#334155" stroke-width="2"/>
    <rect x="16" y="18" width="10" height="10" fill="#4f7cac"/>
    <rect x="28" y="18" width="10" height="10" fill="#7aa6d1"/>
    <rect x="40" y="18" width="10" height="10" fill="#d7e6f5"/>
    <rect x="52" y="18" width="10" height="10" fill="#f3c7a0"/>
    <rect x="16" y="30" width="10" height="10" fill="#6b9bd0"/>
    <rect x="28" y="30" width="10" height="10" fill="#bcd2ea"/>
    <rect x="40" y="30" width="10" height="10" fill="#f6e3c6"/>
    <rect x="52" y="30" width="10" height="10" fill="#df8f53"/>
    <rect x="16" y="42" width="10" height="10" fill="#cfddee"/>
    <rect x="28" y="42" width="10" height="10" fill="#f7eddc"/>
    <rect x="40" y="42" width="10" height="10" fill="#f2c18f"/>
    <rect x="52" y="42" width="10" height="10" fill="#c97741"/>
    <rect x="16" y="54" width="10" height="10" fill="#f8f4eb"/>
    <rect x="28" y="54" width="10" height="10" fill="#f1d3b0"/>
    <rect x="40" y="54" width="10" height="10" fill="#df9b62"/>
    <rect x="52" y="54" width="10" height="10" fill="#7b4d2a"/>
    <rect x="78" y="20" width="8" height="11" rx="2" fill="#4f7cac" stroke="#334155" stroke-width="1"/>
    <rect x="78" y="31" width="8" height="11" rx="2" fill="#bcd2ea" stroke="#334155" stroke-width="1"/>
    <rect x="78" y="42" width="8" height="11" rx="2" fill="#f3c7a0" stroke="#334155" stroke-width="1"/>
    <rect x="78" y="53" width="8" height="11" rx="2" fill="#7b4d2a" stroke="#334155" stroke-width="1"/>
</svg>
''',
    'survival_curve': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <rect x="8" y="10" width="84" height="78" rx="8" fill="#fffaf5" stroke="#334155" stroke-width="2"/>
    <line x1="18" y1="18" x2="18" y2="78" stroke="#334155" stroke-width="2.5"/>
    <line x1="18" y1="78" x2="86" y2="78" stroke="#334155" stroke-width="2.5"/>
    <path d="M18,28 L28,34 L40,42 L52,52 L64,63 L78,72" fill="none" stroke="#c06c84" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M18,24 L28,26 L40,30 L52,34 L64,38 L78,44" fill="none" stroke="#5b8def" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="74" cy="26" r="3" fill="#5b8def"/>
    <circle cx="74" cy="36" r="3" fill="#c06c84"/>
</svg>
''',
    'feature_panel': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <rect x="6" y="6" width="88" height="88" rx="10" fill="{fill}" opacity="0.24" stroke="#6b4c7a" stroke-width="2"/>
    <rect x="55" y="10" width="20" height="10" rx="3" fill="#355c9a"/>
    <rect x="77" y="10" width="10" height="10" rx="3" fill="#6fa1da"/>
    <rect x="15" y="24" width="18" height="10" rx="2" fill="#f6efe7" stroke="#8b6e5c" stroke-width="1.2"/>
    <rect x="38" y="24" width="18" height="10" rx="2" fill="#f0e1d4" stroke="#8b6e5c" stroke-width="1.2"/>
    <rect x="22" y="40" width="36" height="10" rx="3" fill="#f9f4ef" stroke="#8b6e5c" stroke-width="1.2"/>
    <path d="M72,34 L84,34 L90,40 L84,46 L72,46 Z" fill="#6e3f86"/>
    <circle cx="49" cy="62" r="7" fill="#4f86bf" stroke="#355c7d" stroke-width="1.5"/>
    <path d="M16,70 C28,62 38,62 50,70 S72,78 84,70" fill="none" stroke="#8f6b5d" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M80,54 L80,90" fill="none" stroke="#6e3f86" stroke-width="3" stroke-linecap="round"/>
</svg>
''',
    'stack_panel': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
    <rect x="34" y="6" width="32" height="10" rx="3" fill="#4b86c2"/>
    <rect x="26" y="26" width="48" height="10" rx="3" fill="#6e5a4e"/>
    <rect x="18" y="42" width="64" height="10" rx="3" fill="#6186bc"/>
    <rect x="30" y="58" width="40" height="10" rx="3" fill="#9c6791"/>
    <rect x="36" y="76" width="28" height="10" rx="3" fill="#c6884d"/>
    <path d="M50,16 L50,26 M50,36 L50,42 M50,52 L50,58 M50,68 L50,76" fill="none" stroke="#46515f" stroke-width="2.2" stroke-linecap="round"/>
</svg>
''',
    'radial_icon': '''
<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 135 429" preserveAspectRatio="xMidYMid meet">
    <path d="M25.33,18.98 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M22.03,84.79 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M23.10,139.55 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M24.30,169.27 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M23.66,195.95 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M33.74,197.81 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M27.06,216.94 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M48.14,227.65 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M45.64,246.43 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M30.43,246.77 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M21.00,290.05 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M44.63,309.24 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M17.78,413.95 L124.99,211.17" fill="none" stroke="#374151" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="124.99" cy="211.17" r="4.5" fill="#d7263d" />
</svg>
''',
}

# Backward-compatible alias for the existing replacement pipeline.
SVG_TEMPLATES['standard_node'] = SVG_TEMPLATES['cohort']


_TEMPLATE_INSET_RATIOS = {
    'database': (0.88, 0.88),
    'clock': (0.84, 0.84),
    'cohort': (0.84, 0.84),
    'document': (0.84, 0.84),
    'hetero_graph': (0.72, 0.68),
    'heatmap': (0.66, 0.68),
    'survival_curve': (0.60, 0.58),
    'feature_panel': (0.74, 0.70),
    'stack_panel': (0.58, 0.70),
    'radial_icon': (0.92, 0.92),
}


def append_template_role(component_role: str | None, template_name: str) -> str:
    token = f'{_TEMPLATE_ROLE_PREFIX}{template_name}'
    if not component_role:
        return token
    parts = [part for part in str(component_role).split('|') if part]
    if token not in parts:
        parts.append(token)
    return '|'.join(parts)


def extract_template_name(component_role: str | None) -> str | None:
    if not component_role:
        return None
    for part in str(component_role).split('|'):
        if part.startswith(_TEMPLATE_ROLE_PREFIX):
            return part[len(_TEMPLATE_ROLE_PREFIX):]
    return None


def infer_template_from_text_context(text: str | None) -> str | None:
    if not text:
        return None
    lowered = str(text).lower()
    for template_name, keywords in _TEXT_TEMPLATE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return template_name
    return None


def match_svg_template(crop: np.ndarray, complexity: IconComplexity) -> str | None:
    if crop.size == 0:
        return None
    height, width = crop.shape[:2]
    area = width * height
    allow_radial_icon = _is_radial_template_candidate_bbox(width, height)
    if area < 400 or (area > 25000 and not allow_radial_icon):
        return None
    if _looks_like_radial_icon(crop, complexity):
        return 'radial_icon'
    if _looks_like_database_cylinder(crop, complexity):
        return 'database'
    if _looks_like_clock_icon(crop, complexity):
        return 'clock'
    if _looks_like_document_icon(crop, complexity):
        return 'document'
    if _looks_like_cohort_icon(crop, complexity):
        return 'cohort'
    return None


def _is_radial_template_candidate_bbox(width: int, height: int) -> bool:
    area = width * height
    aspect_ratio = max(width, height) / max(min(width, height), 1)
    return (
        area <= 90000
        and height >= 160
        and width >= 60
        and width <= 260
        and aspect_ratio >= 2.0
    )


def render_svg_template(
    template_name: str,
    bbox: list[int],
    *,
    element_id: str,
    node_id: str,
    fill: str | None = None,
    stroke: str | None = None,
) -> str | None:
    del stroke
    x1, y1, x2, y2 = bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    normalized_name = 'cohort' if template_name == 'standard_node' else template_name
    template = SVG_TEMPLATES.get(normalized_name)
    if template is None:
        return None
    inset_width_ratio, inset_height_ratio = _TEMPLATE_INSET_RATIOS.get(normalized_name, (0.84, 0.84))
    inner_width = max(int(round(width * inset_width_ratio)), 1)
    inner_height = max(int(round(height * inset_height_ratio)), 1)
    inner_x = x1 + (width - inner_width) // 2
    inner_y = y1 + (height - inner_height) // 2
    fill_color = fill or '#d9e6f2'
    svg = template.format(x=inner_x, y=inner_y, w=inner_width, h=inner_height, fill=fill_color)
    return (
        f"<g id='{element_id}' class='svg-template' data-node-id='{node_id}' data-template-name='{normalized_name}'>"
        f"{svg}</g>"
    )


def _looks_like_clock_icon(crop: np.ndarray, complexity: IconComplexity) -> bool:
    height, width = crop.shape[:2]
    aspect_ratio = width / max(height, 1)
    if not 0.75 <= aspect_ratio <= 1.25:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(min(width, height) // 3, 8),
        param1=80,
        param2=18,
        minRadius=max(min(width, height) // 5, 6),
        maxRadius=max(min(width, height) // 2, 12),
    )
    if circles is None:
        return False
    dark_ratio = float(np.count_nonzero(gray < 180)) / max(gray.size, 1)
    return dark_ratio >= 0.05 and (complexity.black_fill_risk or complexity.variance >= 1200.0)


def _looks_like_database_cylinder(crop: np.ndarray, complexity: IconComplexity) -> bool:
    height, width = crop.shape[:2]
    aspect_ratio = width / max(height, 1)
    if not 0.55 <= aspect_ratio <= 1.45:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    top_band = float(np.mean(edges[: max(height // 4, 1), :] > 0))
    bottom_band = float(np.mean(edges[-max(height // 4, 1):, :] > 0))
    mid_band = float(np.mean(edges[height // 3 : max((height * 2) // 3, (height // 3) + 1), :] > 0))
    return (
        complexity.variance >= 1200.0
        and complexity.contour_count <= 4
        and top_band >= 0.025
        and bottom_band >= 0.025
        and mid_band <= 0.08
    )


def _looks_like_document_icon(crop: np.ndarray, complexity: IconComplexity) -> bool:
    height, width = crop.shape[:2]
    aspect_ratio = width / max(height, 1)
    if not 0.6 <= aspect_ratio <= 1.15:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False
    largest = max(contours, key=cv2.contourArea)
    perimeter = max(cv2.arcLength(largest, True), 1.0)
    approx = cv2.approxPolyDP(largest, max(2.0, perimeter * 0.03), True)
    upper_right_density = float(np.mean(edges[: max(height // 3, 1), max((width * 2) // 3, 1):] > 0))
    return 4 <= len(approx) <= 6 and complexity.contour_count <= 8 and upper_right_density >= 0.04


def _looks_like_cohort_icon(crop: np.ndarray, complexity: IconComplexity) -> bool:
    height, width = crop.shape[:2]
    aspect_ratio = width / max(height, 1)
    if not 0.7 <= aspect_ratio <= 1.35:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.1,
        minDist=max(min(width, height) // 5, 6),
        param1=80,
        param2=10,
        minRadius=3,
        maxRadius=max(min(width, height) // 4, 10),
    )
    circle_count = 0 if circles is None else circles.shape[1]
    return complexity.significant_colors >= 3 and complexity.contour_count >= 6 and circle_count >= 2


def _looks_like_radial_icon(crop: np.ndarray, complexity: IconComplexity) -> bool:
    height, width = crop.shape[:2]
    if not _is_radial_template_candidate_bbox(width, height):
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    left_band_width = max(int(width * 0.35), 1)
    left_band = hsv[:, :left_band_width]
    circle_mask = np.where(
        (left_band[:, :, 1] >= 40)
        & (left_band[:, :, 2] >= 50)
        & (left_band[:, :, 2] <= 220),
        255,
        0,
    ).astype(np.uint8)
    circle_mask = cv2.morphologyEx(circle_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    circle_mask = cv2.morphologyEx(circle_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(circle_mask, connectivity=8)
    circle_centers: list[tuple[float, float]] = []
    for label in range(1, num_labels):
        x, y, component_width, component_height, area = stats[label]
        fill_ratio = area / max(component_width * component_height, 1)
        if area < 35 or area > max(int(height * width * 0.03), 1200):
            continue
        if component_width < 6 or component_height < 6:
            continue
        aspect_ratio = component_width / max(component_height, 1)
        if not 0.45 <= aspect_ratio <= 1.9:
            continue
        if fill_ratio < 0.30:
            continue
        center_x, center_y = centroids[label]
        circle_centers.append((float(center_x), float(center_y)))
    if len(circle_centers) < 6:
        return False

    xs = [center[0] for center in circle_centers]
    ys = sorted(center[1] for center in circle_centers)
    if np.std(xs) > width * 0.10:
        return False
    if ys[-1] - ys[0] < height * 0.45:
        return False

    line_mask = np.where(gray < 205, 255, 0).astype(np.uint8)
    line_mask[:, :left_band_width] = 0
    line_pixels = int(np.count_nonzero(line_mask))
    hub_pixels = int(np.count_nonzero(line_mask[:, int(width * 0.72):]))
    if line_pixels < max(height * 0.18, 60):
        return False
    if hub_pixels < max(height * 0.03, 10):
        return False
    return complexity.contour_count >= 6 or complexity.variance >= 500.0
