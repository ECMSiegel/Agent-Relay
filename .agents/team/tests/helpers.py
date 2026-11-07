"""Shared test helpers for the team tool. Never point these at the real .agents/team/ folder."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import time
import uuid
from pathlib import Path

TEAM_SRC = Path(__file__).resolve().parent.parent  # the real .agents/team/ (read only)
COPIED = ("team.py", "PROTOCOL.md", "PLAN.template.md", "config.default.json")


def make_workspace(tmp: Path) -> tuple:
    """Copy the tool, protocol, template and default config into <tmp>/.agents/team/ and create
    <tmp>/proj/. Returns (workspace, project)."""
    workspace = Path(tmp).resolve()
    dest = workspace / ".agents" / "team"
    dest.mkdir(parents=True)
    for name in COPIED:
        shutil.copy2(str(TEAM_SRC / name), str(dest / name))
    project = workspace / "proj"
    project.mkdir()
    return workspace, project


def load_tool(path: Path):
    """Import a team.py by file path under a unique module name."""
    spec = importlib.util.spec_from_file_location("team_tool_%s" % uuid.uuid4().hex, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(tool, *argv) -> tuple:
    """Run tool.main(argv) in-process; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = tool.main(list(argv))
    return code, out.getvalue(), err.getvalue()


# --- multiprocessing workers (module level so the spawn start method can import them) ---


def main_worker(tool_path, team_dir, argv, barrier, queue):
    """Load the tool from tool_path, wait at the barrier, run main(argv), report the exit code."""
    os.environ["TEAM_DIR"] = team_dir
    os.environ.pop("TEAM_AGENT", None)
    tool = load_tool(Path(tool_path))
    barrier.wait(timeout=60)
    code, out, err = run(tool, *argv)
    queue.put((list(argv), code, out, err))


def lock_worker(tool_path, team_dir, name, barrier, queue):
    """Acquire and release the lock once; detect a second simultaneous holder with an O_EXCL
    marker file created while holding the lock."""
    tool = load_tool(Path(tool_path))
    team = Path(team_dir)
    marker = str(team / "holder.marker")
    barrier.wait(timeout=60)
    try:
        tool.acquire_lock(team, name)
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            queue.put((name, "double holder"))
            tool.release_lock(team)
            return
        os.close(fd)
        time.sleep(0.005)
        os.unlink(marker)
        tool.release_lock(team)
        queue.put((name, "ok"))
    except Exception as exc:  # report, do not hang the parent
        queue.put((name, "error: %r" % (exc,)))
