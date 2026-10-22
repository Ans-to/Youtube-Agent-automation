"""Tests for the npm audit wrapper.

The wrapper exists so a registry outage cannot be mistaken for either a clean
audit or a security failure. These tests pin that behaviour down without
touching the network.
"""
import json
import subprocess
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import audit_npm_dependencies as audit  # noqa: E402


def report(vulnerabilities, counts=None):
    return {
        "vulnerabilities": vulnerabilities,
        "metadata": {"vulnerabilities": counts or {}},
    }


class ParseAuditJsonTests(unittest.TestCase):
    def test_parses_a_normal_report(self):
        data = audit.parse_audit_json(json.dumps(report({})))
        self.assertEqual(data["vulnerabilities"], {})

    def test_empty_output_is_an_error_not_a_pass(self):
        with self.assertRaises(ValueError):
            audit.parse_audit_json("")

    def test_non_json_output_is_an_error(self):
        with self.assertRaises(ValueError):
            audit.parse_audit_json("npm ERR! network request failed")

    def test_npm_error_object_is_an_error(self):
        payload = json.dumps({"error": {"summary": "ENOTFOUND registry.npmjs.org"}})
        with self.assertRaises(ValueError) as ctx:
            audit.parse_audit_json(payload)
        self.assertIn("ENOTFOUND", str(ctx.exception))

    def test_report_without_vulnerability_sections_is_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_audit_json(json.dumps({"unexpected": True}))


class BlockingAdvisoryTests(unittest.TestCase):
    def test_high_and_critical_block(self):
        data = report({
            "left-pad": {"severity": "critical", "range": "<2", "fixAvailable": True, "via": []},
            "lodash": {"severity": "high", "range": "<5", "fixAvailable": False, "via": []},
        })
        found = audit.blocking_advisories(data, "high")
        self.assertEqual([item["package"] for item in found], ["left-pad", "lodash"])

    def test_moderate_does_not_block_at_high(self):
        data = report({"tiny": {"severity": "moderate", "range": "<1", "via": []}})
        self.assertEqual(audit.blocking_advisories(data, "high"), [])

    def test_advisory_details_are_carried_through(self):
        data = report({
            "pkg": {
                "severity": "high",
                "range": "1.0.0 - 1.2.0",
                "fixAvailable": True,
                "via": [{"title": "Prototype pollution", "url": "https://example.test/a", "severity": "high"}],
            },
        })
        found = audit.blocking_advisories(data, "high")
        self.assertEqual(found[0]["advisories"][0]["title"], "Prototype pollution")
        self.assertEqual(found[0]["advisories"][0]["url"], "https://example.test/a")

    def test_string_via_entries_are_kept(self):
        data = report({"pkg": {"severity": "high", "range": "<1", "via": ["a transitive advisory"]}})
        found = audit.blocking_advisories(data, "high")
        self.assertEqual(found[0]["advisories"][0]["title"], "a transitive advisory")

    def test_unknown_severity_does_not_block(self):
        data = report({"pkg": {"severity": "not-a-severity", "range": "<1", "via": []}})
        self.assertEqual(audit.blocking_advisories(data, "high"), [])


class RunAuditTests(unittest.TestCase):
    """These patch both the npm lookup and subprocess.

    CI runs this suite inside a `python:3.12-slim` container that has no npm at
    all, so a test that only patches subprocess exercises the early "npm is not
    installed" return path instead of the retry logic it is meant to test. The
    lookup is therefore always stubbed.
    """

    def run_with(self, outcome, attempts=3, timeout=1):
        """Run run_audit with npm present and subprocess replaced by `outcome`."""
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        original_run = audit.subprocess.run
        original_which = audit.shutil.which
        audit.subprocess.run = fake_run
        audit.shutil.which = lambda name: "/usr/bin/npm" if name == "npm" else None
        try:
            report_data, error = audit.run_audit(".", timeout=timeout, attempts=attempts, retry_delay=0)
        finally:
            audit.subprocess.run = original_run
            audit.shutil.which = original_which
        return report_data, error, calls

    def test_transport_failure_is_retried_and_reported_as_unavailable(self):
        class Result:
            returncode = 1
            stdout = "npm ERR! code ENOTFOUND"
            stderr = "network"

        report_data, error, calls = self.run_with(Result(), attempts=3)
        self.assertIsNone(report_data)
        self.assertEqual(len(calls), 3, "transport failures should be retried")
        self.assertIn("not JSON", error)

    def test_findings_are_not_retried(self):
        class Result:
            returncode = 1
            stdout = json.dumps(report({"pkg": {"severity": "high", "range": "<1", "via": []}}))
            stderr = ""

        report_data, error, calls = self.run_with(Result(), attempts=3)
        self.assertEqual(len(calls), 1, "a real finding must fail immediately")
        self.assertEqual(error, "")
        self.assertIn("pkg", report_data["vulnerabilities"])

    def test_timeout_is_retried(self):
        report_data, error, calls = self.run_with(
            subprocess.TimeoutExpired(["npm"], 1), attempts=2)
        self.assertIsNone(report_data)
        self.assertEqual(len(calls), 2)
        self.assertIn("timed out", error)

    def test_missing_npm_is_reported_as_unavailable_not_a_pass(self):
        original_which = audit.shutil.which
        audit.shutil.which = lambda name: None
        try:
            report_data, error = audit.run_audit(".", timeout=1, attempts=1, retry_delay=0)
        finally:
            audit.shutil.which = original_which
        self.assertIsNone(report_data)
        self.assertIn("npm is not installed", error)


class MainExitCodeTests(unittest.TestCase):
    def test_clean_report_exits_zero(self):
        original = audit.run_audit
        audit.run_audit = lambda *a, **k: (report({}), "")
        try:
            self.assertEqual(audit.main(["--directory", "."]), 0)
        finally:
            audit.run_audit = original

    def test_findings_exit_one(self):
        original = audit.run_audit
        audit.run_audit = lambda *a, **k: (
            report({"pkg": {"severity": "critical", "range": "<1", "fixAvailable": False, "via": []}}), "")
        try:
            self.assertEqual(audit.main(["--directory", "."]), audit.EXIT_GATE_FAILED)
        finally:
            audit.run_audit = original

    def test_unavailable_warns_by_default(self):
        original = audit.run_audit
        audit.run_audit = lambda *a, **k: (None, "ENOTFOUND")
        try:
            self.assertEqual(audit.main(["--directory", "."]), 0)
        finally:
            audit.run_audit = original

    def test_unavailable_fails_closed_when_required(self):
        original = audit.run_audit
        audit.run_audit = lambda *a, **k: (None, "ENOTFOUND")
        try:
            self.assertEqual(
                audit.main(["--directory", ".", "--require-service"]),
                audit.EXIT_UNAVAILABLE,
            )
        finally:
            audit.run_audit = original


if __name__ == "__main__":
    unittest.main()
