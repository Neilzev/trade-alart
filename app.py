import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")  # optional but recommended

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()

@app.route("/alert", methods=["POST"])
def alert():
    # Optional: verify a shared secret header
    if WEBHOOK_SECRET:
        secret = request.headers.get("X-Webhook-Secret")
        if secret != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Build a readable message from whatever TV sends
    ticker   = data.get("ticker", "N/A")
    action   = data.get("action", "N/A")   # e.g. "BUY" or "SELL"
    price    = data.get("price", "N/A")
    interval = data.get("interval", "N/A")
    message  = data.get("message", "")

    text = (
        f"📊 <b>{ticker}</b> — {action}\n"
        f"Price: <code>{price}</code>  |  TF: {interval}\n"
        f"{message}"
    )

    send_telegram(text)
    return jsonify({"status": "ok"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
```

Create `requirements.txt`:
```
flask>=3.0
requests>=2.31
gunicorn>=21.0
