# Stock-Screener

TSX dividend screener, 160 tickers. Served at /MyRepo/Stock-Screener/.
- `index.html` — frontend, reads `data.json` (relative fetch)
- `fetch_data.py` — writes `data.json`; run locally: `pip install yfinance && python Stock-Screener/fetch_data.py` (from repo root)
- Automation: `.github/workflows/update-stock-data.yml`, weekdays 22:30 UTC + manual trigger
- Scoring: yield gate (default 4%) → analyst target upside (70%) → stability (30%). Tune in-app.
- Technical trend tag (SIGNAL column): a base-breakout screen, not a continuation-trend follower. Uses position within the 52wk range + 20d SMA slope → BUY (bottom 40% of the 52wk range with the 20d trend just turning up), WATCH (momentum improving but not near the low, or bottoming near lows but not confirmed yet), FLAT (no edge, or near lows but still falling), SELL (top 35% of the 52wk range and rolling over — topping out), N/A (under 200 days of price history, or no 52wk range data). Informational only, not part of the score.
