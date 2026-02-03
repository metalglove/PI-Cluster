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
        # Local mode optimizations for better performance
        import multiprocessing
        num_cores = multiprocessing.cpu_count()
        
        builder = builder.master(f"local[{num_cores}]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.sql.shuffle.partitions", "8") \
            .config("spark.default.parallelism", str(num_cores * 2)) \
            .config("spark.driver.maxResultSize", "2g") \
            .config("spark.local.dir", "./spark-temp")

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
# PARTITIONING & SAMPLING
# =============================================================================

def calculate_partitions(n_points: int, target_mb: int = 160, cores: int = 16, local_mode: bool = False) -> int:
    """
    Calculate optimal number of partitions based on data size and cluster resources.
    
    Args:
        n_points: Number of points in dataset
        target_mb: Target size per partition in MB (128-192 MB recommended for Pi cluster)
        cores: Total cores available in cluster (default: 16 for 4-node Pi cluster)
        local_mode: If True, optimize for local single-machine execution
    
    Returns:
        Optimal number of partitions
    """
    # Estimate: ~32 bytes per point (x, y, id, metadata)
    data_size_mb = (n_points * 32) / (1024 * 1024)
    
    if local_mode:
        # Local mode: fewer partitions to reduce overhead
        # For small datasets, use minimal partitions
        if n_points < 10000:
            return cores  # 1 partition per core
        elif n_points < 100000:
            return cores * 2  # 2 partitions per core
        else:
            # For larger datasets, still limit partitions
            return min(cores * 4, int(data_size_mb / 50))  # Larger chunks (50MB)
    else:
        # Cluster mode: original logic
        # Calculate based on data size
        optimal = max(1, int(data_size_mb / target_mb))
        
        # Also consider available cores (2-3x parallelism)
        min_partitions = cores * 2
        
        return max(optimal, min_partitions)


def sample_points_for_ui(
    points_rdd,
    max_display: int = 5000,
    seed: int = 42
) -> Tuple[List[Point], int]:
    """
    Sample points uniformly for UI visualization.
    
    Args:
        points_rdd: Full RDD of points
        max_display: Maximum points to send to UI
        seed: Random seed for reproducibility
    
    Returns:
        Tuple of (sampled_points_list, total_count)
    """
    total_points = points_rdd.count()
    
    if total_points <= max_display:
        # Small dataset - send all points
        return points_rdd.collect(), total_points
    
    # Calculate sampling fraction
    fraction = max_display / total_points
    
    # Use RDD.sample() for distributed sampling
    sampled = points_rdd.sample(
        withReplacement=False,
        fraction=fraction,
        seed=seed
    )
    sampled_points = sampled.collect()
    
    print(f"UI Sampling: {len(sampled_points)} / {total_points} points "
          f"({100*fraction:.1f}%)")
    
    return sampled_points, total_points


def stratified_sample_for_ui(
    points_rdd,
    bounds: Tuple[float, float, float, float],
    grid_size: int = 50,
    points_per_cell: int = 10
) -> Tuple[List[Point], int]:
    """
    Stratified sampling: divide space into grid, sample from each cell.
    Ensures good spatial distribution across the canvas.
    
    Args:
        points_rdd: Full RDD of points
        bounds: (min_x, min_y, max_x, max_y)
        grid_size: Number of grid cells per dimension
        points_per_cell: Max points to sample per cell
    
    Returns:
        Tuple of (sampled_points_list, total_count)
    """
    min_x, min_y, max_x, max_y = bounds
    cell_width = (max_x - min_x) / grid_size
    cell_height = (max_y - min_y) / grid_size
    
    total_points = points_rdd.count()
    
    def assign_cell(point):
        x, y = point
        cell_x = min(int((x - min_x) / cell_width), grid_size - 1)
        cell_y = min(int((y - min_y) / cell_height), grid_size - 1)
        return ((cell_x, cell_y), point)
    
    # Group by cell and sample from each
    sampled = points_rdd \
        .map(assign_cell) \
        .groupByKey() \
        .flatMap(lambda cell_points: list(cell_points[1])[:points_per_cell]) \
        .collect()
    
    print(f"UI Stratified Sampling: {len(sampled)} / {total_points} points "
          f"(grid: {grid_size}x{grid_size}, {points_per_cell} per cell)")
    
    return sampled, total_points


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
                  n_points: int, n_circles: int, k: int, epsilon: float,
                  total_points: Optional[int] = None, total_guesses: Optional[int] = None):
        """
        Send initialization data to UI.
        
        Args:
            points: Points to display (may be sampled)
            bounds: Bounding box
            n_points: Number of points being displayed
            n_circles: Total number of candidate circles
            k: Max circles to select
            epsilon: Epsilon parameter
            total_points: Total points in full dataset (if sampled, otherwise None)
        """
        payload = {
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
            },
            "total_guesses": total_guesses
        }
        
        # Add sampling metadata if points were sampled
        if total_points and total_points > len(points):
            payload["sampling"] = {
                "is_sampled": True,
                "displayed": len(points),
                "total": total_points,
                "percentage": round(100 * len(points) / total_points, 1)
            }
        
        self.send("INIT", payload)

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

    # Clean up broadcast to free memory
    points_bc.unpersist()

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

    # Clean up broadcasts to free memory
    points_bc.unpersist()
    current_set_bc.unpersist()

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
    ui_client: Optional[UIClient] = None
) -> Tuple[List[Circle], int]:
    """
    Single run of greedy thresholding with a fixed threshold τ.
    Adds circles whose marginal gain >= threshold until |S| = k or no candidates.
    
    Returns (selected_circles, total_coverage).
    """
    selected = []
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

    return selected, current_total_coverage


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
        solution, coverage = greedy_threshold_single(circles, points, k, threshold, spark, ui_client)

        print(f"    Selected {len(solution)} circles, coverage = {coverage}")

        if coverage > best_coverage:
            best_coverage = coverage
            best_solution = solution
            best_j = j

        # Early termination if full coverage achieved
        if best_coverage == len(points):
            print("  Full coverage achieved - stopping early!")
            break

    return best_solution, best_coverage, best_j


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Circle Cover Problem - Greedy Thresholding")
    parser.add_argument("--cluster", action="store_true", help="Run on Pi cluster instead of local")
    parser.add_argument("--ui-url", type=str, help="URL of the visualization server (e.g., http://localhost:8000)")
    parser.add_argument("--size", type=str, default="small", choices=["small", "medium", "large"],
                        help="Dataset size: small (2K), medium (25K), or large (100K)")
    args = parser.parse_args()

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
    
    config = SIZE_CONFIGS[args.size]
    N_POINTS = config["N_POINTS"]
    N_CIRCLES = config["N_CIRCLES"]
    N_CLUSTERS = config["N_CLUSTERS"]
    K = 10  # Max circles to select
    EPSILON = 0.2
    BOUNDS = (0, 0, 1000, 1000)
    RADIUS_RANGE = (30, 100)
    SEED = 42

    print("=" * 60)
    print("Circle Cover Problem - Greedy Thresholding Algorithm")
    print("=" * 60)
    print(f"Mode: {'CLUSTER' if args.cluster else 'LOCAL'}")
    print(f"Dataset Size: {args.size.upper()}")
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
    sc = spark.sparkContext
    
    # Set checkpoint directory for lineage breaking
    checkpoint_dir = "./checkpoints"
    sc.setCheckpointDir(checkpoint_dir)
    print(f"Checkpoint directory: {checkpoint_dir}")

    # Generate data
    print("\nGenerating data...")
    points = generate_clustered_points(N_POINTS, N_CLUSTERS, BOUNDS, cluster_std=80, seed=SEED)
    circles = generate_circles(N_CIRCLES, BOUNDS, RADIUS_RANGE, seed=SEED + 1)

    print(f"Generated {len(points)} points and {len(circles)} circles")
    
    # Create RDD for distributed processing
    print("\nSetting up distributed processing...")
    points_rdd = sc.parallelize(points)
    
    # Calculate and apply optimal partitioning
    # Use fewer partitions in local mode to reduce overhead
    import multiprocessing
    num_cores = multiprocessing.cpu_count()
    optimal_partitions = calculate_partitions(
        len(points), 
        cores=16 if args.cluster else num_cores,
        local_mode=not args.cluster
    )
    points_rdd = points_rdd.repartition(optimal_partitions)
    points_rdd.cache()  # Cache for reuse across iterations
    
    print(f"Using {optimal_partitions} partitions for optimal performance")
    
    # Sample points for UI visualization (if UI enabled)
    if ui_client:
        # Choose sampling strategy based on dataset size
        if len(points) <= 5000:
            # Small dataset - send all points
            display_points = points
            total_points = None
            print("UI: Displaying all points")
        elif len(points) <= 50000:
            # Medium dataset - uniform sampling
            display_points, total_points = sample_points_for_ui(
                points_rdd, max_display=5000
            )
        else:
            # Large dataset - stratified sampling for better distribution
            display_points, total_points = stratified_sample_for_ui(
                points_rdd, BOUNDS, grid_size=50, points_per_cell=10
            )
        
        # Calculate total guesses for UI display
        total_guesses = int(math.ceil(math.log(K) / math.log(1 + EPSILON))) + 1
        
        ui_client.send_init(
            display_points, BOUNDS, 
            len(display_points), len(circles), K, EPSILON,
            total_points=total_points,
            total_guesses=total_guesses
        )

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
    points_rdd.unpersist()
    spark.stop()
    print("\nDone!")


if __name__ == "__main__":
    main()
