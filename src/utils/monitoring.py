from datetime import datetime


class IterationMonitor:
    """Monitor performance metrics for each iteration"""

    def __init__(self):
        self.iteration_stats = []

    def record_iteration(self, iteration, circle_id, gain, cumulative_coverage, duration_sec):
        """
        Record stats for one iteration.

        Args:
            iteration: Iteration number
            circle_id: ID of selected circle
            gain: Points covered by this circle
            cumulative_coverage: Total points covered so far
            duration_sec: Time taken for this iteration
        """
        self.iteration_stats.append({
            'iteration': iteration,
            'circle_id': circle_id,
            'gain': gain,
            'cumulative_coverage': cumulative_coverage,
            'duration_sec': duration_sec,
            'timestamp': datetime.now()
        })

    def print_progress(self, iteration, k, gain, cumulative_coverage):
        """
        Print progress to console.

        Args:
            iteration: Current iteration
            k: Total iterations (k value)
            gain: Gain in this iteration
            cumulative_coverage: Total coverage
        """
        percent = (iteration / k) * 100
        print(f"Iteration {iteration}/{k} ({percent:.1f}%): "
              f"Selected circle with gain {gain}, "
              f"Total coverage: {cumulative_coverage}")

    def get_stats_df(self, spark):
        """
        Convert stats to Spark DataFrame.

        Args:
            spark: SparkSession

        Returns:
            DataFrame with iteration statistics
        """
        from src.data.schemas import Schemas
        return spark.createDataFrame(self.iteration_stats, schema=Schemas.result_schema())

    def save_stats(self, output_path, spark):
        """
        Save iteration statistics to Parquet.

        Args:
            output_path: Path to save parquet file
            spark: SparkSession
        """
        df = self.get_stats_df(spark)
        df.write.mode('overwrite').parquet(output_path)
        print(f"Saved iteration stats to {output_path}")

    def get_summary(self):
        """
        Get summary statistics.

        Returns:
            Dictionary with summary stats
        """
        if not self.iteration_stats:
            return {}

        total_duration = sum(stat['duration_sec'] for stat in self.iteration_stats)
        avg_duration = total_duration / len(self.iteration_stats)
        final_coverage = self.iteration_stats[-1]['cumulative_coverage']

        return {
            'total_iterations': len(self.iteration_stats),
            'final_coverage': final_coverage,
            'total_duration_sec': total_duration,
            'avg_iteration_duration_sec': avg_duration
        }


class ResourceMonitor:
    """Monitor resource usage (memory, disk, network)"""

    def __init__(self, spark_context):
        self.sc = spark_context

    def get_executor_metrics(self):
        """
        Retrieve executor memory and disk usage.

        Returns:
            List of executor metrics
        """
        status = self.sc.statusTracker()
        executor_infos = status.getExecutorInfos()

        metrics = []
        for executor in executor_infos:
            metrics.append({
                'executor_id': executor.executorId(),
                'host': executor.host(),
            })
        return metrics

    def print_executor_info(self):
        """Print executor information"""
        metrics = self.get_executor_metrics()
        print(f"\nExecutor Information ({len(metrics)} executors):")
        for m in metrics:
            print(f"  Executor {m['executor_id']} on {m['host']}")
