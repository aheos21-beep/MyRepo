#!/usr/bin/env python3
"""
Monthly script to refresh Asset-Classes/data.json using the Claude API.
Called by GitHub Actions on the 1st of each month.
Requires: ANTHROPIC_API_KEY environment variable
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


def main():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    with open(DATA_PATH) as f:
        data = json.load(f)

    today = date.today().isoformat()

    prompt = f"""Today is {today}. You are updating analyst consensus return projections for a personal investment dashboard.

The dashboard tracks 24 asset classes with 3-year annual return projections: Year 1 (next 12 months), Year 2, Year 3.
Values are annual percentage returns (e.g. 8.0 = 8.0%).

For each asset, provide UPDATED projections based on the latest analyst consensus as of {today}.

Source guidance per category:
- CAD/US Equities: Goldman Sachs, JPMorgan, RBC, BofA, Morgan Stanley year-end targets
- Canadian Real Estate: CREA forecasts, BoC rate path
- US Real Estate: CBRE outlook
- Canadian REITs: RBC Capital Markets, REIT sector reports
- Fixed Income: BoC rate path, RBC bond outlook
- Gold/Silver/Palladium: WGC, LBMA, JPMorgan, Goldman Sachs
- Bitcoin/Ethereum: Bitwise, Standard Chartered, JPMorgan crypto targets
- Oil/Gas: Goldman Sachs, JPMorgan, EIA
- Uranium: Sprott, IAEA
- Copper/Lithium: Goldman Sachs, TD Securities, Wood Mackenzie
- Wheat/Potash: USDA, World Bank
- Lumber: ERA Forecast, Fastmarkets

Current data for reference:
{json.dumps(data["assets"], indent=2)}

Rules:
1. Keep "id", "name", "cat", "color" fields identical — do not change them
2. Update "r" arrays with your best analyst consensus estimates for Y1/Y2/Y3
3. Set "d" arrays equal to the new "r" arrays
4. Update "why" arrays with fresh rationale citing specific analyst names, price targets, and the current date
5. Return ONLY a valid JSON array — no markdown, no code fences, no commentary
6. The array must have exactly {len(data["assets"])} elements in the same order

Return the complete updated JSON array starting with [ and ending with ]."""

    # Auto-select latest Haiku model so no code change needed when versions update
    models = client.models.list()
    model_id = next(m.id for m in models.data if "haiku" in m.id)
    print(f"Using model: {model_id}")
    print(f"Requesting updated projections from Claude for {today}...")

    with client.messages.stream(
        model=model_id,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        message = stream.get_final_message()

    text = next(b.text for b in message.content if b.type == "text")

    # Strip any accidental markdown code fences
    text = re.sub(r"^```[a-z]*\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    updated_assets = json.loads(text.strip())

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

    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    history["history"].append({"date": today, "ranks": new_ranks})
    history["history"] = history["history"][-MAX_HISTORY_MONTHS:]

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"data.json updated — {len(updated_assets)} assets, date: {today}")


if __name__ == "__main__":
    main()
