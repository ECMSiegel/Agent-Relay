"""Acceptance tests for the self-contained HTML board and its Markdown snapshot."""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lifecycle import LifecycleTestCase


class BoardTests(LifecycleTestCase):
    def board(self, title="Board work"):
        self.add(title)
        path = self.team / "BOARD.html"
        self.assertTrue(path.is_file(), "BOARD.html missing after add")
        return path.read_text(encoding="utf-8")

    def board_data(self, html):
        blocks = re.findall(
            r'<script type="application/json" id="board-data">(.*?)</script>', html, re.S)
        self.assertEqual(len(blocks), 1, "expected one board-data script block")
        return json.loads(blocks[0])

    def test_html_is_written_after_add_and_embeds_complete_board_data(self):
        self.ok("join", "--agent", "coord", "--role", "coordinator")
        self.ok("join", "--agent", "worker")
        self.ok("usage", "--agent", "worker", "--percent", "85", "--note", "low on context")
        self.ok("question", "--agent", "user", "--text", "choose a view")
        task_id = self.add("Review the data")

        html = self.board()
        data = self.board_data(html)
        self.assertIn("agents", data)
        self.assertIn("tasks", data)
        self.assertIn("questions", data)
        self.assertIn("attention", data)
        self.assertIn("stale_minutes", data)
        self.assertTrue(data["generated_at"])
        worker = next(agent for agent in data["agents"] if agent["id"] == "worker")
        self.assertIsNone(worker["role"])
        self.assertIn("last_seen", worker)
        self.assertIn("busy_until", worker)
        self.assertEqual(worker["usage"]["percent"], 85)
        task = next(task for task in data["tasks"] if task["id"] == task_id)
        self.assertIn("log", task)
        self.assertTrue(data["questions"])
        self.assertIn("usage_high", [item["kind"] for item in data["attention"]])
        self.assertEqual(data["stale_minutes"], 30)

    def test_html_escapes_script_breakout_and_uses_no_external_assets(self):
        html = self.board("</script><script>alert(1)</script><b>x")
        self.assertEqual(html.count("</script>"), 2)
        self.assertNotIn("<b>x", html)
        data = self.board_data(html)
        self.assertIn("</script><script>alert(1)</script><b>x",
                      next(task["title"] for task in data["tasks"]
                           if task["title"].startswith("</script>")))
        self.assertNotRegex(html, r"https?://")
        # A meta refresh drops the URL hash and closes the open task panel; reload from script.
        self.assertNotIn('http-equiv="refresh"', html)
        self.assertIn("window.location.reload()", html)
        self.assertIn('sessionStorage.setItem("agent-relay-board-open"', html)
        self.assertIn('sessionStorage.getItem("agent-relay-board-open")', html)
        self.assertIn("prefers-color-scheme", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("sessionStorage", html)
        self.assertIn("location.hash", html)
        self.assertIn("try", html)
        self.assertIn("catch", html)

    def test_html_describes_lanes_usage_attention_and_task_timeline(self):
        self.ok("join", "--agent", "coord", "--role", "coordinator")
        self.ok("join", "--agent", "worker")
        self.ok("usage", "--agent", "worker", "--percent", "85", "--note", "budget")
        available = self.add("Available")
        claimed = self.add("Claimed")
        self.ok("claim", claimed, "--agent", "worker")
        active = self.to_in_progress("worker")
        blocked = self.to_in_progress("worker")
        self.ok("block", blocked, "--agent", "worker", "--reason", "waiting for input")
        review = self.to_in_progress("worker")
        self.ok("done", review, "--agent", "worker", "--note", "ready")
        user_task = self.add("User-owned")
        self.ok("claim", user_task, "--agent", "user")
        done = self.to_in_progress("worker", "--no-review")
        self.ok("done", done, "--agent", "worker", "--note", "finished")

        html = self.board()
        data = self.board_data(html)
        statuses = {task["id"]: task["status"] for task in data["tasks"]}
        self.assertEqual(statuses[available], "available")
        self.assertEqual(statuses[claimed], "claimed")
        self.assertEqual(statuses[active], "in_progress")
        self.assertEqual(statuses[blocked], "blocked")
        self.assertEqual(statuses[review], "review")
        self.assertEqual(statuses[user_task], "claimed")
        self.assertEqual(statuses[done], "done")
        for text in ("Needs you", "Unassigned", "Coordinator", "available", "claimed",
                     "in_progress", "in progress", "blocked", "review", "Done", "reported by the agent",
                     "minutes on current task", "tasks finished", "last seen", "timeline",
                     "Description", "Registered paths", "Dependencies", "Handoff note"):
            self.assertIn(text.lower(), html.lower(), text)
        self.assertIn("user", html)

    def test_board_markdown_hides_idle_stale_agents_but_status_all_shows_them(self):
        self.join("stale", "active")
        self.set_last_seen("stale", 31)
        self.add("Trigger rendering")
        board = self.view("BOARD.md")
        self.assertNotIn("| stale |", board)
        self.assertRegex(board, r"1 stale agent hidden \(status --all lists them\)")
        all_agents = self.ok("status", "--all")
        self.assertIn("| stale |", all_agents)

    def test_idle_stale_coordinator_stays_on_the_board(self):
        self.ok("join", "--agent", "lead", "--role", "coordinator")
        self.set_last_seen("lead", 31)
        self.add("Trigger rendering")
        board = self.view("BOARD.md")
        self.assertIn("| lead |", board)
        self.assertNotIn("stale agent hidden", board)
        self.assertIn('agent.role === "coordinator") return true', self.board())

    def test_board_data_is_valid_and_doctor_accepts_it(self):
        html = self.board()
        self.board_data(html)
        self.assertEqual(self.ok("doctor").strip(), "OK")


    def test_detail_panel_is_fixed_on_the_right_with_a_close_button(self):
        html = self.board()
        self.assertRegex(html, r"\.detail-panel \{[^}]*position:fixed[^}]*right:0")
        self.assertIn("@media (max-width:800px) { .detail-panel { width:100vw; }", html)
        self.assertIn('make("button", "close-button", "Close details")', html)
        self.assertIn("body.panel-open { padding-right:", html)

    def test_board_follows_the_flat_style_rules(self):
        html = self.board()
        css = html.split("<style>")[1].split("</style>")[0]
        # Square corners, no gradients, one shadow (the raised details panel), tokens for type.
        self.assertEqual(re.findall(r"border-radius:\s*([^;]+);", css), ["0"])
        self.assertNotIn("gradient", css)
        self.assertEqual(css.count("box-shadow:"), 1)
        self.assertIn("--ui-font: Futura", css)
        self.assertIn("@media (prefers-color-scheme: dark)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertNotIn("transition:all", css.replace(" ", ""))
        self.assertIn(" -- refreshes every 5 seconds", html)
        self.assertIn("function closePanel()", html)
        self.assertIn("replaceState", html)


if __name__ == "__main__":
    import unittest
    unittest.main()
