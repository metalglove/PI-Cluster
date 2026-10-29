"""
The coverage oracle: f(S) is the number of points covered by a set of circles S.
This is the monotone submodular function the algorithms maximize under |S| <= k.
"""

from typing import List
import numpy as np

from data import Point, Circle


# =============================================================================
# COVERAGE FUNCTIONS (Oracle)
# =============================================================================
# The oracle is vectorised with numpy: points are an (n, 2) float array, and a circle test is one
# array expression instead of a Python loop per point. Same float64 arithmetic, so same answers.

def as_points(points) -> np.ndarray:
    """Points as an (n, 2) float array (broadcast arrays pass through unchanged)."""
    return points if isinstance(points, np.ndarray) else np.asarray(points, dtype=float).reshape(-1, 2)

def inside(circle: Circle, pts: np.ndarray) -> np.ndarray:
    """Boolean mask of the points inside circle."""
    cx, cy, r = circle
    return (pts[:, 0] - cx) ** 2 + (pts[:, 1] - cy) ** 2 <= r ** 2

def uncovered_mask(circles: List[Circle], pts: np.ndarray) -> np.ndarray:
    """Boolean mask of the points not covered by any of circles."""
    mask = np.ones(len(pts), dtype=bool)
    for circle in circles:
        mask &= ~inside(circle, pts)
    return mask


def compute_coverage(circles: List[Circle], points: List[Point]) -> int:
    """
    Compute f(S): the number of unique points covered by a set of circles.
    This is the submodular function we're maximizing.
    """
    if not circles:
        return 0

    pts = as_points(points)
    return int(len(pts) - np.count_nonzero(uncovered_mask(circles, pts)))


def compute_marginal_gain(
    candidate: Circle,
    current_set: List[Circle],
    points: List[Point]
) -> int:
    """
    Compute marginal gain: Δf(c|S) = f(S ∪ {c}) - f(S)
    This is the number of NEW points covered by adding candidate to current_set.
    """
    # Points inside the candidate that no circle of current_set covers yet
    pts = as_points(points)
    return int(np.count_nonzero(inside(candidate, pts) & uncovered_mask(current_set, pts)))
