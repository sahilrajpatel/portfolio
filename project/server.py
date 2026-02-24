from flask import Flask, jsonify, render_template, request
import requests
import time
import threading
import pandas as pd
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

BASE = "https://api.delta.exchange/v2"

perpetual_symbols = []
ticker_cache = []
last_fetch = 0
lock = threading.Lock()

# ===============================
# 🔔 ALERT STORAGE
# ===============================
alerts = []

# ===============================
# 🔐 EMAIL CONFIG (EDIT THIS)
# ===============================
EMAIL_ADDRESS = "sahilrajpatel90@gmail.com"
EMAIL_PASSWORD = "edec zfcf jmna clql"


# ===============================
# LOAD PRODUCTS
# ===============================
def load_products():
    global perpetual_symbols
    products = requests.get(f"{BASE}/products").json()["result"]

    perpetual_symbols = [
        p["symbol"] for p in products
        if p.get("contract_type") == "perpetual_futures"
        and p.get("state") == "live"
    ]

    print("Loaded symbols:", len(perpetual_symbols))


# ===============================
# FAST TICKER CACHE
# ===============================
def get_tickers():
    global ticker_cache, last_fetch

    with lock:
        if time.time() - last_fetch < 1:
            return ticker_cache

        tickers = requests.get(f"{BASE}/tickers").json()["result"]
        ticker_cache = tickers
        last_fetch = time.time()
        return ticker_cache


def get_perpetual_data():
    tickers = get_tickers()
    ticker_dict = {t.get("symbol"): t for t in tickers}

    result = []

    for sym in perpetual_symbols:
        ticker = ticker_dict.get(sym)

        if ticker:
            close = float(ticker.get("close", 0))
            open_price = float(ticker.get("open", 0))

            change = 0
            if open_price != 0:
                change = round(((close - open_price) / open_price) * 100, 2)

            result.append({
                "symbol": sym,
                "price": close,
                "change": change
            })

    return result


# ===============================
# EMAIL FUNCTION
# ===============================
def send_email(to_email, subject, message):
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())

        print("📩 Email sent to:", to_email)

    except Exception as e:
        print("Email error:", e)


# ===============================
# FETCH CANDLES
# ===============================
def fetch_candles(symbol, timeframe):
    url = f"{BASE}/candles"
    params = {
        "symbol": symbol,
        "resolution": timeframe,
        "limit": 300
    }

    r = requests.get(url, params=params)
    data = r.json().get("result", [])

    if not data:
        return None

    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)

    return df


# ===============================
# ALERT MONITOR ENGINE
# ===============================
def monitor_alerts():
    while True:
        try:
            for alert in alerts:

                symbol = alert["symbol"]
                timeframe = alert["timeframe"]
                fast = alert["fast"]
                slow = alert["slow"]
                email = alert["email"]

                df = fetch_candles(symbol, timeframe)

                if df is None or len(df) < slow + 5:
                    continue

                df["fast_ema"] = df["close"].ewm(span=fast).mean()
                df["slow_ema"] = df["close"].ewm(span=slow).mean()

                prev = df.iloc[-2]
                curr = df.iloc[-1]

                signal = None

                if prev["fast_ema"] < prev["slow_ema"] and curr["fast_ema"] > curr["slow_ema"]:
                    signal = "BULLISH"

                if prev["fast_ema"] > prev["slow_ema"] and curr["fast_ema"] < curr["slow_ema"]:
                    signal = "BEARISH"

                if signal and alert.get("last_signal") != signal:
                    subject = f"{symbol} EMA Crossover Alert"
                    message = (
                        f"{signal} crossover detected\n\n"
                        f"Symbol: {symbol}\n"
                        f"Timeframe: {timeframe}\n"
                        f"Fast EMA: {fast}\n"
                        f"Slow EMA: {slow}"
                    )

                    send_email(email, subject, message)
                    alert["last_signal"] = signal
                    print("🚨 Alert triggered:", symbol)

        except Exception as e:
            print("Monitor error:", e)

        time.sleep(60)


# ===============================
# ROUTES
# ===============================
@app.route("/")
def home():
    return render_template("index.html")
@app.route("/sahil")
def sahil_dashboard():
    return render_template("sahil.html")

@app.route("/terminal")
def terminal():
    return render_template("terminal.html")


@app.route("/alerts")
def alerts_page():
    return render_template("alerts.html")


@app.route("/data")
def data():
    return jsonify(get_perpetual_data())


@app.route("/add-alert", methods=["POST"])
def add_alert():
    data = request.json

    timeframe = data["timeframe"]
    fast = int(data["fast"])
    slow = int(data["slow"])
    email = data["email"]
    apply_all = data.get("apply_all", False)

    if apply_all:
        for symbol in perpetual_symbols:
            alerts.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "fast": fast,
                "slow": slow,
                "email": email,
                "last_signal": None
            })
    else:
        alerts.append({
            "symbol": data["symbol"].upper(),
            "timeframe": timeframe,
            "fast": fast,
            "slow": slow,
            "email": email,
            "last_signal": None
        })

    return jsonify({"status": "Alert Added"})


@app.route("/get-alerts")
def get_alerts():
    return jsonify(alerts)


@app.route("/delete-alert/<int:index>", methods=["DELETE"])
def delete_alert(index):
    if 0 <= index < len(alerts):
        alerts.pop(index)
    return jsonify({"status": "Deleted"})


@app.route("/test-alert", methods=["POST"])
def test_alert():
    data = request.json
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email required"}), 400

    subject = "✅ EMA Alert System Test"
    message = "Your EMA Alert System is working correctly 🚀"

    send_email(email, subject, message)

    return jsonify({"status": "Test email sent"})


# ===============================
# START APP
# ===============================
if __name__ == "__main__":
    load_products()
    threading.Thread(target=monitor_alerts, daemon=True).start()
    app.run(debug=True)