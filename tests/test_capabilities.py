import unittest

from video_studio.capabilities import profile_device


class DeviceCapabilityProfileTests(unittest.TestCase):
    def test_low_ram_without_gpu_selects_cpu_constrained_profile(self):
        profile = profile_device(
            cpu_count=4,
            total_memory_bytes=8 * 1024**3,
            gpu={"detected": False, "name": None, "dedicated_memory_bytes": None},
            free_disk_bytes=20 * 1024**3,
        )
        self.assertEqual(profile["tier"], "cpu_constrained")
        self.assertEqual(profile["render_threads"], 3)
        self.assertEqual(profile["max_parallel_heavy_jobs"], 1)
        self.assertTrue(profile["preserve_requested_output_quality"])
        self.assertFalse(profile["automatic_resolution_downgrade"])

    def test_gpu_profile_requires_both_memory_thresholds(self):
        gpu = {"detected": True, "name": "Test GPU", "dedicated_memory_bytes": 8 * 1024**3}
        low_ram = profile_device(cpu_count=12, total_memory_bytes=8 * 1024**3, gpu=gpu, free_disk_bytes=1)
        enough_ram = profile_device(cpu_count=12, total_memory_bytes=32 * 1024**3, gpu=gpu, free_disk_bytes=1)
        self.assertEqual(low_ram["tier"], "cpu_constrained")
        self.assertEqual(enough_ram["tier"], "gpu_accelerated")
        self.assertEqual(enough_ram["render_threads"], 8)

    def test_unknown_gpu_does_not_crash_and_keeps_single_heavy_job(self):
        profile = profile_device(
            cpu_count=1,
            total_memory_bytes=None,
            gpu={"detected": False, "name": None, "dedicated_memory_bytes": None},
            free_disk_bytes=None,
        )
        self.assertEqual(profile["tier"], "balanced")
        self.assertEqual(profile["render_threads"], 1)
        self.assertEqual(profile["max_parallel_heavy_jobs"], 1)
        self.assertIsNone(profile["ram_gib"])
        self.assertIsNone(profile["free_disk_bytes"])

    def test_profile_reports_low_disk_without_changing_quality_target(self):
        profile = profile_device(
            cpu_count=8,
            total_memory_bytes=16 * 1024**3,
            gpu={"detected": False, "name": None, "dedicated_memory_bytes": None},
            free_disk_bytes=100,
        )
        self.assertEqual(profile["free_disk_bytes"], 100)
        self.assertFalse(profile["automatic_resolution_downgrade"])
        self.assertTrue(profile["preserve_requested_output_quality"])


if __name__ == "__main__":
    unittest.main()
