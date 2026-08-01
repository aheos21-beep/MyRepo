#!/usr/bin/env python3
"""
Refresh Asset-Classes/data.json from the Claude API. Run monthly by
.github/workflows/monthly-asset-refresh.yml. Requires ANTHROPIC_API_KEY.

Design, and the reasoning behind it:

1. Grounded in real sources. Every call has web_search enabled, so figures
   come from current pages rather than the model's training data. Known
   algorithmic "price prediction" content farms are excluded at search time
   (BLOCKED_SOURCE_DOMAINS) — they publish confident multi-year numbers with
   no analyst behind them and are indistinguishable from research once they
   are in context.

2. Structured output, never free text. Results arrive through a forced tool
   call, so a model that is unsure cannot substitute a prose caveat for an
   answer.

3. The model never does arithmetic. It reports only what it can read off a
   page — a current basis value, three absolute yearly targets, whether those
   are prices or interest rates, and any income yield — and compute_returns()
   derives the annual percentages. An earlier version asked for percentages
   directly and got Year 2/3 as cumulative-from-today figures, which the
   dashboard compounded a second time (ETH: a correct ~1,400% three-year
   total rendered as +77,248%).

4. Bases are pinned or checked, because a wrong starting value yields a
   wrong-but-plausible result that no magnitude guardrail would catch:
     - Crypto: the basis is fetched live from CoinGecko and pinned.
     - Commodities: a second call with no shared context re-checks the basis;
       a mismatch beyond BASIS_MISMATCH_TOLERANCE pins the verified value and
       re-runs the batch.
   Pinned values are enforced in code after the response, not merely
   requested in the prompt.

5. One code path. Crypto is not special-cased — it is simply a batch whose
   bases are pinned up front, which is the same mechanism a commodity retry
   uses.

6. Batched by category to control cost. Related assets share one call's
   search budget and prompt overhead instead of paying it per asset.

7. Failures are isolated, not absorbed. A failed batch is retried one asset
   at a time, so the extra cost of isolation is paid only where something
   actually broke. Anything still failing keeps last month's values, is
   reported, and is recorded in data["staleAssetIds"].

8. Partial runs. --repair-stale re-attempts exactly the assets a previous run
   left stale (and --only takes explicit ids). A partial run merges into the
   existing cycle: it keeps that cycle's date, adds to its cost, preserves the
   sources of untouched assets, and replaces rather than appends its history
   entry — so month-over-month arrows stay anchored to the previous month
   rather than to a run from minutes earlier.
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import anthropic

DATA_PATH = Path(__file__).parent / "data.json"
HISTORY_PATH = Path(__file__).parent / "history.json"
MAX_HISTORY_MONTHS = 12

# Assets per research call. Larger batches amortize prompt/tool overhead but
# give each asset a smaller share of attention and search budget.
BATCH_SIZE = 4
SEARCHES_PER_ASSET = 2
VERIFY_SEARCHES_PER_ASSET = 1

# Categories that get a second, independent basis check. Commodities are the
# most exposed to a wrong single spot price; broad baskets and rate-quoted
# assets are less so, and verifying everything was the largest cost driver.
VERIFY_CATEGORIES = {"Commodity"}
BASIS_MISMATCH_TOLERANCE = 0.20

# A search-heavy turn can come back as stop_reason="pause_turn" (resume it) or
# simply end without answering (retry it). Without both, one such turn used to
# discard a whole batch.
MAX_PAUSE_CONTINUATIONS = 4
REQUEST_ATTEMPTS = 2

# Pricing per token, from https://platform.claude.com/docs/en/about-claude/pricing
# These track PRICING_MODEL_FAMILY; main() warns if a different model is chosen.
PRICING_MODEL_FAMILY = "claude-haiku-4-5"
PRICE_PER_INPUT_TOKEN = 1.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 5.00 / 1_000_000
PRICE_PER_CACHE_WRITE_TOKEN = 1.25 / 1_000_000  # 5-minute cache write rate
PRICE_PER_CACHE_READ_TOKEN = 0.10 / 1_000_000
PRICE_PER_SEARCH = 10.00 / 1_000

CRYPTO_PRICE_IDS = {"btc": "bitcoin", "eth": "ethereum"}

BLOCKED_SOURCE_DOMAINS = [
    "longforecast.com",
    "coinpriceforecast.com",
    "walletinvestor.com",
    "gov.capital",
    "pricepredictions.com",
    "digitalcoinprice.com",
    "coincodex.com",
    "30rates.com",
    "traders-union.com",
    "cryptopolitan.com",
]

# An annual interest rate outside this band is almost certainly a unit error
# (a price that slipped into a rate field). RATE_SCALE_RATIO additionally
# catches decimals-for-percent (0.045 meaning 4.5%), which falls inside the
# band: forecast rates must stay on the same scale as the current rate.
RATE_PERCENT_BOUNDS = (-10.0, 30.0)
RATE_SCALE_RATIO = 5.0

SOURCE_HINTS = {
    "cad-div": "Goldman Sachs, JPMorgan, RBC, BofA, Morgan Stanley TSX dividend stock targets",
    "us-div": "Goldman Sachs, JPMorgan, RBC, BofA, Morgan Stanley S&P 500 dividend stock targets",
    "gold": "World Gold Council, LBMA, JPMorgan, Goldman Sachs gold price forecasts",
    "btc": "Bitwise, Standard Chartered, JPMorgan Bitcoin price targets",
    "eth": "Bitwise, Standard Chartered Ethereum price targets",
    "cad-reit": "RBC Capital Markets Canadian REIT sector outlook",
    "cad-re": "CREA (Canadian Real Estate Association) forecasts, Bank of Canada rate path",
    "us-re": "CBRE US commercial real estate outlook",
    "us-tech": "Goldman Sachs, Morgan Stanley S&P 500 / tech sector targets",
    "hisa": "Bank of Canada policy rate, RBC/Scotiabank GIC and HISA rate tables",
    "intl-div": "MSCI EAFE outlook, Goldman Sachs/JPMorgan international equity strategy",
    "em": "MSCI Emerging Markets outlook, Goldman Sachs/JPMorgan/Morgan Stanley EM strategy",
    "silver": "World Gold Council, JPMorgan, Goldman Sachs silver price forecasts",
    "palladium": "LBMA, BofA, TD Securities palladium price forecasts",
    "oil": "Goldman Sachs, JPMorgan, EIA WTI/Brent crude oil forecasts",
    "natgas": "EIA, JPMorgan Henry Hub natural gas forecasts",
    "uranium": "Sprott, IAEA uranium market outlook",
    "copper": "Goldman Sachs, TD Securities, Wood Mackenzie copper forecasts",
    "lithium": "Goldman Sachs, Wood Mackenzie lithium price forecasts",
    "wheat": "USDA, World Bank wheat price outlook",
    "potash": "USDA, World Bank, Procurement Resource potash/fertilizer outlook",
    "lumber": "ERA Forecast, Fastmarkets lumber price outlook",
}


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

PROJECTION_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "The asset's id, exactly as given in the prompt"},
        "basisValue": {
            "type": "number",
            "description": "The CURRENT value today (price, index level, or rate) that the targets below are measured against",
        },
        "basisDescription": {
            "type": "string",
            "description": "Short phrase naming basisValue and its unit, e.g. 'spot gold price per oz in USD' or 'BoC overnight policy rate, percent'",
        },
        "basisKind": {
            "type": "string",
            "enum": ["price_level", "rate_percent"],
            "description": (
                "'price_level' when basisValue is a price or index level that can appreciate "
                "(stocks, commodities, crypto, REITs, bond ETF prices). 'rate_percent' when "
                "basisValue is itself an interest rate or yield in percent (savings accounts, "
                "GIC rates, policy rates) — for those the rate IS the annual return and there "
                "is no capital appreciation."
            ),
        },
        "targets": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
            "description": (
                "The projected ABSOLUTE value at the END of year 1, year 2 and year 3, in the "
                "SAME UNITS as basisValue — never percentages of change. For 'price_level' these "
                "are forecast price levels; for 'rate_percent' these are forecast rates in "
                "percent. Each entry is a point-in-time value, not a change and not a running "
                "total. Example (price_level): an asset at 100 today expected to reach 110, then "
                "121, then 133 -> [110, 121, 133]."
            ),
        },
        "incomeYieldPct": {
            "type": "number",
            "description": (
                "Recurring annual income yield in percent (dividends, coupons, distributions, "
                "staking), e.g. 4.5. Use 0 if the asset pays no income, and 0 when basisKind is "
                "'rate_percent' since the rate already represents that income."
            ),
        },
        "why": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
            "description": "One rationale per year, under 240 characters, naming the actual source/analyst and date found and stating that year's target value",
        },
    },
    "required": ["id", "basisValue", "basisDescription", "basisKind", "targets", "incomeYieldPct", "why"],
}

SUBMIT_TOOL = {
    "name": "submit_projections",
    "description": "Submit researched 3-year forward outlooks for ALL asset classes listed in this request. Report values read from sources; do NOT compute percentage returns.",
    "input_schema": {
        "type": "object",
        "properties": {
            "projections": {
                "type": "array",
                "description": "One entry per asset class in the prompt, using the exact id given for each.",
                "items": PROJECTION_ITEM,
            }
        },
        "required": ["projections"],
    },
}

VERIFY_TOOL = {
    "name": "submit_verifications",
    "description": "Report independently found current values for each data-point claim listed in this request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The asset id this verification is for, exactly as given"},
                        "verifiedValue": {
                            "type": "number",
                            "description": "The current value you independently found, in the same units as the claim",
                        },
                        "note": {"type": "string", "description": "Brief note (under 200 characters) on what you found and where"},
                    },
                    "required": ["id", "verifiedValue", "note"],
                },
            }
        },
        "required": ["verifications"],
    },
}


def web_search_tool(max_uses):
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max_uses,
        "blocked_domains": BLOCKED_SOURCE_DOMAINS,
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class CostTracker:
    """Accumulates the real metered cost of every API call in a run."""

    def __init__(self):
        self.total = 0.0

    def add(self, usage):
        cost = usage.input_tokens * PRICE_PER_INPUT_TOKEN
        cost += usage.output_tokens * PRICE_PER_OUTPUT_TOKEN
        cost += (usage.cache_creation_input_tokens or 0) * PRICE_PER_CACHE_WRITE_TOKEN
        cost += (usage.cache_read_input_tokens or 0) * PRICE_PER_CACHE_READ_TOKEN
        if usage.server_tool_use:
            cost += usage.server_tool_use.web_search_requests * PRICE_PER_SEARCH
        self.total += cost
        return cost


def chunk(items, size):
    return [items[i : i + size] for i in range(0, len(items), size)]


def avg_return(rates):
    return sum(rates) / len(rates)


def compute_returns(basis_value, targets, income_yield_pct, label="", basis_kind="price_level"):
    """Derive year-over-year percentage returns from absolute target values.

    Computing this here rather than asking the model for percentages is what
    keeps cumulative-vs-annual confusion out of the dashboard.

    price_level : targets are prices/index levels; each year's return is the
                  change against the previous year's level plus income yield.
    rate_percent: targets are themselves rates in percent, so the rate IS that
                  year's return. A HISA going 4.0% -> 4.5% earns 4.5%, not a
                  12.5% "capital gain" on the rate. The same mistake also
                  inverts the sign for bonds, where rising yields cut prices.
    """
    if basis_value is None or not targets or len(targets) != 3:
        raise ValueError(f"{label}: need basisValue and exactly 3 targets, got basis={basis_value} targets={targets}")

    if basis_kind == "rate_percent":
        lo, hi = RATE_PERCENT_BOUNDS
        if not all(lo <= t <= hi for t in targets):
            raise ValueError(f"{label}: rate_percent targets outside {RATE_PERCENT_BOUNDS}, likely a unit error: {targets}")
        # An absolute band alone misses decimals-for-percent (0.045 meaning
        # 4.5%), which sits inside it. Targets must also share the basis's
        # scale — a policy rate does not move 5x in a year.
        if abs(basis_value) > 1e-9:
            ratios = [abs(t / basis_value) for t in targets if abs(t) > 1e-9]
            if ratios and (max(ratios) > RATE_SCALE_RATIO or min(ratios) < 1 / RATE_SCALE_RATIO):
                raise ValueError(
                    f"{label}: rate_percent targets {targets} are not on the same scale as basis "
                    f"{basis_value}; likely percent-vs-decimal mismatch"
                )
        # Income yield is ignored deliberately: the rate already is the income.
        return [round(float(t), 1) for t in targets]

    if basis_value <= 0 or any(t <= 0 for t in targets):
        raise ValueError(f"{label}: price levels must be positive, got basis={basis_value} targets={targets}")

    income = income_yield_pct or 0.0
    levels = [basis_value] + list(targets)
    return [round((levels[i + 1] / levels[i] - 1) * 100 + income, 1) for i in range(3)]


def compute_ranks(assets):
    """Rank assets 1..N by 3-yr average return, best first."""
    ranked = sorted(range(len(assets)), key=lambda i: -avg_return(assets[i]["r"]))
    return {assets[idx]["id"]: rank for rank, idx in enumerate(ranked, start=1)}


def position_change(prev_rank, new_rank):
    if prev_rank is None or prev_rank == new_rank:
        return "same"
    return "up" if new_rank < prev_rank else "down"


def extract_search_sources(content_blocks):
    sources, seen = [], set()
    for b in content_blocks:
        if b.type == "web_search_tool_result" and isinstance(b.content, list):
            for result in b.content:
                if result.url not in seen:
                    seen.add(result.url)
                    sources.append({"title": result.title, "url": result.url})
    return sources


def tool_input(response, tool_name):
    """Return the input of the named tool call, or None if absent."""
    for b in response.content:
        if b.type == "tool_use" and b.name == tool_name:
            return b.input
    return None


def request_tool_call(client, model_id, prompt, tools, tool_name, max_tokens, costs):
    """Run one research/verification request and return (tool_input, sources).

    A single request is not enough on its own. A turn that runs several
    searches can come back as stop_reason="pause_turn", which means "not
    finished, send this back to continue" — and a turn can also simply end
    without the model calling the tool. Either way the batch used to be lost.
    So: continue paused turns, and retry the whole request once if the model
    ends without answering.
    """
    last_stop = None
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        messages = [{"role": "user", "content": prompt}]
        sources = []
        for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
            response = client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                tools=tools,
                # "any" forces a tool call each turn — search again or submit —
                # so the model cannot answer with prose instead.
                tool_choice={"type": "any", "disable_parallel_tool_use": True},
                messages=messages,
            )
            costs.add(response.usage)
            sources += extract_search_sources(response.content)

            payload = tool_input(response, tool_name)
            if payload is not None:
                return payload, sources

            last_stop = response.stop_reason
            if last_stop != "pause_turn":
                break
            # Paused mid-search: hand the turn back verbatim to resume it.
            messages = messages + [{"role": "assistant", "content": response.content}]

        print(f"  Attempt {attempt}/{REQUEST_ATTEMPTS}: ended without calling {tool_name} (stop_reason={last_stop})")

    raise ValueError(f"no {tool_name} call after {REQUEST_ATTEMPTS} attempts (last stop_reason={last_stop})")


def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def write_json(path, payload):
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def fetch_live_crypto_price(coingecko_id):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
    req = urllib.request.Request(url, headers={"User-Agent": "asset-classes-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())[coingecko_id]["usd"]


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def research_assets(client, model_id, assets, today, costs, pinned_bases=None):
    """Research a batch of assets in one call and return {id: projection}.

    pinned_bases maps asset id -> {"value": float, "note": str} for bases we
    already trust (a live crypto price, or a value confirmed by verification).
    Those are stated in the prompt AND overwritten on the response, so the
    result does not depend on the model choosing to comply.
    """
    pinned_bases = pinned_bases or {}

    blocks = []
    for a in assets:
        block = (
            f"- id: {a['id']}\n"
            f"  Name: {a['name']}\n"
            f"  Category: {a['cat']}\n"
            f"  Look for sources like: {SOURCE_HINTS.get(a['id'], '')}"
        )
        if a["id"] in pinned_bases:
            block += f"\n  VERIFIED CURRENT VALUE (use as basisValue): {pinned_bases[a['id']]['note']}"
        blocks.append(block)

    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current market conditions or analyst forecasts from memory alone.

Use the web_search tool to find REAL, CURRENT analyst projections for EACH of the following {len(assets)} asset classes. You share one search budget across all of them, so search efficiently.

{chr(10).join(blocks)}

Find the latest published price targets, index levels or rate outlooks. Where figures are not published for all three years, extrapolate the later ones from the trend implied by what you find and say so in that asset's "why".

Report ONLY values you can read off a source — do NOT calculate percentage returns, that arithmetic is done downstream. For each asset give:
- basisValue + basisKind: the current value today, and whether it is a price/index level ('price_level') or an interest rate in percent ('rate_percent')
- targets: the projected value at the end of year 1, year 2 and year 3, in the same units as basisValue. Three point-in-time values — NOT percentage changes, NOT cumulative growth.
- incomeYieldPct: annual dividend/coupon/distribution/staking yield, or 0. For income-driven assets the level may barely move and this yield carries the return; that is expected.

Once you have researched all {len(assets)}, call submit_projections with one entry per asset, matching each id exactly."""

    submitted, sources = request_tool_call(
        client, model_id, prompt,
        tools=[web_search_tool(max(2, SEARCHES_PER_ASSET * len(assets))), SUBMIT_TOOL],
        tool_name="submit_projections",
        max_tokens=1200 * len(assets),
        costs=costs,
    )

    by_id = {p["id"]: p for p in submitted["projections"]}
    missing = [a["id"] for a in assets if a["id"] not in by_id]
    if missing:
        raise ValueError(f"response missing ids: {missing}")

    for a in assets:
        p = by_id[a["id"]]
        if a["id"] in pinned_bases:
            p["basisValue"] = pinned_bases[a["id"]]["value"]
        p["r"] = compute_returns(
            p["basisValue"],
            p["targets"],
            p.get("incomeYieldPct", 0.0),
            label=a["id"],
            basis_kind=p.get("basisKind", "price_level"),
        )
        pin = " (pinned)" if a["id"] in pinned_bases else ""
        print(f"  {a['id']}: basis {p['basisValue']:,.2f}{pin} -> {p['targets']} +{p.get('incomeYieldPct', 0.0)}% => {p['r']}")

    return by_id, sources


def verify_bases(client, model_id, claims, today, costs):
    """Re-check each basis in one call that shares no context with the
    research call. Returns {id: {"verifiedValue", "note"}}."""
    blocks = [
        f"- id: {c['id']}\n  Asset: {c['name']} ({c['cat']})\n  Claim to verify: \"{c['basisDescription']}\" was reported as {c['basisValue']}"
        for c in claims
    ]
    prompt = f"""Today is {today}. You are independently fact-checking these market data claims — do not assume any of them are correct.

{chr(10).join(blocks)}

Search the web yourself for each one and find the actual current value. Then call submit_verifications with one entry per id, reporting what you actually find whether or not it matches the claim."""

    try:
        submitted, sources = request_tool_call(
            client, model_id, prompt,
            tools=[web_search_tool(max(1, VERIFY_SEARCHES_PER_ASSET * len(claims))), VERIFY_TOOL],
            tool_name="submit_verifications",
            max_tokens=500 * len(claims),
            costs=costs,
        )
    except ValueError as e:
        # Verification is a safety net, not the payload: if it will not answer,
        # keep the researched bases rather than losing the batch.
        print(f"  Warning: verification unavailable ({e}); keeping researched bases")
        return {}, []
    return {v["id"]: v for v in submitted["verifications"]}, sources


def process_batch(client, model_id, batch, today, costs, pinned_bases=None):
    """Research one batch, then for verified categories re-check the bases and
    re-run once with the verified values pinned. Returns (by_id, sources)."""
    by_id, sources = research_assets(client, model_id, batch, today, costs, pinned_bases)

    if batch[0]["cat"] not in VERIFY_CATEGORIES:
        return by_id, sources

    claims = [
        {
            "id": a["id"],
            "name": a["name"],
            "cat": a["cat"],
            "basisValue": by_id[a["id"]]["basisValue"],
            "basisDescription": by_id[a["id"]]["basisDescription"],
        }
        for a in batch
        # A pinned basis is already ground truth; re-checking it would only
        # invite a worse value.
        if a["id"] not in (pinned_bases or {}) and by_id[a["id"]].get("basisValue") is not None
    ]
    if not claims:
        return by_id, sources

    verified, verify_sources = verify_bases(client, model_id, claims, today, costs)
    sources += verify_sources

    corrections = {}
    for c in claims:
        v = verified.get(c["id"])
        if v is None:
            continue
        rel_diff = abs(v["verifiedValue"] - c["basisValue"]) / max(abs(c["basisValue"]), 1e-9)
        if rel_diff > BASIS_MISMATCH_TOLERANCE:
            print(f"  Basis mismatch for {c['id']}: claimed {c['basisValue']}, independently found {v['verifiedValue']} ({rel_diff:.0%} off)")
            corrections[c["id"]] = {
                "value": v["verifiedValue"],
                "note": f"'{c['basisDescription']}' is approximately {v['verifiedValue']}, not {c['basisValue']} ({v['note']}).",
            }
        else:
            print(f"  Basis confirmed for {c['id']}: {c['basisValue']} ≈ {v['verifiedValue']}")

    if corrections:
        print(f"  Re-running batch with verified bases pinned for: {list(corrections)}")
        by_id, retry_sources = research_assets(
            client, model_id, batch, today, costs, {**(pinned_bases or {}), **corrections}
        )
        sources += retry_sources

    return by_id, sources


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def live_crypto_bases(assets):
    """Pin crypto bases to a live price feed, so the most volatile assets never
    depend on the model recalling a spot price correctly."""
    pinned = {}
    for a in assets:
        coingecko_id = CRYPTO_PRICE_IDS.get(a["id"])
        if not coingecko_id:
            continue
        try:
            price = fetch_live_crypto_price(coingecko_id)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
            print(f"  Warning: live price fetch failed for {a['name']} ({e}); falling back to a searched basis")
            continue
        pinned[a["id"]] = {
            "value": price,
            "note": f"{a['name']} is ${price:,.2f} USD right now, fetched live from CoinGecko.",
        }
        print(f"  Live price for {a['name']}: ${price:,.2f}")
    return pinned


def plan_batches(assets):
    """Group assets into batches: crypto together (live-pinned bases), then
    each remaining category chunked to BATCH_SIZE."""
    crypto = [a for a in assets if a["id"] in CRYPTO_PRICE_IDS]

    by_category = {}
    for a in assets:
        if a["id"] in CRYPTO_PRICE_IDS:
            continue
        by_category.setdefault(a["cat"], []).append(a)

    batches = [(cat, b) for cat, group in by_category.items() for b in chunk(group, BATCH_SIZE)]
    if crypto:
        batches.append(("Crypto", crypto))
    return batches


def select_model(client):
    models = [m.id for m in client.models.list().data]
    preferred = [m for m in models if m.startswith(PRICING_MODEL_FAMILY)]
    if preferred:
        return preferred[0]
    fallback = next((m for m in models if "haiku" in m), None)
    if fallback is None:
        raise RuntimeError(f"no Haiku model available; saw: {models}")
    print(f"Warning: {PRICING_MODEL_FAMILY} unavailable, using {fallback}. Cost figures assume {PRICING_MODEL_FAMILY} pricing and may be wrong.")
    return fallback


BATCH_ERRORS = (ValueError, KeyError, anthropic.APIError)


def refresh_assets(client, model_id, assets, today, costs):
    """Research every batch, isolating any batch that fails.

    A failed batch is retried one asset at a time before being given up on.
    Isolation costs more per asset, so it is paid only where something actually
    broke rather than as a standing premium on every run — a batch-of-1 policy
    for all 24 assets would cost more every month than the occasional wasted
    batch it would save.

    Returns (projections, source_groups, stale_ids).
    """
    projections, source_groups, stale_ids = {}, [], []

    for category, batch in plan_batches(assets):
        ids = [a["id"] for a in batch]
        print(f"Researching batch ({category}): {ids}...")
        pinned = live_crypto_bases(batch) if category == "Crypto" else None

        try:
            by_id, sources = process_batch(client, model_id, batch, today, costs, pinned)
        except BATCH_ERRORS as e:
            print(f"  FAILED ({type(e).__name__}: {e})")
            by_id, sources = {}, []
            if len(batch) == 1:
                stale_ids.extend(ids)
            else:
                print(f"  Isolating {ids} and retrying one at a time...")
                for a in batch:
                    solo_pin = {a["id"]: pinned[a["id"]]} if pinned and a["id"] in pinned else None
                    try:
                        one, one_sources = process_batch(client, model_id, [a], today, costs, solo_pin)
                    except BATCH_ERRORS as solo_error:
                        print(f"    {a['id']}: still failing ({type(solo_error).__name__}) — keeping previous values")
                        stale_ids.append(a["id"])
                        continue
                    by_id.update(one)
                    sources += one_sources

        if by_id:
            projections.update(by_id)
            source_groups.append(([i for i in ids if i in by_id], category, sources))

    return projections, source_groups, stale_ids


def apply_history(updated_assets, data_date):
    """Set posChange from the previous *distinct* run date and return the
    history to write.

    Re-running on a day that already has an entry replaces it instead of
    appending. Otherwise repeated same-day runs compare each asset against a
    run from minutes earlier — which silently made the arrows meaningless —
    and evict real months from the 12-month window.
    """
    history = load_json(HISTORY_PATH, {"history": []})
    entries = history["history"]

    replacing = bool(entries) and entries[-1]["date"] == data_date
    baseline = entries[:-1] if replacing else entries
    prev_ranks = baseline[-1]["ranks"] if baseline else {}

    new_ranks = compute_ranks(updated_assets)
    for asset in updated_assets:
        asset["posChange"] = position_change(prev_ranks.get(asset["id"]), new_ranks[asset["id"]])

    history["history"] = (baseline + [{"date": data_date, "ranks": new_ranks}])[-MAX_HISTORY_MONTHS:]
    return history


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh Asset-Classes projections.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--repair-stale", action="store_true",
                       help="refresh only the assets the last run left stale")
    scope.add_argument("--only", metavar="IDS",
                       help="comma-separated asset ids to refresh")
    return parser.parse_args()


def resolve_targets(args, assets, data):
    """Return (targets, partial). A partial run touches only some assets and so
    must merge with, rather than replace, the existing file."""
    known = {a["id"] for a in assets}

    if args.repair_stale:
        wanted = set(data.get("staleAssetIds") or [])
        if not wanted:
            return [], True
    elif args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - known
        if unknown:
            raise SystemExit(f"unknown asset ids: {sorted(unknown)}")
    else:
        return assets, False

    return [a for a in assets if a["id"] in wanted], True


def main():
    args = parse_args()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    data = load_json(DATA_PATH, {"assets": []})
    costs = CostTracker()

    targets, partial = resolve_targets(args, data["assets"], data)
    if partial and not targets:
        print("Nothing to repair: no stale assets recorded.")
        return

    # A partial run patches assets inside the existing cycle, so it keeps that
    # cycle's date and adds to its cost rather than restating either.
    data_date = data.get("updated") if partial else date.today().isoformat()
    print(f"{'Repairing' if partial else 'Refreshing'} {len(targets)} of {len(data['assets'])} assets (date {data_date})")

    model_id = select_model(client)
    print(f"Using model: {model_id}")

    projections, source_groups, stale_ids = refresh_assets(client, model_id, targets, data_date, costs)
    if not projections:
        raise RuntimeError("nothing was refreshed; leaving data.json untouched")

    refreshed = set(projections)
    updated_assets = []
    for asset in data["assets"]:
        updated = {k: v for k, v in asset.items() if k != "d"}  # "d" is a dead field
        fresh = projections.get(asset["id"])
        if fresh:
            updated["r"] = fresh["r"]
            updated["why"] = fresh["why"]
        updated_assets.append(updated)

    # Keep sources for assets this run did not touch; drop the ones it replaced.
    kept = [s for s in data.get("sources", [])
            if not (set(str(s.get("assetId", "")).split("+")) & refreshed)] if partial else []
    seen_urls = {s["url"] for s in kept}
    all_sources = list(kept)
    # A batch shares one search budget, so a source cannot be pinned to a single
    # asset within it. Keep the exact ids in the data, but label the UI by
    # category — joining four asset names truncated the source title away.
    for ids, category, sources in source_groups:
        for s in sources:
            if s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                all_sources.append({**s, "assetId": "+".join(ids), "assetName": category})

    still_stale = sorted((set(data.get("staleAssetIds") or []) | set(stale_ids)) - refreshed) if partial else stale_ids
    total_cost = costs.total + (data.get("lastRunCostUsd", 0.0) if partial else 0.0)

    history = apply_history(updated_assets, data_date)
    data.update({
        "assets": updated_assets,
        "updated": data_date,
        "sources": all_sources,
        "lastRunCostUsd": round(total_cost, 2),
        "staleAssetIds": still_stale,
    })
    write_json(DATA_PATH, data)
    write_json(HISTORY_PATH, history)

    summary = (f"data.json updated — {len(refreshed)} of {len(updated_assets)} assets refreshed, "
               f"{len(all_sources)} sources, cost ${costs.total:.4f}"
               f"{f' (cycle total ${total_cost:.2f})' if partial else ''}, date: {data_date}")
    if still_stale:
        summary += f" | STALE (kept previous values): {still_stale}"
    print(summary)


if __name__ == "__main__":
    main()
