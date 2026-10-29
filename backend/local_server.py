"""
local_server.py  --  Physical Chatbot Trigger  Local Dev Server
================================================================
Runs everything locally WITHOUT AWS credentials:
  - Serves the frontend (index.html / style.css / script.js)
  - Exposes POST /alert  ->  mimics Lambda logic
  - Stores alerts in memory  (GET /alerts to view history)
  - Sends real Discord notifications if DISCORD_WEBHOOK_URL is set
    (optional -- works perfectly fine without it)

FIX HISTORY
  v2  Fixed UnicodeEncodeError on Windows (cp1252 console) by
      reconfiguring stdout to UTF-8 at module load and using a
      safe_print() helper that replaces un-encodable characters.
      Also added SO_REUSEADDR so the port is freed immediately
      after a crash without a TIME_WAIT delay.

Usage (PowerShell):
  # Without Discord:
  python backend/local_server.py

  # With real Discord notifications:
  $env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
  python backend/local_server.py

Then open:  http://localhost:5000
"""

import io
import json
import os
import socket
import sys
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ── Force stdout to UTF-8 on Windows so emoji in messages do not crash
#    the process.  This is the PRIMARY fix for the cp1252 UnicodeEncodeError.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

# ── Paths
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# ── Config from environment
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 5000))
HOST = os.environ.get("HOST", "0.0.0.0")

# ── In-memory alert store (replaces DynamoDB locally)
_alerts: list[dict] = []


# =============================================================================
# SAFE PRINT  (never crashes on non-encodable characters)
# =============================================================================

def safe_print(text: str) -> None:
    """Print text, replacing any character that cannot be encoded."""
    try:
        print(text)
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback: replace every non-ASCII character with its codepoint
        print(text.encode("ascii", errors="replace").decode("ascii"))


# =============================================================================
# DISCORD HELPER
# =============================================================================

def send_to_discord(message: str, sender: str, alert_id: str, timestamp: str) -> str:
    """
    POST a rich embed to Discord.
    Returns: 'sent' | 'skipped' | 'discord_error_NNN' | 'error: ...'
    """
    if not DISCORD_WEBHOOK_URL:
        safe_print("  [Discord] WARNING: DISCORD_WEBHOOK_URL not set -- skipped.")
        return "skipped"

    # Colour based on message content (emoji-safe comparisons)
    colour = 0x7C3AED  # default purple
    msg_lower = message.lower()
    if "emergency" in msg_lower or "\U0001f6a8" in message:   # 🚨
        colour = 0xEF4444
    elif "help" in msg_lower or "\U0001f198" in message:       # 🆘
        colour = 0xF59E0B
    elif "system" in msg_lower or "\U0001f514" in message:     # 🔔
        colour = 0x06B6D4

    payload = {
        "username": "Physical Chatbot Trigger (LOCAL)",
        "embeds": [
            {
                "title": "New Alert (Local Dev)",
                "description": message,
                "color": colour,
                "fields": [
                    {"name": "Sender",    "value": sender,              "inline": True},
                    {"name": "Alert ID",  "value": f"`{alert_id[:8]}`", "inline": True},
                    {"name": "Timestamp", "value": timestamp,           "inline": False},
                ],
                "footer": {"text": "Physical Chatbot Trigger -- Local Dev Server"},
            }
        ],
    }

    # json.dumps handles any Unicode correctly; urllib sends raw bytes
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.getcode()
            return "sent" if code in (200, 204) else f"http_{code}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        safe_print(f"  [Discord] ERROR HTTP {exc.code}: {body[:200]}")
        return f"discord_error_{exc.code}"
    except Exception as exc:
        safe_print(f"  [Discord] ERROR: {exc}")
        return f"error: {exc}"


# =============================================================================
# HTTP HANDLER
# =============================================================================

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png":  "image/png",
    ".ico":  "image/x-icon",
    ".svg":  "image/svg+xml",
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
}


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        """Compact, emoji-safe log line."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"  [{ts}] {self.command} {self.path}"
        safe_print(line)

    # -- OPTIONS (CORS preflight) -------------------------------------------
    def do_OPTIONS(self):
        self._send(200, b"", "text/plain")

    # -- GET -------------------------------------------------------------------
    def do_GET(self):
        clean = self.path.split("?")[0]

        if clean == "/health":
            self._json(200, {
                "status":  "ok",
                "discord": bool(DISCORD_WEBHOOK_URL),
                "alerts":  len(_alerts),
                "server":  "local-dev",
            })
            return

        if clean == "/alerts":
            self._json(200, {"alerts": _alerts, "count": len(_alerts)})
            return

        # Static file serving
        if clean in ("/", ""):
            clean = "/index.html"

        file_path = FRONTEND_DIR / clean.lstrip("/")
        if file_path.is_file():
            mime = MIME_TYPES.get(file_path.suffix, "application/octet-stream")
            self._send(200, file_path.read_bytes(), mime)
        else:
            self._send(404, b"404 Not Found", "text/plain")

    # -- POST ------------------------------------------------------------------
    def do_POST(self):
        if self.path.split("?")[0] != "/alert":
            self._json(404, {"error": "Unknown endpoint. Use POST /alert"})
            return

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)

        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON body."})
            return

        # --- Validate ---------------------------------------------------------
        message = str(body.get("message") or "").strip()
        sender  = str(body.get("sender")  or "Dashboard User").strip() or "Dashboard User"
        source  = str(body.get("source")  or "web-dashboard")
        ts      = body.get("timestamp") or datetime.now(timezone.utc).isoformat()

        if not message:
            self._json(400, {"error": "Field 'message' is required."})
            return
        if len(message) > 500:
            self._json(400, {"error": "Message exceeds 500 character limit."})
            return
        if len(sender) > 60:
            self._json(400, {"error": "Sender name exceeds 60 characters."})
            return

        # --- Process ----------------------------------------------------------
        alert_id = str(uuid.uuid4())

        discord_status = send_to_discord(message, sender, alert_id, ts)
        db_status      = "stored (memory)"

        record = {
            "alertId":       alert_id,
            "message":       message,
            "sender":        sender,
            "source":        source,
            "timestamp":     ts,
            "discordStatus": discord_status,
            "status":        "delivered" if discord_status in ("sent", "skipped") else "failed",
        }
        _alerts.insert(0, record)
        if len(_alerts) > 100:
            _alerts.pop()

        # Safe console log -- message may contain emoji
        preview = message[:50].encode("ascii", errors="replace").decode("ascii")
        safe_print(f"  [Alert] OK  id={alert_id[:8]}  discord={discord_status}  msg={preview!r}")

        self._json(200, {
            "alertId":       alert_id,
            "message":       message,
            "sender":        sender,
            "dbStatus":      db_status,
            "discordStatus": discord_status,
            "timestamp":     ts,
        })

    # -- Helpers ---------------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")


# =============================================================================
# REUSABLE SERVER  (fixes port-in-use after crash)
# =============================================================================

class ReusableHTTPServer(HTTPServer):
    """Sets SO_REUSEADDR so port 5000 is freed immediately after a crash."""
    allow_reuse_address = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    if not FRONTEND_DIR.exists():
        safe_print(f"ERROR: Frontend directory not found: {FRONTEND_DIR}")
        sys.exit(1)

    discord_info = (
        "Configured -- real Discord notifications ON"
        if DISCORD_WEBHOOK_URL
        else "Not set  (set DISCORD_WEBHOOK_URL env var to enable)"
    )

    safe_print("")
    safe_print("=" * 60)
    safe_print("  Physical Chatbot Trigger -- Local Dev Server v2")
    safe_print("=" * 60)
    safe_print(f"  Dashboard : http://localhost:{PORT}/")
    safe_print(f"  POST alert: http://localhost:{PORT}/alert")
    safe_print(f"  GET history: http://localhost:{PORT}/alerts")
    safe_print(f"  GET health:  http://localhost:{PORT}/health")
    safe_print(f"  Discord   : {discord_info}")
    safe_print("-" * 60)
    safe_print("  Press Ctrl+C to stop")
    safe_print("")

    server = ReusableHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
