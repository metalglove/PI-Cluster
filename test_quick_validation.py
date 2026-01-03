#!/usr/bin/env python3
"""
Quick validation test - runs a tiny example locally
"""

import sys
from pyspark import SparkConf, SparkContext
from pyspark.sql import SparkSession

from src.data.schemas import Point, Circle
from src.algorithm.greedy_submodular import GreedySubmodularCircleCover
from src.config.algorithm_config import AlgorithmConfig

def test_simple_example():
    """Run a simple test case"""
    print("\n" + "="*70)
    print("QUICK VALIDATION TEST")
    print("="*70)

    # Set up Spark in local mode
    print("\nSetting up Spark (local mode)...")
    conf = SparkConf().setMaster("local[2]").setAppName("QuickValidation")
    sc = SparkContext(conf=conf)
    sc.setLogLevel("ERROR")  # Reduce Spark logging

    try:
        # Create a simple test case: 10 points in a line
        print("Creating test data...")
        points = [
            Point(0, 0.0, 0.0),
            Point(1, 10.0, 0.0),
            Point(2, 20.0, 0.0),
            Point(3, 30.0, 0.0),
            Point(4, 40.0, 0.0),
            Point(5, 50.0, 0.0),
            Point(6, 60.0, 0.0),
            Point(7, 70.0, 0.0),
            Point(8, 80.0, 0.0),
            Point(9, 90.0, 0.0),
        ]

        # Create circles that can cover these points
        circles = [
            Circle(0, 15.0, 0.0, 20.0),   # Can cover points 0,1,2,3
            Circle(1, 45.0, 0.0, 20.0),   # Can cover points 3,4,5,6
            Circle(2, 75.0, 0.0, 20.0),   # Can cover points 6,7,8,9
            Circle(3, 5.0, 0.0, 10.0),    # Can cover points 0,1
            Circle(4, 85.0, 0.0, 10.0),   # Can cover points 8,9
        ]

        print(f"  Points: {len(points)}")
        print(f"  Circles: {len(circles)}")

        # Convert to RDD and list
        points_rdd = sc.parallelize([p.to_dict() for p in points], numSlices=2)
        circles_list = [c.to_dict() for c in circles]

        # Run algorithm with k=3
        print("\nRunning algorithm with k=3...")
        config = AlgorithmConfig(k=3, checkpoint_interval=10)
        algorithm = GreedySubmodularCircleCover(sc, k=3, config=config)

        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Validate results
        print("\n" + "="*70)
        print("VALIDATION RESULTS")
        print("="*70)

        success = True

        # Check 1: Should select 3 circles
        if len(selected_circles) == 3:
            print(f"✓ Selected {len(selected_circles)} circles (expected 3)")
        else:
            print(f"✗ Selected {len(selected_circles)} circles (expected 3)")
            success = False

        # Check 2: Should have 3 iteration stats
        if len(iteration_stats) == 3:
            print(f"✓ Recorded {len(iteration_stats)} iterations")
        else:
            print(f"✗ Recorded {len(iteration_stats)} iterations (expected 3)")
            success = False

        # Check 3: Coverage should be monotonically increasing
        monotonic = True
        prev = 0
        for stat in iteration_stats:
            if stat['cumulative_coverage'] < prev:
                monotonic = False
            prev = stat['cumulative_coverage']

        if monotonic:
            print("✓ Coverage is monotonically increasing")
        else:
            print("✗ Coverage is not monotonically increasing")
            success = False

        # Check 4: Should cover all or most points
        final_coverage = iteration_stats[-1]['cumulative_coverage']
        if final_coverage >= 8:  # Should cover at least 8 out of 10 points
            print(f"✓ Final coverage: {final_coverage}/10 points")
        else:
            print(f"✗ Final coverage: {final_coverage}/10 points (expected ≥8)")
            success = False

        # Print iteration details
        print("\nIteration details:")
        for stat in iteration_stats:
            print(f"  Iteration {stat['iteration']}: "
                  f"Circle {stat['selected_circle_id']} → "
                  f"Gain: {stat['gain']}, "
                  f"Total: {stat['cumulative_coverage']}, "
                  f"Time: {stat['duration_sec']:.3f}s")

        # Summary
        summary = algorithm.get_stats_summary()
        print(f"\nTotal runtime: {summary['total_duration_sec']:.3f} seconds")
        print(f"Average per iteration: {summary['avg_iteration_duration_sec']:.3f} seconds")

        print("\n" + "="*70)
        if success:
            print("ALL CHECKS PASSED ✓")
            print("="*70 + "\n")
            return 0
        else:
            print("SOME CHECKS FAILED ✗")
            print("="*70 + "\n")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        sc.stop()

if __name__ == "__main__":
    exit_code = test_simple_example()
    sys.exit(exit_code)
