"""Generate the ten Random corridor instances from Leuven-derived patterns.

The profile inputs fix stop counts, supply, operating periods, request counts,
and time-window widths. Five seeded corridor networks are generated; each is
shared by a narrow/wide time-window pair. Requests are sampled from a
normalized Leuven REQreate pool and mapped to the synthetic corridors.
The instances are written to generated/Random/ unless --output-dir is given.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import re
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

from leuven_request_pool import build_leuven_pool, load_json


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = PACKAGE_ROOT / "inputs" / "Random_profiles"
# The Leuven network and operating hours are read from the packaged instance.
LEUVEN_TEMPLATE = PACKAGE_ROOT / "instances" / "Leuven" / "final_update_instance_01.json"
REQUEST_POOL = PACKAGE_ROOT / "inputs" / "Leuven" / "reqreate_request_pool.json"
NETWORK_SEEDS = {index: 7200 + index for index in range(1, 6)}


def write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def number_from_name(name: str) -> int:
    match = re.search(r"rand-(\d+)", name)
    if not match:
        raise ValueError(f"cannot parse Random instance number: {name}")
    return int(match.group(1))


def network_pair_number(name: str) -> int:
    number = number_from_name(name)
    return number if number <= 5 else number - 5


def int_tt(network: Mapping[str, object], left: int, right: int) -> float:
    key = f"{left},{right}"
    try:
        return float(network["travel_times"][key])  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"missing adjacent travel time {key}") from exc


def adjacent_times(network: Mapping[str, object]) -> List[float]:
    stops = [int(value) for value in network["stops"]]  # type: ignore[index]
    return [int_tt(network, left, left + 1) for left in stops[:-1]]


def haversine_like_km(first: Sequence[float], second: Sequence[float]) -> float:
    """Use a local planar approximation for the short Leuven corridor."""
    lon1, lat1 = float(first[0]), float(first[1])
    lon2, lat2 = float(second[0]), float(second[1])
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    east = (lon2 - lon1) * 111.32 * math.cos(mean_lat)
    north = (lat2 - lat1) * 111.32
    return math.hypot(east, north)


def reference_data() -> dict:
    if not LEUVEN_TEMPLATE.exists():
        raise FileNotFoundError(f"missing Leuven template: {LEUVEN_TEMPLATE}")
    if not REQUEST_POOL.exists():
        raise FileNotFoundError(f"missing Leuven request pool: {REQUEST_POOL}")
    template = load_json(LEUVEN_TEMPLATE)
    pool = build_leuven_pool(template, load_json(REQUEST_POOL))
    return {"template": template, "pool": pool}


def normalized_request_pool(template: dict, pool: Tuple[List[dict], List[dict]]) -> Dict[str, List[dict]]:
    """Convert Leuven logical requests to side-relative coordinates.

    The normalized representation lets a target corridor have 15, 20, 25,
    or 30 stops per side without copying Leuven's station numbering.
    """
    n = int(template["network"]["city_center"][0])
    start = float(template["parameters"]["operating_hours"]["start"])
    end = float(template["parameters"]["operating_hours"]["end"])
    horizon = end - start
    result: Dict[str, List[dict]] = {"prebooked": [], "dynamic": []}
    for request_type, records in zip(("prebooked", "dynamic"), pool):
        for record in records:
            origin = int(record["origin"])
            destination = int(record["destination"])
            if destination <= n:
                side = "left"
                origin_fraction = (origin - 1) / float(n - 1)
                destination_fraction = (destination - 1) / float(n - 1)
            elif origin >= n + 1:
                side = "right"
                origin_fraction = (origin - (n + 1)) / float(n - 1)
                destination_fraction = (destination - (n + 1)) / float(n - 1)
            else:
                # The established Leuven pool contains no cross-centre
                # requests; skip one defensively if the source changes.
                continue
            result[request_type].append(
                {
                    "side": side,
                    "origin_fraction": max(0.0, min(1.0, origin_fraction)),
                    "destination_fraction": max(0.0, min(1.0, destination_fraction)),
                    "desired_fraction": max(
                        0.0,
                        min(1.0, (float(record["desired_time"]) - start) / horizon),
                    ),
                }
            )
    for request_type in result:
        if not result[request_type]:
            raise ValueError(f"empty normalized Leuven pool: {request_type}")
    return result


def cumulative(values: Sequence[float]) -> List[float]:
    result = [0.0]
    for value in values:
        result.append(result[-1] + float(value))
    return result


def piecewise_integral(values: Sequence[float], start: float, end: float) -> float:
    """Integrate a piecewise-constant sequence over [0, 1]."""
    if not 0.0 <= start <= end <= 1.0:
        raise ValueError("piecewise interval outside [0, 1]")
    width = 1.0 / len(values)
    total = 0.0
    first = min(len(values) - 1, int(start * len(values)))
    last = min(len(values) - 1, int(math.ceil(end * len(values))))
    for index in range(first, last + 1):
        segment_start = index * width
        segment_end = (index + 1) * width
        overlap = max(0.0, min(end, segment_end) - max(start, segment_start))
        total += float(values[index]) * overlap / width
    return total


def resample_profile(
    reference: Sequence[float], count: int, rng: random.Random, jitter: float
) -> List[float]:
    """Resample Leuven's normalized segment profile at a new stop count."""
    if count < 1:
        raise ValueError("resampling requires at least one segment")
    raw = []
    for index in range(count):
        start = index / float(count)
        end = (index + 1) / float(count)
        value = piecewise_integral(reference, start, end)
        value *= rng.uniform(1.0 - jitter, 1.0 + jitter)
        raw.append(max(value, 1e-9))
    total = sum(raw)
    return [value / total for value in raw]


def allocate_integer(total: int, weights: Sequence[float]) -> List[int]:
    """Allocate an integer total while keeping every ordinary segment positive."""
    count = len(weights)
    total = max(int(total), count)
    remaining = total - count
    scaled = [remaining * float(weight) for weight in weights]
    values = [1 + int(math.floor(value)) for value in scaled]
    missing = total - sum(values)
    order = sorted(
        range(count), key=lambda index: scaled[index] - math.floor(scaled[index]), reverse=True
    )
    for index in order[:missing]:
        values[index] += 1
    return values


def choose_mandatory_positions(
    n: int,
    count: int,
    rng: random.Random,
    reference_positions: Sequence[int],
    reference_n: int,
) -> List[int]:
    """Place ``count`` mandatory stops on one side of an n-stop corridor.

    When ``count`` does not exceed the number of Leuven reference positions,
    the targets are Leuven's relative positions (subsampled if fewer are
    needed); otherwise they are evenly spaced. Each target is mapped to the
    nearest free position; the first and last stops are always mandatory.
    """
    if count < 2 or count > n:
        raise ValueError(f"invalid mandatory count {count} for n={n}")
    reference = [(value - 1) / float(reference_n - 1) for value in reference_positions]
    if count <= len(reference):
        targets = [reference[round(i * (len(reference) - 1) / (count - 1))] for i in range(count)]
    else:
        targets = [i / float(count - 1) for i in range(count)]

    chosen = {1, n}
    interior_targets = targets[1:-1]
    for target in interior_targets:
        candidates = [
            position
            for position in range(2, n)
            if position not in chosen
        ]
        if not candidates:
            break
        desired = 1.0 + target * (n - 1)
        rng.shuffle(candidates)
        selected = min(candidates, key=lambda position: abs(position - desired))
        chosen.add(selected)

    # Fill any rounding collisions with positions nearest the remaining
    # Leuven-like quantiles.  The count is fixed to the source profile.
    if len(chosen) < count:
        candidates = [position for position in range(2, n) if position not in chosen]
        candidates.sort(key=lambda position: min(abs(position - (1 + target * (n - 1))) for target in targets))
        chosen.update(candidates[: count - len(chosen)])
    if len(chosen) != count:
        raise AssertionError("mandatory-stop mapping changed the requested count")
    return sorted(chosen)


def coordinate_path(
    n: int,
    left_weights: Sequence[float],
    right_weights: Sequence[float],
    rng: random.Random,
) -> Dict[str, List[float]]:
    """Create auditable synthetic coordinates along a gently curved corridor."""
    center_lon = 4.70 + rng.uniform(-0.04, 0.04)
    center_lat = 50.90 + rng.uniform(-0.04, 0.04)
    angle = rng.uniform(0.0, 2.0 * math.pi)
    direction = (math.cos(angle), math.sin(angle))
    perpendicular = (-direction[1], direction[0])
    total_km = rng.uniform(0.92, 1.08) * 11.03
    curvature_left = rng.uniform(-0.45, 0.45)
    curvature_right = rng.uniform(-0.45, 0.45)
    coordinates: Dict[str, List[float]] = {}

    def to_lon_lat(x_km: float, y_km: float) -> List[float]:
        lon = center_lon + x_km / (111.32 * math.cos(math.radians(center_lat)))
        lat = center_lat + y_km / 111.32
        return [round(lon, 7), round(lat, 7)]

    def local_point(frac: float, side: str) -> Tuple[float, float]:
        if side == "left":
            longitudinal = -(1.0 - frac) * total_km
            lateral = curvature_left * math.sin(math.pi * frac)
            return (
                longitudinal * direction[0] + lateral * perpendicular[0],
                longitudinal * direction[1] + lateral * perpendicular[1],
            )
        longitudinal = frac * total_km
        lateral = curvature_right * math.sin(math.pi * frac)
        return (
            longitudinal * direction[0] + lateral * perpendicular[0],
            longitudinal * direction[1] + lateral * perpendicular[1],
        )

    left_cum = cumulative(left_weights)
    right_cum = cumulative(right_weights)
    for local, frac in enumerate((value / left_cum[-1] for value in left_cum), 1):
        x, y = local_point(frac, "left")
        coordinates[str(local)] = to_lon_lat(x, y)
    for local, frac in enumerate((value / right_cum[-1] for value in right_cum), 1):
        x, y = local_point(frac, "right")
        # Keep the two center logical stops distinct, as in the Leuven data.
        if local == 1:
            x += perpendicular[0] * 0.01
            y += perpendicular[1] * 0.01
        coordinates[str(n + local)] = to_lon_lat(x, y)
    return coordinates


def build_network(template: dict, reference_template: dict, network_seed: int) -> dict:
    cfg = template["config"]
    old_network = template["network"]
    n = int(cfg["n_stops"])
    total = 2 * n
    rng = random.Random(network_seed)

    ref_network = reference_template["network"]
    ref_n = int(ref_network["city_center"][0])
    ref_tt = [max(1.0, float(ref_network["travel_times"][f"{i},{i + 1}"])) for i in range(1, ref_n)]
    ref_coords = ref_network["coordinates"]
    ref_geom = [
        max(1e-6, haversine_like_km(ref_coords[str(i)], ref_coords[str(i + 1)]))
        for i in range(1, ref_n)
    ]

    left_profile = resample_profile(ref_tt, n - 1, rng, jitter=0.14)
    right_profile = resample_profile(ref_tt, n - 1, rng, jitter=0.14)
    left_geom = resample_profile(ref_geom, n - 1, rng, jitter=0.12)
    right_geom = resample_profile(ref_geom, n - 1, rng, jitter=0.12)

    old_adj = adjacent_times(old_network)
    old_left_total = max(1, int(round(sum(old_adj[: n - 1]) * rng.uniform(0.96, 1.04))))
    old_right_total = max(1, int(round(sum(old_adj[n:]) * rng.uniform(0.96, 1.04))))
    left_times = allocate_integer(old_left_total, left_profile)
    right_times = allocate_integer(old_right_total, right_profile)

    # Leuven's outbound mandatory stops, e.g. 1, 8, 12, 13, 14, 17, 21, 24, 25 of 25.
    reference_mandatory = sorted(
        value for value in map(int, ref_network["mandatory_stops"]) if value <= ref_n
    )
    old_mandatory = {int(value) for value in old_network["mandatory_stops"]}
    left_count = sum(value <= int(old_network["city_center"][0]) for value in old_mandatory)
    right_count = sum(value >= int(old_network["city_center"][1]) for value in old_mandatory)
    # Both sides use the same positions counted from their first stop; the
    # right side is not mirrored as Leuven's return direction is.
    left_mandatory = choose_mandatory_positions(n, left_count, rng, reference_mandatory, ref_n)
    right_local_mandatory = choose_mandatory_positions(
        n, right_count, rng, reference_mandatory, ref_n
    )
    mandatory = set(left_mandatory)
    mandatory.update(n + value for value in right_local_mandatory)
    stops = list(range(1, total + 1))

    adjacent: Dict[Tuple[int, int], int] = {}
    for left in range(1, total):
        if left < n:
            adjacent[left, left + 1] = left_times[left - 1]
        elif left == n:
            adjacent[left, left + 1] = 0
        else:
            adjacent[left, left + 1] = right_times[left - n - 1]

    travel_times: Dict[str, int] = {}
    for left in range(1, total):
        for right in range(left + 1, total + 1):
            if right == left + 1:
                value = adjacent[left, right]
            else:
                path_time = sum(adjacent[index, index + 1] for index in range(left, right))
                discount = rng.uniform(0.0, float(cfg.get("nonadj_discount", 0.3)))
                value = max(1, int(round(path_time * (1.0 - discount))))
            travel_times[f"{left},{right}"] = value

    coordinates = coordinate_path(n, left_geom, right_geom, rng)
    dwell_default = float(cfg.get("dwell", 1.0))
    dwell_times = {
        str(stop): float(old_network.get("dwell_times", {}).get(str(stop), dwell_default))
        for stop in stops
    }
    return {
        "stops": stops,
        "coordinates": coordinates,
        "mandatory_stops": sorted(mandatory),
        "optional_stops": sorted(set(stops) - mandatory),
        "travel_times": travel_times,
        "dwell_times": dwell_times,
        "terminals": [1, total],
        "city_center": [n, n + 1],
    }


def route_prefix(network: dict) -> Tuple[Dict[int, float], Dict[int, float]]:
    stops = [int(value) for value in network["stops"]]
    mandatory = {int(value) for value in network["mandatory_stops"]}
    prefix: Dict[int, float] = {stops[0]: 0.0}
    for left in stops[:-1]:
        prefix[left + 1] = prefix[left] + float(network["travel_times"][f"{left},{left + 1}"])
        if left in mandatory:
            prefix[left + 1] += float(network["dwell_times"][str(left)])
    remaining = {stop: prefix[stops[-1]] - prefix[stop] for stop in stops}
    return prefix, remaining


def map_fraction(value: float, n: int, rng: random.Random) -> int:
    jitter = rng.uniform(-0.025, 0.025)
    return int(round(1.0 + max(0.0, min(1.0, value + jitter)) * (n - 1)))


def generate_requests(template: dict, network: dict, request_seed: int, pool: Dict[str, List[dict]]) -> dict:
    cfg = template["config"]
    n = int(cfg["n_stops"])
    start = int(cfg["window_start"])
    end = int(cfg["window_end"])
    horizon = end - start
    half_width = int(cfg["pb_half_width"])
    prefix, remaining = route_prefix(network)
    rng = random.Random(request_seed)

    def sample_one(request_type: str) -> dict:
        for _ in range(2000):
            source = rng.choice(pool[request_type])
            origin_local = map_fraction(source["origin_fraction"], n, rng)
            destination_local = map_fraction(source["destination_fraction"], n, rng)
            if destination_local <= origin_local:
                destination_local = min(n, origin_local + 1)
            if destination_local <= origin_local:
                continue
            if source["side"] == "left":
                origin = origin_local
                destination = destination_local
            else:
                origin = n + origin_local
                destination = n + destination_local
            earliest = max(
                start,
                start + prefix[origin] - prefix[1] + float(cfg["buffer_start"]),
            )
            latest = min(
                end,
                end - (prefix[destination] - prefix[origin]) - float(cfg["buffer_end"]),
                end - remaining[origin] - float(cfg["buffer_terminal"]),
            )
            lower = int(math.ceil(earliest))
            upper = int(math.floor(latest))
            if lower > upper:
                continue
            target = start + source["desired_fraction"] * horizon
            target += rng.gauss(0.0, max(1.0, 0.03 * horizon))
            desired = int(round(max(lower, min(upper, target))))
            window = [max(start, desired - half_width), min(end, desired + half_width)]
            if request_type == "prebooked":
                advance_days = rng.randint(
                    int(cfg["pb_advance_min_days"]), int(cfg["pb_advance_max_days"])
                )
                request_time = start - advance_days * 1440
            else:
                earliest_reveal = max(start, desired - int(cfg["max_dyn_lead"]))
                latest_reveal = desired - int(cfg["dyn_time_threshold"])
                if earliest_reveal > latest_reveal:
                    continue
                request_time = rng.randint(earliest_reveal, latest_reveal)
            return {
                "origin": origin,
                "destination": destination,
                "desired_time": desired,
                "time_window": window,
                "request_time": request_time,
            }
        raise RuntimeError(f"could not generate a feasible {request_type} request")

    result = {"prebooked": {}, "dynamic": {}}
    request_id = 1
    for _ in range(int(cfg["n_prebooked"])):
        item = sample_one("prebooked")
        item.update({"id": request_id, "type": "prebooked"})
        result["prebooked"][request_id] = item
        request_id += 1
    for _ in range(int(cfg["n_dynamic"])):
        item = sample_one("dynamic")
        item.update({"id": request_id, "type": "dynamic"})
        result["dynamic"][request_id] = item
        request_id += 1
    return result


def make_instance(
    template: dict,
    network: dict,
    request_seed: int,
    pool: Dict[str, List[dict]],
    network_seed: int,
    pair_number: int,
) -> dict:
    result = copy.deepcopy(template)
    # The profile's random_seed is 42, the default request seed; keep the
    # field equal to the seed actually used.
    result["config"]["random_seed"] = request_seed
    result["network"] = copy.deepcopy(network)
    result["requests"] = generate_requests(template, network, request_seed, pool)
    result["generation"] = {
        "family": "Random",
        "method": "Leuven-informed synthetic corridor and demand sampling",
        "network_seed": network_seed,
        "request_seed": request_seed,
        "paired_network_group": f"network_{pair_number:02d}",
        "demand_profile_source": "Leuven REQreate request pool",
    }
    return result


def profile_signature(instance: dict) -> dict:
    cfg = instance["config"]
    return {
        "n_stops": cfg["n_stops"],
        "n_prebooked": cfg["n_prebooked"],
        "n_dynamic": cfg["n_dynamic"],
        "n_vehicles": cfg["n_vehicles"],
        "n_trips_per_vehicle": cfg["n_trips_per_vehicle"],
        "window_start": cfg["window_start"],
        "window_end": cfg["window_end"],
        "pb_half_width": cfg["pb_half_width"],
        "fleet": instance["fleet"],
        "parameters": instance["parameters"],
    }


def validate_instance(template: dict, instance: dict) -> None:
    if profile_signature(template) != profile_signature(instance):
        raise AssertionError("Random generator changed a protected profile/supply field")
    cfg = instance["config"]
    network = instance["network"]
    n = int(cfg["n_stops"])
    total = 2 * n
    stops = list(range(1, total + 1))
    if network["stops"] != stops:
        raise AssertionError("logical stop numbering changed")
    if network["terminals"] != [1, total] or network["city_center"] != [n, n + 1]:
        raise AssertionError("corridor anchors are invalid")
    mandatory = {int(value) for value in network["mandatory_stops"]}
    if not {1, total, n, n + 1}.issubset(mandatory):
        raise AssertionError("terminals and city centre must be mandatory")
    if len(mandatory) != len(template["network"]["mandatory_stops"]):
        raise AssertionError("mandatory-stop count changed")
    if set(map(int, network["optional_stops"])) != set(stops) - mandatory:
        raise AssertionError("optional-stop complement is invalid")
    expected_keys = {f"{left},{right}" for left in stops for right in stops if left < right}
    if set(network["travel_times"]) != expected_keys:
        raise AssertionError("travel-time matrix is not the expected upper triangle")
    for left in range(1, total):
        value = float(network["travel_times"][f"{left},{left + 1}"])
        if left == n:
            if value != 0.0:
                raise AssertionError("city-centre logical link must be zero")
        elif value < 1.0:
            raise AssertionError("ordinary adjacent travel times must be positive")
    prefix, _ = route_prefix(network)
    loop = prefix[total]
    # The empty mandatory-stop route must fit at least one complete trip.
    horizon = float(instance["parameters"]["operating_hours"]["end"] - instance["parameters"]["operating_hours"]["start"])
    if loop > horizon + 1e-9:
        raise AssertionError(f"full route {loop} exceeds operating horizon {horizon}")
    for request_type in ("prebooked", "dynamic"):
        requests = instance["requests"][request_type]
        if len(requests) != int(cfg["n_prebooked" if request_type == "prebooked" else "n_dynamic"]):
            raise AssertionError(f"wrong {request_type} count")
        for raw in requests.values():
            origin = int(raw["origin"])
            destination = int(raw["destination"])
            if not 1 <= origin < destination <= total:
                raise AssertionError("invalid request OD")
            if not raw["time_window"][0] <= raw["desired_time"] <= raw["time_window"][1]:
                raise AssertionError("desired time outside request window")
            if request_type == "dynamic" and raw["request_time"] > raw["desired_time"]:
                raise AssertionError("dynamic request is revealed after desired time")


def load_templates() -> List[Tuple[str, Path, dict]]:
    paths = sorted(PROFILE_ROOT.glob("*.json"))
    if len(paths) != 10:
        raise ValueError(f"expected 10 Random profile templates, found {len(paths)}")
    return [(path.stem, path, load_json(path)) for path in paths]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=PACKAGE_ROOT / "generated" / "Random"
    )
    parser.add_argument("--request-seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    templates = load_templates()
    reference = reference_data()
    pool = normalized_request_pool(reference["template"], reference["pool"])
    outputs = [args.output_dir / f"{name}.json" for name, _, _ in templates]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        parser.error(f"output already exists: {existing[0]}; use --force to replace")

    networks: Dict[int, dict] = {}
    for name, _, template in templates:
        pair = network_pair_number(name)
        if pair not in networks:
            networks[pair] = build_network(template, reference["template"], NETWORK_SEEDS[pair])
        instance = make_instance(
            template, networks[pair], args.request_seed, pool, NETWORK_SEEDS[pair], pair
        )
        validate_instance(template, instance)
        write_json(instance, args.output_dir / f"{name}.json")
        print(args.output_dir / f"{name}.json")


if __name__ == "__main__":
    main()
