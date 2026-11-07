"""Communication tests for team.py: msg, inbox, decide, discover, question, resolve, propose.
Run from .agents/team: python3 -m unittest tests.test_comms -v

Every test works in its own temporary fake workspace made by helpers.make_workspace; nothing is
written under the real .agents/team/.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

PER_SENDER = 50


def send_many_worker(tool_path, team_dir, agent, count, barrier, queue):
    """Wait at the barrier, then send `count` messages to all; report every exit code."""
    os.environ["TEAM_DIR"] = team_dir
    os.environ.pop("TEAM_AGENT", None)
    tool = helpers.load_tool(Path(tool_path))
    barrier.wait(timeout=60)
    codes = []
    for i in range(count):
        code, _, _ = helpers.run(tool, "msg", "--agent", agent, "--to", "all", "--kind", "info",
                                 "--text", "%s-%d" % (agent, i))
        codes.append(code)
    queue.put((agent, codes))


class CommsTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="team-comms-")
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

    def join(self, *ids):
        for agent in ids:
            self.ok("join", "--agent", agent)

    def msg(self, frm, to, text, kind="info", *extra):
        return self.main("msg", "--agent", frm, "--to", to, "--kind", kind, "--text", text, *extra)

    def lines(self, name):
        text = (self.team / name).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def agent(self, agent_id):
        return json.loads((self.team / "agents" / ("%s.json" % agent_id)).read_text())

    def question(self, qid):
        return json.loads((self.team / "questions" / ("%s.json" % qid)).read_text())

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


class ConcurrencyTests(CommsTestCase):
    def test_concurrent_messages_unique_ids(self):
        self.join("a", "b")
        results = self.spawn_all(send_many_worker, [
            (str(self.tool_path), str(self.team), agent, PER_SENDER) for agent in ("a", "b")])
        for agent, codes in results:
            self.assertEqual(codes, [0] * PER_SENDER, agent)
        rows = self.lines("messages.jsonl")
        self.assertEqual(len(rows), 2 * PER_SENDER)
        self.assertEqual([r["id"] for r in rows], list(range(1, 2 * PER_SENDER + 1)))
        self.assertEqual(len({r["id"] for r in rows}), 2 * PER_SENDER)
        for agent in ("a", "b"):
            self.assertEqual(sorted(int(r["text"].split("-")[1]) for r in rows
                                    if r["from"] == agent), list(range(PER_SENDER)))
        entries = [l for l in self.view("MESSAGES.md").splitlines() if l.startswith("- #")]
        self.assertEqual(len(entries), 2 * PER_SENDER)
        self.assertFalse((self.team / ".lock").exists())


class MessageTests(CommsTestCase):
    def test_direct_message_seen_only_by_recipient(self):
        self.join("a", "b", "c")
        code, out, err = self.msg("a", "b", "for b only", "finding", "--task", "T001")
        self.assertEqual(code, 0, err)
        self.assertIn("b", self.ok("inbox", "--agent", "b"))
        self.assertEqual(self.ok("inbox", "--agent", "c").strip(), "No new messages.")
        self.assertEqual(self.ok("inbox", "--agent", "a").strip(), "No new messages.")
        row = self.lines("messages.jsonl")[0]
        self.assertEqual(set(row), {"id", "at", "from", "to", "kind", "task", "text"})
        self.assertEqual((row["id"], row["from"], row["to"], row["kind"], row["task"], row["text"]),
                         (1, "a", "b", "finding", "T001", "for b only"))

    def test_inbox_prints_message_content(self):
        self.join("a", "b")
        self.msg("a", "b", "look at the lock", "warning")
        out = self.ok("inbox", "--agent", "b")
        self.assertIn("look at the lock", out)
        self.assertIn("[warning]", out)
        self.assertIn("from a", out)

    def test_all_seen_by_every_agent_once(self):
        self.join("a", "b", "c")
        self.msg("a", "all", "hello team")
        for agent in ("a", "b", "c"):
            self.assertIn("hello team", self.ok("inbox", "--agent", agent), agent)
            self.assertEqual(self.ok("inbox", "--agent", agent).strip(), "No new messages.")

    def test_cursor_advances_and_oldest_first(self):
        self.join("a", "b")
        self.msg("a", "b", "first")
        self.msg("a", "b", "second")
        out = self.ok("inbox", "--agent", "b")
        self.assertLess(out.index("first"), out.index("second"))
        self.assertEqual(self.agent("b")["inbox_cursor"], 2)
        self.msg("a", "b", "third")
        out = self.ok("inbox", "--agent", "b")
        self.assertIn("third", out)
        self.assertNotIn("first", out)
        self.assertEqual(self.agent("b")["inbox_cursor"], 3)

    def test_cursor_skips_messages_for_others(self):
        self.join("a", "b", "c")
        self.msg("a", "c", "not for b")
        self.assertEqual(self.ok("inbox", "--agent", "b").strip(), "No new messages.")
        self.assertEqual(self.agent("b")["inbox_cursor"], 0)

    def test_peek_does_not_advance(self):
        self.join("a", "b")
        self.msg("a", "b", "peeked")
        self.assertIn("peeked", self.ok("inbox", "--agent", "b", "--peek"))
        self.assertEqual(self.agent("b")["inbox_cursor"], 0)
        self.assertIn("peeked", self.ok("inbox", "--agent", "b"))
        self.assertEqual(self.agent("b")["inbox_cursor"], 1)
        self.assertEqual(self.ok("inbox", "--agent", "b", "--peek").strip(), "No new messages.")

    def test_status_unread_count_matches_inbox(self):
        self.join("a", "b")
        self.msg("a", "b", "x")
        self.assertIn("Unread messages for b: 1", self.ok("status", "--agent", "b"))
        self.ok("inbox", "--agent", "b")
        self.assertIn("Unread messages for b: 0", self.ok("status", "--agent", "b"))

    def test_to_user_refused(self):
        self.join("a")
        code, out, err = self.msg("a", "user", "hi user")
        self.assertEqual(code, 2)
        self.assertIn("refused:", err)
        self.assertIn("Run: team.py question --agent a --text", err)
        self.assertEqual(self.lines("messages.jsonl"), [])

    def test_to_unknown_agent_refused(self):
        self.join("a")
        code, _, err = self.msg("a", "ghost", "anyone?")
        self.assertEqual(code, 2)
        self.assertIn("refused:", err)
        self.assertEqual(self.lines("messages.jsonl"), [])

    def test_to_left_agent_allowed_and_waits_for_rejoin(self):
        self.join("a", "b")
        self.edit_status("b", "left")
        self.assertEqual(self.msg("a", "b", "welcome back")[0], 0)
        self.ok("join", "--agent", "b")
        self.assertIn("welcome back", self.ok("inbox", "--agent", "b"))

    def edit_status(self, agent_id, status):
        path = self.team / "agents" / ("%s.json" % agent_id)
        data = json.loads(path.read_text())
        data["status"] = status
        path.write_text(json.dumps(data))

    def test_to_recipient_in_other_case_reaches_stored_id(self):
        self.join("a", "bob")
        code, out, err = self.msg("a", "BOB", "case typo")
        self.assertEqual(code, 0, err)
        self.assertIn("to bob.", out)
        self.assertEqual(self.lines("messages.jsonl")[-1]["to"], "bob")
        self.assertIn("case typo", self.ok("inbox", "--agent", "bob"))

    def test_views_fold_newlines_into_one_line(self):
        self.join("a")
        self.msg("a", "all", "line one\nline two")
        self.ok("decide", "--agent", "a", "--title", "Pick\nlock", "--text", "why one\n\n  why two")
        self.ok("question", "--agent", "a", "--text", "ask one\nask two")
        self.ok("resolve", "Q001", "--agent", "user", "--text", "answer one\nanswer two")
        self.assertEqual(self.lines("messages.jsonl")[0]["text"], "line one\nline two")
        for name, folded in (("MESSAGES.md", "line one line two"), ("BOARD.md", "line one line two"),
                             ("DECISIONS.md", "Pick lock: why one why two"),
                             ("QUESTIONS.md", "ask one ask two"),
                             ("QUESTIONS.md", "Answer: answer one answer two")):
            text = self.view(name)
            self.assertIn(folded, text, name)
            for second in ("line two", "lock", "why two", "ask two", "answer two"):
                self.assertFalse(any(l.startswith(second) for l in text.splitlines()), (name, second))

    def test_bad_kind_and_missing_text_exit_1(self):
        self.join("a")
        code, _, _ = self.msg("a", "all", "x", "gossip")
        self.assertEqual(code, 1)
        code, _, _ = self.main("msg", "--agent", "a", "--to", "all", "--kind", "info")
        self.assertEqual(code, 1)

    def test_unknown_or_left_sender_refused(self):
        self.join("a")
        code, _, err = self.msg("nobody", "all", "x")
        self.assertEqual(code, 2)
        self.assertIn("join", err)
        self.edit_status("a", "left")
        self.assertEqual(self.msg("a", "all", "x")[0], 2)

    def test_user_can_send_but_has_no_inbox(self):
        self.join("a")
        self.assertEqual(self.msg("user", "a", "from the human")[0], 0)
        self.assertIn("from the human", self.ok("inbox", "--agent", "a"))
        code, _, err = self.main("inbox", "--agent", "user")
        self.assertEqual(code, 1)
        self.assertIn("MESSAGES.md", err)

    def test_messages_view_lists_all_newest_last(self):
        self.join("a")
        self.msg("a", "all", "one")
        self.msg("a", "all", "two")
        text = self.view("MESSAGES.md")
        self.assertTrue(text.startswith("<!-- generated by team.py; do not edit -->"))
        self.assertLess(text.index("one"), text.index("two"))
        self.assertIn("#2", text)


class RecordTests(CommsTestCase):
    def test_decide_logs_and_announces(self):
        self.join("a", "b")
        self.ok("decide", "--agent", "a", "--title", "Use JSON", "--text", "Because it diffs well")
        row = self.lines("decisions.jsonl")[0]
        self.assertEqual(set(row), {"at", "by", "title", "text", "path"})
        self.assertEqual((row["by"], row["title"], row["text"], row["path"]),
                         ("a", "Use JSON", "Because it diffs well", None))
        self.assertIn("Use JSON", self.view("DECISIONS.md"))
        self.assertIn("Because it diffs well", self.view("DECISIONS.md"))
        announced = self.lines("messages.jsonl")[0]
        self.assertEqual((announced["to"], announced["kind"], announced["from"]),
                         ("all", "info", "a"))
        self.assertIn("Use JSON", announced["text"])
        self.assertIn("Use JSON", self.ok("inbox", "--agent", "b"))

    def test_discover_logs_with_and_without_path(self):
        self.join("a")
        self.ok("discover", "--agent", "a", "--text", "Config is loaded twice",
                "--path", "src/config.py")
        self.ok("discover", "--agent", "a", "--text", "Tests need network")
        first, second = self.lines("discoveries.jsonl")
        self.assertEqual(set(first), {"at", "by", "title", "text", "path"})
        self.assertEqual((first["title"], first["path"]), (None, "src/config.py"))
        self.assertIsNone(second["path"])
        text = self.view("DISCOVERIES.md")
        self.assertIn("src/config.py", text)
        self.assertIn("Tests need network", text)
        self.assertEqual(self.lines("messages.jsonl"), [])

    def test_question_resolve_round_trip(self):
        self.join("a")
        out = self.ok("question", "--agent", "a", "--text", "Which database?", "--task", "T001")
        self.assertIn("Q001", out)
        q = self.question("Q001")
        self.assertEqual(set(q), {"id", "at", "by", "task", "text", "status", "resolution"})
        self.assertEqual((q["id"], q["by"], q["task"], q["text"], q["status"], q["resolution"]),
                         ("Q001", "a", "T001", "Which database?", "open", None))
        text = self.view("QUESTIONS.md")
        self.assertIn("Which database?", text)
        self.assertLess(text.index("## Open (1)"), text.index("Which database?"))
        self.assertIn("## Resolved (0)", text)

        self.ok("resolve", "Q001", "--agent", "user", "--text", "SQLite")
        q = self.question("Q001")
        self.assertEqual((q["status"], q["resolution"]), ("resolved", "SQLite"))
        text = self.view("QUESTIONS.md")
        self.assertIn("## Open (0)", text)
        self.assertLess(text.index("## Resolved (1)"), text.index("Which database?"))
        self.assertIn("SQLite", text)
        told = self.ok("inbox", "--agent", "a")
        self.assertIn("Q001 resolved: SQLite", told)

    def test_question_ids_increase(self):
        self.join("a")
        self.assertIn("Q001", self.ok("question", "--agent", "a", "--text", "one"))
        self.assertIn("Q002", self.ok("question", "--agent", "a", "--text", "two"))
        self.assertIsNone(self.question("Q002")["task"])

    def test_resolve_by_agent_tells_asker_not_user_questions(self):
        self.join("a", "b")
        self.ok("question", "--agent", "a", "--text", "ask")
        self.ok("resolve", "Q001", "--agent", "b", "--text", "answer")
        self.assertIn("Q001 resolved: answer", self.ok("inbox", "--agent", "a"))
        self.ok("question", "--agent", "user", "--text", "user's own question")
        before = len(self.lines("messages.jsonl"))
        self.ok("resolve", "Q002", "--agent", "user", "--text", "done")
        self.assertEqual(len(self.lines("messages.jsonl")), before)

    def test_resolve_errors(self):
        self.join("a")
        code, _, err = self.main("resolve", "Q009", "--agent", "a", "--text", "x")
        self.assertEqual(code, 1)
        self.assertIn("Q009", err)
        self.assertEqual(self.main("resolve", "bogus", "--agent", "a", "--text", "x")[0], 1)
        self.ok("question", "--agent", "a", "--text", "q")
        self.ok("resolve", "Q001", "--agent", "a", "--text", "first")
        code, _, err = self.main("resolve", "Q001", "--agent", "a", "--text", "second")
        self.assertEqual(code, 1)
        self.assertEqual(self.question("Q001")["resolution"], "first")

    def test_propose_creates_question_and_message(self):
        self.join("a", "b")
        out = self.ok("propose", "--agent", "a", "--title", "Drop review", "--text", "Too slow")
        self.assertIn("Q001", out)
        q = self.question("Q001")
        self.assertEqual(q["status"], "open")
        self.assertEqual(q["by"], "a")
        self.assertEqual(q["text"], "PLAN CHANGE PROPOSAL: Drop review \u2014 Too slow")
        self.assertIn("PLAN CHANGE PROPOSAL: Drop review", self.view("QUESTIONS.md"))
        announced = self.lines("messages.jsonl")
        self.assertEqual(len(announced), 1)
        self.assertEqual((announced[0]["to"], announced[0]["kind"]), ("all", "info"))
        self.assertIn("Drop review", announced[0]["text"])
        self.assertIn("Drop review", self.ok("inbox", "--agent", "b"))

    def test_user_may_run_record_commands(self):
        self.ok("decide", "--agent", "user", "--title", "T", "--text", "x")
        self.ok("discover", "--agent", "user", "--text", "x")
        self.ok("question", "--agent", "user", "--text", "x")
        self.ok("propose", "--agent", "user", "--title", "T", "--text", "x")
        self.assertEqual([p.name for p in (self.team / "agents").glob("*.json")], [])

    def test_record_commands_refuse_unknown_agent(self):
        for argv in (["decide", "--title", "T", "--text", "x"], ["discover", "--text", "x"],
                     ["question", "--text", "x"], ["propose", "--title", "T", "--text", "x"],
                     ["resolve", "Q001", "--text", "x"], ["inbox"]):
            code, _, err = self.main(argv[0], "--agent", "ghost", *argv[1:])
            self.assertEqual(code, 2, argv)
            self.assertIn("join", err)

    def test_heartbeat_on_comms_commands(self):
        self.join("a")
        path = self.team / "agents" / "a.json"
        data = json.loads(path.read_text())
        data["last_seen"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(data))
        self.ok("inbox", "--agent", "a")
        self.assertNotEqual(self.agent("a")["last_seen"], "2000-01-01T00:00:00+00:00")


class RepairTests(CommsTestCase):
    """Added by the review-repair round (REVIEW.md of 2026-10-24); the finding is named per test."""

    def test_question_says_how_the_user_answers(self):  # finding 1
        self.join("a")
        out = self.ok("question", "--agent", "a", "--text", "Which port?")
        self.assertIn('resolve Q001 --agent user --text "..."', out)
        self.assertNotIn("answers in team/QUESTIONS.md", out)
        view = self.view("QUESTIONS.md")
        self.assertIn("resolve <QID> --agent user", view)
        self.assertIn("anything typed here is lost", view)

    def test_decide_refuses_a_repeated_title(self):  # finding 4, ruling 2
        self.join("a", "b")
        self.ok("decide", "--agent", "a", "--title", "Initial task breakdown", "--text", "x")
        code, _, err = self.main("decide", "--agent", "b", "--title", "Initial task breakdown",
                                 "--text", "y")
        self.assertEqual(code, 2, err)
        self.assertIn("decided by a at", err)
        self.assertIn("Run: team.py status --agent b", err)
        self.assertEqual(len(self.lines("decisions.jsonl")), 1)
        self.ok("decide", "--agent", "b", "--title", "Another title", "--text", "z")

    def test_append_after_a_partial_line_keeps_the_new_entry(self):  # finding 14
        self.join("a", "b")
        self.assertEqual(self.msg("a", "all", "first")[0], 0)
        with open(str(self.team / "messages.jsonl"), "a", encoding="utf-8") as handle:
            handle.write('{"id": 2, "at": "crashed mid-wri')  # no newline: a crashed append
        self.assertEqual(self.msg("a", "all", "after the crash")[0], 0)
        inbox = self.ok("inbox", "--agent", "b")
        self.assertIn("first", inbox)
        self.assertIn("after the crash", inbox)


if __name__ == "__main__":
    unittest.main()
