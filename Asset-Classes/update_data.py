#!/usr/bin/env python3
"""
Monthly script to refresh Asset-Classes/data.json using the Claude API.
Called by GitHub Actions on the 1st of each month.
Requires: ANTHROPIC_API_KEY environment variable

Each asset is researched individually with the web_search tool enabled, so
projections are grounded in real, current search results rather than the
model's training data alone. The projection itself is returned via a forced
tool call (not parsed from free text) so an uncertain model can't skip the
structured answer in favor of a prose caveat.

Every projection rests on a "basis" — the current price/rate/level the model
used as its Year 1 starting point. A wrong basis (e.g. a stale or misread
price) silently produces a wrong-but-plausible-looking projection that a
simple magnitude guardrail wouldn't catch. Two independent defenses:
  - Crypto (btc/eth): the basis is fetched directly from a live price API
    (CoinGecko) and handed to the model as ground truth, removing the
    guesswork entirely.
  - Everything else: a second, separate API call with no shared context
    independently re-searches and fact-checks the specific basis the first
    call claimed. A meaningful disagreement triggers one corrective retry
    with the verified figure injected as ground truth.

The real pages found during research are collected into data["sources"] as
an appendix for the UI, and the run's exact metered cost (from every
response's usage object, including verification/retry calls) is stored in
data["lastRunCostUsd"].
"""
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
SEARCHES_PER_ASSET = 4
VERIFY_SEARCHES = 2
BASIS_MISMATCH_TOLERANCE = 0.20  # >20% relative difference triggers a corrective retry

# Claude Haiku 4.5 pricing (USD per token), from https://platform.claude.com/docs/en/about-claude/pricing
# NOTE: model_id is auto-selected as "latest Haiku" below — if a future Haiku
# version changes pricing, update these rates to match.
PRICE_PER_INPUT_TOKEN = 1.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 5.00 / 1_000_000
PRICE_PER_CACHE_WRITE_TOKEN = 1.25 / 1_000_000  # 5-minute cache write rate
PRICE_PER_CACHE_READ_TOKEN = 0.10 / 1_000_000
PRICE_PER_SEARCH = 10.00 / 1_000

# Assets with a real, free, live price API — used as ground truth instead of
# trusting the model to find and remember a price via search.
CRYPTO_PRICE_IDS = {"btc": "bitcoin", "eth": "ethereum"}

# Forces structured output instead of relying on the model to follow a
# "return only JSON" text instruction — which it may ignore in favor of
# hedging in prose when the data it found is incomplete.
SUBMIT_TOOL = {
    "name": "submit_projection",
    "description": "Submit the researched 3-year forward return projection for this asset class, based on real web search results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "r": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Year 1, Year 2, Year 3 projected annual return percentages, e.g. 8.0 for +8.0%",
            },
            "why": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
                "description": "One rationale per year (under 240 characters), naming the actual source/analyst and date found",
            },
            "basisValue": {
                "type": "number",
                "description": "The single current market figure (price, yield, or rate) you used as the starting reference point for your Year 1 calculation",
            },
            "basisDescription": {
                "type": "string",
                "description": "One short phrase describing exactly what basisValue represents and its unit, e.g. 'spot gold price per oz in USD' or 'BoC overnight policy rate, percent'",
            },
        },
        "required": ["r", "why", "basisValue", "basisDescription"],
    },
}

SUBMIT_VERIFICATION_TOOL = {
    "name": "submit_verified_value",
    "description": "Report the current value you independently found for this specific data point.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verifiedValue": {
                "type": "number",
                "description": "The current numeric value you found via independent search, in the same units as the claim being checked",
            },
            "note": {
                "type": "string",
                "description": "Brief note (under 200 characters) on what you found and where",
            },
        },
        "required": ["verifiedValue", "note"],
    },
}

# Search hints per asset, steering the model toward real, checkable sources.
SOURCE_HINTS = {
    "cad-div": "Goldman Sachs, JPMorgan, RBC, BofA, Morgan Stanley TSX dividend stock targets",
    "us-div": "Goldman Sachs, JPMorgan, RBC, BofA, Morgan Stanley S&P 500 dividend stock targets",
    "gold": "World Gold Council, LBMA, JPMorgan, Goldman Sachs gold price forecasts",
    "btc": "Bitwise, Standard Chartered, JPMorgan Bitcoin price targets",
    "eth": "Bitwise, Standard Chartered Ethereum price targets",
    "cad-reit": "RBC Capital Markets Canadian REIT sector outlook",
    "cad-re": "CREA (Canadian Real Estate Association) forecasts, Bank of Canada rate path",
    "us-re": "CBRE US commercial real estate outlook",
    "cad-bond": "Bank of Canada rate path, RBC bond market outlook",
    "cad-hy": "RBC high-yield credit research, Canadian corporate bond outlook",
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


def avg_return(rates):
    return sum(rates) / len(rates)


def compute_ranks(assets):
    """Rank assets 1..N by 3-yr avg return, best (highest) first."""
    ranked = sorted(range(len(assets)), key=lambda i: -avg_return(assets[i]["r"]))
    return {assets[idx]["id"]: rank for rank, idx in enumerate(ranked, start=1)}


def load_history():
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return {"history": []}


def usage_cost(usage):
    """Convert an Anthropic API response's usage object into a USD cost."""
    cost = usage.input_tokens * PRICE_PER_INPUT_TOKEN
    cost += usage.output_tokens * PRICE_PER_OUTPUT_TOKEN
    cost += (usage.cache_creation_input_tokens or 0) * PRICE_PER_CACHE_WRITE_TOKEN
    cost += (usage.cache_read_input_tokens or 0) * PRICE_PER_CACHE_READ_TOKEN
    if usage.server_tool_use:
        cost += usage.server_tool_use.web_search_requests * PRICE_PER_SEARCH
    return cost


def extract_search_sources(content_blocks):
    sources = []
    seen_urls = set()
    for b in content_blocks:
        if b.type == "web_search_tool_result" and isinstance(b.content, list):
            for result in b.content:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    sources.append({"title": result.title, "url": result.url})
    return sources


def fetch_live_crypto_price(coingecko_id):
    """Ground truth price for crypto assets — no LLM guesswork involved."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
    req = urllib.request.Request(url, headers={"User-Agent": "asset-classes-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode())
    return payload[coingecko_id]["usd"]


def research_asset(client, model_id, asset, today, correction=None):
    """Search the web for one asset's current analyst consensus and return
    (r, why, basis_value, basis_description, sources, cost_usd).

    `correction`, if given, is injected as a hard instruction overriding
    whatever current-price/rate assumption the model would otherwise use —
    either a live-fetched crypto price or a fact-check result from
    verify_basis()."""
    hint = SOURCE_HINTS.get(asset["id"], "")
    correction_block = ""
    if correction:
        correction_block = f"\n\nIMPORTANT — VERIFIED CURRENT DATA: {correction} You MUST use this as your Year 1 starting basisValue rather than any other figure you find or recall.\n"

    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current market conditions or analyst forecasts from memory alone.

Use the web_search tool to find REAL, CURRENT analyst consensus 3-year forward return projections for this asset class:

Name: {asset['name']}
Category: {asset['cat']}
Look for sources like: {hint}
{correction_block}
Current (soon to be replaced) projections for reference — update them based on what you actually find:
Year 1: {asset['r'][0]}%, Year 2: {asset['r'][1]}%, Year 3: {asset['r'][2]}%

Search for the latest available price targets, rate outlooks, or return forecasts. If exact 3-year figures aren't published, reasonably derive Year 2/Year 3 from the trend implied by what you find (e.g. a 12-month price target plus a stated longer-run view) — do not withhold a projection just because the exact figure isn't published verbatim; give your best grounded estimate and explain the derivation in "why".

Once you've searched enough to form a view, call submit_projection with your answer, including the specific current-market basisValue and basisDescription you used as your Year 1 starting point."""

    response = client.messages.create(
        model=model_id,
        max_tokens=3000,
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCHES_PER_ASSET},
            SUBMIT_TOOL,
        ],
        # "any" forces a tool call every turn (search again, or submit) instead of
        # letting the model end the turn with plain prose explaining uncertainty.
        tool_choice={"type": "any", "disable_parallel_tool_use": True},
        messages=[{"role": "user", "content": prompt}],
    )

    submission = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_projection"),
        None,
    )
    if submission is None:
        raise ValueError(
            f"Model never called submit_projection for {asset['id']} (stop_reason={response.stop_reason})"
        )

    return (
        submission.input["r"],
        submission.input["why"],
        submission.input.get("basisValue"),
        submission.input.get("basisDescription", ""),
        extract_search_sources(response.content),
        usage_cost(response.usage),
    )


def verify_basis(client, model_id, asset, basis_value, basis_description, today):
    """Independently re-check a specific numeric claim via a fresh, separate
    web search with no shared context — a second confirming source, not a
    repeat of the first call's own reasoning. Returns
    (verified_value_or_None, note, sources, cost_usd)."""
    prompt = f"""Today is {today}. You are independently fact-checking a specific market data claim — do not assume it is correct.

Asset: {asset['name']} ({asset['cat']})
Claim to verify: "{basis_description}" was reported as {basis_value}

Search the web yourself and find the actual current value for this specific data point. Then call submit_verified_value with what you actually find, regardless of whether it matches the claim."""

    response = client.messages.create(
        model=model_id,
        max_tokens=1500,
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": VERIFY_SEARCHES},
            SUBMIT_VERIFICATION_TOOL,
        ],
        tool_choice={"type": "any", "disable_parallel_tool_use": True},
        messages=[{"role": "user", "content": prompt}],
    )

    submission = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_verified_value"),
        None,
    )
    if submission is None:
        return None, "verification call returned no value", [], usage_cost(response.usage)

    return (
        submission.input["verifiedValue"],
        submission.input["note"],
        extract_search_sources(response.content),
        usage_cost(response.usage),
    )


def research_asset_verified(client, model_id, asset, today, cost_tracker):
    """research_asset() plus the basis-verification defense described in the
    module docstring. Mutates cost_tracker[0] with every call's real cost."""
    live_price_note = None
    if asset["id"] in CRYPTO_PRICE_IDS:
        try:
            price = fetch_live_crypto_price(CRYPTO_PRICE_IDS[asset["id"]])
            live_price_note = f"The current price of {asset['name']} is ${price:,.2f} USD, fetched live from CoinGecko moments ago."
            print(f"  Live price for {asset['name']}: ${price:,.2f}")
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
            print(f"  Warning: live price fetch failed for {asset['name']} ({e}); falling back to search-based basis")

    r, why, basis_value, basis_desc, sources, cost = research_asset(
        client, model_id, asset, today, correction=live_price_note
    )
    cost_tracker[0] += cost

    # Crypto already has a verified ground-truth basis; everything else gets
    # an independent second-source check.
    if asset["id"] not in CRYPTO_PRICE_IDS and basis_value:
        verified_value, note, verify_sources, verify_cost = verify_basis(
            client, model_id, asset, basis_value, basis_desc, today
        )
        cost_tracker[0] += verify_cost
        sources = sources + verify_sources

        if verified_value is not None:
            rel_diff = abs(verified_value - basis_value) / max(abs(basis_value), 1e-9)
            if rel_diff > BASIS_MISMATCH_TOLERANCE:
                print(
                    f"  Basis mismatch for {asset['name']}: claimed {basis_value}, "
                    f"independently found {verified_value} ({rel_diff:.0%} off) — retrying with correction"
                )
                correction = (
                    f"An independent fact-check found that '{basis_desc}' is actually approximately "
                    f"{verified_value}, not {basis_value} as first assumed ({note})."
                )
                r, why, basis_value, basis_desc, retry_sources, retry_cost = research_asset(
                    client, model_id, asset, today, correction=correction
                )
                cost_tracker[0] += retry_cost
                sources = sources + retry_sources
            else:
                print(f"  Basis confirmed for {asset['name']}: {basis_value} ≈ {verified_value}")

    return r, why, sources


def main():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    with open(DATA_PATH) as f:
        data = json.load(f)

    today = date.today().isoformat()

    # Auto-select latest Haiku model so no code change needed when versions update
    models = client.models.list()
    model_id = next(m.id for m in models.data if "haiku" in m.id)
    print(f"Using model: {model_id}")

    updated_assets = []
    all_sources = []
    seen_source_urls = set()
    cost_tracker = [0.0]  # mutable box so research_asset_verified can accumulate into it

    for asset in data["assets"]:
        print(f"Researching {asset['name']}...")
        r, why, sources = research_asset_verified(client, model_id, asset, today, cost_tracker)

        updated = dict(asset)
        updated["r"] = r
        updated["d"] = r
        updated["why"] = why
        updated_assets.append(updated)

        for s in sources:
            if s["url"] not in seen_source_urls:
                seen_source_urls.add(s["url"])
                all_sources.append({**s, "assetId": updated["id"], "assetName": updated["name"]})

    if len(updated_assets) != len(data["assets"]):
        raise ValueError(
            f"Asset count mismatch: expected {len(data['assets'])}, got {len(updated_assets)}"
        )

    # Rank by 3-yr avg return and compare to last month's ranks to flag
    # each asset's position change for the up/down/no-change arrow in the UI.
    new_ranks = compute_ranks(updated_assets)
    history = load_history()
    prev_ranks = history["history"][-1]["ranks"] if history["history"] else {}

    for asset in updated_assets:
        prev_rank = prev_ranks.get(asset["id"])
        new_rank = new_ranks[asset["id"]]
        if prev_rank is None or prev_rank == new_rank:
            asset["posChange"] = "same"
        elif new_rank < prev_rank:
            asset["posChange"] = "up"
        else:
            asset["posChange"] = "down"

    total_cost_usd = cost_tracker[0]

    data["assets"] = updated_assets
    data["updated"] = today
    data["sources"] = all_sources
    data["lastRunCostUsd"] = round(total_cost_usd, 2)

    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    history["history"].append({"date": today, "ranks": new_ranks})
    history["history"] = history["history"][-MAX_HISTORY_MONTHS:]

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(
        f"data.json updated — {len(updated_assets)} assets, {len(all_sources)} sources, "
        f"cost ${total_cost_usd:.4f}, date: {today}"
    )


if __name__ == "__main__":
    main()
