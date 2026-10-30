"""
Algorithm 7 (Sparse Inputs): 1/2 - epsilon approximation in 2 rounds (arXiv:1810.01489)
"""

import math
import random
from typing import Optional
from pyspark import SparkContext
import numpy as np

from data import Point, Circle
from oracle import compute_coverage
from algorithms.building_blocks import threshold_greedy_local
from viz_client import (UIClient, with_partition_stats, split_partition_stats,
                        central_stats, gains_in_order, solution_payload)

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
    points_bc = sc.broadcast(np.asarray(points, dtype=float))

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
