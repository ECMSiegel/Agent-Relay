---
name: team-review
description: Review a finished team task and approve or reject it. Use when the user or an agent says "review a team task", "check the tasks waiting in review", "approve T003", or when next lists tasks in review that you do not own.
---

# Team review

Check another agent's finished work and decide. The review rules are in `team/PROTOCOL.md`
("Rules", Review). Run from the project folder. Agents pass their own `--agent <ID>`; the human
reviews with `--agent user`.

## Procedure

1. Pick the task. Agents: run `python3 team/team.py next --agent <ID>`; its second list shows tasks
   in `review` owned by someone else. Humans: use the task ID you name, or run `status`.
   Never pick your own task: the tool refuses it, and do not try another route around that.
2. Run `python3 team/team.py show <T> --agent <ID>` (humans: `--agent user`). Read the description
   and the registered paths. The `done` note is in the log lines of that output, as
   "review requested: <note>".
3. Check the submitted task still reserves its paths with
   `python3 team/team.py owner "<path>" --agent <ID>`. If another task also reserves a path,
   report the conflicting IDs and pause that review until the intended change can be identified.
4. Read the changes to the task's registered paths. In a git repository, run
   `git diff -- "<path>"` (and `git log -3 -- "<path>"` if the work was committed). Otherwise read the
   files against the `done` note. To spot changes outside the registered paths, run `git status`
   and `git diff` on the whole project when it is a git repository; otherwise compare file
   timestamps. Do not edit any of those paths while reviewing; a fix is the owner's job after a
   reject.
5. Run the verification the task description names, and the checks in the "How to verify" section
   of `team/PLAN.md` that apply. Read the whole output. A pass you did not see is not a pass.
6. Decide:
   - Approve: `python3 team/team.py review <T> --agent <ID> --approve --note "what I checked"`.
   - Reject: `python3 team/team.py review <T> --agent <ID> --reject --note "<what fails and how to
     confirm the fix>"`. The note becomes the next owner's handoff, so name the file, the failing
     check, and the exact command that proves the fix.
7. Report the decision and the reason. Agents then go back to the loop in `team/PROTOCOL.md`.

The one thing most likely to go wrong: approving because the `done` note sounds right. Compare the
diff and fresh verification output, not the note.

## Exit criteria
- The task's description, `done` note, diff (or files) and verification output were all read.
- The verification was run in this session, or the review note says exactly why it could not be.
- `review` was run with `--approve` or `--reject`, and a reject note says what fails and how to
  confirm the fix.
- You did not review your own task, and you edited none of its paths.

## When uncertain
- Verification cannot be run here (missing tool, needs the user's real test): do not approve; reject
  with that stated, or ask the user to run it and tell you the result.
- The diff includes changes outside the task's registered paths: reject and name them.
- No task is in `review` for you: say so; do not review a task that is not in `review`.
- The user wants a human sign-off on a task: leave it for them and run nothing yourself.
