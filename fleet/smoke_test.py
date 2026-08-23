"""Smoke test: submit four independent models and verify their artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pool import BlenderFleet, DEFAULT_BLENDER, DEFAULT_ROOT


def main() -> int:
    fleet = BlenderFleet(
        root=os.environ.get("BLENDER_FLEET_ROOT", str(DEFAULT_ROOT)),
        blender=os.environ.get("BLENDER_EXE", DEFAULT_BLENDER),
        max_parallel=int(os.environ.get("BLENDER_FLEET_PARALLEL", "2")),
        timeout_seconds=int(os.environ.get("BLENDER_FLEET_TIMEOUT", "300")),
    )
    requests = [
        {"name": "smoke-cube", "kind": "cube", "color": [0.1, 0.45, 0.95]},
        {"name": "smoke-robot", "kind": "robot", "color": [0.9, 0.2, 0.08]},
        {"name": "smoke-tower", "kind": "tower", "color": [0.18, 0.75, 0.35]},
        {"name": "smoke-monkey", "kind": "monkey", "color": [0.75, 0.35, 0.9]},
    ]
    try:
        submitted = [fleet.submit(item) for item in requests]
        results = [fleet.wait(item["job_id"], timeout=360) for item in submitted]
        summary = []
        for result in results:
            blend_value = result.get("blend_file")
            preview_value = result.get("preview_file")
            blend_file = Path(blend_value) if blend_value else Path("__missing_blend_file__")
            preview_file = Path(preview_value) if preview_value else Path("__missing_preview_file__")
            summary.append({
                "job_id": result.get("job_id"),
                "state": result.get("state"),
                "duration_seconds": result.get("duration_seconds"),
                "blend_exists": blend_file.exists(),
                "preview_exists": preview_file.exists(),
                "blend_file": str(blend_file),
                "preview_file": str(preview_file),
            })
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if all(item["state"] == "succeeded" and item["blend_exists"] and item["preview_exists"] for item in summary) else 1
    finally:
        fleet.close()


if __name__ == "__main__":
    raise SystemExit(main())
