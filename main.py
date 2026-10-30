"""
Circle Cover Problem on a Raspberry Pi cluster with PySpark

Start-up for every algorithm: reads the command line, starts Spark, generates the data,
binds the visualization UI, and runs the chosen algorithm from algorithms/.

ALGORITHMS (--algorithm):
  greedy    sequential threshold greedy: 1/2(1-ε) approximation, one Spark job per greedy step (default)
  theorem8  Algorithms 6 and 7 in parallel (arXiv:1810.01489): 1/2 - epsilon approximation in 2 rounds
  alg5      Algorithm 5 with t thresholds (arXiv:1810.01489): 1 - (1 - 1/(t+1))^t approximation in 2t + 2 rounds

USAGE (local mode):
    python main.py --size small
    python main.py --algorithm theorem8 --size small
    python main.py --algorithm alg5 --t 3 --size small

USAGE (cluster mode):
    python main.py --cluster --algorithm theorem8 --size medium

USAGE (with the visualization server):
    python main.py --ui-url http://localhost:8000 --size medium

SIZE OPTIONS: small (2K points, 500 circles), medium (25K, 2000), large (100K, 5000)
"""

import argparse
import math
import json
import multiprocessing
import os
import random
import sys
import tempfile
import time
import urllib.request
import zipfile
from typing import Optional
from pyspark.sql import SparkSession

from data import SIZE_CONFIGS, BOUNDS, RADIUS_RANGE, CLUSTER_STD, SEED, generate_dataset
from viz_client import UIClient
from algorithms.greedy import greedy_with_guesses
from algorithms.theorem8 import theorem_8_combined
from algorithms.alg5 import algorithm_5_multi_round

# Configure PySpark to use the same Python as the script
os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

# used when running in cluster mode (raspberry pi) to specify the Spark master URL; otherwise, 
# ignored when running in local mode (e.g., on a single machine with multiple cores).
SPARK_MASTER_URL = "spark://192.168.1.223:7077"
SPARK_MASTER_UI = "http://192.168.1.223:8080/json/"   # lists the workers that are alive
CORES_PER_PI = 4   # one executor of this many cores per Pi, so N Pis = N executors

# Problem parameters, the same for every algorithm
K = 10  # Max circles to select
EPSILON = 0.2
ALGORITHM_SEED = 56  # random partition and sample of the MapReduce algorithms

# The modules Spark tasks use; the workers need them too (see ship_code_to_workers)
CODE = ["data.py", "oracle.py", "viz_client.py", "algorithms"]


# =============================================================================
# SPARK SESSION
# =============================================================================

def alive_pis() -> Optional[int]:
    """Number of workers the Spark master lists as alive, or None if the master can't be reached."""
    try:
        with urllib.request.urlopen(SPARK_MASTER_UI, timeout=5) as response:
            workers = json.loads(response.read()).get("workers", [])
        return sum(1 for w in workers if w.get("state") == "ALIVE") or None
    except Exception:
        return None


def create_spark_session(app_name: str = "CircleCover", cluster_mode: bool = False,
                         pis: Optional[int] = None, cores: Optional[int] = None) -> SparkSession:
    """
    Create a PySpark session (local or cluster mode).
    cluster mode runs on `pis` Pis (default: all alive workers), local mode on `cores` cores (default: all).
    """
    builder = SparkSession.builder.appName(app_name)

    if cluster_mode:
        builder = builder.master(SPARK_MASTER_URL) \
            .config("spark.executor.memory", "5g") \
            .config("spark.executor.cores", str(CORES_PER_PI))
        if pis:
            # The master spreads executors over the workers, so N Pis' worth of cores lands on N different
            # Pis. Wait until all of them have joined before the first job, so every run uses what it asked for.
            builder = builder \
                .config("spark.cores.max", str(pis * CORES_PER_PI)) \
                .config("spark.scheduler.minRegisteredResourcesRatio", "1.0") \
                .config("spark.scheduler.maxRegisteredResourcesWaitingTime", "60s")
    else:
        # Local mode optimizations for better performance
        num_cores = cores or multiprocessing.cpu_count()

        builder = builder.master(f"local[{num_cores}]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.sql.shuffle.partitions", "8") \
            .config("spark.default.parallelism", str(num_cores * 2)) \
            .config("spark.driver.maxResultSize", "2g") \
            .config("spark.local.dir", "./spark-temp")

    return builder.getOrCreate()


def ship_code_to_workers(sc) -> None:
    """
    Make our modules importable inside Spark tasks. The algorithms run on the workers, but on the
    Pis this code is only on the master, so zip it and let Spark send it to every executor.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    archive = os.path.join(tempfile.mkdtemp(), "circle_cover.zip")
    with zipfile.ZipFile(archive, "w") as zf:
        for name in CODE:
            path = os.path.join(here, name)
            if os.path.isfile(path):
                zf.write(path, name)
                continue
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if f.endswith(".py"):
                        zf.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), here))
    sc.addPyFile(archive)


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Circle Cover Problem")
    parser.add_argument("--cluster", action="store_true", help="Run on Pi cluster instead of local")
    parser.add_argument("--ui-url", type=str, help="URL of the visualization server (e.g., http://localhost:8000)")
    parser.add_argument("--size", type=str, default="small", choices=["small", "medium", "large"],
                        help="Dataset size: small (2K), medium (25K), or large (100K)")
    parser.add_argument("--algorithm", type=str, choices=["greedy", "theorem8", "alg5"], default="greedy",
                        help="greedy (threshold greedy), theorem8 (Algorithms 6 + 7) or alg5 (Algorithm 5)")
    parser.add_argument("--t", type=int, default=2, help="number of thresholds for Algorithm 5")
    parser.add_argument("--pis", type=int, help="cluster mode: number of Pis to run on (default: all alive workers)")
    parser.add_argument("--cores", type=int, help="local mode: number of cores to run on (default: all)")
    args = parser.parse_args()

    config = SIZE_CONFIGS[args.size]

    # The paper's m machines, each holding about n / m = sqrt(nk) circles: m = sqrt(n / k), rounded up.
    # It depends only on the input, so the result is the same however many Pis or cores run the m partitions.
    num_machines = math.ceil(math.sqrt(config["N_CIRCLES"] / K))

    # How much hardware runs them; the UI compares wall times across these to show the speedup
    if args.cluster:
        pis = args.pis or alive_pis()
        hardware = {"pis": pis, "cores_per_pi": CORES_PER_PI} if pis else {}
    else:
        hardware = {"cores": args.cores or multiprocessing.cpu_count()}

    print("=" * 60)
    print(f"Circle Cover Problem - {args.algorithm}")
    print("=" * 60)
    print(f"Mode: {'CLUSTER' if args.cluster else 'LOCAL'}")
    print(f"Dataset Size: {args.size.upper()}")
    print(f"Points: {config['N_POINTS']} (in {config['N_CLUSTERS']} clusters)")
    print(f"Circles: {config['N_CIRCLES']} (radius {RADIUS_RANGE[0]}-{RADIUS_RANGE[1]})")
    print(f"k = {K}, epsilon = {EPSILON}" + (f", t = {args.t}" if args.algorithm == "alg5" else ""))
    print(f"Machines (partitions) m = {num_machines}, running on " +
          (f"{hardware['pis']} Pis" if "pis" in hardware else f"{hardware['cores']} cores" if hardware else "all Pis"))

    ui = None
    if args.ui_url:
        ui = UIClient(args.ui_url)
        print(f"UI Visualization enabled at {args.ui_url}")

    print("=" * 60)

    # 1. Setup
    print("\nInitializing PySpark...")
    # the dashboard finds our job by its name: the threshold greedy runs as "CircleCover", the paper's
    # MapReduce algorithms as "CircleCoverMR"
    spark = create_spark_session("CircleCover" if args.algorithm == "greedy" else "CircleCoverMR",
                                 cluster_mode=args.cluster, pis=hardware.get("pis"), cores=hardware.get("cores"))
    sc = spark.sparkContext
    sc.setLogLevel("WARN")
    ship_code_to_workers(sc)

    # 2. Data
    print("\nGenerating data...")
    points, circles = generate_dataset(args.size)
    print(f"Generated {len(points)} points and {len(circles)} circles")

    # 3. UI
    if ui:
        # the browser draws at most 5000 points; send a uniform sample of larger inputs.
        shown = points if len(points) <= 5000 else random.Random(0).sample(points, 5000)
        extra = {"machines": num_machines, **hardware}
        if args.algorithm == "theorem8":
            guesses = int(math.ceil((1.0 / EPSILON) * math.log(K)))
        else:
            # one guess per estimate of OPT, as greedy_with_guesses and algorithm_5_multi_round count them
            guesses = int(math.ceil(math.log(K) / math.log(1 + EPSILON))) + 1
            if args.algorithm == "alg5":
                extra["t"] = args.t
        ui.send_init(shown, BOUNDS, len(shown), len(circles), K, EPSILON,
                     total_points=len(points), total_guesses=guesses, algorithm=args.algorithm,
                     # identifies the input, so the UI only compares runs on the same data
                     dataset=f"{args.size}/seed{SEED}/std{CLUSTER_STD}", **extra)

    # 4. Algorithm
    print(f"\nRunning {args.algorithm}...")
    print("-" * 60)

    started = time.time()
    if args.algorithm == "greedy":
        sol, cov, best_j = greedy_with_guesses(circles, points, K, EPSILON, spark, ui)
        elapsed = time.time() - started
        print(f"  Best guess: j = {best_j}")
        if ui:
            # Send the final best solution for visualization
            ui.send_final_solution(sol, cov, best_j, len(points), elapsed_s=round(elapsed, 1))
    elif args.algorithm == "alg5":
        # Algorithms 5 and 6/7 report their own final solution to the UI
        sol, cov = algorithm_5_multi_round(sc, circles, points, k=K, t=args.t, epsilon=EPSILON,
                                           seed=ALGORITHM_SEED, num_machines=num_machines, ui=ui)
    else:
        sol, cov = theorem_8_combined(sc, circles, points, k=K, epsilon=EPSILON,
                                      seed=ALGORITHM_SEED, num_machines=num_machines, ui=ui)
    elapsed = time.time() - started

    if ui:
        ui.send_finished()

    print("-" * 60)
    print("\nRESULTS:")
    print(f"  Selected circles: {len(sol)}")
    print(f"  Points covered: {cov} / {len(points)} ({100*cov/len(points):.1f}%)")
    print(f"  Wall time: {elapsed:.1f} s")

    spark.stop()
    print("\nDone!")


if __name__ == "__main__":
    main()
