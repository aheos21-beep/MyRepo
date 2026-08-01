# Asset source reference — rebuild spec

Spec for rebuilding the dashboard from the assets that demonstrably work,
rather than patching the ones that do not. Covers which assets are in, where
each one's number comes from, the horizon, and the cost.

---

## Decision 1 — Horizon: a single 1-year figure

6-month / 1-year / 18-month columns were considered and rejected, because
those numbers cannot be derived for every asset:

| Source | Sub-annual granularity? |
| --- | --- |
| EIA STEO | Yes — monthly and quarterly, out to 18 months |
| BoC yield curve | Yes — forward rates at any tenor |
| CREA, CBRE, USDA | **No** — annual or marketing-year figures only |
| Analyst price targets | **No** — year-end targets only |

Producing a 6-month number for CREA or a bank price target would mean
interpolating and presenting the result as if it were published. So the
dashboard shows **one column: the 1-year projected return.**

Where a source gives an 18-month figure, annualise it back:

```
r_1yr = (1 + r_18mo) ** (1 / 1.5) - 1
```

This is a real simplification, not a compromise. One number per asset means
one thing to verify, one thing to get wrong, and no compounding across years
— which is where the worst bugs came from (a correct ~1,400% three-year
Ethereum total once rendered as +77,248% because annual and cumulative
figures were confused).

## Decision 2 — Only assets with a named publisher

> Name the institution that publishes the forecast. If you cannot, the asset
> does not go in.

This test costs nothing and predicts stability better than any code change
made so far. Stable-looking numbers with no provenance are worse than
volatile ones with provenance, because nothing signals they are unsupported.

---

## The finding behind both decisions

Stability does not track how volatile the *asset* is. It tracks **whether one
institution is the recognised publisher of that forecast.**

Measured across three consecutive runs on identical logic (swing = spread of
the 3-year average return between runs):

| Asset | Swing | Sources/yr | Why |
| --- | --- | --- | --- |
| HISA (Canada) | 0.1pp | 5.0 | The Bank of Canada *is* the rate |
| Canadian Real Estate | 0.8pp | 2.0 | CREA is the recognised forecaster |
| US Real Estate | 1.1pp | 4.0 | CBRE is the recognised forecaster |
| Gold | 8.4pp | 4.0 | Four sources, no authority among them |
| Bitcoin | 36.9pp | 3.3 | No authority; houses differ 2-3x |
| Ethereum | 45.4pp | 2.7 | Same, plus content farms in the mix |

More sources does not help. Gold pulls four per year and still swings 8.4pp;
Canadian Real Estate pulls two and swings 0.8pp. **Authority beats quantity.**

---

## The starting nine

### Tier 1 — Fetched. No LLM, no cost, no variance.

The ≤18-month horizon is what makes this tier possible: EIA STEO covers oil
and gas completely within it, so those assets need no search at all.

| Asset | Source | Access | Notes |
| --- | --- | --- | --- |
| HISA (Canada) | Bank of Canada Valet | Free, **no key** | Forward rates from the GoC curve are the market's own 1-year forecast — computed, not guessed |
| WTI Crude Oil | EIA STEO | Free, key required | 18-month projection, annualised back |
| Natural Gas | EIA STEO | Free, key required | 18-month projection, annualised back |

### Tier 2 — One authority, one search, no median.

The median buys nothing where a recognised publisher exists.

| Asset | Authority | Observed swing |
| --- | --- | --- |
| Canadian Real Estate | CREA | 0.8pp |
| US Real Estate | CBRE | 1.1pp |
| Lumber | Fastmarkets | 3.6pp |
| Potash / Fertilizers | USDA / World Bank | 3.9pp |

### Tier 3 — Median of several, variance accepted.

No single authority, but the disagreement is modest and the sources are real.

| Asset | Swing |
| --- | --- |
| Copper | 4.0pp |
| US Dividend Stocks | 4.1pp |

---

## Deliberately excluded

| Asset | Swing | Reason |
| --- | --- | --- |
| Uranium | 2.5pp | **No publisher identifiable in any run** — stable-looking but unattributable |
| CAD Dividend Stocks | 2.9pp | Same; one source per year, unnamed |
| US Tech Stocks | 6.4pp | Borderline variance; easy to add back |
| Palladium | 7.8pp | Borderline |
| Gold | 8.4pp | Borderline; four sources, none authoritative |
| Silver | 8.7pp | Borderline |
| Canadian REITs | 9.0pp | Thin sourcing (1.3 sources/yr) |
| Intl Dividend Stocks | 10.6pp | Content farms were the **only** identifiable sources |
| Wheat | 11.3pp | Has an authority (USDA) but content farms crept into its median |
| Lithium | — | Unit chaos: `$16/kg` and `$15,646/tonne` averaged together once gave +12,074% |
| Bitcoin | 36.9pp | Inherent — no authority exists |
| Ethereum | 45.4pp | Inherent |

**Known bias in this list:** it is commodity and real-estate heavy and thin on
equities. That is not accidental. Equity forecasts are index targets where
every house publishes a different number, so they cannot clear the stability
bar. Equity representation means accepting Tier 3 variance for it.

---

## Cost

Derived from observed runs, not vendor list prices. Today: **~$0.14 per asset
per month** ($2.89 ÷ 21 assets), roughly a quarter search fees and the rest
tokens from search results entering context.

| Tier | Method | Est. cost/asset |
| --- | --- | --- |
| 1 | API fetch | **$0.00** |
| 2 | 1 search, 1 source, no verify pass | ~$0.05 |
| 3 | 2-3 searches, median, verify pass | ~$0.14 |

**The starting nine:**

| Count | Tier | Cost |
| --- | --- | --- |
| 3 | Tier 1 (HISA, oil, natgas) | $0.00 |
| 4 | Tier 2 | $0.20 |
| 2 | Tier 3 | $0.28 |
| **9** | | **≈ $0.48/month** |

Against $2.89 today for 21 assets, for a set whose numbers can be defended.

**Scaling.** Tier 2 assets cost about $0.05 each, so 40 of them lands near
**$2/month** — below today's bill at roughly double the coverage. The
constraint is not cost; it is that only assets with a named publisher
qualify.

**Cadence, separately.** HISA moved 0.1pp across three runs, so refreshing it
monthly is paying for noise. Quarterly for Tiers 1-2 and monthly for Tier 3
roughly halves whatever the above totals to.

---

## Before building

1. **Verify the EIA STEO series IDs** for WTI spot and Henry Hub. Confirmed:
   STEO publishes forward projections and has a free API. Not confirmed: the
   exact series names. Everything in Tier 1 for oil and gas rests on this.
2. **Register an EIA API key** and add it as a repository secret. This is the
   only new operational dependency in the design.
3. **Decide the cash number.** Forward rates from the GoC curve are the
   *market's* forecast, not an analyst's. Correct and free, but a different
   thing wearing the same label — worth being explicit in the UI.

## Carried forward from the current build

Worth keeping regardless of which assets are in:

- The model never does arithmetic — it reports values, Python computes returns.
- Structured output via a forced tool call, never parsed from prose.
- Bases pinned from a live feed where one exists, verified otherwise.
- Failures isolated per asset; stale assets keep their previous value and are
  recorded rather than silently refreshed.
- Output escaped before rendering — model-authored text reaches the page.
