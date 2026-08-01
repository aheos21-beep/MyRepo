# Asset source reference

Working reference for which assets belong in the dashboard, where each one's
numbers should come from, and what that costs. Written to be argued with —
the tiers are a proposal, not a decision.

## The finding this is built on

Stability does not track how volatile the *asset* is. It tracks **whether one
institution is the recognised publisher of that forecast.**

Measured across three consecutive runs on identical logic (swing = spread of
the 3-year average return between runs):

| Asset | Swing | Sources/yr | Why |
| --- | --- | --- | --- |
| HISA (Canada) | 0.1pp | 5.0 | Bank of Canada *is* the rate |
| Canadian Real Estate | 0.8pp | 2.0 | CREA is the recognised forecaster |
| US Real Estate | 1.1pp | 4.0 | CBRE is the recognised forecaster |
| … | | | |
| Bitcoin | 36.9pp | 3.3 | no authority; Bernstein vs StanChart differ 2-3x |
| Ethereum | 45.4pp | 2.7 | same, plus content farms in the mix |

More sources does not help. Gold pulls 4 sources per year and still swings
8.4pp; Canadian Real Estate pulls 2 and swings 0.8pp. **Authority beats
quantity**, which is why the tiers below are organised by source type rather
than by asset class.

## Rule for adding an asset

> Name the institution that publishes its forecast. If you cannot, the asset
> will behave like Bitcoin or Intl Dividend Stocks: expensive, volatile, and
> unattributable.

This test costs nothing and predicts the outcome better than any code change
made so far.

---

## Tier 1 — Fetch it, no LLM

Deterministic, free, and stable by construction. Zero API cost and zero
run-to-run variance.

| Asset | Source | Endpoint | Notes |
| --- | --- | --- | --- |
| HISA (Canada) | Bank of Canada Valet | `bankofcanada.ca/valet` series `CBC20210` | No key, no registration, versioned since 2017 |
| *(rate-quoted assets generally)* | BoC Valet | group `BD.CDN.*.DQ.YLD` | The GoC curve gives **market-implied forward rates** — the market's own forecast, computed not guessed |
| Bitcoin / Ethereum *(basis only)* | CoinGecko | `/simple/price` | Already live in `update_data.py` |

The yield-curve point is the interesting one: for anything quoted as a rate,
forward rates are derivable from today's curve. That is a real forecast,
free, deterministic, and it removes the LLM from those assets entirely.

## Tier 2 — Fetch the near term, extend the rest

| Asset | Source | Horizon | Gap |
| --- | --- | --- | --- |
| WTI Crude Oil | EIA STEO API | 18 months | Year 1 fetched; years 2-3 still need a source |
| Natural Gas | EIA STEO API | 18 months | same |

EIA STEO publishes genuine forward projections monthly, updated on a fixed
schedule. Free, but **requires a registered API key** — a new repository
secret, which is the one operational cost of this tier.

## Tier 3 — Single authoritative source, no median needed

These have one recognised publisher, and the data shows they are already
stable. Paying for several sources and a median buys nothing here.

| Asset | Authority | Observed swing |
| --- | --- | --- |
| Canadian Real Estate | CREA | 0.8pp |
| US Real Estate | CBRE | 1.1pp |
| Potash / Fertilizers | USDA / World Bank | 3.9pp |
| Wheat | USDA | 11.3pp ⚠️ |
| Lumber | Fastmarkets | 3.6pp |

Wheat is the odd one: it has an authority (USDA) but still swung 11.3pp,
because content-farm sources crept into its median alongside USDA. Pinning it
to USDA only should fix that — worth testing before trusting it.

## Tier 4 — Genuine analyst disagreement, median required

No single authority exists. The median is doing real work here and should
stay.

| Asset | Swing | Note |
| --- | --- | --- |
| Copper | 4.0pp | acceptable |
| US Dividend Stocks | 4.1pp | acceptable |
| US Tech Stocks | 6.4pp | acceptable |
| Palladium | 7.8pp | acceptable |
| Gold | 8.4pp | acceptable |
| Silver | 8.7pp | acceptable |
| Canadian REITs | 9.0pp | thin sourcing (1.3/yr) |
| Lithium | — | unit chaos; needs a pinned unit before it is trustworthy |
| Bitcoin | 36.9pp | inherent — analysts differ 2-3x |
| Ethereum | 45.4pp | inherent |

Crypto stays only if volatility is acceptable as *information*: the spread is
the honest answer, and the tooltip already shows it.

## Tier 5 — Candidates to drop

| Asset | Why |
| --- | --- |
| Intl Dividend Stocks | Content farms were the **only** identifiable sources; swings 10.6pp |
| Uranium | No publisher identifiable in any run |
| CAD Dividend Stocks | No publisher identifiable; single source per year |

Stable-looking numbers with no provenance are worse than volatile ones with
provenance, because nothing signals that they are unsupported.

---

## Cost model

Derived from observed runs, not vendor list prices. Current design: **~$0.14
per asset per month** ($2.89 ÷ 21 assets). Roughly a quarter of that is web
search fees ($0.01/search) and the rest is tokens, dominated by search
results entering context.

Per-asset monthly estimate by tier:

| Tier | Method | Est. cost/asset | Variance |
| --- | --- | --- | --- |
| 1 | API fetch | **$0.00** | none |
| 2 | API + light search for years 2-3 | ~$0.05 | low |
| 3 | 1 search, 1 source, no verify pass | ~$0.05 | low |
| 4 | 2-3 searches, median, verify pass | ~$0.14 | high |

### Worked example — a stable core of 10

| Count | Tier | Cost |
| --- | --- | --- |
| 1 | Tier 1 (HISA) | $0.00 |
| 2 | Tier 2 (oil, natgas) | $0.10 |
| 5 | Tier 3 | $0.25 |
| 2 | Tier 4 (gold, copper) | $0.28 |
| **10** | | **≈ $0.63/month** |

Against $2.89 today for 21 assets — and the ten that remain are the ten whose
numbers can be defended.

### Scaling

Adding assets under the Tier 3 discipline costs about **$0.05 each**, so 40
assets lands near **$2/month** — below today's bill with roughly double the
coverage. Adding Tier 4 assets costs ~3x that and brings volatility with it,
which is the real argument for the naming rule above.

### A cadence lever, separately

HISA moved 0.1pp across three runs; refreshing it monthly is paying for
noise. Quarterly for Tier 1-3 and monthly for Tier 4 roughly halves whatever
the above totals to, with no information lost.

---

## Open questions

- EIA STEO stops at 18 months. Extend years 2-3 by trend, source them
  separately, or shorten the dashboard's horizon for those assets?
- Forward rates from the GoC curve are the market's forecast, not an
  analyst's. Is that the number the dashboard should show for cash?
- Is crypto's spread better shown as a **range** than a single median? The
  disagreement is the honest signal and a point estimate hides it.
