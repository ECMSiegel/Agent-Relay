"""Tests for the shared interfaces used by the parallel feature tracks."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lifecycle import LifecycleTestCase


class SeamTests(LifecycleTestCase):
    def test_coordinator_role_and_stale_filter(self):
        self.ok("join", "--agent", "z-coord", "--label", "Z", "--role", "coordinator")
        self.ok("join", "--agent", "a-coord", "--label", "A", "--role", "coordinator")
        self.assertEqual(self.agent("z-coord")["role"], "coordinator")
        self.assertIsNone(self.agent("z-coord")["busy_until"])
        config = self.tool.load_config(self.team)
        self.assertEqual(self.tool.coordinator_ids(self.team, config), ["a-coord", "z-coord"])
        self.set_last_seen("z-coord", 31)  # stale coordinators still get their messages
        self.assertEqual(self.tool.coordinator_ids(self.team, config), ["a-coord", "z-coord"])
        self.ok("leave", "--agent", "z-coord")
        self.assertEqual(self.tool.coordinator_ids(self.team, config), ["a-coord"])
        self.ok("join", "--agent", "z-coord", "--role", "coordinator")
        self.assertEqual(self.tool.coordinator_ids(self.team, config), ["a-coord", "z-coord"])

    def test_busy_agent_is_not_stale(self):
        self.join("a1")
        record = self.agent("a1")
        record["last_seen"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        record["busy_until"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        self.assertFalse(self.tool.is_stale(record, 30))
        record["busy_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertTrue(self.tool.is_stale(record, 30))

    def test_usage_records_report_and_requires_one_value(self):
        self.join("a1")
        self.ok("usage", "--agent", "a1", "--percent", "85", "--note", "near limit")
        usage = self.agent("a1")["usage"]
        self.assertEqual((usage["percent"], usage["note"]), (85, "near limit"))
        self.assertTrue(usage["at"])
        code, _, err = self.main("usage", "--agent", "a1")
        self.assertEqual(code, 1, err)

    def test_attention_items_cover_all_seven_kinds(self):
        self.join("a1", "a2")
        config = self.tool.load_config(self.team)
        observed = set()

        self.ok("question", "--agent", "user", "--text", "choose a format")
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        review_task = self.to_in_progress("a1")
        self.ok("done", review_task, "--agent", "a1", "--note", "ready")
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        stale_task = self.to_in_progress("a2")
        self.set_last_seen("a2", 31)
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        blocked_task = self.to_in_progress("a1", "--no-review")
        self.ok("block", blocked_task, "--agent", "a1", "--reason", "need answer")
        self.ok("resolve", "Q002", "--agent", "user", "--text", "use json")
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        self.ok("usage", "--agent", "a1", "--percent", "80")
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        # Clear live work, leaving a claimable task to exercise the idle item.
        self.ok("handoff", stale_task, "--agent", "a2", "--note", "pause")
        self.ok("handoff", blocked_task, "--agent", "a1", "--note", "pause")
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        self.ok("claim", stale_task, "--agent", "a2")
        self.ok("done", stale_task, "--agent", "a2", "--note", "finished")
        self.ok("review", review_task, "--agent", "user", "--approve")
        self.ok("review", stale_task, "--agent", "user", "--approve")
        # The handed-off blocked task is still available, so finish it too.
        self.ok("claim", blocked_task, "--agent", "a1")
        self.ok("start", blocked_task, "--agent", "a1")
        self.ok("done", blocked_task, "--agent", "a1", "--note", "finished")
        observed.update(item["kind"] for item in self.tool.attention_items(self.team, config))

        self.assertEqual([self.task(task_id)["status"] for task_id in
                          (review_task, stale_task, blocked_task)], ["done", "done", "done"])
        final_items = self.tool.attention_items(self.team, config)
        self.assertTrue(all(set(item) == {"key", "kind", "task", "text"} and item["text"]
                            for item in final_items))
        self.assertEqual(observed, {"question", "review", "stale_owner", "answered",
                                    "usage_high", "idle", "complete"})

    def test_attention_texts_carry_task_and_title(self):
        self.join("a1", "a2")
        config = self.tool.load_config(self.team)
        task = self.to_in_progress("a1")
        self.ok("question", "--agent", "a2", "--task", task, "--text", "x" * 100)
        self.ok("done", task, "--agent", "a1", "--note", "ready")
        second = self.add("Second piece")
        self.ok("claim", second, "--agent", "a2")
        self.set_last_seen("a2", 31)
        texts = {item["kind"]: item["text"]
                 for item in self.tool.attention_items(self.team, config)}
        self.assertEqual(texts["question"], "Question Q001 (%s) is open: %s..." % (task, "x" * 80))
        self.assertEqual(texts["review"], "Task %s (Work) is awaiting review." % task)
        self.assertEqual(texts["stale_owner"],
                         "Task %s (Second piece) has stale or left owner a2." % second)

    def test_usage_percent_out_of_range_is_a_short_error(self):
        self.join("a1")
        for bad in ("101", "-1"):
            code, out, err = self.main("usage", "--agent", "a1", "--percent", bad)
            self.assertEqual(code, 1, err)
            self.assertIn("0 to 100", err)
            self.assertLess(len(err), 200)
        self.ok("usage", "--agent", "a1", "--percent", "100")

    def test_wait_and_watch_dispatch_without_lock_or_view_render(self):
        self.join("a1")
        before = self.view("BOARD.md")
        for argv in (("wait", "--agent", "a1", "--timeout", "0", "--interval", "0.01"),
                     ("watch", "--once", "--no-notify")):
            with self.subTest(argv=argv):
                code, _, err = self.main(*argv)
                self.assertEqual(code, 0, err)
                self.assertFalse((self.team / ".lock").exists())
                self.assertEqual(self.view("BOARD.md"), before)

    def test_coordinator_is_a_reserved_agent_id(self):
        code, _, err = self.main("join", "--agent", "coordinator", "--label", "No")
        self.assertEqual(code, 1)
        self.assertIn("invalid agent ID", err)

    def test_user_owned_live_task_is_not_reported_as_stale_owner(self):
        task_id = self.add("User task", "--no-review")
        self.ok("claim", task_id, "--agent", "user")
        items = self.tool.attention_items(self.team, self.tool.load_config(self.team))
        self.assertFalse([item for item in items if item["kind"] == "stale_owner"])


if __name__ == "__main__":
    import unittest
    unittest.main()
