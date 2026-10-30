"""
Algorithm 6 (Dense Inputs): 1/2 - epsilon approximation in 2 rounds (arXiv:1810.01489)
"""

import math
from operator import add
from typing import List, Optional
from pyspark import Broadcast, SparkContext
import numpy as np

from data import Point, Circle
from oracle import compute_coverage
from algorithms.building_blocks import threshold_greedy_local, threshold_filter_local, algorithm_3_partition_and_sample, in_machine_order
from viz_client import (UIClient, STATS_KEY, circle_payload, with_partition_stats,
                        central_stats, gains_in_order, solution_payload)

# =============================================================================
# DRIVER HELPERS 
# =============================================================================

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

def algorithm_6_dense(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, epsilon: float, seed: int = 42, num_machines: int = 8, ui: Optional[UIClient] = None):
    """
    Algorithm 6: A 1/2 - epsilon approximation for dense inputs in 2 rounds of MapReduce.
     - Round 1: Parallel Filtering
     - Round 2: Central Aggregation
    Note: We assume that the coverage function f is computed via an oracle, 
          which we implement as compute_coverage and compute_marginal_gain functions.
    """
    
    # partition and sample the circles to get S and the RDD for parallel processing.
    circles_rdd, S_bc = algorithm_3_partition_and_sample(sc, circles, k, seed, num_machines)
    
    # NOTE: assumption that all points are broadcasted (or accessible via oracle) to all machines as per paper.
    points_bc = sc.broadcast(np.asarray(points, dtype=float))

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
    round1_aggregated_guesses = in_machine_order(round1_aggregated_guesses, circles)
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
