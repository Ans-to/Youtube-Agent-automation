import json
import tempfile
import unittest
from pathlib import Path

from app_config import ConfigError, load_config


class AppConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"

    def test_missing_file_returns_empty_safe_config(self):
        self.assertEqual(load_config(self.path, environ={}), {})

    def test_reads_json_object(self):
        self.path.write_text(json.dumps({"model": {"enabled": False}}), encoding="utf-8")
        self.assertEqual(load_config(self.path, environ={}), {"model": {"enabled": False}})

    def test_rejects_malformed_json_without_echoing_contents(self):
        self.path.write_text('{"api_key": "do-not-echo",', encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            load_config(self.path, environ={})
        self.assertIn("line 1", str(caught.exception))
        self.assertNotIn("do-not-echo", str(caught.exception))

    def test_rejects_non_object_root_and_wrong_section_type(self):
        self.path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "JSON object"):
            load_config(self.path, environ={})
        self.path.write_text('{"runner": []}', encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "runner.*object"):
            load_config(self.path, environ={})

    def test_environment_override_is_allowlisted_and_typed(self):
        self.path.write_text(json.dumps({"model": {"enabled": False}, "dashboard": {"port": 8765}}), encoding="utf-8")
        result = load_config(self.path, environ={
            "AGENT_HQ_MODEL_ENABLED": "true",
            "AGENT_HQ_DASHBOARD_PORT": "9000",
            "UNRELATED_SETTING": "must-not-appear",
        })
        self.assertIs(result["model"]["enabled"], True)
        self.assertEqual(result["dashboard"]["port"], 9000)
        self.assertNotIn("unrelated", json.dumps(result).lower())

    def test_invalid_environment_override_fails_closed(self):
        with self.assertRaisesRegex(ConfigError, "true/false"):
            load_config(self.path, environ={"AGENT_HQ_MODEL_ENABLED": "sometimes"})
        with self.assertRaisesRegex(ConfigError, "between 1 and 65535"):
            load_config(self.path, environ={"AGENT_HQ_DASHBOARD_PORT": "70000"})

    def test_environment_does_not_mutate_shared_defaults(self):
        self.path.write_text("{}", encoding="utf-8")
        first = load_config(self.path, environ={"AGENT_HQ_MODEL_ENABLED": "true"})
        second = load_config(self.path, environ={})
        self.assertTrue(first["model"]["enabled"])
        self.assertNotIn("model", second)


if __name__ == "__main__":
    unittest.main()
