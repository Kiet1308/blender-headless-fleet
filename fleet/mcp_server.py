"""MCP facade for the Blender worker pool.

The MCP client sees one dispatcher.  The dispatcher fans jobs out to isolated
headless Blender workers, so multiple agents can submit independent models
without sharing a Blender socket or a .blend file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from pool import BlenderFleet, DEFAULT_BLENDER, DEFAULT_ROOT


ROOT = Path(os.environ.get("BLENDER_FLEET_ROOT", str(DEFAULT_ROOT))).resolve()
BLENDER = os.environ.get("BLENDER_EXE", DEFAULT_BLENDER)
MAX_PARALLEL = int(os.environ.get("BLENDER_FLEET_PARALLEL", "2"))
TIMEOUT = int(os.environ.get("BLENDER_FLEET_TIMEOUT", "300"))
fleet = BlenderFleet(ROOT, BLENDER, MAX_PARALLEL, TIMEOUT)
mcp = FastMCP("blender-fleet")


@mcp.tool()
def submit_model_job(name: str, kind: str = "cube", color: list[float] | None = None, resolution: int = 384) -> dict[str, Any]:
    """Queue an isolated model job. Supported kinds: cube, sphere, monkey, tower, robot."""
    return fleet.submit({"name": name, "kind": kind, "color": color or [0.15, 0.45, 0.95], "resolution": resolution})


@mcp.tool()
def get_job_status(job_id: str) -> dict[str, Any]:
    """Return the status/result for one job."""
    return fleet.status(job_id)


@mcp.tool()
def wait_for_job(job_id: str, timeout_seconds: int = 360) -> dict[str, Any]:
    """Wait for one queued job and return its result."""
    return fleet.wait(job_id, timeout=timeout_seconds)


@mcp.tool()
def list_model_jobs() -> list[dict[str, Any]]:
    """List all jobs in the fleet workspace."""
    return fleet.list_jobs()


@mcp.tool()
def fleet_info() -> dict[str, Any]:
    """Return the worker-pool configuration."""
    return {"root": str(ROOT), "blender": BLENDER, "max_parallel": MAX_PARALLEL, "timeout_seconds": TIMEOUT}


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        fleet.close()
