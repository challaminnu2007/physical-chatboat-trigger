"""
Physical Chatbot Trigger — AWS Lambda Function
═══════════════════════════════════════════════════════════════════

PURPOSE
  Receives an alert message from API Gateway, stores it in DynamoDB,
  and sends it to a Discord channel via a webhook.

ENVIRONMENT VARIABLES (set in Lambda console — never hardcode here)
  DYNAMODB_TABLE_NAME   : Name of the DynamoDB table, e.g. "ChatbotAlerts"
  DISCORD_WEBHOOK_URL   : (Optional) Directly set webhook URL.
                          Prefer DISCORD_SECRET_NAME below for production.
  DISCORD_SECRET_NAME   : Name of the Secrets Manager secret that holds
                          {"webhook_url": "https://discord.com/api/webhooks/..."}
  ALLOWED_ORIGIN        : Frontend origin for CORS, e.g. "https://your-bucket.s3.amazonaws.com"
                          Use "*" only during development.

REQUIRED IAM PERMISSIONS  (attach to the Lambda execution role)
  dynamodb:PutItem          on your DynamoDB table
  secretsmanager:GetSecretValue  on your Discord secret  (if using Secrets Manager)
  logs:CreateLogGroup / CreateLogStream / PutLogEvents  (auto-created by Lambda)
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# Try importing urllib.request (stdlib, always available in Lambda)
import urllib.request
import urllib.error

# ─── Logging ────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── AWS clients (initialised outside handler for warm-start reuse) ──────────
dynamodb   = boto3.resource('dynamodb')
secretsmgr = boto3.client('secretsmanager')

# ─── Configuration read from environment variables ──────────────────────────
TABLE_NAME          = os.environ.get('DYNAMODB_TABLE_NAME', 'ChatbotAlerts')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')   # direct URL (dev only)
DISCORD_SECRET_NAME = os.environ.get('DISCORD_SECRET_NAME', '')   # Secrets Manager secret name
ALLOWED_ORIGIN      = os.environ.get('ALLOWED_ORIGIN', '*')

# ─── Module-level cache for the webhook URL so we fetch the secret only once
_cached_webhook_url: str = ''


# ════════════════════════════════════════════════════════════════════════════
# HANDLER
# ════════════════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context) -> dict:
    """Entry point called by API Gateway (proxy integration)."""

    logger.info('Received event: %s', json.dumps(event))

    # ── Handle CORS pre-flight ──────────────────────────────────────────────
    http_method = event.get('httpMethod', '')
    if http_method == 'OPTIONS':
        return _cors_preflight_response()

    # ── Only allow POST ─────────────────────────────────────────────────────
    if http_method != 'POST':
        return _error_response(405, 'Method not allowed. Use POST.')

    # ── Parse and validate body ─────────────────────────────────────────────
    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    message   = body.get('message', '').strip()
    sender    = body.get('sender', 'Dashboard User').strip() or 'Dashboard User'
    source    = body.get('source', 'web-dashboard')
    timestamp = body.get('timestamp') or datetime.now(timezone.utc).isoformat()

    if not message:
        return _error_response(400, 'Field "message" is required and cannot be empty.')
    if len(message) > 500:
        return _error_response(400, 'Message exceeds 500 character limit.')
    if len(sender) > 60:
        return _error_response(400, 'Sender name exceeds 60 characters.')

    # ── Generate unique alert ID ────────────────────────────────────────────
    alert_id = str(uuid.uuid4())

    # ── Store in DynamoDB ───────────────────────────────────────────────────
    db_status = 'stored'
    try:
        _store_in_dynamodb(alert_id, message, sender, source, timestamp)
        logger.info('Stored alert %s in DynamoDB', alert_id)
    except Exception as exc:
        logger.error('DynamoDB write failed: %s', exc, exc_info=True)
        db_status = f'db_error: {type(exc).__name__}'
        # Continue — still attempt to send Discord notification

    # ── Send to Discord ─────────────────────────────────────────────────────
    discord_status = 'sent'
    try:
        webhook_url = _get_webhook_url()
        _send_to_discord(webhook_url, message, sender, alert_id, timestamp)
        logger.info('Discord notification sent for alert %s', alert_id)
    except WebhookNotConfiguredError as exc:
        logger.warning('Discord webhook not configured: %s', exc)
        discord_status = 'webhook_not_configured'
    except Exception as exc:
        logger.error('Discord send failed: %s', exc, exc_info=True)
        discord_status = f'discord_error: {type(exc).__name__}'

    # ── Update delivery status in DynamoDB ─────────────────────────────────
    if db_status == 'stored':
        try:
            _update_status(alert_id, discord_status)
        except Exception as exc:
            logger.warning('Status update failed: %s', exc)

    # ── Return response ─────────────────────────────────────────────────────
    response_body = {
        'alertId':       alert_id,
        'message':       message,
        'sender':        sender,
        'dbStatus':      db_status,
        'discordStatus': discord_status,
        'timestamp':     timestamp,
    }
    return _success_response(response_body)


# ════════════════════════════════════════════════════════════════════════════
# DYNAMODB HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _store_in_dynamodb(alert_id: str, message: str, sender: str,
                        source: str, timestamp: str) -> None:
    table = dynamodb.Table(TABLE_NAME)
    table.put_item(
        Item={
            'alertId':   alert_id,
            'timestamp': timestamp,
            'message':   message,
            'sender':    sender,
            'source':    source,
            'status':    'pending',
        }
    )


def _update_status(alert_id: str, discord_status: str) -> None:
    table = dynamodb.Table(TABLE_NAME)
    final_status = 'delivered' if discord_status == 'sent' else 'failed'
    table.update_item(
        Key={'alertId': alert_id},
        UpdateExpression='SET #s = :s, discordStatus = :ds',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':s': final_status, ':ds': discord_status},
    )


# ════════════════════════════════════════════════════════════════════════════
# DISCORD HELPERS
# ════════════════════════════════════════════════════════════════════════════

class WebhookNotConfiguredError(Exception):
    """Raised when no Discord webhook URL is available."""


def _get_webhook_url() -> str:
    """Return the Discord webhook URL, fetching from Secrets Manager if needed."""
    global _cached_webhook_url

    if _cached_webhook_url:
        return _cached_webhook_url

    # 1. Prefer Secrets Manager (production)
    if DISCORD_SECRET_NAME:
        try:
            secret = secretsmgr.get_secret_value(SecretId=DISCORD_SECRET_NAME)
            secret_dict = json.loads(secret['SecretString'])
            url = secret_dict.get('webhook_url', '')
            if url:
                _cached_webhook_url = url
                return _cached_webhook_url
        except ClientError as exc:
            logger.error('Secrets Manager error: %s', exc)
            raise WebhookNotConfiguredError(f'Could not retrieve secret: {exc}') from exc

    # 2. Fall back to direct environment variable (dev / testing)
    if DISCORD_WEBHOOK_URL:
        _cached_webhook_url = DISCORD_WEBHOOK_URL
        return _cached_webhook_url

    raise WebhookNotConfiguredError(
        'Set DISCORD_SECRET_NAME or DISCORD_WEBHOOK_URL environment variable.'
    )


def _send_to_discord(webhook_url: str, message: str, sender: str,
                      alert_id: str, timestamp: str) -> None:
    """POST a rich embed to the Discord webhook."""

    # Determine embed colour from message keywords
    colour = 0x7c3aed  # default purple
    msg_lower = message.lower()
    if 'emergency' in msg_lower or '🚨' in message:
        colour = 0xef4444  # red
    elif 'help' in msg_lower or '🆘' in message:
        colour = 0xf59e0b  # amber
    elif 'system' in msg_lower or '🔔' in message:
        colour = 0x06b6d4  # teal

    payload = {
        'username':   'Physical Chatbot Trigger',
        'avatar_url': 'https://i.imgur.com/vSzDqW2.png',
        'embeds': [
            {
                'title':       '🔔 New Alert Received',
                'description': message,
                'color':       colour,
                'fields': [
                    {'name': 'Sender',    'value': sender,   'inline': True},
                    {'name': 'Alert ID',  'value': f'`{alert_id[:8]}…`', 'inline': True},
                    {'name': 'Timestamp', 'value': timestamp, 'inline': False},
                ],
                'footer': {
                    'text': 'Physical Chatbot Trigger · AWS Lambda',
                },
            }
        ],
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            logger.info('Discord responded with HTTP %s', status_code)
            # Discord returns 204 No Content on success
            if status_code not in (200, 204):
                raise RuntimeError(f'Unexpected Discord status: {status_code}')
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        logger.error('Discord HTTP error %s: %s', exc.code, body)
        raise RuntimeError(f'Discord HTTP {exc.code}: {body}') from exc


# ════════════════════════════════════════════════════════════════════════════
# HTTP RESPONSE HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _cors_headers() -> dict:
    return {
        'Access-Control-Allow-Origin':  ALLOWED_ORIGIN,
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Requested-With',
        'Access-Control-Max-Age':       '86400',
    }


def _cors_preflight_response() -> dict:
    return {
        'statusCode': 200,
        'headers':    _cors_headers(),
        'body':       '',
    }


def _success_response(body: dict) -> dict:
    headers = _cors_headers()
    headers['Content-Type'] = 'application/json'
    return {
        'statusCode': 200,
        'headers':    headers,
        'body':       json.dumps(body),
    }


def _error_response(status_code: int, message: str) -> dict:
    headers = _cors_headers()
    headers['Content-Type'] = 'application/json'
    return {
        'statusCode': status_code,
        'headers':    headers,
        'body':       json.dumps({'error': message}),
    }


def _parse_body(event: dict) -> dict:
    raw = event.get('body', '')
    if not raw:
        raise ValueError('Request body is empty.')
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError('Invalid JSON in request body.') from exc
    if isinstance(raw, dict):
        return raw
    raise ValueError('Unexpected body type.')
