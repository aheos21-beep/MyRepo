# Asset source reference — rebuild spec

Which asset classes are in, where each number comes from, when it changes,
what it costs. Every claim marked verified or not.

**Status: the list is settled. Nothing is built yet.** Four data-path
lookups remain (see *To verify before building*); those are lookups, not
open questions.

## Decisions

**Horizon: a single 1-year figure.** 6mo/1yr/18mo was rejected — not derivable
from CREA, CBRE or analyst targets, which publish year-end or 12-month figures
only. An 18-month figure is annualised back: `(1 + r) ** (1/1.5) - 1`. One
column also removes multi-year compounding, the source of the worst bug in the
previous build.

**Inclusion rule: name the institution that publishes the forecast.** If you
cannot, the asset does not go in.

**An asset class is defined by a benchmark you could buy.** The ETF is not a
forecast — the forecast is the analyst target on each holding. The ETF settles
the prior question of *which names, at what weight*, so that decision belongs
to the fund provider rather than to us. Expected return is
`Σ wᵢ × [(targetᵢ / priceᵢ − 1) + yieldᵢ]` over the fund's actual holdings.
Strictly the right object is an index, but index providers do not publish
constituents freely and the tracking ETF does, daily.

**No asset requires a median.** Copper was the last holdout and now reads from
the World Bank CMO. Every row traces to one named publisher — which is the
inclusion rule actually being enforced rather than merely stated.

---

## The list — 18 assets

### Tier 1 — Fetched. No LLM, $0, no run-to-run variance.

| Asset | Publisher | Benchmark | Credential | Publishes | Pull |
| --- | --- | --- | --- | --- | --- |
| HISA (Canada) | Bank of Canada | Valet series `CBC20210` + curve `BD.CDN.*.DQ.YLD` | **None** ✅ | Daily | Monthly |
| CAD Dividend Stocks | Yahoo via `yfinance` | **XDV** | **None** ✅ | Daily | Monthly |
| US Dividend Stocks | Yahoo via `yfinance` | **SCHD** | **None** | Daily | Monthly |
| Canadian REITs | Yahoo via `yfinance` | **XRE** (cap-weighted) | **None** | Daily | Monthly |
| US Tech | Yahoo via `yfinance` | **XLK** | **None** | Daily | Monthly |
| Canadian Energy | Yahoo via `yfinance` | **XEG** | **None** | Daily | Monthly |
| Canadian Financials | Yahoo via `yfinance` | **XFN** | **None** | Daily | Monthly |
| Canadian Utilities | Yahoo via `yfinance` | **ZUT** (equal-weighted) | **None** | Daily | Monthly |
| Intl Dividend | Yahoo via `yfinance` | ⚠️ TBD — **drop if coverage fails** | **None** | Daily | Monthly |
| WTI Crude Oil | EIA STEO | REST API | Key (free) | Monthly ~6-12th | Mid-month |
| Natural Gas | EIA STEO | REST API | Key (free) | Monthly ~6-12th | Mid-month |

Notes on the benchmark picks:

- **XLK is deliberately top-heavy.** A handful of megacaps drive the number.
  That is what US tech *is* on a cap-weighted basis; QQQ would have diluted it
  with non-tech names.
- **ZUT is equal-weighted, XRE is not.** Not an inconsistency — each is the
  standard benchmark for its sleeve. The provider's choice, not ours.
- **XDV over VDY** to keep the Canadian dividend sleeve from becoming a bank
  proxy; **SCHD over VYM** for its quality screen.
- **Intl Dividend is provisional.** `yfinance` target coverage on foreign
  listings is unverified. If it fails, the row is dropped — not substituted.

### Tier 2 — One authority, one LLM search, no median.

| Asset | Publisher | Publishes | Pull | Prior swing |
| --- | --- | --- | --- | --- |
| Canadian Real Estate | CREA | **Quarterly** — Jan 15, Apr, Jul 15, Oct 16 ✅ | Late Jan/Apr/Jul/Oct | 0.8pp |
| US Real Estate | CBRE | Annual + mid-year | Jan, Jul | 1.1pp |
| Potash / Fertilizers | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | 3.9pp |
| Copper | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | 4.0pp → expect lower |
| Aluminium | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | — |
| Nickel | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | — |
| Lumber | Fastmarkets | ⚠️ Cadence unknown | Quarterly until known | 3.6pp |

**One CMO search covers four assets.** Potash, copper, aluminium and nickel
all come out of the same twice-yearly document, so metals three and four cost
nothing beyond the first.

**Copper moved off the sell-side median.** Its 4.0pp swing came from averaging
houses that disagreed. A single publisher should be steadier, at the price of
being up to six months stale — the publication date makes that visible.

### Cost

| Rows | Cost |
| --- | --- |
| 11 fetched | $0 |
| 7 searched, across 4 searches at their own cadence (~1/month averaged) | ≈ $0.05/mo |

**≈ $0.05/month, estimated** — against $2.89/month for 21 assets today. Treat
the figure as unconfirmed until the first real run meters it.

Cost scales with **sources, not assets**. Adding an equity sleeve or another
CMO metal is free; adding a new publisher is what costs.

---

## What each number actually is

Not the same kind of claim, and the dashboard should not blur them:

| Kind | Assets | Caveat |
| --- | --- | --- |
| Market-implied | HISA | Not an opinion — what the curve prices. But forward rates are biased predictors of future spot. **The only fixed-income row on the list** |
| Official projection | Oil, gas, potash, copper, aluminium, nickel | A government or multilateral model. EIA publishes wide confidence bands on oil |
| Analyst consensus | All 8 equity sleeves | Real consensus, but sell-side targets are **persistently optimistic as a class** — expect the equity rows to skew positive |
| Single-institution | Canadian / US real estate, lumber | One organisation's view on its own schedule |

**Show a range, not just a point, for equity sleeves.** Dispersion within a
sleeve is large — Canadian financials span roughly −1% to +25% at the
quartiles. A single number hides more than any weighting choice does.

**Track the publisher's date, not the fetch date.** If CREA last published 15
July and next publishes 16 October, a July number must not wear an August
badge. This matters more now: the CMO rows can legitimately be five months old.

**Composition:** 8 equity sleeves · 7 commodities · 2 real estate · 1 cash.
No bonds — the SPF route was considered and declined.

---

## To verify before building

Lookups, not judgment calls.

1. **EIA STEO series IDs** for WTI spot and Henry Hub — both energy rows depend on it.
2. **`yfinance` US coverage** — Canadian is proven (171 of 173 TSX names return
   targets daily in `Stock-Screener/fetch_data.py`); all 173 rows there are
   Canadian, so US is expected but untested. Gates SCHD and XLK.
3. **ETF holdings fetch** — provider CSVs (iShares, BMO) are free and daily, but
   format stability is unproven. Fallback: `yfinance` top-10 holdings
   renormalised, which for concentrated Canadian ETFs is often 50-70% of the fund.
4. **Fastmarkets cadence** — the only Tier 2 row with an unknown schedule.

Plus one that resolves itself on first run: whether `yfinance` returns targets
for the Intl Dividend benchmark's foreign listings. If not, drop the row.

## Rejected, and why

| Asset | Reason |
| --- | --- |
| Uranium (2.5pp) | Looked stable, **no publisher identifiable in any run** |
| Gold (8.4pp), Silver (8.7pp), Palladium (7.8pp) | Four sources apiece, none authoritative |
| Lithium | Unit chaos: `$16/kg` and `$15,646/tonne` averaged once gave +12,074% |
| Bitcoin (36.9pp), Ethereum (45.4pp) | No authority exists; houses differ 2-3x. The spread is the honest answer |
| Canadian Bonds, HY Bonds | Reported the policy rate rather than their own return. A Philadelphia Fed SPF route existed and was declined — bonds stay out |
| Wheat and other ags | Content farms entered wheat's median (11.3pp). A USDA WASDE route existed and was declined |
| Refined fuels, electricity, coal | Consumption prices, not holdable asset classes. Would have been free off the existing EIA key |
| Tin, lead, iron ore | Free off the CMO search, but not things a retail allocation holds |

## Failure modes

| What breaks | Effect | Response |
| --- | --- | --- |
| `yfinance` breaks (unofficial Yahoo scraper) | **All 8 equity sleeves stale at once** — the single largest concentration of risk on the list | Already a repo dependency and holding; keep last value, flag |
| ETF provider changes its holdings file | That sleeve stales | Fall back to top-10 holdings |
| Yahoo returns no target for a holding | 2 of 173 already do | Drop and reweight; do not substitute |
| EIA key revoked / STEO reshaped | Oil and gas stale | Keep last value, flag |
| World Bank CMO search fails | **Four commodity rows stale together** | Keep last value, flag |
| A Tier 2 publisher stops publishing | That asset stales indefinitely | Publication date makes it visible, not silent |

## Practices to carry forward

- The model never does arithmetic — it reports values, Python computes returns.
- Structured output via a forced tool call, never parsed from prose.
- Bases pinned from a live feed where one exists, verified otherwise.
- Failures isolated per asset; stale assets keep their previous value and are
  recorded rather than silently refreshed.
- Output escaped before rendering — model-authored text reaches the page.
