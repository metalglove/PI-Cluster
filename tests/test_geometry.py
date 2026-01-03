import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.geometry import euclidean_distance, is_point_in_circle, circle_coverage, point_distance_to_circle


class TestGeometry(unittest.TestCase):

    def test_euclidean_distance(self):
        """Test Euclidean distance calculation"""
        self.assertEqual(euclidean_distance(0, 0, 3, 4), 5.0)
        self.assertEqual(euclidean_distance(0, 0, 0, 0), 0.0)
        self.assertAlmostEqual(euclidean_distance(1, 1, 2, 2), 1.414213, places=5)

    def test_is_point_in_circle_dict(self):
        """Test point-in-circle with dictionaries"""
        # Point at origin, circle centered at origin with radius 5
        point = {'x': 0, 'y': 0}
        circle = {'center_x': 0, 'center_y': 0, 'radius': 5}
        self.assertTrue(is_point_in_circle(point, circle))

        # Point on boundary
        point = {'x': 3, 'y': 4}
        circle = {'center_x': 0, 'center_y': 0, 'radius': 5}
        self.assertTrue(is_point_in_circle(point, circle))

        # Point outside
        point = {'x': 10, 'y': 10}
        circle = {'center_x': 0, 'center_y': 0, 'radius': 5}
        self.assertFalse(is_point_in_circle(point, circle))

        # Point inside
        point = {'x': 1, 'y': 1}
        circle = {'center_x': 0, 'center_y': 0, 'radius': 5}
        self.assertTrue(is_point_in_circle(point, circle))

    def test_is_point_in_circle_object(self):
        """Test point-in-circle with objects"""
        class Point:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class Circle:
            def __init__(self, cx, cy, r):
                self.center_x = cx
                self.center_y = cy
                self.radius = r

        point = Point(0, 0)
        circle = Circle(0, 0, 5)
        self.assertTrue(is_point_in_circle(point, circle))

        point = Point(10, 10)
        circle = Circle(0, 0, 5)
        self.assertFalse(is_point_in_circle(point, circle))

    def test_circle_coverage(self):
        """Test circle coverage counting"""
        circle = {'center_x': 0, 'center_y': 0, 'radius': 5}
        points = [
            {'x': 0, 'y': 0},    # inside
            {'x': 3, 'y': 4},    # on boundary
            {'x': 1, 'y': 1},    # inside
            {'x': 10, 'y': 10},  # outside
            {'x': 20, 'y': 20},  # outside
        ]
        self.assertEqual(circle_coverage(circle, points), 3)

        # Empty points
        self.assertEqual(circle_coverage(circle, []), 0)

        # All points outside
        points_outside = [{'x': 10, 'y': 10}, {'x': 20, 'y': 20}]
        self.assertEqual(circle_coverage(circle, points_outside), 0)

        # All points inside
        points_inside = [{'x': 0, 'y': 0}, {'x': 1, 'y': 1}, {'x': 2, 'y': 2}]
        self.assertEqual(circle_coverage(circle, points_inside), 3)

    def test_point_distance_to_circle(self):
        """Test distance from point to circle boundary"""
        circle = {'center_x': 0, 'center_y': 0, 'radius': 5}

        # Point at center
        point = {'x': 0, 'y': 0}
        self.assertEqual(point_distance_to_circle(point, circle), -5.0)

        # Point on boundary
        point = {'x': 5, 'y': 0}
        self.assertAlmostEqual(point_distance_to_circle(point, circle), 0.0, places=10)

        # Point outside
        point = {'x': 10, 'y': 0}
        self.assertEqual(point_distance_to_circle(point, circle), 5.0)

        # Point inside
        point = {'x': 3, 'y': 0}
        self.assertEqual(point_distance_to_circle(point, circle), -2.0)


if __name__ == '__main__':
    unittest.main()
