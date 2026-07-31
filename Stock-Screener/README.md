# Stock-Screener

TSX dividend screener, 175 tickers (includes the full S&P/TSX Canadian Dividend Aristocrats list, excluding REIT trust units with a -UN ticker suffix). Served at /MyRepo/Stock-Screener/.
- `index.html` — frontend, reads `data.json` (relative fetch)
- `fetch_data.py` — writes `data.json`; run locally: `pip install yfinance && python Stock-Screener/fetch_data.py` (from repo root)
- Automation: `.github/workflows/update-stock-data.yml`, weekdays 22:30 UTC + manual trigger
## Screening philosophy

Hunting for a TSX dividend payer with a credible path to meaningful price upside over
roughly a 4-month window: caught at the beginning-to-middle of a **confirmed** upward
trend — early, but only once the trend is real, not a guess on an unconfirmed bounce
(falling knife) and not chasing a name that's already had its move (extended, near highs).

- **YIELD GATE %** (default 4%, tunable in-app) is the *only* hard cutoff. Everything else
  is a 0–100 spectrum score, not a pass/fail filter — a stock doesn't vanish from the table
  for being weak on trend or headroom, it just scores lower.
- **SCORE** = the plain average of five 0–100 components computed server-side in
  `fetch_data.py` from a single 3-year daily price/dividend/fundamentals pull per ticker
  (all free via `yfinance`, no paid data):
  - **Trend** — how established the uptrend is: consecutive trading days SMA50 has held
    above SMA200 (persistence, capped at 60 days), blended with risk-adjusted momentum
    (200-day return ÷ realized volatility). Deliberately *not* ADX — synthetic testing
    showed ADX badly underrates the slow, low-volatility drift typical of blue-chip
    dividend payers, and can even score pure sideways noise higher than a genuine trend.
  - **Headroom** — position within the **3-year** high/low range (not 52-week — a steady
    compounder can sit near its 52wk high all year without being "extended" in any
    meaningful sense). Near the 3yr low scores high, at/above the 3yr high scores 0.
  - **Fundamentals** — forward EPS growth vs. trailing EPS, blended with real dividend
    growth (trailing-12-month dividend total vs. the 12-month total from 2–3 years back,
    from `yfinance` dividend history) — "growing," not just "hasn't been cut."
  - **Catalyst** — proximity to the next known earnings date (100 inside the ~4-month
    window, decaying to 0 further out). The one dated catalyst reliably free and
    automatable; regulatory decisions, in-service dates, etc. aren't in any free feed and
    aren't modeled.
  - **Valuation** — whether the analyst target price sits within the 3yr range (100) or
    implies a fresh multi-year-high re-rating (decaying toward 0).
  - Missing data defaults to a neutral 50 for a component (not 0), so a data gap doesn't
    masquerade as a bad read. Needs 260+ trading days of history or the whole assessment
    falls back to "unknown" rather than guessing.
- **SIGNAL badge** (BUY/WATCH/FLAT/AVOID/N/A) is a derived quick-glance category from the
  Trend+Headroom blend — informational, not a separate cutoff.
- **ROR (1Yr)** (analyst-implied expected return) is still shown for context but no longer
  feeds the score.
- An empty or sparse "pass" list in a market that's run hard is an expected, acceptable
  outcome of this design, not a bug.
