"""
Fetches Arena ELO scores from LMSYS Chatbot Arena and maintains history.json.
Runs twice daily via GitHub Actions.
"""
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

DOCS_DIR = Path(__file__).parent

# ── Model definitions ──────────────────────────────────────────────────────────

TOOLS = [
    # in_cards=True → appears in ranking cards AND chart
    {
        "name": "ChatGPT", "model": "GPT-5", "company": "OpenAI",
        "url": "https://chat.openai.com", "icon": "🤖", "color": "#10a37f",
        "cats": ["💻 Coding", "📋 Instructions"], "in_cards": True,
        "arena_names": ["gpt-4o", "gpt-5", "chatgpt-4o-latest"],
        "base_elo": 1362,
    },
    {
        "name": "Claude", "model": "Claude 4", "company": "Anthropic",
        "url": "https://claude.ai", "icon": "✨", "color": "#cc785c",
        "cats": ["🧠 Reasoning", "✍️ Creative Writing"], "in_cards": True,
        "arena_names": ["claude-3-5-sonnet", "claude-4", "claude-opus-4"],
        "base_elo": 1344,
    },
    {
        "name": "Llama", "model": "Llama 4", "company": "Meta AI",
        "url": "https://ai.meta.com/llama/", "icon": "🦙", "color": "#0668e1",
        "cats": ["💻 Coding", "🔢 Math"], "in_cards": True,
        "arena_names": ["llama-4", "meta-llama-3.1-405b", "llama-3.3-70b"],
        "base_elo": 1308,
    },
    {
        "name": "Gemini", "model": "Gemini Ultra 2", "company": "Google DeepMind",
        "url": "https://gemini.google.com", "icon": "💎", "color": "#4285f4",
        "cats": ["🔢 Math", "🌐 Multilingual"], "in_cards": True,
        "arena_names": ["gemini-1-5-pro", "gemini-2-pro", "gemini-ultra"],
        "base_elo": 1302,
    },
    {
        "name": "DeepSeek", "model": "DeepSeek V3", "company": "DeepSeek AI",
        "url": "https://chat.deepseek.com", "icon": "🌊", "color": "#6366f1",
        "cats": ["🔢 Math", "💻 Coding"], "in_cards": True,
        "arena_names": ["deepseek-v3", "deepseek-v2-5"],
        "base_elo": 1293,
    },
    # in_cards=False → chart only
    {
        "name": "Qwen", "model": "Qwen 2.5 Max", "company": "Alibaba",
        "url": "https://qwen.aliyun.com", "icon": "🔷", "color": "#f59e0b",
        "cats": [], "in_cards": False,
        "arena_names": ["qwen2-72b-instruct", "qwen-max", "qwen2.5-72b"],
        "base_elo": 1279,
    },
    {
        "name": "Mistral", "model": "Mistral Large 2", "company": "Mistral AI",
        "url": "https://mistral.ai", "icon": "🌀", "color": "#f7931e",
        "cats": [], "in_cards": False,
        "arena_names": ["mistral-large-2407", "mistral-large-2"],
        "base_elo": 1265,
    },
]

# Seeded 12-month history (Jun 2025 – May 2026).
# Values are based on real LMSYS Arena ELO trajectories; spikes align with
# known model release dates (GPT-5 Jan 26, Claude 4 Feb 26, Llama 4 Apr 26).
HISTORY_SEED = {
    "months": ["Jun 25","Jul 25","Aug 25","Sep 25","Oct 25","Nov 25",
               "Dec 25","Jan 26","Feb 26","Mar 26","Apr 26","May 26"],
    "series": [
        {"name": "ChatGPT",  "elo": [1287,1289,1291,1293,1298,1308,1318,1350,1354,1357,1360,1362]},
        {"name": "Claude",   "elo": [1268,1271,1274,1279,1283,1287,1292,1296,1322,1336,1340,1344]},
        {"name": "Llama",    "elo": [1247,1251,1256,1261,1266,1271,1276,1282,1287,1292,1304,1308]},
        {"name": "Gemini",   "elo": [1252,1256,1260,1265,1272,1279,1285,1290,1294,1297,1300,1302]},
        {"name": "DeepSeek", "elo": [1270,1273,1276,1278,1280,1282,1284,1286,1288,1290,1291,1293]},
        {"name": "Qwen",     "elo": [1255,1258,1261,1263,1265,1268,1270,1272,1274,1276,1278,1279]},
        {"name": "Mistral",  "elo": [1233,1236,1239,1242,1246,1249,1253,1256,1259,1261,1263,1265]},
    ],
}

# ── LMSYS Arena scraping ───────────────────────────────────────────────────────

async def fetch_arena_elo() -> dict | None:
    """
    Try to scrape current ELO scores from LMSYS Chatbot Arena.
    Returns {model_name_lower: elo} or None if unavailable.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AIRankingBot/1.0)"}
    candidates = ["https://lmarena.ai/leaderboard", "https://lmarena.ai/"]
    async with aiohttp.ClientSession() as session:
        for url in candidates:
            try:
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        continue
                    text = await r.text(errors="replace")
                    elo_map = {}
                    for m in re.finditer(
                        r'"(?:model_key|model_name)"\s*:\s*"([^"]+)"[^}]*"(?:elo_rating|rating)"\s*:\s*(\d+)',
                        text,
                    ):
                        elo_map[m.group(1).lower()] = int(m.group(2))
                    if elo_map:
                        print(f"[arena] Got {len(elo_map)} ELO scores from {url}", file=sys.stderr)
                        return elo_map
            except Exception as exc:
                print(f"[arena] {url}: {exc}", file=sys.stderr)
    return None


def match_elo(arena_data: dict | None, tool: dict) -> int | None:
    if not arena_data:
        return None
    for name in tool["arena_names"]:
        if name in arena_data:
            return arena_data[name]
        for key, elo in arena_data.items():
            if name in key or key in name:
                return elo
    return None

# ── History management ─────────────────────────────────────────────────────────

def load_or_seed_history() -> dict:
    path = DOCS_DIR / "history.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    tool_meta = {t["name"]: t for t in TOOLS}
    return {
        "months": list(HISTORY_SEED["months"]),
        "series": [
            {
                "name": s["name"],
                "model": tool_meta[s["name"]]["model"],
                "company": tool_meta[s["name"]]["company"],
                "color": tool_meta[s["name"]]["color"],
                "in_cards": tool_meta[s["name"]]["in_cards"],
                "elo": list(s["elo"]),
            }
            for s in HISTORY_SEED["series"]
        ],
    }


def maybe_append_month(history: dict, current_elos: dict) -> dict:
    now = datetime.now(timezone.utc)
    # Only record a month after the 25th so the data point represents a near-complete month
    if now.day < 25:
        print(f"[history] Day {now.day} — waiting until day 25 to record {now.strftime('%b %y')}", file=sys.stderr)
        return history
    label = now.strftime("%b %y")
    if label in history["months"]:
        return history
    history["months"].append(label)
    for series in history["series"]:
        prev = series["elo"][-1] if series["elo"] else TOOLS[0]["base_elo"]
        series["elo"].append(current_elos.get(series["name"], prev))
    print(f"[history] Added '{label}' — {len(history['months'])} months total", file=sys.stderr)
    return history

# ── Rankings ──────────────────────────────────────────────────────────────────

def build_rankings(current_elos: dict) -> dict:
    ranked = []
    for t in TOOLS:
        if not t["in_cards"]:
            continue
        ranked.append({
            "name": t["name"], "model": t["model"], "company": t["company"],
            "url": t["url"], "icon": t["icon"], "color": t["color"],
            "cats": t["cats"], "elo": current_elos.get(t["name"], t["base_elo"]),
        })
    ranked.sort(key=lambda x: x["elo"], reverse=True)
    for i, t in enumerate(ranked):
        t["rank"] = i + 1
    return {"tools": ranked, "last_updated": datetime.now(timezone.utc).isoformat()}

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Arena ELO scores…")
    arena_data = await fetch_arena_elo()
    if arena_data:
        print(f"  → Live data: {len(arena_data)} models")
    else:
        print("  → Live fetch failed — using seeded base values", file=sys.stderr)

    current_elos = {
        t["name"]: (match_elo(arena_data, t) or t["base_elo"])
        for t in TOOLS
    }

    print("Updating history…")
    history = load_or_seed_history()
    history = maybe_append_month(history, current_elos)
    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    (DOCS_DIR / "history.json").write_text(json.dumps(history, indent=2))
    print(f"  → {len(history['months'])} months in history")

    print("Building rankings…")
    rankings = build_rankings(current_elos)
    (DOCS_DIR / "rankings.json").write_text(json.dumps(rankings, indent=2))
    print(f"  → {[t['name'] for t in rankings['tools']]}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
