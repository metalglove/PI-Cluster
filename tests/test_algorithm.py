import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyspark import SparkConf, SparkContext
from pyspark.sql import SparkSession

from src.data.schemas import Point, Circle
from src.algorithm.greedy_submodular import GreedySubmodularCircleCover
from src.config.algorithm_config import AlgorithmConfig


class TestGreedySubmodularAlgorithm(unittest.TestCase):
    """Integration tests for the Greedy Submodular algorithm"""

    @classmethod
    def setUpClass(cls):
        """Set up Spark context for all tests"""
        conf = SparkConf().setMaster("local[2]").setAppName("AlgorithmTest")
        cls.sc = SparkContext(conf=conf)
        cls.spark = SparkSession(cls.sc)

    @classmethod
    def tearDownClass(cls):
        """Tear down Spark context"""
        cls.sc.stop()

    def test_simple_coverage(self):
        """Test algorithm on simple case with known solution"""
        # Create 10 points in a line
        points = [
            Point(i, i * 10.0, 0.0) for i in range(10)
        ]

        # Create 5 circles, each covering 2 adjacent points
        circles = [
            Circle(0, 5.0, 0.0, 7.0),    # Covers points 0, 1
            Circle(1, 15.0, 0.0, 7.0),   # Covers points 1, 2
            Circle(2, 25.0, 0.0, 7.0),   # Covers points 2, 3
            Circle(3, 35.0, 0.0, 7.0),   # Covers points 3, 4
            Circle(4, 45.0, 0.0, 7.0),   # Covers points 4, 5
        ]

        # Convert to RDD and list
        points_rdd = self.sc.parallelize([p.to_dict() for p in points])
        circles_list = [c.to_dict() for c in circles]

        # Run algorithm with k=5
        config = AlgorithmConfig(k=5, checkpoint_interval=10)
        algorithm = GreedySubmodularCircleCover(self.sc, k=5, config=config)

        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Verify results
        self.assertEqual(len(selected_circles), 5)
        self.assertEqual(len(iteration_stats), 5)

        # Check that coverage is monotonically increasing
        prev_coverage = 0
        for stat in iteration_stats:
            self.assertGreaterEqual(stat['cumulative_coverage'], prev_coverage)
            prev_coverage = stat['cumulative_coverage']

        # Final coverage should be at least 6 points (best case with k=5)
        final_coverage = iteration_stats[-1]['cumulative_coverage']
        self.assertGreaterEqual(final_coverage, 6)

    def test_complete_coverage(self):
        """Test that algorithm can achieve complete coverage"""
        # 5 points at (0,0), (10,0), (20,0), (30,0), (40,0)
        points = [
            Point(i, i * 10.0, 0.0) for i in range(5)
        ]

        # 5 circles, each perfectly covering one point
        circles = [
            Circle(i, i * 10.0, 0.0, 5.0) for i in range(5)
        ]

        points_rdd = self.sc.parallelize([p.to_dict() for p in points])
        circles_list = [c.to_dict() for c in circles]

        # Run with k=5
        config = AlgorithmConfig(k=5, checkpoint_interval=10)
        algorithm = GreedySubmodularCircleCover(self.sc, k=5, config=config)

        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Should cover all 5 points
        final_coverage = iteration_stats[-1]['cumulative_coverage']
        self.assertEqual(final_coverage, 5)

    def test_early_termination(self):
        """Test that algorithm stops early if no more points can be covered"""
        # 3 points
        points = [
            Point(0, 0.0, 0.0),
            Point(1, 10.0, 0.0),
            Point(2, 20.0, 0.0),
        ]

        # 2 circles that together cover all points
        circles = [
            Circle(0, 5.0, 0.0, 7.0),    # Covers points 0, 1
            Circle(1, 15.0, 0.0, 7.0),   # Covers points 1, 2
        ]

        points_rdd = self.sc.parallelize([p.to_dict() for p in points])
        circles_list = [c.to_dict() for c in circles]

        # Request k=5 but should stop at 2
        config = AlgorithmConfig(k=5, checkpoint_interval=10)
        algorithm = GreedySubmodularCircleCover(self.sc, k=5, config=config)

        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Should select at most 2 circles (might be less if coverage is complete)
        self.assertLessEqual(len(selected_circles), 2)

        # All points should be covered
        final_coverage = iteration_stats[-1]['cumulative_coverage']
        self.assertEqual(final_coverage, 3)

    def test_greedy_property(self):
        """Test that algorithm selects circles greedily (max gain each iteration)"""
        # 6 points clustered in two groups
        points = [
            # Cluster 1: 4 points
            Point(0, 0.0, 0.0),
            Point(1, 2.0, 0.0),
            Point(2, 0.0, 2.0),
            Point(3, 2.0, 2.0),
            # Cluster 2: 2 points
            Point(4, 100.0, 100.0),
            Point(5, 102.0, 100.0),
        ]

        # Two circles: one covers 4 points, one covers 2
        circles = [
            Circle(0, 1.0, 1.0, 2.0),     # Covers all 4 points in cluster 1
            Circle(1, 101.0, 100.0, 2.0), # Covers 2 points in cluster 2
        ]

        points_rdd = self.sc.parallelize([p.to_dict() for p in points])
        circles_list = [c.to_dict() for c in circles]

        # Run with k=1
        config = AlgorithmConfig(k=1, checkpoint_interval=10)
        algorithm = GreedySubmodularCircleCover(self.sc, k=1, config=config)

        selected_circles, iteration_stats = algorithm.run(points_rdd, circles_list)

        # Should select circle 0 (covers 4 points) over circle 1 (covers 2)
        self.assertEqual(selected_circles[0], 0)
        self.assertEqual(iteration_stats[0]['gain'], 4)


if __name__ == '__main__':
    unittest.main()
