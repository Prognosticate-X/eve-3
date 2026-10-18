"""Grid Tasks: L1 Discrete Visual Grid Transformations (ARC-Style).

Implements Phase 9 L1 Discrete Perception Substrate:
- 2D integer matrix representations (colors / symbols 0..9).
- Programmatic oracles for spatial transformations: rotation, reflection, gravity, replication.
- Conversion to standardized EVE-3 Task models with visible and hidden examples.
"""

from dataclasses import dataclass
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.models import Task


class Grid:
    """Represents a 2D discrete visual grid with integer color cells."""

    def __init__(self, cells: List[List[int]]):
        self.cells = [list(row) for row in cells]
        self.height = len(self.cells)
        self.width = len(self.cells[0]) if self.height > 0 else 0

    def to_list(self) -> List[List[int]]:
        return [list(row) for row in self.cells]

    @classmethod
    def from_list(cls, data: List[List[int]]) -> "Grid":
        return cls(data)

    def rotate90_cw(self) -> "Grid":
        """Rotate grid 90 degrees clockwise."""
        if self.height == 0 or self.width == 0:
            return Grid([])
        new_cells = [
            [self.cells[self.height - 1 - r][c] for r in range(self.height)]
            for c in range(self.width)
        ]
        return Grid(new_cells)

    def reflect_horizontal(self) -> "Grid":
        """Reflect grid horizontally (left-right flip)."""
        return Grid([list(reversed(row)) for row in self.cells])

    def reflect_vertical(self) -> "Grid":
        """Reflect grid vertically (up-down flip)."""
        return Grid(list(reversed([list(row) for row in self.cells])))

    def gravity_down(self) -> "Grid":
        """Simulate downward gravity: non-zero colors drop to bottom of column."""
        new_cells = [[0] * self.width for _ in range(self.height)]
        for c in range(self.width):
            col_vals = [self.cells[r][c] for r in range(self.height) if self.cells[r][c] != 0]
            zeros_needed = self.height - len(col_vals)
            for r in range(zeros_needed):
                new_cells[r][c] = 0
            for idx, val in enumerate(col_vals):
                new_cells[zeros_needed + idx][c] = val
        return Grid(new_cells)

    def color_shift(self, offset: int = 1) -> "Grid":
        """Shift non-zero colors by fixed offset mod 9."""
        new_cells = [
            [((val + offset - 1) % 8) + 1 if val != 0 else 0 for val in row]
            for row in self.cells
        ]
        return Grid(new_cells)

    def replicate2x2(self) -> "Grid":
        """Tile the grid into a 2x2 macro pattern."""
        new_cells = []
        for row in self.cells:
            new_cells.append(row + row)
        for row in self.cells:
            new_cells.append(row + row)
        return Grid(new_cells)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Grid):
            return False
        return self.cells == other.cells

    def __repr__(self) -> str:
        return f"Grid({self.height}x{self.width}, cells={self.cells})"


def generate_random_grid(h: int, w: int, num_colors: int = 3, density: float = 0.5, seed: Optional[int] = None) -> Grid:
    """Generate a random colored grid."""
    rng = random.Random(seed)
    cells = []
    for _ in range(h):
        row = []
        for _ in range(w):
            if rng.random() < density:
                row.append(rng.randint(1, num_colors))
            else:
                row.append(0)
        cells.append(row)
    return Grid(cells)


class GridTaskSuite:
    """Generates L1 visual transformation tasks with exact programmatic oracles."""

    @staticmethod
    def create_grid_task(
        task_id: str,
        name: str,
        description: str,
        transform_fn: Callable[[Grid], Grid],
        seed: int = 42,
    ) -> Task:
        """Construct an EVE-3 Task from a programmatic 2D grid transformation."""
        rng = random.Random(seed)
        visible_examples: List[Dict[str, Any]] = []
        hidden_tests: List[Dict[str, Any]] = []

        # Generate 2 visible training examples (3x3 and 4x4)
        for i, (h, w) in enumerate([(3, 3), (4, 4)]):
            inp = generate_random_grid(h, w, seed=rng.randint(1, 10000))
            out = transform_fn(inp)
            visible_examples.append({"input": inp.to_list(), "output": out.to_list()})

        # Generate 4 hidden test examples with varying dimensions
        for i, (h, w) in enumerate([(2, 2), (3, 5), (5, 3), (5, 5)]):
            inp = generate_random_grid(h, w, seed=rng.randint(1, 10000))
            out = transform_fn(inp)
            hidden_tests.append({"input": inp.to_list(), "output": out.to_list()})

        return Task(
            task_id=task_id,
            task_family="grid_perception",
            description=description,
            visible_examples=visible_examples,
            hidden_tests=hidden_tests,
            metadata={"domain": "L1_discrete_grid", "name": name},
            source="benchmark",
        )

    @classmethod
    def get_standard_suite(cls) -> List[Task]:
        """Return the standard benchmark suite of 4 L1 discrete grid tasks."""
        return [
            cls.create_grid_task(
                "grid_rotate_90",
                "Grid Rotate 90 CW",
                "Rotate 2D discrete visual grid 90 degrees clockwise",
                lambda g: g.rotate90_cw(),
                seed=101,
            ),
            cls.create_grid_task(
                "grid_reflect_h",
                "Grid Reflect Horizontal",
                "Reflect 2D discrete visual grid horizontally across vertical axis",
                lambda g: g.reflect_horizontal(),
                seed=202,
            ),
            cls.create_grid_task(
                "grid_gravity_down",
                "Grid Gravity Down",
                "Drop all foreground blocks downwards to bottom of each column",
                lambda g: g.gravity_down(),
                seed=303,
            ),
            cls.create_grid_task(
                "grid_color_shift",
                "Grid Color Shift",
                "Permute non-zero colors by fixed integer offset mod 8",
                lambda g: g.color_shift(1),
                seed=404,
            ),
        ]
