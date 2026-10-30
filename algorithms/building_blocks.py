"""
Building blocks from Liu & Vondrak (arXiv:1810.01489) shared by Algorithms 5 and 6:
Algorithm 1 (ThresholdGreedy), Algorithm 2 (ThresholdFilter) and Algorithm 3 (PartitionAndSample).
"""

import math
from typing import List, Tuple
from pyspark import RDD, Broadcast, SparkContext
import numpy as np

from data import Point, Circle
from oracle import as_points, inside, uncovered_mask

# =============================================================================
# LOCAL HELPERS (Algorithms 1 & 2)
# =============================================================================

def threshold_greedy_local(candidates: List[Circle], current_solution: List[Circle], k: int, tau: float, points: List[Point]) -> List[Circle]:
    """
    Algorithm 1: ThresholdGreedy(S, G, tau)
    Greedy algorithm with threshold tau for local processing on each machine.
    """
    G_prime = list(current_solution)
    pts = as_points(points)
    # keep the uncovered points up to date instead of recomputing them for every candidate
    uncovered = uncovered_mask(G_prime, pts)
    for circle in candidates:
        if len(G_prime) >= k: 
            break
        new = inside(circle, pts) & uncovered
        if np.count_nonzero(new) >= tau:
            G_prime.append(circle)
            uncovered &= ~new
    return G_prime

def threshold_filter_local(candidates: List[Circle], current_solution: List[Circle], tau: float, points: List[Point]) -> List[Circle]:
    """
    Algorithm 2: ThresholdFilter(S, G, tau)
    Filter candidates based on marginal gain threshold tau for local processing on each machine.
    """
    pts = as_points(points)
    remaining = pts[uncovered_mask(current_solution, pts)]   # the gain only counts these points
    return [c for c in candidates if np.count_nonzero(inside(c, remaining)) >= tau]

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
