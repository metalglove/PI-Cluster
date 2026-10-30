"""
Theorem 8: running Algorithms 6 and 7 in parallel gives a 2-round 1/2 - epsilon approximation for all inputs (arXiv:1810.01489)
"""

import time
from typing import Optional
from pyspark import SparkContext

from data import Point, Circle
from algorithms.alg6 import algorithm_6_dense
from algorithms.alg7 import algorithm_7_sparse
from viz_client import UIClient

# =============================================================================
# THEOREM 8 (Algorithms 6 and 7 in parallel)
# =============================================================================

def theorem_8_combined(sc: SparkContext, circles: list[Circle], points: list[Point], k: int, epsilon: float, seed: int = 42, num_machines: int = 8, ui: Optional[UIClient] = None):
    """
    Theorem 8: By running Algorithms 6 and 7 in parallel, we have a 2-round 1/2 - epsilon approximation.
    We do not know whether the input is dense or sparse, so we run both and return the better of the two solutions.
    Note: in the paper each machine runs both algorithms in the same 2 rounds; here they run as separate Spark jobs.
    """
    started = time.time()
    print("Running Algorithm 6 (dense)...")
    sol_6, cov_6 = algorithm_6_dense(sc, circles, points, k, epsilon, seed, num_machines, ui=ui)
    print(f"Algorithm 6 coverage: {cov_6}")

    print("Running Algorithm 7 (sparse)...")
    sol_7, cov_7 = algorithm_7_sparse(sc, circles, points, k, epsilon, seed, num_machines, ui=ui)
    print(f"Algorithm 7 coverage: {cov_7}")

    # return the better of the two solutions.
    winner, sol, cov = ("alg7", sol_7, cov_7) if cov_7 > cov_6 else ("alg6", sol_6, cov_6)
    if ui:
        ui.send_final_solution(sol, cov, None, len(points), algorithm=winner,
                               coverages={"alg6": cov_6, "alg7": cov_7},
                               elapsed_s=round(time.time() - started, 1))
    return sol, cov
