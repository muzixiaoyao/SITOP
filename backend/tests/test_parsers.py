from django.test import TestCase
from apps.tasks.parsers import extract_json, parse_health_output, parse_completion_output


class TestExtractJson(TestCase):
    def test_single_line_json(self):
        self.assertEqual(extract_json('{"status": "ok"}'), {"status": "ok"})

    def test_json_after_noise(self):
        output = "Loading modules...\nChecking disks...\n{\"status\": \"ok\", \"details\": {\"disk\": 42}}"
        result = extract_json(output)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["disk"], 42)

    def test_json_embedded_in_line(self):
        output = "RESULT: {\"step1\": \"ok\", \"step2\": \"failed\"} DONE"
        result = extract_json(output)
        self.assertEqual(result, {"step1": "ok", "step2": "failed"})

    def test_no_json(self):
        self.assertIsNone(extract_json("plain text output"))

    def test_empty(self):
        self.assertIsNone(extract_json(""))


class TestParseHealth(TestCase):
    def test_ok_json(self):
        result = parse_health_output('{"status": "ok", "details": {"cpu": 10}}', 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["cpu"], 10)

    def test_failed_status_in_json(self):
        result = parse_health_output('{"status": "failed"}', 0)
        self.assertFalse(result["ok"])

    def test_nonzero_exit_no_json(self):
        result = parse_health_output("error happened", 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")

    def test_zero_exit_no_json(self):
        result = parse_health_output("all good", 0)
        self.assertTrue(result["ok"])


class TestParseCompletion(TestCase):
    def test_matrix_all_ok(self):
        output = '{"step1": "ok", "step2": "ok", "step3": "ok"}'
        result = parse_completion_output(output, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["steps"], {"step1": "ok", "step2": "ok", "step3": "ok"})

    def test_matrix_with_failure(self):
        output = '{"step1": "ok", "step2": "failed"}'
        result = parse_completion_output(output, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"]["step2"], "failed")

    def test_no_json_fallback_to_exit_code(self):
        result = parse_completion_output("no json here", 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["steps"], {})
        result2 = parse_completion_output("no json here", 2)
        self.assertFalse(result2["ok"])
