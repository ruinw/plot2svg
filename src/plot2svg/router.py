"""Grid-based orthogonal router for flowchart connectors."""

from __future__ import annotations

import heapq
import math


class FlowchartRouter:
    """Route connector paths on a coarse grid using A* with turn penalties."""

    _DIRECTIONS: tuple[tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))

    def __init__(self, width: int, height: int, grid_size: int = 8, turn_penalty: float = 5.0) -> None:
        self.width = max(int(width), 1)
        self.height = max(int(height), 1)
        self.grid_size = max(int(grid_size), 4)
        self.turn_penalty = float(turn_penalty)
        self.cols = max(int(math.ceil(self.width / self.grid_size)) + 1, 2)
        self.rows = max(int(math.ceil(self.height / self.grid_size)) + 1, 2)
        self.obstacles: set[tuple[int, int]] = set()

    def add_obstacle(self, bbox: list[int] | list[float], padding: int = 12) -> None:
        min_x = max(0, int(math.floor((float(bbox[0]) - padding) / self.grid_size)))
        min_y = max(0, int(math.floor((float(bbox[1]) - padding) / self.grid_size)))
        max_x = min(self.cols - 1, int(math.ceil((float(bbox[2]) + padding) / self.grid_size)))
        max_y = min(self.rows - 1, int(math.ceil((float(bbox[3]) + padding) / self.grid_size)))
        for row in range(min_y, max_y + 1):
            for col in range(min_x, max_x + 1):
                self.obstacles.add((col, row))

    def find_orthogonal_path(self, start_pt: list[float], end_pt: list[float]) -> list[list[float]] | None:
        start = self._point_to_grid(start_pt)
        end = self._point_to_grid(end_pt)
        if start == end:
            return [start_pt[:], end_pt[:]]

        blocked = set(self.obstacles)
        blocked.discard(start)
        blocked.discard(end)

        if self._direct_grid_segment_clear(start, end, blocked):
            return [start_pt[:], end_pt[:]]

        start_state = (start[0], start[1], -1)
        frontier: list[tuple[float, float, int, int, int]] = []
        heapq.heappush(frontier, (self._heuristic(start, end), 0.0, start[0], start[1], -1))
        best_cost: dict[tuple[int, int, int], float] = {start_state: 0.0}
        parents: dict[tuple[int, int, int], tuple[int, int, int] | None] = {start_state: None}
        end_state: tuple[int, int, int] | None = None

        while frontier:
            _priority, cost, col, row, direction_idx = heapq.heappop(frontier)
            state = (col, row, direction_idx)
            if cost > best_cost.get(state, float('inf')) + 1e-9:
                continue
            if (col, row) == end:
                end_state = state
                break

            for next_direction_idx in range(len(self._DIRECTIONS)):
                dx, dy = self._DIRECTIONS[next_direction_idx]
                next_col = col + dx
                next_row = row + dy
                if not (0 <= next_col < self.cols and 0 <= next_row < self.rows):
                    continue
                if (next_col, next_row) in blocked and (next_col, next_row) != end:
                    continue
                step_cost = 1.0
                if direction_idx != -1 and direction_idx != next_direction_idx:
                    step_cost += self.turn_penalty
                step_cost += self._border_penalty(next_col, next_row, end)
                next_cost = cost + step_cost
                next_state = (next_col, next_row, next_direction_idx)
                if next_cost >= best_cost.get(next_state, float('inf')) - 1e-9:
                    continue
                best_cost[next_state] = next_cost
                parents[next_state] = state
                priority = next_cost + self._heuristic((next_col, next_row), end)
                heapq.heappush(frontier, (priority, next_cost, next_col, next_row, next_direction_idx))

        if end_state is None:
            return None

        cells: list[tuple[int, int]] = []
        current: tuple[int, int, int] | None = end_state
        while current is not None:
            cells.append((current[0], current[1]))
            current = parents.get(current)
        cells.reverse()
        return self._cells_to_path(cells, start_pt, end_pt)

    def _cells_to_path(
        self,
        cells: list[tuple[int, int]],
        start_pt: list[float],
        end_pt: list[float],
    ) -> list[list[float]]:
        if len(cells) <= 1:
            return [start_pt[:], end_pt[:]]

        lattice_points = [self._grid_to_point(cell) for cell in cells]
        path: list[list[float]] = [start_pt[:]]

        first_step = lattice_points[1]
        if abs(first_step[0] - path[-1][0]) > 1e-6 and abs(first_step[1] - path[-1][1]) > 1e-6:
            if cells[1][0] != cells[0][0]:
                path.append([first_step[0], path[-1][1]])
            else:
                path.append([path[-1][0], first_step[1]])
        path.append(first_step)

        for point in lattice_points[2:-1]:
            path.append(point)

        if len(lattice_points) >= 2:
            penultimate = lattice_points[-2]
            if abs(end_pt[0] - penultimate[0]) > 1e-6 and abs(end_pt[1] - penultimate[1]) > 1e-6:
                if cells[-1][0] != cells[-2][0]:
                    path.append([penultimate[0], end_pt[1]])
                else:
                    path.append([end_pt[0], penultimate[1]])
        path.append(end_pt[:])
        return _simplify_orthogonal_path(path)

    def _point_to_grid(self, point: list[float]) -> tuple[int, int]:
        col = int(round(float(point[0]) / self.grid_size))
        row = int(round(float(point[1]) / self.grid_size))
        return min(max(col, 0), self.cols - 1), min(max(row, 0), self.rows - 1)

    def _grid_to_point(self, cell: tuple[int, int]) -> list[float]:
        x = min(max(cell[0] * self.grid_size, 0), self.width)
        y = min(max(cell[1] * self.grid_size, 0), self.height)
        return [float(x), float(y)]

    def _heuristic(self, cell: tuple[int, int], goal: tuple[int, int]) -> float:
        return float(abs(cell[0] - goal[0]) + abs(cell[1] - goal[1]))

    def _border_penalty(self, col: int, row: int, goal: tuple[int, int]) -> float:
        if (col, row) == goal:
            return 0.0
        edge_distance = min(col, row, self.cols - 1 - col, self.rows - 1 - row)
        if edge_distance <= 1:
            return 2.5
        if edge_distance == 2:
            return 1.0
        return 0.0

    def _direct_grid_segment_clear(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        if start[0] == end[0]:
            row_start, row_end = sorted((start[1], end[1]))
            return all((start[0], row) not in blocked for row in range(row_start, row_end + 1))
        if start[1] == end[1]:
            col_start, col_end = sorted((start[0], end[0]))
            return all((col, start[1]) not in blocked for col in range(col_start, col_end + 1))
        return False


def _simplify_orthogonal_path(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for point in points:
        if not deduped or not _same_point(deduped[-1], point):
            deduped.append([float(point[0]), float(point[1])])
    if len(deduped) <= 2:
        return deduped

    simplified = [deduped[0]]
    for index in range(1, len(deduped) - 1):
        prev = simplified[-1]
        curr = deduped[index]
        nxt = deduped[index + 1]
        if _collinear(prev, curr, nxt):
            continue
        simplified.append(curr)
    simplified.append(deduped[-1])
    return simplified


def _same_point(left: list[float], right: list[float], eps: float = 1e-6) -> bool:
    return abs(left[0] - right[0]) <= eps and abs(left[1] - right[1]) <= eps


def _collinear(first: list[float], second: list[float], third: list[float], eps: float = 1e-6) -> bool:
    return (
        abs(first[0] - second[0]) <= eps and abs(second[0] - third[0]) <= eps
    ) or (
        abs(first[1] - second[1]) <= eps and abs(second[1] - third[1]) <= eps
    )
