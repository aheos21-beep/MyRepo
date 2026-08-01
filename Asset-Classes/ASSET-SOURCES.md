# Asset source reference — rebuild spec

Which asset classes are in, where each number comes from, when it changes,
what it costs. Every claim marked verified or not.

**Horizon: a single 1-year figure.** 6mo/1yr/18mo was rejected — not derivable
from CREA, CBRE or analyst targets, which publish year-end or 12-month figures
only. An 18-month figure is annualised back: `(1 + r) ** (1/1.5) - 1`. One
column also removes multi-year compounding, the source of the worst bug in the
previous build.

**Inclusion rule: name the institution that publishes the forecast.** If you
cannot, the asset does not go in.

**An asset class is defined by a benchmark you could buy.** For equity sleeves
the benchmark ETF's published holdings and weights settle what the asset class
*is* — no invented equal-weight vs cap-weight decision. Expected return is
`Σ wᵢ × [(targetᵢ / priceᵢ − 1) + yieldᵢ]` over the fund's actual holdings.

---

## Core — ten assets, confirmed

### Tier 1 — Fetched. No LLM, $0, no run-to-run variance.

| Asset | Publisher | Method | Credential | Publishes | Pull | The number is |
| --- | --- | --- | --- | --- | --- | --- |
| HISA (Canada) | Bank of Canada | Valet API, series `CBC20210` + curve `BD.CDN.*.DQ.YLD` | **None** ✅ | Daily | Monthly | Forward rate implied by the GoC curve — the market's own expectation |
| CAD Dividend Stocks | Yahoo via `yfinance` | Benchmark ETF holdings → per-holding target + yield | **None** ✅ | Daily | Monthly | Weighted analyst consensus, 12-14 analysts/name |
| US Dividend Stocks | Yahoo via `yfinance` | Same | **None** | Daily | Monthly | Same |
| WTI Crude Oil | EIA STEO | REST API | Key (free) | Monthly ~6-12th | Mid-month | EIA's own 18-month projection, annualised |
| Natural Gas | EIA STEO | REST API | Key (free) | Monthly ~6-12th | Mid-month | Same |

### Tier 2 — One authority, one LLM search, no median.

| Asset | Publisher | Publishes | Pull | Swing |
| --- | --- | --- | --- | --- |
| Canadian Real Estate | CREA | **Quarterly** — Jan 15, Apr, Jul 15, Oct 16 ✅ | Late Jan/Apr/Jul/Oct | 0.8pp |
| US Real Estate | CBRE | Annual + mid-year | Jan, Jul | 1.1pp |
| Potash / Fertilizers | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | 3.9pp |
| Lumber | Fastmarkets | ⚠️ Cadence unknown | Quarterly until known | 3.6pp |

### Tier 3 — Median of several. No authority exists.

| Asset | Publisher | Publishes | Pull | Swing |
| --- | --- | --- | --- | --- |
| Copper | Mixed sell-side | Ad hoc | Monthly | 4.0pp |

**Core cost ≈ $0.19/month** (5 fetched at $0, 4 searched at their own cadence
≈ $0.05, copper ≈ $0.14). Today's build is $2.89/month for 21 assets.

---

## Suggested additions

Grouped by the source that unlocks them. **Marginal cost is near zero within
a source already integrated** — cost scales with sources, not assets.

### A. Equity sleeves — $0 each, same method as the two core sleeves

Any sleeve with a benchmark ETF works. Candidate benchmarks:

| Asset class | Benchmark | Note |
| --- | --- | --- |
| Canadian REITs | XRE / ZRE | REITs are stocks, so they carry analyst targets. Previously dropped for thin LLM sourcing (9.0pp) — this method fixes that |
| US Tech | XLK / QQQ | Previously dropped at 6.4pp |
| Canadian Energy | XEG | 30 names already in the screener universe |
| Canadian Financials | XFN | 32 names |
| Canadian Utilities | ZUT | 12 names |
| Intl Dividend | ⚠️ | Foreign listings — `yfinance` target coverage is patchier abroad. Verify before committing |

### B. EIA STEO — $0 each, same API call and key

Gasoline · Diesel / heating oil · Propane · Electricity · Coal.
Monthly, 18-month horizon, same credential as oil and gas.

### C. World Bank CMO — ~$0 marginal, same twice-yearly search

Aluminium · Nickel · Zinc · Tin · Lead · Iron ore.
One document already being read for potash; more rows cost nothing extra.
Filter to what is investable rather than taking all 46 commodities.

### D. USDA WASDE — one monthly search covers several

Wheat · Corn · Soybeans.
**Wheat is a re-entry candidate**: it was dropped at 11.3pp not for lack of an
authority but because content farms entered its median. Pinning to USDA only
should fix it — worth testing before trusting.

### E. Philadelphia Fed Survey of Professional Forecasters — free, quarterly

3-month T-bill · 10-year Treasury · inflation.
Notable because it is a **published median of ~40 professional forecasters** —
the thing the app's own median was trying to construct, done properly and for
free. This is the honest route back to bonds, which were dropped for reporting
the policy rate rather than their own return.

---

## What each number actually is

Not the same kind of claim, and the dashboard should not blur them:

| Kind | Assets | Caveat |
| --- | --- | --- |
| Market-implied | HISA, Treasuries | Not an opinion — what the curve prices. But forward rates are biased predictors of future spot |
| Official projection | Oil, gas, potash, ags | A government or multilateral model. EIA publishes wide confidence bands on oil |
| Analyst consensus | All equity sleeves, copper | Real consensus, but sell-side targets are **persistently optimistic as a class** — expect the equity rows to skew positive |
| Single-institution | Canadian / US real estate | One organisation's view on its own schedule |

**Show a range, not just a point, for equity sleeves.** Dispersion within a
sleeve is large — Canadian financials span roughly −1% to +25% at the
quartiles. A single number hides more than any weighting choice does.

**Track the publisher's date, not the fetch date.** If CREA last published 15
July and next publishes 16 October, a July number must not wear an August
badge.

---

## Not verified

1. **EIA STEO series IDs** for WTI spot and Henry Hub — both oil rows depend on it.
2. **`yfinance` US coverage** — Canadian is proven (171 of 173 TSX names return
   targets daily in `Stock-Screener/fetch_data.py`); all 173 rows are Canadian,
   so US is expected but untested here.
3. **ETF holdings fetch** — provider CSVs (iShares, Vanguard) are free and
   daily, but format stability is unproven. Fallback: `yfinance` top-10
   holdings renormalised, which for concentrated Canadian dividend ETFs is
   often 50-70% of the fund.
4. **Benchmark choice per sleeve** — a judgment call, not a technical one.
5. **Fastmarkets cadence.**

## Rejected, and why

| Asset | Reason |
| --- | --- |
| Uranium (2.5pp) | Looked stable, **no publisher identifiable in any run** |
| Gold (8.4pp), Silver (8.7pp), Palladium (7.8pp) | Four sources apiece, none authoritative |
| Intl Dividend via LLM (10.6pp) | Content farms were the only identifiable sources — but see A above for an ETF route |
| Lithium | Unit chaos: `$16/kg` and `$15,646/tonne` averaged once gave +12,074% |
| Bitcoin (36.9pp), Ethereum (45.4pp) | No authority exists; houses differ 2-3x. The spread is the honest answer |
| Canadian Bonds, HY Bonds | Reported the policy rate rather than their own return — but see E above for an SPF route |

## Failure modes

| What breaks | Effect | Response |
| --- | --- | --- |
| `yfinance` breaks (unofficial Yahoo scraper) | **All equity sleeves stale at once** | Already a repo dependency and holding; keep last value, flag |
| ETF provider changes its holdings file | That sleeve stales | Fall back to top-10 holdings |
| Yahoo returns no target for a holding | 2 of 173 already do | Drop and reweight; do not substitute |
| EIA key revoked / STEO reshaped | Oil and gas stale | Keep last value, flag |
| A Tier 2 publisher stops publishing | That asset stales indefinitely | Publication date makes it visible, not silent |

## Practices to carry forward

- The model never does arithmetic — it reports values, Python computes returns.
- Structured output via a forced tool call, never parsed from prose.
- Bases pinned from a live feed where one exists, verified otherwise.
- Failures isolated per asset; stale assets keep their previous value and are
  recorded rather than silently refreshed.
- Output escaped before rendering — model-authored text reaches the page.
