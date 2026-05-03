"""
Circle Cover Problem - MapReduce Algorithm (arXiv:1810.01489)
Algorithm 6 (Dense Inputs): 1/2 - epsilon approximation in 2 rounds

SETUP:
  Install dependencies:
    pip install pyspark

USAGE (local mode):
    python alg.py --size small

USAGE (cluster mode):
    python alg.py --cluster --size medium

SIZE OPTIONS: small (500 circles), medium (2000 circles), large (5000 circles)
"""

import argparse
import math
from operator import add
import os
import random
import sys
from typing import List, Tuple
from pyspark import RDD, Broadcast, SparkContext
from pyspark.sql import SparkSession
import multiprocessing

# configure PySpark
os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

# type aliases
Point = Tuple[float, float]           # (x, y)
Circle = Tuple[float, float, float]   # (cx, cy, radius)

# used when running in cluster mode (raspberry pi) to specify the Spark master URL; otherwise, 
# ignored when running in local mode (e.g., on a single machine with multiple cores).
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
        num_cores = multiprocessing.cpu_count()
        builder = builder.master(f"local[{num_cores}]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.driver.maxResultSize", "2g")
    return builder.getOrCreate()

# =============================================================================
# DATA GENERATION
# =============================================================================

def generate_clustered_points(n_points: int, n_clusters: int, bounds: Tuple[float, float, float, float], cluster_std=50.0, seed=None) -> List[Point]:
    if seed: 
        random.seed(seed)
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

def generate_circles(n_circles: int, bounds: Tuple[float, float, float, float], radius_range: Tuple[float, float], seed=None) -> List[Circle]:
    if seed: 
        random.seed(seed)
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
        # check if point is already covered
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
    """
    Algorithm 1: ThresholdGreedy(S, G, tau)
    Greedy algorithm with threshold tau for local processing on each machine.
    """
    G_prime = list(current_solution)
    for circle in candidates:
        if len(G_prime) >= k: 
            break
        if compute_marginal_gain(circle, G_prime, points) >= tau:
            G_prime.append(circle)
    return G_prime

def threshold_filter_local(candidates: List[Circle], current_solution: List[Circle], tau: float, points: List[Point]) -> List[Circle]:
    """
    Algorithm 2: ThresholdFilter(S, G, tau)
    Filter candidates based on marginal gain threshold tau for local processing on each machine.
    """
    return [c for c in candidates if compute_marginal_gain(c, current_solution, points) >= tau]

# =============================================================================
# DRIVER HELPERS 
# =============================================================================

def algorithm_3_partition_and_sample(sc: SparkContext, circles: list[Circle], k: int, seed: int = 42, cluster_mode=False) -> Tuple[RDD[Circle], Broadcast[List[Circle]]]:
    """
    Algorithm 3: PartionAndSample(V)
    1. Sample S subset of V by including each element with probability p = min(1, 4 * sqrt(k / n))
       where n is the total number of elements and k is the maximum cardinality of the solution.
    2. Partition V into m = sqrt(k / n) random subsets (machines).
    3. Send S to all machines (including the central machine).
    """
    # let n be the number of elements in V (number of circles).
    n = len(circles)
    
    # let m be the number of machines.
    m = math.sqrt(k / n)
    
    # sampling probability p = min(1, 4 * sqrt(k / n)) as per paper.
    p = min(1.0, 4.0 * m)

    # NOTE: in an ideal scenario we would have m machines and partition V into m random subsets.
    # however, in Spark we can just parallelize the data over a number of partitions (e.g., in essence machines/cores)
    # considering we are running on a raspberrypi cluster with total 8 cores per machine and 2 machines, 
    # we can use 16 partitions to simulate the distributed environment.
    # as m is O(sqrt(k/n)), it will be small for large n, so we can just use a fixed number of partitions that is >= m.
    circles_rdd = sc.parallelize(circles, 16 if cluster_mode else 8) # m

    # we sample each element from V independently with probability p to form S.
    S = circles_rdd.sample(False, p, seed).collect()

    # then, we broadcast S to all machines (including the central machine).
    S_bc = sc.broadcast(S)
    
    # the expected size of S is p * n_circles, which is O(sqrt(k * n_circles)) as per paper.
    return circles_rdd, S_bc

def initial_guess_v_S(sc: SparkContext, S_bc: Broadcast[List[Circle]], points_bc: Broadcast[List[Point]]) -> Broadcast[int]:
    """
    Initial guess for max value v_S = max_{e in S} f({e}).
    Note: this is the first guess for the max coverage value, which is used to generate the sequence of thresholds tau_j.
    As this value is used in the mapper for all guesses on the same set of points, we compute it once and broadcast it.
    We still use the broadcasted values to stay consistent with the distributed environment, even though this computation is done on the driver.
    """
    v_S = 0
    if S_bc.value:
        v_S = max([compute_coverage([c], points_bc.value) for c in S_bc.value])
    return sc.broadcast(v_S)

# =============================================================================
# ALGORITHM 6 (2-Round MapReduce)
# =============================================================================

def algorithm_6_dense(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, epsilon: float, seed: int = 42, cluster_mode: bool = False):
    """
    Algorithm 6: A 1/2 - epsilon approximation for dense inputs in 2 rounds of MapReduce.
     - Round 1: Parallel Filtering
     - Round 2: Central Aggregation
    Note: We assume that the coverage function f is computed via an oracle, 
          which we implement as compute_coverage and compute_marginal_gain functions.
    """
    
    # partition and sample the circles to get S and the RDD for parallel processing.
    circles_rdd, S_bc = algorithm_3_partition_and_sample(sc, circles, k, seed, cluster_mode)
    
    # NOTE: assumption that all points are broadcasted (or accessible via oracle) to all machines as per paper.
    points_bc = sc.broadcast(points)

    # initial guess for max value v_S = max_{e in S} f({e}). 
    # this is used to generate the sequence of thresholds tau_j for the mappers.
    v_bc = initial_guess_v_S(sc, S_bc, points_bc)
        
    print(f"Max value estimate (from Sample): {v_bc.value}")
    print(f"Running {int(math.ceil((1.0 / epsilon) * math.log(k)))} guesses in parallel on each machine...")
    
    # -------------------------------------------------------------------------
    # ROUND 1: Parallel Filtering
    # -------------------------------------------------------------------------
    def mapper_round1(iterator):
        local_circles = list(iterator)
        local_res = []
        
        # the number of guesses is (1/epsilon) * log(k) as per paper.
        num_guesses = int(math.ceil((1.0 / epsilon) * math.log(k)))
        
        # iterate over guesses in parallel on each machine.
        for j in range(1, num_guesses + 1):
            # compute threshold tau_j = (v * ((1 + epsilon) ** j)) / k as per paper.
            tau_j = (v_bc.value * ((1.0 + epsilon) ** j)) / k
            
            # G0 = Greedy(S, empty, tau)
            G0 = threshold_greedy_local(S_bc.value, [], k, tau_j, points_bc.value)
            
            # Ri = Filter (Vi, G0, tau)
            if len(G0) < k:
                Ri = threshold_filter_local(local_circles, G0, tau_j, points_bc.value)
                if Ri:
                    local_res.append((j, Ri))
                 
        return local_res

    # we aggregate the result by key (j) to get the union of all Ri for each guess j across all machines (cores / partitions).
    round1_aggregated_guesses = circles_rdd.mapPartitions(mapper_round1) \
        .reduceByKey(add) \
        .collect()
        
    # -------------------------------------------------------------------------
    # ROUND 2: Central Aggregation
    # -------------------------------------------------------------------------
    best_sol = []
    best_cov = 0
    
    # for each guess j, we use the union of all Ri from round 1 to compute a new solution G and its coverage,
    # and we keep track of the best solution across all guesses.
    for j, R_union in round1_aggregated_guesses:
        # we recompute the threshold tau_j for the central aggregation step, as it is used in the greedy algorithm to compute G0 and G.
        tau_j = (v_bc.value * ((1.0 + epsilon) ** j)) / k
        
        # recompute G0 = Greedy(S, empty, tau) on the central machine, 
        # as it is used as the starting point for the greedy algorithm to compute G.
        G0 = threshold_greedy_local(S_bc.value, [], k, tau_j, points_bc.value)
        
        # compute G = Greedy(R_union, G0, k, tau) on the central machine using the 
        # union of all Ri from round 1 as candidates and G0 as the starting solution.
        G = threshold_greedy_local(R_union, G0, k, tau_j, points_bc.value)
        
        # compute coverage of G using the oracle (compute_coverage) and update best solution if needed.
        cov = compute_coverage(G, points_bc.value)
        if cov > best_cov:
            best_cov = cov
            best_sol = G

    # return the best solution and its coverage.            
    return best_sol, best_cov

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster", action="store_true")
    parser.add_argument("--size", type=str, default="small")
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
    
    # 3. Algorithm
    print("Running Algorithm 6...")
    sol, cov = algorithm_6_dense(sc, circles, points, k=10, epsilon=0.2, seed=56, cluster_mode=args.cluster)
    
    print("-" * 60)
    print(f"Solution Size: {len(sol)}")
    print(f"Coverage: {cov} / {len(points)} ({100*cov/len(points):.2f}%)")
    print("-" * 60)
    
    spark.stop()

if __name__ == "__main__":
    main()
