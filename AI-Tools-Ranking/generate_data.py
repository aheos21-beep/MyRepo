"""
Phase 1 — discovers the current top frontier AI models via web search.
Phase 2 — fetches benchmark scores for those models.
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
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
ELO_MIN = 1100
ELO_MAX = 1450
WEIGHTS = {"lmsys_elo": 0.40, "mmlu": 0.25, "humaneval": 0.20, "math": 0.15}
MAX_MODELS = 7    # total tracked
CARD_COUNT = 5    # top N shown in ranking cards

# Stable visual identity — survives model version changes
BRAND_META = {
    "ChatGPT":    {"icon": "🤖", "color": "#10a37f"},
    "Claude":     {"icon": "✨", "color": "#cc785c"},
    "Gemini":     {"icon": "💎", "color": "#4285f4"},
    "Llama":      {"icon": "🦙", "color": "#0668e1"},
    "DeepSeek":   {"icon": "🌊", "color": "#6366f1"},
    "Qwen":       {"icon": "🔷", "color": "#f59e0b"},
    "Mistral":    {"icon": "🌀", "color": "#f7931e"},
    "Grok":       {"icon": "🌑", "color": "#e879f9"},
    "Perplexity": {"icon": "🔍", "color": "#20c997"},
    "Command":    {"icon": "🔮", "color": "#9b59b6"},
    "Falcon":     {"icon": "🦅", "color": "#e67e22"},
    "Yi":         {"icon": "🌙", "color": "#3498db"},
}

FALLBACK_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#1abc9c", "#9b59b6", "#e67e22"]
FALLBACK_ICONS  = ["🤖", "🧠", "💡", "⚡", "🔮", "🌟", "💫"]

# Used only if Phase 1 discovery fails
FALLBACK_TOOLS = [
    {"name": "ChatGPT",  "model": "GPT-5",          "company": "OpenAI",      "url": "https://chat.openai.com",    "arena_names": ["gpt-5", "gpt-4o"]},
    {"name": "Claude",   "model": "Claude 4",        "company": "Anthropic",   "url": "https://claude.ai",          "arena_names": ["claude-4", "claude-opus-4"]},
    {"name": "Gemini",   "model": "Gemini Ultra 2",  "company": "Google",      "url": "https://gemini.google.com",  "arena_names": ["gemini-2-pro", "gemini-ultra"]},
    {"name": "DeepSeek", "model": "DeepSeek V3",     "company": "DeepSeek AI", "url": "https://chat.deepseek.com",  "arena_names": ["deepseek-v3"]},
    {"name": "Llama",    "model": "Llama 4",         "company": "Meta AI",     "url": "https://ai.meta.com/llama/", "arena_names": ["llama-4"]},
    {"name": "Qwen",     "model": "Qwen 2.5 Max",    "company": "Alibaba",     "url": "https://qwen.aliyun.com",    "arena_names": ["qwen2.5-72b"]},
    {"name": "Mistral",  "model": "Mistral Large 2", "company": "Mistral AI",  "url": "https://mistral.ai",         "arena_names": ["mistral-large-2"]},
]

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

# ── Helpers ────────────────────────────────────────────────────────────────────

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


def get_brand_meta(name: str, idx: int = 0) -> dict:
    meta = BRAND_META.get(name, {})
    return {
        "icon":  meta.get("icon",  FALLBACK_ICONS[idx % len(FALLBACK_ICONS)]),
        "color": meta.get("color", FALLBACK_COLORS[idx % len(FALLBACK_COLORS)]),
    }


def _call_tokens_cost(response) -> float:
    i = getattr(response.usage, "input_tokens", 0)
    o = getattr(response.usage, "output_tokens", 0)
    return (i * 1.00 + o * 5.00) / 1_000_000


# ── Phase 1: Discover top models ───────────────────────────────────────────────

def discover_top_models(client) -> tuple[list[dict] | None, float]:
    now_str = datetime.now(timezone.utc).strftime("%B %Y")
    prompt = (
        f"Search the web for the current top frontier AI chat/language models as of {now_str}.\n"
        "Check the LMSYS Chatbot Arena leaderboard (lmarena.ai) and recent AI benchmark news.\n\n"
        f"Return ONLY valid JSON — a list of exactly {MAX_MODELS} models ordered best to worst:\n"
        '[{"name":"ChatGPT","model":"GPT-5","company":"OpenAI","url":"https://chat.openai.com","arena_names":["gpt-5","gpt-4o"]}]\n\n'
        "Rules:\n"
        "- name: short stable brand name only (ChatGPT, Claude, Gemini, Llama, DeepSeek, Grok, Qwen, Mistral …)\n"
        "- model: specific current version being benchmarked (GPT-5, Claude 5, Gemini Ultra 2 …)\n"
        "- company: company name\n"
        "- url: main product URL\n"
        "- arena_names: 1-3 LMSYS Arena identifiers for this model (null if not listed)\n"
        "- Only include production models with known public benchmark scores"
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"[discover] API call failed: {exc}", file=sys.stderr)
        return None, 0.0

    cost = _call_tokens_cost(response)
    raw_text = "".join(
        b.text for b in response.content if hasattr(b, "type") and b.type == "text"
    )

    match = re.search(r"\[[\s\S]+\]", raw_text)
    if not match:
        print(f"[discover] No JSON array in response: {raw_text[:300]}", file=sys.stderr)
        return None, cost

    try:
        models = json.loads(match.group())
        clean = [
            {
                "name":        str(m.get("name", "")),
                "model":       str(m.get("model", m.get("name", ""))),
                "company":     str(m.get("company", "")),
                "url":         str(m.get("url", "")),
                "arena_names": m.get("arena_names") or [],
            }
            for m in models if isinstance(m, dict) and m.get("name")
        ]
        if clean:
            print(f"[discover] Found: {[m['name'] for m in clean]}", file=sys.stderr)
            return clean[:MAX_MODELS], cost
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[discover] Parse error: {exc}", file=sys.stderr)

    return None, cost


# ── Phase 2: Fetch benchmark scores ───────────────────────────────────────────

def fetch_benchmarks_via_claude(client, tools: list[dict]) -> tuple[dict | None, float]:
    model_list = "\n".join(
        f"- {t['name']} (search for: {', '.join((t.get('arena_names') or [t['name']])[:2])})"
        for t in tools
    )
    example = "{" + ",".join(
        f'"{t["name"]}":{{"lmsys_elo":1300,"mmlu":85.0,"humaneval":80.0,"math":75.0}}'
        for t in tools[:3]
    ) + ",...}"

    prompt = (
        "Search the web for the latest AI benchmark scores for these models:\n"
        f"{model_list}\n\n"
        "For each model find:\n"
        "1. LMSYS Chatbot Arena ELO (from lmarena.ai) — integer around 1100-1500\n"
        "2. MMLU accuracy % (0-100)\n"
        "3. HumanEval pass@1 % (0-100)\n"
        "4. MATH accuracy % (0-100)\n\n"
        f"Return ONLY valid JSON, no markdown fences:\n{example}\n\n"
        "Use null for any value you cannot find. Keep name keys exactly as shown."
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"[benchmarks] API call failed: {exc}", file=sys.stderr)
        return None, 0.0

    cost = _call_tokens_cost(response)
    raw_text = "".join(
        b.text for b in response.content if hasattr(b, "type") and b.type == "text"
    )

    if not raw_text.strip():
        print("[benchmarks] Empty response", file=sys.stderr)
        return None, cost

    match = re.search(r"\{[\s\S]+\}", raw_text)
    if not match:
        print(f"[benchmarks] No JSON object: {raw_text[:300]}", file=sys.stderr)
        return None, cost

    try:
        data = json.loads(match.group())
        clean = {
            name: {k: (float(v) if v is not None else None) for k, v in bm.items() if k in WEIGHTS}
            for name, bm in data.items() if isinstance(bm, dict)
        }
        if clean:
            print(f"[benchmarks] Got data for: {list(clean.keys())}", file=sys.stderr)
            return clean, cost
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[benchmarks] Parse error: {exc}", file=sys.stderr)

    return None, cost


# ── History ────────────────────────────────────────────────────────────────────

def load_or_seed_history() -> dict:
    path = DOCS_DIR / "history.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "months": list(HISTORY_SEED["months"]),
        "series": [
            {"name": s["name"], "color": BRAND_META.get(s["name"], {}).get("color", "#888"), "score": list(s["score"])}
            for s in HISTORY_SEED["series"]
        ],
    }


def maybe_append_month(history: dict, current_scores: dict, tools: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    label = now.strftime("%b %y")
    if label in history["months"]:
        return history

    # Mark the start of real data on the first automated append
    if "real_from" not in history:
        history["real_from"] = len(history["months"])

    history["months"].append(label)
    existing_names = {s["name"] for s in history["series"]}

    for series in history["series"]:
        prev = series["score"][-1] if series["score"] else 70
        series["score"].append(current_scores.get(series["name"], prev))

    # Add newly discovered models not yet in history
    pad = len(history["months"]) - 1
    for t in tools:
        if t["name"] not in existing_names:
            meta = get_brand_meta(t["name"])
            score = current_scores.get(t["name"], 70)
            history["series"].append({
                "name":  t["name"],
                "color": meta["color"],
                "score": [score] * pad + [score],
            })
            print(f"[history] New model added: {t['name']}", file=sys.stderr)

    print(f"[history] Added '{label}' — {len(history['months'])} months total", file=sys.stderr)
    return history


def sync_history_meta(history: dict, tools: list[dict], current_scores: dict) -> None:
    """Keep color and in_cards up to date in history series."""
    tool_lookup = {t["name"]: t for t in tools}
    top_names = {
        name for name, _ in
        sorted(current_scores.items(), key=lambda x: x[1], reverse=True)[:CARD_COUNT]
    }
    for series in history["series"]:
        meta = get_brand_meta(series["name"])
        series["color"]    = tool_lookup.get(series["name"], {}).get("color", meta["color"]) or meta["color"]
        series["in_cards"] = series["name"] in top_names


# ── Rankings ───────────────────────────────────────────────────────────────────

def build_rankings(tools: list[dict], current_scores: dict, current_benchmarks: dict) -> dict:
    ranked = []
    for idx, t in enumerate(tools):
        meta = get_brand_meta(t["name"], idx)
        ranked.append({
            "name":       t["name"],
            "model":      t["model"],
            "company":    t["company"],
            "url":        t["url"],
            "icon":       meta["icon"],
            "color":      meta["color"],
            "score":      current_scores.get(t["name"], 70),
            "benchmarks": current_benchmarks.get(t["name"], {}),
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, t in enumerate(ranked):
        t["rank"] = i + 1

    return {
        "tools": ranked[:CARD_COUNT],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[main] ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    total_cost = 0.0

    print(f"Using model: {CLAUDE_MODEL}")

    # Phase 1
    print("Phase 1: Discovering top frontier models…")
    discovered, cost1 = discover_top_models(client)
    total_cost += cost1
    if discovered:
        tools = discovered
        print(f"  → {len(tools)} models discovered — phase cost ${cost1:.4f}")
    else:
        tools = FALLBACK_TOOLS
        print("  → Discovery failed — using fallback list", file=sys.stderr)

    # Phase 2
    print("Phase 2: Fetching benchmark scores…")
    all_benchmarks, cost2 = fetch_benchmarks_via_claude(client, tools)
    total_cost += cost2
    if all_benchmarks:
        print(f"  → Scores for {len(all_benchmarks)} models — phase cost ${cost2:.4f}")
    else:
        print("  → Benchmark fetch failed — defaulting scores to 70", file=sys.stderr)
        all_benchmarks = {}

    api_cost_str = f"${total_cost:.2f}"

    # Compute composite scores
    current_scores, current_benchmarks = {}, {}
    for t in tools:
        raw = all_benchmarks.get(t["name"], {})
        merged = {k: raw.get(k) for k in WEIGHTS}
        score = compute_composite({k: v for k, v in merged.items() if v is not None}) or 70
        current_scores[t["name"]] = round(score)
        current_benchmarks[t["name"]] = merged

    # History
    print("Updating history…")
    history = load_or_seed_history()
    sync_history_meta(history, tools, current_scores)
    history = maybe_append_month(history, current_scores, tools)
    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    (DOCS_DIR / "history.json").write_text(json.dumps(history, indent=2))
    print(f"  → {len(history['months'])} months in history")

    # Rankings
    print("Building rankings…")
    rankings = build_rankings(tools, current_scores, current_benchmarks)
    rankings["api_cost"] = api_cost_str
    (DOCS_DIR / "rankings.json").write_text(json.dumps(rankings, indent=2))
    print(f"  → {[(t['name'], t['score']) for t in rankings['tools']]}")
    print(f"Total cost: {api_cost_str}")
    print("Done.")


if __name__ == "__main__":
    main()
