import json
import os
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
}

def send_to_discord(message: str, sender: str, alert_id: str, timestamp: str) -> str:
    if not DISCORD_WEBHOOK_URL:
        return "skipped"

    colour = 0x7C3AED
    msg_lower = message.lower()
    if "emergency" in msg_lower or "\U0001f6a8" in message:
        colour = 0xEF4444
    elif "help" in msg_lower or "\U0001f198" in message:
        colour = 0xF59E0B
    elif "system" in msg_lower or "\U0001f514" in message:
        colour = 0x06B6D4

    payload = {
        "username": "Physical Chatbot Trigger (Vercel)",
        "embeds": [
            {
                "title": "New Alert (Vercel Serverless)",
                "description": message,
                "color": colour,
                "fields": [
                    {"name": "Sender", "value": sender, "inline": True},
                    {"name": "Alert ID", "value": f"`{alert_id[:8]}`", "inline": True},
                    {"name": "Timestamp", "value": timestamp, "inline": False},
                ],
                "footer": {"text": "Physical Chatbot Trigger -- Vercel Serverless"},
            }
        ],
    }

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
        return f"discord_error_{exc.code}"
    except Exception as exc:
        return f"error: {exc}"

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        response = {"status": "ok", "discord": bool(DISCORD_WEBHOOK_URL), "runtime": "vercel-serverless"}
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw)
        except Exception:
            self._json(400, {"error": "Invalid JSON body."})
            return

        message = str(body.get("message") or "").strip()
        sender = str(body.get("sender") or "Dashboard User").strip() or "Dashboard User"
        source = str(body.get("source") or "vercel-dashboard")
        ts = body.get("timestamp") or datetime.now(timezone.utc).isoformat()

        if not message:
            self._json(400, {"error": "Field 'message' is required."})
            return
        if len(message) > 500:
            self._json(400, {"error": "Message exceeds 500 character limit."})
            return

        alert_id = str(uuid.uuid4())
        discord_status = send_to_discord(message, sender, alert_id, ts)

        self._json(200, {
            "alertId": alert_id,
            "message": message,
            "sender": sender,
            "discordStatus": discord_status,
            "timestamp": ts,
        })

    def _json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

