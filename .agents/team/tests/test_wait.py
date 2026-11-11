"""Wait and watch tests for team.py. All state is in a disposable project."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

from test_lifecycle import LifecycleTestCase


class WaitAndWatchTests(LifecycleTestCase):
    def run_process(self, *argv):
        env = dict(os.environ)
        env["TEAM_DIR"] = str(self.team)
        env.pop("TEAM_AGENT", None)
        return subprocess.Popen([sys.executable, str(self.tool_path), *argv],
                                cwd=str(self.project), env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def test_wait_timeout_reports_nothing_new_and_leaves_no_lock(self):
        self.join("a1")
        proc = self.run_process("wait", "--agent", "a1", "--timeout", "0.1",
                                "--interval", "0.02")
        out, err = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0, err)
        self.assertTrue(out.startswith("NOTHING NEW after"), out)
        self.assertFalse((self.team / ".lock").exists())

    def test_wait_ignores_starting_items_and_returns_on_new_question(self):
        self.join("a1", "a2")
        self.ok("question", "--agent", "a2", "--text", "already open")
        proc = self.run_process("wait", "--agent", "a1", "--timeout", "2",
                                "--interval", "0.03")
        try:
            ready = proc.stdout.readline()
            self.assertEqual(ready.strip(), "Already waiting:")
            existing = proc.stdout.readline()
            self.assertIn("Question Q001 is open.", existing)
            self.ok("question", "--agent", "a2", "--text", "wake up")
            before = self.view("BOARD.md")
            out, err = proc.communicate(timeout=3)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        self.assertEqual(proc.returncode, 0, err)
        self.assertNotIn("NEW: Question Q001", out)
        self.assertRegex(out, r"(?m)^NEW:.*Q002")
        self.assertEqual(before, self.view("BOARD.md"))
        self.assertFalse((self.team / ".lock").exists())

    def test_wait_returns_on_new_direct_message(self):
        self.join("a1", "a2")
        self.ok("question", "--agent", "a2", "--text", "baseline")
        proc = self.run_process("wait", "--agent", "a1", "--timeout", "2",
                                "--interval", "0.03")
        try:
            self.assertEqual(proc.stdout.readline().strip(), "Already waiting:")
            proc.stdout.readline()
            self.ok("msg", "--agent", "a2", "--to", "a1", "--text", "ping",
                    "--kind", "info")
            out, err = proc.communicate(timeout=3)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("NEW:", out)
        self.assertIn("ping", out)

    def test_wait_heartbeats_agent(self):
        self.join("a1")
        self.set_last_seen("a1", 90)
        proc = self.run_process("wait", "--agent", "a1", "--timeout", "0.12",
                                "--interval", "0.02")
        out, err = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("NOTHING NEW", out)
        self.assertFalse(self.tool.is_stale(self.agent("a1"), 30))

    def test_watch_once_prints_current_items_without_notification(self):
        self.join("a1")
        self.ok("question", "--agent", "a1", "--text", "look here")
        out = self.ok("watch", "--once", "--no-notify")
        self.assertIn("Question Q001 is open.", out)

    def test_notify_desktop_passes_title_and_text_as_arguments(self):
        with mock.patch.object(self.tool.sys, "platform", "darwin"), \
                mock.patch.object(shutil, "which", return_value="/usr/bin/osascript"), \
                mock.patch.object(self.tool.subprocess, "run") as run:
            self.tool._notify_desktop('; do shell script "x', "body")
        args = run.call_args[0][0]
        self.assertEqual(args[0:2], ["osascript", "-e"])
        self.assertEqual(args[-2:], ['; do shell script "x', "body"])
        self.assertEqual(run.call_args.kwargs["check"], False)
        self.assertNotIn('; do shell script "x', args[2])


if __name__ == "__main__":
    unittest.main()
