"""Map REQreate requests to the Leuven logical corridor.

Both generators use this module: the Leuven generator samples its requests
from the returned candidates, and the Random generator converts the same
candidates to corridor-relative positions.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# Minutes between the end of a trip that serves a request at its desired time
# and the end of the operating period.
TERMINAL_BUFFER = 5.0


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _travel_times(instance: dict) -> dict[tuple[int, int], float]:
    return {
        tuple(map(int, key.split(","))): float(value)
        for key, value in instance["network"]["travel_times"].items()
    }


def _nearest_physical_stop(lat: float, lon: float, coordinates: list[list[float]]) -> int:
    return min(
        range(1, len(coordinates) + 1),
        key=lambda index: (coordinates[index - 1][1] - lat) ** 2
        + (coordinates[index - 1][0] - lon) ** 2,
    )


def build_leuven_pool(template: dict, raw_data: dict) -> tuple[list[dict], list[dict]]:
    """Map the REQreate candidate pool to the Leuven logical corridor.

    ``template`` supplies the Leuven network and operating hours in the
    instance format. Each candidate is mapped to its nearest physical stops
    and to the logical direction in which the destination follows the origin.
    It is kept when a vehicle that starts at the first terminal at the start
    of the operating period can reach the origin by the desired time, and a
    vehicle that leaves the origin at the desired time can complete the trip
    ``TERMINAL_BUFFER`` minutes before the end. A dynamic candidate must also
    be revealed within the operating period and no later than its desired
    time. Returns the kept pre-booked and dynamic candidates in pool order.
    """
    network = template["network"]
    n = int(network["city_center"][0])
    n2 = len(network["stops"])
    coordinates = [network["coordinates"][str(i)] for i in range(1, n + 1)]
    mandatory = sorted(map(int, network["mandatory_stops"]))
    travel = _travel_times(template)
    dwell = {int(key): float(value) for key, value in network["dwell_times"].items()}
    start = int(template["parameters"]["operating_hours"]["start"])
    end = int(template["parameters"]["operating_hours"]["end"])

    arrival = {mandatory[0]: 0.0}
    elapsed = 0.0
    for left, right in zip(mandatory, mandatory[1:]):
        elapsed += travel[left, right] + dwell[left]
        arrival[right] = elapsed
    total_loop = elapsed

    previous = {}
    following = {}
    for stop in range(1, n2 + 1):
        previous[stop] = max((m for m in mandatory if m <= stop), default=mandatory[0])
        following[stop] = min((m for m in mandatory if m >= stop), default=mandatory[-1])

    valid_prebooked = []
    valid_dynamic = []
    for key, item in raw_data["requests"].items():
        try:
            origin_raw = item["origin"]
            destination_raw = item["destination"]
            origin_physical = _nearest_physical_stop(
                float(origin_raw[0]), float(origin_raw[1]), coordinates
            )
            destination_physical = _nearest_physical_stop(
                float(destination_raw[0]), float(destination_raw[1]), coordinates
            )
            desired = math.floor(float(item["earliest_departure"]) / 60.0)
            revealed = math.floor(float(item["time_stamp"]) / 60.0)
            sort_time = float(item["time_stamp"])
            is_prebooked = float(item["is_prebooked"]) >= 0.5
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed REQreate request {key!r}: {exc!r}") from exc

        if origin_physical == destination_physical:
            continue

        if origin_physical < destination_physical:
            origin = origin_physical
            destination = destination_physical
        else:
            origin = 2 * n - origin_physical + 1
            destination = 2 * n - destination_physical + 1

        if not is_prebooked and not (start <= revealed <= end and revealed <= desired):
            continue

        prev_stop = previous[origin]
        next_stop = following[origin]
        earliest = (
            start
            + arrival[prev_stop]
            + dwell[prev_stop]
            + travel.get((prev_stop, origin), 0.0)
        )
        latest = (
            end
            - travel.get((origin, next_stop), 0.0)
            - (total_loop - arrival[next_stop])
            - TERMINAL_BUFFER
        )
        if not earliest <= desired <= latest:
            continue

        record = {
            "type": "prebooked" if is_prebooked else "dynamic",
            "origin": origin,
            "destination": destination,
            "desired_time": desired,
            "request_time": revealed,
            "sort_time": sort_time,
        }
        (valid_prebooked if is_prebooked else valid_dynamic).append(record)

    return valid_prebooked, valid_dynamic
