"""Check that the regenerated instances match the packaged ones.

Run after the two generators. Files are compared by JSON content, so line
endings, which follow the operating system, do not matter; floating-point
values (the synthetic coordinates) are compared to within 1e-6. The exit
status is 0 when every packaged instance has been reproduced.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("Leuven", "Random")
FLOAT_TOLERANCE = 1e-6


def first_difference(expected, actual, path: str = "") -> str | None:
    """Describe the first difference between two JSON values, or return None."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if list(expected) != list(actual):
            missing = [key for key in expected if key not in actual]
            extra = [key for key in actual if key not in expected]
            if not missing and not extra:
                return f"{path or '/'}: keys appear in a different order"
            return f"{path or '/'}: keys differ (missing {missing[:5]}, extra {extra[:5]})"
        for key in expected:
            difference = first_difference(expected[key], actual[key], f"{path}/{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}: {len(expected)} items expected, {len(actual)} found"
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if type(expected) is float and type(actual) is float:
        if math.isclose(expected, actual, rel_tol=0.0, abs_tol=FLOAT_TOLERANCE):
            return None
    elif type(expected) is type(actual) and expected == actual:
        return None
    return f"{path}: expected {expected!r}, found {actual!r}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generated-dir", type=Path, default=PACKAGE_ROOT / "generated",
        help="folder that holds the Leuven/ and Random/ output folders",
    )
    args = parser.parse_args()

    problems = 0
    checked = 0
    for family in FAMILIES:
        for packaged in sorted((PACKAGE_ROOT / "instances" / family).glob("*.json")):
            checked += 1
            generated = args.generated_dir / family / packaged.name
            label = f"{family}/{packaged.name}"
            if not generated.exists():
                print(f"MISSING    {label}: run the {family} generator first")
                problems += 1
                continue
            if generated.read_bytes() == packaged.read_bytes():
                print(f"identical  {label}")
                continue
            difference = first_difference(
                json.loads(packaged.read_text(encoding="utf-8")),
                json.loads(generated.read_text(encoding="utf-8")),
            )
            if difference is None:
                print(f"same data  {label} (formatting or line endings differ)")
            else:
                print(f"DIFFERENT  {label}: {difference}")
                problems += 1

    if problems:
        print(f"\n{problems} of {checked} instances were not reproduced.")
        sys.exit(1)
    print(f"\nAll {checked} packaged instances were reproduced.")


if __name__ == "__main__":
    main()
