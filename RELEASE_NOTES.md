# Release notes (draft)

**Version:** 0.1.0 draft
**Status:** Local release candidate; not approved for public distribution. The project is licensed under the MIT License.

This candidate packages a small Python 3.8+ standard-library task board for coordinating coding
agents in one project folder. It records task ownership, reserved paths, questions, handoffs, and
independent review without moving or rewriting the project's source files.

## Candidate contents

- `team.py` commands for setup, task lifecycle, file reservations, messages, handoffs, review,
  status, and consistency checks.
- Eight portable team skills for setup, joining, task creation, handoff, review, status, answers,
  and board diagnosis.
- Protocol and human documentation, plus an Event Page starter fixture for a fresh setup.
- Unit and concurrent-simulation checks.

## Validation recorded locally

- 184 unit tests passed on the development machine.
- All 11 concurrent simulation scenarios passed on the development machine.
- A two-agent interruption, handoff, and review trial is documented in the local work records.

These results are scoped local evidence. They do not establish support on every vendor host or an
uncoached beginner setup experience. Those trials remain open.

## Before any public distribution

- Review and approve the final release contents and package.
- Complete uncoached setup and any claimed vendor-host trials.
