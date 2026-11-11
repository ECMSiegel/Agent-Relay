---
name: team-init
description: Enable the local team coordination tool in a project and set up its plan. Use when someone asks to set up team coordination, initialize a board, or prepare a project for several coding agents.
---

# Set up team coordination

Use this procedure for the human-facing setup. The project agent loop begins after `team/PROTOCOL.md` exists.

1. Identify the intended project folder. Preserve all existing files, including any `AGENTS.md` and any existing plan or board data.
2. Find the kit's `.agents/team/team.py` in a parent folder when the project is nested under the kit. For a project elsewhere, ask for the kit location rather than guessing. Run its `init` from the intended project folder. If the kit cannot be reached there, use an available copy with `init --standalone`.
3. Read the resulting `team/PLAN.md`. Ask two concise questions:
   - What outcome should the project achieve, what work is in scope, and what should stay out?
   - How should success be checked, and what must be true before the work is done?
   If information is already present in project files, use it to draft answers and ask the user to correct gaps instead of repeating known facts.
4. Draft all plan sections from the answers and relevant project context. If task seeding would help, prepare a short task proposal alongside it with task titles, descriptions, exact files, dependencies, priority, and review policy. Present the plan and any task proposal together for one review, then wait for approval or corrections before writing either. If a meaningful existing plan is present, preserve it and include proposed revisions in this same review.
5. After approval, write the approved plan and create only the approved starter tasks. If no task proposal was included or approved, leave the board empty for the first agent to break down.
6. Show `status` and give each worker this startup sentence: **“Join the project and start working.”** Explain that review is enabled by default and a task owner cannot approve their own work. In a solo workflow, the user must approve each task requiring review, or explicitly set `review_default` to false before tasks are created. When a separate reviewer is useful, the user can open a second chat and give it the review task ID.

After setup, tell the user that `team/BOARD.html` is a page they can open by double-click to watch the agents, that one agent can join with `--role coordinator` to be alerted and to take over stuck tasks, and that `python3 team/team.py watch` gives Mac notifications.

`init` creates `team/`, copies the protocol and launcher, and initializes plan/config only when absent. Re-running it refreshes the protocol and launcher while preserving plans, configuration, tasks, messages, and records. It does not replace the project's existing `AGENTS.md`; offer a small protocol pointer as an additive edit only when appropriate.

## Exit criteria
- The intended project has a usable `team/` folder and its existing files were preserved.
- The user answered or corrected the two setup prompts and reviewed the full plan draft once before it was written.
- The plan and any proposed starter tasks were presented together for one approval before either was written.
- The user received the startup sentence and a clear explanation of default review.

## When uncertain
- If the target project or kit location is unknown, ask one direct question and do not initialize a guessed folder.
- If an existing plan has meaningful content, show it and wait for the user's review before changing it.
- If no answer is available for a plan section, label it unresolved in the draft and ask the user to fill it rather than inventing requirements.
