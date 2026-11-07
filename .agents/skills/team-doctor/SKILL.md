---
name: team-doctor
description: Check a team project's team/ folder for inconsistencies and explain how to fix each one. Use when the user says "team doctor", "something is wrong with the team board", "the board looks broken", or when a team command fails oddly or doctor reports a problem.
---

# Team doctor

Find what is inconsistent in `team/` and fix it safely, through the tool, not by hand. Run from the
project folder. This skill is for the human's session.

## Procedure

1. Run `python3 team/team.py doctor`. It is read-only. `OK` means nothing is wrong. Exit code 2
   means at least one `problem:` line; a `warning:` line (a leftover lock file) does not change the
   exit code and clears itself on the next command.
   `doctor` prints `OK` even when a silent agent still owns live tasks. For an "an agent went
   silent" complaint, also run `python3 team/team.py stale` and `python3 team/team.py status`; the
   fix is `reclaim` by a live agent (see the list below).
2. Explain each `problem:` line to the user in plain English: what it means, and which task or
   agent it touches. Then offer the safe fix from the list below and wait for the user's go-ahead
   before running anything that changes state.
   - Live task whose owner is gone: run `python3 team/team.py stale`. A live agent can take it with
     `reclaim <T> --agent <ID>` (read the old owner's recent messages in `team/MESSAGES.md` first).
     The old owner cannot `handoff` or `release` it, because those need the owner's own ID.
     An owner of `user` is never stale; the user hands it off or releases it with `--agent user`.
   - Two live tasks register overlapping paths: `files add` cannot fix it. Ask the user which
     task keeps the path; the other task's owner then hands it off (`handoff`) and the task is
     re-added or re-planned with the `team-task` skill.
   - A `depends_on` that names a missing task, or a dependency cycle: tell the user which tasks
     are involved; the fix is a new task that replaces the bad one, chosen by the user.
   - A task file that will not read or lacks keys: `show` cannot read it. Open the JSON file itself
     under `team/tasks/` and restore it from its own `log` entries, from version control, or from
     the last good state the user remembers. Do not rewrite the JSON by hand unless the user tells you to.
   - An agent's current task owned by someone else, a question pointing at a missing task, or
     message IDs out of order: report the exact line; these point to a hand-edited or damaged file,
     so ask the user how to proceed.
   - Missing or stale view files (`BOARD.md` and friends): run
     `python3 team/team.py doctor --fix-views`. This rewrites only the views; use it only when
     views are the whole problem.
3. After any fix, run `python3 team/team.py doctor` again until it prints `OK` or only items the
   user chose to leave.
4. Report what was fixed, what was left, and why.

The one thing most likely to go wrong: editing JSON in `team/tasks/` or `team/agents/` by hand to
silence a problem. That skips the lock and hides the cause. Use a command, or ask.

## Exit criteria
- `doctor` was run, and every `problem:` line was explained to the user.
- Each change was approved by the user first and was made with a tool command.
- The final `doctor` run prints `OK`, or the user has agreed to leave what remains.
- No file under `team/` (JSON, logs, views, `PLAN.md`) was edited by hand unless the user said so.

## When uncertain
- Unsure what a problem line means: show it to the user as printed and read `team/PROTOCOL.md`
  ("Command reference", `doctor`) before suggesting a fix.
- A fix would discard someone's work (a task, a note, a question): stop and ask.
- `doctor` itself fails (exit 1 or 3): report the message; for 3 (lock busy) retry once.
- Several agents are still working: tell them with `msg --agent user --to all` before any reclaim.
