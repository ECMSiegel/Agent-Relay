"""Tests for optional task worktrees (config "worktrees": true).
Run from .agents/team: python3 -m unittest tests.test_worktrees -v

Each test builds its own temporary git repo as the project folder; nothing touches the real repo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lifecycle import LifecycleTestCase  # noqa: E402


def git(folder, *argv):
    result = subprocess.run(["git", "-C", str(folder)] + list(argv), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True)
    assert result.returncode == 0, "git %s failed: %s" % (argv, result.stderr)
    return result.stdout.strip()


class WorktreeTestCase(LifecycleTestCase):
    worktrees = True

    def setUp(self):
        super().setUp()
        git(self.project, "init", "-q")
        git(self.project, "config", "user.name", "Test")
        git(self.project, "config", "user.email", "test@example.com")
        (self.project / "readme.txt").write_text("hello\n")
        git(self.project, "add", "readme.txt")
        git(self.project, "commit", "-q", "-m", "first")
        self.base = git(self.project, "rev-parse", "--abbrev-ref", "HEAD")
        self.set_flag(self.worktrees)

    def set_flag(self, value):
        path = self.team / "config.json"
        config = json.loads(path.read_text())
        config["worktrees"] = value
        path.write_text(json.dumps(config, indent=2))

    def wt(self, task_id="T001"):
        return self.project / "team" / "worktrees" / task_id

    def commit_in(self, task_id, name, text="x\n"):
        (self.wt(task_id) / name).write_text(text)
        git(self.wt(task_id), "add", name)
        git(self.wt(task_id), "commit", "-q", "-m", "add " + name)


class WorktreeTests(WorktreeTestCase):
    def test_claim_creates_worktree_and_prints_paths(self):
        self.join("a1")
        task_id = self.add()
        out = self.ok("claim", task_id, "--agent", "a1")
        folder = self.wt(task_id).resolve()
        self.assertTrue((folder / "readme.txt").is_file())
        self.assertEqual(git(folder, "rev-parse", "--abbrev-ref", "HEAD"), "team/T001")
        self.assertIn(str(folder), out)
        self.assertIn(str((self.team / "team.py").resolve()), out)
        record = self.task(task_id)["worktree"]
        self.assertEqual(record, {"path": "team/worktrees/T001", "branch": "team/T001",
                                  "base": self.base})
        self.assertIn("team/", (self.project / ".git" / "info" / "exclude").read_text())
        self.assertEqual(git(self.project, "status", "--porcelain"), "")

    def test_handoff_then_second_agent_reuses_folder_and_edits(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        (self.wt(task_id) / "scratch.txt").write_text("half done\n")
        self.ok("handoff", task_id, "--agent", "a1", "--note", "stopping\nteam/worktrees: x")
        out = self.ok("claim", task_id, "--agent", "a2")
        self.assertEqual((self.wt(task_id) / "scratch.txt").read_text(), "half done\n")
        self.assertIn(str(self.wt(task_id).resolve()), out)

    def test_done_refused_with_uncommitted_edits(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        (self.wt(task_id) / "new.txt").write_text("loose\n")
        self.refused("done", task_id, "--agent", "a1", "--note", "n")
        self.assertEqual(self.task(task_id)["status"], "in_progress")
        git(self.wt(task_id), "add", "new.txt")
        git(self.wt(task_id), "commit", "-q", "-m", "c")
        self.ok("done", task_id, "--agent", "a1", "--note", "n")
        self.assertEqual(self.task(task_id)["status"], "review")

    def test_approve_merges_and_removes_worktree(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.commit_in(task_id, "feature.txt")
        self.ok("done", task_id, "--agent", "a1", "--note", "n")
        self.assertFalse((self.project / "feature.txt").exists())
        self.ok("review", task_id, "--agent", "a2", "--approve", "--note", "ok")
        self.assertEqual((self.project / "feature.txt").read_text(), "x\n")
        self.assertFalse(self.wt(task_id).exists())
        self.assertEqual(git(self.project, "branch", "--list", "team/T001"), "")
        self.assertEqual(self.task(task_id)["status"], "done")
        self.assertTrue(self.task(task_id)["worktree"]["merged"])
        self.assertEqual(git(self.project, "status", "--porcelain"), "")

    def test_merge_conflict_keeps_review_and_main_clean(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.commit_in(task_id, "readme.txt", "from task\n")
        self.ok("done", task_id, "--agent", "a1", "--note", "n")
        (self.project / "readme.txt").write_text("from main\n")
        git(self.project, "commit", "-q", "-am", "main change")
        err = self.refused("review", task_id, "--agent", "a2", "--approve", "--note", "ok")
        self.assertIn("merge conflict", err)
        self.assertEqual(self.task(task_id)["status"], "review")
        self.assertEqual(git(self.project, "status", "--porcelain"), "")
        self.assertEqual((self.project / "readme.txt").read_text(), "from main\n")
        self.assertTrue(self.wt(task_id).exists())

    def test_merge_refused_by_uncommitted_edits_is_not_called_a_conflict(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.commit_in(task_id, "readme.txt", "from task\n")
        self.ok("done", task_id, "--agent", "a1", "--note", "n")
        (self.project / "readme.txt").write_text("loose edit\n")
        err = self.refused("review", task_id, "--agent", "a2", "--approve", "--note", "ok")
        self.assertNotIn("merge conflict", err)
        self.assertIn("uncommitted edits", err)
        self.assertEqual(self.task(task_id)["status"], "review")
        self.assertEqual((self.project / "readme.txt").read_text(), "loose edit\n")
        self.assertTrue(self.wt(task_id).exists())

    def test_reclaim_reuses_existing_worktree(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        (self.wt(task_id) / "scratch.txt").write_text("half done\n")
        out = self.ok("reclaim", task_id, "--agent", "user")
        self.assertIn("Worktree ready: %s" % self.wt(task_id).resolve(), out)
        self.assertEqual((self.wt(task_id) / "scratch.txt").read_text(), "half done\n")
        self.assertEqual(self.task(task_id)["worktree"]["path"], "team/worktrees/T001")

    def test_approve_refused_when_base_branch_not_checked_out(self):
        self.join("a1", "a2")
        task_id = self.to_in_progress("a1")
        self.commit_in(task_id, "feature.txt")
        self.ok("done", task_id, "--agent", "a1", "--note", "n")
        git(self.project, "checkout", "-q", "-b", "other")
        self.refused("review", task_id, "--agent", "a2", "--approve", "--note", "ok")
        self.assertEqual(self.task(task_id)["status"], "review")

    def test_no_review_done_merges(self):
        self.join("a1")
        task_id = self.add("Work", "--no-review")
        self.ok("claim", task_id, "--agent", "a1")
        self.commit_in(task_id, "feature.txt")
        self.ok("done", task_id, "--agent", "a1", "--note", "n")
        self.assertTrue((self.project / "feature.txt").is_file())
        self.assertFalse(self.wt(task_id).exists())

    def test_absolute_worktree_path_maps_to_project_path(self):
        self.join("a1")
        task_id = self.add("Work", "--files", "src/a.py")
        self.ok("claim", task_id, "--agent", "a1")
        inside = str(self.wt(task_id).resolve() / "src" / "a.py")
        self.assertIn("via task %s" % task_id, self.ok("owner", inside))
        self.ok("files", "add", task_id, "--agent", "a1", str(self.wt(task_id).resolve() / "lib" / "b.py"))
        self.assertIn("lib/b.py", self.task(task_id)["files"])

    def test_show_prints_worktree_and_review_lines(self):
        self.join("a1")
        task_id = self.add()
        self.ok("claim", task_id, "--agent", "a1")
        out = self.ok("show", task_id)
        self.assertIn("Worktree: %s" % self.wt(task_id).resolve(), out)
        self.assertIn("Review with: git diff %s...team/T001" % self.base, out)

    def test_refused_when_project_is_not_repo_top(self):
        self.join("a1")
        task_id = self.add()
        # make the project a sub-folder of a repo: move .git up is awkward, so rebuild
        outer = self.project.parent / "outer"
        inner = outer / "proj2"
        inner.mkdir(parents=True)
        git(outer, "init", "-q")
        os.rename(str(self.team), str(inner / "team"))
        self.team = inner / "team"
        os.environ["TEAM_DIR"] = str(self.team)
        err = self.refused("claim", task_id, "--agent", "a1")
        self.assertIn("top", err)
        self.assertEqual(self.task(task_id)["status"], "available")

    def test_refused_when_team_files_are_tracked(self):
        self.join("a1")
        task_id = self.add()
        git(self.project, "add", "-f", "team/config.json")
        err = self.refused("claim", task_id, "--agent", "a1")
        self.assertIn("tracked", err)
        self.assertEqual(self.task(task_id)["status"], "available")


class WorktreesOffTests(WorktreeTestCase):
    worktrees = False

    def test_flag_off_changes_nothing(self):
        self.join("a1")
        task_id = self.to_in_progress("a1")
        self.assertFalse((self.project / "team" / "worktrees").exists())
        self.assertNotIn("worktree", self.task(task_id))
        self.assertNotIn("Worktree:", self.ok("show", task_id))
        self.ok("done", task_id, "--agent", "a1", "--note", "n")


if __name__ == "__main__":
    unittest.main()
