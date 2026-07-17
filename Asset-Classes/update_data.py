#!/usr/bin/env python3
"""
Monthly script to refresh Asset-Classes/data.json using the Claude API.
Called by GitHub Actions on the 1st of each month.
Requires: ANTHROPIC_API_KEY environment variable

Each asset is researched individually with the web_search tool enabled, so
projections are grounded in real, current search results rather than the
model's training data alone. The projection itself is returned via a forced
tool call (not parsed from free text) so an uncertain model can't skip the
structured answer in favor of a prose caveat. The real pages found during
research are collected into data["sources"] as an appendix for the UI, and
the run's exact metered cost (from each response's usage object) is stored
in data["lastRunCostUsd"].
"""
import json
import os
from datetime import date
from pathlib import Path

import anthropic

DATA_PATH = Path(__file__).parent / "data.json"
HISTORY_PATH = Path(__file__).parent / "history.json"
MAX_HISTORY_MONTHS = 12
SEARCHES_PER_ASSET = 4

# Claude Haiku 4.5 pricing (USD per token), from https://platform.claude.com/docs/en/about-claude/pricing
# NOTE: model_id is auto-selected as "latest Haiku" below — if a future Haiku
# version changes pricing, update these rates to match.
PRICE_PER_INPUT_TOKEN = 1.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 5.00 / 1_000_000
PRICE_PER_CACHE_WRITE_TOKEN = 1.25 / 1_000_000  # 5-minute cache write rate
PRICE_PER_CACHE_READ_TOKEN = 0.10 / 1_000_000
PRICE_PER_SEARCH = 10.00 / 1_000

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
        },
        "required": ["r", "why"],
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


def research_asset(client, model_id, asset, today):
    """Search the web for one asset's current analyst consensus and return
    (r, why, sources, cost_usd), where sources are the real pages found
    during research and cost_usd is this call's real, metered API cost."""
    hint = SOURCE_HINTS.get(asset["id"], "")
    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current market conditions or analyst forecasts from memory alone.

Use the web_search tool to find REAL, CURRENT analyst consensus 3-year forward return projections for this asset class:

Name: {asset['name']}
Category: {asset['cat']}
Look for sources like: {hint}

Current (soon to be replaced) projections for reference — update them based on what you actually find:
Year 1: {asset['r'][0]}%, Year 2: {asset['r'][1]}%, Year 3: {asset['r'][2]}%

Search for the latest available price targets, rate outlooks, or return forecasts. If exact 3-year figures aren't published, reasonably derive Year 2/Year 3 from the trend implied by what you find (e.g. a 12-month price target plus a stated longer-run view) — do not withhold a projection just because the exact figure isn't published verbatim; give your best grounded estimate and explain the derivation in "why".

Once you've searched enough to form a view, call submit_projection with your answer."""

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

    r = submission.input["r"]
    why = submission.input["why"]

    sources = []
    seen_urls = set()
    for b in response.content:
        if b.type == "web_search_tool_result" and isinstance(b.content, list):
            for result in b.content:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    sources.append({"title": result.title, "url": result.url})

    return r, why, sources, usage_cost(response.usage)


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
    total_cost_usd = 0.0

    for asset in data["assets"]:
        print(f"Researching {asset['name']}...")
        r, why, sources, cost_usd = research_asset(client, model_id, asset, today)
        total_cost_usd += cost_usd

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
