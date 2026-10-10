#!/usr/bin/env python3
"""Give a task to a fleet session on the right model (see docs/agent-pr-pipeline-protocol.md, section 2b).

Severity decides the model. A P0 or P1 task runs on the session's "raised" profile, anything else on
its default profile (the table is PROFILES in pipeline_gate.py). This script stores the profile on
the session, restarts the session if the profile differs and the session is idle, and then sends
the task with `agent-deck session send <session> -queue`.

  assign_task.py juke-implementer-2 P1 "Fix the red base build: ..."
  assign_task.py --batch tasks.json          # [{"session": ..., "severity": "P2", "task": ...}, ...]
  assign_task.py --dry-run ...               # print what would run; change nothing

Several tasks: each session's tasks are ordered P0 to P4 and grouped by profile, so a session
switches models as few times as possible. A switch restarts the session, so it only happens while
the session is idle. Only the first profile group of each session is sent in one run; the rest is
listed as deferred, to be assigned again once the session has finished and is idle.

Safety:
  * The only text sent is the task text given on the command line or in the batch file, which the
    owner or the conductor wrote. This script never reads GitHub, so PR titles, bodies and
    comments (untrusted text) cannot reach a session through it.
  * A session that may not take P0/P1 work (no raised profile) is refused; nothing is sent.
  * Queued sends to Codex sessions can be left typed but not submitted. After sending to a Codex
    session the script waits and presses Enter in its tmux pane if the input box still shows the
    task (same check as the gate).

Exit codes: 0 everything sent, 1 agent-deck failure (including a send that was not delivered or a
restart that failed; the restart is remembered and retried), 2 usage error (nothing sent),
3 something was deferred or could not be confirmed as submitted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline_gate as pg  # noqa: E402

TASK_MARKER = "[assign-task]"


def task_message(session: str, severity: str, text: str) -> str:
    return f"{TASK_MARKER} {severity} task for {session}. The task text follows.\n\n{text}"


def parse_tasks(args) -> "tuple[list, list]":
    """([(session, severity index, text)], [errors]) from the command line or the batch file."""
    raw, errors = [], []
    if args.batch:
        try:
            text = sys.stdin.read() if args.batch == "-" else Path(args.batch).read_text()
            data = json.loads(text)
        except (OSError, ValueError) as exc:
            return [], [f"could not read batch file: {exc}"]
        if not isinstance(data, list):
            return [], ["batch file must hold a JSON list of {session, severity, task}"]
        for item in data:
            if not isinstance(item, dict):
                errors.append("batch entries must be objects with session, severity and task")
                continue
            raw.append((item.get("session"), item.get("severity"), item.get("task")))
    if args.task:
        if len(args.task) != 3:
            return [], ["give SESSION SEVERITY TASK, or --batch FILE"]
        raw.append(tuple(args.task))
    if not raw and not errors:
        errors.append("no task given: SESSION SEVERITY TASK, or --batch FILE")

    tasks = []
    for session, severity, text in raw:
        if session not in pg.PROFILES:
            errors.append(f"unknown session {session!r} (known: {', '.join(sorted(pg.PROFILES))})")
        elif severity not in pg.SEVERITY_LABELS:
            errors.append(f"{session}: severity must be one of {', '.join(pg.SEVERITY_LABELS)}, not {severity!r}")
        elif not isinstance(text, str) or not text.strip():
            errors.append(f"{session}: the task text is empty")
        elif pg.profile_for(session, pg.SEVERITY_LABELS.index(severity)) is None:
            errors.append(f"{session} never takes P0/P1 work; give this {severity} task to another session")
        else:
            tasks.append((session, pg.SEVERITY_LABELS.index(severity), text))
    return tasks, errors


def batches(tasks: list) -> dict:
    """{session: [[(sev, text), ...], ...]}: each session's tasks P0 to P4, grouped by profile."""
    out = {}
    for session in dict.fromkeys(s for s, _, _ in tasks):
        mine = sorted(((sev, text) for s, sev, text in tasks if s == session), key=lambda item: item[0])
        groups = []
        for sev, text in mine:
            profile = pg.profile_for(session, sev)
            if groups and groups[-1][0] == profile:
                groups[-1][1].append((sev, text))
            else:
                groups.append((profile, [(sev, text)]))
        out[session] = [group for _, group in groups]
    return out


def confirm_codex_sends(run, pending: dict, fleet: dict, wait: float, poll: float, sleep, say) -> bool:
    """Wait for queued sends to a Codex session to be submitted, pressing Enter when needed.

    pending: {send id: session}. Returns "ok" when every send was submitted, "failed" when
    agent-deck reported that one was not delivered, else "unconfirmed". Only a send that
    agent-deck reports as submitted, or whose text has left the input box, counts as submitted.
    """
    nudges = {send_id: 0 for send_id in pending}
    waited, failed = 0.0, False
    while pending:
        for send_id, session in list(pending.items()):
            tmux = (fleet.get(session) or {}).get("tmux", "")
            result = pg.nudge_send(run, send_id, tmux, TASK_MARKER, dry_run=nudges[send_id] >= pg.MAX_NUDGES)
            if result == "nudged":
                nudges[send_id] += 1
                say(f"pressed Enter in {session} to submit the typed task")
            elif result == "done":
                del pending[send_id]
            elif result == "failed":
                say(f"failed: send {send_id} to {session} was not delivered; assign the task again")
                del pending[send_id]
                failed = True
        if not pending or waited >= wait:
            break
        sleep(poll)
        waited += poll
    for send_id, session in pending.items():
        say(f"not confirmed: send {send_id} to {session} was not submitted; check `agent-deck session send-status {send_id}`")
    return "failed" if failed else "unconfirmed" if pending else "ok"


def main(argv: Optional[list] = None, run: pg.Runner = pg.default_run, out=sys.stdout,
         sleep: Callable[[float], None] = time.sleep) -> int:
    ap = argparse.ArgumentParser(description="Assign tasks to fleet sessions on the right model profile.")
    ap.add_argument("task", nargs="*", metavar="SESSION SEVERITY TASK")
    ap.add_argument("--batch", help="JSON file with a list of {session, severity, task} ('-' for stdin)")
    ap.add_argument("--dry-run", action="store_true", help="print what would run; change nothing")
    ap.add_argument("--state", default=pg.DEFAULT_STATE,
                    help="the gate's state file; restarts that failed are remembered next to it")
    ap.add_argument("--submit-wait-sec", type=int, default=180,
                    help="how long to wait for a send to a Codex session to be submitted")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    def say(text: str) -> None:
        print(text, file=out)

    tasks, errors = parse_tasks(args)
    if errors:
        for error in errors:
            say(f"error: {error}")
        say("nothing sent")
        return 2

    fleet = pg.fleet_status(run)
    if fleet is None:
        say("could not read agent-deck sessions; nothing sent")
        return 1

    restarts = pg.restarts_path(args.state)
    status, deferred, pending = 0, False, {}
    for session, groups in batches(tasks).items():
        first, later = groups[0], [item for group in groups[1:] for item in group]
        info = fleet.get(session)
        if info is None:
            say(f"{session}: no such agent-deck session; its {sum(len(g) for g in groups)} task(s) were not sent")
            status = 1
            continue
        want = pg.profile_for(session, first[0][0])
        idle = info["status"] in pg.IDLE_STATUSES
        if pg.switch_commands(session, info, want, restarts) and not idle:
            say(f"{session}: needs {want.model} / {want.effort} but is {info['status'] or 'not running'}; "
                f"a model switch restarts the session, so its {sum(len(g) for g in groups)} task(s) are deferred")
            deferred = True
            continue
        if not pg.apply_profile(run, session, info, want, args.dry_run, say, restarts):
            status = 1
            continue
        for sev, text in first:
            label = pg.SEVERITY_LABELS[sev]
            if args.dry_run:
                say(f"[dry-run] would send {label} task to {session} ({want.model} / {want.effort}): {text}")
                continue
            rc, reply = run(["agent-deck", "session", "send", session, "-queue", task_message(session, label, text)])
            if rc != 0:
                say(f"could not send {label} task to {session}: {reply}")
                status = 1
                continue
            say(f"sent {label} task to {session} ({want.model} / {want.effort}): {reply}")
            found = re.search(r"Queued\s+(\S+)", reply or "")
            if info["tool"] == "codex" and found:
                pending[found.group(1)] = session
        for sev, text in later:
            say(f"deferred {pg.SEVERITY_LABELS[sev]} task for {session} (needs a different profile; "
                f"assign it again when the session is idle): {text}")
            deferred = True

    if pending:
        outcome = confirm_codex_sends(run, pending, fleet, args.submit_wait_sec, 5.0, sleep, say)
        status = status or (1 if outcome == "failed" else 0)
        deferred = deferred or outcome == "unconfirmed"
    return status or (3 if deferred else 0)


if __name__ == "__main__":
    sys.exit(main())
