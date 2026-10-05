import unittest

from tools.litepoint_scpi import (
    parse_fetch_response,
    parse_scpi_error,
    validate_read_only_query,
)


class ParseScpiErrorTests(unittest.TestCase):
    def test_parses_litepoint_command_error(self):
        parsed = parse_scpi_error(
            '-100,"Command error; 01:01:00020031; SYS; CHAN1; N/A; '
            'Command not recognized: SYST:ML_DATASET_PROBE"'
        )
        self.assertEqual(parsed["code"], -100)
        self.assertEqual(parsed["message"], "Command error")
        self.assertIn("00020031", parsed["detail"])
        self.assertIn("SYST:ML_DATASET_PROBE", parsed["detail"])

    def test_parses_no_error(self):
        parsed = parse_scpi_error('0,"No error"')
        self.assertEqual(parsed["code"], 0)
        self.assertEqual(parsed["message"], "No error")
        self.assertIsNone(parsed["detail"])

    def test_preserves_unstructured_response(self):
        parsed = parse_scpi_error("unexpected")
        self.assertIsNone(parsed["code"])
        self.assertEqual(parsed["message"], "unexpected")


class ValidateReadOnlyQueryTests(unittest.TestCase):
    def test_accepts_simple_query(self):
        validate_read_only_query("*IDN?")

    def test_accepts_context_selectors_before_query(self):
        validate_read_only_query("CHAN1;5G;FETC:SEGM1:TXQ?")

    def test_rejects_hidden_setter(self):
        with self.assertRaises(ValueError):
            validate_read_only_query("VSG1;WAVE:EXEC ON;*IDN?")

    def test_rejects_non_query(self):
        with self.assertRaises(ValueError):
            validate_read_only_query("VSG1;WAVE:EXEC OFF")


class ParseFetchResponseTests(unittest.TestCase):
    def test_parses_unavailable_result_and_sentinel(self):
        parsed = parse_fetch_response("-33,9.91E+37")
        self.assertEqual(parsed["code"], -33)
        self.assertEqual(parsed["name"], "RESULT_UNAVAILABLE")
        self.assertEqual(parsed["severity"], "error")
        self.assertEqual(parsed["values"], ["9.91E+37"])

    def test_parses_valid_result(self):
        parsed = parse_fetch_response("0,1.25,-42.0")
        self.assertEqual(parsed["code"], 0)
        self.assertEqual(parsed["severity"], "ok")
        self.assertEqual(parsed["values"], ["1.25", "-42.0"])


if __name__ == "__main__":
    unittest.main()
