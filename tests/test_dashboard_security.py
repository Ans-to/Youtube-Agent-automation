import unittest


class DashboardRequestSecurityTests(unittest.TestCase):
    def _headers(self, **overrides):
        from email.message import Message
        headers = Message()
        values = {
            "Host": "127.0.0.1:8765",
            "Origin": "http://127.0.0.1:8765",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": "0",
        }
        values.update(overrides)
        for key, value in values.items():
            headers[key] = value
        return headers

    def test_same_origin_loopback_form_is_allowed(self):
        from dashboard import validate_post_request
        self.assertIsNone(validate_post_request(self._headers(), 8765))

    def test_missing_origin_is_rejected(self):
        from dashboard import validate_post_request
        headers = self._headers()
        del headers["Origin"]
        self.assertIn("Missing Origin", validate_post_request(headers, 8765))

    def test_cross_origin_is_rejected(self):
        from dashboard import validate_post_request
        result = validate_post_request(self._headers(Origin="http://evil.example:8765"), 8765)
        self.assertIn("Cross-origin", result)

    def test_host_header_must_be_loopback_and_correct_port(self):
        from dashboard import validate_post_request
        for host in ("evil.example:8765", "127.0.0.1:9999", "127.0.0.1", "127.0.0.1:8765.evil.example"):
            with self.subTest(host=host):
                result = validate_post_request(self._headers(Host=host), 8765)
                self.assertIsNotNone(result)

    def test_content_type_must_be_urlencoded_form(self):
        from dashboard import validate_post_request
        result = validate_post_request(self._headers(**{"Content-Type": "text/plain"}), 8765)
        self.assertIn("content type", result)

    def test_transfer_encoding_is_rejected(self):
        from dashboard import validate_post_request
        result = validate_post_request(self._headers(**{"Transfer-Encoding": "chunked"}), 8765)
        self.assertIn("Transfer-Encoding", result)

    def test_ipv6_loopback_host_and_origin_are_allowed(self):
        from dashboard import validate_post_request
        headers = self._headers(
            Host="[::1]:8765",
            Origin="http://[::1]:8765",
        )
        self.assertIsNone(validate_post_request(headers, 8765))


if __name__ == "__main__":
    unittest.main()
