import unittest

import simulation_harness


class SimulationHarnessTests(unittest.TestCase):
    def test_seeded_run_is_reproducible(self):
        first = simulation_harness.run_simulations(5000, 12345)
        second = simulation_harness.run_simulations(5000, 12345)
        self.assertEqual(first, second)
        self.assertTrue(first["ok"])
        self.assertEqual(first["trials_completed"], 5000)

    def test_one_trial_smoke(self):
        result = simulation_harness.run_simulations(1, 1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["trials_completed"], 1)

    def test_zero_trials_are_rejected(self):
        with self.assertRaises(ValueError):
            simulation_harness.run_simulations(0, 1)

    def test_unapproved_external_action_is_blocked(self):
        status, may_execute = simulation_harness.action_gate(True, False)
        self.assertEqual(status, "needs_human_action")
        self.assertFalse(may_execute)

    def test_approved_external_action_can_execute(self):
        status, may_execute = simulation_harness.action_gate(True, True)
        self.assertEqual(status, "running")
        self.assertTrue(may_execute)

    def test_no_requested_action_does_not_execute(self):
        status, may_execute = simulation_harness.action_gate(False, False)
        self.assertEqual(status, "running")
        self.assertFalse(may_execute)

    def test_blocked_action_does_not_continue_to_terminal_state(self):
        class ControlledRandom:
            def __init__(self):
                self.values = iter([0.01, 0.99])

            def random(self):
                return next(self.values)

            def randrange(self, *args):
                raise AssertionError("blocked task must stop before later lifecycle steps")

        ok, label = simulation_harness.run_case(ControlledRandom(), 7)
        self.assertTrue(ok)
        self.assertEqual(label, "external_blocked")

    def test_interrupted_task_without_retry_stays_blocked(self):
        class ControlledRandom:
            def __init__(self):
                self.values = iter([0.99, 0.99, 0.01, 0.99])

            def random(self):
                return next(self.values)

            def randrange(self, *args):
                return 2

        ok, label = simulation_harness.run_case(ControlledRandom(), 8)
        self.assertTrue(ok)
        self.assertEqual(label, "interrupted")

    def test_illegal_terminal_transition_is_rejected(self):
        task = simulation_harness.TaskModel()
        task.transition("queued")
        task.transition("running")
        task.transition("needs_human_action")
        with self.assertRaises(ValueError):
            task.transition("completed")

    def test_completed_task_cannot_be_reopened(self):
        task = simulation_harness.TaskModel()
        task.transition("queued")
        task.transition("running")
        task.transition("completed")
        with self.assertRaises(ValueError):
            task.transition("running")


if __name__ == "__main__":
    unittest.main()
