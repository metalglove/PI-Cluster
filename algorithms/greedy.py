"""
Circle Cover Problem - Greedy Thresholding Algorithm with PySpark
1/2(1-ε) approximation using logarithmic guesses for unknown OPT
"""

import math
from typing import List, Tuple, Set, Optional
import numpy as np
from pyspark.sql import SparkSession

from data import Point, Circle
from oracle import inside, uncovered_mask
from viz_client import UIClient, machine_identity


# =============================================================================
# GREEDY THRESHOLDING ALGORITHM
# =============================================================================

def evaluate_on_cluster(
    sc,
    indexed_circles: List[Tuple[int, Circle]],
    score,
    threshold: Optional[float] = None,
    keep: str = "all"
) -> Tuple[List[Tuple[int, int, int]], List[dict]]:
    """
    Score every candidate circle on the cluster in one Spark job (= one MapReduce round).

    Returns (results, partition_stats):
      results: (circle_index, score, partition_id) for candidates with score >= threshold
               (all candidates when threshold is None), in partition order. With keep="first"
               each partition sends only its first such candidate, with keep="best" only its
               highest-scoring one (the first, on ties).
      partition_stats: one dict per partition saying which machine ran it and how much
               work it did, so the UI can show the work being split across the Pis.
    """
    def run_partition(pid, iterator):
        import time
        start = time.time()
        host, ip = machine_identity()
        kept = []
        evaluated = 0
        passed = 0
        best = 0
        best_item = None
        for idx, circle in iterator:
            value = score(circle)
            evaluated += 1
            if best_item is None or value > best:
                best, best_item = value, (idx, value, pid)
            if threshold is None or value >= threshold:
                passed += 1
                if keep == "all" or (keep == "first" and not kept):
                    kept.append((idx, value, pid))
        if keep == "best" and best_item is not None:
            kept = [best_item]
        yield ("stats", {
            "partition": pid,
            "host": host,
            "ip": ip,
            "evaluated": evaluated,
            "passed": passed,
            "sent": len(kept),
            "best": best,
            "ms": round((time.time() - start) * 1000, 1)
        })
        for item in kept:
            yield ("result", item)

    output = sc.parallelize(indexed_circles) \
        .mapPartitionsWithIndex(run_partition) \
        .collect()

    results = [value for kind, value in output if kind == "result"]
    stats = [value for kind, value in output if kind == "stats"]
    return results, stats


def find_max_single_coverage(
    circles: List[Circle],
    points: List[Point],
    spark: SparkSession
) -> Tuple[int, int, List[dict]]:
    """
    Find the circle with maximum coverage (for establishing f(e)).
    Returns (circle_index, coverage, partition_stats).

    This is parallelized using PySpark.
    """
    sc = spark.sparkContext
    points_bc = sc.broadcast(np.asarray(points, dtype=float))

    def single_coverage(circle):
        return int(np.count_nonzero(inside(circle, points_bc.value)))

    # Each partition only needs to send its best circle: the max over those is the overall max.
    results, stats = evaluate_on_cluster(sc, list(enumerate(circles)), single_coverage, keep="best")

    # Clean up broadcast to free memory
    points_bc.unpersist()

    # Find maximum
    best_idx, best_coverage, _ = max(results, key=lambda x: x[1])
    return best_idx, best_coverage, stats


def find_candidate_above_threshold(
    circles: List[Circle],
    remaining_indices: Set[int],
    current_set: List[Circle],
    points: List[Point],
    threshold: float,
    spark: SparkSession
) -> Tuple[Optional[int], int, Optional[int], List[dict]]:
    """
    Find a circle whose marginal gain >= threshold.
    Returns (index, gain, partition_id, partition_stats) or (None, 0, None, partition_stats).

    This is parallelized using PySpark.
    """
    if not remaining_indices:
        return None, 0, None, []

    sc = spark.sparkContext
    points_bc = sc.broadcast(np.asarray(points, dtype=float))
    current_set_bc = sc.broadcast(current_set)

    cache = {}
    def marginal_gain(circle):
        # The points S does not cover yet, worked out once per task and reused for every candidate
        if "uncovered" not in cache:
            pts = points_bc.value
            cache["uncovered"] = pts[uncovered_mask(current_set_bc.value, pts)]
        return int(np.count_nonzero(inside(circle, cache["uncovered"])))

    # Only consider remaining circles
    candidates = [(i, circles[i]) for i in remaining_indices]

    # Each partition only sends its first candidate >= threshold: the driver takes the first
    # one in partition order anyway, so the pick is the same and far fewer circles travel.
    results, stats = evaluate_on_cluster(sc, candidates, marginal_gain, threshold, keep="first")

    # Clean up broadcasts to free memory
    points_bc.unpersist()
    current_set_bc.unpersist()

    if not results:
        return None, 0, None, stats

    # Return the first candidate meeting the threshold
    idx, gain, partition = results[0]
    return idx, gain, partition, stats


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
        candidate_idx, gain, partition, stats = find_candidate_above_threshold(
            circles, remaining, selected, points, threshold, spark
        )

        if ui_client:
            ui_client.send_round("threshold", stats, threshold=threshold, step=step + 1,
                                 found_partition=partition)

        if candidate_idx is None:
            break  # No more candidates meet threshold

        circle = circles[candidate_idx]
        selected.append(circle)
        remaining.remove(candidate_idx)
        
        current_total_coverage += gain

        if ui_client:
            host = next((p["host"] for p in stats if p["partition"] == partition), None)
            ui_client.send_circle_added(circle, gain, threshold, current_total_coverage, step + 1,
                                        partition=partition, host=host)

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
        
    best_circle_idx, f_e, stats = find_max_single_coverage(circles, points, spark)

    if ui_client:
        ui_client.send_round("oracle", stats, best=f_e)

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
