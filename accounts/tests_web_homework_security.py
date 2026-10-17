"""Pure-Python storage boundary tests: python -m unittest accounts.tests_web_homework_security."""
import json
import unittest

from accounts.web_homework import decode_project, encode_project, valid_project


class ProjectStorageSecurityTests(unittest.TestCase):
    def test_code_is_inert_and_roundtrips(self):
        project = {'html': '</pre><script>parent.pwned=true</script>',
                   'css': '', 'js': 'console.log("</script>&lt;")'}
        encoded = encode_project(json.dumps(project))
        self.assertNotIn('<script>', encoded)
        self.assertEqual(decode_project(encoded), project)

    def test_strict_schema_and_limits(self):
        for project in (
            {'language': 'python', 'code': 'pass', 'url': 'https://evil.test'},
            {'language': 'python', 'code': 'pass', 'version': '../../evil'},
            {'language': 'python', 'code': []},
            {'language': ' ', 'code': 'pass'},
            {'language': 'python', 'code': 'pass', 'stdin': 'x' * 20001},
            {'language': 'python', 'code': 'x' * 150001},
        ):
            with self.subTest(project=str(project)[:100]):
                self.assertFalse(valid_project(project))
                with self.assertRaises(ValueError):
                    encode_project(json.dumps(project))

    def test_nested_json_does_not_raise_server_error(self):
        raw = '[' * 2000 + '0' + ']' * 2000
        with self.assertRaises(ValueError):
            encode_project(raw)
        self.assertIsNone(decode_project('<pre>LMS_WEB_PROJECT_V1\n' + raw + '</pre>'))

    def test_decoder_rejects_invalid_envelopes(self):
        encoded = encode_project(json.dumps({'language': 'python', 'code': 'pass'}))
        self.assertIsNone(decode_project(encoded + '<img src=x>'))
        self.assertIsNone(decode_project(encoded[:-6]))
        self.assertIsNone(decode_project(100))


if __name__ == '__main__':
    unittest.main()
