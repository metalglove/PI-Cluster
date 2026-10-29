"""
Algorithm 5 (t thresholds): 1 - (1 - 1/(t+1))^t approximation in 2t + 2 rounds (OPT unknown) (arXiv:1810.01489)
"""

import math
from operator import add
import time
from typing import Optional
from pyspark import SparkContext
import numpy as np

from data import Point, Circle
from oracle import compute_coverage
from algorithms.building_blocks import threshold_greedy_local, threshold_filter_local, algorithm_3_partition_and_sample
from viz_client import (UIClient, STATS_KEY, circle_payload, with_partition_stats, split_partition_stats,
                        central_stats, gains_in_order)

# =============================================================================
# ALGORITHM 5 (2t + 2 Rounds MapReduce)
# =============================================================================

def algorithm_5_multi_round(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, t: int, epsilon: float, seed: int = 42, cluster_mode: bool = False, ui: Optional[UIClient] = None):
    """
    Algorithm 5: A 1 - (1 - 1/(t+1))^t approximation in 2t + 2 rounds of MapReduce.
     - Round 0: extra initial round to find the maximum-value element, which estimates OPT within a factor of k
     - Rounds 2l - 1 and 2l (for l = 1, ..., t): Algorithm 5 with threshold alpha_l, for every estimate of OPT in parallel
     - Final round: extra final round to choose the best of the solutions found for the different estimates of OPT
    Note: Algorithm 5 in the paper assumes OPT is known. We handle unknown OPT as described in Section 2.2,
          with the 2 extra rounds (not the omitted tricks that reduce it to 2t rounds).
    """
    # NOTE: assumption that all points are broadcasted (or accessible via oracle) to all machines as per paper.
    points_bc = sc.broadcast(np.asarray(points, dtype=float))

    # -------------------------------------------------------------------------
    # ROUND 0: find the maximum-value element
    # -------------------------------------------------------------------------
    # v_max = max_{e in V} f({e}), which gives v_max <= OPT <= k * v_max.
    started = time.time()
    if ui:
        # same job, but each partition also reports its machine (via with_partition_stats).
        def partition_max(iterator):
            return [max((compute_coverage([c], points_bc.value) for c in iterator), default=0)]
        round0 = sc.parallelize(circles, 16 if cluster_mode else 8) \
            .mapPartitionsWithIndex(with_partition_stats(partition_max, lambda item: [])) \
            .collect()
        partition_maxima, round0_stats = split_partition_stats(round0)
        v_max = max(partition_maxima)
        ui.send_partition_round("alg5_r0", round0_stats, algo="alg5", round=1, v=v_max)
    else:
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

    # UI only: where each chosen circle came from (the sample, or the machine that sent it).
    source_of = {}

    for l in range(1, t + 1):
        # -------------------------------------------------------------------------
        # ROUND 2l - 1: Parallel Filtering
        # -------------------------------------------------------------------------
        # a fresh random partition and sample for every threshold, as per paper.
        circles_rdd, S_bc = algorithm_3_partition_and_sample(sc, circles, k, seed + l, cluster_mode)
        solutions_bc = sc.broadcast(solutions)
        if ui:
            ui.send("SAMPLE", {"algo": "alg5", "l": l, "circles": [circle_payload(c) for c in S_bc.value],
                               "n": len(circles), "v": v_max})

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
        if ui:
            round1 = circles_rdd.mapPartitionsWithIndex(with_partition_stats(mapper_round, lambda item: item[1]))
        else:
            round1 = circles_rdd.mapPartitions(mapper_round)
        aggregated = dict(round1 \
            .reduceByKey(add) \
            .collect())
        round1_stats = aggregated.pop(STATS_KEY, [])

        if ui:
            origin = ui.send_partition_round("alg5_filter", round1_stats, algo="alg5", round=2 * l, l=l,
                                             estimates=num_estimates)
            ui.send_round("alg5_central", [central_stats(len(origin))], algo="alg5", round=2 * l + 1, l=l,
                          central=True)

        # -------------------------------------------------------------------------
        # ROUND 2l: Central Aggregation
        # -------------------------------------------------------------------------
        for g in range(num_estimates):
            alpha_l = alpha(g)

            # recompute G0 = Greedy(S, G, alpha_l) on the central machine as in the first round.
            kept = len(solutions[g])
            G0 = threshold_greedy_local(S_bc.value, solutions[g], k, alpha_l, points_bc.value)

            # G = Greedy(union of all Ri, G0, alpha_l)
            solutions[g] = threshold_greedy_local(aggregated.get(g, []), G0, k, alpha_l, points_bc.value)

            if ui:
                for i, c in enumerate(solutions[g]):
                    if c not in source_of:
                        source_of[c] = ("sample", None, None) if i < len(G0) else ("round1", *origin.get(c, (None, None)))
                G = solutions[g]
                ui.send("GUESS_RESULT", {
                    "algo": "alg5", "l": l, "j": g, "threshold": alpha_l,
                    "candidates": len(aggregated.get(g, [])), "kept": kept, "g0": len(G0),
                    "circles": [circle_payload(c, source=source_of[c][0], host=source_of[c][1], ip=source_of[c][2])
                                for c in G],
                    "gains": gains_in_order(G, points_bc.value),
                    "coverage": compute_coverage(G, points_bc.value)})

        print(f"  Threshold l={l}: solution sizes {[len(solutions[g]) for g in range(num_estimates)]}")

    # -------------------------------------------------------------------------
    # FINAL ROUND: choose the best solution over all estimates of OPT
    # -------------------------------------------------------------------------
    best_sol = []
    best_cov = 0
    best_g = 0
    for g in range(num_estimates):
        cov = compute_coverage(solutions[g], points_bc.value)
        if cov > best_cov:
            best_cov = cov
            best_sol = solutions[g]
            best_g = g

    if ui:
        ui.send_round("alg5_final", [central_stats(num_estimates)], algo="alg5", round=2 * t + 2, central=True)
        ui.send_final_solution(best_sol, best_cov, best_g, len(points), algorithm="alg5",
                               elapsed_s=round(time.time() - started, 1))

    # return the best solution and its coverage.
    return best_sol, best_cov
