---
name: team-answer
description: Walk the user through the open questions and plan-change proposals from the agents and record their answers. Use when the user says "answer team questions", "what are the agents asking", "go through the proposals", or after status shows questions waiting.
---

# Team answer

Agents ask the user questions and propose plan changes through the team tool; the answers only
count once they are recorded with the tool. This skill is for the human's session. Run from the
project folder.

## Procedure

1. Read `team/QUESTIONS.md`. List every open question and plan-change proposal, with its ID
   (`Q001`...), who asked, the task it relates to, and the text. A plan-change proposal appears
   there as text starting "PLAN CHANGE PROPOSAL: <title> - <text>". Answered ones need nothing.
   The rules for questions and proposals are in `team/PROTOCOL.md`.
   If none are open, say so and stop.
2. For each open item, one at a time, tell the user in plain English what is being asked and what
   happens if they choose each way (for example a blocked task continues, a plan changes). Then ask
   for their answer. Do not answer for them.
3. Record each answer exactly as the user gave it:
   `python3 team/team.py resolve Q00n --agent user --text "<the user's answer>"`
   The asking agent is told through its messages when it is a joined agent.
4. For an accepted plan-change proposal, make the change real, in this order:
   1. Log it first: `python3 team/team.py decide --agent user --title "<short title>" --text "<what changed and why>"`.
   2. Then edit `team/PLAN.md` with the agreed wording, only the sections the proposal changes.
   Resolve the proposal's question as in step 3, mentioning that the plan was edited. A declined
   proposal is only resolved; `team/PLAN.md` stays as it is.
5. Check the result: run `python3 team/team.py status` and read `team/QUESTIONS.md` again to confirm
   the items now show as answered.
6. Remind the user once: `QUESTIONS.md` and the other rendered files are never edited by hand,
   because the next command regenerates them and typed answers are lost. Answers go through
   `resolve`.

The one thing most likely to go wrong: typing the answer into `team/QUESTIONS.md`. It is lost at the
next command. Always use `resolve`.

## Exit criteria
- Every open question and proposal was shown to the user, and each answer they gave was recorded
  with `resolve`.
- For every accepted proposal, `team/PLAN.md` was edited and a `decide` entry was logged.
- The re-read of `team/QUESTIONS.md` shows no item that the user answered as still open.
- No rendered file was edited by hand.

## When uncertain
- The user wants to skip an item: leave it open and say what stays blocked by it.
- A proposal is partly accepted: write only the accepted part into `team/PLAN.md` and say in
  the `resolve` text what was left out.
- `resolve` exits 1 (unknown or already answered ID): re-read `team/QUESTIONS.md` for the right ID.
- Unsure whether a question needs a plan change: record the answer, then ask the user if the plan
  should change; do not edit `team/PLAN.md` on a guess.
