"""Tests for the T9 additions: the unread-message line, `doctor` and `check-exit`.
Run from .agents/team: python3 -B -m unittest tests.test_extras -v

Every test works in its own temporary fake workspace made by helpers.make_workspace; nothing is
written under the real .agents/team/.
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lifecycle import LifecycleTestCase  # noqa: E402


class UnreadLineTests(LifecycleTestCase):
    def line(self, agent, count=1):
        return "%d unread message(s): team.py inbox --agent %s" % (count, agent)

    def test_line_follows_a_command_until_inbox_is_read(self):
        self.join("a1", "a2")
        task_id = self.add()
        self.ok("msg", "--agent", "a2", "--to", "a1", "--kind", "info", "--text", "hello")
        out = self.ok("show", task_id, "--agent", "a1")
        lines = out.rstrip("\n").splitlines()
        self.assertEqual(lines[-2], self.line("a1"))
        self.assertIn("from a2 [info]: hello", lines[-1])  # the direct-message preview follows
        inbox = self.ok("inbox", "--agent", "a1")
        self.assertIn("hello", inbox)
        self.assertNotIn("unread message(s)", inbox)  # inbox itself prints no reminder
        out = self.ok("show", task_id, "--agent", "a1")
        self.assertNotIn("unread message(s)", out)

    def test_line_counts_broadcasts_and_peek_leaves_it(self):
        self.join("a1", "a2")
        self.ok("msg", "--agent", "a2", "--to", "all", "--kind", "info", "--text", "one")
        self.ok("msg", "--agent", "a2", "--to", "a1", "--kind", "info", "--text", "two")
        self.ok("msg", "--agent", "a2", "--to", "a2", "--kind", "info", "--text", "not for a1")
        self.ok("inbox", "--agent", "a1", "--peek")
        out = self.ok("next", "--agent", "a1")
        lines = out.rstrip("\n").splitlines()
        self.assertEqual(lines[-2], self.line("a1", 2))
        self.assertIn("from a2 [info]: two", lines[-1])  # the direct-message preview follows

    def test_no_line_for_user_join_or_when_nothing_is_unread(self):
        self.join("a1")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "hi")
        self.assertIn("1 unread message(s)", self.ok("next", "--agent", "a1"))  # control
        self.assertNotIn("unread message(s)", self.ok("next", "--agent", "user"))
        self.assertNotIn("unread message(s)", self.ok("join", "--agent", "a2"))
        self.ok("inbox", "--agent", "a1")
        self.assertNotIn("unread message(s)", self.ok("next", "--agent", "a1"))

    def test_line_comes_after_the_command_output_and_keeps_the_exit_code(self):
        self.join("a1", "a2")
        self.ok("msg", "--agent", "a2", "--to", "a1", "--kind", "info", "--text", "hello")
        code, out, _ = self.main("complete", "--agent", "a1")  # exit 2: not finished
        self.assertEqual(code, 2)
        lines = out.rstrip("\n").splitlines()
        self.assertEqual(lines[-2], self.line("a1"))
        self.assertIn("from a2 [info]: hello", lines[-1])  # the direct-message preview follows
        self.assertIn("NOT COMPLETE", out)


class StatusUnreadTests(LifecycleTestCase):
    def test_status_shows_the_count_once(self):
        self.join("a1")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "hi")
        out = self.ok("status", "--agent", "a1")
        self.assertIn("Unread messages for a1: 1", out)
        self.assertNotIn("unread message(s)", out)


class CheckExitTests(LifecycleTestCase):
    def test_ok_when_no_live_task(self):
        self.join("a1")
        out = self.ok("check-exit", "--agent", "a1")
        self.assertEqual(out.strip(), "OK to leave: no live task owned by a1")

    def test_ok_with_task_in_review_or_done(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.ok("done", task_id, "--agent", "a1", "--note", "ready")  # review required: review
        self.assertEqual(self.task(task_id)["status"], "review")
        self.assertIn("OK to leave", self.ok("check-exit", "--agent", "a1"))

    def test_refused_listing_live_tasks_and_changes_nothing(self):
        self.join("a1")
        first = self.to_in_progress("a1")
        second = self.add("Other")
        self.ok("claim", second, "--agent", "a1")
        before = (self.task(first), self.task(second))
        err = self.refused("check-exit", "--agent", "a1")
        self.assertIn("%s (in_progress)" % first, err)
        self.assertIn("%s (claimed)" % second, err)
        self.assertIn('handoff %s --agent a1 --note "..."' % first, err)
        self.assertEqual((self.task(first), self.task(second)), before)
        self.assertEqual(self.agent("a1")["status"], "active")

    def test_blocked_counts_as_live_and_other_agents_tasks_do_not(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.ok("block", task_id, "--agent", "a1", "--reason", "x")
        self.refused("check-exit", "--agent", "a1")
        self.assertIn("OK to leave", self.ok("check-exit", "--agent", "a2"))

    def test_heartbeat_and_unknown_agent(self):
        self.join("a1")
        self.set_last_seen("a1", 20)
        old = self.agent("a1")["last_seen"]
        self.ok("check-exit", "--agent", "a1")
        self.assertNotEqual(self.agent("a1")["last_seen"], old)
        self.refused("check-exit", "--agent", "ghost")
        code, _, err = self.main("check-exit")
        self.assertEqual(code, 1, err)


class DoctorTests(LifecycleTestCase):
    def edit_task(self, task_id, **fields):
        path = self.team / "tasks" / ("%s.json" % task_id)
        data = json.loads(path.read_text())
        data.update(fields)
        path.write_text(json.dumps(data, indent=2))

    def problems(self):
        code, out, err = self.main("doctor")
        self.assertEqual(code, 2, out + err)
        return out

    def snapshot(self):
        return {str(p.relative_to(self.team)): p.read_bytes()
                for p in sorted(self.team.rglob("*")) if p.is_file()}

    def test_clean_workspace_is_ok(self):
        self.assertEqual(self.ok("doctor"), "OK\n")

    def test_clean_after_a_full_lifecycle(self):
        self.join("a1", "a2")
        t1 = self.to_in_progress("a1")
        t2 = self.add("Second", "--depends", t1, "--files", "src/b.py")
        self.ok("msg", "--agent", "a1", "--to", "a2", "--kind", "info", "--text", "hi")
        self.ok("done", t1, "--agent", "a1", "--note", "ok")
        self.ok("review", t1, "--agent", "a2", "--reject", "--note", "again")
        self.ok("claim", t1, "--agent", "a2")
        self.ok("start", t1, "--agent", "a2")
        self.ok("block", t1, "--agent", "a2", "--reason", "q")
        self.ok("question", "--agent", "a2", "--text", "why", "--task", t2)
        self.ok("unblock", t1, "--agent", "a2")
        self.ok("handoff", t1, "--agent", "a2", "--note", "stop")
        self.ok("claim", t1, "--agent", "a1")
        self.ok("done", t1, "--agent", "a1", "--note", "done")
        self.ok("review", t1, "--agent", "a2", "--approve")
        self.assertEqual(self.ok("doctor", "--agent", "a1").splitlines()[0], "OK")

    def test_owner_without_agent_file(self):
        t1 = self.to_in_progress("user")
        self.edit_task(t1, owner="ghost")
        code, out, _ = self.main("doctor")
        self.assertEqual(code, 2)
        self.assertIn(t1, out)
        self.assertIn("ghost", out)
        self.assertNotIn("OK", out)

    def test_owner_who_left(self):
        self.join("a1")
        t1 = self.to_in_progress("a1")
        path = self.team / "agents" / "a1.json"
        record = json.loads(path.read_text())
        record["status"] = "left"
        path.write_text(json.dumps(record))
        out = self.problems()
        self.assertIn("%s: owner a1 is left, not active" % t1, out)

    def test_two_live_tasks_with_overlapping_paths(self):
        self.join("a1", "a2")
        t1 = self.to_in_progress("a1", "--files", "src/a.py")
        t2 = self.to_in_progress("a2", "--files", "lib/b.py")
        self.assertEqual(self.ok("doctor"), "OK\n")
        self.edit_task(t2, files=["src"])
        out = self.problems()
        self.assertIn(t1, out)
        self.assertIn(t2, out)
        self.assertIn("overlapping", out)

    def test_depends_on_missing_and_cycle(self):
        t1, t2 = self.add("One"), self.add("Two")
        self.edit_task(t1, depends_on=["T099"])
        self.assertIn("%s: depends_on T099, which does not exist" % t1, self.problems())
        self.edit_task(t1, depends_on=[t2])
        self.edit_task(t2, depends_on=[t1])
        out = self.problems()
        self.assertIn("depends_on cycle: %s -> %s -> %s" % (t1, t2, t1), out)
        self.assertEqual(out.count("cycle"), 1)

    def test_self_dependency_is_a_cycle(self):
        t1 = self.add("One")
        self.edit_task(t1, depends_on=[t1])
        self.assertIn("depends_on cycle: %s -> %s" % (t1, t1), self.problems())

    def test_agent_current_task_must_match_owner(self):
        self.join("a1", "a2")
        t1 = self.to_in_progress("a1")
        path = self.team / "agents" / "a2.json"
        record = json.loads(path.read_text())
        record["current_task"] = t1
        path.write_text(json.dumps(record))
        self.assertIn("agent a2: current_task %s is owned by a1" % t1, self.problems())
        record["current_task"] = "T077"
        path.write_text(json.dumps(record))
        self.assertIn("agent a2: current_task T077 does not exist", self.problems())

    def test_message_ids_must_run_one_to_n(self):
        self.join("a1")
        for text in ("a", "b", "c"):
            self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", text)
        path = self.team / "messages.jsonl"
        rows = [json.loads(ln) for ln in path.read_text().splitlines()]
        rows[1]["id"] = 5
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        out = self.problems()
        self.assertIn("messages.jsonl line 2 has id 5, expected 2", out)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows[:1] + rows[2:]))
        self.assertIn("messages.jsonl line 2 has id 3, expected 2", self.problems())

    def test_question_with_unknown_task(self):
        self.join("a1")
        self.ok("question", "--agent", "a1", "--text", "why", "--task", "T042")
        self.assertIn("Q001: refers to task T042, which does not exist", self.problems())

    def test_unreadable_and_incomplete_task_files(self):
        t1, t2 = self.add("One"), self.add("Two")
        (self.team / "tasks" / ("%s.json" % t1)).write_text("{not json")
        data = json.loads((self.team / "tasks" / ("%s.json" % t2)).read_text())
        del data["owner"]
        (self.team / "tasks" / ("%s.json" % t2)).write_text(json.dumps(data))
        out = self.problems()
        self.assertIn("tasks/%s.json: not readable JSON" % t1, out)
        self.assertIn("%s: task file is missing key(s) owner" % t2, out)

    def test_stale_lock_files_are_warnings_only(self):
        guard = self.team / ".lock.break"
        guard.write_text("")
        old = time.time() - 60
        os.utime(str(guard), (old, old))
        code, out, _ = self.main("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("warning: .lock.break is", out)
        self.assertTrue(out.rstrip().endswith("OK (1 warning(s))"), out)
        guard.unlink()
        lock = self.team / ".lock"
        lock.write_text("someone 1 2000-01-01T00:00:00+00:00")
        os.utime(str(lock), (old, old))
        problems, warnings = self.tool.doctor_report(self.team, self.tool.load_config(self.team))
        self.assertEqual(problems, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn(".lock is", warnings[0])

    def test_fresh_lock_files_are_not_reported(self):
        (self.team / ".lock.break").write_text("")
        self.assertEqual(self.ok("doctor"), "OK\n")

    def test_missing_view_is_reported_and_only_fix_views_restores_it(self):
        (self.team / "QUESTIONS.md").unlink()
        self.assertIn("QUESTIONS.md is missing", self.problems())
        self.assertFalse((self.team / "QUESTIONS.md").exists())  # doctor alone does not repair
        self.assertIn("QUESTIONS.md is missing", self.problems())
        self.assertEqual(self.ok("doctor", "--fix-views"), "OK\n")
        self.assertTrue((self.team / "QUESTIONS.md").is_file())
        self.assertEqual(self.ok("doctor"), "OK\n")

    def test_doctor_changes_no_file(self):
        self.join("a1")
        self.to_in_progress("a1", "--files", "src/a.py")
        self.edit_task("T001", owner="ghost")
        before = self.snapshot()
        code, out, _ = self.main("doctor")
        self.assertEqual(code, 2)
        self.assertIn("ghost", out)  # it did find the problem, and still wrote nothing
        self.assertEqual(self.snapshot(), before)

    def test_doctor_survives_a_corrupt_task_and_fix_views_reports_it(self):
        t1 = self.add("One")
        (self.team / "tasks" / ("%s.json" % t1)).write_text("{not json")
        code, out, err = self.main("doctor", "--fix-views")
        self.assertEqual(code, 2, out + err)
        self.assertIn("views not rewritten", out)
        self.assertIn("not readable JSON", out)

    def test_optional_agent_heartbeats(self):
        self.join("a1")
        self.set_last_seen("a1", 20)
        old = self.agent("a1")["last_seen"]
        self.ok("doctor", "--agent", "a1")
        self.assertNotEqual(self.agent("a1")["last_seen"], old)
        self.refused("doctor", "--agent", "ghost")


class HelpTests(LifecycleTestCase):
    def test_help_lists_35_commands_including_the_new_features(self):
        out = self.ok("--help")
        rows = [ln for ln in out.splitlines() if ln[:2] == "  " and ln[2:3].islower()]
        self.assertEqual(len(rows), 35)
        self.assertTrue(any(r.startswith("  check-exit ") for r in rows))
        self.assertTrue(any(r.startswith("  doctor ") for r in rows))
        for command in ("usage", "busy", "wait", "watch"):
            self.assertTrue(any(r.startswith("  %s " % command) for r in rows), command)


if __name__ == "__main__":
    unittest.main()
