# Agent Relay

A local task board that lets several coding agents work in one project folder without overwriting each other, and lets one agent pick up exactly where another stopped.

I built it because I run Claude Code, Codex and OpenCode chats against the same project, and two things kept going wrong: agents edited the same files, and work was lost whenever a chat hit its usage limit. Agent Relay is one Python file and a `team/` folder of plain files. There is no server, no account and nothing to install.

![The Agent Relay board: one lane per agent, a "Needs you" strip, and reported usage](docs/board.png)

## What it does

- **Task board.** Tasks have an owner, a state, a priority, dependencies and a timestamped log. States are `available`, `claimed`, `in_progress`, `blocked`, `review` and `done`.
- **File reservations.** A task registers the paths it may change. A second task that overlaps them cannot be claimed until the first is finished.
- **Handoffs.** An agent that is about to stop writes a note saying what is done and what is next. The next agent sees that note when it claims the task.
- **Independent review.** The agent that did a task cannot approve it. Another agent or I have to.
- **Questions and decisions.** Agents log questions for me, decisions other agents must follow, and facts they found in the code, so nobody rediscovers them.
- **A visual board.** `team/BOARD.html` is regenerated on every change and opens by double-click.
- **Alerts.** `watch` plays a sound and shows a Mac banner when something needs me. `wait` lets a coordinator chat sleep until something needs it.
- **Stall recovery.** A coordinator can take or release a task from a stuck agent at once, and `next` offers tasks whose owner has gone quiet.
- **Optional git worktrees.** Each task can get its own working copy and branch, merged when the task is approved.

## How it works

All state lives in the project's `team/` folder:

| Path | What it holds |
|---|---|
| `team/team.py` | The command agents run. A small launcher that points at this kit, or a full copy with `init --standalone`. |
| `team/PLAN.md` | The goal, scope, rules and definition of done. I write it; agents propose changes. |
| `team/PROTOCOL.md` | The rules every agent follows, copied in by `init`. |
| `team/tasks/`, `agents/`, `questions/` | One JSON file per task, agent and question. |
| `team/*.jsonl` | Append-only logs of messages, decisions and discoveries. |
| `team/BOARD.md`, `BOARD.html` and other views | Generated from the files above. Never edited by hand. |

Every state change runs under a lock file and writes through a temporary file followed by an atomic rename, so agents can run commands at the same moment without corrupting anything. `status`, `wait` and `watch` only read and never take the lock.

An agent needs two abilities: reading a file and running a shell command. That is why it works across vendors. The eight skills in `.agents/skills/` (`team-init`, `team-join`, `team-task`, `team-status`, `team-review`, `team-handoff`, `team-answer`, `team-doctor`) wrap the common jobs for tools that load skills.

## Quick start

Clone the kit somewhere, then set up a board from the project you want to work on:

```sh
git clone https://github.com/ECMSiegel/Agent-Relay.git
cd /path/to/your/project
python3 "/path/to/Agent-Relay/.agents/team/team.py" init
```

`init` creates `team/` and leaves your files, your `AGENTS.md` and any existing board alone. Fill in `team/PLAN.md`, add a task or two, then open the project in each chat and say:

> Join the project and start working.

The agent reads `team/PROTOCOL.md`, joins, claims a task, does it and submits it for review. The same steps by hand:

```sh
python3 team/team.py add --agent user --title "Add the schedule" --desc "Eight rows, in order" --files index.html
python3 team/team.py join --label "Codex"          # prints an agent ID
python3 team/team.py next --agent <ID>             # what can I claim?
python3 team/team.py claim T001 --agent <ID>
python3 team/team.py start T001 --agent <ID>
python3 team/team.py done T001 --agent <ID> --note "what changed and how I checked it"
python3 team/team.py review T001 --agent user --approve --note "checked"
```

`python3 team/team.py --help` lists every command with the reason it can refuse.

## The board

Open `team/BOARD.html` in a browser. It reloads itself every five seconds and needs no server.

- **Lanes.** One row per agent, a row for the coordinator, and an Unassigned row. Columns are the task states.
- **Needs you.** Open questions, tasks waiting for review, tasks whose owner has gone quiet, agents close to their usage limit, and work nobody has picked up.
- **Stale agents.** An agent with no command for `stale_minutes` (30 by default) is flagged. The page works this out in the browser, so the flag appears even when no command has run since.
- **Usage.** Each lane shows the usage its agent last reported with `usage --percent`, plus what the tool measures itself: minutes on the current task, tasks finished and last seen.
- **Task details.** Selecting a task opens its description, paths, dependencies, handoff note and full timeline.

The usage percentage is self-reported. Agent Relay cannot read token or quota numbers from any vendor, so an agent that never reports shows "not reported".

## Coordinating a team

One agent can join as the coordinator:

```sh
python3 team/team.py join --role coordinator --label "Claude Code"
```

- **It is told things.** Questions, blocked tasks, review requests, handoffs and plan proposals arrive in its inbox automatically. Workers can also run `msg --to coordinator`.
- **It can wait.** `wait --agent <ID>` blocks until something new needs attention, then prints it and exits. Run it as a background command in a tool that resumes when a command finishes, and the coordinator wakes on its own. I have confirmed this in Claude Code only.
- **It can unstick work.** `reclaim <T> --agent <ID>` takes a task from any owner, and `reclaim <T> --agent <ID> --release` returns it to the pool with a note. Ordinary agents can only do this once the owner has left or gone stale.
- **Long steps are not mistaken for silence.** A worker runs `busy --minutes 25 --text "running the full build"` and is not treated as stale until that time is up.

For my own alerts I keep this running in a terminal:

```sh
python3 team/team.py watch
```

It prints each new item and, on macOS, plays a sound and shows a banner. The sound needs no setup. Banners need one: open Script Editor, run `display notification "test"`, and choose Allow. They do not show while Do Not Disturb is on.

## Task worktrees

With `"worktrees": true` in `team/config.json`, claiming a task creates `team/worktrees/<T>` on a branch named `team/<T>`. The agent works and commits there. A handoff leaves the folder in place, so the next owner continues with any half-finished edits. Approving the task merges the branch into the branch it started from and removes the folder; a merge conflict leaves the task in review.

This needs the project folder to be the top of its own git repository, with `team/` untracked. A plain recursive search from the project root will also find the copies under `team/worktrees/`.

## Choosing models

Agent Relay does not route work or spend tokens; I choose the model in each chat. What works for me is the strongest model for planning and coordinating, a cheaper one for bounded tasks, and a different model for review than the one that did the work.

## Try the walkthrough

`examples/Event Page` is a small page with an unfinished schedule. Open that folder in two chats and use the three prompts below. Chat A sets up the board and does part of the task, then hands off as if it had run out of usage. Chat B resumes from the handoff and submits for review. The page goes from two schedule rows to four to eight.

If an agent cannot find the kit, point it to `../../.agents/skills/team-init/SKILL.md`.

<details>
<summary>Prompt 1, in chat A: set up the task and do the first part</summary>

```text
Set up team coordination here. Goal: finish the accessible Harbor Lights Community Night page. Scope: local, dependency-free edits to index.html only. Success: title, date, venue, and complete schedule are visible in order at narrow and wide widths, with no remote assets.

Create review-required T001 “Complete the event schedule” for index.html. Its complete schedule is: 5:30 PM check-in and harbor welcome; 5:45 PM welcome from the neighborhood; 6:00 PM opening toast; 6:15 PM make-and-share activity; 6:45 PM harbor supper break; 7:00 PM community performances; 7:45 PM closing thanks; 8:00 PM event ends. Create T002 for later visual polish in index.html, dependent on T001. Show the full plan and task proposals; wait for my approval.

After approval, initialize, join, claim, and start T001. Add only the 6:00 PM opening toast and 6:15 PM activity. Leave T001 in progress, the remaining entries for the next worker, and “The rest of the program is being finalized.” in place. Do not hand off yet.
```

</details>

<details>
<summary>Prompt 2, in chat A: leave a handoff</summary>

```text
Hand off T001. Record that index.html has the 5:30, 5:45, 6:00, and 6:15 rows; the 6:45 supper break, 7:00 performances, 7:45 closing thanks, and 8:00 event end remain; and the “rest of the program” note must be removed. End the handoff with `index.html: uncommitted edits`. Run check-exit, leave, and do not edit index.html further.
```

</details>

<details>
<summary>Prompt 3, in chat B: resume and submit for review</summary>

```text
Join and follow team/PROTOCOL.md. Claim T001 and read its full handoff. Add the four remaining rows, remove the note, verify all eight rows are visible and ordered, then submit for independent review. Leave visual polish for later.
```

</details>

## Requirements and limits

- **Python 3.8 or later**, standard library only. The GitHub check runs the tests on 3.8 and 3.12.
- **Tools.** I use it with Claude Code, Codex and OpenCode. Any tool that can read a file and run a shell command should work, but I have not tested others.
- **Platform.** Developed and tested on macOS. Sounds and banners from `watch` are macOS only; everything else is plain Python and files.
- **One machine.** Agents share a folder on one computer. There is no network sync.
- **Cooperative, not enforced.** File reservations stop a conflicting claim, but nothing prevents an agent from editing a file it did not register. The protocol tells it not to.
- **No scheduler.** Agent Relay does not start agents or assign work. I open the chats, or a coordinator session spawns them.

## Development

```sh
python3 -B -m unittest discover -s .agents/team/tests       # unit tests
python3 -B .agents/team/tests/simulate.py --report /tmp/sim.md  # several agents at once
python3 scripts/build_release.py --check-first-commit        # build the zip
python3 scripts/smoke_release.py                             # test the built zip
```

The tool is `.agents/team/team.py`. The rules agents follow are in `.agents/team/PROTOCOL.md`, and `docs/RELEASE.md` covers packaging.

## License

MIT License. Copyright (c) 2026 Ethan Siegel. See [LICENSE](LICENSE).
