"""
Fetches Arena ELO scores via Claude API web search and maintains history.json.
Runs bi-monthly (1st and 15th) via GitHub Actions.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

DOCS_DIR = Path(__file__).parent

# Upgrade by changing this env var in GitHub Actions secrets or locally.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

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

# ── Claude API web search ──────────────────────────────────────────────────────

def fetch_arena_elo_via_claude() -> dict | None:
    """
    Use Claude + web search to find current LMSYS Chatbot Arena ELO scores.
    Returns {model_display_name: elo_int} or None on failure.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[claude] ANTHROPIC_API_KEY not set — skipping web search", file=sys.stderr)
        return None

    client = anthropic.Anthropic(api_key=api_key)
    model_names = ", ".join(
        name
        for t in TOOLS
        for name in t["arena_names"]
    )
    prompt = (
        "Search the web for the current LMSYS Chatbot Arena ELO leaderboard "
        "(lmarena.ai or huggingface.co/spaces/lmsys/chatbot-arena-leaderboard). "
        "Find the latest ELO scores for these models (use partial matches if exact names differ): "
        f"{model_names}. "
        "Return ONLY a JSON object mapping each model key to its integer ELO score, "
        'e.g. {"gpt-4o": 1287, "claude-3-5-sonnet": 1265, ...}. '
        "No markdown, no explanation — raw JSON only."
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"[claude] API call failed: {exc}", file=sys.stderr)
        return None

    # Extract text from the final assistant message
    raw_text = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            raw_text += block.text

    if not raw_text.strip():
        print("[claude] No text in response", file=sys.stderr)
        return None

    # Parse JSON — handle possible markdown code fences
    json_match = re.search(r"\{[^{}]+\}", raw_text, re.DOTALL)
    if not json_match:
        print(f"[claude] No JSON found in response: {raw_text[:200]}", file=sys.stderr)
        return None

    try:
        elo_map = json.loads(json_match.group())
        # Validate: values should be plausible ELO integers
        elo_map = {
            k.lower(): int(v)
            for k, v in elo_map.items()
            if isinstance(v, (int, float)) and 800 < float(v) < 2000
        }
        if elo_map:
            print(f"[claude] Got {len(elo_map)} ELO scores via web search", file=sys.stderr)
            return elo_map
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[claude] JSON parse error: {exc} — raw: {raw_text[:200]}", file=sys.stderr)

    return None


def match_elo(arena_data: dict | None, tool: dict) -> int | None:
    if not arena_data:
        return None
    for name in tool["arena_names"]:
        key = name.lower()
        if key in arena_data:
            return arena_data[key]
        for arena_key, elo in arena_data.items():
            if name.lower() in arena_key or arena_key in name.lower():
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

def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Using model: {CLAUDE_MODEL}")
    print("Fetching Arena ELO scores via Claude web search…")
    arena_data = fetch_arena_elo_via_claude()
    if arena_data:
        print(f"  → Live data: {len(arena_data)} models")
    else:
        print("  → Web search unavailable — using seeded base values", file=sys.stderr)

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
    main()
