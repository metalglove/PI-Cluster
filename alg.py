"""
Circle Cover Problem - MapReduce Algorithm (arXiv:1810.01489)
Algorithm 6 (Dense Inputs): 1/2 - epsilon approximation in 2 rounds
Algorithm 7 (Sparse Inputs): 1/2 - epsilon approximation in 2 rounds
Theorem 8: running Algorithms 6 and 7 in parallel gives a 2-round 1/2 - epsilon approximation for all inputs
Algorithm 5 (t thresholds): 1 - (1 - 1/(t+1))^t approximation in 2t + 2 rounds (OPT unknown)

SETUP:
  Install dependencies:
    pip install pyspark

USAGE (local mode):
    python alg.py --size small

USAGE (cluster mode):
    python alg.py --cluster --size medium

USAGE (Algorithm 5 with t thresholds):
    python alg.py --algorithm alg5 --t 3 --size small

SIZE OPTIONS: small (500 circles), medium (2000 circles), large (5000 circles)
"""

import argparse
import math
from operator import add
import os
import random
import sys
import time
from typing import List, Optional, Tuple
from pyspark import RDD, Broadcast, SparkContext
from pyspark.sql import SparkSession
import multiprocessing

from viz_client import (UIClient, STATS_KEY, circle_payload, machine_identity, ship_to_workers,
                        split_partition_stats, with_partition_stats)

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
# UI HELPERS (only used when a visualization server is attached)
# =============================================================================

def gains_in_order(G: List[Circle], points: List[Point]) -> List[int]:
    """Marginal gain of each circle in G when added in order (for the UI's gain chart)."""
    covered = [False] * len(points)
    gains = []
    for circle in G:
        gain = 0
        for i, point in enumerate(points):
            if not covered[i] and point_in_circle(point, circle):
                covered[i] = True
                gain += 1
        gains.append(gain)
    return gains

def solution_payload(G: List[Circle], from_sample: int, origin: dict) -> List[dict]:
    """G's circles for the UI: the first from_sample came from the sample S, the rest from round 1."""
    payload = []
    for i, c in enumerate(G):
        if i < from_sample:
            payload.append(circle_payload(c, source="sample"))
        else:
            host, ip = origin.get(c, (None, None))
            payload.append(circle_payload(c, source="round1", host=host, ip=ip))
    return payload

def central_stats(candidates: int) -> dict:
    """Round 2 runs on the driver: describe it like a single partition for the UI."""
    host, ip = machine_identity()
    return {"partition": "central", "host": host, "ip": ip, "held": candidates, "sent": 0}

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

def algorithm_6_dense(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, epsilon: float, seed: int = 42, cluster_mode: bool = False, ui: Optional[UIClient] = None):
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

    if ui:
        ui.send("SAMPLE", {"algo": "alg6", "circles": [circle_payload(c) for c in S_bc.value],
                           "n": len(circles), "v": v_bc.value})
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
    # guesses for which no machine sent any Ri (e.g., |G0| = k) are missing here and get an empty union in round 2.
    # with a UI attached, each partition also reports its machine and how much it sent (under STATS_KEY).
    if ui:
        round1 = circles_rdd.mapPartitionsWithIndex(with_partition_stats(mapper_round1, lambda item: item[1]))
    else:
        round1 = circles_rdd.mapPartitions(mapper_round1)
    round1_aggregated_guesses = dict(round1 \
        .reduceByKey(add) \
        .collect())
    round1_stats = round1_aggregated_guesses.pop(STATS_KEY, [])
    num_guesses = int(math.ceil((1.0 / epsilon) * math.log(k)))

    origin = {}
    if ui:
        origin = ui.send_partition_round("alg6_r1", round1_stats, algo="alg6", round=1, guesses=num_guesses)
        ui.send_round("alg6_r2", [central_stats(len(origin))], algo="alg6", round=2, central=True)
        
    # -------------------------------------------------------------------------
    # ROUND 2: Central Aggregation
    # -------------------------------------------------------------------------
    best_sol = []
    best_cov = 0
    
    # for each guess j, we use the union of all Ri from round 1 to compute a new solution G and its coverage,
    # and we keep track of the best solution across all guesses.
    # as per paper, every guess j is evaluated, even when the union of all Ri is empty (then G = G0).
    for j in range(1, num_guesses + 1):
        R_union = round1_aggregated_guesses.get(j, [])
        
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

        if ui:
            ui.send("GUESS_RESULT", {"algo": "alg6", "j": j, "threshold": tau_j, "candidates": len(R_union),
                                     "g0": len(G0), "circles": solution_payload(G, len(G0), origin),
                                     "gains": gains_in_order(G, points_bc.value), "coverage": cov})

    # return the best solution and its coverage.            
    return best_sol, best_cov

# =============================================================================
# ALGORITHM 7 (2-Round MapReduce, Sparse Inputs)
# =============================================================================

def algorithm_7_sparse(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, epsilon: float, seed: int = 42, cluster_mode: bool = False, top_factor: int = 2, ui: Optional[UIClient] = None):
    """
    Algorithm 7: A 1/2 - epsilon approximation for sparse inputs in 2 rounds of MapReduce.
     - Round 1: each machine sends its O(k) largest elements to the central machine
     - Round 2: Central thresholding on the received elements
    Note: the paper only specifies O(k) elements per machine; we send top_factor * k elements.
    """
    # partition V uniformly at random to the m machines.
    # we shuffle a copy of the circles before parallelizing, as sc.parallelize slices the list in order.
    shuffled = list(circles)
    random.Random(seed).shuffle(shuffled)
    circles_rdd = sc.parallelize(shuffled, 16 if cluster_mode else 8) # m

    # NOTE: assumption that all points are broadcasted (or accessible via oracle) to all machines as per paper.
    points_bc = sc.broadcast(points)

    # the number of largest elements each machine sends to the central machine.
    top_count = top_factor * k

    # -------------------------------------------------------------------------
    # ROUND 1: each machine sends its O(k) largest elements
    # -------------------------------------------------------------------------
    def mapper_round1(iterator):
        # compute f({e}) for every element on this machine and keep the top_count largest.
        valued = [(compute_coverage([c], points_bc.value), c) for c in iterator]
        valued.sort(key=lambda x: x[0], reverse=True)
        return valued[:top_count]

    # with a UI attached, each partition also reports its machine and how much it sent.
    if ui:
        round1_output = circles_rdd.mapPartitionsWithIndex(
            with_partition_stats(mapper_round1, lambda item: [item[1]])).collect()
        round1_elements, round1_stats = split_partition_stats(round1_output)
    else:
        round1_elements = circles_rdd.mapPartitions(mapper_round1).collect()

    # -------------------------------------------------------------------------
    # ROUND 2: Central Thresholding
    # -------------------------------------------------------------------------
    # S = all elements sent to the central machine, in decreasing order of f({e}).
    round1_elements.sort(key=lambda x: x[0], reverse=True)
    S = [c for _, c in round1_elements]

    # v = max_{e in S} f({e}).
    v = round1_elements[0][0] if round1_elements else 0

    print(f"Elements sent to central machine: {len(S)}")
    print(f"Max value estimate (from largest elements): {v}")

    # the number of guesses is (1/epsilon) * log(k) as per paper.
    num_guesses = int(math.ceil((1.0 / epsilon) * math.log(k)))

    origin = {}
    if ui:
        origin = ui.send_partition_round("alg7_r1", round1_stats, algo="alg7", round=1, top=top_count, v=v)
        ui.send_round("alg7_r2", [central_stats(len(S))], algo="alg7", round=2, central=True)

    best_sol = []
    best_cov = 0

    for j in range(1, num_guesses + 1):
        # compute threshold tau_j = (v * ((1 + epsilon) ** j)) / k as per paper.
        tau_j = (v * ((1.0 + epsilon) ** j)) / k

        # G_j = Greedy(S, empty, tau_j)
        G = threshold_greedy_local(S, [], k, tau_j, points_bc.value)

        # compute coverage of G using the oracle (compute_coverage) and update best solution if needed.
        cov = compute_coverage(G, points_bc.value)
        if cov > best_cov:
            best_cov = cov
            best_sol = G

        if ui:
            ui.send("GUESS_RESULT", {"algo": "alg7", "j": j, "threshold": tau_j, "candidates": len(S),
                                     "g0": 0, "circles": solution_payload(G, 0, origin),
                                     "gains": gains_in_order(G, points_bc.value), "coverage": cov})

    # return the best solution and its coverage.
    return best_sol, best_cov

# =============================================================================
# THEOREM 8 (Algorithms 6 and 7 in parallel)
# =============================================================================

def theorem_8_combined(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, epsilon: float, seed: int = 42, cluster_mode: bool = False, ui: Optional[UIClient] = None):
    """
    Theorem 8: By running Algorithms 6 and 7 in parallel, we have a 2-round 1/2 - epsilon approximation.
    We do not know whether the input is dense or sparse, so we run both and return the better of the two solutions.
    Note: in the paper each machine runs both algorithms in the same 2 rounds; here they run as separate Spark jobs.
    """
    started = time.time()
    print("Running Algorithm 6 (dense)...")
    sol_6, cov_6 = algorithm_6_dense(sc, circles, points, k, epsilon, seed, cluster_mode, ui=ui)
    print(f"Algorithm 6 coverage: {cov_6}")

    print("Running Algorithm 7 (sparse)...")
    sol_7, cov_7 = algorithm_7_sparse(sc, circles, points, k, epsilon, seed, cluster_mode, ui=ui)
    print(f"Algorithm 7 coverage: {cov_7}")

    # return the better of the two solutions.
    winner, sol, cov = ("alg7", sol_7, cov_7) if cov_7 > cov_6 else ("alg6", sol_6, cov_6)
    if ui:
        ui.send_final_solution(sol, cov, None, len(points), algorithm=winner,
                               coverages={"alg6": cov_6, "alg7": cov_7},
                               elapsed_s=round(time.time() - started, 1))
    return sol, cov

# =============================================================================
# ALGORITHM 5 (2t + 2 Rounds MapReduce)
# =============================================================================

def algorithm_5_multi_round(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, t: int, epsilon: float, seed: int = 42, cluster_mode: bool = False):
    """
    Algorithm 5: A 1 - (1 - 1/(t+1))^t approximation in 2t + 2 rounds of MapReduce.
     - Round 0: extra initial round to find the maximum-value element, which estimates OPT within a factor of k
     - Rounds 2l - 1 and 2l (for l = 1, ..., t): Algorithm 5 with threshold alpha_l, for every estimate of OPT in parallel
     - Final round: extra final round to choose the best of the solutions found for the different estimates of OPT
    Note: Algorithm 5 in the paper assumes OPT is known. We handle unknown OPT as described in Section 2.2,
          with the 2 extra rounds (not the omitted tricks that reduce it to 2t rounds).
    """
    # NOTE: assumption that all points are broadcasted (or accessible via oracle) to all machines as per paper.
    points_bc = sc.broadcast(points)

    # -------------------------------------------------------------------------
    # ROUND 0: find the maximum-value element
    # -------------------------------------------------------------------------
    # v_max = max_{e in V} f({e}), which gives v_max <= OPT <= k * v_max.
    v_max = sc.parallelize(circles, 16 if cluster_mode else 8) \
        .map(lambda c: compute_coverage([c], points_bc.value)) \
        .max()

    # the estimates of OPT are v_max * (1 + epsilon)^g for g = 0, ..., ceil(log_{1+epsilon} k),
    # so that one of them is within a factor of 1 + epsilon of OPT.
    num_estimates = int(math.ceil(math.log(k) / math.log(1.0 + epsilon))) + 1
    opt_estimates = [v_max * ((1.0 + epsilon) ** g) for g in range(num_estimates)]

    print(f"Max single-element value: {v_max}")
    print(f"Running {num_estimates} estimates of OPT with t = {t} thresholds ({2 * t + 2} rounds)...")

    # G <- empty, for every estimate of OPT.
    solutions = {g: [] for g in range(num_estimates)}

    for l in range(1, t + 1):
        # -------------------------------------------------------------------------
        # ROUND 2l - 1: Parallel Filtering
        # -------------------------------------------------------------------------
        # a fresh random partition and sample for every threshold, as per paper.
        circles_rdd, S_bc = algorithm_3_partition_and_sample(sc, circles, k, seed + l, cluster_mode)
        solutions_bc = sc.broadcast(solutions)

        # alpha_l = (1 - 1/(t+1))^l * OPT / k as per paper.
        def alpha(g: int) -> float:
            return ((1.0 - 1.0 / (t + 1)) ** l) * opt_estimates[g] / k

        def mapper_round(iterator):
            local_circles = list(iterator)
            local_res = []

            for g in range(num_estimates):
                alpha_l = alpha(g)

                # G0 = Greedy(S, G, alpha_l)
                G0 = threshold_greedy_local(S_bc.value, solutions_bc.value[g], k, alpha_l, points_bc.value)

                # Ri = Filter(Vi, G0, alpha_l)
                if len(G0) < k:
                    Ri = threshold_filter_local(local_circles, G0, alpha_l, points_bc.value)
                    if Ri:
                        local_res.append((g, Ri))

            return local_res

        # we aggregate the result by key (g) to get the union of all Ri for each estimate g across all machines.
        # estimates for which no machine sent any Ri are missing here and get an empty union.
        aggregated = dict(circles_rdd.mapPartitions(mapper_round) \
            .reduceByKey(add) \
            .collect())

        # -------------------------------------------------------------------------
        # ROUND 2l: Central Aggregation
        # -------------------------------------------------------------------------
        for g in range(num_estimates):
            alpha_l = alpha(g)

            # recompute G0 = Greedy(S, G, alpha_l) on the central machine as in the first round.
            G0 = threshold_greedy_local(S_bc.value, solutions[g], k, alpha_l, points_bc.value)

            # G = Greedy(union of all Ri, G0, alpha_l)
            solutions[g] = threshold_greedy_local(aggregated.get(g, []), G0, k, alpha_l, points_bc.value)

        print(f"  Threshold l={l}: solution sizes {[len(solutions[g]) for g in range(num_estimates)]}")

    # -------------------------------------------------------------------------
    # FINAL ROUND: choose the best solution over all estimates of OPT
    # -------------------------------------------------------------------------
    best_sol = []
    best_cov = 0
    for g in range(num_estimates):
        cov = compute_coverage(solutions[g], points_bc.value)
        if cov > best_cov:
            best_cov = cov
            best_sol = solutions[g]

    # return the best solution and its coverage.
    return best_sol, best_cov

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster", action="store_true")
    parser.add_argument("--size", type=str, default="small")
    parser.add_argument("--algorithm", type=str, choices=["theorem8", "alg5"], default="theorem8")
    parser.add_argument("--t", type=int, default=2, help="number of thresholds for Algorithm 5")
    parser.add_argument("--ui-url", type=str, help="URL of the visualization server (e.g., http://localhost:8000)")
    args = parser.parse_args()
    ui = UIClient(args.ui_url) if args.ui_url else None
    if ui and args.algorithm != "theorem8":
        print("The UI only knows Theorem 8 so far; running without it.")
        ui = None
    
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
    if ui:
        ship_to_workers(sc)  # round-1 tasks report which Pi ran them via viz_client
    
    # 2. Data
    print("Generating data...")
    points = generate_clustered_points(cfg["N_POINTS"], cfg["N_CLUSTERS"], (0,0,1000,1000), seed=42)
    circles = generate_circles(cfg["N_CIRCLES"], (0,0,1000,1000), (30,100), seed=43)
    
    if ui:
        # the browser draws at most 5000 points; send a uniform sample of larger inputs.
        shown = points if len(points) <= 5000 else random.Random(0).sample(points, 5000)
        ui.send_init(shown, (0, 0, 1000, 1000), len(shown), len(circles), 10, 0.2,
                     total_points=len(points), total_guesses=int(math.ceil((1.0 / 0.2) * math.log(10))),
                     algorithm="theorem8")

    # 3. Algorithm
    if args.algorithm == "alg5":
        sol, cov = algorithm_5_multi_round(sc, circles, points, k=10, t=args.t, epsilon=0.2, seed=56, cluster_mode=args.cluster)
    else:
        sol, cov = theorem_8_combined(sc, circles, points, k=10, epsilon=0.2, seed=56, cluster_mode=args.cluster, ui=ui)

    if ui:
        ui.send_finished()
    
    print("-" * 60)
    print(f"Solution Size: {len(sol)}")
    print(f"Coverage: {cov} / {len(points)} ({100*cov/len(points):.2f}%)")
    print("-" * 60)
    
    spark.stop()

if __name__ == "__main__":
    main()
