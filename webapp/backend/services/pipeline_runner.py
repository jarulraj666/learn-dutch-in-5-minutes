"""Subprocess-based pipeline runner with SSE log streaming."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from asyncio.subprocess import Process
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

ROOT = Path(__file__).resolve().parent.parent.parent.parent
PYTHON = sys.executable  # Same venv that runs the backend


@dataclass
class PipelineJob:
    job_id: str
    args: list[str]
    started_at: str
    status: str = "running"   # running | done | failed | aborted
    exit_code: int | None = None
    log_buffer: deque[str] = field(default_factory=lambda: deque(maxlen=2000))
    _process: Process | None = field(default=None, repr=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def _emit(self, line: str) -> None:
        self.log_buffer.append(line)
        for q in self._subscribers:
            q.put_nowait(line)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        # Replay buffered lines so late-joining clients see history
        for line in self.log_buffer:
            q.put_nowait(line)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass


# Global registry: job_id → PipelineJob
_jobs: dict[str, PipelineJob] = {}


def get_job(job_id: str) -> PipelineJob | None:
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    return [
        {
            "job_id": j.job_id,
            "args": j.args,
            "started_at": j.started_at,
            "status": j.status,
            "exit_code": j.exit_code,
        }
        for j in _jobs.values()
    ]


def _is_topic_running(topic_id: str) -> bool:
    return any(
        j.status == "running" and f"--topic-id={topic_id}" in " ".join(j.args)
        for j in _jobs.values()
    )


async def start_pipeline(
    *,
    level: str | None = None,
    category: str | None = None,
    topic_id: str | None = None,
    count: int = 1,
    no_upload: bool = False,
    script_only: bool = False,
    resume_checkpoint: str | None = None,
    artifact_path: str | None = None,
    stages: list[int] | None = None,
) -> PipelineJob:
    """Start run_pipeline.py as an async subprocess and return the job."""

    if topic_id and _is_topic_running(topic_id):
        raise ValueError(f"A pipeline run for '{topic_id}' is already in progress.")

    cmd: list[str] = [PYTHON, "-m", "pipeline.run_pipeline"]

    if artifact_path and stages:
        cmd += ["--artifact", artifact_path, "--stages", ",".join(map(str, stages))]
    elif resume_checkpoint:
        cmd += ["--resume", resume_checkpoint]  # now accepts artifact path
    else:
        if topic_id:
            cmd += ["--topic-id", topic_id]
        else:
            if level:
                cmd += ["--level", level]
            if category:
                cmd += ["--category", category]
            cmd += ["--count", str(count)]
        if no_upload:
            cmd.append("--no-upload")
        if script_only:
            cmd.append("--script-only")

    job_id = str(uuid.uuid4())[:8]
    job = PipelineJob(
        job_id=job_id,
        args=cmd,
        started_at=datetime.utcnow().isoformat() + "Z",
    )
    _jobs[job_id] = job

    asyncio.create_task(_run_job(job, cmd))
    return job


async def _run_job(job: PipelineJob, cmd: list[str]) -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
            env=env,
        )
        job._process = proc

        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            job._emit(line)

        await proc.wait()
        job.exit_code = proc.returncode
        job.status = "done" if proc.returncode == 0 else "failed"
        job._emit(f"__STATUS__{job.status}__EXIT__{job.exit_code}__")
    except asyncio.CancelledError:
        job.status = "aborted"
        job._emit("__STATUS__aborted__EXIT__-1__")
    except Exception as exc:
        job.status = "failed"
        job._emit(f"[error] {exc}")
        job._emit("__STATUS__failed__EXIT__-1__")


async def abort_job(job_id: str) -> bool:
    job = _jobs.get(job_id)
    if not job or job.status != "running" or job._process is None:
        return False
    job._process.terminate()
    return True


async def stream_logs(job_id: str) -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted lines."""
    job = _jobs.get(job_id)
    if not job:
        yield "data: {\"error\": \"Job not found\"}\n\n"
        return

    q = job.subscribe()
    try:
        while True:
            try:
                line = await asyncio.wait_for(q.get(), timeout=30)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue

            yield f"data: {line}\n\n"

            if line.startswith("__STATUS__"):
                break
    finally:
        job.unsubscribe(q)
