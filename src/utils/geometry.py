import math


def euclidean_distance(x1, y1, x2, y2):
    """
    Calculate Euclidean distance between two points.

    Args:
        x1, y1: Coordinates of first point
        x2, y2: Coordinates of second point

    Returns:
        float: Euclidean distance
    """
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)


def is_point_in_circle(point, circle):
    """
    Check if a point is covered by a circle.

    Args:
        point: Object with .x and .y attributes or dict with 'x' and 'y' keys
        circle: Object with .center_x, .center_y, .radius attributes
                or dict with 'center_x', 'center_y', 'radius' keys

    Returns:
        bool: True if point is within or on the circle boundary
    """
    # Handle both object attributes and dictionary access
    if isinstance(point, dict):
        px, py = point['x'], point['y']
    else:
        px, py = point.x, point.y

    if isinstance(circle, dict):
        cx, cy, r = circle['center_x'], circle['center_y'], circle['radius']
    else:
        cx, cy, r = circle.center_x, circle.center_y, circle.radius

    distance = euclidean_distance(px, py, cx, cy)
    return distance <= r


def circle_coverage(circle, points):
    """
    Compute how many points are covered by a circle.

    Args:
        circle: Circle object or dict with center and radius
        points: Iterable of point objects or dicts

    Returns:
        int: Count of covered points
    """
    count = 0
    for point in points:
        if is_point_in_circle(point, circle):
            count += 1
    return count


def point_distance_to_circle(point, circle):
    """
    Calculate distance from point to circle boundary.

    Args:
        point: Point object or dict
        circle: Circle object or dict

    Returns:
        float: Distance to circle boundary (negative if inside)
    """
    if isinstance(point, dict):
        px, py = point['x'], point['y']
    else:
        px, py = point.x, point.y

    if isinstance(circle, dict):
        cx, cy, r = circle['center_x'], circle['center_y'], circle['radius']
    else:
        cx, cy, r = circle.center_x, circle.center_y, circle.radius

    center_distance = euclidean_distance(px, py, cx, cy)
    return center_distance - r
