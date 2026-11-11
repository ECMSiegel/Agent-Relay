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
            self.assertIn("Question Q001 is open: already open", existing)
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
        self.assertIn("Question Q001 is open: look here", out)

    def test_watch_alerts_again_when_an_item_returns(self):
        import argparse
        import contextlib
        import io
        item = {"key": "review:T001", "kind": "review", "task": "T001", "text": "T001 in review"}
        args = argparse.Namespace(interval=1, once=False, no_notify=True)
        buffer = io.StringIO()
        with mock.patch.object(self.tool, "attention_items",
                               side_effect=[[item], [item], [], [item], KeyboardInterrupt()]), \
                mock.patch.object(self.tool.time, "sleep"), \
                contextlib.redirect_stdout(buffer):
            self.assertEqual(self.tool.cmd_watch(self.team, args, None), 0)
        self.assertEqual(buffer.getvalue().count("T001 in review"), 2)

    def run_watch(self, items_by_pass, no_notify, platform="darwin"):
        import argparse
        import contextlib
        import io
        args = argparse.Namespace(interval=1, once=False, no_notify=no_notify)
        buffer = io.StringIO()
        with mock.patch.object(self.tool, "attention_items",
                               side_effect=list(items_by_pass) + [KeyboardInterrupt()]), \
                mock.patch.object(self.tool.sys, "platform", platform), \
                mock.patch.object(self.tool.time, "sleep"), \
                mock.patch.object(self.tool, "_notify_desktop") as banner, \
                mock.patch.object(self.tool, "_play_sound") as sound, \
                contextlib.redirect_stdout(buffer):
            self.assertEqual(self.tool.cmd_watch(self.team, args, None), 0)
        return buffer.getvalue(), banner, sound

    def test_watch_plays_one_sound_per_pass_and_prints_the_setup_note(self):
        first = {"key": "question:Q001", "kind": "question", "task": None, "text": "Q001 open"}
        second = {"key": "review:T001", "kind": "review", "task": "T001", "text": "T001 in review"}
        out, banner, sound = self.run_watch([[first, second], [first, second]], no_notify=False)
        self.assertEqual(banner.call_count, 2)  # one banner per item
        self.assertEqual(sound.call_count, 1)   # one sound for the pass; none for the quiet pass
        self.assertIn("Script Editor", out)
        self.assertIn("Do Not Disturb", out)

    def test_watch_no_notify_is_silent_and_prints_no_setup_note(self):
        item = {"key": "question:Q001", "kind": "question", "task": None, "text": "Q001 open"}
        out, banner, sound = self.run_watch([[item]], no_notify=True)
        self.assertEqual((banner.call_count, sound.call_count), (0, 0))
        self.assertNotIn("Script Editor", out)

    def test_watch_setup_note_is_macos_only(self):
        out, _, _ = self.run_watch([[]], no_notify=False, platform="linux")
        self.assertNotIn("Script Editor", out)

    def test_play_sound_does_not_wait_and_is_macos_only(self):
        with mock.patch.object(self.tool.sys, "platform", "darwin"), \
                mock.patch.object(shutil, "which", return_value="/usr/bin/afplay"), \
                mock.patch.object(self.tool.os.path, "isfile", return_value=True), \
                mock.patch.object(self.tool.subprocess, "Popen") as popen:
            self.assertTrue(self.tool._play_sound())
        self.assertEqual(popen.call_args[0][0], ["afplay", self.tool.ALERT_SOUND])
        with mock.patch.object(self.tool.sys, "platform", "linux"):
            self.assertFalse(self.tool._play_sound())

    def test_wait_survives_a_busy_lock_on_the_first_heartbeat(self):
        import argparse
        import contextlib
        import io
        self.join("a1")
        args = argparse.Namespace(timeout=0, interval=1)
        busy = self.tool.TeamError("lock busy", 3)
        buffer = io.StringIO()
        with mock.patch.object(self.tool, "acquire_lock", side_effect=busy), \
                contextlib.redirect_stdout(buffer):
            self.assertEqual(self.tool.cmd_wait(self.team, args, "a1"), 0)
        self.assertIn("NOTHING NEW", buffer.getvalue())

    def test_shutil_is_imported_at_the_top_of_the_tool(self):
        self.assertIs(self.tool.shutil, shutil)

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
