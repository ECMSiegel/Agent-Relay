---
name: team-join
description: Join a project that has a team/ coordination folder and work as one of its agents. Use when told to join the project, start working, or pick up team tasks; not for other requests in such a project.
---

# Team join

Some projects coordinate several coding agents through a `team/` folder inside the project. The
rules for working there live in that project's `team/PROTOCOL.md`. This skill only gets you to that
file; the protocol itself is the procedure.

## Procedure

1. Find the project folder: the folder you were opened in, or the project the user named.
2. Check whether it contains `team/PROTOCOL.md`.
3. If it does and you were told to join, start working, or pick up team tasks: read
   `team/PROTOCOL.md` in full, then follow it exactly, starting with its
   "Identity" section (run `python3 team/team.py join --label "<your tool name>"` from the project
   folder) and then its loop. The protocol overrides any habit of yours that conflicts with it, for
   example editing files outside your task, or continuing to work without handing off when near a
   limit.
4. If it does but the request is something else: do not join. Run `python3 team/team.py status`
   once from the project folder, do not edit paths registered to live tasks, and carry on with
   the request.
5. If there is no `team/` folder: say so plainly. Offer to enable the team tool only when the user
   explicitly asked you to join a project; otherwise carry on with the user's request as normal.
   Do not create the folder unasked. If the user asked to join and agrees to enable it, run from
   the project folder:
   `python3 "<kit path>/.agents/team/team.py" init`
   (for a nested project, the kit initializer is in its parent tree; for a project elsewhere, ask
   for the kit path. Add `--standalone` when the kit cannot be reached from the project). Use
   `team-init` to prepare and review the project plan before anyone claims work.

If you were told to join as the coordinator, run `join --role coordinator`. You are then told when
a question, review, block or handoff needs attention; the protocol's "Coordinating a team" section
says how to use `wait` and `reclaim`. Workers report usage with `usage` and use `busy` before a long
step.

The one thing most likely to go wrong: forgetting your agent ID. Write it down as soon as `join`
prints it, and pass `--agent <ID>` on every command.

## Exit criteria
- `team/PROTOCOL.md` was read in full, and `join` printed your agent ID; or
- the request was not to join, `status` was run once, and no path registered to a live task was
  edited; or
- there was no `team/` folder, the user was told so, and (only if they had asked to join) they were
  asked whether to run `init` and their answer was followed.
- From then on you are working in the protocol's loop, which ends with `handoff` and `leave` (or
  with `complete` printing `COMPLETE`).

## When uncertain
- Unsure which folder is the project: ask the user one short question; do not run `init` or `join`
  in a guessed folder.
- `python3 team/team.py` fails to start (no Python 3, or the workspace tool is not found): report
  the exact error to the user and stop; do not edit `team/` files by hand to imitate a command.
- The protocol and the project's `team/PLAN.md` seem to disagree: follow the protocol for how to
  work and the plan for what to build, and raise the conflict with the `question` command.
