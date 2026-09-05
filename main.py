from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import requests, time

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
    "ondo-finance","official-trump","movement","zcash","hyperliquid"
]

# 只掃20個，減少 timeout 風險
OKX_SCAN = [
    "BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","TON",
    "SUI","DOT","ARB","OP","INJ","TRX","LTC","NEAR","UNI","ZEC","HYPE"
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

def okx_get(url):
    try:
        r = requests.get(url, timeout=4, headers=HEADERS)
        d = r.json()
        return d if d.get("code") == "0" else None
    except Exception:
        return None

def fetch_coin_data(sym):
    inst = f"{sym}-USDT-SWAP"
    data = {"sym": sym}
    try:
        d = okx_get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")
        if d and d.get("data"):
            t = d["data"][0]
            last = float(t.get("last") or 0)
            open24 = float(t.get("open24h") or 1) or 1
            data["price"]  = last
            data["pct24h"] = (last - open24) / open24 * 100
            data["vol24h"] = float(t.get("volCcy24h") or 0)
    except Exception:
        pass
    try:
        d = okx_get(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst}")
        if d and d.get("data"):
            data["funding_rate"] = float(d["data"][0].get("fundingRate") or 0)
    except Exception:
        pass
    try:
        d = okx_get(f"https://www.okx.com/api/v5/public/open-interest?instId={inst}")
        if d and d.get("data"):
            data["oi"]     = float(d["data"][0].get("oiCcy") or 0)
            data["oi_usd"] = float(d["data"][0].get("oi") or 0)
    except Exception:
        pass
    try:
        d = okx_get(f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy={sym}&period=1H")
        if d and d.get("data") and len(d["data"]) >= 2:
            latest = float(d["data"][0][1])
            prev   = float(d["data"][1][1])
            data["oi_1h_pct"] = (latest - prev) / prev * 100 if prev else 0
    except Exception:
        pass
    try:
        d = okx_get(f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={sym}&period=5m")
        if d and d.get("data"):
            row = d["data"][0]
            data["long_ratio"]  = float(row[1]) * 100
            data["short_ratio"] = float(row[2]) * 100
    except Exception:
        pass
    try:
        d = okx_get(f"https://www.okx.com/api/v5/rubik/stat/contracts/liquidation-order?instFamily={sym}-USDT&period=5m")
        if d and d.get("data"):
            row = d["data"][0]
            data["liq_long"]  = float(row[1])
            data["liq_short"] = float(row[2])
    except Exception:
        pass
    return data

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
        except Exception:
            pass
    result["coins"] = all_coins
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        result["fear_greed"] = r.json()["data"][0]
    except Exception:
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
    except Exception:
        pass
    return jsonify(result)

@app.route("/detail/<sym>")
def detail(sym):
    return jsonify(fetch_coin_data(sym.upper()))

@app.route("/oi-dashboard")
def oi_dashboard():
    results = []
    for sym in OKX_SCAN:
        try:
            results.append(fetch_coin_data(sym))
        except Exception:
            pass
    results.sort(key=lambda x: abs(x.get("oi_1h_pct") or 0), reverse=True)
    return jsonify(results)

@app.route("/alerts")
def alerts():
    all_data = []
    for sym in OKX_SCAN:
        try:
            all_data.append(fetch_coin_data(sym))
        except Exception:
            pass

    alerts_list = []
    for d in all_data:
        sym  = d.get("sym", "")
        oi1h = d.get("oi_1h_pct")
        fr   = d.get("funding_rate")
        lr   = d.get("long_ratio")
        p24  = d.get("pct24h") or 0
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
            triggered.append({"type":"大量爆倉","level":"high","msg":f"5分鐘爆倉 ${total_liq/1e6:.1f}M","icon":"💥"})
        if oi1h is not None and oi1h > 3 and p24 < -2:
            triggered.append({"type":"空方建倉","level":"high","msg":f"OI +{oi1h:.1f}% 但價格跌 {p24:.1f}%","icon":"🚨"})

        if triggered:
            alerts_list.append({
                "sym": sym, "price": d.get("price"), "pct24h": p24,
                "oi_1h_pct": oi1h, "funding_rate": fr, "long_ratio": lr,
                "alerts": triggered, "alert_count": len(triggered),
                "max_level": "high" if any(a["level"]=="high" for a in triggered) else "medium"
            })

    alerts_list.sort(key=lambda x: (x["max_level"]!="high", -x["alert_count"]))
    return jsonify(alerts_list)



# ═══════════════════════════════════════════════════════════════════
# SNR (Support & Resistance) 分析模組
# 採用 MSNR (Malaysian SNR) 規則：實體 vs 影線、Fresh Level 判定
# ═══════════════════════════════════════════════════════════════════

def get_candles(sym, bar="4H", limit=300):
    """抓 K 線資料，回傳 [{ts,o,h,l,c,vol}, ...] 由舊到新"""
    inst = f"{sym}-USDT-SWAP"
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar={bar}&limit={limit}"
    d = okx_get(url)
    if not d or not d.get("data"):
        return []
    rows = []
    for r in d["data"]:
        try:
            rows.append({
                "ts": int(r[0]),
                "o": float(r[1]), "h": float(r[2]),
                "l": float(r[3]), "c": float(r[4]),
                "vol": float(r[5]),
            })
        except:
            continue
    rows.reverse()  # OKX 回傳是新到舊，反轉成舊到新
    return rows


def find_swings(candles, lookback=5):
    """找出擺盪高低點 (swing high / swing low)
    lookback: 左右各需比較幾根K棒"""
    swings = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        c = candles[i]
        left  = candles[i-lookback:i]
        right = candles[i+1:i+1+lookback]

        # Swing High: 高點高於左右兩側
        if all(c["h"] >= x["h"] for x in left) and all(c["h"] >= x["h"] for x in right):
            swings.append({
                "type": "high", "idx": i, "price": c["h"],
                "ts": c["ts"], "candle": c
            })
        # Swing Low: 低點低於左右兩側
        if all(c["l"] <= x["l"] for x in left) and all(c["l"] <= x["l"] for x in right):
            swings.append({
                "type": "low", "idx": i, "price": c["l"],
                "ts": c["ts"], "candle": c
            })
    return swings


def classify_candle(c):
    """MSNR 燭台分類：判斷實體與影線比例"""
    body   = abs(c["c"] - c["o"])
    total  = c["h"] - c["l"]
    if total == 0:
        return {"type": "doji", "body_pct": 0, "strength": 0}
    body_pct = body / total * 100
    upper_wick = c["h"] - max(c["o"], c["c"])
    lower_wick = min(c["o"], c["c"]) - c["l"]

    if body_pct < 20:
        ctype = "doji"       # 十字星，猶豫
    elif body_pct > 70:
        ctype = "marubozu"   # 大實體，強勢
    elif lower_wick > body * 2:
        ctype = "pinbar_bull"  # 下影線長，看漲
    elif upper_wick > body * 2:
        ctype = "pinbar_bear"  # 上影線長，看跌
    else:
        ctype = "normal"

    return {
        "type": ctype,
        "body_pct": round(body_pct, 1),
        "bullish": c["c"] > c["o"],
        "upper_wick_pct": round(upper_wick/total*100, 1) if total else 0,
        "lower_wick_pct": round(lower_wick/total*100, 1) if total else 0,
    }


def build_snr_levels(candles, swings, tolerance_pct=0.6):
    """把 swing 點聚合成 SNR 區域，計算觸碰次數與 freshness"""
    if not candles:
        return []
    current_price = candles[-1]["c"]
    levels = []

    for s in swings:
        price = s["price"]
        # 找是否已有相近的 level (在 tolerance 內視為同一區)
        merged = False
        for lv in levels:
            if abs(lv["price"] - price) / price * 100 <= tolerance_pct:
                lv["touches"] += 1
                lv["swing_idxs"].append(s["idx"])
                # 取平均價
                lv["price"] = (lv["price"] * (lv["touches"]-1) + price) / lv["touches"]
                lv["last_idx"] = max(lv["last_idx"], s["idx"])
                merged = True
                break
        if not merged:
            cd = classify_candle(s["candle"])
            levels.append({
                "price": price,
                "type": s["type"],          # high=壓力, low=支撐
                "touches": 1,
                "first_idx": s["idx"],
                "last_idx": s["idx"],
                "swing_idxs": [s["idx"]],
                "candle_type": cd["type"],
                "body_pct": cd["body_pct"],
            })

    # 計算 freshness：level 形成後，價格有沒有再回來測試過
    n = len(candles)
    for lv in levels:
        after = candles[lv["last_idx"]+1:]
        retests = 0
        for c in after:
            # 價格進入這個 level 區間就算一次回測
            in_range = (c["l"] <= lv["price"] * (1 + tolerance_pct/100)) and (c["h"] >= lv["price"] * (1 - tolerance_pct/100))
            if in_range:
                retests += 1
        lv["retests"] = retests
        lv["fresh"] = retests == 0          # MSNR: 未被測試過 = fresh level
        lv["distance_pct"] = (lv["price"] - current_price) / current_price * 100
        lv["age_bars"] = n - lv["last_idx"]

        # 強度評分：fresh > touches > 燭台型態
        strength = 0
        if lv["fresh"]:            strength += 40
        if lv["touches"] >= 3:     strength += 30
        elif lv["touches"] == 2:   strength += 20
        if lv["candle_type"] in ("marubozu", "pinbar_bull", "pinbar_bear"):
            strength += 20
        if lv["body_pct"] > 60:    strength += 10
        lv["strength"] = min(100, strength)

    return levels


def analyze_snr(sym, bar="4H"):
    """完整 SNR 分析：找出當前價格上下最近的關鍵位"""
    candles = get_candles(sym, bar=bar, limit=300)
    if len(candles) < 30:
        return {"error": "K線資料不足", "sym": sym}

    current = candles[-1]["c"]
    swings  = find_swings(candles, lookback=5)
    levels  = build_snr_levels(candles, swings)

    # 分成上方壓力 / 下方支撐
    resistances = sorted(
        [l for l in levels if l["price"] > current],
        key=lambda x: x["price"]
    )[:5]
    supports = sorted(
        [l for l in levels if l["price"] < current],
        key=lambda x: -x["price"]
    )[:5]

    # 最近一根 K 棒的型態
    last_candle = classify_candle(candles[-1])

    # 判斷當前位置：靠近支撐還是壓力
    position = "區間中段"
    nearest_sup = supports[0] if supports else None
    nearest_res = resistances[0] if resistances else None
    if nearest_sup and nearest_res:
        range_size = nearest_res["price"] - nearest_sup["price"]
        if range_size > 0:
            pos_pct = (current - nearest_sup["price"]) / range_size * 100
            if pos_pct < 25:   position = "貼近支撐"
            elif pos_pct > 75: position = "貼近壓力"

    # 趨勢判斷：用最近20根的高低點結構
    recent = candles[-20:]
    highs = [c["h"] for c in recent]
    lows  = [c["l"] for c in recent]
    if highs[-1] > max(highs[:10]) and lows[-1] > min(lows[:10]):
        trend = "上升結構 (HH/HL)"
    elif highs[-1] < max(highs[:10]) and lows[-1] < min(lows[:10]):
        trend = "下降結構 (LH/LL)"
    else:
        trend = "橫向整理"

    return {
        "sym": sym,
        "timeframe": bar,
        "current_price": current,
        "trend": trend,
        "position": position,
        "last_candle": last_candle,
        "resistances": [{
            "price": round(l["price"], 6),
            "distance_pct": round(l["distance_pct"], 2),
            "touches": l["touches"],
            "fresh": l["fresh"],
            "retests": l["retests"],
            "strength": l["strength"],
            "candle_type": l["candle_type"],
            "age_bars": l["age_bars"],
        } for l in resistances],
        "supports": [{
            "price": round(l["price"], 6),
            "distance_pct": round(l["distance_pct"], 2),
            "touches": l["touches"],
            "fresh": l["fresh"],
            "retests": l["retests"],
            "strength": l["strength"],
            "candle_type": l["candle_type"],
            "age_bars": l["age_bars"],
        } for l in supports],
    }


@app.route("/snr/<sym>")
def snr_endpoint(sym):
    bar = request.args.get("tf", "4H")
    return jsonify(analyze_snr(sym.upper(), bar))


@app.route("/snr-confluence/<sym>")
def snr_confluence(sym):
    """SNR + 微觀結構匯流分析：把價格行為跟衍生品數據結合"""
    sym = sym.upper()
    htf = analyze_snr(sym, "4H")   # HTF 找位階
    ltf = analyze_snr(sym, "1H")   # LTF 找進場
    deriv = fetch_coin_data(sym)   # 微觀結構

    if htf.get("error"):
        return jsonify({"error": htf["error"], "sym": sym})

    signals = []
    score = 0

    # ── 1. HTF 位置訊號 ────────────────────────────────────────
    pos = htf.get("position")
    if pos == "貼近支撐":
        score += 25
        signals.append({
            "cat": "SNR", "level": "high", "dir": "long",
            "text": f"HTF({htf['timeframe']}) 價格貼近支撐區，具備做多位階優勢"
        })
    elif pos == "貼近壓力":
        score -= 25
        signals.append({
            "cat": "SNR", "level": "high", "dir": "short",
            "text": f"HTF({htf['timeframe']}) 價格貼近壓力區，具備做空位階優勢"
        })

    # ── 2. Fresh Level 加權 ────────────────────────────────────
    fresh_sup = [s for s in htf["supports"] if s["fresh"]]
    fresh_res = [r for r in htf["resistances"] if r["fresh"]]
    if fresh_sup and abs(fresh_sup[0]["distance_pct"]) < 3:
        score += 20
        signals.append({
            "cat": "SNR", "level": "high", "dir": "long",
            "text": f"下方 {abs(fresh_sup[0]['distance_pct']):.1f}% 有 Fresh 支撐 ${fresh_sup[0]['price']}，強度 {fresh_sup[0]['strength']}"
        })
    if fresh_res and abs(fresh_res[0]["distance_pct"]) < 3:
        score -= 20
        signals.append({
            "cat": "SNR", "level": "high", "dir": "short",
            "text": f"上方 {abs(fresh_res[0]['distance_pct']):.1f}% 有 Fresh 壓力 ${fresh_res[0]['price']}，強度 {fresh_res[0]['strength']}"
        })

    # ── 3. 趨勢結構 ────────────────────────────────────────────
    trend = htf.get("trend", "")
    if "上升" in trend:
        score += 15
        signals.append({"cat":"結構","level":"medium","dir":"long","text":f"HTF {trend}，順勢偏多"})
    elif "下降" in trend:
        score -= 15
        signals.append({"cat":"結構","level":"medium","dir":"short","text":f"HTF {trend}，順勢偏空"})

    # ── 4. LTF 燭台確認 ────────────────────────────────────────
    lc = ltf.get("last_candle", {}) if not ltf.get("error") else {}
    ct = lc.get("type")
    if ct == "pinbar_bull":
        score += 15
        signals.append({"cat":"燭台","level":"medium","dir":"long","text":"LTF 出現看漲 Pin Bar（下影線長，買方防守）"})
    elif ct == "pinbar_bear":
        score -= 15
        signals.append({"cat":"燭台","level":"medium","dir":"short","text":"LTF 出現看跌 Pin Bar（上影線長，賣方壓制）"})
    elif ct == "marubozu":
        d = "long" if lc.get("bullish") else "short"
        score += 10 if lc.get("bullish") else -10
        signals.append({"cat":"燭台","level":"medium","dir":d,
                        "text":f"LTF 大實體K棒（實體 {lc.get('body_pct')}%），{'買' if lc.get('bullish') else '賣'}方主導"})

    # ── 5. 微觀結構匯流 ────────────────────────────────────────
    oi1h = deriv.get("oi_1h_pct")
    fr   = deriv.get("funding_rate")
    lr   = deriv.get("long_ratio")
    p24  = deriv.get("pct24h") or 0

    if oi1h is not None:
        if oi1h > 3 and pos == "貼近支撐":
            score += 20
            signals.append({"cat":"微觀","level":"high","dir":"long",
                            "text":f"支撐區 OI +{oi1h:.1f}%，多方在關鍵位建倉（強匯流）"})
        elif oi1h > 3 and pos == "貼近壓力":
            score -= 20
            signals.append({"cat":"微觀","level":"high","dir":"short",
                            "text":f"壓力區 OI +{oi1h:.1f}%，空方在關鍵位建倉（強匯流）"})
        elif oi1h < -3:
            signals.append({"cat":"微觀","level":"low","dir":"neutral",
                            "text":f"OI {oi1h:.1f}% 減倉，市場觀望"})

    if fr is not None:
        frp = fr * 100
        if frp < -0.01 and pos == "貼近支撐":
            score += 15
            signals.append({"cat":"微觀","level":"medium","dir":"long",
                            "text":f"支撐區負資金費率 {frp:.4f}%，空方付費，反轉條件成熟"})
        elif frp > 0.05 and pos == "貼近壓力":
            score -= 15
            signals.append({"cat":"微觀","level":"medium","dir":"short",
                            "text":f"壓力區費率 +{frp:.4f}% 偏高，多頭擁擠"})

    if lr is not None:
        if lr < 35 and pos == "貼近支撐":
            score += 10
            signals.append({"cat":"情緒","level":"medium","dir":"long",
                            "text":f"支撐區散戶做空 {100-lr:.0f}%，逆向指標偏多"})
        elif lr > 65 and pos == "貼近壓力":
            score -= 10
            signals.append({"cat":"情緒","level":"medium","dir":"short",
                            "text":f"壓力區散戶做多 {lr:.0f}%，逆向指標偏空"})

    # ── 結論 ───────────────────────────────────────────────────
    if score >= 45:    verdict, vcolor = "強力做多", "strong_long"
    elif score >= 20:  verdict, vcolor = "偏多", "long"
    elif score <= -45: verdict, vcolor = "強力做空", "strong_short"
    elif score <= -20: verdict, vcolor = "偏空", "short"
    else:              verdict, vcolor = "觀望", "neutral"

    # 建議進出場位
    plan = {}
    if score >= 20 and htf["supports"]:
        s = htf["supports"][0]
        r = htf["resistances"][0] if htf["resistances"] else None
        plan = {
            "dir": "做多",
            "entry": f"回踩 ${s['price']} 附近（支撐 {s['strength']}分）",
            "stop":  f"跌破 ${round(s['price']*0.985, 6)}",
            "target": f"${r['price']}" if r else "前高",
            "rr": round(abs((r['price']-htf['current_price'])/(htf['current_price']-s['price']*0.985)), 2) if r and htf['current_price']!=s['price']*0.985 else None
        }
    elif score <= -20 and htf["resistances"]:
        r = htf["resistances"][0]
        s = htf["supports"][0] if htf["supports"] else None
        plan = {
            "dir": "做空",
            "entry": f"反彈 ${r['price']} 附近（壓力 {r['strength']}分）",
            "stop":  f"突破 ${round(r['price']*1.015, 6)}",
            "target": f"${s['price']}" if s else "前低",
            "rr": round(abs((htf['current_price']-s['price'])/(r['price']*1.015-htf['current_price'])), 2) if s and r['price']*1.015!=htf['current_price'] else None
        }

    return jsonify({
        "sym": sym,
        "current_price": htf["current_price"],
        "score": score,
        "verdict": verdict,
        "verdict_class": vcolor,
        "htf": htf,
        "ltf_candle": lc,
        "derivatives": {
            "oi_1h_pct": oi1h, "funding_rate": fr,
            "long_ratio": lr, "pct24h": p24
        },
        "signals": signals,
        "plan": plan,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
