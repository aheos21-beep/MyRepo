#!/usr/bin/env python3
"""
Monthly script to refresh Asset-Classes/data.json using the Claude API.
Called by GitHub Actions on the 1st of each month.
Requires: ANTHROPIC_API_KEY environment variable

Each asset is researched individually with the web_search tool enabled, so
projections are grounded in real, current search results rather than the
model's training data alone. The actual pages Claude cited are collected
into data["sources"] as an appendix for the UI.
"""
import json
import os
import re
from datetime import date
from pathlib import Path

import anthropic

DATA_PATH = Path(__file__).parent / "data.json"
HISTORY_PATH = Path(__file__).parent / "history.json"
MAX_HISTORY_MONTHS = 12
SEARCHES_PER_ASSET = 4

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


def research_asset(client, model_id, asset, today):
    """Search the web for one asset's current analyst consensus and return
    (r, why, sources), where sources are real pages Claude actually cited."""
    hint = SOURCE_HINTS.get(asset["id"], "")
    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current market conditions or analyst forecasts from memory alone.

Use the web_search tool to find REAL, CURRENT analyst consensus 3-year forward return projections for this asset class:

Name: {asset['name']}
Category: {asset['cat']}
Look for sources like: {hint}

Current (soon to be replaced) projections for reference — update them based on what you actually find:
Year 1: {asset['r'][0]}%, Year 2: {asset['r'][1]}%, Year 3: {asset['r'][2]}%

Search for the latest available price targets, rate outlooks, or return forecasts. If exact 3-year figures aren't published, reasonably derive Year 2/Year 3 from the trend implied by what you find (e.g. a 12-month price target plus a stated longer-run view), and say so in the rationale.

Return ONLY a single JSON object, no markdown, no commentary, in exactly this shape:
{{"r": [year1_pct, year2_pct, year3_pct], "why": ["reason for year 1 naming the source/analyst and date found", "reason for year 2", "reason for year 3"]}}

Each "why" entry must be under 240 characters."""

    response = client.messages.create(
        model=model_id,
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCHES_PER_ASSET}],
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [b for b in response.content if b.type == "text"]
    text = "".join(b.text for b in text_blocks).strip()
    text = re.sub(r"^```[a-z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response for {asset['id']}: {text[:200]}")
    parsed = json.loads(match.group(0))

    # Prefer sources Claude actually cited in its answer; fall back to raw
    # search results if citations weren't attached to the final text.
    sources = []
    seen_urls = set()
    for b in text_blocks:
        for citation in (b.citations or []):
            if citation.type == "web_search_result_location" and citation.url not in seen_urls:
                seen_urls.add(citation.url)
                sources.append({"title": citation.title or citation.url, "url": citation.url})

    if not sources:
        for b in response.content:
            if b.type == "web_search_tool_result" and isinstance(b.content, list):
                for result in b.content:
                    if result.url not in seen_urls:
                        seen_urls.add(result.url)
                        sources.append({"title": result.title, "url": result.url})

    return parsed["r"], parsed["why"], sources


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

    for asset in data["assets"]:
        print(f"Researching {asset['name']}...")
        r, why, sources = research_asset(client, model_id, asset, today)

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

    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    history["history"].append({"date": today, "ranks": new_ranks})
    history["history"] = history["history"][-MAX_HISTORY_MONTHS:]

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"data.json updated — {len(updated_assets)} assets, {len(all_sources)} sources, date: {today}")


if __name__ == "__main__":
    main()
