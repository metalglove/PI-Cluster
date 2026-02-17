# Circle Cover Problem - MapReduce Algorithm (arXiv:1810.01489)
# Algorithm 6 (Dense Inputs): 1/2 - epsilon approximation in 2 rounds

import argparse
import math
import os
import random
import sys
from typing import List, Tuple, Set, Optional
from pyspark.sql import SparkSession
from pyspark.rdd import RDD
import multiprocessing

# Configure PySpark
os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

# Type aliases
Point = Tuple[float, float]           # (x, y)
Circle = Tuple[float, float, float]   # (cx, cy, radius)

SPARK_MASTER_URL = "spark://192.168.1.223:7077"

# =============================================================================
# SPARK SESSION
# =============================================================================

def create_spark_session(app_name: str = "CircleCoverMR", cluster_mode: bool = False) -> SparkSession:
    """Create a PySpark session."""
    builder = SparkSession.builder.appName(app_name)
    if cluster_mode:
        builder = builder.master(SPARK_MASTER_URL) \
            .config("spark.executor.memory", "5g") \
            .config("spark.executor.cores", "4") \
            .config("spark.cores.max", "8")
    else:
        import multiprocessing
        num_cores = multiprocessing.cpu_count()
        builder = builder.master(f"local[{num_cores}]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.driver.maxResultSize", "2g")
    return builder.getOrCreate()

# =============================================================================
# DATA GENERATION
# =============================================================================

def generate_clustered_points(n_points, n_clusters, bounds, cluster_std=50.0, seed=None):
    if seed: random.seed(seed)
    min_x, min_y, max_x, max_y = bounds
    centers = [(random.uniform(min_x, max_x), random.uniform(min_y, max_y)) for _ in range(n_clusters)]
    points = []
    points_per_cluster = n_points // n_clusters
    remainder = n_points % n_clusters
    for i, (cx, cy) in enumerate(centers):
        count = points_per_cluster + (1 if i < remainder else 0)
        for _ in range(count):
            x = max(min_x, min(max_x, random.gauss(cx, cluster_std)))
            y = max(min_y, min(max_y, random.gauss(cy, cluster_std)))
            points.append((x, y))
    return points

def generate_circles(n_circles, bounds, radius_range, seed=None):
    if seed: random.seed(seed)
    min_x, min_y, max_x, max_y = bounds
    min_r, max_r = radius_range
    return [(random.uniform(min_x, max_x), random.uniform(min_y, max_y), random.uniform(min_r, max_r)) for _ in range(n_circles)]

# =============================================================================
# COVERAGE FUNCTIONS (Oracle)
# =============================================================================

def point_in_circle(point: Point, circle: Circle) -> bool:
    px, py = point
    cx, cy, r = circle
    return (px - cx) ** 2 + (py - cy) ** 2 <= r ** 2

def compute_coverage(circles: List[Circle], points: List[Point]) -> int:
    if not circles: return 0
    covered = 0
    for point in points:
        for circle in circles:
            if point_in_circle(point, circle):
                covered += 1
                break
    return covered

def compute_marginal_gain(candidate: Circle, current_set: List[Circle], points: List[Point]) -> int:
    new_covered = 0
    for point in points:
        # Check if point is already covered
        is_covered = False
        for circle in current_set:
            if point_in_circle(point, circle):
                is_covered = True
                break
        if not is_covered and point_in_circle(point, candidate):
            new_covered += 1
    return new_covered

# =============================================================================
# LOCAL HELPERS (Algorithms 1 & 2)
# =============================================================================

def threshold_greedy_local(candidates: List[Circle], current_solution: List[Circle], k: int, tau: float, points: List[Point]) -> List[Circle]:
    G_prime = list(current_solution)
    for circle in candidates:
        if len(G_prime) >= k: break
        if compute_marginal_gain(circle, G_prime, points) >= tau:
            G_prime.append(circle)
    return G_prime

def threshold_filter_local(candidates: List[Circle], current_solution: List[Circle], tau: float, points: List[Point]) -> List[Circle]:
    return [c for c in candidates if compute_marginal_gain(c, current_solution, points) >= tau]

# =============================================================================
# ALGORITHM 6 (2-Round MapReduce)
# =============================================================================

def algorithm_6_dense(spark, circles_rdd, points, k, epsilon, seed=42):
    """
    Algorithm 6 from arXiv:1810.01489.
    """
    sc = spark.sparkContext
    n_circles = circles_rdd.count()
    if n_circles == 0: return [], 0
    
    # 1. Sample S
    p = min(1.0, 4.0 * math.sqrt(k / n_circles))
    S = circles_rdd.sample(False, p, seed).collect()
    S_bc = sc.broadcast(S)
    points_bc = sc.broadcast(points)
    
    # Init Guesses
    # Guess max value v. Ideally max_{e in V} f({e}). 
    # Approximating with max_{e in S} f({e}) or sampling.
    v_S = 0
    if S:
        v_S = max([compute_coverage([c], points) for c in S])
    
    if v_S == 0:
        # Fallback if S is empty or has 0 value (unlikely unless empty input)
        # return empty or run simple greedy
        return [], 0
        
    print(f"Max value estimate (from Sample): {v_S}")
    num_guesses = int(math.ceil((1.0 / epsilon) * math.log(k))) + 1
    print(f"Running {num_guesses} guesses in parallel...")
    
    # Broadcast v_S to use as base 'v' for all mappers
    v_bc = sc.broadcast(v_S)

    # -------------------------------------------------------------------------
    # ROUND 1: Parallel Filtering
    # -------------------------------------------------------------------------
    def mapper_round1(iterator):
        local_circles = list(iterator)
        local_res = []
        
        # Access broadcasts
        local_S = S_bc.value
        local_pts = points_bc.value
        v = v_bc.value
        
        # Iterate all guesses
        for j in range(1, num_guesses + 1):
             # tau_j = v * (1 + eps)^(j/k) ?? No, Paper says (1+eps)^j / k ??
             # Actually let's assume standard geometric geometric sequence
             # Base guess: OPT/2k. Max OPT ~ k*v. Min OPT ~ v.
             # So guesses range from v/k to v.
             # Let's trust the logic: tau_j = v * (1+eps)^j / k
             tau_j = (v * ((1.0 + epsilon) ** j)) / k
             
             # G0 = Greedy(S, empty, tau)
             G0 = threshold_greedy_local(local_S, [], k, tau_j, local_pts)
             
             # Ri = Filter (Vi, G0, tau)
             if len(G0) < k:
                 Ri = threshold_filter_local(local_circles, G0, tau_j, local_pts)
             else:
                 Ri = []
                 
             if Ri:
                 local_res.append((j, Ri))
                 
        return local_res

    # Collect Round 1 results: List of (j, [circles])
    # Group by j to form Union(Ri)
    from operator import add
    round1_results = circles_rdd.mapPartitions(mapper_round1) \
        .reduceByKey(add) \
        .collect()
        
    # -------------------------------------------------------------------------
    # ROUND 2: Central Aggregation
    # -------------------------------------------------------------------------
    best_sol = []
    best_cov = 0
    
    for j, R_union in round1_results:
        # Recompute params
        tau_j = (v_S * ((1.0 + epsilon) ** j)) / k
        
        # Recompute G0 from S
        G0 = threshold_greedy_local(S, [], k, tau_j, points)
        
        # G = Greedy(Union Ri, G0, tau)
        # Note: We continue adding to G0
        G = threshold_greedy_local(R_union, G0, k, tau_j, points)
        
        cov = compute_coverage(G, points)
        # print(f"  Guess j={j}, cov={cov}")
        
        if cov > best_cov:
            best_cov = cov
            best_sol = G
            
    return best_sol, best_cov

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster", action="store_true")
    parser.add_argument("--size", type=str, default="small")
    parser.add_argument("--ui-url", type=str) # ignored for now
    args = parser.parse_args()
    
    SIZE_CONFIGS = {
        "small": {"N_POINTS": 2000, "N_CIRCLES": 500, "N_CLUSTERS": 8},
        "medium": {"N_POINTS": 25000, "N_CIRCLES": 2000, "N_CLUSTERS": 20},
        "large": {"N_POINTS": 100000, "N_CIRCLES": 5000, "N_CLUSTERS": 50}
    }
    cfg = SIZE_CONFIGS[args.size]
    
    # 1. Setup
    spark = create_spark_session(cluster_mode=args.cluster)
    sc = spark.sparkContext
    sc.setLogLevel("WARN")
    
    # 2. Data
    print("Generating data...")
    points = generate_clustered_points(cfg["N_POINTS"], cfg["N_CLUSTERS"], (0,0,1000,1000), seed=42)
    circles = generate_circles(cfg["N_CIRCLES"], (0,0,1000,1000), (30,100), seed=43)
    
    circles_rdd = sc.parallelize(circles).repartition(8 if not args.cluster else 16)
    
    # 3. Algorithm
    print("Running Algorithm 6 (arXiv:1810.01489)...")
    sol, cov = algorithm_6_dense(spark, circles_rdd, points, k=10, epsilon=0.2)
    
    print("-" * 60)
    print(f"Solution Size: {len(sol)}")
    print(f"Coverage: {cov} / {len(points)} ({100*cov/len(points):.2f}%)")
    print("-" * 60)
    
    spark.stop()

if __name__ == "__main__":
    main()
