"""
tests/test_lambda.py
════════════════════════════════════════════════════════
Unit tests for the Physical Chatbot Trigger Lambda function.

Run locally:
  cd physical-chatbot-trigger
  pip install pytest
  pytest tests/ -v

No AWS credentials are needed — all AWS calls are mocked.
"""

import json
import sys
import os
import types
import unittest
from unittest.mock import MagicMock, patch, ANY

# ─── Make sure the backend module is importable from the tests/ directory ───
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# ─── Stub boto3 BEFORE importing lambda_function so the module-level client
#     creation does not need real AWS credentials. ────────────────────────────
boto3_stub  = types.ModuleType('boto3')
botocore_stub = types.ModuleType('botocore')
exceptions_stub = types.ModuleType('botocore.exceptions')

class _FakeClientError(Exception):
    def __init__(self, error_response=None, operation_name=''):
        self.response = error_response or {}
        self.operation_name = operation_name
        super().__init__(str(error_response))

exceptions_stub.ClientError = _FakeClientError
botocore_stub.exceptions = exceptions_stub
sys.modules['boto3']             = boto3_stub
sys.modules['botocore']          = botocore_stub
sys.modules['botocore.exceptions'] = exceptions_stub

# Set up boto3 stubs
_mock_table   = MagicMock()
_mock_dynamo  = MagicMock()
_mock_dynamo.Table.return_value = _mock_table
boto3_stub.resource = MagicMock(return_value=_mock_dynamo)

_mock_secrets = MagicMock()
boto3_stub.client = MagicMock(return_value=_mock_secrets)

# Now import — it will use the stubs
import importlib
import lambda_function as lf   # noqa: E402

# ════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════

def _make_event(body: dict | None = None, method: str = 'POST') -> dict:
    """Build a minimal API Gateway proxy event."""
    return {
        'httpMethod': method,
        'body': json.dumps(body) if body is not None else '',
        'headers': {'Content-Type': 'application/json'},
    }


def _fake_context():
    ctx = MagicMock()
    ctx.function_name    = 'physical-chatbot-trigger'
    ctx.aws_request_id   = 'test-request-id'
    return ctx


# ════════════════════════════════════════════════════════
#  TEST CLASSES
# ════════════════════════════════════════════════════════

class TestCORSPreflight(unittest.TestCase):
    """OPTIONS requests must return 200 with CORS headers."""

    def test_options_returns_200(self):
        event = _make_event(method='OPTIONS')
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 200)

    def test_options_has_cors_header(self):
        event = _make_event(method='OPTIONS')
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertIn('Access-Control-Allow-Origin', resp['headers'])


class TestMethodValidation(unittest.TestCase):
    """Non-POST, non-OPTIONS methods must return 405."""

    def test_get_returns_405(self):
        event = _make_event(method='GET')
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 405)

    def test_delete_returns_405(self):
        event = _make_event(method='DELETE')
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 405)


class TestInputValidation(unittest.TestCase):
    """Invalid payloads must return 400."""

    def setUp(self):
        # Patch _get_webhook_url so we don't need Discord in unit tests
        self.patcher = patch.object(lf, '_get_webhook_url', return_value='http://fake-webhook')
        self.patcher.start()
        # Patch _send_to_discord to be a no-op
        self.discord_patcher = patch.object(lf, '_send_to_discord')
        self.discord_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.discord_patcher.stop()

    def test_empty_body_returns_400(self):
        event = _make_event(body=None)
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 400)

    def test_missing_message_field_returns_400(self):
        event = _make_event(body={'sender': 'Tester'})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 400)

    def test_empty_message_returns_400(self):
        event = _make_event(body={'message': '   '})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 400)

    def test_message_too_long_returns_400(self):
        event = _make_event(body={'message': 'A' * 501})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 400)

    def test_invalid_json_returns_400(self):
        event = {
            'httpMethod': 'POST',
            'body': '{ this is not json }',
        }
        resp = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 400)


class TestSuccessfulAlert(unittest.TestCase):
    """A valid request should return 200 with alertId."""

    def setUp(self):
        # Reset module-level webhook cache
        lf._cached_webhook_url = ''

        self.hook_patcher    = patch.object(lf, '_get_webhook_url', return_value='http://fake-webhook')
        self.discord_patcher = patch.object(lf, '_send_to_discord')
        self.db_patcher      = patch.object(lf, '_store_in_dynamodb')
        self.update_patcher  = patch.object(lf, '_update_status')

        self.hook_patcher.start()
        self.discord_patcher.start()
        self.db_patcher.start()
        self.update_patcher.start()

    def tearDown(self):
        self.hook_patcher.stop()
        self.discord_patcher.stop()
        self.db_patcher.stop()
        self.update_patcher.stop()

    def test_valid_request_returns_200(self):
        event = _make_event(body={'message': 'Test alert message', 'sender': 'Pytest'})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 200)

    def test_response_contains_alert_id(self):
        event = _make_event(body={'message': 'Hello', 'sender': 'Tester'})
        resp  = lf.lambda_handler(event, _fake_context())
        body  = json.loads(resp['body'])
        self.assertIn('alertId', body)
        self.assertTrue(body['alertId'])

    def test_dynamodb_store_is_called(self):
        event = _make_event(body={'message': 'DynamoDB test', 'sender': 'Unit Test'})
        lf.lambda_handler(event, _fake_context())
        lf._store_in_dynamodb.assert_called_once()

    def test_discord_send_is_called(self):
        event = _make_event(body={'message': 'Discord test'})
        lf.lambda_handler(event, _fake_context())
        lf._send_to_discord.assert_called_once()

    def test_response_includes_cors_header(self):
        event = _make_event(body={'message': 'CORS check'})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertIn('Access-Control-Allow-Origin', resp['headers'])

    def test_default_sender_used_when_missing(self):
        event = _make_event(body={'message': 'No sender provided'})
        resp  = lf.lambda_handler(event, _fake_context())
        body  = json.loads(resp['body'])
        self.assertEqual(body['sender'], 'Dashboard User')

    def test_exact_500_char_message_succeeds(self):
        event = _make_event(body={'message': 'B' * 500})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 200)


class TestWebhookNotConfigured(unittest.TestCase):
    """When no webhook is set, Discord status should indicate misconfiguration."""

    def setUp(self):
        lf._cached_webhook_url = ''
        os.environ.pop('DISCORD_WEBHOOK_URL', None)
        os.environ.pop('DISCORD_SECRET_NAME', None)
        lf.DISCORD_WEBHOOK_URL = ''
        lf.DISCORD_SECRET_NAME = ''
        self.db_patcher     = patch.object(lf, '_store_in_dynamodb')
        self.update_patcher = patch.object(lf, '_update_status')
        self.db_patcher.start()
        self.update_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        self.update_patcher.stop()

    def test_missing_webhook_still_returns_200(self):
        """Lambda should not crash — it returns 200 with a discord error status."""
        event = _make_event(body={'message': 'No webhook test'})
        resp  = lf.lambda_handler(event, _fake_context())
        # Should still succeed at HTTP level; discordStatus will indicate the problem
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertIn('webhook_not_configured', body.get('discordStatus', ''))


class TestEscapeAndSanitisation(unittest.TestCase):
    """Messages with special characters should be handled safely."""

    def setUp(self):
        lf._cached_webhook_url = ''
        self.hook_patcher    = patch.object(lf, '_get_webhook_url', return_value='http://fake-webhook')
        self.discord_patcher = patch.object(lf, '_send_to_discord')
        self.db_patcher      = patch.object(lf, '_store_in_dynamodb')
        self.update_patcher  = patch.object(lf, '_update_status')
        for p in (self.hook_patcher, self.discord_patcher, self.db_patcher, self.update_patcher):
            p.start()

    def tearDown(self):
        for p in (self.hook_patcher, self.discord_patcher, self.db_patcher, self.update_patcher):
            p.stop()

    def test_message_with_html_characters(self):
        event = _make_event(body={'message': '<script>alert("xss")</script>'})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 200)

    def test_message_with_unicode(self):
        event = _make_event(body={'message': '🚨 Emergency! Ünïcödé tëst.'})
        resp  = lf.lambda_handler(event, _fake_context())
        self.assertEqual(resp['statusCode'], 200)


# ════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
