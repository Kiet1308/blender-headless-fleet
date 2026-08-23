"""Concurrent, isolated Blender worker pool.

This is intentionally independent of the installed Blender add-on.  Each
job gets a new background Blender process and a private directory, so agents
cannot cross-write another agent's .blend file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any


DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SCRIPT = Path(__file__).with_name("worker_job.py")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return value[:48] or "job"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


class BlenderFleet:
    def __init__(self, root: str | Path = DEFAULT_ROOT, blender: str = DEFAULT_BLENDER, max_parallel: int = 2, timeout_seconds: int = 300):
        self.root = Path(root).resolve()
        self.jobs_root = self.root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.blender = str(Path(blender).resolve())
        self.max_parallel = max(1, int(max_parallel))
        self.timeout_seconds = max(30, int(timeout_seconds))
        self.executor = ThreadPoolExecutor(max_workers=self.max_parallel, thread_name_prefix="blender-worker")
        self.futures: dict[str, Future] = {}
        self.lock = threading.Lock()

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        name = str(request.get("name") or request.get("kind") or "model")
        job_id = f"{_slug(name)}-{uuid.uuid4().hex[:8]}"
        job_dir = self.jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        payload = {"job_id": job_id, "name": name, "kind": request.get("kind", "cube"), "color": request.get("color", [0.15, 0.45, 0.95]), "resolution": request.get("resolution", 384)}
        request_file = job_dir / "request.json"
        _write_json(request_file, payload)
        _write_json(job_dir / "status.json", {"state": "queued", "job_id": job_id, "updated_at": time.time()})
        future = self.executor.submit(self._run, job_id, request_file)
        with self.lock:
            self.futures[job_id] = future
        return {"job_id": job_id, "state": "queued", "job_dir": str(job_dir)}

    def _run(self, job_id: str, request_file: Path) -> dict[str, Any]:
        job_dir = request_file.parent
        log_file = job_dir / "blender.log"
        env = os.environ.copy()
        env["BLENDER_FLEET_JOB"] = str(request_file)
        env["BLENDER_USER_RESOURCES"] = str(job_dir / "blender_user")
        command = [self.blender, "--background", "--factory-startup", "--python", str(WORKER_SCRIPT)]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with log_file.open("w", encoding="utf-8", errors="replace") as log:
                # Never inherit the MCP stdio pipe. Blender background mode can
                # otherwise keep the process alive while waiting on stdin.
                process = subprocess.Popen(command, cwd=str(job_dir), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=creationflags)
                try:
                    return_code = process.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    return {"job_id": job_id, "state": "failed", "error": f"Blender timed out after {self.timeout_seconds} seconds", "log_file": str(log_file)}
            result_file = job_dir / "result.json"
            if result_file.exists():
                result = json.loads(result_file.read_text(encoding="utf-8"))
                result["process_return_code"] = return_code
                _write_json(result_file, result)
                return result
            return {"job_id": job_id, "state": "failed", "error": f"Worker exited without result.json (code {return_code})", "log_file": str(log_file)}
        except Exception as exc:
            return {"job_id": job_id, "state": "failed", "error": str(exc), "log_file": str(log_file)}

    def status(self, job_id: str) -> dict[str, Any]:
        job_dir = self.jobs_root / job_id
        result_file = job_dir / "result.json"
        status_file = job_dir / "status.json"
        if result_file.exists():
            return json.loads(result_file.read_text(encoding="utf-8"))
        if status_file.exists():
            return json.loads(status_file.read_text(encoding="utf-8"))
        return {"job_id": job_id, "state": "unknown"}

    def list_jobs(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self.jobs_root.iterdir() if self.jobs_root.exists() else []):
            if path.is_dir() and (path / "request.json").exists():
                items.append(self.status(path.name))
        return items

    def wait(self, job_id: str, timeout: float | None = None) -> dict[str, Any]:
        with self.lock:
            future = self.futures.get(job_id)
        if future is not None:
            return future.result(timeout=timeout)
        return self.status(job_id)

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated Blender jobs concurrently")
    parser.add_argument("--blender", default=os.environ.get("BLENDER_EXE", DEFAULT_BLENDER))
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    fleet = BlenderFleet(args.root, args.blender, args.parallel, args.timeout)
    requests = [
        {"name": "agent-cube", "kind": "cube", "color": [0.1, 0.45, 0.95]},
        {"name": "agent-robot", "kind": "robot", "color": [0.9, 0.2, 0.08]},
        {"name": "agent-tower", "kind": "tower", "color": [0.18, 0.75, 0.35]},
        {"name": "agent-monkey", "kind": "monkey", "color": [0.75, 0.35, 0.9]},
    ][: max(1, min(args.jobs, 4))]
    try:
        submitted = [fleet.submit(request) for request in requests]
        print(json.dumps({"submitted": submitted}, indent=2))
        results = [fleet.wait(item["job_id"], timeout=args.timeout + 30) for item in submitted]
        print(json.dumps({"results": results}, indent=2, ensure_ascii=False))
        return 0 if all(item.get("state") == "succeeded" for item in results) else 1
    finally:
        fleet.close()


if __name__ == "__main__":
    raise SystemExit(main())
