"""Tests for scripts/assign_task.py. Run: python3 -m unittest discover -s scripts/tests -v"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import assign_task as at  # noqa: E402
from test_pipeline_gate import FakeRunner  # noqa: E402

I1, I2, I3 = "juke-implementer-1", "juke-implementer-2", "juke-implementer-3"
CODEX_DEFAULT = "codex -m gpt-6-luna -c model_reasoning_effort=high"
CODEX_RAISED = "codex -m gpt-6.1-sol -c model_reasoning_effort=medium"


def fleet():
    return [
        {"title": I1, "tool": "codex", "status": "waiting", "tmux_session": "tmux-i1", "command": CODEX_DEFAULT},
        {"title": I2, "tool": "claude", "status": "waiting", "tmux_session": "tmux-i2", "command": "claude",
         "model": "claude-sonnet-5-5", "extra_args": ["--effort", "medium"]},
        {"title": I3, "tool": "claude", "status": "waiting", "tmux_session": "tmux-i3", "command": "claude",
         "model": "claude-sonnet-5-5", "extra_args": ["--effort", "medium"]},
    ]


class AssignTaskTest(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.runner.fleet = fleet()
        self.slept = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = str(Path(self.tmp.name) / "state.json")

    def assign(self, *argv):
        out = io.StringIO()
        rc = at.main(["--state", self.state, *argv], run=self.runner, out=out, sleep=self.slept.append)
        return rc, out.getvalue()

    def batch(self, *tasks, extra=()):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump([{"session": s, "severity": sev, "task": text} for s, sev, text in tasks], handle)
        self.addCleanup(Path(handle.name).unlink)
        return self.assign("--batch", handle.name, *extra)

    def sets(self):
        return [c for c in self.runner.commands if c[2] == "set"]

    def restarts(self):
        return [c[3] for c in self.runner.commands if c[2] == "restart"]

    # ---- rule 1: severity decides the model --------------------------------------------------
    def test_p1_task_raises_the_claude_implementer_then_sends(self):
        rc, out = self.assign(I2, "P1", "Fix the red base build")
        self.assertEqual(rc, 0)
        self.assertEqual(self.runner.commands, [
            ["agent-deck", "session", "set", I2, "model", "claude-opus-5-5"],
            ["agent-deck", "session", "restart", I2],
        ])
        self.assertEqual(len(self.runner.sent), 1)
        session, text = self.runner.sent[0]
        self.assertEqual(session, I2)
        self.assertIn("P1 task", text)
        self.assertTrue(text.endswith("Fix the red base build"))
        self.assertIn("claude-opus-5-5 / medium", out)

    def test_p1_task_raises_the_codex_implementer(self):
        self.runner.send_states["S1"] = "landed"
        rc, _ = self.assign(I1, "P0", "Rotate the leaked key")
        self.assertEqual(rc, 0)
        self.assertEqual(self.sets(), [["agent-deck", "session", "set", I1, "command", CODEX_RAISED]])
        self.assertEqual(self.restarts(), [I1])

    def test_default_profile_task_needs_no_restart(self):
        rc, _ = self.assign(I2, "P2", "Add the settings screen")
        self.assertEqual((rc, self.runner.commands, len(self.runner.sent)), (0, [], 1))

    def test_raised_session_stays_raised_for_the_next_p1(self):
        self.assign(I2, "P1", "first")
        self.assign(I2, "P0", "second")
        self.assertEqual(self.restarts(), [I2])  # one switch, not two

    def test_raised_session_returns_to_default_for_a_p2(self):
        self.assign(I2, "P1", "first")
        self.assign(I2, "P3", "polish")
        self.assertEqual([c[5] for c in self.sets()], ["claude-opus-5-5", "claude-sonnet-5-5"])
        self.assertEqual(self.restarts(), [I2, I2])

    def test_implementer_3_never_takes_p0_or_p1(self):
        for severity in ("P0", "P1"):
            rc, out = self.assign(I3, severity, "urgent thing")
            self.assertEqual(rc, 2)
            self.assertIn("never takes P0/P1", out)
        self.assertEqual((self.runner.sent, self.runner.commands), ([], []))
        rc, _ = self.assign(I3, "P2", "normal thing")
        self.assertEqual((rc, len(self.runner.sent)), (0, 1))

    # ---- a switch only happens when the session is idle ---------------------------------------
    def test_busy_session_is_not_restarted_and_its_task_is_deferred(self):
        self.runner.session(I2)["status"] = "running"
        rc, out = self.assign(I2, "P1", "urgent")
        self.assertEqual((rc, self.runner.commands, self.runner.sent), (3, [], []))
        self.assertIn("deferred", out)

    def test_busy_session_on_the_right_profile_just_gets_the_task_queued(self):
        self.runner.session(I2)["status"] = "running"
        rc, _ = self.assign(I2, "P2", "normal")
        self.assertEqual((rc, self.runner.commands, len(self.runner.sent)), (0, [], 1))
        self.assertIn("-queue", self.runner.send_cmds[0])

    def test_failed_profile_change_sends_nothing(self):
        self.runner.set_rc = 1
        rc, out = self.assign(I2, "P1", "urgent")
        self.assertEqual((rc, self.runner.sent), (1, []))
        self.assertIn("could not set", out)

    def test_failed_restart_is_retried_before_the_next_task_is_sent(self):
        self.runner.restart_rc = 1
        rc, out = self.assign(I2, "P1", "urgent")
        self.assertEqual((rc, self.runner.sent), (1, []))
        self.assertIn("could not restart juke-implementer-2", out)
        # The model is stored now, so only the remembered restart tells the next run apart.
        self.runner.session(I2)["status"] = "running"
        rc, _ = self.assign(I2, "P1", "urgent")
        self.assertEqual((rc, self.runner.sent), (3, []))    # restart still owed, session busy: deferred
        self.runner.session(I2)["status"] = "waiting"
        self.runner.restart_rc = 0
        rc, _ = self.assign(I2, "P1", "urgent")
        self.assertEqual((rc, len(self.runner.sent)), (0, 1))
        self.assertEqual([c[2] for c in self.runner.commands], ["set", "restart", "restart"])
        self.assign(I2, "P0", "next")
        self.assertEqual(len(self.restarts()), 2)  # no further restart once it succeeded

    # ---- rule 2: several tasks, ordered and batched -------------------------------------------
    def test_tasks_are_sent_p0_to_p4_within_a_profile(self):
        rc, _ = self.batch((I2, "P4", "docs"), (I2, "P2", "feature"), (I2, "P3", "polish"))
        self.assertEqual(rc, 0)
        self.assertEqual([text.rsplit("\n", 1)[-1] for _, text in self.runner.sent], ["feature", "polish", "docs"])
        self.assertEqual(self.runner.commands, [])

    def test_only_the_first_profile_group_is_sent_and_the_rest_is_deferred(self):
        rc, out = self.batch((I2, "P3", "polish"), (I2, "P1", "hotfix"), (I2, "P2", "feature"), (I2, "P0", "outage"))
        self.assertEqual(rc, 3)
        self.assertEqual([text.rsplit("\n", 1)[-1] for _, text in self.runner.sent], ["outage", "hotfix"])
        self.assertEqual(self.restarts(), [I2])  # one switch for both urgent tasks
        self.assertIn("deferred P2 task for juke-implementer-2", out)
        self.assertIn("deferred P3 task for juke-implementer-2", out)

    def test_sessions_are_handled_independently(self):
        self.runner.send_states["S1"] = "landed"
        rc, _ = self.batch((I1, "P3", "small"), (I2, "P1", "hotfix"), (I3, "P2", "feature"))
        self.assertEqual(rc, 0)
        self.assertEqual([s for s, _ in self.runner.sent], [I1, I2, I3])
        self.assertEqual(self.restarts(), [I2])

    def test_one_bad_entry_in_a_batch_sends_nothing(self):
        rc, out = self.batch((I2, "P2", "feature"), (I3, "P1", "not allowed"), ("juke-nobody", "P2", "x"),
                             (I2, "P9", "x"), (I2, "P2", "  "))
        self.assertEqual((rc, self.runner.sent, self.runner.commands), (2, [], []))
        for expected in ("never takes P0/P1", "unknown session", "severity must be", "task text is empty"):
            self.assertIn(expected, out)

    def test_batches_group_by_profile(self):
        groups = at.batches([(I1, 3, "a"), (I1, 0, "b"), (I1, 2, "c"), (I1, 1, "d")])
        self.assertEqual(groups, {I1: [[(0, "b"), (1, "d")], [(2, "c"), (3, "a")]]})

    # ---- dry run and usage --------------------------------------------------------------------
    def test_dry_run_changes_nothing(self):
        rc, out = self.assign("--dry-run", I2, "P1", "urgent")
        self.assertEqual((rc, self.runner.sent, self.runner.commands), (0, [], []))
        self.assertIn("would run: agent-deck session set juke-implementer-2 model claude-opus-5-5", out)
        self.assertIn("would run: agent-deck session restart juke-implementer-2", out)
        self.assertIn("would send P1 task to juke-implementer-2", out)

    def test_usage_errors(self):
        self.assertEqual(self.assign()[0], 2)
        self.assertEqual(self.assign(I2, "P1")[0], 2)
        self.assertEqual(self.assign("--batch", "/nonexistent/tasks.json")[0], 2)
        self.assertEqual(self.runner.sent, [])

    def test_unreadable_session_list_sends_nothing(self):
        self.runner.fleet_rc = 1
        rc, _ = self.assign(I2, "P2", "feature")
        self.assertEqual((rc, self.runner.sent), (1, []))

    def test_missing_session_is_reported(self):
        self.runner.fleet = [item for item in self.runner.fleet if item["title"] != I1]
        rc, out = self.assign(I1, "P3", "small")
        self.assertEqual((rc, self.runner.sent), (1, []))
        self.assertIn("no such agent-deck session", out)

    # ---- safety -------------------------------------------------------------------------------
    def test_only_the_given_task_text_is_sent_and_github_is_never_read(self):
        self.assign(I2, "P2", "exactly this text")
        self.assertEqual(self.runner.sent[0][1],
                         "[assign-task] P2 task for juke-implementer-2. The task text follows.\n\nexactly this text")
        self.assertEqual([cmd for cmd in self.runner.calls if cmd[0] == "gh"], [])

    # ---- Codex sends that were typed but not submitted ------------------------------------------
    def test_typed_codex_task_is_submitted_with_enter(self):
        self.runner.send_states["S1"] = "typed"
        self.runner.panes["tmux-i1"] = "› [assign-task] P3 task for juke-implementer-1. The task text follows.\n  small"
        real = self.runner.__call__

        def run(cmd):
            result = real(cmd)
            if cmd[:2] == ["tmux", "send-keys"]:
                self.runner.panes["tmux-i1"] = "› Ask Codex to do anything"  # Enter submitted it
            return result

        out = io.StringIO()
        rc = at.main(["--state", self.state, I1, "P3", "small"], run=run, out=out, sleep=self.slept.append)
        self.assertEqual(rc, 0)
        self.assertEqual([c for c in self.runner.commands if c[0] == "tmux"],
                         [["tmux", "send-keys", "-t", "tmux-i1", "Enter"]])
        self.assertIn("pressed Enter in juke-implementer-1", out.getvalue())

    def test_unconfirmed_codex_send_is_reported(self):
        self.runner.send_states["S1"] = "queued"  # never becomes idle within the wait
        rc, out = self.assign("--submit-wait-sec", "10", I1, "P3", "small")
        self.assertEqual(rc, 3)
        self.assertIn("not confirmed: send S1", out)
        self.assertEqual(self.slept, [5.0, 5.0])
        self.assertEqual([c for c in self.runner.commands if c[0] == "tmux"], [])

    def test_send_that_was_not_delivered_is_a_failure(self):
        self.runner.send_states["S1"] = "failed"
        rc, out = self.assign(I1, "P3", "small")
        self.assertEqual(rc, 1)
        self.assertIn("failed: send S1 to juke-implementer-1 was not delivered", out)

    def test_unreadable_send_status_is_not_reported_as_submitted(self):
        rc, out = self.assign("--submit-wait-sec", "5", I1, "P3", "small")  # no status for S1
        self.assertEqual(rc, 3)
        self.assertIn("not confirmed: send S1", out)

    def test_task_enter_cannot_submit_is_not_reported_as_submitted(self):
        self.runner.send_states["S1"] = "typed"
        self.runner.panes["tmux-i1"] = "\u203a [assign-task] P3 task for juke-implementer-1. The task text follows."
        rc, out = self.assign("--submit-wait-sec", "60", I1, "P3", "small")
        self.assertEqual(rc, 3)
        self.assertEqual(len([c for c in self.runner.commands if c[0] == "tmux"]), 3)
        self.assertIn("not confirmed: send S1", out)

    def test_unreadable_pane_is_not_reported_as_submitted(self):
        self.runner.send_states["S1"] = "typed"
        self.runner.capture_rc = 1
        rc, out = self.assign("--submit-wait-sec", "5", I1, "P3", "small")
        self.assertEqual(rc, 3)
        self.assertIn("not confirmed: send S1", out)
        self.assertEqual([c for c in self.runner.commands if c[0] == "tmux"], [])

    def test_claude_sends_are_not_followed_up(self):
        rc, _ = self.assign(I2, "P2", "feature")
        self.assertEqual((rc, self.slept), (0, []))
        self.assertEqual([c for c in self.runner.calls if c[:3] == ["agent-deck", "session", "send-status"]], [])


if __name__ == "__main__":
    unittest.main()
