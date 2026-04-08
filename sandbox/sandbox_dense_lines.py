from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import random
import xml.sax.saxutils as saxutils

import cv2
import numpy as np


# =============================
# Tunable parameters
# =============================
DILATE_KERNEL = 3
DILATE_ITERATIONS = 1
SATURATION_MAX = 90
VALUE_MAX = 185
GRAY_THRESHOLD = 190
HOUGH_THRESHOLD = 18
MIN_LINE_LENGTH = 20      # 降低最小长度，先捕捉更多碎线段
MAX_LINE_GAP = 25         # 放宽Hough自带的断点容忍度
ANGLE_TOLERANCE_DEG = 6.0
ENDPOINT_MERGE_RADIUS = 10.0
RIGHT_CLUSTER_X_RATIO = 0.72
SVG_STROKE_WIDTH = 1.4

# 新增缝合参数
COLLINEAR_ANGLE_TOLERANCE = 5.0
COLLINEAR_OFFSET_TOLERANCE = 8.0
COLLINEAR_GAP_TOLERANCE = 65.0   # 允许跨越的最大断裂距离

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / 'A.png'
DEBUG_SKELETON = BASE_DIR / 'debug_01_skeleton.png'
DEBUG_EXTRACTED = BASE_DIR / 'debug_02_extracted_lines.png'
OUTPUT_SVG = BASE_DIR / 'slice_A.svg'


@dataclass
class LineSegment:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle_deg(self) -> float:
        angle = math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))
        return angle

    def normalized(self) -> 'LineSegment':
        if (self.x1, self.y1) <= (self.x2, self.y2):
            return self
        return LineSegment(self.x2, self.y2, self.x1, self.y1)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (int(round(self.x1)), int(round(self.y1)), int(round(self.x2)), int(round(self.y2)))


def main() -> None:
    image = load_image(INPUT_PATH)
    line_mask = build_line_mask(image)
    skeleton = skeletonize(line_mask)
    lines = detect_lines(skeleton)
    # 核心新增步骤：在聚类收束之前，先把断掉的共线片段缝合
    joined_lines = join_collinear_lines(lines)
    merged_lines = merge_lines(joined_lines, image.shape[1])
    render_debug_outputs(image, skeleton, merged_lines)
    write_svg(merged_lines, image.shape[1], image.shape[0], OUTPUT_SVG)
    print(f'Extracted {len(merged_lines)} merged lines from {INPUT_PATH.name}')
    print(f'Generated: {DEBUG_SKELETON.name}, {DEBUG_EXTRACTED.name}, {OUTPUT_SVG.name}')


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f'Failed to load {path}')
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        bgr = image[:, :, :3].astype(np.float32)
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        white = np.full_like(bgr, 255.0)
        composited = bgr * alpha + white * (1.0 - alpha)
        return np.clip(composited, 0, 255).astype(np.uint8)
    return image[:, :, :3]


def build_line_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    low_sat_dark = cv2.inRange(hsv, np.array([0, 0, 0], dtype=np.uint8), np.array([180, SATURATION_MAX, VALUE_MAX], dtype=np.uint8))
    _, gray_mask = cv2.threshold(gray, GRAY_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    mask = cv2.bitwise_and(low_sat_dark, gray_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (DILATE_KERNEL, DILATE_KERNEL))
    mask = cv2.dilate(mask, kernel, iterations=DILATE_ITERATIONS)
    return mask


def skeletonize(mask: np.ndarray) -> np.ndarray:
    work = mask.copy()
    skeleton = np.zeros_like(work)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while True:
        opened = cv2.morphologyEx(work, cv2.MORPH_OPEN, kernel)
        residue = cv2.subtract(work, opened)
        skeleton = cv2.bitwise_or(skeleton, residue)
        work = cv2.erode(work, kernel)
        if cv2.countNonZero(work) == 0:
            break
    return skeleton


def detect_lines(skeleton: np.ndarray) -> list[LineSegment]:
    raw_lines = cv2.HoughLinesP(
        skeleton,
        rho=1,
        theta=np.pi / 180.0,
        threshold=HOUGH_THRESHOLD,
        minLineLength=MIN_LINE_LENGTH,
        maxLineGap=MAX_LINE_GAP,
    )
    if raw_lines is None:
        return []
    segments = [LineSegment(float(l[0][0]), float(l[0][1]), float(l[0][2]), float(l[0][3])).normalized() for l in raw_lines]
    return segments


def join_collinear_lines(segments: list[LineSegment]) -> list[LineSegment]:
    """核心算法：递归缝合共线片段"""
    current_segments = list(segments)
    merged = True
    while merged:
        merged = False
        next_segments = []
        while current_segments:
            base = current_segments.pop(0)
            absorbed = False
            for i, other in enumerate(current_segments):
                if is_collinear(base, other):
                    # 如果共线，提取四个端点
                    pts = [(base.x1, base.y1), (base.x2, base.y2), (other.x1, other.y1), (other.x2, other.y2)]
                    # 找到距离最远的两个点作为新的合并线段
                    max_dist = -1
                    best_pair = (pts[0], pts[1])
                    for p1 in pts:
                        for p2 in pts:
                            d = point_distance(p1, p2)
                            if d > max_dist:
                                max_dist = d
                                best_pair = (p1, p2)
                    
                    new_line = LineSegment(best_pair[0][0], best_pair[0][1], best_pair[1][0], best_pair[1][1]).normalized()
                    current_segments.pop(i)
                    current_segments.insert(0, new_line)
                    absorbed = True
                    merged = True
                    break
            if not absorbed:
                next_segments.append(base)
        current_segments = next_segments
    
    # 过滤掉依然太短的碎屑
    return [s for s in current_segments if s.length >= MIN_LINE_LENGTH]


def is_collinear(s1: LineSegment, s2: LineSegment) -> bool:
    # 1. 角度差检验
    if angle_distance(s1.angle_deg, s2.angle_deg) > COLLINEAR_ANGLE_TOLERANCE:
        return False
        
    # 2. 垂直偏移检验 (点到直线的距离)
    # 直线方程 Ax + By + C = 0
    A = s1.y2 - s1.y1
    B = s1.x1 - s1.x2
    C = s1.x2 * s1.y1 - s1.x1 * s1.y2
    norm = math.hypot(A, B)
    if norm < 1e-5: return False
    
    d1 = abs(A * s2.x1 + B * s2.y1 + C) / norm
    d2 = abs(A * s2.x2 + B * s2.y2 + C) / norm
    if max(d1, d2) > COLLINEAR_OFFSET_TOLERANCE:
        return False
        
    # 3. 断裂间距检验 (最近端点距离)
    gaps = [
        point_distance((s1.x1, s1.y1), (s2.x1, s2.y1)),
        point_distance((s1.x1, s1.y1), (s2.x2, s2.y2)),
        point_distance((s1.x2, s1.y2), (s2.x1, s2.y1)),
        point_distance((s1.x2, s1.y2), (s2.x2, s2.y2))
    ]
    # 只要这四个距离中最小的一个在容忍范围内，就说明是可以缝合的连贯线
    if min(gaps) > COLLINEAR_GAP_TOLERANCE:
        return False
        
    return True


def merge_lines(segments: list[LineSegment], image_width: int) -> list[LineSegment]:
    if not segments:
        return []
    right_threshold = image_width * RIGHT_CLUSTER_X_RATIO
    right_points = [(seg.x2, seg.y2) for seg in segments if seg.x2 >= right_threshold]
    if right_points:
        right_center = (
            sum(point[0] for point in right_points) / len(right_points),
            sum(point[1] for point in right_points) / len(right_points),
        )
    else:
        right_center = None

    merged: list[LineSegment] = []
    for segment in segments:
        x1, y1, x2, y2 = segment.x1, segment.y1, segment.x2, segment.y2
        if right_center is not None and point_distance((x2, y2), right_center) <= ENDPOINT_MERGE_RADIUS * 4.0:
            x2, y2 = right_center
        merged.append(LineSegment(x1, y1, x2, y2).normalized())

    merged.sort(key=lambda seg: seg.y1)
    return merged


def render_debug_outputs(image: np.ndarray, skeleton: np.ndarray, lines: list[LineSegment]) -> None:
    cv2.imwrite(str(DEBUG_SKELETON), skeleton)
    overlay = image.copy()
    rng = random.Random(7)
    for segment in lines:
        color = (rng.randint(40, 255), rng.randint(40, 255), rng.randint(40, 255))
        x1, y1, x2, y2 = segment.as_tuple()
        cv2.line(overlay, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        cv2.circle(overlay, (x1, y1), 3, (0, 0, 255), -1)
        cv2.circle(overlay, (x2, y2), 3, (0, 128, 255), -1)
    cv2.imwrite(str(DEBUG_EXTRACTED), overlay)


def write_svg(lines: list[LineSegment], width: int, height: int, output_path: Path) -> None:
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#ffffff' />",
    ]
    for index, segment in enumerate(lines):
        parts.append(
            f"<line id='line-{index:03d}' x1='{segment.x1:.1f}' y1='{segment.y1:.1f}' x2='{segment.x2:.1f}' y2='{segment.y2:.1f}' stroke='#4b5563' stroke-width='{SVG_STROKE_WIDTH}' stroke-linecap='round' />"
        )
    parts.append('</svg>')
    output_path.write_text('\n'.join(parts), encoding='utf-8')


def point_distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def angle_distance(left: float, right: float) -> float:
    delta = abs(left - right) % 180.0
    return min(delta, 180.0 - delta)


if __name__ == '__main__':
    main()
