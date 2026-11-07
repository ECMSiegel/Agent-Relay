#!/usr/bin/env python3
"""Extract a release into a random path with spaces and exercise its local workflow."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release-manifest.json"


def invoke(command: list[str], cwd: Path, expected: int = 0) -> str:
    proc = subprocess.run(command, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)
    print("$ (cd %s && %s)" % (cwd, " ".join(command)))
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != expected:
        raise RuntimeError("command returned %d, expected %d: %r" %
                           (proc.returncode, expected, command))
    return proc.stdout + proc.stderr


SCHEDULE_ITEMS = (
    ("17:30", "5:30 PM", "Check-in & harbor welcome", "Find your name tag, grab a program, and get settled."),
    ("17:45", "5:45 PM", "Welcome from the neighborhood", "Meet the organizers and hear a little about the evening."),
    ("18:00", "6:00 PM", "Opening toast", "Raise a glass to the people and places that make Harborview home."),
    ("18:15", "6:15 PM", "Make-and-share activity", "Create a postcard for a neighbor or a note for the community wall."),
    ("18:45", "6:45 PM", "Harbor supper break", "Enjoy a light supper, refreshments, and a chance to catch up."),
    ("19:00", "7:00 PM", "Community performances", "Local musicians and neighbors share a short set by the water."),
    ("19:45", "7:45 PM", "Closing thanks", "One last toast and a warm send-off for the evening."),
    ("20:00", "8:00 PM", "Event ends", "Safe travels home, and we will see you around the harbor."),
)


def append_schedule_items(path: Path, items: tuple) -> None:
    source = path.read_text(encoding="utf-8")
    if len(re.findall(r'<time\b[^>]*>\s*\d{1,2}:\d{2}\s*[AP]M\s*</time>', source,
                      flags=re.IGNORECASE)) < 2:
        raise RuntimeError("starter page no longer has its two visible schedule rows")
    rows = "".join(
        '        <li>\n          <time datetime="%s">%s</time>\n'
        '          <div><h3>%s</h3><p>%s</p></div>\n        </li>\n' % item
        for item in items
    )
    match = re.search(r"</ol\s*>", source, flags=re.IGNORECASE)
    if not match:
        raise RuntimeError("cannot find schedule list close tag in Event Page")
    source = source[:match.start()] + rows + source[match.start():]
    path.write_text(source, encoding="utf-8")


def visible_text(path: Path) -> str:
    parser = VisibleText()
    parser.feed(path.read_text(encoding="utf-8"))
    return " ".join(parser.parts)


def visible_times(text: str) -> list[str]:
    accepted = {item[1] for item in SCHEDULE_ITEMS}
    return [value for value in re.findall(r"\b\d{1,2}:\d{2}\s*[AP]M\b", text)
            if value in accepted]


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?",
                        help="ZIP from scripts/build_release.py; default is dist/<version>.zip")
    parser.add_argument("--temp-parent", type=Path, help="optional parent for the random smoke directory")
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    archive = args.archive or ROOT / "dist" / ("agent-coordination-v%s.zip" % manifest["version"])
    archive = archive.resolve()
    if not archive.is_file():
        raise FileNotFoundError("release archive not found: %s" % archive)

    with tempfile.TemporaryDirectory(prefix="agent kit smoke with spaces ", dir=args.temp_parent) as scratch:
        scratch_path = Path(scratch)
        with zipfile.ZipFile(archive) as zf:
            root_names = {name.split("/", 1)[0] for name in zf.namelist()}
            expected_root = "agent-coordination-v%s" % manifest["version"]
            if root_names != {expected_root}:
                raise RuntimeError("unexpected archive root(s): %r" % sorted(root_names))
            zf.extractall(scratch_path)
        extracted = scratch_path / expected_root
        project = extracted / "examples" / "Event Page"
        html = project / "index.html"
        if not html.is_file():
            raise RuntimeError("packaged Event Page index.html is missing")
        starter_text = visible_text(html)
        if not all(value in starter_text for value in
                   ("Harbor Lights Community Night", "Saturday, June 12, 2027", "Pier 8 Community Hall")):
            raise RuntimeError("starter Event Page is missing its event title, date, or venue")
        if visible_times(starter_text) != ["5:30 PM", "5:45 PM"]:
            raise RuntimeError("walkthrough starter must show only check-in at 5:30 and welcome at 5:45")
        protected = project / "organizer-notes.txt"
        protected.write_text("independent event page content\n", encoding="utf-8")

        # Mirror the documented setup route: initialize from Event Page, then use its own launcher.
        invoke([sys.executable, "../../.agents/team/team.py", "init"], project)
        local = [sys.executable, "team/team.py"]
        a_output = invoke(local + ["join", "--label", "Smoke worker A"], project)
        worker_a = re.search(r"You are ([\w-]+)", a_output).group(1)

        add = invoke(local + ["add", "--agent", "user", "--title", "Complete the event schedule",
                              "--desc", "Complete all eight event schedule rows in index.html.",
                              "--files", "index.html"], project)
        task_id = re.search(r"\b(T\d+)\b", add).group(1)
        invoke(local + ["claim", task_id, "--agent", worker_a], project)
        invoke(local + ["start", task_id, "--agent", worker_a], project)
        append_schedule_items(html, SCHEDULE_ITEMS[2:4])
        intermediate = visible_text(html)
        if visible_times(intermediate) != [item[1] for item in SCHEDULE_ITEMS[:4]]:
            raise RuntimeError("first worker's visible partial schedule should contain the first four rows")
        in_progress_note = "The rest of the program is being finalized."
        if in_progress_note not in intermediate:
            raise RuntimeError("the starter note should remain while the first worker's task is in progress")
        partial_task = invoke(local + ["show", task_id, "--agent", worker_a, "--full"], project)
        if "Status: in_progress" not in partial_task:
            raise RuntimeError("the first worker must hand off a task that is still in progress")
        invoke(local + ["handoff", task_id, "--agent", worker_a, "--note",
                        "The 6:45 PM supper break, 7:00 PM performances, 7:45 PM closing thanks, and 8:00 PM event end remain. Remove the rest-of-program note. index.html: uncommitted edits"], project)
        invoke(local + ["check-exit", "--agent", worker_a], project)
        invoke(local + ["leave", "--agent", worker_a], project)
        b_output = invoke(local + ["join", "--label", "Smoke worker B"], project)
        worker_b = re.search(r"You are ([\w-]+)", b_output).group(1)
        invoke(local + ["claim", task_id, "--agent", worker_b], project)
        handoff = invoke(local + ["show", task_id, "--agent", worker_b, "--full"], project)
        if "index.html: uncommitted edits" not in handoff or "6:45 PM supper break" not in handoff:
            raise RuntimeError("the second worker could not read the first worker's handoff note")
        invoke(local + ["start", task_id, "--agent", worker_b], project)
        append_schedule_items(html, SCHEDULE_ITEMS[4:])
        source = html.read_text(encoding="utf-8")
        note_markup = '<p class="schedule-note">The opening is confirmed. The rest of the program is being finalized.</p>'
        if source.count(note_markup) != 1:
            raise RuntimeError("the second worker must find exactly one starter note to remove")
        html.write_text(source.replace(note_markup, "", 1), encoding="utf-8")
        if "rest of the program" in html.read_text(encoding="utf-8").lower():
            raise RuntimeError("the second worker's final edit did not remove the starter note")
        invoke(local + ["done", task_id, "--agent", worker_b, "--note",
                        "Added the remaining schedule rows and checked all eight visible times in order."], project)
        visible_output = visible_text(html)
        if visible_times(visible_output) != [item[1] for item in SCHEDULE_ITEMS]:
            raise RuntimeError("final visible Event Page schedule is incomplete or out of order")
        if not all(item[2] in visible_output for item in SCHEDULE_ITEMS):
            raise RuntimeError("final visible Event Page is missing one or more schedule item titles")
        if not all(value in visible_output for value in
                   ("Harbor Lights Community Night", "Saturday, June 12, 2027", "Pier 8 Community Hall")):
            raise RuntimeError("final Event Page is missing its event title, date, or venue")
        reviewer_output = invoke(local + ["join", "--label", "Smoke reviewer"], project)
        reviewer = re.search(r"You are ([\w-]+)", reviewer_output).group(1)
        review_result = invoke(local + ["review", task_id, "--agent", reviewer, "--approve",
                                        "--note", "Independently checked title, date, venue, and all eight visible schedule rows in order."], project)
        if "approved" not in review_result:
            raise RuntimeError("independent review did not approve the final visible output")

        contest = invoke(local + ["add", "--agent", "user", "--title", "Contested claim",
                                  "--desc", "Exactly one worker may claim this.", "--files", "claim.txt"], project)
        contest_id = re.search(r"\b(T\d+)\b", contest).group(1)
        def claim(agent: str) -> subprocess.CompletedProcess:
            return subprocess.run(local + ["claim", contest_id, "--agent", agent], cwd=str(project),
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, (worker_b, reviewer)))
        for agent, result in zip((worker_b, reviewer), results):
            print("$ (cd %s && %s)" % (project, " ".join(local + ["claim", contest_id, "--agent", agent])))
            print((result.stdout + result.stderr).rstrip())
        if sorted(result.returncode for result in results) != [0, 2]:
            raise RuntimeError("conflicting claims must have exactly one winner and one refusal; got %r" %
                               [result.returncode for result in results])
        status = invoke(local + ["status"], project)
        if "Contested claim" not in status or "Complete the event schedule" not in status:
            raise RuntimeError("visible status output is missing the smoke tasks")
        if protected.read_text(encoding="utf-8") != "independent event page content\n":
            raise RuntimeError("an independent, unregistered project file was changed")
        print("PASS: extracted-space starter setup, visible partial schedule, leave/handoff recovery, final-page review, conflicting claims, status output, and file preservation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
