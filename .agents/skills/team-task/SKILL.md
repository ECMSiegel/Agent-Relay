---
name: team-task
description: Turn a description of work into well-formed tasks on the team board. Use when the user or an agent says "add a team task", "create tasks for this", "break this down into team tasks", or "put this on the board".
---

# Team task

Create tasks that other agents can claim without stepping on each other. The rules for tasks
(states, file claims, review) are in `team/PROTOCOL.md`; this is only the procedure for writing
them well. Run from the project folder. Agents pass `--agent <ID>`; the user passes `--agent user`.

## Procedure

1. Run `python3 team/team.py status` first. Read the existing tasks so you do not duplicate one,
   and note every path registered to a live task.
   If the board has no tasks and you are an agent (not `user`), first run
   `python3 team/team.py decide --agent <ID> --title "Initial task breakdown" --text "..."`. If it
   exits 2, another agent is doing the breakdown: add nothing, run `inbox` and `status` later, and
   re-run `next`. The human (`--agent user`) is exempt.
2. Read `team/PLAN.md` (Scope, Architecture notes, How to verify) so the tasks fit the plan. If
   the request contradicts the plan, do not add it; use `propose` (agent) or tell the user.
3. Split the request: one task per independently verifiable piece. If a piece cannot be checked
   on its own, it belongs inside a neighbouring task. If one piece needs another first, record it.
4. For each task, decide:
   - title: short, starts with a verb.
   - description: what to build, and how to verify it (the command or the observable result).
   - `--files`: declare every path the task will touch, relative to the project folder. Use exact
     files or the narrowest necessary directories; do not create wildcard reservations. Missing a
     path means the agent has to register it later and may be refused.
   - `--depends <T>`: only real order constraints.
   - `--priority 1|2|3` (1 is highest).
   - `--no-review`: only where `team/PLAN.md` or the user says that area needs no review;
     otherwise leave review on.
5. Compare the paths against every reserved task (step 1), including tasks in review. If a path overlaps one, either make the new
   task depend on that task, move the shared piece into one task, or ask the user which task keeps
   the path. Do not ask others to give theirs up.
6. Create each task:
   `python3 team/team.py add --agent <ID> --title "..." --desc "..." --files "<path>" "<path>" --depends T001 --priority 2`
   Quote every path. Note the ID the command prints.
7. If other agents are affected (a shared file, an interface, a changed order), announce it:
   `python3 team/team.py msg --agent <ID> --to all --kind info --text "added T006: ..."`.
8. Run `python3 team/team.py status` and report the new task IDs to the requester.

The one thing most likely to go wrong: a task whose `--files` is too narrow. Tasks cannot be
deleted, so a badly shaped task is cancelled with `decide` plus `done --note "not needed"`
(see "Rules" in `team/PROTOCOL.md`). Get the shape right before running `add`.

## Exit criteria
- `status` was read before any `add`, and no new task duplicates an existing one.
- Every new task has a title, a description with how to verify, declared `--files`, and a priority.
- No new task's paths overlap a live task, or the overlap was resolved with the user.
- The new IDs were reported, and affected agents were told with `msg --to all`.

## When uncertain
- The request is too vague to split: ask the user one short question about the outcome, then split.
- Unsure which paths a task touches: search the code to find them; if still unsure, register the
  folder, not individual files.
- Unsure whether review is needed: leave it on.
- `add` exits 1: fix the flag it names (often an unknown `--depends` ID) and run it again.
