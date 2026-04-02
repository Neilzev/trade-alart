import os, time, threading, json
import yfinance as yf
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ALERTS_FILE = "alerts.json"

def load_alerts():
    try:
        with open(ALERTS_FILE) as f:
            return json.load(f)
    except:
        return []

def save_alerts(alerts):
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f)

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }, timeout=10)

# ── parser ──────────────────────────────────────────────────────────────────

def parse_command(text: str):
    text = text.strip()
    parts = text.lower().split()

    # list
    if parts[0] == "list":
        return {"action": "list"}

    # remove
    if parts[0] == "remove":
        return {"action": "remove", "raw": text[7:].strip()}

    # alert
    if parts[0] == "alert" and len(parts) >= 2:
        rest = parts[1:]

        # alert NVDA crosses 200 MA  /  alert NVDA crosses 50 MA
        if "crosses" in rest and "ma" in rest:
            idx = rest.index("crosses")
            ticker = rest[idx-1].upper()
            period = int(rest[idx+1])
            return {"action":"add","type":"ma_cross","ticker":ticker,"period":period,
                    "label":f"{ticker} crosses {period} MA"}

        # alert RKLB drops 1.5 ATR
        if "drops" in rest and "atr" in rest:
            idx = rest.index("drops")
            ticker = rest[idx-1].upper()
            mult   = float(rest[idx+1])
            return {"action":"add","type":"atr_drop","ticker":ticker,"mult":mult,
                    "label":f"{ticker} drops {mult} ATR"}

        # alert QQQ volume 1.5x  /  alert QQQ volume 2x yesterday
        if "volume" in rest:
            idx = rest.index("volume")
            ticker = rest[idx-1].upper()
            raw_mult = rest[idx+1].replace("x","")
            mult = float(raw_mult)
            return {"action":"add","type":"volume_spike","ticker":ticker,"mult":mult,
                    "label":f"{ticker} volume {mult}x yesterday"}

        # alert AAPL above 200  /  alert AAPL below 150
        if "above" in rest or "below" in rest:
            direction = "above" if "above" in rest else "below"
            idx = rest.index(direction)
            ticker = rest[idx-1].upper()
            target = float(rest[idx+1])
            return {"action":"add","type":"price_level","ticker":ticker,
                    "direction":direction,"target":target,
                    "label":f"{ticker} {direction} ${target}"}

    return None

# ── check logic ─────────────────────────────────────────────────────────────

def check_alert(a: dict):
    ticker = a["ticker"]
    t = yf.Ticker(ticker)

    if a["type"] == "price_level":
        price = t.fast_info["last_price"]
        if a["direction"] == "above":
            return price > a["target"], f"🟢 <b>{ticker}</b> is above ${a['target']}\nCurrent price: ${price:.2f}"
        else:
            return price < a["target"], f"🔴 <b>{ticker}</b> is below ${a['target']}\nCurrent price: ${price:.2f}"

    if a["type"] == "ma_cross":
        hist = t.history(period="1y")["Close"]
        ma   = hist.rolling(a["period"]).mean().iloc[-1]
        price = hist.iloc[-1]
        crossed = price > ma
        return crossed, f"📈 <b>{ticker}</b> crossed above {a['period']} MA\nPrice: ${price:.2f} | MA: ${ma:.2f}"

    if a["type"] == "atr_drop":
        hist  = t.history(period="60d")
        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        tr    = (high - low).abs()
        atr   = tr.rolling(14).mean().iloc[-1]
        price = close.iloc[-1]
        prev  = close.iloc[-2]
        dropped = (prev - price) >= (a["mult"] * atr)
        return dropped, f"🔴 <b>{ticker}</b> dropped {a['mult']} ATR\nPrice: ${price:.2f} | ATR: ${atr:.2f}"

    if a["type"] == "volume_spike":
        hist = t.history(period="5d")
        today_vol = hist["Volume"].iloc[-1]
        prev_vol  = hist["Volume"].iloc[-2]
        spiked = today_vol >= (a["mult"] * prev_vol)
        return spiked, f"📊 <b>{ticker}</b> volume spike!\nToday: {int(today_vol):,} | Yesterday: {int(prev_vol):,}"

    return False, ""

# ── background loop ──────────────────────────────────────────────────────────

def monitor():
    fired = set()
    while True:
        alerts = load_alerts()
        for a in alerts:
            key = a["label"]
            try:
                triggered, msg = check_alert(a)
                if triggered and key not in fired:
                    fired.add(key)
                    send_telegram(msg)
                elif not triggered and key in fired:
                    fired.discard(key)
            except Exception as e:
                print(f"Error checking {key}: {e}")
        time.sleep(20)

# ── telegram webhook ─────────────────────────────────────────────────────────

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    text = data.get("message", {}).get("text", "").strip()
    if not text:
        return jsonify({}), 200

    cmd = parse_command(text)

    if cmd is None:
        send_telegram(
            "❓ I didn't understand that. Try:\n\n"
            "<code>alert NVDA crosses 200 MA</code>\n"
            "<code>alert RKLB drops 1.5 ATR</code>\n"
            "<code>alert AAPL above 200</code>\n"
            "<code>alert QQQ volume 1.5x</code>\n"
            "<code>list</code>\n"
            "<code>remove AAPL above 200</code>"
        )
        return jsonify({}), 200

    alerts = load_alerts()

    if cmd["action"] == "list":
        if not alerts:
            send_telegram("📋 No active alerts.")
        else:
            msg = "📋 <b>Active alerts:</b>\n" + "\n".join(f"• {a['label']}" for a in alerts)
            send_telegram(msg)

    elif cmd["action"] == "add":
        if any(a["label"] == cmd["label"] for a in alerts):
            send_telegram(f"⚠️ Alert already exists: {cmd['label']}")
        else:
            alerts.append(cmd)
            save_alerts(alerts)
            send_telegram(f"✅ Alert set: <b>{cmd['label']}</b>")

    elif cmd["action"] == "remove":
        original = load_alerts()
        updated  = [a for a in original if a["label"].lower() != cmd["raw"].lower()]
        save_alerts(updated)
        removed = len(original) - len(updated)
        send_telegram(f"🗑️ Removed {removed} alert(s)." if removed else "⚠️ Alert not found.")

    return jsonify({}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running"}), 200

threading.Thread(target=monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
