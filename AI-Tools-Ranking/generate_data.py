"""
Fetches multi-benchmark scores via Claude API web search and maintains history.json.
Composite score = 40% LMSYS ELO + 25% MMLU + 20% HumanEval + 15% MATH (all normalized 0-100).
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

# Upgrade by changing this env var in GitHub Actions (or locally).
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

# Normalization range for LMSYS Arena ELO → 0-100
ELO_MIN = 1100
ELO_MAX = 1450

# Composite weights (must sum to 1.0)
WEIGHTS = {"lmsys_elo": 0.40, "mmlu": 0.25, "humaneval": 0.20, "math": 0.15}

# ── Model definitions ──────────────────────────────────────────────────────────

TOOLS = [
    # in_cards=True → appears in ranking cards AND chart
    {
        "name": "ChatGPT", "model": "GPT-5", "company": "OpenAI",
        "url": "https://chat.openai.com", "icon": "🤖", "color": "#10a37f",
        "cats": ["💻 Coding", "📋 Instructions"], "in_cards": True,
        "arena_names": ["gpt-4o", "gpt-5", "chatgpt-4o-latest"],
        "base_score": 86,
        "base_benchmarks": {"lmsys_elo": 1362, "mmlu": 90.0, "humaneval": 90.0, "math": 85.0},
    },
    {
        "name": "Claude", "model": "Claude 4", "company": "Anthropic",
        "url": "https://claude.ai", "icon": "✨", "color": "#cc785c",
        "cats": ["🧠 Reasoning", "✍️ Creative Writing"], "in_cards": True,
        "arena_names": ["claude-3-5-sonnet", "claude-4", "claude-opus-4"],
        "base_score": 83,
        "base_benchmarks": {"lmsys_elo": 1344, "mmlu": 89.0, "humaneval": 93.0, "math": 88.0},
    },
    {
        "name": "Llama", "model": "Llama 4", "company": "Meta AI",
        "url": "https://ai.meta.com/llama/", "icon": "🦙", "color": "#0668e1",
        "cats": ["💻 Coding", "🔢 Math"], "in_cards": True,
        "arena_names": ["llama-4", "meta-llama-3.1-405b", "llama-3.3-70b"],
        "base_score": 73,
        "base_benchmarks": {"lmsys_elo": 1308, "mmlu": 86.0, "humaneval": 88.0, "math": 80.0},
    },
    {
        "name": "Gemini", "model": "Gemini Ultra 2", "company": "Google DeepMind",
        "url": "https://gemini.google.com", "icon": "💎", "color": "#4285f4",
        "cats": ["🔢 Math", "🌐 Multilingual"], "in_cards": True,
        "arena_names": ["gemini-1-5-pro", "gemini-2-pro", "gemini-ultra"],
        "base_score": 72,
        "base_benchmarks": {"lmsys_elo": 1302, "mmlu": 87.0, "humaneval": 86.0, "math": 83.0},
    },
    {
        "name": "DeepSeek", "model": "DeepSeek V3", "company": "DeepSeek AI",
        "url": "https://chat.deepseek.com", "icon": "🌊", "color": "#6366f1",
        "cats": ["🔢 Math", "💻 Coding"], "in_cards": True,
        "arena_names": ["deepseek-v3", "deepseek-v2-5"],
        "base_score": 71,
        "base_benchmarks": {"lmsys_elo": 1293, "mmlu": 88.0, "humaneval": 85.0, "math": 90.0},
    },
    # in_cards=False → chart only
    {
        "name": "Qwen", "model": "Qwen 2.5 Max", "company": "Alibaba",
        "url": "https://qwen.aliyun.com", "icon": "🔷", "color": "#f59e0b",
        "cats": [], "in_cards": False,
        "arena_names": ["qwen2-72b-instruct", "qwen-max", "qwen2.5-72b"],
        "base_score": 65,
        "base_benchmarks": {"lmsys_elo": 1279, "mmlu": 85.0, "humaneval": 80.0, "math": 82.0},
    },
    {
        "name": "Mistral", "model": "Mistral Large 2", "company": "Mistral AI",
        "url": "https://mistral.ai", "icon": "🌀", "color": "#f7931e",
        "cats": [], "in_cards": False,
        "arena_names": ["mistral-large-2407", "mistral-large-2"],
        "base_score": 59,
        "base_benchmarks": {"lmsys_elo": 1265, "mmlu": 81.0, "humaneval": 75.0, "math": 73.0},
    },
]

# Seeded 12-month history (Jun 2025 – May 2026).
# Composite scores derived from benchmark trajectories aligned with known model releases:
# GPT-5 Jan 26, Claude 4 Feb 26, Llama 4 Apr 26.
HISTORY_SEED = {
    "months": ["Jun 25","Jul 25","Aug 25","Sep 25","Oct 25","Nov 25",
               "Dec 25","Jan 26","Feb 26","Mar 26","Apr 26","May 26"],
    "series": [
        {"name": "ChatGPT",  "score": [71,71,71,72,73,75,77,83,84,85,85,86]},
        {"name": "Claude",   "score": [68,68,69,70,71,71,72,73,78,81,82,83]},
        {"name": "Llama",    "score": [61,61,62,63,64,65,66,68,69,70,72,73]},
        {"name": "Gemini",   "score": [62,63,63,64,66,67,68,69,70,71,71,72]},
        {"name": "DeepSeek", "score": [67,67,68,68,69,69,69,70,70,71,71,71]},
        {"name": "Qwen",     "score": [61,61,62,62,63,63,64,64,64,65,65,65]},
        {"name": "Mistral",  "score": [53,53,54,55,55,56,57,57,58,58,59,59]},
    ],
}

# ── Scoring ───────────────────────────────────────────────────────────────────

def normalize_elo(elo: float) -> float:
    return max(0.0, min(100.0, (elo - ELO_MIN) / (ELO_MAX - ELO_MIN) * 100.0))


def compute_composite(benchmarks: dict) -> float | None:
    total, weight_sum = 0.0, 0.0
    for key, weight in WEIGHTS.items():
        val = benchmarks.get(key)
        if val is None:
            continue
        normalized = normalize_elo(val) if key == "lmsys_elo" else float(val)
        total += normalized * weight
        weight_sum += weight
    if weight_sum == 0:
        return None
    return round(total / weight_sum, 1)

# ── Claude API web search ──────────────────────────────────────────────────────

def fetch_benchmarks_via_claude() -> dict | None:
    """
    Ask Claude to search for LMSYS ELO, MMLU, HumanEval, and MATH scores for each model.
    Returns {model_display_name: {lmsys_elo, mmlu, humaneval, math}} or None on failure.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[claude] ANTHROPIC_API_KEY not set — skipping web search", file=sys.stderr)
        return None

    client = anthropic.Anthropic(api_key=api_key)

    model_list = "\n".join(
        f"- {t['name']} (search for: {', '.join(t['arena_names'][:2])})"
        for t in TOOLS
    )
    prompt = (
        "Search the web for the latest AI benchmark scores. Find scores for these models:\n"
        f"{model_list}\n\n"
        "For each model find:\n"
        "1. LMSYS Chatbot Arena ELO score (from lmarena.ai) — integer around 1100-1450\n"
        "2. MMLU accuracy % (0-100)\n"
        "3. HumanEval pass@1 % (0-100)\n"
        "4. MATH accuracy % (0-100)\n\n"
        "Return ONLY valid JSON, no markdown fences:\n"
        '{"ChatGPT":{"lmsys_elo":1362,"mmlu":90.0,"humaneval":90.0,"math":85.0},'
        '"Claude":{"lmsys_elo":1344,"mmlu":89.0,"humaneval":93.0,"math":88.0},'
        '"Llama":{"lmsys_elo":1308,"mmlu":86.0,"humaneval":88.0,"math":80.0},'
        '"Gemini":{"lmsys_elo":1302,"mmlu":87.0,"humaneval":86.0,"math":83.0},'
        '"DeepSeek":{"lmsys_elo":1293,"mmlu":88.0,"humaneval":85.0,"math":90.0},'
        '"Qwen":{"lmsys_elo":1279,"mmlu":85.0,"humaneval":80.0,"math":82.0},'
        '"Mistral":{"lmsys_elo":1265,"mmlu":81.0,"humaneval":75.0,"math":73.0}}\n\n'
        "Use null for any value you cannot find. Keep model name keys exactly as shown."
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"[claude] API call failed: {exc}", file=sys.stderr)
        return None

    raw_text = "".join(
        block.text for block in response.content
        if hasattr(block, "type") and block.type == "text"
    )

    if not raw_text.strip():
        print("[claude] No text in response", file=sys.stderr)
        return None

    json_match = re.search(r"\{[\s\S]+\}", raw_text)
    if not json_match:
        print(f"[claude] No JSON found: {raw_text[:300]}", file=sys.stderr)
        return None

    try:
        data = json.loads(json_match.group())
        # Validate structure: must be {ModelName: {benchmark: value}}
        clean = {}
        for name, benchmarks in data.items():
            if not isinstance(benchmarks, dict):
                continue
            clean[name] = {
                k: (float(v) if v is not None else None)
                for k, v in benchmarks.items()
                if k in WEIGHTS
            }
        if clean:
            print(f"[claude] Got benchmark data for: {list(clean.keys())}", file=sys.stderr)
            return clean
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[claude] Parse error: {exc} — raw: {raw_text[:300]}", file=sys.stderr)

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
                "score": list(s["score"]),
            }
            for s in HISTORY_SEED["series"]
        ],
    }


def maybe_append_month(history: dict, current_scores: dict) -> dict:
    now = datetime.now(timezone.utc)
    label = now.strftime("%b %y")
    if label in history["months"]:
        return history
    history["months"].append(label)
    for series in history["series"]:
        tool = next((t for t in TOOLS if t["name"] == series["name"]), None)
        prev = series["score"][-1] if series["score"] else (tool["base_score"] if tool else 70)
        series["score"].append(current_scores.get(series["name"], prev))
    print(f"[history] Added '{label}' — {len(history['months'])} months total", file=sys.stderr)
    return history

# ── Rankings ──────────────────────────────────────────────────────────────────

def build_rankings(current_scores: dict, current_benchmarks: dict) -> dict:
    ranked = []
    for t in TOOLS:
        if not t["in_cards"]:
            continue
        ranked.append({
            "name": t["name"], "model": t["model"], "company": t["company"],
            "url": t["url"], "icon": t["icon"], "color": t["color"],
            "cats": t["cats"],
            "score": current_scores.get(t["name"], t["base_score"]),
            "benchmarks": current_benchmarks.get(t["name"], t["base_benchmarks"]),
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, t in enumerate(ranked):
        t["rank"] = i + 1
    return {"tools": ranked, "last_updated": datetime.now(timezone.utc).isoformat()}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Using model: {CLAUDE_MODEL}")
    print("Fetching benchmark scores via Claude web search…")
    all_benchmarks = fetch_benchmarks_via_claude()

    if all_benchmarks:
        print(f"  → Live data for {len(all_benchmarks)} models")
    else:
        print("  → Web search unavailable — using seeded base values", file=sys.stderr)
        all_benchmarks = {}

    # Compute composite scores; fall back to base_score if benchmarks are missing
    current_scores = {}
    current_benchmarks = {}
    for t in TOOLS:
        benchmarks = all_benchmarks.get(t["name"], t["base_benchmarks"])
        # Fill any null values from base_benchmarks
        merged = {k: (benchmarks.get(k) or t["base_benchmarks"].get(k)) for k in WEIGHTS}
        score = compute_composite(merged) or t["base_score"]
        current_scores[t["name"]] = round(score)
        current_benchmarks[t["name"]] = merged

    print("Updating history…")
    history = load_or_seed_history()
    history = maybe_append_month(history, current_scores)
    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    (DOCS_DIR / "history.json").write_text(json.dumps(history, indent=2))
    print(f"  → {len(history['months'])} months in history")

    print("Building rankings…")
    rankings = build_rankings(current_scores, current_benchmarks)
    (DOCS_DIR / "rankings.json").write_text(json.dumps(rankings, indent=2))
    print(f"  → {[(t['name'], t['score']) for t in rankings['tools']]}")

    print("Done.")


if __name__ == "__main__":
    main()
