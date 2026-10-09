# Juke PR pipeline protocol (implementor -> reviewer -> integrator)

Owner: Mario. Version 1, 2026-10-07. This is the owner's standing process for PRs into
`integration/juke-app`. Every agent in the fleet reads this file at the start of each turn.

## 1. Roles and limits

| Role | Session | May | May NOT |
|---|---|---|---|
| Implementer | `juke-implementer-1` (Codex), `juke-implementer-2`, `juke-implementer-3` (Claude) | write code, push to its own branch, open PRs, fix review comments | merge, approve, label `approved`, edit another worker's branch |
| Reviewer | `juke-reviewer-1` (Codex), `juke-reviewer-2` (Claude); a PR goes to the reviewer of the other family than its author (section 2b) | read the repo, check out the PR in its own worktree, run build/tests, post PR reviews/comments, set `approved` / `changes-requested` | push, edit code, merge |
| Integrator | `juke-integrator` | merge approved PRs into `integration/juke-app`, retarget stacked PRs, update bases | merge anything not approved, touch master or PR #177, force-push |
| Conductor | `conductor-juke` | assign work, launch/restart workers, escalate to the owner, send digests | do a worker's job inside the PR loop |
| Owner | Mario | everything, including PR #177 into master | |

Nothing here lets any agent merge into `master`, touch PR #177, edit `/srv/juke-dev` or
`/srv/juke-prod`, use `--no-verify`, or put secrets in files.

## 2. State lives on GitHub, not in sessions

Labels on the PR are the only workflow state. Sessions may restart or go idle without losing it.
Create them once (idempotent): `needs-review`, `changes-requested`, `approved`, `blocked`.
Exactly one of these is on an open PR at a time. One writer per label:

| Label | Set by | Meaning |
|---|---|---|
| `needs-review` | implementor | ready for a review of the current head commit |
| `changes-requested` | reviewer | the reviewer found problems; implementor must fix |
| `approved` | reviewer | the reviewed commit is good to merge |
| `blocked` | reviewer or integrator | needs the owner (round cap hit, conflict, unclear spec) |

Use the same GitHub account for all agents, so GitHub's own "Approve" review is unavailable on
your own PRs. The reviewer therefore posts a normal review/comment and records its verdict as a
comment in this exact form, plus the label:

```
VERDICT: APPROVED  <full head SHA>
VERDICT: CHANGES REQUESTED  <full head SHA>
```

## 2a. Severity labels (P0 to P4)

Every open PR carries **exactly one** severity label, so fixes and process changes are reviewed
before routine work. A PR with none (or two) is not reviewed, and the gate tells the owner.

| Label | Meaning |
|---|---|
| `P0` | base CI is red, a security problem, or something that breaks the whole pipeline |
| `P1` | a fix or process change that other work is waiting on |
| `P2` | normal feature work |
| `P3` | polish |
| `P4` | docs and chores |

- **Who sets it:** the implementor, when it opens the PR (together with `needs-review`). The
  reviewer may relabel with a one-line reason in a PR comment. The owner may relabel any PR.
- **Cap:** at most two open PRs may be P0 or P1. Any extra one counts as P2 (the gate applies this
  automatically: the most severe, then lowest-numbered, keep their level). Do not label a third.
- **Aging:** a PR waiting for its role moves up one level for every 2 hours it has waited (since the
  newest `needs-review` or `approved` label), up to P0, so P3 and P4 cannot starve. The effective
  severity is the label after the cap and aging.
- **Missing label:** the gate sends the owner an info notification after 15 minutes without a
  severity label and an urgent one after 60 minutes (each once per PR).
- **New P0:** whoever labels a PR P0 (or relabels one to P0) sends the owner an immediate urgent
  notification with `agent-deck conductor notify --conductor juke --tier urgent`. A review already
  in progress is not interrupted.

## 2b. The fleet: sessions, model profiles and author labels

"Implementer" and "implementor" mean the same role in this file. Model names are always the full
names below, never aliases.

| Session | Tool and model | Effort | Raised for P0/P1 work |
|---|---|---|---|
| `juke-implementer-1` | Codex, `gpt-6-luna` | high | `gpt-6.1-sol`, medium |
| `juke-implementer-2` | Claude, `claude-sonnet-5-5` | medium | `claude-opus-5-5`, medium |
| `juke-implementer-3` | Claude, `claude-sonnet-5-5` | medium | none (never takes P0/P1) |
| `juke-reviewer-1` | Codex, `gpt-6.1-sol` | medium | high |
| `juke-reviewer-2` | Claude, `claude-opus-5-5` | medium | high |
| `juke-integrator` | unchanged | | |
| `conductor-juke` | unchanged | | |

The table lives in code as `PROFILES` in `scripts/pipeline_gate.py`; change both together.

**Author labels.** The implementer adds one of `author:codex` or `author:claude` when it opens a
PR, next to `needs-review` and the severity label. A PR with no author label is treated as
`author:claude`.

**Rules.**

1. **Severity decides the model, per task.** When a P0 or P1 task is assigned, the implementer is
   raised to its "raised" profile for that task. It stays raised if its next task is also P0/P1 and
   returns to its default profile when it takes a P2 or lower task. Only `juke-implementer-1` and
   `juke-implementer-2` take P0/P1 tasks.
2. **Batch and sort.** Each implementer's queue is ordered P0 to P4 and grouped by profile, so a
   session switches models as few times as possible. A switch restarts the session, so it only
   happens while the session is idle.
3. **Reviewers.** A P0 or P1 review runs at high effort, everything else at medium. The gate picks
   an idle reviewer, restarts it only when its stored profile differs from what the review needs,
   and wakes it. One wake carries PRs of one effort level. A reviewer keeps no memory between
   reviews (all state is on GitHub), so a restart loses nothing.
4. **Pair contrasting work.** A PR written by Codex (`author:codex`) goes to `juke-reviewer-2`
   (Claude). A PR written by Claude goes to `juke-reviewer-1` (Codex). If the preferred reviewer
   has not been available for 20 minutes, the other one is used. A P0 never waits: it goes to
   whichever reviewer is idle.
5. **Concurrency is capped by pool:** at most 2 Claude implementers and 1 Codex implementer running
   at once, and no more than 2 open PRs at P0/P1 (section 2a).
6. **`juke-implementer-1` takes bounded small tasks** (P3 and easy P2). Heavy or ambiguous work
   goes to `juke-implementer-2` or `juke-implementer-3`.

**Assigning tasks.** The conductor assigns implementer work with `scripts/assign_task.py`, which
applies rules 1 and 2:

```
python3 scripts/assign_task.py juke-implementer-2 P1 "task text"
python3 scripts/assign_task.py --batch tasks.json     # [{"session": ..., "severity": "P2", "task": ...}]
python3 scripts/assign_task.py --dry-run ...          # print what would run; change nothing
```

It stores the profile on the session (`agent-deck session set <s> model <m>` and
`session set <s> extra-args -- --effort <e>` for Claude; `session set <s> command
"codex -m <m> -c model_reasoning_effort=<e>"` for Codex), restarts the session if the profile
differs and the session is idle, and sends the task with `agent-deck session send <s> -queue`.
With several tasks for one session it sends the first profile group and lists the rest as
deferred; assign those again when the session is idle. It refuses a P0/P1 task for
`juke-implementer-3`. It sends only the task text the owner or conductor wrote and never reads
GitHub, so PR titles, bodies and comments cannot reach a session through it.

## 3. The flow

1. **Implementor** finishes a slice, pushes, opens a PR into `integration/juke-app`
   (never master), adds `needs-review`, one severity label (section 2a) and its author label
   (section 2b), and keeps going on
   the next slice. Before its own feature queue it handles any of its P0 or P1 PRs that are in
   `changes-requested`. It does not stop
   after opening a PR and does not end a turn to report.
2. **Reviewer** polls every 5 minutes for open PRs with `needs-review` (most severe first, then
   lowest number; in wake-driven mode, in the order the wake message lists them, one at a time). It reviews the exact head commit (`gh pr view N --json headRefOid`), then:
   - good: comment `VERDICT: APPROVED <sha>`, replace the label with `approved`;
   - problems: post inline comments, comment `VERDICT: CHANGES REQUESTED <sha>`, replace the
     label with `changes-requested`.
3. **Implementor** polls for its PRs labelled `changes-requested`, fixes them, pushes, and
   replaces the label with `needs-review`. Each fix round counts.
4. **Integrator** polls every 5 minutes for open PRs labelled `approved` and merges one at a
   time when ALL of these hold:
   - the latest `VERDICT: APPROVED <sha>` comment's SHA equals the PR's current head SHA
     (a push after approval voids it: relabel `needs-review` and tell the implementor);
   - CI on the head commit is green (`gh pr checks N`);
   - the base is `integration/juke-app` and the PR is mergeable;
   - no unresolved review thread, and no `blocked` label.
   When several are ready, merge in dependency order first (a parent before its children), then by
   severity (P0 first), then by PR number.
   Merge with a plain merge commit (no force-push, no squash). For stacked PRs, merge the
   parent first, then retarget children onto `integration/juke-app` and wait for their CI.
   After each merge, wait for CI on the base branch to go green before the next merge. If the
   base goes red, stop merging, label the last merged PR's follow-up `blocked`, and notify the owner.

## 3a. Wake-driven mode (replaces polling for the reviewer and the integrator)

A session that polls GitHub itself keeps a model call running about once a minute even when
nothing is waiting, which costs hundreds of millions of cached tokens a day. In wake-driven mode a
small script does the polling and a session only runs when there is work for it.

- `scripts/pipeline_gate.py` runs every few minutes (launchd or cron). It reads the open PRs into
  `integration/juke-app` and wakes a reviewer for each `needs-review` PR and `juke-integrator`
  for each `approved` PR that is not `blocked` or `changes-requested`, using
  `agent-deck session send <session> -queue`. The message is delivered when the session is idle.
  PRs without exactly one severity label are skipped (see section 2a).
- **Which reviewer.** The script assigns each `needs-review` PR to `juke-reviewer-1` or
  `juke-reviewer-2` by rules 3 and 4 of section 2b and records the assignment in its state file. It
  uses a reviewer only when that session is idle (`waiting` or `idle` in `agent-deck list`) and has
  no review woken in the last 30 minutes; a busy reviewer is never interrupted or restarted. Before
  a wake it restarts the reviewer if its stored model or effort differs from what the review needs.
- **Codex sessions.** A queued send to a Codex session can be left typed in the input box without
  being submitted. The script remembers each send to a Codex session and, on a later run, presses
  Enter in that session's tmux pane, at most three times, and only if `agent-deck session
  send-status` reports `typed` and the input box still shows the script's own message.
  A send that agent-deck reports as failed, or that Enter could not submit, does not count as
  delivered: its PRs become due again at once.
- **Claude sessions.** A Claude session's input box can also keep a wake without submitting it
  (agent-deck keeps reporting the send as queued). The script remembers these sends too and, on a
  later run, presses Enter in the tmux pane (same limit of three) whenever the input box still
  shows the script's own message, whatever state agent-deck reports. An empty box, or a box
  showing something else such as a dialog, is never answered.
- **Restarts.** If the profile was stored but the restart failed, the script remembers the owed
  restart (a `.restarts` file next to its state file, shared with `assign_task.py`) and retries it
  before that session gets any work.
- The wake message lists PRs by effective severity, then PR number. The reviewer takes them in that
  order. The integrator uses the list as a hint only: dependency order still comes first.
- The wake message names only PR numbers and commit hashes. It never contains PR titles, bodies or
  comments, which are untrusted data.
- On a wake, the reviewer or integrator does section 3 for exactly the listed PRs, then **ends its
  turn and waits**. It does not poll and it does not loop. This replaces the 5-minute poll in
  section 7.
- Each review round wakes a role once. A round is a new head commit, or the role's label being
  added again on the same commit (for example when only the description or screenshots were fixed);
  the script tells them apart by the id of the newest `labeled` event. If nothing happens after
  30 minutes the script wakes the role once more (for a review: the other reviewer if it is idle,
  otherwise the same one; a reviewer that is still running is left alone), and after another
  30 minutes it sends the owner one urgent notification
  (`agent-deck conductor notify --conductor juke --tier urgent`) and stays quiet until the next
  round. A PR that no reviewer has been free to take for 60 minutes, or whose retry cannot be
  delivered for 60 minutes (its reviewer stopped and the other is busy), is escalated the same way. If GitHub's label history cannot be read, the script skips that role for the
  run and changes nothing.
- Implementors are not covered: they work from their own task lists, and a PR labelled
  `changes-requested` stays with the implementor that opened it.

Schedule it with a launchd job like this, run as the owner (do not enable it before the reviewer
and integrator have been restarted in wake-driven mode, or both will run at once):

```xml
<key>ProgramArguments</key><array>
  <string>/usr/bin/python3</string><string>/path/to/juke/scripts/pipeline_gate.py</string>
</array>
<key>StartInterval</key><integer>180</integer>
```

Try it first with `python3 scripts/pipeline_gate.py --dry-run`, which prints what it would send and
changes nothing.

## 4. Limits that prevent loops and runaway merges

- **Round cap:** after 3 `CHANGES REQUESTED` verdicts on one PR, the reviewer labels it
  `blocked` and sends an urgent notification. No agent keeps cycling.
- **One merge at a time**, in dependency order.
- **Review comes first:** an implementor never labels its own PR `approved`.
- **The reviewer never edits code.** If it wants a change, it comments.
- **Idle rule:** an agent that has nothing to do polls again; it does not end its turn or wait
  to be messaged. It stops only for a `NEED:` blocker.

## 5. What the reviewer checks

1. The PR does what its task spec in `tasks/` says, including every acceptance criterion.
2. Tests exist for new behavior; CI is green; claims in the PR description match the diff.
3. No secrets, no weakened security (auth, ATS/TLS, permissions), no `--no-verify` commits.
4. Matches the repo conventions in `AGENTS.md` and the platform `AGENTS.md`.
5. For ports from macOS to iOS: behavior parity, and anything not ported is called out.
6. For anything that cannot be checked from the diff (device behavior, touch, live backend),
   say so explicitly in the review instead of approving it silently.

## 6. Notifications to the owner (Telegram via the bridge)

Worker sessions (reviewer, integrator, implementors) are not conductor sessions, so they must
name the conductor with `--conductor juke`; without it the command fails with
`no --conductor given and this is not a conductor session`. The conductor's own session may omit it.

- `agent-deck conductor notify --conductor juke --tier urgent "<one line>"`: a PR becomes
  `blocked`, base CI goes red after a merge, a worker has a `NEED:`, or a decision only the owner
  can make.
- `agent-deck conductor notify --conductor juke --tier info "<one line>"`: each merge
  (`Merged #N: title`) and each approval. Do not send routine polling noise.

## 7. Setup steps (the conductor does these once, then confirms in one paragraph)

1. Create the labels with `gh label create` (ignore "already exists"): the four state labels,
   `P0` to `P4`, `author:codex` and `author:claude`.
2. Launch `juke-reviewer-1` as a Codex session in its own worktree off `origin/integration/juke-app`
   (read-only workflow: no pushes), with this file as its standing instructions and a 5-minute poll loop.
3. Re-parent the implementors under `juke-integrator` (or a reviewer for review wake-ups);
   confirm the exact `agent-deck` flags with `--help` before using them.
4. Restart `juke-integrator` with this file as its standing instructions and a 5-minute poll loop.
5. Tell every implementor to follow section 3 step 1 and 3, and to read this file each turn.
6. Dry run on the next 2-3 PRs with the owner watching. Auto-merge is on only after the owner
   says the dry run went well.

## 8. Not covered here

PR #177 (integration -> master), anything in `/srv/juke-prod`, and secrets or signing decisions
always stay with the owner.
