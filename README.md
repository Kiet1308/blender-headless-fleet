# Blender MCP Fleet prototype

This prototype exposes one MCP dispatcher and fans independent model jobs out
to isolated, headless Blender processes. It is intended for multiple agents:
each agent submits a job, and each job gets its own directory, `.blend`,
preview, log, and Blender process.

## Why this design

The currently installed `ahujasid/blender-mcp` add-on is a GUI TCP bridge and
uses one fixed port by default. A worker pool avoids port routing and avoids
cross-contamination between projects. It also makes failures recoverable: a
failed worker is just one failed job.

## Run the smoke test

From PowerShell:

```powershell
Set-Location D:\blender-mcp-fleet\prototype\fleet
python .\smoke_test.py
```

The test submits four models with two workers, so two Blender jobs run at a
time. Results are written under `D:\blender-mcp-fleet\prototype\jobs`.

## Run the MCP dispatcher

The MCP dependency can be installed into a local environment with `uv`:

```powershell
Set-Location D:\blender-mcp-fleet\prototype
uv venv --python 3.11 .venv
uv pip install --python .\.venv\Scripts\python.exe "mcp[cli]==1.29.0"
```

Then register this as a separate MCP entry for testing; it does not replace
the current `blender` entry:

```toml
[mcp_servers.blender_fleet]
command = "D:\\blender-mcp-fleet\\prototype\\.venv\\Scripts\\python.exe"
args = ["D:\\blender-mcp-fleet\\prototype\\fleet\\mcp_server.py"]

[mcp_servers.blender_fleet.env]
BLENDER_FLEET_PARALLEL = "2"
```

The exposed tools are `submit_model_job`, `get_job_status`,
`wait_for_job`, `list_model_jobs`, and `fleet_info`.

To test the actual MCP stdio handshake without changing Codex configuration:

```powershell
D:\blender-mcp-fleet\prototype\.venv\Scripts\python.exe .\fleet\mcp_smoke.py
```

## Safety boundaries

The first version only accepts a small allow-listed set of model kinds. It
does not execute arbitrary agent-provided Python. A later version can add a
reviewed recipe/script mode with per-job timeouts and an explicit workspace
allow-list.
