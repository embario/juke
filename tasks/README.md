# Tasks Directory Guide

This directory is the repo-native task board for humans and agents.

## How To Pick Work

1. Open `tasks/_index.md`.
2. Choose the highest-priority item with status `ready` (unless the user explicitly directs another task).
3. Set the task to `in_progress` and assign an owner.
4. Keep the task file updated with handoff notes.

## File Layout

- `tasks/_index.md`: canonical queue for active/discoverable work.
- `tasks/_template.md`: template for new task files.
- `tasks/<task-slug>.md|txt`: one file per task.
- `tasks/archives/`: completed/retired tasks.
- `tasks/TODO`: legacy scratch list; migrate items into structured task files over time.

## Status Values

- `ready`: unclaimed and actionable.
- `in_progress`: currently being worked.
- `blocked`: cannot proceed due dependency/decision.
- `review`: implementation done, awaiting validation.
- `done`: completed and ready to archive.

## Priority Values

- `p0`: urgent, production-impacting.
- `p1`: high priority.
- `p2`: normal priority.
- `p3`: low priority / backlog.

## Complexity Values

- Use a 1-5 scale (`1` smallest, `5` largest).
- Ranges are allowed (example: `2-3`) when uncertainty is intentional.
- Every active task should include an explicit complexity value.

## Minimum Task Contents

- Goal
- Scope
- Acceptance criteria
- Execution notes (files/commands/risks)
- Handoff notes (what changed, what is next, blockers)
