"""
Client for the visualization server (viz_server.py), shared by main.py and alg.py.

Besides sending events, it has small helpers that let a Spark job report which machine ran
each partition and how much work it did, so the UI can show the work being split across the Pis.
Helpers used inside Spark tasks need this file on the workers: call ship_to_workers(sc) first.
"""

import os
import socket
import time
from typing import Callable, Iterable, List, Optional, Tuple

Point = Tuple[float, float]           # (x, y)
Circle = Tuple[float, float, float]   # (cx, cy, radius)

# Key of the extra item with_partition_stats() adds to a partition's output.
STATS_KEY = "__partition_stats__"


def ship_to_workers(sc) -> None:
    """Make this module importable inside Spark tasks (on the Pis it is only on the driver)."""
    sc.addPyFile(os.path.abspath(__file__))


def machine_identity() -> Tuple[str, Optional[str]]:
    """(hostname, LAN IP) of the machine running this code."""
    host = socket.gethostname()
    ip = None
    try:
        # The Spark master lists workers by IP; find ours so the UI can match them up.
        # (Connecting a UDP socket sends nothing, it only picks the outgoing interface.)
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))
        ip = probe.getsockname()[0]
        probe.close()
    except OSError:
        pass
    return host, ip


def with_partition_stats(mapper: Callable[[Iterable], Iterable],
                         sent_circles: Callable[[object], List[Circle]]):
    """
    Wrap a mapPartitions function for use with mapPartitionsWithIndex.

    The partition's output is unchanged, plus one extra item (STATS_KEY, [stats]) saying which
    machine ran it, how many circles it held, how many it sent on, and how long it took.
    The value is a one-element list so that reduceByKey(add) gathers all partitions' stats.
    sent_circles(item) lists the circles one output item sends to the central machine.
    """
    def run(pid, iterator):
        start = time.time()
        host, ip = machine_identity()
        held = list(iterator)
        output = list(mapper(iter(held)))
        sent = [c for item in output for c in sent_circles(item)]
        stats = {
            "partition": pid,
            "host": host,
            "ip": ip,
            "held": len(held),
            "sent": len(sent),
            "sent_circles": list(dict.fromkeys(sent)),   # distinct, in order
            "sent_distinct": len(set(sent)),
            "ms": round((time.time() - start) * 1000, 1)
        }
        return output + [(STATS_KEY, [stats])]
    return run


def split_partition_stats(items: list) -> Tuple[list, List[dict]]:
    """Separate the stats items added by with_partition_stats from a collected output."""
    rest, stats = [], []
    for item in items:
        if isinstance(item, tuple) and len(item) == 2 and item[0] == STATS_KEY:
            stats.extend(item[1])
        else:
            rest.append(item)
    return rest, stats


def circle_payload(circle: Circle, **extra) -> dict:
    payload = {"cx": circle[0], "cy": circle[1], "r": circle[2]}
    payload.update(extra)
    return payload


class UIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.endpoint = f"{self.base_url}/update"
        print(f"UI Client initialized. sending updates to {self.endpoint}")

    def send(self, event_type: str, payload: dict):
        try:
            import urllib.request
            import json
            
            data = payload.copy()
            data['type'] = event_type
            
            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                self.endpoint,
                data=json_data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                pass
        except Exception as e:
            print(f"Failed to send UI update: {e}")

    def send_status(self, message: str, total_guesses: Optional[int] = None):
        payload = {"message": message}
        if total_guesses is not None:
            payload["total_guesses"] = total_guesses
        self.send("STATUS", payload)

    def send_init(self, points: List[Point], bounds: Tuple[float, float, float, float], 
                  n_points: int, n_circles: int, k: int, epsilon: float,
                  total_points: Optional[int] = None, total_guesses: Optional[int] = None,
                  algorithm: str = "greedy"):
        """
        Send initialization data to UI.
        
        Args:
            points: Points to display (may be sampled)
            bounds: Bounding box
            n_points: Number of points being displayed
            n_circles: Total number of candidate circles
            k: Max circles to select
            epsilon: Epsilon parameter
            total_points: Total points in full dataset (if sampled, otherwise None)
            algorithm: "greedy" (main.py) or "theorem8" (alg.py); picks the UI's pseudocode
        """
        payload = {
            "points": points,
            "config": {
                "n_points": n_points,
                "n_circles": n_circles,
                "k": k,
                "epsilon": epsilon,
                "algorithm": algorithm
            },
            "bounds": {
                "minX": bounds[0],
                "minY": bounds[1],
                "maxX": bounds[2],
                "maxY": bounds[3]
            },
            "total_guesses": total_guesses
        }
        
        # Add sampling metadata if points were sampled
        if total_points and total_points > len(points):
            payload["sampling"] = {
                "is_sampled": True,
                "displayed": len(points),
                "total": total_points,
                "percentage": round(100 * len(points) / total_points, 1)
            }
        
        self.send("INIT", payload)

    def send_start_guess(self, j: int, threshold: float):
        self.send("START_GUESS", {"value": j, "threshold": threshold})

    def send_round(self, kind: str, partitions: List[dict], **details):
        """One Spark job finished: report what every partition (and its Pi) did."""
        payload = {"kind": kind, "partitions": partitions}
        payload.update(details)
        self.send("ROUND", payload)

    def send_partition_round(self, kind: str, stats: List[dict], **details) -> dict:
        """
        Send a ROUND for stats gathered by with_partition_stats. The circles each partition sent
        to the central machine go along once, tagged with the machine that sent them.
        Returns {circle: (host, ip)} for those circles.
        """
        origin = {}
        partitions = []
        for p in stats:
            p = dict(p)
            for c in p.pop("sent_circles", []):
                origin.setdefault(c, (p["host"], p["ip"]))
            partitions.append(p)
        sent = [circle_payload(c, host=host, ip=ip) for c, (host, ip) in origin.items()]
        self.send_round(kind, partitions, sent_circles=sent, **details)
        return origin

    def send_circle_added(self, circle: Circle, gain: int, threshold: float, coverage: int, step: int,
                          partition: Optional[int] = None, host: Optional[str] = None):
        self.send("CIRCLE_ADDED", {
            "circle": {"cx": circle[0], "cy": circle[1], "r": circle[2]},
            "gain": gain,
            "threshold": threshold,
            "coverage": coverage,
            "step": step,
            "partition": partition,
            "host": host
        })

    def send_final_solution(self, circles: List[Circle], coverage: int, best_j: Optional[int], total_points: int,
                            **details):
        """Send the final best solution to display in UI."""
        payload = {
            "circles": [{"cx": c[0], "cy": c[1], "r": c[2]} for c in circles],
            "coverage": coverage,
            "best_guess": best_j,
            "total_points": total_points,
            "coverage_percentage": round(100 * coverage / total_points, 1) if total_points > 0 else 0
        }
        payload.update(details)
        self.send("FINAL_SOLUTION", payload)

    def send_finished(self):
        self.send("FINISHED", {})
