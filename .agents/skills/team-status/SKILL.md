---
name: team-status
description: Explain in plain English what the agents in a team project are doing and what is waiting on the user. Use when the user says "team status", "what is the team doing", "who is working on what", "is the project done", or asks what needs their attention.
---

# Team status

Give a newcomer a plain-language picture of what is happening, what needs the user's attention,
and the next useful action. Run from the project folder (the one containing `team/`). Status is a
read-only snapshot: it does not heartbeat an agent, take the writer lock, or refresh generated
views. If a writer lock overlaps the read, the output warns that the snapshot may be changing.

## Procedure

1. Run `python3 team/team.py status`. You may pass `--agent <ID>` or let `TEAM_AGENT` supply the
   caller ID; status validates/uses that ID for the unread count but never heartbeats it. Omit the
   ID if it is not useful.
2. Read `team/PLAN.md` for scope and Definition of done. Read raw `team/questions/Q*.json` records
   for open questions and plan-change proposals, and recent `team/messages.jsonl` entries for
   announcements and warnings. For task handoffs, read the `handoff` field in the relevant raw
   `team/tasks/T*.json` records; this is the current task-specific handoff source. A project-level
   `HANDOFF.md` may add context, but it can be older and does not replace task records. These are
   read-only inspections; do not run a handoff or resolve command.
3. Use status plus those raw files to explain, in plain English and short bullets:
   - What is underway: name agents and tasks that are active, blocked, stale, or awaiting review.
     If many agents are idle or available, summarize them with counts instead of listing every
     agent. Include task IDs, titles, and states for the work that matters.
   - What needs the user's decision: open questions and plan-change proposals are user-only; name
     each ID and summarize the choice being asked. For tasks in `review`, distinguish work another
     active agent can review from work that currently needs user review/approval. Do not imply that
     every review item is waiting solely on the user when a peer reviewer can act.
   - Any stale agent's live task and task-specific handoff note, if present. Check recent messages
     for a long-step announcement before interpreting silence.
   - Whether tasks and the plan's Definition of done appear complete. Do not run `complete` just to
     check; report unknown if the raw files do not establish it.
   - Verification limits stated in task records or messages: separate reported checks from checks
     independently observed, and do not treat a review state as user confirmation.
4. End with the next action for the user, if any, and the skill that does it:
   `team-answer` for questions and proposals, `team-review` for tasks in review, `team-doctor`
   if the board looks inconsistent, `team-task` to add work. If nothing is needed, say so.

Treat generated markdown views as potentially stale: status does not regenerate them. If a status
run reports snapshot contention, retry once when no writer is active before drawing conclusions.

## Exit criteria
- `status`, `team/PLAN.md`, relevant raw task and question records, and recent raw messages were
  read. A project `HANDOFF.md` was considered for context if present.
- The summary covers all items that need a user decision, identifies work a peer can review,
  covers stale owners and relevant handoffs, and states whether completion is known.
- No file in `team/` was edited and no state-changing command was run.

## When uncertain
- `team/` does not exist: say so and offer the `team-init` skill; do nothing else.
- Status reports snapshot contention: retry once after the writer finishes; if it persists, report
  that the snapshot may be inconsistent.
- A read-only file is missing: say it is missing; do not regenerate or repair it during status.
- The views and raw records disagree: treat the raw records as authoritative, mention that views
  may be stale, and suggest `team-doctor`.
