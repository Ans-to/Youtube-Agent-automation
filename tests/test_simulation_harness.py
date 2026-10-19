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


if __name__ == "__main__":
    unittest.main()
