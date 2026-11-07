"""Lifecycle tests for team.py: done, review, handoff, release, block, unblock, stale, reclaim,
files add, owner, leave, skills, skill register, complete.
Run from .agents/team: python3 -m unittest tests.test_lifecycle -v

Every test works in its own temporary fake workspace made by helpers.make_workspace; nothing is
written under the real .agents/team/.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402


class LifecycleTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="team-life-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.workspace, self.project = helpers.make_workspace(Path(tmp))
        self.tool_path = self.workspace / ".agents" / "team" / "team.py"
        self.tool = helpers.load_tool(self.tool_path)
        self.team = self.project / "team"
        saved = {k: os.environ.get(k) for k in ("TEAM_DIR", "TEAM_AGENT")}
        self.addCleanup(self._restore_env, saved)
        for key in saved:
            os.environ.pop(key, None)
        old = os.getcwd()
        os.chdir(str(self.project))
        try:
            code, _, err = helpers.run(self.tool, "init")
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, err)
        os.environ["TEAM_DIR"] = str(self.team)

    @staticmethod
    def _restore_env(saved):
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # -- helpers --
    def main(self, *argv):
        return helpers.run(self.tool, *argv)

    def ok(self, *argv):
        code, out, err = self.main(*argv)
        self.assertEqual(code, 0, "%s -> %s %s" % (argv, out, err))
        return out

    def refused(self, *argv):
        code, out, err = self.main(*argv)
        self.assertEqual(code, 2, "%s -> %s %s" % (argv, out, err))
        self.assertTrue(err.startswith("refused: "), err)
        return err

    def join(self, *ids):
        for agent in ids:
            self.ok("join", "--agent", agent)

    def add(self, title="Work", *extra):
        return self.ok("add", "--agent", "user", "--title", title, "--desc", "d", *extra).strip()

    def to_in_progress(self, agent, *extra_add):
        """Add a task, claim and start it as `agent`; return its ID."""
        task_id = self.add("Work", *extra_add)
        self.ok("claim", task_id, "--agent", agent)
        self.ok("start", task_id, "--agent", agent)
        return task_id

    def task(self, task_id):
        return json.loads((self.team / "tasks" / ("%s.json" % task_id)).read_text())

    def agent(self, agent_id):
        return json.loads((self.team / "agents" / ("%s.json" % agent_id)).read_text())

    def set_last_seen(self, agent_id, minutes_ago):
        path = self.team / "agents" / ("%s.json" % agent_id)
        record = json.loads(path.read_text())
        stamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        record["last_seen"] = stamp.replace(microsecond=0).isoformat()
        path.write_text(json.dumps(record, indent=2))

    def lines(self, name):
        text = (self.team / name).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def view(self, name):
        return (self.team / name).read_text(encoding="utf-8")

    def spawn_all(self, target, arglists):
        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(len(arglists))
        queue = ctx.Queue()
        procs = [ctx.Process(target=target, args=tuple(a) + (barrier, queue)) for a in arglists]
        for p in procs:
            p.start()
        results = [queue.get(timeout=240) for _ in procs]
        for p in procs:
            p.join(timeout=30)
            self.assertFalse(p.is_alive(), "worker process hung")
        return results


def reclaim_args(tool_path, team_dir, agent):
    return (str(tool_path), str(team_dir), ["reclaim", "T001", "--agent", agent])


def write_skill(root, folder, text):
    path = Path(root) / ".agents" / "skills" / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(text, encoding="utf-8")


GOOD_SKILL = ("---\nname: %s\ndescription: Does a thing. Use when asked.\n---\n\n# Title\n\n"
              "## Exit criteria\n\nDone.\n\n## When uncertain\n\nAsk.\n")


class ReviewTests(LifecycleTestCase):
    def test_done_review_approve_done(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "built and tested")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("review", "a1"))
        self.assertEqual(self.agent("a1")["current_task"], task_id)
        self.assertIn("- %s " % task_id, self.view("BOARD.md").split("### review")[1].split("###")[0])
        self.ok("review", task_id, "--agent", "a2", "--approve", "--note", "looks right")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("done", None))
        self.assertEqual(task["review"]["verdict"], "approved")
        self.assertEqual(task["review"]["by"], "a2")
        self.assertIsNone(self.agent("a1")["current_task"])
        self.assertEqual([e["event"] for e in task["log"]],
                         ["created", "claimed", "started", "review requested", "approved"])

    def test_done_without_review_goes_to_done(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "trivial")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("done", None))
        self.assertIsNone(self.agent("a1")["current_task"])

    def test_done_from_claimed_allowed_and_wrong_state_refused(self):
        self.join("a1")
        task_id = self.add()
        self.refused("done", task_id, "--agent", "a1", "--note", "x")  # available, not owned
        self.ok("claim", task_id, "--agent", "a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")  # claimed -> review
        err = self.refused("done", task_id, "--agent", "a1", "--note", "again")
        self.assertIn("review", err)

    def test_done_by_non_owner_names_owner(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        err = self.refused("done", task_id, "--agent", "a2", "--note", "x")
        self.assertIn("a1", err)
        self.assertIn("next --agent a2", err)

    def test_reject_makes_available_with_handoff_and_message(self):
        self.join("a1", "a2", "a3")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        self.ok("review", task_id, "--agent", "a2", "--reject", "--note", "tests missing")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("available", None))
        self.assertEqual(task["handoff"]["by"], "a2")
        self.assertEqual(task["handoff"]["text"], "tests missing")
        self.assertEqual(task["review"]["verdict"], "rejected")
        self.assertIsNone(self.agent("a1")["current_task"])
        inbox = self.ok("inbox", "--agent", "a1")
        self.assertIn("tests missing", inbox)
        self.assertIn(task_id, inbox)
        self.assertIn("tests missing", self.ok("claim", task_id, "--agent", "a3"))

    def test_reject_needs_note(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        code, _, err = self.main("review", task_id, "--agent", "a2", "--reject")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.task(task_id)["status"], "review")

    def test_review_needs_exactly_one_verdict(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        self.assertEqual(self.main("review", task_id, "--agent", "a2")[0], 1)
        self.assertEqual(self.main("review", task_id, "--agent", "a2", "--approve",
                                   "--reject", "--note", "x")[0], 1)

    def test_owner_cannot_review_own_task(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        self.refused("review", task_id, "--agent", "a1", "--approve")
        self.assertEqual(self.task(task_id)["status"], "review")

    def test_user_can_review(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        self.assertIn("1 task awaits review by another agent or the user "
                      "(team.py review %s --agent user --approve)" % task_id,
                      self.ok("next", "--agent", "a1"))
        self.ok("review", task_id, "--agent", "user", "--approve", "--note", "checked")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["review"]["by"]), ("done", "user"))

    def test_review_by_unjoined_agent_refused(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        err = self.refused("review", task_id, "--agent", "ghost", "--approve")
        self.assertIn("join", err)

    def test_review_of_task_not_in_review_refused(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.refused("review", task_id, "--agent", "a2", "--approve")


class HandoffTests(LifecycleTestCase):
    def test_handoff_then_claim_prints_note(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.ok("handoff", task_id, "--agent", "a1", "--note", "parser done, tests left")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("available", None))
        self.assertEqual(task["handoff"]["text"], "parser done, tests left")
        self.assertEqual(task["log"][-1]["event"], "handoff")
        self.assertIsNone(self.agent("a1")["current_task"])
        out = self.ok("claim", task_id, "--agent", "a2")
        self.assertIn("HANDOFF NOTE from a1", out)
        self.assertIn("parser done, tests left", out)

    def test_handoff_from_claimed_and_blocked(self):
        self.join("a1")
        task_id = self.add()
        self.ok("claim", task_id, "--agent", "a1")
        self.ok("handoff", task_id, "--agent", "a1", "--note", "from claimed")
        self.ok("claim", task_id, "--agent", "a1")
        self.ok("start", task_id, "--agent", "a1")
        self.ok("block", task_id, "--agent", "a1", "--reason", "need an answer")
        self.ok("handoff", task_id, "--agent", "a1", "--note", "from blocked")
        self.assertEqual(self.task(task_id)["status"], "available")

    def test_handoff_note_file(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        note = self.project / "note.txt"
        note.write_text("long note\nsecond line\n", encoding="utf-8")
        self.ok("handoff", task_id, "--agent", "a1", "--note-file", str(note))
        self.assertEqual(self.task(task_id)["handoff"]["text"], "long note\nsecond line")
        code, _, err = self.main("handoff", task_id, "--agent", "a1", "--note-file",
                                 str(self.project / "missing.txt"))
        self.assertEqual(code, 1, err)

    def test_handoff_needs_a_note(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.assertEqual(self.main("handoff", task_id, "--agent", "a1")[0], 1)
        self.assertEqual(self.main("handoff", task_id, "--agent", "a1", "--note", "  ")[0], 1)
        self.assertEqual(self.task(task_id)["status"], "in_progress")

    def test_handoff_by_non_owner_refused(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        err = self.refused("handoff", task_id, "--agent", "a2", "--note", "mine now")
        self.assertIn("a1", err)
        self.assertEqual(self.task(task_id)["owner"], "a1")

    def test_handoff_of_task_in_review_refused(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        self.refused("handoff", task_id, "--agent", "a1", "--note", "x")
        self.refused("release", task_id, "--agent", "a1")

    def test_release_uses_note_released(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("release", task_id, "--agent", "a1")
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("available", None))
        self.assertEqual(task["handoff"]["text"], "released")


class BlockTests(LifecycleTestCase):
    def test_block_opens_question_and_unblock_resolves_it(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("block", task_id, "--agent", "a1", "--reason", "which database?")
        task = self.task(task_id)
        self.assertEqual(task["status"], "blocked")
        question = json.loads((self.team / "questions" / "Q001.json").read_text())
        self.assertEqual((question["task"], question["by"], question["status"]),
                         (task_id, "a1", "open"))
        self.assertIn("which database?", question["text"])
        self.assertIn("which database?", self.view("QUESTIONS.md"))
        self.ok("unblock", task_id, "--agent", "a1")
        self.assertEqual(self.task(task_id)["status"], "in_progress")
        question = json.loads((self.team / "questions" / "Q001.json").read_text())
        self.assertEqual(question["status"], "resolved")

    def test_unblock_after_user_answered_keeps_answer(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("block", task_id, "--agent", "a1", "--reason", "which database?")
        self.ok("resolve", "Q001", "--agent", "user", "--text", "sqlite")
        self.ok("unblock", task_id, "--agent", "a1")
        question = json.loads((self.team / "questions" / "Q001.json").read_text())
        self.assertEqual(question["resolution"], "sqlite")

    def test_block_and_unblock_wrong_state_or_owner_refused(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.refused("unblock", task_id, "--agent", "a1")  # not blocked
        self.refused("block", task_id, "--agent", "a2", "--reason", "x")  # not owner
        self.ok("block", task_id, "--agent", "a1", "--reason", "x")
        self.refused("block", task_id, "--agent", "a1", "--reason", "again")  # already blocked
        self.refused("unblock", task_id, "--agent", "a2")
        self.assertEqual(self.main("block", task_id, "--agent", "a1")[0], 1)  # --reason missing


class LeaveTests(LifecycleTestCase):
    def test_leave_refused_while_owning_live_task(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        err = self.refused("leave", "--agent", "a1")
        self.assertIn(task_id, err)
        self.assertIn("handoff", err)
        self.assertEqual(self.agent("a1")["status"], "active")
        self.ok("handoff", task_id, "--agent", "a1", "--note", "stopping")
        self.ok("leave", "--agent", "a1")
        self.assertEqual(self.agent("a1")["status"], "left")
        self.refused("next", "--agent", "a1")  # a left agent is unknown to commands

    def test_leave_refused_for_claimed_and_blocked_tasks(self):
        self.join("a1")
        task_id = self.add()
        self.ok("claim", task_id, "--agent", "a1")
        self.refused("leave", "--agent", "a1")
        self.ok("start", task_id, "--agent", "a1")
        self.ok("block", task_id, "--agent", "a1", "--reason", "x")
        self.refused("leave", "--agent", "a1")

    def test_leave_allowed_with_task_in_review(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--files", "src/a.py")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")
        self.ok("leave", "--agent", "a1")
        self.assertEqual(self.task(task_id)["status"], "review")
        self.assertIn(task_id, self.ok("owner", "src/a.py"))
        self.assertEqual(self.ok("doctor").strip(), "OK")
        self.ok("review", task_id, "--agent", "user", "--approve")
        self.assertEqual(self.task(task_id)["status"], "done")

    def test_left_agent_can_join_again_with_same_id(self):
        self.join("a1")
        self.ok("leave", "--agent", "a1")
        self.ok("join", "--agent", "a1")
        self.assertEqual(self.agent("a1")["status"], "active")


class ReclaimTests(LifecycleTestCase):
    def test_reclaim_refused_when_owner_fresh(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        err = self.refused("reclaim", task_id, "--agent", "a2")
        self.assertIn("a1", err)
        self.assertEqual(self.task(task_id)["owner"], "a1")

    def test_reclaim_allowed_when_owner_stale(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.ok("handoff", task_id, "--agent", "a1", "--note", "first stop")
        self.ok("claim", task_id, "--agent", "a1")
        self.set_last_seen("a1", 29)
        self.refused("reclaim", task_id, "--agent", "a2")
        self.set_last_seen("a1", 31)
        out = self.ok("reclaim", task_id, "--agent", "a2")
        self.assertIn("first stop", out)  # previous handoff note
        self.assertIn("handoff", out)  # log entries
        self.assertIn("Claimed %s" % task_id, out)
        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("claimed", "a2"))
        self.assertEqual(task["log"][-1]["event"], "reclaimed from a1")
        self.assertEqual(task["log"][-1]["agent"], "a2")
        self.assertEqual(self.agent("a2")["current_task"], task_id)
        self.assertIsNone(self.agent("a1")["current_task"])
        self.assertIn("reclaimed", self.ok("inbox", "--agent", "a1"))

    def test_reclaim_prints_last_ten_log_entries(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        for i in range(12):
            self.ok("block" if i % 2 == 0 else "unblock", task_id, "--agent", "a1",
                    *(["--reason", "r%d" % i] if i % 2 == 0 else []))
        self.set_last_seen("a1", 40)
        out = self.ok("reclaim", task_id, "--agent", "a2")
        listed = [l for l in out.split("Last 10 log entries:")[1].split("Claimed")[0].splitlines()
                  if l.strip()]
        self.assertEqual(len(listed), 10)

    def test_reclaim_allowed_when_owner_left(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        path = self.team / "agents" / "a1.json"
        record = json.loads(path.read_text())
        record["status"] = "left"
        path.write_text(json.dumps(record))
        self.ok("reclaim", task_id, "--agent", "a2")
        self.assertEqual(self.task(task_id)["owner"], "a2")

    def test_returning_agent_learns_it_lost_the_task(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.set_last_seen("a1", 45)
        self.ok("reclaim", task_id, "--agent", "a2")
        for argv in (("done", task_id, "--agent", "a1", "--note", "x"),
                     ("start", task_id, "--agent", "a1"),
                     ("handoff", task_id, "--agent", "a1", "--note", "x"),
                     ("files", "add", task_id, "--agent", "a1", "src/x.py")):
            err = self.refused(*argv)
            self.assertIn("a2", err)
            self.assertIn("reclaimed from a1", err)
            self.assertIn("next --agent a1", err)

    def test_reclaim_refused_for_available_done_review_and_own_tasks(self):
        self.join("a1", "a2")
        task_id = self.add()
        self.refused("reclaim", task_id, "--agent", "a2")  # available
        self.ok("claim", task_id, "--agent", "a1")
        self.refused("reclaim", task_id, "--agent", "a1")  # already mine
        self.ok("start", task_id, "--agent", "a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        self.set_last_seen("a1", 90)
        self.refused("reclaim", task_id, "--agent", "a2")  # review
        self.ok("review", task_id, "--agent", "user", "--approve")
        self.refused("reclaim", task_id, "--agent", "a2")  # done
        self.assertEqual(self.main("reclaim", "T099", "--agent", "a2")[0], 1)  # missing

    def test_reclaim_by_unjoined_agent_refused(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.set_last_seen("a1", 90)
        err = self.refused("reclaim", task_id, "--agent", "ghost")
        self.assertIn("join", err)

    def test_stale_lists_stale_agents_and_their_tasks(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.assertIn("No stale agents", self.ok("stale"))
        self.set_last_seen("a1", 31)
        out = self.ok("stale")
        self.assertIn("a1", out)
        self.assertIn(task_id, out)
        self.assertNotIn("a2", out)
        out = self.ok("status")
        self.assertIn("[OWNER STALE]", out)

    def test_concurrent_reclaim_one_winner(self):
        # a0 is the stale owner and does not race: its own command would refresh it (correct).
        self.join(*("a%d" % i for i in range(9)))
        task_id = self.to_in_progress("a0")
        self.assertEqual(task_id, "T001")
        self.set_last_seen("a0", 60)
        results = self.spawn_all(helpers.main_worker, [
            reclaim_args(self.tool_path, self.team, "a%d" % i) for i in range(1, 9)])
        codes = sorted(code for _, code, _, _ in results)
        winners = [argv[3] for argv, code, _, _ in results if code == 0]
        self.assertEqual(len(winners), 1, "codes %s" % codes)
        self.assertEqual(codes, [0] + [2] * 7)
        task = self.task("T001")
        self.assertEqual(task["owner"], winners[0])
        events = [e["event"] for e in task["log"]]
        self.assertEqual(sum(1 for e in events if e.startswith("reclaimed from")), 1, events)
        self.assertFalse((self.team / ".lock").exists())


class FilesTests(LifecycleTestCase):
    def test_files_add_registers_paths(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--files", "src/a.py")
        out = self.ok("files", "add", task_id, "--agent", "a1", "src/b.py", "docs")
        self.assertIn("src/b.py", out)
        self.assertEqual(self.task(task_id)["files"], ["src/a.py", "src/b.py", "docs"])
        self.ok("files", "add", task_id, "--agent", "a1", "src/b.py")  # no duplicate
        self.assertEqual(self.task(task_id)["files"], ["src/a.py", "src/b.py", "docs"])

    def test_files_add_overlap_refused(self):
        self.join("a1", "a2")
        t1 = self.to_in_progress("a1", "--files", "src")
        t2 = self.to_in_progress("a2", "--files", "docs")
        err = self.refused("files", "add", t2, "--agent", "a2", "src/deep/x.py")
        self.assertIn(t1, err)
        self.assertIn("a1", err)
        self.assertEqual(self.task(t2)["files"], ["docs"])
        code, _, err = self.main("files", "add", t2, "--agent", "a2", "ok.py", "src/*.py")
        self.assertEqual(code, 1)
        self.assertIn("wildcard", err.lower())
        self.assertEqual(self.task(t2)["files"], ["docs"])  # all or nothing

    def test_files_add_by_non_owner_refused(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        err = self.refused("files", "add", task_id, "--agent", "a2", "x.py")
        self.assertIn("a1", err)

    def test_files_add_needs_a_live_task(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        self.refused("files", "add", task_id, "--agent", "a1", "x.py")

    def test_owner_reports_live_owner_or_unowned(self):
        self.join("a1")
        self.add("Parked", "--files", "lib/parked.py")  # available: not owned
        task_id = self.to_in_progress("a1", "--files", "src")
        out = self.ok("owner", "src/app/main.py")
        self.assertIn(task_id, out)
        self.assertIn("a1", out)
        self.assertEqual(self.ok("owner", "lib/parked.py").strip(), "unowned")
        self.assertEqual(self.ok("owner", "other/file.py").strip(), "unowned")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")  # review reserves its paths
        out = self.ok("owner", "src/app/main.py")
        self.assertIn(task_id, out)
        self.assertIn("review", out)


class SkillsTests(LifecycleTestCase):
    def test_skills_outside_project_lists_the_running_tools_workspace(self):  # round 2, item 3
        write_skill(self.workspace, "ws-skill", GOOD_SKILL % "ws-skill")
        lone = Path(tempfile.mkdtemp(prefix="team-lone-")).resolve()
        self.addCleanup(shutil.rmtree, str(lone), True)
        os.environ.pop("TEAM_DIR")
        old = os.getcwd()
        os.chdir(str(lone))
        try:
            code, _, err = helpers.run(self.tool, "init")  # shim falls back to the workspace tool
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, err)
        write_skill(lone, "mine", GOOD_SKILL % "mine")
        env = {k: v for k, v in os.environ.items() if k not in ("TEAM_DIR", "TEAM_AGENT")}
        result = subprocess.run([sys.executable, "team/team.py", "skills"], cwd=str(lone), env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[workspace] ws-skill: Does a thing. Use when asked.", result.stdout)
        self.assertIn("[project] mine:", result.stdout)
        self.assertEqual(result.stdout.count("ws-skill"), 1)

    def test_skills_lists_workspace_and_project_skills(self):
        write_skill(self.workspace, "ws-skill", GOOD_SKILL % "ws-skill")
        write_skill(self.project, "proj-skill", GOOD_SKILL % "proj-skill")
        out = self.ok("skills")
        self.assertIn("[workspace] ws-skill: Does a thing. Use when asked.", out)
        self.assertIn("[project] proj-skill: Does a thing. Use when asked.", out)

    def test_skills_marks_invalid_skills_without_crashing(self):
        write_skill(self.project, "no-front", "# no frontmatter here\n")
        write_skill(self.project, "bad-front", "---\nname: bad-front\njust some words\n---\n")
        (self.project / ".agents" / "skills" / "empty-dir").mkdir(parents=True)
        write_skill(self.project, "good", GOOD_SKILL % "good")
        out = self.ok("skills")
        self.assertIn("[project] good:", out)
        for name in ("no-front", "bad-front", "empty-dir"):
            self.assertRegex(out, r"\[invalid\] %s:" % name)

    def test_skills_without_any_skills(self):
        self.assertIn("No skills found", self.ok("skills"))

    def test_skills_standalone_project_has_no_workspace_section(self):
        write_skill(self.workspace, "ws-skill", GOOD_SKILL % "ws-skill")
        lone = Path(tempfile.mkdtemp(prefix="team-lone-"))
        self.addCleanup(shutil.rmtree, str(lone), True)
        tool = self.tool_path
        (lone / "proj" / "team").mkdir(parents=True)
        shutil.copy2(str(tool), str(lone / "proj" / "team" / "team.py"))  # the standalone copy
        for name in ("config.default.json",):
            shutil.copy2(str(tool.parent / name), str(lone / "proj" / "team" / "config.json"))
        os.environ["TEAM_DIR"] = str(lone / "proj" / "team")
        write_skill(lone / "proj", "mine", GOOD_SKILL % "mine")
        code, out, err = helpers.run(helpers.load_tool(lone / "proj" / "team" / "team.py"), "skills")
        self.assertEqual(code, 0, err)
        self.assertIn("[project] mine:", out)
        self.assertNotIn("ws-skill", out)

    def test_skill_register_ok_announces(self):
        self.join("a1")
        write_skill(self.project, "mine", GOOD_SKILL % "mine")
        self.ok("skill", "register", "mine", "--agent", "a1")
        decision = self.lines("decisions.jsonl")[-1]
        self.assertEqual((decision["title"], decision["by"]), ("Skill added: mine", "a1"))
        message = self.lines("messages.jsonl")[-1]
        self.assertEqual((message["to"], message["kind"]), ("all", "info"))
        self.assertIn("mine", message["text"])

    def test_skill_register_rejects_missing_when_uncertain(self):
        self.join("a1")
        text = GOOD_SKILL % "mine"
        write_skill(self.project, "mine", text.replace("## When uncertain\n\nAsk.\n", ""))
        err = self.refused("skill", "register", "mine", "--agent", "a1")
        self.assertIn("When uncertain", err)
        self.assertEqual(self.lines("decisions.jsonl"), [])
        self.assertEqual(self.lines("messages.jsonl"), [])

    def test_skill_register_rejects_missing_exit_criteria(self):
        self.join("a1")
        write_skill(self.project, "mine",
                    (GOOD_SKILL % "mine").replace("## Exit criteria\n\nDone.\n\n", ""))
        self.assertIn("Exit criteria", self.refused("skill", "register", "mine", "--agent", "a1"))

    def test_skill_register_rejects_name_mismatch_and_extra_keys(self):
        self.join("a1")
        write_skill(self.project, "mine", GOOD_SKILL % "other")
        self.assertIn("differs", self.refused("skill", "register", "mine", "--agent", "a1"))
        write_skill(self.project, "mine",
                    (GOOD_SKILL % "mine").replace("---\n\n#", "version: 2\n---\n\n#", 1))
        self.assertIn("exactly name and description",
                      self.refused("skill", "register", "mine", "--agent", "a1"))

    def test_skill_register_refuses_non_utf8_file(self):
        self.join("a1")
        folder = self.project / ".agents" / "skills" / "mine"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_bytes(b"---\nname: mine\n\xff\xfe\n---\n")
        self.assertIn("UTF-8", self.refused("skill", "register", "mine", "--agent", "a1"))

    def test_skill_register_rejects_missing_file(self):
        self.join("a1")
        self.refused("skill", "register", "nope", "--agent", "a1")


class CompleteTests(LifecycleTestCase):
    def finish_plan(self):
        plan = self.team / "PLAN.md"
        plan.write_text("""# Example Project

## Goal
The example project succeeds when its parser handles the requested inputs.

## Scope
Implement the parser and its focused tests.

## Non-goals
Do not add unrelated features.

## Architecture notes
Follow the existing module boundaries.

## How to verify
Run the parser unit tests from the project folder.

## Definition of done
- [x] The parser tests pass.

## Milestones
Initial implementation.
""", encoding="utf-8")

    def test_complete_exit_2_without_tasks(self):
        self.finish_plan()
        code, out, _ = self.main("complete")
        self.assertEqual(code, 2)
        self.assertNotIn("COMPLETE\n", out.replace("NOT COMPLETE", ""))

    def test_complete_exit_2_with_open_task(self):
        self.join("a1")
        self.finish_plan()
        task_id = self.to_in_progress("a1", "--no-review")
        code, out, _ = self.main("complete")
        self.assertEqual(code, 2)
        self.assertIn(task_id, out)
        self.assertIn("in_progress 1", out)
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        self.assertEqual(self.ok("complete").strip(), "COMPLETE")

    def test_complete_exit_2_with_unchecked_box(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        code, out, _ = self.main("complete")  # the template still has an unchecked box
        self.assertEqual(code, 2)
        self.assertIn("unchecked Definition-of-done boxes: 1", out)
        self.finish_plan()
        self.assertEqual(self.ok("complete").strip(), "COMPLETE")

    def test_complete_rejects_checked_template_criterion(self):
        self.join("a1")
        self.finish_plan()
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        plan = self.team / "PLAN.md"
        plan.write_text(plan.read_text().replace("The parser tests pass.",
                                                 "<Example: every task is done and checks pass.>"),
                        encoding="utf-8")
        code, out, _ = self.main("complete")
        self.assertEqual(code, 2)
        self.assertIn("template", out.lower())

    def test_complete_accepts_real_criterion_with_replace_verb(self):
        self.join("a1")
        self.finish_plan()
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        plan = self.team / "PLAN.md"
        plan.write_text(plan.read_text().replace("The parser tests pass.",
                                                 "Replace the obsolete labels."),
                        encoding="utf-8")
        self.assertEqual(self.ok("complete").strip(), "COMPLETE")

    def test_complete_rejects_missing_malformed_or_empty_criteria(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        plan = self.team / "PLAN.md"
        for text, expected in (
                ("# Example Project\n## Goal\nA goal.\n", "Definition of done"),
                ("# Example Project\n## Definition of done\n- [x] \n", "empty"),
                ("## Definition of done\n- [x] TODO", "template"),
                ("## Definition of done\n- [x] TBD", "template"),
                ("## Definition of done\n~~~md\n- [x] Demo loads\n~~~", "real"),
                ("# Example Project\n## Definition of done\n- [?] Do the thing.\n",
                 "malformed")):
            with self.subTest(expected=expected):
                plan.write_text(text, encoding="utf-8")
                code, out, _ = self.main("complete")
                self.assertEqual(code, 2)
                self.assertIn(expected.lower(), out.lower())

    def test_complete_ignores_boxes_outside_definition_of_done(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        self.finish_plan()
        plan = self.team / "PLAN.md"
        plan.write_text(plan.read_text() + "\n- [ ] a later milestone item\n", encoding="utf-8")
        self.assertEqual(self.ok("complete").strip(), "COMPLETE")

    def test_complete_ignores_fenced_code_and_subheadings(self):
        self.join("a1")
        task_id = self.to_in_progress("a1", "--no-review")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        plan = self.team / "PLAN.md"
        text = plan.read_text().replace("- [ ]", "- [x]").replace(
            "## Milestones", "### Release checks\n```\n- [ ] example box in a fence\n"
            "## Not a section\n```\n- [ ] real box after the fence\n\n## Milestones")
        plan.write_text(text, encoding="utf-8")
        code, out, _ = self.main("complete")
        self.assertEqual(code, 2, out)
        self.assertIn("unchecked Definition-of-done boxes: 1", out)
        self.assertIn("real box after the fence", out)
        self.assertNotIn("example box in a fence", out)

    def test_complete_review_task_is_not_done(self):
        self.join("a1")
        self.finish_plan()
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "x")
        self.assertEqual(self.main("complete")[0], 2)
        self.ok("review", task_id, "--agent", "user", "--approve")
        self.assertEqual(self.ok("complete").strip(), "COMPLETE")


if __name__ == "__main__":
    unittest.main()
