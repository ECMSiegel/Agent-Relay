"""Drive the team tool the way several real agents would and write a PASS/FAIL report.

Usage: python3 .agents/team/tests/simulate.py [--report PATH]

Every scenario runs in a throw-away workspace under tempfile.mkdtemp(); the real .agents/team/
folder is only read (copied). The CLI is always driven through the team/team.py shim that `init`
writes, as a real agent would: subprocess.run([python, "team/team.py", ...], cwd=project).
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # importing helpers below must not write tests/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import TEAM_SRC, make_workspace  # noqa: E402

DEFAULT_REPORT = Path.cwd() / "SIMULATION.md"
ROUNDS = 50
CONTENDERS = 8
MAX_OUT_LINES = 6
MAX_LINE = 170

PLAN_TEXT = """# Simulated project

## Goal
Exercise the team tool with several agents at once.

## Scope
Seven small invented tasks.

## Non-goals
Anything real.

## Architecture notes
None.

## How to verify
Run the simulation.

## Definition of done
- [ ] Every task on the board is done.
- [ ] The simulation report shows ALL PASS.

## Milestones
1. all tasks done.
"""


# ---------------------------------------------------------------------------
# Running the CLI
# ---------------------------------------------------------------------------


def clean_env():
    env = dict(os.environ)
    env.pop("TEAM_DIR", None)
    env.pop("TEAM_AGENT", None)
    return env


def run(project, *args):
    """Run `python3 team/team.py <args>` in the project through its shim; (code, stdout, stderr)."""
    proc = subprocess.run([sys.executable, "team/team.py"] + [str(a) for a in args],
                          cwd=str(project), env=clean_env(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


def run_parallel(project, arglists):
    """Start all commands at the same moment (threads released by a barrier, each launching its
    own subprocess) and return [(code, stdout, stderr)] in the order given."""
    barrier = threading.Barrier(len(arglists))
    results = [None] * len(arglists)

    def worker(index):
        barrier.wait(timeout=60)
        results[index] = run(project, *arglists[index])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(arglists))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def leftover_locks(project):
    return sorted(p.name for p in (Path(project) / "team").glob(".lock*"))


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


class Log:
    """Collects the lines of one scenario and whether any check failed."""

    def __init__(self):
        self.lines = []
        self.failures = []

    def say(self, text):
        self.lines.append(text)

    def cmd(self, args, result, grep=()):
        code, out, err = result
        shown = " ".join(a if a and not any(c in a for c in " \"'") else json.dumps(a) for a in args)
        self.lines.append("$ python3 team/team.py %s" % shown)
        text = [l for l in (out + err).splitlines() if l.strip()]
        shown = text[:MAX_OUT_LINES]
        extra = [l for l in text[MAX_OUT_LINES:] if any(g in l for g in grep)]
        for line in shown:
            self.lines.append("    " + (line if len(line) <= MAX_LINE else line[:MAX_LINE] + "..."))
        if len(text) > MAX_OUT_LINES:
            self.lines.append("    ... (%d more lines)" % (len(text) - MAX_OUT_LINES))
            for line in extra:
                self.lines.append("    " + (line if len(line) <= MAX_LINE else line[:MAX_LINE] + "..."))
        self.lines.append("    [exit %d]" % code)

    def check(self, condition, message):
        if condition:
            self.lines.append("  ok: %s" % message)
        else:
            self.lines.append("  FAILED: %s" % message)
            self.failures.append(message)
        return bool(condition)

    def step(self, project, *args, **kw):
        result = run(project, *args)
        self.cmd(args, result, kw.get("grep", ()))
        return result

    def parallel(self, project, arglists):
        results = run_parallel(project, arglists)
        for args, result in zip(arglists, results):
            self.cmd(args, result)
        return results

    def done(self):
        return (not self.failures, self.lines)


def registered_paths(shown):
    """The `Registered paths:` list from `show` output."""
    lines = shown.splitlines()
    start = lines.index("Registered paths:") + 1 if "Registered paths:" in lines else len(lines)
    paths = []
    for line in lines[start:]:
        if not line.startswith("  - "):
            break
        paths.append(line[4:])
    return paths


def agent_id_from(out):
    marker = "You are "
    if marker not in out:
        return None
    return out.split(marker, 1)[1].split(".", 1)[0].strip()


# ---------------------------------------------------------------------------
# Workspace building
# ---------------------------------------------------------------------------


def init_project(project, tool_path):
    """Run `init` once with the tool itself (no shim exists yet); it writes the shim."""
    proc = subprocess.run([sys.executable, str(tool_path), "init"], cwd=str(project),
                          env=clean_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=60)
    if proc.returncode != 0 or not (Path(project) / "team" / "team.py").is_file():
        raise RuntimeError("init failed (%d): %s%s" % (proc.returncode, proc.stdout, proc.stderr))


def build_workspace(prefix):
    """Fresh temp workspace with an initialised project; returns (workspace, project)."""
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        workspace, project = make_workspace(tmp / "ws")
        init_project(project, workspace / ".agents" / "team" / "team.py")
    except BaseException:
        shutil.rmtree(str(tmp), ignore_errors=True)
        raise
    return workspace, project


def seed_plan_and_tasks(project, agent):
    """Write the plan and add the five tasks as `agent`. Returns the list of command results."""
    (Path(project) / "team" / "PLAN.md").write_text(PLAN_TEXT, encoding="utf-8")
    specs = [
        ("Task one", ["src/a.py"], [], True),
        ("Task two", ["src/b.py"], [], True),
        ("Task three", ["src/c.py"], ["T001"], False),
        ("Task four", ["src/d.py"], [], False),
        ("Task five", ["src/e.py"], [], False),
    ]
    results = []
    for title, files, deps, review in specs:
        args = ["add", "--agent", agent, "--title", title, "--desc", "Simulated work: " + title]
        for f in files:
            args += ["--files", f]
        for d in deps:
            args += ["--depends", d]
        if not review:
            args.append("--no-review")
        results.append((args, run(project, *args)))
    return results


# ---------------------------------------------------------------------------
# Scenario 0 - the lock fail-first proof
# ---------------------------------------------------------------------------


def doctor(text, sleep_seconds):
    """Return a copy of the tool text with the lock disabled and a delay in the claim."""
    out, marks = [], {"acquire": 0, "release": 0, "claim": 0}
    for line in text.splitlines():
        out.append(line)
        if "# LOCK-ACQUIRE" in line:
            out.append("    return")
            marks["acquire"] += 1
        elif line.startswith("def release_lock"):
            out.append("    return")
            marks["release"] += 1
        elif "# CLAIM-CHECK-THEN-WRITE" in line:
            indent = line[:len(line) - len(line.lstrip())]
            out.append("%stime.sleep(%s)" % (indent, sleep_seconds))
            marks["claim"] += 1
    if marks != {"acquire": 1, "release": 1, "claim": 1}:
        raise RuntimeError("doctoring markers not found exactly once: %r" % (marks,))
    return "\n".join(out) + "\n"


def contention_rounds(project, agents, rounds, stop_on_double, log, check_locks):
    """Each round: add a fresh task, then all agents claim it at once. Returns a summary dict.
    With a log, round 1's command lines and outputs are written to it."""
    summary = {"rounds": 0, "double_rounds": [], "max_winners": 0, "bad_rounds": [],
               "lock_leftovers": [], "first_codes": None}
    for n in range(1, rounds + 1):
        add_args = ["add", "--agent", agents[0], "--title", "Contested %d" % n,
                    "--desc", "round %d" % n, "--files", "r%d/x.py" % n, "--no-review"]
        code, out, err = run(project, *add_args)
        if log is not None and n == 1:
            log.say("Round 1, as run (every round repeats it with a fresh task; the claims start "
                    "together):")
            log.cmd(add_args, (code, out, err))
        if code != 0:
            summary["bad_rounds"].append((n, "add exit %d: %s" % (code, err.strip())))
            break
        task = out.strip().splitlines()[-1]
        claim_args = [["claim", task, "--agent", a] for a in agents]
        results = run_parallel(project, claim_args)
        if log is not None and n == 1:
            for args, result in zip(claim_args, results):
                log.cmd(args, result)
        codes = [r[0] for r in results]
        winners = [agents[i] for i, c in enumerate(codes) if c == 0]
        if n == 1:
            summary["first_codes"] = codes
            summary["first_refusal"] = next((r[2].strip() for r in results if r[0] == 2), "")
        summary["rounds"] = n
        summary["max_winners"] = max(summary["max_winners"], len(winners))
        if len(winners) > 1:
            summary["double_rounds"].append((n, task, winners, codes))
        elif len(winners) != 1 or any(c not in (0, 2) for c in codes):
            summary["bad_rounds"].append((n, "task %s codes %r" % (task, codes)))
        else:
            _, shown, _ = run(project, "show", task)
            if "Owner: %s" % winners[0] not in shown:
                summary["bad_rounds"].append((n, "task %s: winner %s not owner in show" %
                                              (task, winners[0])))
        if check_locks:
            left = leftover_locks(project)
            if left:
                summary["lock_leftovers"].append((n, left))
        if stop_on_double and summary["double_rounds"]:
            break
        if summary["bad_rounds"] or summary["lock_leftovers"]:
            break
    return summary


def join_agents(project, count, log=None):
    ids = []
    for i in range(count):
        result = run(project, "join", "--label", "sim-%d" % i)
        if log is not None:
            log.cmd(["join", "--label", "sim-%d" % i], result)
        ids.append(agent_id_from(result[1]))
    if not all(ids):
        raise RuntimeError("join failed: %r" % ids)
    return ids


def scenario_0(ctx):
    log = Log()
    tool_text = (TEAM_SRC / "team.py").read_text(encoding="utf-8")

    # Doctored copy: lock disabled, delay between the check and the write.
    log.say("Doctored copy of the tool (a second temp workspace): `    return` after the "
            "`# LOCK-ACQUIRE` line and after `def release_lock`, `time.sleep(S)` after "
            "`# CLAIM-CHECK-THEN-WRITE`. The real file is never touched.")
    doctored_rounds = 0
    detected = None
    for sleep_seconds in ("0.05", "0.2"):
        tmp = Path(tempfile.mkdtemp(prefix="team-sim-doctored-"))
        ctx.setdefault("tmp", []).append(tmp)
        ws, project = make_workspace(tmp / "ws")
        tool = ws / ".agents" / "team" / "team.py"
        tool.write_text(doctor(tool_text, sleep_seconds), encoding="utf-8")
        init_project(project, tool)
        agents = join_agents(project, CONTENDERS)
        summary = contention_rounds(project, agents, ROUNDS, True, None, False)
        doctored_rounds += summary["rounds"]
        log.say("doctored, sleep %s s: %d rounds of %d simultaneous claims; double-claim rounds: %s"
                % (sleep_seconds, summary["rounds"], CONTENDERS,
                   [(r, w) for r, _, w, _ in summary["double_rounds"]] or "none"))
        if summary["bad_rounds"]:
            log.say("  other anomalies: %r" % (summary["bad_rounds"][:3],))
        if summary["double_rounds"]:
            r, task, winners, codes = summary["double_rounds"][0]
            log.say("  round %d, task %s: %d agents all got exit 0 on `claim`: %s; exit codes %r"
                    % (r, task, len(winners), ", ".join(winners), codes))
            detected = (sleep_seconds, r, len(winners))
            break
        log.say("  no double claim seen; raising the delay and retrying once")
    log.check(detected is not None,
              "the doctored (lock-less) tool shows a double claim, so the test can detect the race"
              + (" (round %d, %d winners, delay %s s)" % (detected[1], detected[2], detected[0])
                 if detected else " (none in %d rounds)" % doctored_rounds))

    # Real tool.
    ws, project = build_workspace("team-sim-real-")
    ctx.setdefault("tmp", []).append(ws.parent)
    agents = join_agents(project, CONTENDERS)
    summary = contention_rounds(project, agents, ROUNDS, False, log, True)
    log.say("real tool: %d rounds of %d simultaneous claims; most winners in any round: %d; "
            "rounds with more than one winner: %d" % (summary["rounds"], CONTENDERS,
                                                      summary["max_winners"],
                                                      len(summary["double_rounds"])))
    log.say("  round 1 exit codes: %r; a loser's output: %s" % (summary["first_codes"],
                                                            summary.get("first_refusal", "")))
    log.check(summary["rounds"] == ROUNDS, "all %d real-tool rounds ran" % ROUNDS)
    log.check(not summary["double_rounds"], "no real-tool round had more than one winner")
    log.check(summary["max_winners"] == 1 and not summary["bad_rounds"],
              "every real-tool round had exactly one winner (exit 0) and the rest exit 2"
              + ("; anomalies: %r" % (summary["bad_rounds"][:3],) if summary["bad_rounds"] else ""))
    log.check(not summary["lock_leftovers"] and not leftover_locks(project),
              "no team/.lock* file left behind after any round"
              + ("; found %r" % (summary["lock_leftovers"][:3],) if summary["lock_leftovers"] else ""))
    return log.done()


# ---------------------------------------------------------------------------
# Scenarios 1-10
# ---------------------------------------------------------------------------


def scenario_1(ctx):
    log = Log()
    project = ctx["project"]
    log.say("Four agents run `join` at the same moment.")
    arglists = [["join", "--label", "Agent %s" % n] for n in "ABCD"]
    results = run_parallel(project, arglists)
    ids = [agent_id_from(r[1]) for r in results]
    log.say("Agents in this report: %s" % ", ".join("%s = %s" % (n, i) for n, i in zip("ABCD", ids)))
    for args, result in zip(arglists, results):
        log.cmd(args, result)
    log.check(all(r[0] == 0 for r in results), "all four joins exit 0")
    log.check(all(ids) and len(set(ids)) == 4, "four distinct agent IDs: %s" % ", ".join(map(str, ids)))
    log.check(not leftover_locks(project), "no team/.lock* file left behind")
    ctx["agents"] = ids
    return log.done()


def scenario_2(ctx):
    log = Log()
    project, (a, b, c, d) = ctx["project"], ctx["agents"]
    plan = [(a, "T001"), (b, "T002"), (c, "T004"), (d, "T005")]
    log.say("Each agent claims a different task at the same moment.")
    results = log.parallel(project, [["claim", t, "--agent", ag] for ag, t in plan])
    log.check(all(r[0] == 0 for r in results), "all four claims exit 0")
    for ag, t in plan:
        _, shown, _ = run(project, "show", t)
        log.check("Owner: %s" % ag in shown, "%s is held by %s" % (t, ag))
    log.check(not leftover_locks(project), "no team/.lock* file left behind")
    return log.done()


def scenario_3(ctx):
    log = Log()
    project, agents = ctx["project"], ctx["agents"]
    log.say("A sixth task is added (the five seeded ones are spoken for), then all four agents "
            "claim it at the same moment.")
    code, out, _ = log.step(project, "add", "--agent", agents[0], "--title", "Contested task",
                            "--desc", "Four agents want this", "--files", "src/f.py", "--no-review")
    task = out.strip().splitlines()[-1] if out.strip() else "T006"
    log.check(code == 0 and task == "T006", "added %s" % task)
    results = log.parallel(project, [["claim", task, "--agent", a] for a in agents])
    codes = [r[0] for r in results]
    winners = [agents[i] for i, c in enumerate(codes) if c == 0]
    log.check(len(winners) == 1, "exactly one winner (exit 0): %s" % (winners or "none"))
    log.check(sorted(codes) == [0, 2, 2, 2], "the other three were refused with exit 2: %r" % codes)
    if winners:
        _, shown, _ = log.step(project, "show", task)
        log.check("Owner: %s " % winners[0] in shown, "show %s names the winner %s as owner"
                  % (task, winners[0]))
    ctx["t6_owner"] = winners[0] if winners else None
    ctx["t6"] = task
    log.check(not leftover_locks(project), "no team/.lock* file left behind")
    return log.done()


def scenario_4(ctx):
    log = Log()
    project, (a, b, c, d) = ctx["project"], ctx["agents"]
    direct, broadcast = "direct note for B only", "broadcast note for everyone"
    log.step(project, "msg", "--agent", a, "--to", b, "--kind", "info", "--text", direct)
    log.step(project, "msg", "--agent", c, "--to", "all", "--kind", "warning", "--text", broadcast)
    _, inbox_b, _ = log.step(project, "inbox", "--agent", b)
    _, inbox_d, _ = log.step(project, "inbox", "--agent", d)
    log.check(direct in inbox_b and broadcast in inbox_b, "B receives the direct and the broadcast message")
    log.check(broadcast in inbox_d and direct not in inbox_d,
              "D receives the broadcast but not the message addressed to B")
    _, again, _ = log.step(project, "inbox", "--agent", b)
    log.check("No new messages" in again, "B's inbox is empty on the second read")
    return log.done()


def scenario_5(ctx):
    log = Log()
    project, d = ctx["project"], ctx["agents"][3]
    code, _, _ = log.step(project, "start", "T005", "--agent", d)
    log.check(code == 0, "start exits 0")
    code, out, _ = log.step(project, "done", "T005", "--agent", d, "--note", "built and checked")
    log.check(code == 0 and "T005 is done" in out, "done on the no-review task goes straight to done")
    _, shown, _ = log.step(project, "show", "T005")
    log.check("Status: done" in shown, "show T005 reports Status: done")
    return log.done()


def scenario_6(ctx):
    log = Log()
    project, agents = ctx["project"], ctx["agents"]
    d, owner, t6 = agents[3], ctx["t6_owner"], ctx["t6"]
    code, out, _ = log.step(project, "add", "--agent", d, "--title", "Follow-up", "--desc",
                            "Needs the contested task first", "--files", "src/g.py",
                            "--depends", t6, "--no-review")
    task = out.strip().splitlines()[-1] if out.strip() else "T007"
    log.check(code == 0, "follow-up %s created depending on %s" % (task, t6))
    code, out, err = log.step(project, "claim", task, "--agent", d)
    log.check(code == 2 and t6 in (out + err), "claim refused (exit 2) while %s is not done" % t6)
    log.step(project, "start", t6, "--agent", owner)
    code, out, _ = log.step(project, "done", t6, "--agent", owner, "--note", "contested work done")
    log.check(code == 0 and "%s is done." % t6 in out, "%s finished by %s" % (t6, owner))
    _, shown, _ = log.step(project, "show", t6)
    log.check("Status: done |" in shown, "show %s reports Status: done" % t6)
    code, out, _ = log.step(project, "claim", task, "--agent", d)
    log.check(code == 0, "claim succeeds once %s is done" % t6)
    log.step(project, "start", task, "--agent", d)
    code, _, _ = log.step(project, "done", task, "--agent", d, "--note", "follow-up done")
    log.check(code == 0, "follow-up finished")
    ctx["followup"] = task
    return log.done()


def scenario_7(ctx):
    log = Log()
    project, (a, b, c, d) = ctx["project"], ctx["agents"]
    note = "Finished the parser; next is the tests in src/b.py line 40; do not redo the parser."
    log.step(project, "start", "T002", "--agent", b)
    code, _, _ = log.step(project, "handoff", "T002", "--agent", b, "--note", note)
    log.check(code == 0, "owner hands off T002 with a note")
    code, out, _ = log.step(project, "leave", "--agent", b)
    log.check(code == 0, "owner leaves after the handoff")
    code, out, _ = log.step(project, "claim", "T002", "--agent", d, grep=("HANDOFF NOTE", "parser"))
    log.check(code == 0 and note in out, "another agent claims T002 and the output contains the note")
    return log.done()


def scenario_8(ctx):
    log = Log()
    project, (a, b, c, d) = ctx["project"], ctx["agents"]
    record_path = Path(project) / "team" / "agents" / ("%s.json" % c)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    config = json.loads((Path(project) / "team" / "config.json").read_text(encoding="utf-8"))
    minutes = float(config.get("stale_minutes", 30)) + 1
    old = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).replace(microsecond=0)
    record["last_seen"] = old.isoformat()
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    log.say("(the only direct edit of tool state in the whole run: %s's last_seen set to %s, "
            "%g minutes ago: stale_minutes from team/config.json plus one)"
            % (c, record["last_seen"], minutes))
    code, out, _ = log.step(project, "stale")
    log.check(code == 0 and c in out and "T004" in out, "stale lists %s and its task T004" % c)
    code, out, _ = log.step(project, "reclaim", "T004", "--agent", a, grep=("Reclaimed", "Last 10"))
    log.check(code == 0 and "Reclaimed from %s" % c in out, "reclaim succeeds")
    log.check("Last 10 log entries" in out and "claimed" in out,
              "reclaim prints the log of the task")
    return log.done()


def scenario_9(ctx):
    log = Log()
    project, (a, b, c, d) = ctx["project"], ctx["agents"]
    log.say("D holds T002 (src/b.py). A tries to register that path on its own task T001.")
    before = registered_paths(run(project, "show", "T001")[1])
    code, out, err = log.step(project, "files", "add", "T001", "--agent", a, "src/b.py")
    log.check(code == 2, "files add of another live task's path exits 2")
    after = registered_paths(run(project, "show", "T001")[1])
    log.check(after == before and before, "T001 still registers only %s" % (after,))
    code, out, _ = log.step(project, "owner", "src/b.py")
    log.check(code == 0 and d in out and "T002" in out, "owner names %s and T002" % d)
    code, out, _ = log.step(project, "files", "add", "T001", "--agent", a, "docs/free.md")
    log.check(code == 0, "a path nobody holds can be registered (exit 0)")
    return log.done()


def scenario_10(ctx):
    log = Log()
    project, (a, b, c, d) = ctx["project"], ctx["agents"]
    code, out, _ = log.step(project, "complete")
    log.check(code == 2, "complete exits 2 while work remains")
    log.step(project, "start", "T001", "--agent", a)
    code, out, _ = log.step(project, "done", "T001", "--agent", a, "--note", "ready for review")
    log.check(code == 0 and "review" in out, "done on a review-required task goes to review")
    code, out, err = log.step(project, "review", "T001", "--agent", a, "--approve", "--note", "mine")
    log.check(code == 2 and "owner" in err, "the owner cannot review their own task (exit 2, "
              "and the reason says why: owner)")
    code, out, _ = log.step(project, "review", "T001", "--agent", d, "--approve", "--note", "looks good")
    log.check(code == 0 and "approved" in out, "another agent approves; T001 is done")
    # Finish everything else.
    log.say("Remaining work is finished by the agents (T002 via review, T003, T004).")
    log.step(project, "start", "T002", "--agent", d)
    log.step(project, "done", "T002", "--agent", d, "--note", "tests written")
    code, _, _ = log.step(project, "review", "T002", "--agent", a, "--approve", "--note", "ok")
    log.check(code == 0, "T002 reviewed and done")
    log.step(project, "start", "T004", "--agent", a)
    log.step(project, "done", "T004", "--agent", a, "--note", "done after reclaim")
    code, _, _ = log.step(project, "claim", "T003", "--agent", d)
    log.check(code == 0, "T003 is claimable now that T001 is done")
    log.step(project, "start", "T003", "--agent", d)
    log.step(project, "done", "T003", "--agent", d, "--note", "done")
    code, out, _ = log.step(project, "complete")
    log.check(code == 2 and "unchecked Definition-of-done boxes: 2" in out,
              "complete still exits 2: all tasks done but two boxes are unticked")
    log.step(project, "decide", "--agent", d, "--title", "Tick Definition of done",
             "--text", "Both items are met; ticking the boxes in team/PLAN.md.")
    plan = Path(project) / "team" / "PLAN.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8")
    log.say("(boxes ticked in team/PLAN.md, the one hand edit protocol allows, after the decide)")
    code, out, _ = log.step(project, "complete")
    log.check(code == 0 and "COMPLETE" in out, "complete exits 0 and prints COMPLETE")
    return log.done()


SCENARIOS = [
    ("Scenario 0 - lock fail-first proof (doctored tool must double-claim, real tool must not)", scenario_0),
    ("Scenario 1 - four agents join at once", scenario_1),
    ("Scenario 2 - each agent claims a different task", scenario_2),
    ("Scenario 3 - four agents claim one task at once", scenario_3),
    ("Scenario 4 - messages: one direct, one to all", scenario_4),
    ("Scenario 5 - complete work on a no-review task", scenario_5),
    ("Scenario 6 - follow-up task blocked by its dependency", scenario_6),
    ("Scenario 7 - handoff then leave, another agent picks up", scenario_7),
    ("Scenario 8 - stale owner recovered with reclaim", scenario_8),
    ("Scenario 9 - do not touch another agent's active files", scenario_9),
    ("Scenario 10 - review gate and project completion", scenario_10),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description="Simulate several agents using the team tool.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="where to write the report")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc).replace(microsecond=0)
    ctx = {}
    tmp_roots = []
    try:
        return _simulate(args, started, ctx, tmp_roots)
    finally:
        for root in tmp_roots + ctx.get("tmp", []):
            shutil.rmtree(str(root), ignore_errors=True)


def _simulate(args, started, ctx, tmp_roots):
    sections = []

    # Shared workspace for scenarios 1-10: init, plan, five tasks added by the user.
    workspace, project = build_workspace("team-sim-main-")
    tmp_roots.append(workspace.parent)
    ctx["project"] = project
    seeding = seed_plan_and_tasks(project, "user")
    seed_ok = all(r[1][0] == 0 for r in seeding)

    failures = 0
    for title, func in SCENARIOS:
        if func is not scenario_0 and not seed_ok:
            passed, lines = False, ["seeding the plan and tasks failed: %r" % (seeding,)]
        else:
            try:
                passed, lines = func(ctx)
            except Exception:  # a script crash is a FAIL, not a silent stop
                passed = False
                lines = ["script error:"] + ["    " + l for l in traceback.format_exc().splitlines()[-8:]]
        reasons = [l.strip()[len("FAILED: "):] for l in lines if l.strip().startswith("FAILED: ")]
        if passed:
            result = "RESULT: PASS"
        else:
            failures += 1
            result = "RESULT: FAIL — %s" % ("; ".join(reasons) if reasons else lines[-1].strip())
        print("%s: %s" % (title, "PASS" if passed else "FAIL"), flush=True)
        sections.append((title, lines, result))

    body = ["# Team tool simulation — %s" % started.strftime("%Y-%m-%d %H:%M:%SZ"), "",
            "Seeded plan and tasks (main workspace): T001 src/a.py (review), T002 src/b.py (review), "
            "T003 src/c.py (depends on T001, no review), T004 src/d.py, T005 src/e.py (no review). "
            "Scenario 3 adds T006, scenario 6 adds T007.", ""]
    for title, lines, result in sections:
        body.append("## %s" % title)
        body.append("")
        body.append("```")
        body.extend(lines)
        body.append("```")
        body.append("")
        body.append(result)
        body.append("")
    body.append("ALL PASS" if failures == 0 else "FAILURES: %d" % failures)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(body) + "\n", encoding="utf-8")
    print("ALL PASS" if failures == 0 else "FAILURES: %d" % failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
