---
name: blender-headless-fleet
description: Run independent Blender model jobs through isolated headless workers when several agents must build assets in parallel without file or process conflicts.
---

# Blender Headless Fleet

Use this skill when the user asks for multiple agents to create Blender assets at the same time.

## Core rules

- Give each agent one job ID, one Blender process, one project directory, and one output `.blend` file.
- Never let two agents write the same `.blend`, preview, cache, or temporary directory.
- Keep worker concurrency at or below available CPU/GPU/RAM. Start with 2 workers on one GPU and increase only after testing.
- Headless workers need the Blender executable, but they do not need a visible Blender window or the GUI MCP add-on. The dispatcher launches Blender with `--background`.

## Basic workflow

1. Submit one independent job per agent through the fleet dispatcher (`submit_model_job`). Use a unique name and a separate output target.
2. Record the returned `job_id`; do not route work by foreground window or shared port.
3. Poll or wait with `get_job_status` / `wait_for_job`.
4. Return the job's `scene.blend` and `preview.png` only after the result is `succeeded`.
5. If a job fails, inspect that job's `blender.log` and retry only that job.

For local testing, use `D:\blender-mcp-fleet\prototype\fleet\mcp_server.py` with the repo's `.venv`. Keep the existing GUI `blender` MCP entry unchanged unless the user explicitly asks to replace it.
