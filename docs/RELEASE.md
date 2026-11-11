# Release guide

This describes the release workflow for future maintainers. The source is public on GitHub at
`origin` and is licensed under the MIT License in the root `LICENSE` file. Version 0.2.0 is tagged
`v0.2.0` on `main`. A packaged download exists only once its GitHub Release is published; a draft
release is not public.

## Build and inspect the candidate

From the repository root, run:

```sh
python3 scripts/build_release.py --check-first-commit
```

This checks the first-commit allowlist and creates the deterministic allowlisted ZIP at
`dist/agent-coordination-v0.2.0.zip`, with files under the visible root
`agent-coordination-v0.2.0/`.

Run the extracted-package smoke test:

```sh
python3 scripts/smoke_release.py
```

It extracts to a temporary path containing spaces, initializes the packaged Event Page fixture,
then checks visible edits by two workers, handoff recovery, independent review, conflicting-claim
refusal, status output, and preservation of an unregistered file. The temporary extraction is
removed when the command exits.

## Validate the source tree

Run the full unit suite and concurrent simulation:

```sh
python3 -B -m unittest discover -s .agents/team/tests -v
python3 -B .agents/team/tests/simulate.py --report /tmp/agent-coordination-simulation.md
```

The smoke test should pass on the ZIP built above. Keep full logs and any simulation report under
the ignored `docs/agent-work/` directory for local review.

## Current gate status

- **Source unit suite:** passed locally, 241 tests.
- **Concurrent simulation:** passed locally, 14 scenarios.
- **Extracted package smoke:** passed locally on the `0.2.0` ZIP. The archive's 32 entries
  exactly matched the archive manifest and used the expected single visible root.
- **Two-chat extracted candidate trial:** Chat A and Chat B completed in a separate fresh
  extraction; static content checks passed. Independent review left T001 pending because browser
  wide/narrow visual checks remain unverified. The browser tool rejected the local file URL and
  prohibited a workaround.
- **License:** MIT License, with copyright © 2026 Ethan Siegel, as stated in the root `LICENSE` file.
- **Beginner and additional host trials:** not completed.
- **GitHub check:** the unit suite and simulation pass on Python 3.8 and 3.12; the build and smoke
  test pass on 3.12.
- **Manifest allowlist:** all 39 explicit manifest paths exist and are committed.

## Release procedure

For each release, only after the owner approves the final contents, archive, and validation:

1. Confirm the version in `release-manifest.json` and the workflow artifact name match the intended
   release version.
2. Run the build, extraction smoke, unit suite, and simulation above; review the output ZIP.
3. Commit only the reviewed first-commit allowlist, then create the matching annotated tag, for
   example `git tag -a v0.2.0 -m "Agent Coordination v0.2.0"`.
4. Push the approved branch and tag to the owner-selected remote. The current workflow runs on
   `main`, pull requests, or manual dispatch; it does not publish a GitHub Release or run on tag
   pushes.
5. Create a draft release in the selected hosting service, attach the reviewed
   `dist/agent-coordination-v0.2.0.zip`, and leave it unpublished until the owner approves it.

For 0.2.0, steps 1 to 4 are done: the tag `v0.2.0` is on `main` and pushed. Step 5 leaves a draft
GitHub Release holding the ZIP until the owner publishes it.
