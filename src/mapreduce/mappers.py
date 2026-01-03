from src.utils.geometry import is_point_in_circle


def compute_local_circle_gains(partition_iterator, broadcast_circles, broadcast_uncovered, broadcast_selected):
    """
    Map function: Compute local gain for each candidate circle on this partition.

    This function processes a partition of points and computes how many uncovered
    points in this partition would be covered by each candidate circle.

    Args:
        partition_iterator: Iterator of points in this partition (Row objects or dicts)
        broadcast_circles: Broadcast variable containing all candidate circles
        broadcast_uncovered: Broadcast variable with coverage status dict {point_id: is_uncovered}
        broadcast_selected: Broadcast variable with set of already selected circle IDs

    Yields:
        Dictionary: {circle_id: local_gain} for all candidate circles
    """
    # Convert partition to list to allow multiple passes
    points = list(partition_iterator)

    if len(points) == 0:
        # Empty partition, yield empty gains
        yield {}
        return

    # Get broadcast values
    circles = broadcast_circles.value
    uncovered = broadcast_uncovered.value
    selected = broadcast_selected.value

    # Convert selected to set for fast lookup
    selected_set = set(selected) if isinstance(selected, list) else selected

    # Initialize gains dictionary
    local_gains = {}

    # For each candidate circle (not already selected)
    for circle in circles:
        # Handle both dict and object access
        if isinstance(circle, dict):
            circle_id = circle['circle_id']
        else:
            circle_id = circle.circle_id

        # Skip if already selected
        if circle_id in selected_set:
            continue

        # Count how many uncovered points in this partition are covered by this circle
        gain = 0
        for point in points:
            # Get point_id
            if isinstance(point, dict):
                point_id = point['point_id']
            else:
                point_id = point.point_id

            # Only count if point is still uncovered
            if uncovered.get(point_id, True):
                if is_point_in_circle(point, circle):
                    gain += 1

        local_gains[circle_id] = gain

    # Yield the local gains dictionary
    yield local_gains


def update_coverage_partition(partition_iterator, broadcast_selected_circle, broadcast_uncovered):
    """
    Map function: Update coverage status for points in this partition.

    After a circle is selected, this function identifies which points in the
    partition are now covered by that circle.

    Args:
        partition_iterator: Iterator of points in this partition
        broadcast_selected_circle: Broadcast variable with the newly selected circle
        broadcast_uncovered: Broadcast variable with current coverage status

    Yields:
        Tuples: (point_id, False) for each newly covered point
    """
    selected_circle = broadcast_selected_circle.value
    uncovered = broadcast_uncovered.value

    for point in partition_iterator:
        # Get point_id
        if isinstance(point, dict):
            point_id = point['point_id']
        else:
            point_id = point.point_id

        # Only process if point was uncovered
        if uncovered.get(point_id, True):
            # Check if now covered by selected circle
            if is_point_in_circle(point, selected_circle):
                yield (point_id, False)  # Mark as covered


def compute_initial_coverage_status(partition_iterator):
    """
    Map function: Initialize coverage status for all points.

    Args:
        partition_iterator: Iterator of points

    Yields:
        Tuples: (point_id, True) for each point (all initially uncovered)
    """
    for point in partition_iterator:
        if isinstance(point, dict):
            point_id = point['point_id']
        else:
            point_id = point.point_id

        yield (point_id, True)  # True = uncovered
