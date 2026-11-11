"""Tests for coordinator routing, takeover, and stall handling."""
from __future__ import annotations

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lifecycle import LifecycleTestCase


class StallTests(LifecycleTestCase):
    def messages(self):
        return self.lines("messages.jsonl")

    def test_busy_sets_deadline_and_tells_everyone(self):
        self.ok("join", "--agent", "coord-a", "--role", "coordinator")
        self.ok("join", "--agent", "coord-b", "--role", "coordinator")
        self.join("worker")

        self.ok("busy", "--agent", "worker", "--minutes", "15", "--text", "running tests")

        self.assertTrue(self.agent("worker")["busy_until"])
        notices = self.messages()
        self.assertEqual([(m["to"], m["kind"], m["text"]) for m in notices], [
            ("all", "info", "worker is busy for about 15 minutes: running tests"),
        ])

    def test_busy_refuses_minutes_outside_configured_range(self):
        self.join("worker")
        for minutes in (0, 121):
            with self.subTest(minutes=minutes):
                code, _, err = self.main("busy", "--agent", "worker", "--minutes",
                                         str(minutes), "--text", "waiting")
                self.assertEqual(code, 1, err)
                self.assertIn("between 1 and 120", err)

    def test_next_offers_stale_and_left_tasks_in_priority_order(self):
        self.join("owner-a", "owner-b", "worker")
        low = self.add("Low priority", "--priority", "3")
        high = self.add("High priority", "--priority", "1")
        left = self.add("Left owner", "--priority", "2")
        for task_id, owner in ((low, "owner-a"), (high, "owner-a"), (left, "owner-b")):
            self.ok("claim", task_id, "--agent", owner)
        self.set_last_seen("owner-a", 31)
        record = self.agent("owner-b")
        record["status"] = "left"
        self.tool.save_agent(self.team, record)

        out = self.ok("next", "--agent", "worker")

        section = out.split("Tasks you can take over (owner stale or left):", 1)[1]
        self.assertLess(section.index("reclaim %s" % high), section.index("reclaim %s" % left))
        self.assertLess(section.index("reclaim %s" % left), section.index("reclaim %s" % low))
        self.assertIn("owner-a", section)
        self.assertIn("owner-b", section)

    def test_coordinator_can_reclaim_active_owner_with_override_log(self):
        self.ok("join", "--agent", "coord-a", "--role", "coordinator")
        self.join("worker")
        task_id = self.to_in_progress("worker")

        self.ok("reclaim", task_id, "--agent", "coord-a")

        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("claimed", "coord-a"))
        self.assertEqual(task["log"][-1]["event"], "reclaimed from worker (override)")
        self.assertIn("reclaimed from you", self.ok("inbox", "--agent", "worker"))

    def test_user_can_reclaim_active_owner_without_coordinator_role(self):
        self.join("worker")
        task_id = self.to_in_progress("worker")

        self.ok("reclaim", task_id, "--agent", "user")

        self.assertEqual(self.task(task_id)["owner"], "user")
        self.assertEqual(self.task(task_id)["log"][-1]["event"],
                         "reclaimed from worker (override)")
        self.assertIn("reclaimed from you", self.ok("inbox", "--agent", "worker"))

    def test_coordinator_can_release_active_task_without_creating_worktree(self):
        self.ok("join", "--agent", "coord-a", "--role", "coordinator")
        self.join("worker")
        task_id = self.to_in_progress("worker")
        called = []
        self.tool._wt_on_take = lambda _team, _task: called.append(True)

        self.ok("reclaim", task_id, "--agent", "coord-a", "--release")

        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"], task["claimed_at"]),
                         ("available", None, None))
        self.assertEqual(task["handoff"]["text"],
                         "Released from worker by coord-a. Registered paths may hold "
                         "uncommitted edits; check them before continuing.")
        self.assertFalse(called)
        self.assertIn("released", self.ok("inbox", "--agent", "worker"))

    def test_regular_agent_cannot_reclaim_active_task_even_with_release(self):
        self.join("owner", "worker")
        task_id = self.to_in_progress("owner")

        err = self.refused("reclaim", task_id, "--agent", "worker", "--release")

        self.assertIn("active", err)
        self.assertEqual(self.task(task_id)["owner"], "owner")

    def test_stale_owner_task_can_be_released_by_regular_agent(self):
        self.join("owner", "worker")
        task_id = self.to_in_progress("owner")
        self.set_last_seen("owner", 31)

        self.ok("reclaim", task_id, "--agent", "worker", "--release")

        task = self.task(task_id)
        self.assertEqual((task["status"], task["owner"]), ("available", None))
        self.assertEqual(task["handoff"]["text"],
                         "Released from owner by worker. Registered paths may hold "
                         "uncommitted edits; check them before continuing.")

    def test_msg_to_coordinator_reaches_all_active_coordinators(self):
        self.ok("join", "--agent", "coord-a", "--role", "coordinator")
        self.ok("join", "--agent", "coord-b", "--role", "coordinator")
        self.join("worker")

        self.ok("msg", "--agent", "worker", "--to", "coordinator", "--kind", "question",
                "--text", "need a decision")

        self.assertEqual([(m["to"], m["text"]) for m in self.messages()], [
            ("coord-a", "need a decision"), ("coord-b", "need a decision")])

    def test_msg_to_coordinator_without_one_refuses_with_question_hint(self):
        self.join("worker")

        err = self.refused("msg", "--agent", "worker", "--to", "coordinator", "--kind",
                           "info", "--text", "need help")

        self.assertIn('question --agent worker --text "..."', err)

    def test_questions_lifecycle_and_handoffs_notify_coordinators(self):
        self.ok("join", "--agent", "coord-a", "--role", "coordinator")
        self.join("worker")
        task_id = self.to_in_progress("worker")

        self.ok("question", "--agent", "worker", "--text", "pick an API", "--task", task_id)
        question = self.messages()[-1]
        self.assertEqual((question["to"], question["kind"], question["task"]),
                         ("coord-a", "info", task_id))
        self.assertIn("Q001", question["text"])

        self.ok("block", task_id, "--agent", "worker", "--reason", "need an answer")
        self.assertIn("is blocked", self.messages()[-1]["text"])
        self.ok("propose", "--agent", "worker", "--title", "Change scope", "--text", "why")
        self.assertIn("plan change proposed", self.messages()[-1]["text"])
        self.ok("resolve", "Q001", "--agent", "user", "--text", "use API v2")
        self.assertIn("Q001 resolved", self.messages()[-1]["text"])

        self.ok("handoff", task_id, "--agent", "worker", "--note", "pausing")
        self.assertIn("handed off", self.messages()[-1]["text"])
        self.ok("claim", task_id, "--agent", "worker")
        self.ok("done", task_id, "--agent", "worker", "--note", "ready for review")
        self.assertIn("review", self.messages()[-1]["text"])
        coordinator_messages = [m for m in self.messages() if m["to"] == "coord-a"]
        self.assertEqual(len(coordinator_messages), 6)
        self.assertIn("Q001 opened", coordinator_messages[0]["text"])
        self.assertIn("is blocked", coordinator_messages[1]["text"])
        self.assertIn("plan change proposed", coordinator_messages[2]["text"])
        self.assertIn("Q001 resolved", coordinator_messages[3]["text"])
        self.assertIn("handed off", coordinator_messages[4]["text"])
        self.assertIn("entered review", coordinator_messages[5]["text"])

    def test_coordinator_notification_is_silent_when_none_exist(self):
        self.join("worker")

        self.ok("question", "--agent", "worker", "--text", "anyone there?")

        self.assertEqual(self.messages(), [])

    def test_unread_line_prints_three_direct_messages_without_advancing_cursor(self):
        self.join("sender", "recipient")
        for text in ("direct one", "direct two", "direct three", "direct four"):
            self.tool.send_message(self.team, "sender", "recipient", "info", text)
        self.tool.send_message(self.team, "sender", "all", "info", "broadcast")
        before = self.agent("recipient")["inbox_cursor"]
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.tool.print_unread_line(self.team, "recipient")

        text = output.getvalue()
        self.assertIn("5 unread message(s)", text)
        self.assertIn("direct one", text)
        self.assertIn("direct two", text)
        self.assertIn("direct three", text)
        self.assertNotIn("direct four", text)
        self.assertNotIn("broadcast", text)
        self.assertEqual(self.agent("recipient")["inbox_cursor"], before)


if __name__ == "__main__":
    import unittest
    unittest.main()
