from flask import Flask, jsonify, send_file
from flask_cors import CORS
import requests, concurrent.futures

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

OKX_TOP = [
    "BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","TON",
    "SUI","DOT","UNI","NEAR","ARB","OP","INJ","TRX","LTC","BCH",
    "ATOM","FIL","MKR","AAVE","ENA","SEI","WIF","ZEC","WLD","STX"
]

HEADERS = {"User-Agent": "Mozilla/5.0 CryptoScan/1.0"}

def okx_get(url, timeout=5):
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS)
        if r.status_code != 200:
            return None
        d = r.json()
        return d if d.get("code") == "0" else None
    except:
        return None

@app.route("/")
def index():
    return send_file("index.html")

@app.route("/market")
def market():
    result = {"coins": [], "fear_greed": None, "global": None}
    all_coins = []
    for i in range(0, len(COINS_CG), 25):
        batch = COINS_CG[i:i+25]
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets"
                "?vs_currency=usd&ids=" + ",".join(batch) +
                "&order=market_cap_desc&sparkline=false&price_change_percentage=24h,7d",
                timeout=10)
            data = r.json()
            if isinstance(data, list):
                all_coins.extend(data)
        except:
            pass
    result["coins"] = all_coins
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        result["fear_greed"] = r.json()["data"][0]
    except:
        pass
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
        pass
    return jsonify(result)


def fetch_coin_data(sym):
    """抓單一幣種完整衍生品數據，任何欄位失敗都不影響其他欄位"""
    inst = f"{sym}-USDT-SWAP"
    data = {"sym": sym}

    # Ticker
    d = okx_get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")
    if d and d.get("data"):
        t = d["data"][0]
        last   = float(t.get("last") or 0)
        open24 = float(t.get("open24h") or 1) or 1
        data["price"]   = last
        data["pct24h"]  = (last - open24) / open24 * 100
        data["vol24h"]  = float(t.get("volCcy24h") or 0)

    # Funding rate
    d = okx_get(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst}")
    if d and d.get("data"):
        data["funding_rate"] = float(d["data"][0].get("fundingRate") or 0)

    # Open Interest
    d = okx_get(f"https://www.okx.com/api/v5/public/open-interest?instId={inst}")
    if d and d.get("data"):
        data["oi"]     = float(d["data"][0].get("oiCcy") or 0)
        data["oi_usd"] = float(d["data"][0].get("oi") or 0)

    # OI 1H change
    d = okx_get(f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy={sym}&period=1H")
    if d and d.get("data") and len(d["data"]) >= 2:
        try:
            latest = float(d["data"][0][1])
            prev   = float(d["data"][1][1])
            data["oi_1h_pct"] = (latest - prev) / prev * 100 if prev else 0
        except:
            data["oi_1h_pct"] = None

    # Long/Short ratio
    d = okx_get(f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={sym}&period=5m")
    if d and d.get("data"):
        try:
            row = d["data"][0]
            data["long_ratio"]  = float(row[1]) * 100
            data["short_ratio"] = float(row[2]) * 100
        except:
            pass

    # Liquidations
    d = okx_get(f"https://www.okx.com/api/v5/rubik/stat/contracts/liquidation-order?instFamily={sym}-USDT&period=5m")
    if d and d.get("data"):
        try:
            row = d["data"][0]
            data["liq_long"]  = float(row[1])
            data["liq_short"] = float(row[2])
        except:
            pass

    return data


@app.route("/detail/<sym>")
def detail(sym):
    return jsonify(fetch_coin_data(sym.upper()))


@app.route("/oi-dashboard")
def oi_dashboard():
    results = []
    # 限制最多同時 8 個請求，避免 timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_coin_data, sym): sym for sym in OKX_TOP}
        for future in concurrent.futures.as_completed(futures, timeout=25):
            try:
                r = future.result(timeout=8)
                if r:
                    results.append(r)
            except:
                pass
    results.sort(key=lambda x: abs(x.get("oi_1h_pct") or 0), reverse=True)
    return jsonify(results)


@app.route("/alerts")
def alerts():
    all_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_coin_data, sym): sym for sym in OKX_TOP}
        for future in concurrent.futures.as_completed(futures, timeout=25):
            try:
                r = future.result(timeout=8)
                if r:
                    all_data.append(r)
            except:
                pass

    alerts_list = []
    for d in all_data:
        sym  = d.get("sym", "")
        oi1h = d.get("oi_1h_pct")
        fr   = d.get("funding_rate")
        lr   = d.get("long_ratio")
        p24  = d.get("pct24h", 0) or 0
        ll   = d.get("liq_long") or 0
        ls   = d.get("liq_short") or 0
        triggered = []

        if oi1h is not None and oi1h > 5:
            triggered.append({"type":"OI暴增","level":"high","msg":f"OI 1H +{oi1h:.1f}%，大量資金進場","icon":"🔥"})
        elif oi1h is not None and oi1h < -5:
            triggered.append({"type":"OI暴減","level":"medium","msg":f"OI 1H {oi1h:.1f}%，大量平倉","icon":"⚠️"})

        if fr is not None and fr > 0.001:
            triggered.append({"type":"費率過高","level":"high","msg":f"資金費率 +{fr*100:.4f}%，多方過熱","icon":"💸"})
        elif fr is not None and fr < -0.0003:
            triggered.append({"type":"負資金費率","level":"medium","msg":f"資金費率 {fr*100:.4f}%，空方付費","icon":"📉"})

        if lr is not None:
            if lr > 70:
                triggered.append({"type":"多方過擠","level":"medium","msg":f"多空比 {lr:.1f}% 做多，散戶過度樂觀","icon":"🐂"})
            elif lr < 30:
                triggered.append({"type":"空方過擠","level":"medium","msg":f"多空比 {lr:.1f}% 做多，恐慌性做空","icon":"🐻"})

        total_liq = ll + ls
        if total_liq > 1000000:
            triggered.append({"type":"大量爆倉","level":"high","msg":f"5分鐘爆倉 ${total_liq/1e6:.1f}M (多${ll/1e6:.1f}M / 空${ls/1e6:.1f}M)","icon":"💥"})

        if oi1h is not None and oi1h > 3 and p24 < -2:
            triggered.append({"type":"空方建倉","level":"high","msg":f"OI +{oi1h:.1f}% 但價格跌 {p24:.1f}%，空方大量進場","icon":"🚨"})

        if triggered:
            alerts_list.append({
                "sym": sym,
                "price": d.get("price"),
                "pct24h": p24,
                "oi_1h_pct": oi1h,
                "funding_rate": fr,
                "long_ratio": lr,
                "alerts": triggered,
                "alert_count": len(triggered),
                "max_level": "high" if any(a["level"]=="high" for a in triggered) else "medium"
            })

    alerts_list.sort(key=lambda x: (x["max_level"]!="high", -x["alert_count"]))
    return jsonify(alerts_list)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
