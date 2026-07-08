# Stock-Screener

TSX dividend screener, 160 tickers. Served at /MyRepo/Stock-Screener/.
- `index.html` — frontend, reads `data.json` (relative fetch)
- `fetch_data.py` — writes `data.json`; run locally: `pip install yfinance && python Stock-Screener/fetch_data.py` (from repo root)
- Automation: `.github/workflows/update-stock-data.yml`, weekdays 22:30 UTC + manual trigger
- Scoring: yield gate (default 4%) → analyst target upside (70%) → stability (30%). Tune in-app.
- Technical trend tag (SIGNAL column): 50/200d SMA trend regime + RSI(14) momentum, symmetric in both directions → BUY (bullish trend + RSI genuinely recovering off a dip), WATCH (bullish trend without a clean entry yet, or a downtrend where momentum already turned up), FLAT (no edge, or a downtrend so deeply oversold it's bounce-risk rather than a confident sell), SELL (confirmed downtrend, momentum still weak), N/A (under 200 days of price history). Informational only, not part of the score.
