"""
Input data for the circle cover problem: points to cover, and candidate circles to cover them with.
Every algorithm runs on the same data for a given size, so their results can be compared directly.
Also the input string for the k-th frequency moment (--algorithm kfm), see generate_string_pairs.
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



def dataset_config(size: str, n_points: Optional[int] = None, n_circles: Optional[int] = None,
                   n_clusters: Optional[int] = None) -> dict:
    """
    The numbers of points, circles and clusters for a dataset size (small, medium or large),
    with any of them replaced by a custom number. The same numbers always give the same data.
    """
    config = dict(SIZE_CONFIGS[size])
    if n_points:
        config["N_POINTS"] = n_points
    if n_circles:
        config["N_CIRCLES"] = n_circles
    if n_clusters:
        config["N_CLUSTERS"] = n_clusters
    # every cluster needs at least one point
    config["N_CLUSTERS"] = max(1, min(config["N_CLUSTERS"], config["N_POINTS"]))
    return config


def preset_name(config: dict) -> Optional[str]:
    """The dataset size whose numbers these are (small, medium or large), or None for a custom input."""
    return next((name for name, c in SIZE_CONFIGS.items() if c == config), None)


def generate_dataset(size: str, config: Optional[dict] = None) -> Tuple[List[Point], List[Circle]]:
    """The points and circles for a dataset size (small, medium or large), or for a custom config from dataset_config."""
    config = config or SIZE_CONFIGS[size]
    points = generate_clustered_points(config["N_POINTS"], config["N_CLUSTERS"], BOUNDS,
                                       cluster_std=CLUSTER_STD, seed=SEED)
    circles = generate_circles(config["N_CIRCLES"], BOUNDS, RADIUS_RANGE, seed=SEED + 1)
    return points, circles


# =============================================================================
# INPUT STRING FOR THE k-th FREQUENCY MOMENT
# =============================================================================

# Length n of the generated string per size. Much longer than the circle inputs: each symbol is
# little work, so it takes millions of them before the machines' work outweighs Spark's overhead.
STRING_SIZES = {"small": 1_000_000, "medium": 10_000_000, "large": 30_000_000}
# Symbols are the numbers 0 .. |Sigma| - 1, drawn uniformly. The default alphabet; --alphabet picks
# another one, e.g. 1 (a string of one repeated symbol) or n (almost every symbol different).
STRING_ALPHABET_SIZE = 1000
# The string is generated in this many chunks, one per input partition. Fixed, so the string (and f_k)
# is the same on any number of Pis, and it divides evenly over 1, 2, 3, 5 Pis of 4 cores (4, 8, 12, 20 cores).
STRING_CHUNKS = 120


def string_chunk(c: int, n: int, alphabet: int = STRING_ALPHABET_SIZE):
    """Positions (1-based) and symbols of chunk c of the generated string of length n, as numpy arrays."""
    import numpy as np
    start, end = c * n // STRING_CHUNKS, (c + 1) * n // STRING_CHUNKS
    symbols = np.random.default_rng([SEED, c]).integers(0, alphabet, size=end - start)
    return np.arange(start + 1, end + 1), symbols


def generate_string_pairs(sc, n: int, alphabet: int = STRING_ALPHABET_SIZE):
    """
    The input pairs <i; x_i> of a random string of length n, generated on the machines themselves
    (each partition makes its own chunk), so the driver does not have to send n pairs over the network.
    """
    def chunk_pairs(c):
        positions, symbols = string_chunk(c, n, alphabet)
        return zip(positions.tolist(), symbols.tolist())
    return sc.parallelize(range(STRING_CHUNKS), STRING_CHUNKS).flatMap(chunk_pairs)


def string_counts(n: int, alphabet: int = STRING_ALPHABET_SIZE) -> list:
    """
    How often each symbol that occurs in the generated string occurs, counted on the driver (to check
    the answer). Only the counts, not which symbol: with a huge alphabet a dict per symbol gets big.
    """
    import numpy as np
    if alphabet <= 20_000_000:
        counts = np.zeros(alphabet, dtype=np.int64)
        for c in range(STRING_CHUNKS):
            counts += np.bincount(string_chunk(c, n, alphabet)[1], minlength=alphabet)
        return counts[counts > 0].tolist()
    # an alphabet this large would not fit as one count per symbol: count the symbols that occur instead
    symbols = np.concatenate([string_chunk(c, n, alphabet)[1] for c in range(STRING_CHUNKS)])
    return np.unique(symbols, return_counts=True)[1].tolist()
