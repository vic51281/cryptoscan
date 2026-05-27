from flask import Flask, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

COINS = [
    "bitcoin", "ethereum", "solana", "binancecoin",
    "ripple", "dogecoin", "cardano", "avalanche-2"
]

@app.route("/")
def index():
    return jsonify({"status": "CryptoScan API running"})

@app.route("/market")
def market():
    result = {}

    try:
        ids = ",".join(COINS)
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&ids={ids}&order=market_cap_desc"
            f"&sparkline=false&price_change_percentage=24h,7d",
            timeout=8
        )
        result["coins"] = r.json()
    except Exception as e:
        result["coins"] = []
        result["coins_error"] = str(e)

    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        result["fear_greed"] = r.json()["data"][0]
    except Exception as e:
        result["fear_greed"] = None

    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=5)
        d = r.json()["data"]
        result["global"] = {
            "btc_dominance": d["market_cap_percentage"].get("bitcoin", 0),
            "eth_dominance": d["market_cap_percentage"].get("ethereum", 0),
            "total_market_cap_usd": d["total_market_cap"].get("usd", 0),
            "total_volume_usd": d["total_volume"].get("usd", 0),
        }
    except Exception as e:
        result["global"] = None

    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
