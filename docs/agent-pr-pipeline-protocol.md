# Juke PR pipeline protocol (implementor -> reviewer -> integrator)

Owner: Mario. Version 1, 2026-10-07. This is the owner's standing process for PRs into
`integration/juke-app`. Every agent in the fleet reads this file at the start of each turn.

## 1. Roles and limits

| Role | Session | May | May NOT |
|---|---|---|---|
| Implementor | `juke-implementor`, `juke-ios-port`, others | write code, push to its own branch, open PRs, fix review comments | merge, approve, label `approved`, edit another worker's branch |
| Reviewer | `juke-reviewer` (Codex, so it is independent of the Claude implementors) | read the repo, check out the PR in its own worktree, run build/tests, post PR reviews/comments, set `approved` / `changes-requested` | push, edit code, merge |
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

## 3. The flow

1. **Implementor** finishes a slice, pushes, opens a PR into `integration/juke-app`
   (never master), adds `needs-review` and one severity label (section 2a), and keeps going on
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
  `integration/juke-app` and wakes `juke-reviewer` for each `needs-review` PR and `juke-integrator`
  for each `approved` PR that is not `blocked` or `changes-requested`, using
  `agent-deck session send <session> -queue`. The message is delivered when the session is idle.
  PRs without exactly one severity label are skipped (see section 2a).
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
  30 minutes the script wakes the role once more, and after another 30 minutes it sends the owner one
  urgent notification (`agent-deck conductor notify --conductor juke --tier urgent`) and stays quiet
  until the next round. If GitHub's label history cannot be read, the script skips that role for the
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

1. Create the four labels with `gh label create` (ignore "already exists").
2. Launch `juke-reviewer` as a Codex session in its own worktree off `origin/integration/juke-app`
   (read-only workflow: no pushes), with this file as its standing instructions and a 5-minute poll loop.
3. Re-parent the implementors under `juke-integrator` (or `juke-reviewer` for review wake-ups);
   confirm the exact `agent-deck` flags with `--help` before using them.
4. Restart `juke-integrator` with this file as its standing instructions and a 5-minute poll loop.
5. Tell every implementor to follow section 3 step 1 and 3, and to read this file each turn.
6. Dry run on the next 2-3 PRs with the owner watching. Auto-merge is on only after the owner
   says the dry run went well.

## 8. Not covered here

PR #177 (integration -> master), anything in `/srv/juke-prod`, and secrets or signing decisions
always stay with the owner.
