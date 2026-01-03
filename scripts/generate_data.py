#!/usr/bin/env python3
"""
Generate synthetic datasets for Circle Cover experiments.
"""

import argparse
import yaml
import sys
from pyspark.sql import SparkSession

# Add parent directory to path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.data.generators import DatasetBuilder
from src.config.spark_config import SparkClusterConfig


def main():
    parser = argparse.ArgumentParser(
        description='Generate synthetic point and circle datasets'
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to experiment YAML configuration file'
    )
    parser.add_argument(
        '--output-dir',
        required=True,
        help='Output directory for generated data'
    )
    parser.add_argument(
        '--master',
        default=None,
        help='Spark master URL (default: local mode)'
    )

    args = parser.parse_args()

    # Load configuration
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    print(f"\n{'='*70}")
    print("Data Generation for Circle Cover Experiments")
    print(f"{'='*70}\n")
    print(f"Configuration: {args.config}")
    print(f"Output directory: {args.output_dir}")

    # Create Spark session
    spark_conf = SparkClusterConfig.get_spark_conf(
        app_name="DataGenerator",
        master=args.master
    )
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()

    try:
        # Build dataset
        builder = DatasetBuilder(spark)
        points_df, circles_df = builder.build_and_save(config, args.output_dir)

        print(f"\nDataset generation complete!")
        print(f"  Points: {points_df.count()}")
        print(f"  Circles: {circles_df.count()}")
        print(f"  Location: {args.output_dir}")

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
