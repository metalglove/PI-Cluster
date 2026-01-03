import argparse
import sys
from pyspark.sql import SparkSession
from pyspark import SparkContext

from src.config.spark_config import SparkClusterConfig
from src.config.algorithm_config import AlgorithmConfig
from src.data.loaders import DataLoader
from src.algorithm.greedy_submodular import GreedySubmodularCircleCover


def main():
    """
    Main entry point for running the Greedy Submodular Circle Cover algorithm.
    """
    parser = argparse.ArgumentParser(
        description='Run Greedy Submodular Circle Cover algorithm on Pi cluster'
    )
    parser.add_argument(
        '--points',
        required=True,
        help='Path to points parquet directory'
    )
    parser.add_argument(
        '--circles',
        required=True,
        help='Path to circles parquet directory'
    )
    parser.add_argument(
        '--k',
        type=int,
        required=True,
        help='Number of circles to select'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output directory for results'
    )
    parser.add_argument(
        '--master',
        default=None,
        help='Spark master URL (default: local mode)'
    )
    parser.add_argument(
        '--checkpoint-dir',
        default=None,
        help='Directory for checkpoints (default: no checkpointing)'
    )
    parser.add_argument(
        '--checkpoint-interval',
        type=int,
        default=5,
        help='Checkpoint every N iterations (default: 5)'
    )

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print("Greedy Submodular Circle Cover - PySpark Implementation")
    print(f"{'='*70}\n")

    # Create Spark configuration
    print("Setting up Spark configuration...")
    spark_conf = SparkClusterConfig.get_spark_conf(
        app_name="GreedySubmodularCircleCover",
        master=args.master
    )

    # Create Spark session
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()
    sc = spark.sparkContext

    print(f"Spark version: {spark.version}")
    print(f"Master: {sc.master}")
    print(f"App ID: {sc.applicationId}\n")

    try:
        # Load data
        print("Loading data...")
        loader = DataLoader(spark)
        points_df = loader.load_points(args.points)
        circles_df = loader.load_circles(args.circles)

        # Convert to RDD and list
        points_rdd = points_df.rdd
        circles_list = circles_df.collect()

        # Calculate and set optimal partitions
        n_points = points_df.count()
        data_size_mb = SparkClusterConfig.estimate_data_size_mb(n_points)
        optimal_partitions = SparkClusterConfig.calculate_partitions(data_size_mb)

        print(f"\nData statistics:")
        print(f"  Points: {n_points}")
        print(f"  Estimated size: {data_size_mb:.2f} MB")
        print(f"  Optimal partitions: {optimal_partitions}")
        print(f"  Circles: {len(circles_list)}")

        # Repartition if needed
        current_partitions = points_rdd.getNumPartitions()
        print(f"  Current partitions: {current_partitions}")

        if current_partitions != optimal_partitions:
            print(f"  Repartitioning to {optimal_partitions}...")
            points_rdd = points_rdd.repartition(optimal_partitions)

        # Create algorithm config
        algo_config = AlgorithmConfig(
            k=args.k,
            checkpoint_interval=args.checkpoint_interval,
            checkpoint_dir=args.checkpoint_dir
        )

        print(f"\nAlgorithm configuration:")
        print(f"  k (circles to select): {algo_config.k}")
        print(f"  Checkpoint interval: {algo_config.checkpoint_interval}")
        print(f"  Checkpoint directory: {algo_config.checkpoint_dir}")

        # Run algorithm
        print("\nStarting algorithm...")
        algorithm = GreedySubmodularCircleCover(sc, args.k, algo_config)
        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Save results
        print(f"\nSaving results to {args.output}...")
        loader.save_results(iteration_stats, f"{args.output}/iterations")

        # Print summary
        summary = algorithm.get_stats_summary()
        print("\n" + "="*70)
        print("RESULTS SUMMARY")
        print("="*70)
        print(f"Iterations completed: {summary['iterations_completed']}")
        print(f"Total coverage: {summary['total_coverage']} points")
        print(f"Total duration: {summary['total_duration_sec']:.2f} seconds")
        print(f"Avg iteration duration: {summary['avg_iteration_duration_sec']:.2f} seconds")
        print(f"Selected circles: {summary['selected_circles']}")
        print("="*70 + "\n")

        print(f"Results saved successfully to {args.output}")

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # Stop Spark
        spark.stop()
        print("\nSpark session stopped.")


if __name__ == "__main__":
    main()
