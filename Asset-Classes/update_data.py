#!/usr/bin/env python3
"""
Monthly script to refresh Asset-Classes/data.json using the Claude API.
Called by GitHub Actions on the 1st of each month.
Requires: ANTHROPIC_API_KEY environment variable

Each asset is researched with the web_search tool enabled, so projections
are grounded in real, current search results rather than the model's
training data alone. The projection itself is returned via a forced tool
call (not parsed from free text) so an uncertain model can't skip the
structured answer in favor of a prose caveat.

Every projection rests on a "basis" — the current price/rate/level the model
used as its Year 1 starting point. A wrong basis (e.g. a stale or misread
price) silently produces a wrong-but-plausible-looking projection that a
simple magnitude guardrail wouldn't catch. Two defenses:
  - Crypto (btc/eth): the basis is fetched directly from a live price API
    (CoinGecko) and handed to the model as ground truth, removing the
    guesswork entirely. Researched individually (only 2 assets, already cheap).
  - Commodities (gold, oil, copper, etc.) — the category most prone to a
    wrong spot-price basis, which is exactly how this bug first surfaced —
    get a second, separate API call with no shared context that
    independently re-searches and fact-checks the basis the first call
    claimed. A meaningful disagreement triggers one corrective retry with
    the verified figure injected as ground truth.
  - Every other category (equities, real estate, bonds, cash) is researched
    but not independently re-verified: these are basket/rate-based rather
    than single-spot-price assets, where this specific failure mode is less
    likely, and double-checking all 24 assets individually was the single
    biggest driver of API cost for comparatively little accuracy benefit.

To keep cost down, non-crypto assets are researched (and, for commodities,
verified) in small batches grouped by category rather than one call per
asset — this amortizes the fixed per-call tool/system-prompt overhead and
lets a shared, smaller search budget cover several related assets at once,
instead of paying that overhead 22+ times over.

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
BASIS_MISMATCH_TOLERANCE = 0.20  # >20% relative difference triggers a corrective retry

# Batching knobs for non-crypto assets. A batch shares one search budget and
# one tool/system-prompt overhead across BATCH_SIZE related assets instead of
# paying that overhead per-asset.
BATCH_SIZE = 4
SEARCHES_PER_ASSET_BATCHED = 2
VERIFY_SEARCHES_PER_ASSET_BATCHED = 1

# Only this category gets the second independent verification pass — the
# one most prone to a wrong single spot-price basis (the failure mode that
# produced the original ETH bug).
VERIFY_CATEGORIES = {"Commodity"}

# Crypto assets researched individually with a live price API (see
# CRYPTO_PRICE_IDS below) instead of via the batched/verified flow.
SEARCHES_PER_CRYPTO_ASSET = 4

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

# Batched variants: one tool call covers several assets at once, keyed by id
# so results can be mapped back to the right asset.
BATCH_SUBMIT_TOOL = {
    "name": "submit_projections",
    "description": "Submit researched 3-year forward return projections for ALL the asset classes listed in this request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "projections": {
                "type": "array",
                "description": "One entry per asset class listed in the prompt, using the exact same id given for each.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The asset's id, exactly as given in the prompt"},
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
                            "description": "The single current market figure (price, yield, or rate) used as the Year 1 starting reference point",
                        },
                        "basisDescription": {
                            "type": "string",
                            "description": "One short phrase describing exactly what basisValue represents and its unit",
                        },
                    },
                    "required": ["id", "r", "why", "basisValue", "basisDescription"],
                },
            },
        },
        "required": ["projections"],
    },
}

BATCH_VERIFY_TOOL = {
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
                        "id": {"type": "string", "description": "The asset id this verification is for, exactly as given in the prompt"},
                        "verifiedValue": {
                            "type": "number",
                            "description": "The current numeric value you independently found, in the same units as the claim",
                        },
                        "note": {
                            "type": "string",
                            "description": "Brief note (under 200 characters) on what you found and where",
                        },
                    },
                    "required": ["id", "verifiedValue", "note"],
                },
            },
        },
        "required": ["verifications"],
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


def chunk(items, size):
    return [items[i : i + size] for i in range(0, len(items), size)]


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


# ---------------------------------------------------------------------------
# Crypto: researched individually, basis grounded via a live price API.
# ---------------------------------------------------------------------------


def research_crypto_asset(client, model_id, asset, today, live_price_note):
    hint = SOURCE_HINTS.get(asset["id"], "")
    correction_block = f"\n\nIMPORTANT — VERIFIED CURRENT DATA: {live_price_note} You MUST use this as your Year 1 starting basisValue rather than any other figure you find or recall.\n" if live_price_note else ""

    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current market conditions or analyst forecasts from memory alone.

Use the web_search tool to find REAL, CURRENT analyst consensus 3-year forward return projections for this asset class:

Name: {asset['name']}
Category: {asset['cat']}
Look for sources like: {hint}
{correction_block}
Current (soon to be replaced) projections for reference — update them based on what you actually find:
Year 1: {asset['r'][0]}%, Year 2: {asset['r'][1]}%, Year 3: {asset['r'][2]}%

Search for the latest available price targets. If exact 3-year figures aren't published, reasonably derive Year 2/Year 3 from the trend implied by what you find, and say so in "why".

Once you've searched enough to form a view, call submit_projection with your answer, including the specific current-market basisValue and basisDescription you used as your Year 1 starting point."""

    response = client.messages.create(
        model=model_id,
        max_tokens=3000,
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCHES_PER_CRYPTO_ASSET},
            SUBMIT_TOOL,
        ],
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
        extract_search_sources(response.content),
        usage_cost(response.usage),
    )


def process_crypto_asset(client, model_id, asset, today, cost_tracker):
    live_price_note = None
    try:
        price = fetch_live_crypto_price(CRYPTO_PRICE_IDS[asset["id"]])
        live_price_note = f"The current price of {asset['name']} is ${price:,.2f} USD, fetched live from CoinGecko moments ago."
        print(f"  Live price for {asset['name']}: ${price:,.2f}")
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        print(f"  Warning: live price fetch failed for {asset['name']} ({e}); falling back to search-based basis")

    r, why, sources, cost = research_crypto_asset(client, model_id, asset, today, live_price_note)
    cost_tracker[0] += cost
    return {"r": r, "why": why}, sources


# ---------------------------------------------------------------------------
# Non-crypto: researched (and, for commodities, verified) in small batches.
# ---------------------------------------------------------------------------


def research_batch(client, model_id, assets, today, corrections=None):
    """Research a batch of related assets in a single call, sharing search
    budget and prompt overhead across them. `corrections`, if given, maps
    asset id -> a hard-override instruction for that asset's basis (used on
    a retry after verify_batch finds a mismatch). Returns
    (by_id, sources, cost_usd) where by_id maps asset id -> tool input dict."""
    corrections = corrections or {}
    blocks = []
    for a in assets:
        hint = SOURCE_HINTS.get(a["id"], "")
        block = (
            f"- id: {a['id']}\n"
            f"  Name: {a['name']}\n"
            f"  Category: {a['cat']}\n"
            f"  Look for sources like: {hint}\n"
            f"  Current (soon to be replaced) projections: Year1 {a['r'][0]}%, Year2 {a['r'][1]}%, Year3 {a['r'][2]}%"
        )
        if a["id"] in corrections:
            block += f"\n  VERIFIED CURRENT DATA (override): {corrections[a['id']]} You MUST use this as this asset's Year 1 starting basisValue."
        blocks.append(block)
    assets_block = "\n\n".join(blocks)

    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current market conditions or analyst forecasts from memory alone.

Use the web_search tool to find REAL, CURRENT analyst consensus 3-year forward return projections for EACH of the following {len(assets)} asset classes. You have a shared search budget across all of them — search efficiently.

{assets_block}

Search for the latest available price targets, rate outlooks, or return forecasts for each asset. If exact 3-year figures aren't published for one, reasonably derive Year 2/Year 3 from the trend implied by what you find, and say so in that asset's "why".

Once you've researched all {len(assets)} asset classes, call submit_projections with one entry per asset (matching each "id" exactly), including the specific current-market basisValue and basisDescription you used as each asset's Year 1 starting point."""

    max_uses = max(2, SEARCHES_PER_ASSET_BATCHED * len(assets))
    response = client.messages.create(
        model=model_id,
        max_tokens=1200 * len(assets),
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses},
            BATCH_SUBMIT_TOOL,
        ],
        tool_choice={"type": "any", "disable_parallel_tool_use": True},
        messages=[{"role": "user", "content": prompt}],
    )

    submission = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_projections"),
        None,
    )
    if submission is None:
        raise ValueError(
            f"Model never called submit_projections for batch {[a['id'] for a in assets]} (stop_reason={response.stop_reason})"
        )

    by_id = {p["id"]: p for p in submission.input["projections"]}
    missing = [a["id"] for a in assets if a["id"] not in by_id]
    if missing:
        raise ValueError(f"submit_projections response missing ids: {missing}")

    return by_id, extract_search_sources(response.content), usage_cost(response.usage)


def verify_batch(client, model_id, claims, today):
    """claims: list of {id, name, cat, basisValue, basisDescription}.
    Independently fact-checks each claim in ONE call with no shared context
    from the research call. Returns (by_id_verified, sources, cost_usd)."""
    blocks = []
    for c in claims:
        blocks.append(
            f"- id: {c['id']}\n"
            f"  Asset: {c['name']} ({c['cat']})\n"
            f"  Claim to verify: \"{c['basisDescription']}\" was reported as {c['basisValue']}"
        )
    claims_block = "\n\n".join(blocks)

    prompt = f"""Today is {today}. You are independently fact-checking these market data claims — do not assume any of them are correct.

{claims_block}

Search the web yourself for each one and find the actual current value. Then call submit_verifications with one entry per id, reporting what you actually find regardless of whether it matches the claim."""

    max_uses = max(1, VERIFY_SEARCHES_PER_ASSET_BATCHED * len(claims))
    response = client.messages.create(
        model=model_id,
        max_tokens=500 * len(claims),
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses},
            BATCH_VERIFY_TOOL,
        ],
        tool_choice={"type": "any", "disable_parallel_tool_use": True},
        messages=[{"role": "user", "content": prompt}],
    )

    submission = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_verifications"),
        None,
    )
    if submission is None:
        return {}, extract_search_sources(response.content), usage_cost(response.usage)

    by_id = {v["id"]: v for v in submission.input["verifications"]}
    return by_id, extract_search_sources(response.content), usage_cost(response.usage)


def process_batch(client, model_id, batch, today, cost_tracker):
    """Research one batch, verifying+retrying it if it's a category that
    gets the independent double-check. Returns (by_id, sources)."""
    by_id, sources, cost = research_batch(client, model_id, batch, today)
    cost_tracker[0] += cost

    category = batch[0]["cat"]
    if category in VERIFY_CATEGORIES:
        claims = [
            {
                "id": a["id"],
                "name": a["name"],
                "cat": a["cat"],
                "basisValue": by_id[a["id"]]["basisValue"],
                "basisDescription": by_id[a["id"]]["basisDescription"],
            }
            for a in batch
            if by_id[a["id"]].get("basisValue") is not None
        ]

        if claims:
            verified_by_id, verify_sources, verify_cost = verify_batch(client, model_id, claims, today)
            cost_tracker[0] += verify_cost
            sources = sources + verify_sources

            corrections = {}
            for c in claims:
                v = verified_by_id.get(c["id"])
                if v is None:
                    continue
                rel_diff = abs(v["verifiedValue"] - c["basisValue"]) / max(abs(c["basisValue"]), 1e-9)
                if rel_diff > BASIS_MISMATCH_TOLERANCE:
                    print(
                        f"  Basis mismatch for {c['id']}: claimed {c['basisValue']}, "
                        f"independently found {v['verifiedValue']} ({rel_diff:.0%} off)"
                    )
                    corrections[c["id"]] = (
                        f"An independent fact-check found that '{c['basisDescription']}' is actually "
                        f"approximately {v['verifiedValue']}, not {c['basisValue']} ({v['note']})."
                    )
                else:
                    print(f"  Basis confirmed for {c['id']}: {c['basisValue']} ≈ {v['verifiedValue']}")

            if corrections:
                print(f"  Retrying batch with corrections for: {list(corrections.keys())}")
                by_id, retry_sources, retry_cost = research_batch(
                    client, model_id, batch, today, corrections=corrections
                )
                cost_tracker[0] += retry_cost
                sources = sources + retry_sources

    return by_id, sources


def main():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    with open(DATA_PATH) as f:
        data = json.load(f)

    today = date.today().isoformat()

    # Auto-select latest Haiku model so no code change needed when versions update
    models = client.models.list()
    model_id = next(m.id for m in models.data if "haiku" in m.id)
    print(f"Using model: {model_id}")

    all_sources = []
    seen_source_urls = set()
    cost_tracker = [0.0]  # mutable box so helpers can accumulate real per-call cost
    results_by_id = {}

    def merge_sources(asset_id, asset_name, sources):
        for s in sources:
            if s["url"] not in seen_source_urls:
                seen_source_urls.add(s["url"])
                all_sources.append({**s, "assetId": asset_id, "assetName": asset_name})

    non_crypto = [a for a in data["assets"] if a["id"] not in CRYPTO_PRICE_IDS]
    crypto = [a for a in data["assets"] if a["id"] in CRYPTO_PRICE_IDS]

    # Group non-crypto assets by category (preserving first-seen order), then
    # chunk each category into batches so related assets share one call.
    by_category = {}
    category_order = []
    for a in non_crypto:
        by_category.setdefault(a["cat"], []).append(a)
        if a["cat"] not in category_order:
            category_order.append(a["cat"])

    for category in category_order:
        for batch in chunk(by_category[category], BATCH_SIZE):
            print(f"Researching batch ({category}): {[a['id'] for a in batch]}...")
            by_id, sources = process_batch(client, model_id, batch, today, cost_tracker)
            for a in batch:
                results_by_id[a["id"]] = by_id[a["id"]]
            # A batch's sources aren't attributable to one specific asset within
            # it (shared search budget), so attribute each source to the whole
            # batch once rather than either duplicating it under every asset or
            # silently losing it to global URL-dedup after the first asset claims it.
            batch_id = "+".join(a["id"] for a in batch)
            batch_name = ", ".join(a["name"] for a in batch)
            merge_sources(batch_id, batch_name, sources)

    for asset in crypto:
        print(f"Researching {asset['name']}...")
        result, sources = process_crypto_asset(client, model_id, asset, today, cost_tracker)
        results_by_id[asset["id"]] = result
        merge_sources(asset["id"], asset["name"], sources)

    updated_assets = []
    for asset in data["assets"]:
        result = results_by_id[asset["id"]]
        updated = dict(asset)
        updated["r"] = result["r"]
        updated["d"] = result["r"]
        updated["why"] = result["why"]
        updated_assets.append(updated)

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
