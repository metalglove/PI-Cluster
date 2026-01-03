import time
from datetime import datetime
from src.mapreduce.mappers import compute_local_circle_gains, update_coverage_partition
from src.mapreduce.reducers import aggregate_circle_gains, find_best_circle, merge_coverage_updates


class GreedySubmodularCircleCover:
    """
    Distributed Greedy Submodular algorithm for Circle Cover problem.

    Iteratively selects k circles that maximize coverage of points,
    achieving a 0.5-approximation guarantee.
    """

    def __init__(self, spark_context, k, config):
        """
        Args:
            spark_context: Active SparkContext
            k: Number of circles to select
            config: AlgorithmConfig object with checkpoint settings
        """
        self.sc = spark_context
        self.k = k
        self.config = config
        self.iteration_stats = []

        # Set checkpoint directory if configured
        if config.checkpoint_dir:
            self.sc.setCheckpointDir(config.checkpoint_dir)

    def run(self, points_rdd, circles_list):
        """
        Run the greedy submodular algorithm.

        Args:
            points_rdd: RDD of points (each point is a Row or dict with point_id, x, y)
            circles_list: List of circles (each circle is a dict or object with circle_id, center_x, center_y, radius)

        Returns:
            Tuple: (selected_circles, iteration_stats)
                - selected_circles: List of selected circle IDs in order
                - iteration_stats: List of dicts with per-iteration statistics
        """
        print(f"\n{'='*70}")
        print(f"Starting Greedy Submodular Circle Cover Algorithm")
        print(f"  Points: {points_rdd.count()}")
        print(f"  Candidate Circles: {len(circles_list)}")
        print(f"  k (circles to select): {self.k}")
        print(f"{'='*70}\n")

        # Initialize state
        selected_circles = []
        cumulative_coverage = 0

        # Broadcast circles (small enough to broadcast)
        circles_bc = self.sc.broadcast(circles_list)

        # Initialize coverage status: all points start uncovered
        # Build dict: {point_id: True} where True = uncovered
        print("Initializing coverage status...")
        points_list = points_rdd.collect()
        uncovered_dict = {}
        for point in points_list:
            if isinstance(point, dict):
                uncovered_dict[point['point_id']] = True
            else:
                uncovered_dict[point.point_id] = True

        uncovered_bc = self.sc.broadcast(uncovered_dict)
        selected_bc = self.sc.broadcast([])

        # Cache points RDD for faster iteration
        points_rdd.cache()

        # Main iteration loop
        for iteration in range(1, self.k + 1):
            start_time = time.time()

            print(f"\n--- Iteration {iteration}/{self.k} ---")

            # STAGE 1: MAP - Compute gains
            print("  Stage 1: Computing local circle gains...")
            gains_rdd = points_rdd.mapPartitions(
                lambda partition: compute_local_circle_gains(
                    partition,
                    circles_bc,
                    uncovered_bc,
                    selected_bc
                )
            )

            # STAGE 2: REDUCE - Aggregate and find best
            print("  Stage 2: Aggregating gains and finding best circle...")
            aggregated_gains = gains_rdd.reduce(aggregate_circle_gains)
            best_circle_id, gain = find_best_circle(aggregated_gains)

            if best_circle_id is None or gain == 0:
                print(f"  No more circles can cover any points. Stopping early at iteration {iteration}.")
                break

            print(f"  Selected Circle ID: {best_circle_id}, Gain: {gain}")

            # STAGE 3: UPDATE - Update coverage
            print("  Stage 3: Updating coverage status...")
            # Find the selected circle object
            selected_circle = None
            for circle in circles_list:
                cid = circle['circle_id'] if isinstance(circle, dict) else circle.circle_id
                if cid == best_circle_id:
                    selected_circle = circle
                    break

            selected_circle_bc = self.sc.broadcast(selected_circle)

            coverage_updates_rdd = points_rdd.mapPartitions(
                lambda partition: update_coverage_partition(
                    partition,
                    selected_circle_bc,
                    uncovered_bc
                )
            )

            # Collect updates
            coverage_updates = coverage_updates_rdd.collect()

            # Update state
            selected_circles.append(best_circle_id)
            cumulative_coverage += gain

            # Merge coverage updates
            new_uncovered_dict = merge_coverage_updates(coverage_updates, uncovered_bc.value)

            # Unpersist old broadcast variables
            uncovered_bc.unpersist()
            selected_bc.unpersist()
            if iteration > 1:
                selected_circle_bc.unpersist()

            # Broadcast new state
            uncovered_bc = self.sc.broadcast(new_uncovered_dict)
            selected_bc = self.sc.broadcast(selected_circles)

            # Record iteration statistics
            duration = time.time() - start_time
            self.iteration_stats.append({
                'iteration': iteration,
                'selected_circle_id': best_circle_id,
                'gain': gain,
                'cumulative_coverage': cumulative_coverage,
                'duration_sec': duration,
                'timestamp': datetime.now()
            })

            print(f"  Cumulative Coverage: {cumulative_coverage}")
            print(f"  Duration: {duration:.2f}s")

            # Checkpoint periodically to break lineage
            if self.config.checkpoint_dir and iteration % self.config.checkpoint_interval == 0:
                print(f"  Checkpointing at iteration {iteration}...")
                points_rdd.checkpoint()
                points_rdd.count()  # Force checkpoint

        # Cleanup
        points_rdd.unpersist()
        circles_bc.unpersist()
        uncovered_bc.unpersist()
        selected_bc.unpersist()

        print(f"\n{'='*70}")
        print(f"Algorithm Complete!")
        print(f"  Selected {len(selected_circles)} circles")
        print(f"  Total Coverage: {cumulative_coverage} points")
        print(f"{'='*70}\n")

        return selected_circles, self.iteration_stats

    def get_stats_summary(self):
        """
        Get summary statistics for the algorithm run.

        Returns:
            Dictionary with summary stats
        """
        if not self.iteration_stats:
            return {}

        total_duration = sum(stat['duration_sec'] for stat in self.iteration_stats)
        avg_duration = total_duration / len(self.iteration_stats)
        final_coverage = self.iteration_stats[-1]['cumulative_coverage']

        return {
            'iterations_completed': len(self.iteration_stats),
            'total_coverage': final_coverage,
            'total_duration_sec': total_duration,
            'avg_iteration_duration_sec': avg_duration,
            'selected_circles': [stat['selected_circle_id'] for stat in self.iteration_stats]
        }
