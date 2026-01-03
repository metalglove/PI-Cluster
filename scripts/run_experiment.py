#!/usr/bin/env python3
"""
Run Circle Cover experiments from YAML configuration.
"""

import argparse
import yaml
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyspark.sql import SparkSession
from src.config.spark_config import SparkClusterConfig
from src.config.algorithm_config import AlgorithmConfig
from src.data.loaders import DataLoader
from src.data.generators import DatasetBuilder
from src.algorithm.greedy_submodular import GreedySubmodularCircleCover


def main():
    parser = argparse.ArgumentParser(
        description='Run Circle Cover experiment from YAML config'
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to experiment YAML configuration file'
    )
    parser.add_argument(
        '--master',
        default=None,
        help='Spark master URL (default: local mode)'
    )
    parser.add_argument(
        '--generate-data',
        action='store_true',
        help='Generate data before running experiment'
    )

    args = parser.parse_args()

    # Load configuration
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    print(f"\n{'='*70}")
    print("Circle Cover Experiment")
    print(f"{'='*70}\n")
    print(f"Configuration file: {args.config}")

    # Extract configurations
    algo_config_dict = config['algorithm']
    points_config = config['points']
    circles_config = config['circles']
    output_config = config['output']

    output_dir = output_config['dir']
    data_dir = f"{output_dir}/data"

    # Create Spark session
    spark_conf = SparkClusterConfig.get_spark_conf(
        app_name="CircleCoverExperiment",
        master=args.master
    )
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()
    sc = spark.sparkContext

    print(f"Spark version: {spark.version}")
    print(f"Master: {sc.master}\n")

    try:
        # Generate data if requested
        if args.generate_data:
            print("Generating dataset...")
            builder = DatasetBuilder(spark)
            points_df, circles_df = builder.build_and_save(
                {'points': points_config, 'circles': circles_config},
                data_dir
            )
        else:
            # Load existing data
            print("Loading dataset...")
            loader = DataLoader(spark)
            points_df = loader.load_points(f"{data_dir}/points")
            circles_df = loader.load_circles(f"{data_dir}/circles")

        # Prepare data
        points_rdd = points_df.rdd
        circles_list = circles_df.collect()

        # Calculate optimal partitions
        n_points = points_df.count()
        data_size_mb = SparkClusterConfig.estimate_data_size_mb(n_points)
        optimal_partitions = SparkClusterConfig.calculate_partitions(data_size_mb)

        print(f"\nData statistics:")
        print(f"  Points: {n_points}")
        print(f"  Circles: {len(circles_list)}")
        print(f"  Optimal partitions: {optimal_partitions}")

        # Repartition
        points_rdd = points_rdd.repartition(optimal_partitions)

        # Create algorithm config
        algo_config = AlgorithmConfig(
            k=algo_config_dict['k'],
            checkpoint_interval=algo_config_dict.get('checkpoint_interval', 5),
            checkpoint_dir=algo_config_dict.get('checkpoint_dir', None)
        )

        print(f"\nAlgorithm parameters:")
        print(f"  k: {algo_config.k}")
        print(f"  Checkpoint interval: {algo_config.checkpoint_interval}")

        # Run algorithm
        print("\nRunning algorithm...")
        algorithm = GreedySubmodularCircleCover(sc, algo_config.k, algo_config)
        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Save results
        print(f"\nSaving results...")
        loader = DataLoader(spark)
        results_dir = f"{output_dir}/results"
        loader.save_results(iteration_stats, results_dir)

        # Print summary
        summary = algorithm.get_stats_summary()
        print("\n" + "="*70)
        print("EXPERIMENT RESULTS")
        print("="*70)
        print(f"Iterations: {summary['iterations_completed']}")
        print(f"Coverage: {summary['total_coverage']} / {n_points} points "
              f"({100.0 * summary['total_coverage'] / n_points:.2f}%)")
        print(f"Duration: {summary['total_duration_sec']:.2f}s")
        print(f"Avg iteration: {summary['avg_iteration_duration_sec']:.2f}s")
        print(f"Selected circles: {summary['selected_circles']}")
        print("="*70 + "\n")

        print(f"Results saved to {output_dir}")

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
