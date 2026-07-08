#!/usr/bin/env python3
"""Fetch TSX dividend universe data from Yahoo Finance -> Stock-Screener/data.json"""
import json, time, datetime
import yfinance as yf

SYMBOLS = [
# Banks & lenders
"RY.TO","TD.TO","BNS.TO","BMO.TO","CM.TO","NA.TO","LB.TO","EQB.TO",
# Insurance & holdcos
"MFC.TO","SLF.TO","GWO.TO","IAG.TO","POW.TO","IFC.TO","FFH.TO","ONEX.TO",
# Financial services
"IGM.TO","AGF-B.TO","FSZ.TO","X.TO","GSY.TO","PRL.TO","MKP.TO","FN.TO",
"TF.TO","AI.TO","FC.TO","DIV.TO","EFN.TO","CF.TO","SII.TO","OLY.TO","TRI.TO",
# Telecom & media
"BCE.TO","T.TO","RCI-B.TO","QBR-B.TO","CCA.TO","CGO.TO",
# Utilities & renewables
"FTS.TO","EMA.TO","CU.TO","ACO-X.TO","H.TO","AQN.TO","CPX.TO","NPI.TO",
"BLX.TO","TA.TO","ALA.TO","SPB.TO","PIF.TO","BEPC.TO","BIPC.TO",
# Pipelines & midstream
"ENB.TO","TRP.TO","SOBO.TO","PPL.TO","KEY.TO","GEI.TO",
# Energy
"CNQ.TO","SU.TO","IMO.TO","CVE.TO","TOU.TO","ARX.TO","WCP.TO","VET.TO",
"CJ.TO","PEY.TO","BIR.TO","SGY.TO","POU.TO","HWX.TO","FRU.TO","PSK.TO",
"TPZ.TO","BTE.TO","PXT.TO","PSI.TO","TOT.TO",
# Materials, gold & royalties
"NTR.TO","LIF.TO","AEM.TO","FNV.TO","WPM.TO","ABX.TO","K.TO","AGI.TO",
"PAAS.TO","OR.TO","DPM.TO","BTO.TO","LUN.TO","LUG.TO","CG.TO","TECK-B.TO",
"SJ.TO","ADN.TO","WFG.TO","CAS.TO","RCH.TO",
# Industrials, transport & services
"CNR.TO","CP.TO","TFII.TO","CJT.TO","EIF.TO","MTL.TO","RUS.TO","WTE.TO",
"WJX.TO","ARE.TO","BDT.TO","KBL.TO","XTC.TO","DBM.TO","MRE.TO","LNR.TO",
"MG.TO","FTT.TO","TIH.TO","BDGI.TO","STN.TO","WCN.TO","GIL.TO","VCM.TO","WPK.TO",
# Consumer & staples
"ATD.TO","DOL.TO","L.TO","MRU.TO","WN.TO","EMP-A.TO","SAP.TO","QSR.TO",
"MTY.TO","AW.TO","PZA.TO","CTC-A.TO","NWC.TO","PBH.TO","TCL-A.TO","RSI.TO",
"HLF.TO","JWEL.TO","MFI.TO","CSW-A.TO","ADW-A.TO","DOO.TO","TOY.TO",
# Tech & healthcare
"ENGH.TO","OTEX.TO","ET.TO","CMG.TO","SYZ.TO","TCS.TO","GIB-A.TO","FSV.TO",
"SIA.TO","EXE.TO",
]

FIELDS = ["shortName","sector","currentPrice","regularMarketPrice","dividendRate",
          "dividendYield","trailingEps","trailingPE","beta","marketCap",
          "fiftyTwoWeekHigh","targetMeanPrice","numberOfAnalystOpinions","payoutRatio"]

def _rsi14(closes):
    d = closes.diff()
    gain, loss = d.clip(lower=0).tail(14).mean(), (-d.clip(upper=0)).tail(14).mean()
    return 50.0 if gain == 0 and loss == 0 else 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)

def technical_signal(ticker, hi52, lo52):
    """Base-breakout screen: near the 52wk low with the short-term (20d) trend turning up.
    Deliberately not a continuation-trend follower, so it won't flag stocks already
    extended near their highs. Needs 200+ daily closes and a valid 52wk range;
    otherwise falls back to 'unknown'."""
    try:
        closes = ticker.history(period="1y", interval="1d", auto_adjust=True)["Close"].dropna()
    except Exception:
        return "unknown", None
    if len(closes) < 200 or not hi52 or not lo52 or hi52 <= lo52:
        return "unknown", None
    price = closes.iloc[-1]
    pct_range = (price - lo52) / (hi52 - lo52)  # 0 = at 52wk low, 1 = at 52wk high
    sma20, sma20_prev = closes.tail(20).mean(), closes.iloc[:-10].tail(20).mean()
    band = 0.01  # 1% slope band so a flat SMA20 isn't called turning up/over from noise
    turning_up = price > sma20 and sma20 > sma20_prev * (1 + band)
    rolling_over = price < sma20 and sma20 < sma20_prev * (1 - band)
    near_low, near_high = pct_range <= 0.40, pct_range >= 0.65
    if near_low and turning_up:
        signal = "buy"        # near the 52wk low, short-term trend just turned up - the setup we want
    elif near_high and rolling_over:
        signal = "sell"       # near the 52wk high and starting to roll over - topping out
    elif turning_up or (near_low and not rolling_over):
        signal = "potential"  # improving momentum off the lows, or bottoming near lows but not confirmed yet
    else:
        signal = "neutral"
    return signal, round(_rsi14(closes), 1)

def fetch(sym):
    for attempt in range(3):
        try:
            t = yf.Ticker(sym)
            info = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                raise ValueError("no price")
            rate = info.get("dividendRate")
            yld = round(rate / price * 100, 2) if rate else None
            if yld is None:
                dy = info.get("dividendYield")
                if dy: yld = round(dy * 100, 2) if dy < 0.5 else round(dy, 2)
            hi52, lo52 = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
            signal, rsi = technical_signal(t, hi52, lo52)
            return {
                "sym": sym.replace(".TO",""),
                "name": info.get("shortName",""),
                "sector": info.get("sector","—"),
                "price": round(price,2),
                "yield": yld,
                "divRate": rate,
                "eps": info.get("trailingEps"),
                "pe": info.get("trailingPE"),
                "beta": info.get("beta"),
                "mcap": info.get("marketCap"),
                "hi52": hi52,
                "lo52": lo52,
                "target": info.get("targetMeanPrice"),
                "analysts": info.get("numberOfAnalystOpinions"),
                "payout": info.get("payoutRatio"),
                "signal": signal,
                "rsi": rsi,
            }
        except Exception as e:
            if attempt == 2:
                return {"sym": sym.replace(".TO",""), "error": str(e)[:80]}
            time.sleep(2 * (attempt + 1))

def main():
    out, dead = [], []
    for s in SYMBOLS:
        row = fetch(s)
        (dead if "error" in row else out).append(row)
        time.sleep(0.4)  # be polite
    payload = {
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
        "count": len(out),
        "dead": dead,
        "stocks": out,
    }
    with open("Stock-Screener/data.json","w") as f:
        json.dump(payload, f, separators=(",",":"))
    print(f"OK {len(out)} fetched, {len(dead)} dead: {[d['sym'] for d in dead]}")

if __name__ == "__main__":
    main()
