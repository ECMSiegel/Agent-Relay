# Release notes

**Version:** 0.2.0
**Status:** Tagged `v0.2.0`. Source is public on GitHub under the MIT License.

This release packages a small Python 3.8+ standard-library task board for coordinating coding
agents in one project folder. It records task ownership, reserved paths, questions, handoffs, and
independent review without moving or rewriting the project's source files.

## Contents

- `team.py` commands for setup, task lifecycle, file reservations, messages, handoffs, review,
  status, and consistency checks.
- A generated `team/BOARD.html` page with agent lanes, usage, stale flags and a "Needs you" strip.
- A coordinator role (`join --role coordinator`), `msg --to coordinator`, automatic coordinator
  alerts, `reclaim` override and `--release`, and `busy` so long steps are not called stale.
- `usage` (self-reported), `wait` (for coordinators) and `watch` (a sound and a banner on a Mac) commands.
- Optional per-task git worktrees (`"worktrees": true`): a task's work stays in its own folder and branch until its approval merges it.
- Eight portable team skills for setup, joining, task creation, handoff, review, status, answers,
  and board diagnosis.
- Protocol and human documentation, plus an Event Page starter fixture for a fresh setup.
- Unit and concurrent-simulation checks.

## Validation

- 241 unit tests passed on the development machine.
- All 14 concurrent simulation scenarios passed on the development machine.
- The GitHub check runs the unit suite and simulation on Python 3.8 and 3.12, and builds and smoke-tests the package on 3.12.
- A two-agent interruption, handoff, and review trial is documented in the local work records.

These results do not establish support on every vendor host or an
uncoached beginner setup experience. Those trials remain open.

## Still open

- An uncoached beginner setup trial.
- Trials on tools other than Claude Code, Codex and OpenCode.
