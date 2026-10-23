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


class EnvFileTests(unittest.TestCase):
    """`.env` is configuration, not code: parsed, allowlisted, overridable."""

    def setUp(self):
        from app_config import load_env_file, parse_env_file
        self.load_env_file = staticmethod(load_env_file).__func__
        self.parse_env_file = staticmethod(parse_env_file).__func__
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".env"

    def test_comments_blank_lines_and_quotes_are_handled(self):
        self.path.write_text(
            "# comment\n\nAGENT_HQ_MODEL_NAME=quoted-name\n"
            'AGENT_HQ_MODEL_BASE_URL="http://127.0.0.1:8080/v1"\n'
            "export AGENT_HQ_MODEL_ENABLED=true\n",
            encoding="utf-8",
        )
        values = self.parse_env_file(self.path.read_text(encoding="utf-8"))
        self.assertEqual(values["AGENT_HQ_MODEL_NAME"], "quoted-name")
        self.assertEqual(values["AGENT_HQ_MODEL_BASE_URL"], "http://127.0.0.1:8080/v1")
        self.assertEqual(values["AGENT_HQ_MODEL_ENABLED"], "true")

    def test_a_malformed_line_names_the_line_and_not_its_content(self):
        from app_config import ConfigError
        with self.assertRaises(ConfigError) as caught:
            self.parse_env_file("GOOD=1\nthis-is-not-a-setting\n", source=".env")
        self.assertIn("line 2", str(caught.exception))
        self.assertNotIn("this-is-not-a-setting", str(caught.exception))

    def test_a_missing_file_is_not_an_error(self):
        from app_config import load_env_file
        self.assertIn("PATH", load_env_file(Path(self.temp.name) / "nope.env"))

    def test_the_real_environment_wins_over_the_file(self):
        from app_config import load_env_file
        self.path.write_text("AGENT_HQ_MODEL_NAME=from-file\n", encoding="utf-8")
        merged = load_env_file(self.path, environ={})
        self.assertEqual(merged["AGENT_HQ_MODEL_NAME"], "from-file")
        merged = load_env_file(self.path, environ={"AGENT_HQ_MODEL_NAME": "from-shell"})
        self.assertEqual(merged["AGENT_HQ_MODEL_NAME"], "from-shell")

    def test_config_can_be_pointed_elsewhere_by_a_variable(self):
        from unittest.mock import patch
        alternate = Path(self.temp.name) / "other.json"
        alternate.write_text(json.dumps({"dashboard": {"port": 9100}}), encoding="utf-8")
        with patch("app_config.DEFAULT_CONFIG_PATH", Path(self.temp.name) / "config.json"):
            result = load_config(environ={"AGENT_HQ_CONFIG": str(alternate)})
        self.assertEqual(result["dashboard"]["port"], 9100)

    def test_an_explicit_environment_is_not_merged_with_the_dotenv_file(self):
        from unittest.mock import patch
        from app_config import DEFAULT_CONFIG_PATH
        self.path.write_text("AGENT_HQ_MODEL_ENABLED=true\n", encoding="utf-8")
        with patch("app_config.DEFAULT_CONFIG_PATH", Path(self.temp.name) / "config.json"):
            self.assertEqual(load_config(environ={}), {})
