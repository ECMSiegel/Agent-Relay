---
name: team-handoff
description: Hand off every team task you own before you stop. Use when the user says "hand off my team task", "I am running out of usage", "stop and hand off", or when you are close to a usage, context, or time limit in a project that has a team/ folder.
---

# Team handoff

The stopping ritual from the limit rule in `team/PROTOCOL.md`: leave each live task you own on the
board with a note a different agent can pick up cold, then leave. Run from the project folder, and
pass your own `--agent <ID>` on every command.

Relation to the `handoff` skill: that one writes `HANDOFF.md`, the state of the whole project.
This one records the state of each task inside `team/`. When stopping in a team project, run this
skill first; run the project-wide `handoff` skill only if the user asks for it.

## Procedure

1. Stop starting new work. Find your live tasks: run `python3 team/team.py status --agent <ID>`
   and note every task you own that is `claimed`, `in_progress`, or `blocked`. Tasks of yours in
   `review` need nothing.
2. For each live task, run `python3 team/team.py show <T> --agent <ID>` to get its registered paths.
3. Check the real state of those paths; do not write from memory. Read the files, run the task's
   verification if it is quick, and if the project is a git repository look at
   `git status -- "<path>"` and `git log -1 -- "<path>"`.
4. Write the note to a file outside `team/` (for example a scratch file), saying:
   - what is done (and verified);
   - what is next, as the first concrete action;
   - exact pointers: file paths and line numbers;
   - what not to redo;
   - then, as the last lines, one line per registered path:
     `<path>: committed` or `<path>: clean` or `<path>: uncommitted edits`
     (`committed` = you committed it; `clean` = you left it untouched; `uncommitted edits` =
     changes sit in the working tree).
5. Hand it off: `python3 team/team.py handoff <T> --agent <ID> --note-file "<note file>"`.
   Repeat steps 2 to 5 for every live task.
6. Run `python3 team/team.py check-exit --agent <ID>`. It must print `OK to leave`. If it lists a
   task, go back to step 5 for that task.
7. Run `python3 team/team.py leave --agent <ID>`.
8. Tell the user which tasks were handed off and anything they must do (for example an open
   question you raised). A `blocked` task's question stays open after handoff; the next owner holds
   the task as `claimed`, reads the question in `team/QUESTIONS.md`, and runs `start` once it is
   resolved (see "Blocked tasks" in `team/PROTOCOL.md`).

The one thing most likely to go wrong: skipping the per-path state lines, or writing `clean` for a
path with half-written edits. Check each path before choosing the word.

## Exit criteria
- Every live task you owned was handed off with a note that includes one state line per registered
  path.
- `check-exit` printed `OK to leave`, and `leave` succeeded.
- The user was told what was handed off.
- If the user asked for it, the `handoff` skill was run afterwards.

## When uncertain
- Unsure of a path's state: choose `uncommitted edits` and say what you saw; it is the safe word.
- `handoff` exits 2 (not your task, or not live): run `status`, read the reason, and do not
  retry blindly; a task reclaimed from you needs no handoff.
- Not enough time for a full note: write a short one (done / next / path states) and hand off
  anyway; an imperfect note beats an owned task that goes stale.
- You lost your agent ID: look in your notes or ask the user. A new `join` ID cannot hand off the
  old one's tasks; they go stale and another agent reclaims them.
