# Asset source reference — rebuild spec

Which assets are in, where each number comes from, when it changes, and what
it costs. One row per asset, and every claim marked verified or not.

**Horizon: a single 1-year figure.** 6mo/1yr/18mo was rejected because those
numbers are not derivable for every source — EIA and the BoC curve give
sub-annual granularity, but CREA, CBRE and analyst targets publish year-end or
12-month figures only. An 18-month figure is annualised back:
`r_1yr = (1 + r_18mo) ** (1/1.5) - 1`. One column also removes multi-year
compounding, the source of the worst bug in the previous build.

**Inclusion rule: name the institution that publishes the forecast.** If you
cannot, the asset does not go in. Stable-looking numbers with no provenance
are worse than volatile ones with it, because nothing signals they are
unsupported.

---

## The list

### Tier 1 — Fetched. No LLM, $0, no run-to-run variance.

| Asset | Source | Method | Credential | Publishes | Pull when | The number is | Swing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HISA (Canada) | Bank of Canada Valet | REST API, series `CBC20210` + curve group `BD.CDN.*.DQ.YLD` | **None** ✅ verified | Daily (business days) | Monthly | Forward rate implied by the GoC curve — the *market's* 1-yr expectation, computed not opined | 0.1pp |
| CAD Dividend Stocks | Yahoo, via `yfinance` | Basket of TSX names → `targetMeanPrice`, `numberOfAnalystOpinions`, `yield` | **None** | Daily | Monthly | `(target ÷ price − 1) + yield`, weighted across the basket. 12-14 analysts/name | — |
| US Dividend Stocks | Yahoo, via `yfinance` | Same method, US names | **None** | Daily | Monthly | Same | — |
| WTI Crude Oil | EIA STEO | REST API | **Key required** (free) | Monthly, ~6th-12th | Mid-month | EIA's own 18-month projection, annualised back | — |
| Natural Gas | EIA STEO | REST API | **Key required** (free) | Monthly, ~6th-12th | Mid-month | Same | — |

### Tier 2 — One authority, one LLM search, no median.

The median buys nothing where a recognised publisher exists.

| Asset | Source | Method | Publishes | Pull when | The number is | Swing |
| --- | --- | --- | --- | --- | --- | --- |
| Canadian Real Estate | CREA | LLM search, pinned to CREA | **Quarterly** — Jan 15, Apr, Jul 15, Oct 16 ✅ verified | Late Jan / Apr / Jul / Oct | CREA's national average price forecast | 0.8pp |
| US Real Estate | CBRE | LLM search, pinned to CBRE | Annual + mid-year update | Jan and Jul | CBRE outlook figure | 1.1pp |
| Potash / Fertilizers | World Bank CMO | LLM search, pinned to World Bank | **Semi-annual** — April, October | May and November | World Bank commodity forecast | 3.9pp |
| Lumber | Fastmarkets | LLM search | ⚠️ **Cadence unknown** | Quarterly until known | Price forecast | 3.6pp |

### Tier 3 — Median of several. No authority exists.

| Asset | Source | Method | Publishes | Pull when | Swing |
| --- | --- | --- | --- | --- | --- |
| Copper | Mixed sell-side | LLM search + median + basis verification | Ad hoc revisions | Monthly | 4.0pp |

**Ten assets.** Swing = spread of the 3-year average across three consecutive
runs on identical logic; it measures *search reproducibility*, not accuracy.
Assets sourced by API have no swing by construction. Equity sleeves have no
swing figure because the method is new.

---

## Cost

Today's build: **$2.89/month for 21 assets** (~$0.14 each), roughly a quarter
search fees and the rest tokens from search results entering context.

| Tier | Assets | Method | Monthly |
| --- | --- | --- | --- |
| 1 | 5 | API / library fetch | **$0.00** |
| 2 | 4 | 1 search each, at source cadence | ~$0.05 |
| 3 | 1 | Search + median + verify, monthly | ~$0.14 |
| | **10** | | **≈ $0.19/month** |

Tier 2 is cheap because pulls follow the publisher: CREA four times a year and
the World Bank twice, not twelve times each.

**Scaling.** Two paths, both cheap:

- **Equity sleeves are now nearly free to add.** The `yfinance` basket method
  generalises — US Tech, Canadian REITs, or any sleeve you can name
  constituents for costs $0 and inherits double-digit analyst counts. The
  assets dropped for weak sourcing (US Tech, Canadian REITs) can come back
  this way rather than via LLM search.
- **Tier 2 assets cost ~$0.05 each**, so 40 of them lands near $2/month —
  under today's bill at roughly double the coverage.

---

## What each number actually is

Worth keeping straight, because they are not the same kind of claim:

| Kind | Assets | Caveat |
| --- | --- | --- |
| Market-implied | HISA | Not an opinion — it is what the curve prices. But forward rates are known to be biased predictors of future spot rates |
| Official projection | Oil, gas, potash | A government or multilateral body's own model. EIA publishes wide confidence bands on its oil forecasts |
| Analyst consensus | CAD/US dividends, copper | Real consensus (12-14 analysts), but sell-side targets are persistently optimistic as a class |
| Single-institution forecast | Canadian/US real estate | One organisation's view, revised on its own schedule |

**Track the publisher's date, not ours.** The badge previously said "Updated
Aug 1" for every asset. If CREA last published on 15 July and next publishes
16 October, a July number was wearing an August date. Store the source's
publication date per asset and show that — it makes staleness visible instead
of implied.

---

## Not verified yet

1. **EIA STEO series IDs** for WTI spot and Henry Hub. STEO's forward
   projections and free API are confirmed; the exact series names are not.
   Both oil and gas rows depend on this.
2. **`yfinance` US coverage.** Canadian is proven — this repo's
   `Stock-Screener/fetch_data.py` returns targets and analyst counts for 171
   of 173 TSX names, updated daily. The 173 rows are all Canadian, so US is
   expected to work but is untested here.
3. **Lumber / Fastmarkets publication cadence.**
4. **Basket constituents** for each equity sleeve — not yet chosen.

## Rejected, and why

| Asset | Reason |
| --- | --- |
| Uranium (2.5pp), CAD Dividend via LLM (2.9pp) | Looked stable, but **no publisher identifiable in any run** |
| Gold (8.4pp), Silver (8.7pp), Palladium (7.8pp) | Four sources apiece, none authoritative |
| Intl Dividend Stocks (10.6pp) | Content farms were the **only** identifiable sources |
| Wheat (11.3pp) | Has an authority (USDA) but content farms entered its median |
| Lithium | Unit chaos — `$16/kg` and `$15,646/tonne` averaged together once gave +12,074% |
| Bitcoin (36.9pp), Ethereum (45.4pp) | No authority exists; houses differ 2-3x. The spread is the honest answer |
| Canadian Bonds, HY Bonds | Reported the BoC policy rate rather than their own return; HY would not refresh at all |

**Known bias:** this list is commodity and real-estate heavy. Equity coverage
now rests entirely on the `yfinance` basket method, which is one library
against one site — see the failure modes below.

## Failure modes

| What breaks | Effect | Response |
| --- | --- | --- |
| `yfinance` breaks (unofficial Yahoo scraper) | Both equity sleeves go stale at once | Already a repo dependency and holding; keep last value and flag |
| Yahoo returns no target for a name | 2 of 173 already do | Drop from basket, reweight, do not substitute |
| EIA key revoked / STEO reshaped | Oil and gas stale | Keep last value and flag |
| A Tier 2 publisher stops publishing | That asset stales indefinitely | Publication date makes it visible rather than silent |

## Practices to carry forward

- The model never does arithmetic — it reports values, Python computes returns.
- Structured output via a forced tool call, never parsed from prose.
- Bases pinned from a live feed where one exists, verified otherwise.
- Failures isolated per asset; stale assets keep their previous value and are
  recorded rather than silently refreshed.
- Output escaped before rendering — model-authored text reaches the page.
