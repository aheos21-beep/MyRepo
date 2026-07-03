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

def fetch(sym):
    for attempt in range(3):
        try:
            info = yf.Ticker(sym).info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                raise ValueError("no price")
            rate = info.get("dividendRate")
            yld = round(rate / price * 100, 2) if rate else None
            if yld is None:
                dy = info.get("dividendYield")
                if dy: yld = round(dy * 100, 2) if dy < 0.5 else round(dy, 2)
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
                "hi52": info.get("fiftyTwoWeekHigh"),
                "target": info.get("targetMeanPrice"),
                "analysts": info.get("numberOfAnalystOpinions"),
                "payout": info.get("payoutRatio"),
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
