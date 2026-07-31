#!/usr/bin/env python3
"""Fetch TSX dividend universe data from Yahoo Finance -> Stock-Screener/data.json"""
import json, time, datetime
import numpy as np
import pandas as pd
import yfinance as yf

SYMBOLS = [
# Banks & lenders
"RY.TO","TD.TO","BNS.TO","BMO.TO","CM.TO","NA.TO","LB.TO","EQB.TO",
# Insurance & holdcos
"MFC.TO","SLF.TO","GWO.TO","IAG.TO","POW.TO","IFC.TO","FFH.TO","ONEX.TO","BAM.TO","BN.TO","TSU.TO",
# Financial services
"IGM.TO","AGF-B.TO","FSZ.TO","X.TO","GSY.TO","PRL.TO","MKP.TO","FN.TO",
"TF.TO","AI.TO","FC.TO","DIV.TO","EFN.TO","CF.TO","SII.TO","OLY.TO","TRI.TO",
# Telecom & media
"BCE.TO","T.TO","RCI-B.TO","QBR-B.TO","CCA.TO","CGO.TO",
# Utilities & renewables
"FTS.TO","EMA.TO","CU.TO","ACO-X.TO","H.TO","AQN.TO","CPX.TO","NPI.TO",
"BLX.TO","TA.TO","ALA.TO","SPB.TO","PIF.TO","BEPC.TO","BIPC.TO","RNW.TO",
# Pipelines & midstream
"ENB.TO","TRP.TO","SOBO.TO","PPL.TO","KEY.TO","GEI.TO",
# Energy
"CNQ.TO","SU.TO","IMO.TO","CVE.TO","TOU.TO","ARX.TO","WCP.TO","VET.TO",
"CJ.TO","PEY.TO","BIR.TO","SGY.TO","POU.TO","HWX.TO","FRU.TO","PSK.TO",
"TPZ.TO","BTE.TO","PXT.TO","PSI.TO","TOT.TO","CEU.TO",
# Materials, gold & royalties
"NTR.TO","LIF.TO","AEM.TO","FNV.TO","WPM.TO","ABX.TO","K.TO","AGI.TO",
"PAAS.TO","OR.TO","DPM.TO","BTO.TO","LUN.TO","LUG.TO","CG.TO","TECK-B.TO",
"SJ.TO","ADN.TO","WFG.TO","CAS.TO","RCH.TO","ALS.TO","TXG.TO",
# Industrials, transport & services
"CNR.TO","CP.TO","TFII.TO","CJT.TO","EIF.TO","MTL.TO","RUS.TO","WTE.TO",
"WJX.TO","ARE.TO","BDT.TO","KBL.TO","XTC.TO","DBM.TO","MRE.TO","LNR.TO",
"MG.TO","FTT.TO","TIH.TO","BDGI.TO","STN.TO","WCN.TO","GIL.TO","VCM.TO","WPK.TO",
"ADEN.TO","BYD.TO","CCL-B.TO","GFL.TO","HPS-A.TO","NOA.TO","WSP.TO",
# Consumer & staples
"ATD.TO","DOL.TO","L.TO","MRU.TO","WN.TO","EMP-A.TO","SAP.TO","QSR.TO",
"MTY.TO","AW.TO","PZA.TO","CTC-A.TO","NWC.TO","PBH.TO","TCL-A.TO","RSI.TO",
"HLF.TO","JWEL.TO","MFI.TO","CSW-A.TO","ADW-A.TO","DOO.TO","TOY.TO",
# Tech & healthcare
"ENGH.TO","OTEX.TO","ET.TO","CMG.TO","SYZ.TO","TCS.TO","GIB-A.TO","FSV.TO",
"SIA.TO","EXE.TO","SIS.TO",
]

FIELDS = ["shortName","sector","currentPrice","regularMarketPrice","dividendRate",
          "dividendYield","trailingEps","trailingPE","beta","marketCap",
          "fiftyTwoWeekHigh","targetMeanPrice","numberOfAnalystOpinions","payoutRatio"]

def _rsi14(closes):
    """Informational only - no longer drives the signal, kept for the detail panel."""
    d = closes.diff()
    gain, loss = d.clip(lower=0).tail(14).mean(), (-d.clip(upper=0)).tail(14).mean()
    return 50.0 if gain == 0 and loss == 0 else 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)

def _clamp(x, lo, hi):
    return max(lo, min(hi, x))

def _persistence_days(bullish):
    """How many consecutive trading days (ending today) SMA50 has stayed above SMA200."""
    days = 0
    for v in bullish.iloc[::-1]:
        if bool(v):
            days += 1
        else:
            break
    return days

def _risk_adj_momentum(closes, window=200):
    """200-day return divided by realized (annualized) volatility over the same window.
    Tried ADX first; on realistic low-daily-vol blue-chip drift it read as noise (day-to-day
    +DI/-DI is too short-memory to see a slow multi-month compounding trend, and on a pure
    zero-drift random walk it frequently reads as strong purely by chance - both confirmed by
    synthetic testing). This risk-adjusted-return measure directly asks 'is the move large
    relative to the noise', which is the right question and held up correctly in testing."""
    if len(closes) < window + 1:
        return None
    c = closes.tail(window + 1)
    ret = c.iloc[-1] / c.iloc[0] - 1
    daily_vol = c.pct_change().std()
    if not daily_vol or pd.isna(daily_vol):
        return 0.0
    return float(ret / (daily_vol * (252 ** 0.5)))

def trend_score(closes, highs, lows):
    """0-100 spectrum: how established is the uptrend, not just 'is there one'.
    Blends how long SMA50 has held above SMA200 (persistence) with risk-adjusted momentum
    (200d return / realized vol), crediting strength only when momentum is actually positive."""
    if len(closes) < 260:
        return None, None, None
    sma50, sma200 = closes.rolling(50).mean(), closes.rolling(200).mean()
    days = _persistence_days(sma50 > sma200)
    persistence = _clamp(days / 60 * 100, 0, 100)  # 60+ consecutive days = full marks
    ram = _risk_adj_momentum(closes)
    strength = _clamp(max(ram, 0) / 2.0 * 100, 0, 100) if ram is not None else 0.0  # ram >= 2.0 = full marks
    score = round(0.6 * persistence + 0.4 * strength, 1)
    return score, days, (round(ram, 2) if ram is not None else None)

def headroom_score(price, hi3y, lo3y):
    """0-100 spectrum: room below the 3yr high, not a hard 52wk-range cutoff."""
    if not hi3y or not lo3y or hi3y <= lo3y:
        return None
    pct = _clamp((price - lo3y) / (hi3y - lo3y), 0, 1)
    return round((1 - pct) * 100, 1)

def fundamentals_score(trailing_eps, forward_eps, dividends, payout):
    """0-100 spectrum blending forward EPS growth with real (multi-year) dividend growth,
    not just a dividend that hasn't been cut. Missing pieces default to a neutral 50,
    not zero, so thin data doesn't masquerade as bad fundamentals.
    A stretched payout ratio discounts the whole score - a rebound in a name that's
    paying out well beyond its earnings isn't credible 'fundamentals moving with price',
    it's a dividend at risk regardless of what EPS growth estimates say."""
    eps_score = 50.0
    if trailing_eps and forward_eps is not None and trailing_eps > 0:
        growth = (forward_eps - trailing_eps) / trailing_eps
        eps_score = _clamp(max(growth, 0) / 0.15 * 100, 0, 100)  # 15%+ forward growth = full marks
    div_score = 50.0
    if dividends is not None and len(dividends):
        tz = dividends.index.tz
        now = pd.Timestamp.now(tz=tz) if tz else pd.Timestamp.now()
        recent = dividends[dividends.index > now - pd.Timedelta(days=365)].sum()
        older = dividends[(dividends.index <= now - pd.Timedelta(days=730)) &
                           (dividends.index > now - pd.Timedelta(days=1095))].sum()
        if older > 0:
            growth = (recent - older) / older
            div_score = _clamp(max(growth, 0) / 0.15 * 100, 0, 100)  # 15%+ cumulative growth = full marks
    payout_factor = 1.0 if payout is None else _clamp(1 - max(payout - 0.75, 0) / 0.75, 0.3, 1.0)
    return round((eps_score + div_score) / 2 * payout_factor, 1)

def catalyst_score(next_earnings_date, today):
    """0-100 spectrum on distance to the next known earnings date - the one dated catalyst
    reliably available for free. Missing data (common for smaller TSX names) defaults to a
    neutral 50 rather than 0, since that's a data-coverage gap, not evidence of no catalyst."""
    if not next_earnings_date:
        return 50.0
    days_out = (next_earnings_date - today).days
    if days_out < 0:
        return 50.0  # stale calendar entry
    if days_out <= 120:
        return 100.0
    return round(_clamp(100 - (days_out - 120) / 60 * 100, 0, 100), 1)

def valuation_score(target, hi3y):
    """0-100 spectrum: does the analyst target imply a valuation the stock has actually
    reached before (within its 3yr range), or a fresh all-time-high re-rating."""
    if not target or not hi3y:
        return 50.0
    if target <= hi3y:
        return 100.0
    overshoot = (target - hi3y) / hi3y
    return round(_clamp(100 - overshoot / 0.20 * 100, 0, 100), 1)

def _next_earnings_date(ticker, today):
    try:
        cal = ticker.calendar
        raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if raw:
            dates = [d for d in (raw if isinstance(raw, list) else [raw]) if d]
            future = [d for d in dates if d >= today]
            if future:
                return min(future)
    except Exception:
        pass
    return None

def assess(ticker, price, trailing_eps, forward_eps, target, payout, today):
    """Runs the full spectrum-scoring engine off one 3yr price-history pull.
    Returns None fields (and 'unknown' signal) when there's too little history to trust."""
    try:
        hist = ticker.history(period="3y", interval="1d", auto_adjust=True)
        closes, highs, lows = hist["Close"].dropna(), hist["High"].dropna(), hist["Low"].dropna()
    except Exception:
        closes = pd.Series(dtype=float)
    if len(closes) < 260:
        return {"signal": "unknown", "trend": None, "headroom": None, "fund": None,
                "catalyst": None, "valuation": None, "hi3y": None, "lo3y": None,
                "persistDays": None, "momentum": None, "rsi": None, "nextEarnings": None}
    hi3y, lo3y = float(highs.tail(756).max()), float(lows.tail(756).min())
    trend, persist_days, momentum = trend_score(closes, highs, lows)
    headroom = headroom_score(price, hi3y, lo3y)
    try:
        dividends = ticker.dividends
    except Exception:
        dividends = None
    fund = fundamentals_score(trailing_eps, forward_eps, dividends, payout)
    next_earn = _next_earnings_date(ticker, today)
    catalyst = catalyst_score(next_earn, today)
    valuation = valuation_score(target, hi3y)
    # Geometric mean of trend, headroom, and the fund/catalyst/valuation average - a stock
    # weak on EITHER trend or headroom gets pulled down hard (both are required, not just
    # averaged-in factors 1-of-5), while still being a smooth spectrum rather than a cutoff.
    # Calibrated against real output: thresholds are approx. top-3% / top-25% / top-75%.
    if trend is not None and headroom is not None:
        others = [x for x in (fund, catalyst, valuation) if x is not None]
        avg_others = sum(others) / len(others) if others else 50.0
        combo = 100 * ((trend / 100) * (headroom / 100) * (avg_others / 100)) ** (1 / 3)
    else:
        combo = None
    if combo is None:
        signal = "unknown"
    elif combo >= 65:
        signal = "buy"
    elif combo >= 45:
        signal = "potential"
    elif combo >= 20:
        signal = "neutral"
    else:
        signal = "avoid"
    return {"signal": signal, "trend": trend, "headroom": headroom, "fund": fund,
            "catalyst": catalyst, "valuation": valuation, "hi3y": hi3y, "lo3y": lo3y,
            "persistDays": persist_days, "momentum": momentum, "rsi": round(_rsi14(closes), 1),
            "nextEarnings": next_earn.isoformat() if next_earn else None}

def fetch(sym):
    today = datetime.date.today()
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
            trailing_eps, forward_eps = info.get("trailingEps"), info.get("forwardEps")
            target = info.get("targetMeanPrice")
            payout = info.get("payoutRatio")
            a = assess(t, price, trailing_eps, forward_eps, target, payout, today)
            return {
                "sym": sym.replace(".TO",""),
                "name": info.get("shortName",""),
                "sector": info.get("sector","—"),
                "price": round(price,2),
                "yield": yld,
                "divRate": rate,
                "eps": trailing_eps,
                "forwardEps": forward_eps,
                "pe": info.get("trailingPE"),
                "beta": info.get("beta"),
                "mcap": info.get("marketCap"),
                "hi52": hi52,
                "lo52": lo52,
                "target": target,
                "analysts": info.get("numberOfAnalystOpinions"),
                "payout": payout,
                "signal": a["signal"],
                "trend": a["trend"],
                "headroom": a["headroom"],
                "fund": a["fund"],
                "catalyst": a["catalyst"],
                "valuation": a["valuation"],
                "hi3y": a["hi3y"],
                "lo3y": a["lo3y"],
                "persistDays": a["persistDays"],
                "momentum": a["momentum"],
                "rsi": a["rsi"],
                "nextEarnings": a["nextEarnings"],
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
