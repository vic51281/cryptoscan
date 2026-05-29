from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

COINS_CG = [
    "bitcoin","ethereum","ripple","binancecoin","solana",
    "dogecoin","cardano","tron","avalanche-2","chainlink",
    "the-open-network","sui","shiba-inu","stellar","polkadot",
    "litecoin","bitcoin-cash","uniswap","near","aptos",
    "internet-computer","ethereum-classic","matic-network","arbitrum","bittensor",
    "cosmos","optimism","filecoin","crypto-com-chain","injective-protocol",
    "vechain","maker","the-graph","aave","algorand",
    "blockstack","fantom","worldcoin-wld","jupiter-exchange-solana","ethena",
    "bonk","sei-network","dogwifcoin","pudgy-penguins","hedera-hashgraph",
    "ondo-finance","official-trump","movement","zcash"
]

@app.route("/")
def index():
    return send_file("index.html")

@app.route("/market")
def market():
    result = {}
    all_coins = []
    for i in range(0, len(COINS_CG), 25):
        batch = COINS_CG[i:i+25]
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets"
                "?vs_currency=usd&ids=" + ",".join(batch) +
                "&order=market_cap_desc&sparkline=false&price_change_percentage=24h,7d",
                timeout=10
            )
            all_coins.extend(r.json())
        except Exception as e:
            result["coins_error"] = str(e)
    result["coins"] = all_coins

    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        result["fear_greed"] = r.json()["data"][0]
    except:
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
    except:
        result["global"] = None

    return jsonify(result)


@app.route("/detail/<sym>")
def detail(sym):
    """抓單一幣種的完整合約數據"""
    inst_id = f"{sym.upper()}-USDT-SWAP"
    result = {"sym": sym.upper()}

    # 1. 資金費率
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}",
            timeout=5
        )
        d = r.json()
        if d.get("code") == "0" and d.get("data"):
            fr = float(d["data"][0].get("fundingRate", 0))
            result["funding_rate"] = fr
        else:
            result["funding_rate"] = None
    except:
        result["funding_rate"] = None

    # 2. 未平倉量 OI
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/public/open-interest?instId={inst_id}",
            timeout=5
        )
        d = r.json()
        if d.get("code") == "0" and d.get("data"):
            oi = float(d["data"][0].get("oiCcy", 0))
            result["open_interest"] = oi
        else:
            result["open_interest"] = None
    except:
        result["open_interest"] = None

    # 3. 多空比
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
            f"?ccy={sym.upper()}&period=5m",
            timeout=5
        )
        d = r.json()
        if d.get("code") == "0" and d.get("data"):
            ls = d["data"][0]
            result["long_ratio"] = float(ls[1]) * 100
            result["short_ratio"] = float(ls[2]) * 100
        else:
            result["long_ratio"] = None
            result["short_ratio"] = None
    except:
        result["long_ratio"] = None
        result["short_ratio"] = None

    # 4. 爆倉數據
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/rubik/stat/contracts/liquidation-order"
            f"?instFamily={sym.upper()}-USDT&period=5m",
            timeout=5
        )
        d = r.json()
        if d.get("code") == "0" and d.get("data"):
            liq = d["data"][0]
            result["liq_long"] = float(liq[1])   # 多單爆倉
            result["liq_short"] = float(liq[2])  # 空單爆倉
        else:
            result["liq_long"] = None
            result["liq_short"] = None
    except:
        result["liq_long"] = None
        result["liq_short"] = None

    # 5. 24H 行情 (ticker)
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}",
            timeout=5
        )
        d = r.json()
        if d.get("code") == "0" and d.get("data"):
            t = d["data"][0]
            result["price"] = float(t.get("last", 0))
            result["price_24h_pct"] = (float(t.get("last",0)) - float(t.get("open24h",1))) / float(t.get("open24h",1)) * 100
            result["vol_24h"] = float(t.get("volCcy24h", 0))
    except:
        pass

    # 6. OI 1H 變化
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume"
            f"?ccy={sym.upper()}&period=1H",
            timeout=5
        )
        d = r.json()
        if d.get("code") == "0" and d.get("data") and len(d["data"]) >= 2:
            latest = float(d["data"][0][1])
            prev   = float(d["data"][1][1])
            result["oi_1h_pct"] = (latest - prev) / prev * 100 if prev else 0
        else:
            result["oi_1h_pct"] = None
    except:
        result["oi_1h_pct"] = None

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
