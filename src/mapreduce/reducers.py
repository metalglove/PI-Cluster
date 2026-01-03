def aggregate_circle_gains(gains_dict_1, gains_dict_2):
    """
    Reduce function: Merge two local gain dictionaries.

    This function aggregates gain counts from different partitions by
    summing the gains for each circle.

    Args:
        gains_dict_1: Dictionary of circle_id -> gain
        gains_dict_2: Dictionary of circle_id -> gain

    Returns:
        Merged dictionary with summed gains
    """
    # Start with a copy of the first dictionary
    merged = gains_dict_1.copy()

    # Add gains from second dictionary
    for circle_id, gain in gains_dict_2.items():
        merged[circle_id] = merged.get(circle_id, 0) + gain

    return merged


def find_best_circle(aggregated_gains):
    """
    Find the circle with maximum gain.

    Args:
        aggregated_gains: Dictionary of circle_id -> total_gain

    Returns:
        Tuple: (best_circle_id, max_gain)
               Returns (None, 0) if no circles available
    """
    if not aggregated_gains:
        return (None, 0)

    # Find circle with maximum gain
    best_circle_id = max(aggregated_gains, key=aggregated_gains.get)
    max_gain = aggregated_gains[best_circle_id]

    return (best_circle_id, max_gain)


def merge_coverage_updates(coverage_updates, current_uncovered):
    """
    Merge coverage updates from all partitions into current status.

    Args:
        coverage_updates: List of (point_id, new_uncovered_status) tuples from partitions
                         where new_uncovered_status=False means point is now covered
        current_uncovered: Current coverage status dictionary (True=uncovered, False=covered)

    Returns:
        Updated coverage status dictionary
    """
    # Start with current status
    updated = current_uncovered.copy()

    # Apply updates - the second element is the new uncovered status
    for point_id, new_uncovered_status in coverage_updates:
        updated[point_id] = new_uncovered_status

    return updated


def reduce_coverage_status(status_1, status_2):
    """
    Reduce function for coverage status (if using RDD reduce instead of collect).

    Args:
        status_1: Dictionary of point_id -> is_uncovered
        status_2: Dictionary of point_id -> is_uncovered

    Returns:
        Merged dictionary (OR logic: covered if covered in either)
    """
    merged = status_1.copy()

    for point_id, is_uncovered in status_2.items():
        # If covered in either, it's covered
        merged[point_id] = merged.get(point_id, True) and is_uncovered

    return merged
