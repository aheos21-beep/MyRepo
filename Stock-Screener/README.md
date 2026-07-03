# Stock-Screener

TSX dividend screener, 160 tickers. Served at /MyRepo/Stock-Screener/.
- `index.html` — frontend, reads `data.json` (relative fetch)
- `fetch_data.py` — writes `data.json`; run locally: `pip install yfinance && python Stock-Screener/fetch_data.py` (from repo root)
- Automation: `.github/workflows/update-stock-data.yml`, weekdays 22:30 UTC + manual trigger
- Scoring: yield gate (default 4%) → analyst target upside (70%) → stability (30%). Tune in-app.
