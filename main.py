# Circle Cover Problem - Greedy Thresholding Algorithm with PySpark
# 1/2(1-ε) approximation using logarithmic guesses for unknown OPT

import argparse
import math
import os
import random
import sys
from typing import List, Tuple, Set, Optional
from pyspark.sql import SparkSession

# Configure PySpark to use the same Python as the script
os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

# Type aliases
Point = Tuple[float, float]           # (x, y)
Circle = Tuple[float, float, float]   # (cx, cy, radius)

# Cluster configuration
SPARK_MASTER_URL = "spark://192.168.1.223:7077"


# =============================================================================
# SPARK SESSION
# =============================================================================

def create_spark_session(app_name: str = "CircleCover", cluster_mode: bool = False) -> SparkSession:
    """Create a PySpark session (local or cluster mode)."""
    builder = SparkSession.builder.appName(app_name)

    if cluster_mode:
        builder = builder.master(SPARK_MASTER_URL) \
            .config("spark.executor.memory", "5g") \
            .config("spark.executor.cores", "4") \
            .config("spark.cores.max", "8")
    else:
        builder = builder.master("local[*]")

    return builder.getOrCreate()


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


# =============================================================================
# COVERAGE FUNCTIONS (Oracle)
# =============================================================================

def point_in_circle(point: Point, circle: Circle) -> bool:
    """Check if a point is inside a circle (Euclidean distance)."""
    px, py = point
    cx, cy, r = circle
    return (px - cx) ** 2 + (py - cy) ** 2 <= r ** 2


def compute_coverage(circles: List[Circle], points: List[Point]) -> int:
    """
    Compute f(S): the number of unique points covered by a set of circles.
    This is the submodular function we're maximizing.
    """
    if not circles:
        return 0

    covered = 0
    for point in points:
        for circle in circles:
            if point_in_circle(point, circle):
                covered += 1
                break  # Point is covered, move to next
    return covered


def compute_marginal_gain(
    candidate: Circle,
    current_set: List[Circle],
    points: List[Point]
) -> int:
    """
    Compute marginal gain: Δf(c|S) = f(S ∪ {c}) - f(S)
    This is the number of NEW points covered by adding candidate to current_set.
    """
    new_covered = 0
    for point in points:
        # Check if point is already covered by current_set
        already_covered = False
        for circle in current_set:
            if point_in_circle(point, circle):
                already_covered = True
                break

        # If not already covered, check if candidate covers it
        if not already_covered and point_in_circle(point, candidate):
            new_covered += 1

    return new_covered



# =============================================================================
# UI CLIENT
# =============================================================================

class UIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.endpoint = f"{self.base_url}/update"
        print(f"UI Client initialized. sending updates to {self.endpoint}")

    def send(self, event_type: str, payload: dict):
        try:
            import urllib.request
            import json
            
            data = payload.copy()
            data['type'] = event_type
            
            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                self.endpoint,
                data=json_data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                pass
        except Exception as e:
            print(f"Failed to send UI update: {e}")

    def send_status(self, message: str, total_guesses: Optional[int] = None):
        payload = {"message": message}
        if total_guesses is not None:
            payload["total_guesses"] = total_guesses
        self.send("STATUS", payload)

    def send_init(self, points: List[Point], bounds: Tuple[float, float, float, float], 
                  n_points: int, n_circles: int, k: int, epsilon: float):
        self.send("INIT", {
            "points": points,
            "config": {
                "n_points": n_points,
                "n_circles": n_circles,
                "k": k,
                "epsilon": epsilon
            },
            "bounds": {
                "minX": bounds[0],
                "minY": bounds[1],
                "maxX": bounds[2],
                "maxY": bounds[3]
            }
        })

    def send_start_guess(self, j: int, threshold: float):
        self.send("START_GUESS", {"value": j, "threshold": threshold})

    def send_circle_added(self, circle: Circle, gain: int, threshold: float, coverage: int, step: int):
        self.send("CIRCLE_ADDED", {
            "circle": {"cx": circle[0], "cy": circle[1], "r": circle[2]},
            "gain": gain,
            "threshold": threshold,
            "coverage": coverage,
            "step": step
        })

    def send_finished(self):
        self.send("FINISHED", {})


# =============================================================================
# GREEDY THRESHOLDING ALGORITHM
# =============================================================================

def find_max_single_coverage(
    circles: List[Circle],
    points: List[Point],
    spark: SparkSession
) -> Tuple[int, int]:
    """
    Find the circle with maximum coverage (for establishing f(e)).
    Returns (circle_index, coverage).

    This is parallelized using PySpark.
    """
    sc = spark.sparkContext
    points_bc = sc.broadcast(points)

    def compute_single_coverage(indexed_circle):
        idx, circle = indexed_circle
        coverage = sum(1 for p in points_bc.value if point_in_circle(p, circle))
        return (idx, coverage)

    indexed_circles = list(enumerate(circles))
    results = sc.parallelize(indexed_circles) \
        .map(compute_single_coverage) \
        .collect()

    # Find maximum
    best_idx, best_coverage = max(results, key=lambda x: x[1])
    return best_idx, best_coverage


def find_candidate_above_threshold(
    circles: List[Circle],
    remaining_indices: Set[int],
    current_set: List[Circle],
    points: List[Point],
    threshold: float,
    spark: SparkSession
) -> Tuple[Optional[int], int]:
    """
    Find a circle whose marginal gain >= threshold.
    Returns (index, gain) or (None, 0).

    This is parallelized using PySpark.
    """
    if not remaining_indices:
        return None, 0

    sc = spark.sparkContext
    points_bc = sc.broadcast(points)
    current_set_bc = sc.broadcast(current_set)

    def compute_gain(indexed_circle):
        idx, circle = indexed_circle
        gain = compute_marginal_gain(circle, current_set_bc.value, points_bc.value)
        return (idx, gain)

    # Only consider remaining circles
    candidates = [(i, circles[i]) for i in remaining_indices]

    results = sc.parallelize(candidates) \
        .map(compute_gain) \
        .filter(lambda x: x[1] >= threshold) \
        .collect()

    if not results:
        return None, 0

    # Return the first candidate meeting the threshold
    return results[0]


def greedy_threshold_single(
    circles: List[Circle],
    points: List[Point],
    k: int,
    threshold: float,
    spark: SparkSession,
    ui_client: Optional[UIClient] = None,
    current_coverage_base: int = 0
) -> List[Circle]:
    """
    Single run of greedy thresholding with a fixed threshold τ.
    Adds circles whose marginal gain >= threshold until |S| = k or no candidates.
    """
    selected = []
    current_coverage = 0  # We can track coverage cumulatively if we assume non-overlapping gain, 
                          # but better to recompute or trust the gain? 
                          # Gain is accurate for specific points.
                          
    # Re-computing exact coverage might be expensive if done every step, 
    # but we have gain. New Coverage = Old Coverage + Gain.
    
    current_total_coverage = 0
    
    remaining = set(range(len(circles)))

    for step in range(k):
        candidate_idx, gain = find_candidate_above_threshold(
            circles, remaining, selected, points, threshold, spark
        )

        if candidate_idx is None:
            break  # No more candidates meet threshold

        circle = circles[candidate_idx]
        selected.append(circle)
        remaining.remove(candidate_idx)
        
        current_total_coverage += gain

        if ui_client:
            ui_client.send_circle_added(circle, gain, threshold, current_total_coverage, step + 1)

    return selected


def greedy_with_guesses(
    circles: List[Circle],
    points: List[Point],
    k: int,
    epsilon: float,
    spark: SparkSession,
    ui_client: Optional[UIClient] = None
) -> Tuple[List[Circle], int, int]:
    """
    Main algorithm: tries multiple threshold guesses since OPT is unknown.
    Returns (best_solution, best_coverage, best_guess_index).

    Guarantees 0.5(1-ε) approximation.
    """
    # Step 1: Find the circle with maximum single coverage
    # This gives us f(e) where f(e) <= OPT <= k * f(e)
    if ui_client:
        ui_client.send_status("Calculating max single coverage f(e)...")
        
    best_circle_idx, f_e = find_max_single_coverage(circles, points, spark)

    print(f"Max single-circle coverage: {f_e} (circle index {best_circle_idx})")

    if f_e == 0:
        return [], 0, 0

    # Step 2: Compute number of guesses needed
    # y = ceil(log(k) / log(1+ε))
    num_guesses = math.ceil(math.log(k) / math.log(1 + epsilon))

    print(f"Number of guesses: {num_guesses + 1} (j = 0 to {num_guesses})")
    
    if ui_client:
        ui_client.send_status(f"Starting guesses...", total_guesses=num_guesses + 1)

    # Step 3: Try each guess and track best solution
    best_solution = None
    best_coverage = 0
    best_j = 0

    for j in range(num_guesses + 1):
        # Threshold for this guess: τⱼ = ((1+ε)^j × f(e)) / (2k)
        threshold = ((1 + epsilon) ** j * f_e) / (2 * k)

        print(f"  Guess j={j}: threshold = {threshold:.2f}")

        if ui_client:
            ui_client.send_start_guess(j, threshold)

        # Run greedy with this threshold
        solution = greedy_threshold_single(circles, points, k, threshold, spark, ui_client)
        coverage = compute_coverage(solution, points)

        print(f"    Selected {len(solution)} circles, coverage = {coverage}")

        if coverage > best_coverage:
            best_coverage = coverage
            best_solution = solution
            best_j = j

    return best_solution, best_coverage, best_j


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Circle Cover Problem - Greedy Thresholding")
    parser.add_argument("--cluster", action="store_true", help="Run on Pi cluster instead of local")
    parser.add_argument("--ui-url", type=str, help="URL of the visualization server (e.g., http://localhost:8000)")
    args = parser.parse_args()

    # Configuration (smaller values for cluster testing)
    N_POINTS = 2000
    N_CIRCLES = 500
    N_CLUSTERS = 8
    K = 10  # Max circles to select
    EPSILON = 0.2
    BOUNDS = (0, 0, 1000, 1000)
    RADIUS_RANGE = (30, 100)
    SEED = 42

    print("=" * 60)
    print("Circle Cover Problem - Greedy Thresholding Algorithm")
    print("=" * 60)
    print(f"Mode: {'CLUSTER' if args.cluster else 'LOCAL'}")
    print(f"Points: {N_POINTS} (in {N_CLUSTERS} clusters)")
    print(f"Circles: {N_CIRCLES} (radius {RADIUS_RANGE[0]}-{RADIUS_RANGE[1]})")
    print(f"k = {K}, epsilon = {EPSILON}")
    
    ui_client = None
    if args.ui_url:
        ui_client = UIClient(args.ui_url)
        print(f"UI Visualization enabled at {args.ui_url}")

    print("=" * 60)

    # Create Spark session
    print("\nInitializing PySpark...")
    spark = create_spark_session(cluster_mode=args.cluster)
    spark.sparkContext.setLogLevel("WARN")

    # Generate data
    print("\nGenerating data...")
    points = generate_clustered_points(N_POINTS, N_CLUSTERS, BOUNDS, cluster_std=80, seed=SEED)
    circles = generate_circles(N_CIRCLES, BOUNDS, RADIUS_RANGE, seed=SEED + 1)

    print(f"Generated {len(points)} points and {len(circles)} circles")
    
    if ui_client:
        ui_client.send_init(points, BOUNDS, len(points), len(circles), K, EPSILON)

    # Run algorithm
    print("\nRunning greedy thresholding with logarithmic guesses...")
    print("-" * 60)

    solution, coverage, best_j = greedy_with_guesses(circles, points, K, EPSILON, spark, ui_client)

    if ui_client:
        ui_client.send_finished()

    print("-" * 60)
    print("\nRESULTS:")
    print(f"  Best guess: j = {best_j}")
    print(f"  Selected circles: {len(solution)}")
    print(f"  Points covered: {coverage} / {len(points)} ({100*coverage/len(points):.1f}%)")

    # Clean up
    spark.stop()
    print("\nDone!")


if __name__ == "__main__":
    main()
