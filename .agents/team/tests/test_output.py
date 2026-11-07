"""Tests for the output fixes: left agents hidden from status/BOARD.md, a new agent's inbox
cursor, trimmed log notes in `show`, and no view rendering for read-only commands.
Run from .agents/team: python3 -B -m unittest tests.test_output -v

Every test works in its own temporary fake workspace made by helpers.make_workspace; nothing is
written under the real .agents/team/.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lifecycle import LifecycleTestCase  # noqa: E402

MARKER = " [... show --full]"


class NewAgentCursorTests(LifecycleTestCase):
    def test_new_agent_starts_at_latest_message_and_inbox_is_empty(self):
        self.join("a1")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "one")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "two")
        out = self.ok("join", "--agent", "a2")
        self.assertIn("You are a2", out)
        self.assertEqual(self.agent("a2")["inbox_cursor"], 2)
        self.assertEqual(self.ok("inbox", "--agent", "a2"), "No new messages.\n")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "three")
        self.assertIn("three", self.ok("inbox", "--agent", "a2"))

    def test_generated_id_agent_also_starts_at_latest_message(self):
        self.join("a1")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "one")
        out = self.ok("join", "--label", "Codex")
        new_id = re.search(r"You are (agent-[0-9a-f]{4})", out).group(1)
        self.assertEqual(self.agent(new_id)["inbox_cursor"], 1)

    def test_rejoin_keeps_old_cursor(self):
        self.join("a1")
        self.ok("msg", "--agent", "a1", "--to", "all", "--kind", "info", "--text", "one")
        path = self.team / "agents" / "a1.json"
        record = json.loads(path.read_text())
        record.update(status="left", inbox_cursor=0)
        path.write_text(json.dumps(record))
        self.ok("join", "--agent", "a1")
        self.assertEqual(self.agent("a1")["inbox_cursor"], 0)


class ShowTrimTests(LifecycleTestCase):
    def logged_task(self, event, note):
        if not (self.team / "agents" / "a1.json").exists():
            self.join("a1")
        task_id = self.to_in_progress("a1")
        path = self.team / "tasks" / ("%s.json" % task_id)
        task = json.loads(path.read_text())
        task["log"].append({"at": "2026-01-01T00:00:00+00:00", "agent": "a1",
                            "event": event, "note": note})
        path.write_text(json.dumps(task))
        return task_id

    def test_default_show_cuts_long_started_note_and_full_keeps_it(self):
        note = "".join(chr(97 + i % 26) for i in range(600))
        task_id = self.logged_task("started", note)
        out = self.ok("show", task_id)
        self.assertNotIn(note, out)
        self.assertIn(note[:240] + MARKER, out)
        self.assertNotIn(note[:241], out)
        self.assertIn(note, self.ok("show", task_id, "--full"))
        self.assertNotIn(MARKER, self.ok("show", task_id, "--full"))

    def test_rejected_review_requested_and_handoff_notes_never_cut(self):
        note = "x" * 600
        for event in ("rejected", "review requested", "handoff", "handoff to a2"):
            task_id = self.logged_task(event, note)
            out = self.ok("show", task_id)
            self.assertIn(note, out, event)
            self.assertNotIn(MARKER, out, event)

    def test_short_note_untouched(self):
        task_id = self.logged_task("started", "y" * 240)
        out = self.ok("show", task_id)
        self.assertIn("y" * 240, out)
        self.assertNotIn(MARKER, out)

    def test_claim_output_is_not_trimmed(self):
        task_id = self.logged_task("started", "z" * 600)
        self.ok("handoff", task_id, "--agent", "a1", "--note", "n")
        out = self.ok("claim", task_id, "--agent", "a1")  # claim prints format_task too
        self.assertIn("z" * 600, out)
        self.assertNotIn(MARKER, out)


class LeftAgentTests(LifecycleTestCase):
    def leave(self, *ids):
        for agent in ids:
            path = self.team / "agents" / ("%s.json" % agent)
            record = json.loads(path.read_text())
            record["status"] = "left"
            path.write_text(json.dumps(record))

    def test_status_and_board_hide_left_agents_status_all_shows_them(self):
        self.join("a1", "a2", "a3")
        self.leave("a2", "a3")
        out = self.ok("status")
        self.assertIn("| a1 |", out)
        self.assertNotIn("| a2 |", out)
        self.assertNotIn("| a3 |", out)
        self.assertIn("2 left agents hidden (status --all lists them)", out)
        # Status does not refresh generated views; the prior board snapshot is left untouched.
        board = self.view("BOARD.md")
        self.assertIn("| a2 |", board)
        self.assertNotIn("left agents hidden", board)
        everything = self.ok("status", "--all")
        self.assertIn("| a2 |", everything)
        self.assertIn("| a3 |", everything)
        self.assertNotIn("hidden", everything)
        self.assertIn("| a2 |", self.view("BOARD.md"))  # status and --all are read-only

    def test_one_left_agent_line_and_no_line_when_none_hidden(self):
        self.join("a1", "a2")
        self.assertNotIn("hidden", self.ok("status"))
        self.leave("a2")
        self.assertIn("1 left agent hidden (status --all lists them)", self.ok("status"))

    def test_owner_left_flag_survives_hiding(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.leave("a1")
        out = self.ok("status")
        self.assertNotIn("| a1 |", out)
        self.assertIn("[OWNER LEFT]", out)
        self.assertIn(task_id, out)


class ReadOnlyViewTests(LifecycleTestCase):
    def test_read_only_commands_do_not_render_views(self):
        self.join("a1")
        task_id = self.add()
        board = self.team / "BOARD.md"
        board.unlink()
        for argv in (("show", task_id), ("next", "--agent", "a1"), ("owner", "x"), ("stale",),
                     ("skills",), ("complete",), ("check-exit", "--agent", "a1")):
            self.main(*argv)  # complete / check-exit may exit 2; only the views matter here
            self.assertFalse(board.exists(), "%s recreated BOARD.md" % argv[0])
        self.ok("status")
        self.assertFalse(board.exists())
        self.ok("inbox", "--agent", "a1")
        self.assertTrue(board.exists())


class StatusReadOnlyTests(LifecycleTestCase):
    def test_status_with_agent_does_not_heartbeat_or_rewrite_views(self):
        self.join("a1")
        self.set_last_seen("a1", 90)
        agent_path = self.team / "agents" / "a1.json"
        before_agent = agent_path.read_bytes()
        board = self.team / "BOARD.md"
        board.unlink()
        code, out, err = self.main("status", "--agent", "a1")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Unread messages for a1", out)
        self.assertEqual(agent_path.read_bytes(), before_agent)
        self.assertFalse(board.exists())
        self.assertFalse((self.team / ".lock").exists())

    def test_status_ignores_team_agent_for_heartbeat_and_does_not_lock(self):
        self.join("a1")
        self.set_last_seen("a1", 90)
        path = self.team / "agents" / "a1.json"
        before = path.read_bytes()
        os.environ["TEAM_AGENT"] = "a1"
        code, _, err = self.main("status")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.team / ".lock").exists())

    def test_status_during_writer_lock_reports_possible_snapshot_contention(self):
        self.join("a1")
        lock = self.team / ".lock"
        lock.write_text("writer\n")
        code, out, err = self.main("status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("snapshot may be changing", out.lower())
        self.assertEqual(lock.read_text(), "writer\n")
        self.assertFalse((self.team / ".lock.break").exists())

    def test_status_rejects_unknown_agent_without_writing(self):
        before = (self.team / "agents").glob("*.json")
        self.assertEqual(list(before), [])
        code, _, err = self.main("status", "--agent", "missing")
        self.assertEqual(code, 2)
        self.assertFalse((self.team / ".lock").exists())


if __name__ == "__main__":
    unittest.main()
