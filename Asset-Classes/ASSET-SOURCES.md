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

## The list — 17 assets

### Tier 1 — Fetched. No LLM, $0, no run-to-run variance.

| Asset | Publisher | Benchmark | Credential | Publishes | Pull |
| --- | --- | --- | --- | --- | --- |
| HISA (Canada) | Bank of Canada | Valet series `CBC20210` + curve `BD.CDN.*.DQ.YLD` | **None** ✅ | Daily | Monthly |
| CAD Dividend Stocks | Yahoo via `yfinance` | **CDZ** (Dividend Aristocrats, ~90 names) | **None** ✅ | Daily | Monthly |
| US Dividend Stocks | Yahoo via `yfinance` | **DVY** (iShares Select Dividend) | **None** | Daily | Monthly |
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
- **CDZ, not XDV.** XDV was picked to keep the Canadian dividend sleeve from
  becoming a bank proxy, and turned out to be one — seven of its top ten are
  financials, and it shared six of ten with XFN. CDZ screens on dividend-growth
  streaks over ~90 names, so the sleeve is genuinely distinct from Financials.
  The cost: ~90 names means `yfinance`'s top-10 is far too thin, so CDZ needs a
  real holdings file. **DVY, not SCHD.** SCHD's quality screen was the better
  index, but Schwab returns 403 to non-browser requests and publishes no
  fetchable holdings file. DVY is the same asset class from the one provider
  that does publish openly. An unfetchable benchmark is not a benchmark.
- **Intl Dividend is confirmed viable.** Foreign target coverage came back
  6/6. Benchmark still to pick between IDV and ZDI.

**Resolved:** the XDV/XFN duplication and the bank-proxy problem were the
same problem, and moving the dividend sleeve to CDZ fixes both.

### Tier 2 — One authority, one LLM search, no median.

| Asset | Publisher | Publishes | Pull | Prior swing |
| --- | --- | --- | --- | --- |
| Canadian Real Estate | CREA | **Quarterly** — Jan 15, Apr, Jul 15, Oct 16 ✅ | Late Jan/Apr/Jul/Oct | 0.8pp |
| US Real Estate | CBRE | Annual + mid-year | Jan, Jul | 1.1pp |
| Potash / Fertilizers | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | 3.9pp |
| Copper | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | 4.0pp → expect lower |
| Aluminium | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | — |
| Nickel | World Bank CMO | **Semi-annual** — Apr, Oct | May, Nov | — |

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
| 6 searched, across 3 searches at their own cadence (<1/month averaged) | ≈ $0.04/mo |

**≈ $0.04/month, estimated** — against $2.89/month for 21 assets today. Treat
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
| Single-institution | Canadian / US real estate | One organisation's view on its own schedule |

**Show a range, not just a point, for equity sleeves.** Dispersion within a
sleeve is large — Canadian financials span roughly −1% to +25% at the
quartiles. A single number hides more than any weighting choice does.

**Track the publisher's date, not the fetch date.** If CREA last published 15
July and next publishes 16 October, a July number must not wear an August
badge. This matters more now: the CMO rows can legitimately be five months old.

**Composition:** 8 equity sleeves · 6 commodities · 2 real estate · 1 cash.
No bonds — the SPF route was considered and declined. No lumber — no free
forecast exists.

---

## Verification status — all clear, 2026-08-02

| # | Item | Result |
| --- | --- | --- |
| 1 | EIA STEO series IDs | ✅ `STEO.WTIPUUS`, `STEO.NGHHUUS` |
| 1b | EIA v2 query shape + key | ✅ **200, real forward data** — see below |
| 2 | `yfinance` target coverage | ✅ **18/18** — US 8/8, Canadian 4/4, foreign 6/6 |
| 3 | Holdings files | ✅ **CDZ 102 rows, DVY 106, IDV 132**, all identity-checked |
| 4 | Lumber authority | ❌ none free — dropped |

**Nothing is unverified. The design is ready to build.**

### The EIA call works and returns genuine projections

`GET https://api.eia.gov/v2/steo/data/?api_key=…&frequency=monthly&data[0]=value`
`&facets[seriesId][]=WTIPUUS&sort[0][column]=period&sort[0][direction]=desc`

Returned WTI at 57–61 $/bbl and Henry Hub at 3.27–4.19 $/mmBtu for periods
running to **2027-12** — sixteen months past the run date, confirming STEO is a
forward projection and not a restated history.

### `yfinance` target coverage

Every ticker returned a price, a mean target and an analyst count (13–58 per
name). Foreign listings worked across `.SW`, `.PA`, `.L`, `.T`, `.AX` and `.DE`,
which is what keeps the Intl Dividend row alive.

### Holdings files — iShares only, and the schema is not uniform

| Fund | Rows | Identity |
| --- | --- | --- |
| CDZ | 102 | MATCH |
| DVY | 106 | MATCH |
| IDV | 132 | MATCH |

Pattern: `…/products/{id}/{slug}/latest-holdings.csv`, preceded by a preamble
and dated (`Fund Holdings as of, "Jul 31, 2026"`).

**Columns differ between funds** — CDZ has `Shares`, DVY and IDV have
`Quantity`, and IDV carries an extra `Type` column. **Parse by column name,
never by position.**

Other providers were tried and failed: Schwab 403s non-browser requests, BMO
times out. That is why all three full-holdings sleeves are iShares funds.

**A wrong product ID returns 200 and a valid CSV for the wrong fund.** ID
239500 was used for IDV and served DVY, with nothing in the response signalling
an error; IDV is 239499. Every holdings fetch must assert the fund name inside
the file. A 200 is not evidence the right fund was fetched.

### `yfinance` top-10 coverage, for the sleeves that use it

| XFN 88.7% · XEG 88.1% · XRE 82.3% · ZUT 79.0% · XLK 59.3% |
| --- |

Renormalising a top-10 reweights a sleeve onto its largest names. At ~85% that
distortion is small, which is why these five ship without a holdings file.

## Rejected, and why

| Asset | Reason |
| --- | --- |
| Uranium (2.5pp) | Looked stable, **no publisher identifiable in any run** |
| Gold (8.4pp), Silver (8.7pp), Palladium (7.8pp) | Four sources apiece, none authoritative |
| Lithium | Unit chaos: `$16/kg` and `$15,646/tonne` averaged once gave +12,074% |
| Bitcoin (36.9pp), Ethereum (45.4pp) | No authority exists; houses differ 2-3x. The spread is the honest answer |
| Canadian Bonds, HY Bonds | Reported the policy rate rather than their own return. A Philadelphia Fed SPF route existed and was declined — bonds stay out |
| US Real Estate | CBRE publishes a narrative outlook, not a readable one-year figure. Two searches over sixteen sources returned nothing usable — the same shape of failure as lumber: the institution is nameable, the number is not readable |
| Lumber (3.6pp) | **No free forecast exists.** Fastmarkets Random Lengths sells price assessments, not forecasts; FEA's forecast service is also paywalled. An institution could be named but its published forecast could not be read |
| Wheat and other ags | Content farms entered wheat's median (11.3pp). A USDA WASDE route existed and was declined |
| Refined fuels, electricity, coal | Consumption prices, not holdable asset classes. Would have been free off the existing EIA key |
| Tin, lead, iron ore | Free off the CMO search, but not things a retail allocation holds |

## Making the rows comparable

The sources do not carry the same bias, so showing them side by side unadjusted
invites a false comparison. Analyst price targets sit systematically above
realised prices; an EIA projection and a government bond yield do not.

**Analyst targets are divided by 1.094 before weighting** — a ~9.4% systematic
upward bias on the target level, the most directly applicable published figure.
Applied per holding, to the price target only; a dividend yield is not an
analyst opinion and is left alone. `rRaw` keeps the unadjusted figure so the
source stays auditable, and each tooltip states both.

A flat 20% was considered and rejected: nothing in the literature supports that
magnitude, and applied to the target level it drives most sleeves deeply
negative. Published estimates vary widely by market and period — treat 9.4% as
a defensible default, not a constant of nature.

**The other rows are not adjusted, and that is not a claim they are unbiased.**
Forward rates carry a term premium; a real-estate association forecasting house
prices has an evident conflict. It is that no comparable published estimate
exists for them, and inventing one would be worse than leaving it visible.

## Annual-average forecasts are not one-year-ahead forecasts

The World Bank CMO publishes calendar-year averages. Read in August 2026, its
2026 column is two-thirds elapsed history, so taking it as "one year ahead"
overstates the forecast. Copper's April 2026 table reads $12,000/mt for 2026
and $11,000/mt for 2027 — against a $9,947 spot those are +20.6% and +10.6%,
and only the second answers the question being asked. The prompt now names the
calendar year containing today + 12 months.

The same caution applies to any annual table, including CREA and any commodity
source added later.

## Failure modes

| What breaks | Effect | Response |
| --- | --- | --- |
| `yfinance` breaks (unofficial Yahoo scraper) | **All 8 equity sleeves stale at once** — the single largest concentration of risk on the list | Already a repo dependency and holding; keep last value, flag |
| `yfinance` silently narrows holdings | A sleeve quietly becomes its top names | Assert coverage ≥ a floor per sleeve; stale rather than distort |
| ETF provider changes its holdings file | That sleeve stales | Fall back to top-10 holdings |
| Holdings fetch returns the wrong fund | **Silent** — a wrong product ID gives 200 and valid CSV | Assert the fund name inside the file every run |
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
