#!/usr/bin/env python3
"""Build the versioned, allowlisted Agent Coordination release archive."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release-manifest.json"
STEM = "agent-coordination-v{version}"


def load_manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data.get("version"), str) or not data["version"]:
        raise ValueError("manifest needs a non-empty version")
    for field in ("archive", "first_commit"):
        entries = data.get(field)
        if not isinstance(entries, list) or not entries or any(not isinstance(x, str) for x in entries):
            raise ValueError("manifest %s must be a non-empty list of paths" % field)
        if len(set(entries)) != len(entries):
            raise ValueError("manifest %s contains duplicate paths" % field)
        for entry in entries:
            path = PurePosixPath(entry)
            if path.is_absolute() or ".." in path.parts or "\\" in entry or str(path) != entry:
                raise ValueError("unsafe or non-canonical manifest path: %r" % entry)
    if set(data["archive"]) - set(data["first_commit"]):
        raise ValueError("every archive path must also be in first_commit")
    return data


def verify_files(data: dict) -> None:
    for relative in data["first_commit"]:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("allowlisted first-commit file missing or not regular: %s" % relative)
    for relative in data["archive"]:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("allowlisted archive file missing or not regular: %s" % relative)


def archive_bytes(data: dict) -> bytes:
    import io
    out = io.BytesIO()
    root_name = STEM.format(version=data["version"])
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for relative in sorted(data["archive"]):
            info = zipfile.ZipInfo(root_name + "/" + relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.internal_attr = 0
            info.extra = b""
            info.comment = b""
            zf.writestr(info, (ROOT / relative).read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9)
    return out.getvalue()


def validate_archive(payload: bytes, data: dict) -> None:
    root_name = STEM.format(version=data["version"])
    expected = {root_name + "/" + item for item in data["archive"]}
    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as zf:
        actual = set(zf.namelist())
        if actual != expected:
            raise ValueError("archive entries differ from allowlist; missing=%r extra=%r" %
                             (sorted(expected - actual), sorted(actual - expected)))
        if any(info.is_dir() for info in zf.infolist()):
            raise ValueError("archive must contain files only, under its single visible root")
        if len({name.split("/", 1)[0] for name in actual}) != 1:
            raise ValueError("archive must have one visible root")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="output ZIP (default: dist/<versioned stem>.zip)")
    parser.add_argument("--check-first-commit", action="store_true",
                        help="check that every explicit first-commit allowlist path exists")
    args = parser.parse_args(argv)
    data = load_manifest()
    verify_files(data)
    if args.check_first_commit:
        print("first-commit allowlist: %d files present" % len(data["first_commit"]))
    payload = archive_bytes(data)
    validate_archive(payload, data)
    output = args.output or ROOT / "dist" / (STEM.format(version=data["version"]) + ".zip")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + output.name + ".", suffix=".tmp", dir=str(output.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("built %s (%d files, %d bytes)" % (output, len(data["archive"]), len(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
