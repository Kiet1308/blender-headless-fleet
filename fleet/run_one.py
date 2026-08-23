"""Submit exactly one isolated fleet job from the command line."""

from __future__ import annotations

import argparse
import json

from pool import BlenderFleet, DEFAULT_BLENDER, DEFAULT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--kind", choices=["cube", "sphere", "monkey", "tower", "robot"], required=True)
    parser.add_argument("--color", nargs=3, type=float, default=[0.15, 0.45, 0.95])
    args = parser.parse_args()
    fleet = BlenderFleet(DEFAULT_ROOT, DEFAULT_BLENDER, max_parallel=1, timeout_seconds=300)
    try:
        submitted = fleet.submit({"name": args.name, "kind": args.kind, "color": args.color})
        result = fleet.wait(submitted["job_id"], timeout=360)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("state") == "succeeded" else 1
    finally:
        fleet.close()


if __name__ == "__main__":
    raise SystemExit(main())
