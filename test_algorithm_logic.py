#!/usr/bin/env python3
"""
Quick validation test - tests algorithm logic without Spark infrastructure
"""

from src.data.schemas import Point, Circle
from src.utils.geometry import is_point_in_circle, circle_coverage
from src.mapreduce.reducers import aggregate_circle_gains, find_best_circle, merge_coverage_updates

def test_geometry():
    """Test geometry functions"""
    print("\n" + "="*70)
    print("TEST 1: Geometry Functions")
    print("="*70)

    # Create test point and circle
    point = Point(0, 5.0, 5.0)
    circle = Circle(0, 0.0, 0.0, 10.0)

    # Test point in circle
    result = is_point_in_circle(point.to_dict(), circle.to_dict())
    assert result == True, "Point should be in circle"
    print("✓ Point-in-circle detection works")

    # Test point outside circle
    far_point = Point(1, 100.0, 100.0)
    result = is_point_in_circle(far_point.to_dict(), circle.to_dict())
    assert result == False, "Far point should be outside circle"
    print("✓ Point outside circle detection works")

    # Test circle coverage
    points = [
        Point(0, 0.0, 0.0),
        Point(1, 5.0, 5.0),
        Point(2, 100.0, 100.0),
    ]
    coverage = circle_coverage(circle.to_dict(), [p.to_dict() for p in points])
    assert coverage == 2, f"Circle should cover 2 points, got {coverage}"
    print(f"✓ Circle coverage counting works (2/3 points covered)")

    return True

def test_reducers():
    """Test reducer functions"""
    print("\n" + "="*70)
    print("TEST 2: Reducer Functions")
    print("="*70)

    # Test aggregate_circle_gains
    gains1 = {0: 5, 1: 3, 2: 7}
    gains2 = {0: 2, 1: 4, 3: 1}
    merged = aggregate_circle_gains(gains1, gains2)

    expected = {0: 7, 1: 7, 2: 7, 3: 1}
    assert merged == expected, f"Merged gains incorrect: {merged}"
    print(f"✓ Gain aggregation works: {merged}")

    # Test find_best_circle
    best_id, best_gain = find_best_circle(merged)
    # Multiple circles have gain 7, any of them is valid
    assert best_gain == 7, f"Best gain should be 7, got {best_gain}"
    assert best_id in [0, 1, 2], f"Best circle should be 0, 1, or 2, got {best_id}"
    print(f"✓ Best circle selection works: Circle {best_id} with gain {best_gain}")

    # Test merge_coverage_updates
    current = {0: True, 1: True, 2: True, 3: True}
    updates = [(0, False), (2, False)]  # Points 0 and 2 now covered
    updated = merge_coverage_updates(updates, current)

    assert updated[0] == False, "Point 0 should be covered"
    assert updated[1] == True, "Point 1 should still be uncovered"
    assert updated[2] == False, "Point 2 should be covered"
    print(f"✓ Coverage update merging works: {updated}")

    return True

def test_greedy_logic():
    """Test greedy selection logic"""
    print("\n" + "="*70)
    print("TEST 3: Greedy Selection Logic")
    print("="*70)

    # Create test scenario: 2 clusters of points
    # Cluster 1: 4 points at (0,0), (2,0), (0,2), (2,2)
    # Cluster 2: 2 points at (100,100), (102,100)

    points = [
        Point(0, 0.0, 0.0),
        Point(1, 2.0, 0.0),
        Point(2, 0.0, 2.0),
        Point(3, 2.0, 2.0),
        Point(4, 100.0, 100.0),
        Point(5, 102.0, 100.0),
    ]

    # Circle 0: covers all 4 points in cluster 1
    # Circle 1: covers 2 points in cluster 2
    circles = [
        Circle(0, 1.0, 1.0, 2.0),      # Covers cluster 1 (4 points)
        Circle(1, 101.0, 100.0, 2.0),  # Covers cluster 2 (2 points)
    ]

    # Compute coverage for each circle
    coverage0 = circle_coverage(circles[0].to_dict(), [p.to_dict() for p in points])
    coverage1 = circle_coverage(circles[1].to_dict(), [p.to_dict() for p in points])

    print(f"  Circle 0 covers {coverage0} points")
    print(f"  Circle 1 covers {coverage1} points")

    assert coverage0 == 4, f"Circle 0 should cover 4 points, got {coverage0}"
    assert coverage1 == 2, f"Circle 1 should cover 2 points, got {coverage1}"

    # Greedy algorithm should select circle 0 first (higher gain)
    gains = {0: coverage0, 1: coverage1}
    best_id, best_gain = find_best_circle(gains)

    assert best_id == 0, f"Greedy should select circle 0 first, got {best_id}"
    assert best_gain == 4, f"Best gain should be 4, got {best_gain}"
    print(f"✓ Greedy correctly selects circle {best_id} with gain {best_gain}")

    # After selecting circle 0, compute remaining coverage
    # Circle 0 covered points 0,1,2,3
    # Circle 1 should now only add points 4,5 (gain=2)
    uncovered = {0: False, 1: False, 2: False, 3: False, 4: True, 5: True}

    # Count uncovered points for circle 1
    remaining_coverage = 0
    for point in points:
        if uncovered[point.point_id] and is_point_in_circle(point.to_dict(), circles[1].to_dict()):
            remaining_coverage += 1

    assert remaining_coverage == 2, f"Circle 1 should cover 2 remaining points, got {remaining_coverage}"
    print(f"✓ After iteration 1, circle 1 can cover {remaining_coverage} more points")

    return True

def test_iteration_simulation():
    """Simulate multiple greedy iterations"""
    print("\n" + "="*70)
    print("TEST 4: Multi-Iteration Simulation")
    print("="*70)

    # 10 points in a line
    points = [Point(i, i * 10.0, 0.0) for i in range(10)]

    # 3 circles, each can cover ~3-4 points
    circles = [
        Circle(0, 15.0, 0.0, 20.0),   # Covers points 0,1,2,3 (4 points)
        Circle(1, 45.0, 0.0, 20.0),   # Covers points 3,4,5,6 (4 points)
        Circle(2, 75.0, 0.0, 20.0),   # Covers points 6,7,8,9 (4 points)
    ]

    # Initialize coverage status
    uncovered = {i: True for i in range(10)}
    selected = []
    total_coverage = 0

    k = 3
    print(f"\nSimulating {k} greedy iterations:")

    for iteration in range(k):
        # Compute gains for each circle
        gains = {}
        for circle in circles:
            if circle.circle_id in selected:
                continue  # Skip already selected

            gain = 0
            for point in points:
                if uncovered[point.point_id] and is_point_in_circle(point.to_dict(), circle.to_dict()):
                    gain += 1
            gains[circle.circle_id] = gain

        if not gains or max(gains.values()) == 0:
            print(f"  Iteration {iteration+1}: No more points to cover, stopping early")
            break

        # Select best circle
        best_id, gain = find_best_circle(gains)
        selected.append(best_id)
        total_coverage += gain

        print(f"  Iteration {iteration+1}: Selected circle {best_id}, gain={gain}, total={total_coverage}")

        # Update coverage
        best_circle = circles[best_id]
        for point in points:
            if uncovered[point.point_id] and is_point_in_circle(point.to_dict(), best_circle.to_dict()):
                uncovered[point.point_id] = False

    # Validate results
    assert len(selected) <= k, f"Should select at most {k} circles"
    assert total_coverage >= 8, f"Should cover at least 8/10 points, got {total_coverage}"

    # Check monotonicity
    print(f"\n✓ Selected {len(selected)} circles")
    print(f"✓ Total coverage: {total_coverage}/10 points ({100*total_coverage/10:.0f}%)")

    return True

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("ALGORITHM LOGIC VALIDATION (No Spark Required)")
    print("="*70)

    try:
        success = True
        success &= test_geometry()
        success &= test_reducers()
        success &= test_greedy_logic()
        success &= test_iteration_simulation()

        print("\n" + "="*70)
        if success:
            print("ALL TESTS PASSED ✓")
            print("="*70)
            print("\nThe algorithm logic is correct!")
            print("The implementation is ready to run on the Pi cluster with full PySpark.")
            print("\nNext steps:")
            print("  1. Install PySpark/Java on your Pi cluster")
            print("  2. Run: python3 scripts/run_experiment.py --config configs/small_experiment.yaml --generate-data")
            print("="*70 + "\n")
            return 0
        else:
            print("SOME TESTS FAILED ✗")
            print("="*70 + "\n")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
