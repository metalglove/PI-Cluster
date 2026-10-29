"""
Input data for the circle cover problem: points to cover, and candidate circles to cover them with.
Every algorithm runs on the same data for a given size, so their results can be compared directly.
"""

import random
from typing import List, Tuple, Optional

# Type aliases
Point = Tuple[float, float]           # (x, y)
Circle = Tuple[float, float, float]   # (cx, cy, radius)

# Configuration based on job size
SIZE_CONFIGS = {
    "small": {
        "N_POINTS": 2000,
        "N_CIRCLES": 500,
        "N_CLUSTERS": 8
    },
    "medium": {
        "N_POINTS": 25000,
        "N_CIRCLES": 2000,
        "N_CLUSTERS": 20
    },
    "large": {
        "N_POINTS": 100000,
        "N_CIRCLES": 5000,
        "N_CLUSTERS": 50
    }
}
BOUNDS = (0, 0, 1000, 1000)
RADIUS_RANGE = (30, 100)
CLUSTER_STD = 80
SEED = 42


# =============================================================================
# DATA GENERATION
# =============================================================================

def generate_clustered_points(
    n_points: int,
    n_clusters: int,
    bounds: Tuple[float, float, float, float],
    cluster_std: float = 50.0,
    seed: Optional[int] = None
) -> List[Point]:
    """
    Generate points clustered around random centers.

    Args:
        n_points: Total number of points to generate
        n_clusters: Number of cluster centers
        bounds: (min_x, min_y, max_x, max_y) bounding box
        cluster_std: Standard deviation for Gaussian distribution around centers
        seed: Random seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)

    min_x, min_y, max_x, max_y = bounds

    # Generate cluster centers
    centers = [
        (random.uniform(min_x, max_x), random.uniform(min_y, max_y))
        for _ in range(n_clusters)
    ]

    # Generate points around clusters
    points = []
    points_per_cluster = n_points // n_clusters
    remainder = n_points % n_clusters

    for i, (cx, cy) in enumerate(centers):
        # Distribute remainder points to first few clusters
        count = points_per_cluster + (1 if i < remainder else 0)
        for _ in range(count):
            x = random.gauss(cx, cluster_std)
            y = random.gauss(cy, cluster_std)
            # Clamp to bounds
            x = max(min_x, min(max_x, x))
            y = max(min_y, min(max_y, y))
            points.append((x, y))

    return points


def generate_circles(
    n_circles: int,
    bounds: Tuple[float, float, float, float],
    radius_range: Tuple[float, float],
    seed: Optional[int] = None
) -> List[Circle]:
    """
    Generate circles with random centers and variable radii.

    Args:
        n_circles: Number of circles to generate
        bounds: (min_x, min_y, max_x, max_y) bounding box for centers
        radius_range: (min_radius, max_radius) range for radii
        seed: Random seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)

    min_x, min_y, max_x, max_y = bounds
    min_r, max_r = radius_range

    circles = []
    for _ in range(n_circles):
        cx = random.uniform(min_x, max_x)
        cy = random.uniform(min_y, max_y)
        r = random.uniform(min_r, max_r)
        circles.append((cx, cy, r))

    return circles



def generate_dataset(size: str) -> Tuple[List[Point], List[Circle]]:
    """The points and circles for a dataset size (small, medium or large)."""
    config = SIZE_CONFIGS[size]
    points = generate_clustered_points(config["N_POINTS"], config["N_CLUSTERS"], BOUNDS,
                                       cluster_std=CLUSTER_STD, seed=SEED)
    circles = generate_circles(config["N_CIRCLES"], BOUNDS, RADIUS_RANGE, seed=SEED + 1)
    return points, circles
