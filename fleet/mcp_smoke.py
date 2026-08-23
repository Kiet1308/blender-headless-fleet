"""Exercise the dispatcher through the MCP stdio protocol."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = Path(__file__).with_name("mcp_server.py")
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def text_payload(result) -> dict:
    for item in result.content:
        if getattr(item, "type", None) == "text":
            return json.loads(item.text)
    raise RuntimeError(f"MCP result did not contain JSON text: {result!r}")


async def main() -> int:
    params = StdioServerParameters(
        command=str(PYTHON),
        args=[str(SERVER)],
        env={**os.environ, "BLENDER_FLEET_PARALLEL": "2"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            requests = [
                {"name": "mcp-sphere", "kind": "sphere", "color": [0.2, 0.7, 0.95]},
                {"name": "mcp-monkey", "kind": "monkey", "color": [0.75, 0.35, 0.9]},
                {"name": "mcp-tower", "kind": "tower", "color": [0.18, 0.75, 0.35]},
            ]
            submitted = [text_payload(await session.call_tool("submit_model_job", request)) for request in requests]
            results = await asyncio.gather(*(
                session.call_tool("wait_for_job", {"job_id": item["job_id"], "timeout_seconds": 360})
                for item in submitted
            ))
            jobs = [text_payload(result) for result in results]
            print(json.dumps({"tool_names": names, "jobs": jobs}, indent=2, ensure_ascii=False))
            return 0 if all(job.get("state") == "succeeded" for job in jobs) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
