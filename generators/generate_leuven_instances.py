"""Generate the ten Leuven corridor instances from the supplied input files.

The instances are written to generated/Leuven/ unless --output-dir is given.
"""

import argparse
import json
import math
import random
from pathlib import Path

from leuven_request_pool import build_leuven_pool, load_json

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = PACKAGE_ROOT / "inputs" / "Leuven"
REQUEST_POOL_PATH = INPUT_ROOT / "reqreate_request_pool.json"
TRAVEL_TIME_MATRIX_PATH = INPUT_ROOT / "travel_time_matrix_seconds.json"
REQREATE_CONFIG_PATH = INPUT_ROOT / "reqreate_configuration.json"
DEFAULT_OUTPUT_DIR = PACKAGE_ROOT / "generated" / "Leuven"

# ─────────────────────────────────────────────────────────────
# Per-instance specifications
# ─────────────────────────────────────────────────────────────
INSTANCE_SPECS = [
    # (name,                        n_veh, pre,  dyn,  seed, tw)
    ("final_update_instance_01",    4,     50,   50,   42,   5),
    ("final_update_instance_02",    5,     50,   50,   42,   5),
    ("final_update_instance_03",    4,     50,   50,   42,  10),  # TW widened
    ("final_update_instance_04",    4,     50,   50,   42,   3),  # TW narrowed
    ("final_update_instance_05",    3,     50,   50,   42,   5),
    ("final_update_instance_06",    4,     30,   70,   42,   5),
    ("final_update_instance_07",    4,     70,   30,   42,   5),
    ("final_update_instance_08",    4,     100,  100,  42,   5),
    ("final_update_instance_09",    4,     50,   50,    9,   5),
    ("final_update_instance_10",    4,     50,   50,   10,   5),
]

# ─────────────────────────────────────────────────────────────
# Shared model parameters
# ─────────────────────────────────────────────────────────────
TIME_START          = 360   # 06:00
TIME_END            = 540   # 09:00
VEHICLE_CAPACITY    = 20
DWELL_TIME          = 1
TRIPS               = [1, 2]
REJECTION_PENALTY   = 1000

# ─────────────────────────────────────────────────────────────
# Network
# ─────────────────────────────────────────────────────────────
def estimate_travel_time_fallback(u_idx, v_idx, sorted_places):
    """Straight-line travel time in minutes (25 km/h with a 1.4 detour factor)."""
    p1, p2 = sorted_places[u_idx-1], sorted_places[v_idx-1]
    lat_diff = (p1['lat'] - p2['lat']) * 111.0
    lon_diff = (p1['lon'] - p2['lon']) * 70.0
    dist_km  = math.sqrt(lat_diff**2 + lon_diff**2)
    return (dist_km / 25.0) * 60.0 * 1.4

def get_travel_time_int(u_sorted, v_sorted, matrix, sorted_places):
    """Whole-minute travel time between physical stops (1-based), rounded down.

    A source time above five minutes and above three times the straight-line
    estimate is treated as a routing artefact and replaced by the estimate.
    No entry of the supplied matrix meets this condition.
    """
    source_min = float(matrix[u_sorted-1][v_sorted-1]) / 60.0
    est_min    = estimate_travel_time_fallback(u_sorted, v_sorted, sorted_places)
    if source_min > (est_min * 3.0) and source_min > 5.0:
        source_min = est_min
    return int(math.floor(source_min))

def build_network(sorted_places, matrix):
    """Map the physical stops to the outbound and return logical stops."""
    N  = len(sorted_places)
    N2 = N * 2

    # Logical stops 1..N run outbound over physical stops 1..N; logical
    # stops N+1..2N return over physical stops N..1.
    log_to_phy = {}
    for i in range(1, N+1):
        log_to_phy[i] = i
    for i in range(1, N+1):
        log_to_phy[N+i] = N - i + 1

    mandatory_phy_ids = [i+1 for i, p in enumerate(sorted_places) if p.get('class') == 'mandatory']
    if not mandatory_phy_ids:
        raise ValueError("the REQreate configuration marks no stop as mandatory")

    # Kept as a set and listed in set order, as in the study files; the order
    # of network.mandatory_stops carries no meaning.
    mandatory_logical = set()
    for m in mandatory_phy_ids:
        mandatory_logical.add(m)
        mandatory_logical.add(2*N - m + 1)

    travel_times = {}
    for i in range(1, N2+1):
        for j in range(1, N2+1):
            if i != j:
                travel_times[f"{i},{j}"] = get_travel_time_int(
                    log_to_phy[i], log_to_phy[j], matrix, sorted_places)

    # The return direction is offset slightly so both directions stay visible.
    coordinates = {}
    for i in range(1, N2+1):
        p = sorted_places[log_to_phy[i]-1]
        x, y = p['lon'], p['lat']
        if i > N:
            x += 0.0001
            y += 0.0001
        coordinates[str(i)] = [x, y]

    return {
        "stops":           list(range(1, N2+1)),
        "coordinates":     coordinates,
        "mandatory_stops": list(mandatory_logical),
        "optional_stops":  [i for i in range(1, N2+1) if i not in mandatory_logical],
        "terminals":       [1, N2],
        "city_center":     [N, N+1],
        "dwell_times":     {str(i): DWELL_TIME for i in range(1, N2+1)},
        "travel_times":    travel_times
    }

# ─────────────────────────────────────────────────────────────
# Requests
# ─────────────────────────────────────────────────────────────
def sample_requests(valid_pre, valid_dyn, n_pre, n_dyn, seed, pw):
    """Draw the requests of one instance and number them by request time."""
    if n_pre > len(valid_pre) or n_dyn > len(valid_dyn):
        raise ValueError(
            f"requested {n_pre} pre-booked and {n_dyn} dynamic requests, but only "
            f"{len(valid_pre)} and {len(valid_dyn)} feasible candidates exist")

    rng = random.Random(seed)
    selected = rng.sample(valid_pre, n_pre) + rng.sample(valid_dyn, n_dyn)
    selected.sort(key=lambda r: r['sort_time'])

    requests = {"prebooked": {}, "dynamic": {}}
    for idx, r in enumerate(selected):
        kind = r['type']
        requests[kind][idx] = {
            "id": idx,
            "type": kind,
            "origin": r['origin'],
            "destination": r['destination'],
            "desired_time": r['desired_time'],
            "time_window": [
                r['desired_time'] - pw[f"early_allowance_{kind}"],
                r['desired_time'] + pw[f"late_allowance_{kind}"]
            ],
            "request_time": r['request_time']
        }
    return requests

def validate_instance(instance, n_pre, n_dyn):
    network = instance["network"]
    N2 = len(network["stops"])
    N = network["city_center"][0]
    if not {1, N, N+1, N2}.issubset(network["mandatory_stops"]):
        raise AssertionError("terminals and city centre must be mandatory")
    requests = instance["requests"]
    if len(requests["prebooked"]) != n_pre or len(requests["dynamic"]) != n_dyn:
        raise AssertionError("wrong number of requests")
    for kind in ("prebooked", "dynamic"):
        for r in requests[kind].values():
            if r["type"] != kind:
                raise AssertionError(f"request {r['id']} has the wrong type")
            if not 1 <= r["origin"] < r["destination"] <= N2:
                raise AssertionError(f"request {r['id']} has an invalid origin-destination pair")
            if not TIME_START <= r["desired_time"] <= TIME_END:
                raise AssertionError(f"request {r['id']} is outside the operating period")
            if not r["time_window"][0] <= r["desired_time"] <= r["time_window"][1]:
                raise AssertionError(f"request {r['id']} has its desired time outside its window")
            if r["request_time"] > r["desired_time"]:
                raise AssertionError(f"request {r['id']} is revealed after its desired time")

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    gen_config = load_json(REQREATE_CONFIG_PATH)
    matrix     = load_json(TRAVEL_TIME_MATRIX_PATH)
    raw_data   = load_json(REQUEST_POOL_PATH)

    network = build_network(gen_config["places"], matrix)
    operating_hours = {"start": TIME_START, "end": TIME_END}
    valid_pre, valid_dyn = build_leuven_pool(
        {"network": network, "parameters": {"operating_hours": operating_hours}}, raw_data)
    print(f"Feasible REQreate candidates: {len(valid_pre)} pre-booked, {len(valid_dyn)} dynamic")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for (name, n_veh, n_pre, n_dyn, seed, tw) in INSTANCE_SPECS:
        pw = {"early_allowance_prebooked": tw, "late_allowance_prebooked": tw,
              "early_allowance_dynamic":   tw, "late_allowance_dynamic":   tw}
        instance = {
            "config": {
                "window_start": TIME_START,
                "window_end":   TIME_END,
                "n_vehicles":   n_veh,
                "vehicle_capacity": VEHICLE_CAPACITY
            },
            "network": network,
            "fleet": {
                "vehicles": list(range(1, n_veh+1)),
                "trips":    TRIPS,
                "capacity": VEHICLE_CAPACITY
            },
            "requests": sample_requests(valid_pre, valid_dyn, n_pre, n_dyn, seed, pw),
            "parameters": {
                "operating_hours": operating_hours,
                "promise_window":   pw,
                "rejection_penalty": REJECTION_PENALTY,
                # Settings of the study's experiment runner, kept so that the
                # files match the study files; they are not model input.
                "visualize": False,
                "output_path": "results/MM2/"
            }
        }
        validate_instance(instance, n_pre, n_dyn)

        out_path = args.output_dir / f"{name}.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(instance, f, indent=2)
        print(out_path)

if __name__ == "__main__":
    main()
