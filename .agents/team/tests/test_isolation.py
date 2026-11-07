"""A nested project's launcher may execute only the kit used to initialize it."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import make_workspace


class KitIsolation(unittest.TestCase):
    def test_moved_kit_and_missing_inner_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, project = make_workspace(root / "Nested Kit")
            tool = kit / ".agents/team/team.py"
            subprocess.run([sys.executable, str(tool), "init"], cwd=project, check=True,
                           stdout=subprocess.PIPE)
            kit.rename(root / "Moved Kit")
            kit = root / "Moved Kit"
            project = kit / "proj"
            argv = [sys.executable, "team/team.py", "--help"]
            self.assertEqual(subprocess.run(argv, cwd=project, capture_output=True).returncode, 0)
            # A harmless sentinel stands in for another installed ancestor tool.
            outer = root / ".agents/team/team.py"
            outer.parent.mkdir(parents=True)
            outer.write_text("raise SystemExit(47)\n")
            (kit / ".agents/team/team.py").rename(kit / "temporarily-missing.py")
            result = subprocess.run(argv, cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, "launcher executed an unrelated ancestor tool")
            self.assertIn("--standalone", result.stderr)


class OldBoardCompatibility(unittest.TestCase):
    def test_legacy_globs_and_aliases_use_same_reservation_rules(self):
        import json

        with tempfile.TemporaryDirectory() as temp:
            kit, project = make_workspace(Path(temp))
            subprocess.run([sys.executable, str(kit / ".agents/team/team.py"), "init"],
                           cwd=project, check=True, capture_output=True)

            def run(*args, expected=0):
                r = subprocess.run([sys.executable, "team/team.py", *args], cwd=project,
                                   text=True, capture_output=True)
                self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
                return r.stdout + r.stderr

            (project / "src").mkdir()
            (project / "alias").symlink_to(project / "src", target_is_directory=True)
            for task_name, path in (("old", "src"), ("overlap", "src"), ("free", "docs")):
                run("add", "--agent", "user", "--title", task_name, "--desc", task_name,
                    "--files", path)
            for number, pattern in ((1, "alias/a*.py"), (2, "src/*b.py")):
                path = project / ("team/tasks/T%03d.json" % number)
                task = json.loads(path.read_text())
                task["files"] = [pattern]  # model serialized records written by an earlier kit
                path.write_text(json.dumps(task))
            run("claim", "T001", "--agent", "user")
            self.assertIn("T001", run("owner", "src/ab.py"))
            ready = run("next", "--agent", "user")
            self.assertIn("T003", ready)
            self.assertNotIn("T002", ready)
            self.assertIn("overlaps", run("claim", "T002", "--agent", "user", expected=2))
            run("claim", "T003", "--agent", "user")
            self.assertEqual(json.loads((project / "team/tasks/T001.json").read_text())["files"],
                             ["alias/a*.py"])
