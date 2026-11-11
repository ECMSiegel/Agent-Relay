# Agent Coordination

This is the human guide to a small, local-only task board for several coding agents working in one project. `team.py` records task state and generates the Markdown views; agents edit only paths registered to their tasks.

The tool uses Python 3.8+ and the standard library. Keep the project and its `team/` folder on a normal local filesystem. Network shares and background-sync folders can interfere with its file lock. A lock lease can expire after 20 seconds, so do not suspend a running command or hold it in a debugger.

## Set up a project

From the project folder that should contain `team/`, run the kit initializer. For a project nested under the kit, use its `.agents/team/team.py` path; for a project elsewhere, ask for the kit location and use that path:

```sh
python3 "/path/to/kit/.agents/team/team.py" init
```

If the project cannot reach the kit, run `init --standalone` using an available copy. This copies the tool into `team/team.py`. Keep the project and board on a normal local filesystem, not a network share or a folder synchronized in the background.

`init` creates `team/` and preserves existing project files, `team/PLAN.md`, `team/config.json`, tasks, messages, and records. Re-running it refreshes the protocol and launcher only. It does not replace existing `AGENTS.md`; you can add a short pointer there to `team/PROTOCOL.md` so agents discover the board rules.

Answer two prompts: (1) the project's goal, scope, and exclusions; (2) how to verify success and what “done” means. The setup procedure drafts `team/PLAN.md` and asks you to review it once before writing. Then either seed tasks or let the first agent break down the plan. To start workers, tell each: **“Join the project and start working.”**

## Skills

Eight portable procedures live in `.agents/skills/` and can be used as slash commands in supported tools:

| Skill | Purpose |
|---|---|
| `team-init` | Set up a board and prepare its project plan |
| `team-join` | Join and follow the project protocol |
| `team-status` | Summarize current work, review, and blockers |
| `team-task` | Create tasks with bounded file ownership |
| `team-handoff` | Hand off live work before stopping |
| `team-review` | Review another agent's completed task |
| `team-answer` | Resolve user questions and proposals |
| `team-doctor` | Diagnose board consistency |

## Working loop

Agents read `team/PROTOCOL.md`, join, inspect the plan and board, read messages, then use `next` to find work. They claim and start one task, change only its registered paths, verify it, and finish it. Tasks requiring review wait for another agent or the user. Before stopping, an agent hands off every live task, runs `check-exit`, and leaves.

The board does not infer progress from silence or a separate background process. Staleness is based on the timestamp recorded by supported agent commands. `status` is read-only and does not refresh that timestamp. For an explicit check-in while continuing work, run `python3 team/team.py next --agent <ID>`; it shows claimable and review work and records activity.

## The board page and the coordinator

Every change also rewrites `team/BOARD.html`, a self-contained page you open by double-click. It shows a lane per agent (stale, last seen, usage the agent reported with `usage`), a "Needs you" strip, and a detail panel for any task. It reloads every 5 seconds. For desktop notifications on a Mac, run `python3 team/team.py watch` in a terminal.

One agent can join with `join --role coordinator`. Coordinators are told when a question, block, review or handoff needs attention, can run `wait` in the background to be woken by it, and can take a task from a live owner (`reclaim <T> --agent <ID>`, or `--release` to return it to the pool). An agent about to run something long calls `busy` so it is not mistaken for stale.

## Commands

Run from the project folder with `python3 team/team.py <command>`. Agents include `--agent <ID>` on agent commands; `join` prints an ID. `python3 team/team.py --help` and each command's `--help` show exact options.

Common commands:

```sh
python3 team/team.py status
python3 team/team.py join --label "Codex"
python3 team/team.py next --agent <ID>
python3 team/team.py claim T001 --agent <ID>
python3 team/team.py start T001 --agent <ID>
python3 team/team.py done T001 --agent <ID> --note "Changed and verified ..."
python3 team/team.py review T001 --agent user --approve --note "Reviewed ..."
python3 team/team.py complete
```

By default, completed tasks require review. The reviewer must be someone other than the task owner. A task keeps its registered path reservations while it is in `review`; approval or rejection releases them. This prevents another task from changing the submitted files while review is pending.

Task paths should be specific files or the narrowest necessary directories. Do not register wildcard paths for new tasks; the tool may interpret path patterns for overlap checks, but task ownership should be explicit and reviewable. Avoid broad project-root reservations.

Exit codes: `0` success; `1` invalid command or ID; `2` a team rule refused the action (except `complete`, where it means unfinished); `3` lock busy, retry shortly. No command commits, publishes, or contacts an external service.

## Files and records

Truth is stored in JSON under `team/tasks/`, `team/agents/`, and `team/questions/`, and in the JSONL logs. `BOARD.md`, `MESSAGES.md`, `DECISIONS.md`, `DISCOVERIES.md`, and `QUESTIONS.md` are generated views; do not edit them by hand. The lock files are transient.

`complete` passes only when at least one task exists, every task is `done`, and `team/PLAN.md` has exactly one non-empty Definition of done section with at least one real checkbox criterion, no malformed or placeholder criteria, and no unchecked boxes. The final agent verifies each item and logs a decision before ticking it; an empty or template plan cannot pass.
