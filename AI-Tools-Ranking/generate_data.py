"""
Fetches AI model rankings via the Claude API and maintains history.json.

Each phase is split into two calls:
  research  — web search enabled, free-form prose output
  extract   — no tools, structured output (json_schema) → guaranteed valid JSON

This split exists because structured outputs are incompatible with citations,
which web search always produces. Doing both in one call is what previously
caused silent failures: when the search came up empty the model replied with a
prose apology, the JSON regex found nothing, and every score silently collapsed
to a hardcoded default that was then committed over good data.

Rules this script now enforces:
  - Never invent a benchmark number. Missing data carries forward the previous
    run's real value, or the model is dropped.
  - If a run produces no real data at all, exit non-zero so the Actions run goes
    red and the existing good data is left untouched.

Runs bi-monthly (1st and 15th) via GitHub Actions.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

DOCS_DIR = Path(__file__).parent

# Research is the quality-critical step; extraction is mechanical and cheap.
RESEARCH_MODEL = os.getenv("RESEARCH_MODEL", "claude-opus-4-8")
EXTRACT_MODEL  = os.getenv("EXTRACT_MODEL",  "claude-haiku-4-5")

# $ per 1M tokens (input, output)
PRICING = {
    "claude-fable-5":    (10.00, 50.00),
    "claude-opus-4-8":   (5.00,  25.00),
    "claude-opus-4-7":   (5.00,  25.00),
    "claude-opus-4-6":   (5.00,  25.00),
    "claude-sonnet-5":   (3.00,  15.00),
    "claude-sonnet-4-6": (3.00,  15.00),
    "claude-haiku-4-5":  (1.00,   5.00),
}

# Only these models support the dynamic-filtering web search tool.
DYNAMIC_SEARCH_MODELS = {
    "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-opus-4-6", "claude-sonnet-5", "claude-sonnet-4-6",
}

ELO_MIN, ELO_MAX = 1100, 1500
WEIGHTS = {"lmsys_elo": 0.40, "mmlu": 0.25, "humaneval": 0.20, "math": 0.15}
MAX_MODELS = 7
CARD_COUNT = 5

# Stable brand identity — survives model version changes.
BRAND_META = {
    "ChatGPT":    {"icon": "🤖", "color": "#10a37f", "cats": ["💻 Coding", "📋 Instructions"]},
    "Claude":     {"icon": "✨", "color": "#cc785c", "cats": ["🧠 Reasoning", "✍️ Creative Writing"]},
    "Gemini":     {"icon": "💎", "color": "#4285f4", "cats": ["🔢 Math", "🌐 Multilingual"]},
    "Llama":      {"icon": "🦙", "color": "#0668e1", "cats": ["💻 Coding", "🔢 Math"]},
    "DeepSeek":   {"icon": "🌊", "color": "#6366f1", "cats": ["🔢 Math", "💻 Coding"]},
    "Qwen":       {"icon": "🔷", "color": "#f59e0b", "cats": ["🔢 Math", "🌐 Multilingual"]},
    "Mistral":    {"icon": "🌀", "color": "#f7931e", "cats": ["💻 Coding", "🌐 Multilingual"]},
    "Grok":       {"icon": "🌑", "color": "#e879f9", "cats": ["🧠 Reasoning", "💻 Coding"]},
    "Perplexity": {"icon": "🔍", "color": "#20c997", "cats": ["🌐 Search", "📋 Instructions"]},
    "Command":    {"icon": "🔮", "color": "#9b59b6", "cats": ["📋 Instructions", "🌐 Multilingual"]},
    "Falcon":     {"icon": "🦅", "color": "#e67e22", "cats": ["💻 Coding", "🔢 Math"]},
    "Yi":         {"icon": "🌙", "color": "#3498db", "cats": ["🧠 Reasoning", "🌐 Multilingual"]},
}
FALLBACK_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#1abc9c", "#9b59b6", "#e67e22"]
FALLBACK_ICONS  = ["🤖", "🧠", "💡", "⚡", "🔮", "🌟", "💫"]

NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}

DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "models": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "model":       {"type": "string"},
                    "company":     {"type": "string"},
                    "url":         {"type": "string"},
                    "arena_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "model", "company", "url", "arena_names"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["models"],
    "additionalProperties": False,
}

BENCHMARK_SCHEMA = {
    "type": "object",
    "properties": {
        "models": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":      {"type": "string"},
                    "lmsys_elo": NULLABLE_NUMBER,
                    "mmlu":      NULLABLE_NUMBER,
                    "humaneval": NULLABLE_NUMBER,
                    "math":      NULLABLE_NUMBER,
                },
                "required": ["name", "lmsys_elo", "mmlu", "humaneval", "math"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["models"],
    "additionalProperties": False,
}

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

# ── Cost tracking ──────────────────────────────────────────────────────────────

class Cost:
    def __init__(self):
        self.total = 0.0

    def add(self, model: str, response) -> float:
        rate_in, rate_out = PRICING.get(model, (5.00, 25.00))
        usage = response.usage
        spend = (
            getattr(usage, "input_tokens", 0)  * rate_in +
            getattr(usage, "output_tokens", 0) * rate_out
        ) / 1_000_000
        self.total += spend
        return spend


# ── API helpers ────────────────────────────────────────────────────────────────

def web_search_tool(model: str, max_uses: int) -> dict:
    tool_type = ("web_search_20260209" if model in DYNAMIC_SEARCH_MODELS
                 else "web_search_20250305")
    return {"type": tool_type, "name": "web_search", "max_uses": max_uses}


def research(client, cost: Cost, prompt: str, max_uses: int, label: str) -> str:
    """Web-search call. Free-form output — prose is fine, it feeds the extractor."""
    response = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=8000,
        tools=[web_search_tool(RESEARCH_MODEL, max_uses)],
        messages=[{"role": "user", "content": prompt}],
    )
    spend = cost.add(RESEARCH_MODEL, response)
    text = "".join(b.text for b in response.content
                   if getattr(b, "type", None) == "text")
    print(f"[{label}] research done — ${spend:.4f}, {len(text)} chars", file=sys.stderr)
    if response.stop_reason == "max_tokens":
        print(f"[{label}] WARNING: hit max_tokens, findings may be truncated", file=sys.stderr)
    return text


def extract(client, cost: Cost, text: str, schema: dict, instruction: str, label: str) -> dict:
    """
    No tools + json_schema → the response is guaranteed to parse.
    A failed research pass yields nulls here rather than an unparseable apology.
    """
    response = client.messages.create(
        model=EXTRACT_MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"{instruction}\n\nResearch notes:\n---\n{text}\n---",
        }],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    spend = cost.add(EXTRACT_MODEL, response)
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"{label}: extraction truncated — raise max_tokens")
    payload = next(b.text for b in response.content
                   if getattr(b, "type", None) == "text")
    print(f"[{label}] extract done — ${spend:.4f}", file=sys.stderr)
    return json.loads(payload)


# ── Phase 1: discover current frontier models ──────────────────────────────────

def discover_models(client, cost: Cost) -> list[dict]:
    today = datetime.now(timezone.utc).strftime("%B %Y")
    notes = research(
        client, cost, max_uses=6, label="discover",
        prompt=(
            f"It is {today}. Search the web and identify the top {MAX_MODELS} frontier "
            "AI chat/language models that are currently ranked highest.\n\n"
            "Check the LMSYS Chatbot Arena leaderboard (lmarena.ai) and recent benchmark coverage.\n\n"
            "CRITICAL: only include a model if you can actually find published benchmark "
            "results for it (Arena ELO, MMLU, HumanEval, or MATH). A brand-new release with "
            "no published scores is useless here — in that case list the most recent version "
            "of that family that DOES have published scores instead.\n\n"
            "For each model report: the short brand name (ChatGPT, Claude, Gemini, Llama, "
            "DeepSeek, Grok, Qwen, Mistral…), the specific version that has published scores, "
            "the company, the product URL, and the identifiers it appears under on the Arena "
            "leaderboard.\n\n"
            "List at most one entry per brand — the strongest one."
        ),
    )

    data = extract(
        client, cost, notes, DISCOVERY_SCHEMA, label="discover",
        instruction=(
            f"From these research notes, list up to {MAX_MODELS} frontier AI models, "
            "strongest first.\n"
            "- name: short brand name only (e.g. 'Claude', not 'Claude Opus 5')\n"
            "- model: the specific version that has published benchmark scores\n"
            "- arena_names: LMSYS Arena identifiers mentioned, or an empty list\n"
            "Include a brand at most once. Include only models actually named in the notes."
        ),
    )

    seen, models = set(), []
    for m in data.get("models", []):
        name = (m.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        models.append({
            "name":        name,
            "model":       (m.get("model") or name).strip(),
            "company":     (m.get("company") or "").strip(),
            "url":         (m.get("url") or "").strip(),
            "arena_names": m.get("arena_names") or [],
        })

    if not models:
        raise RuntimeError("discovery returned no models")
    print(f"[discover] {[m['name'] for m in models]}", file=sys.stderr)
    return models[:MAX_MODELS]


# ── Phase 2: fetch benchmark scores ────────────────────────────────────────────

def fetch_benchmarks(client, cost: Cost, models: list[dict]) -> dict:
    listing = "\n".join(
        f"- {m['name']} ({m['model']})" +
        (f" — Arena: {', '.join(m['arena_names'][:3])}" if m["arena_names"] else "")
        for m in models
    )
    notes = research(
        client, cost, max_uses=12, label="benchmarks",
        prompt=(
            "Search the web for published benchmark scores for these models:\n"
            f"{listing}\n\n"
            "For each, find whichever of these are published:\n"
            "1. LMSYS Chatbot Arena ELO (lmarena.ai) — integer, roughly 1100-1500\n"
            "2. MMLU accuracy %\n"
            "3. HumanEval pass@1 %\n"
            "4. MATH accuracy %\n\n"
            "Report the number and where you found it. If a score is not published for a "
            "model, say so explicitly for that model and benchmark — do not estimate, "
            "interpolate, or carry a number over from a different model version. "
            "Partial results are useful; report everything you did find."
        ),
    )

    data = extract(
        client, cost, notes, BENCHMARK_SCHEMA, label="benchmarks",
        instruction=(
            "Extract the benchmark scores stated in these research notes.\n"
            "Include one entry for each of these models: "
            f"{', '.join(m['name'] for m in models)}.\n"
            "Use null for any score the notes do not explicitly state. "
            "Never estimate or infer a value — null is the correct answer when the notes "
            "do not give a number. Copy numbers exactly as written."
        ),
    )

    scores = {}
    for entry in data.get("models", []):
        name = (entry.get("name") or "").strip()
        if name:
            scores[name] = {k: entry.get(k) for k in WEIGHTS}

    found = sum(1 for b in scores.values() for v in b.values() if v is not None)
    print(f"[benchmarks] {found} real datapoints across {len(scores)} models", file=sys.stderr)
    return scores


# ── Scoring ────────────────────────────────────────────────────────────────────

def normalize_elo(elo: float) -> float:
    return max(0.0, min(100.0, (elo - ELO_MIN) / (ELO_MAX - ELO_MIN) * 100.0))


def compute_composite(benchmarks: dict) -> float | None:
    """Weighted mean over whichever benchmarks are present; weight redistributes."""
    total, weight_sum = 0.0, 0.0
    for key, weight in WEIGHTS.items():
        val = benchmarks.get(key)
        if val is None:
            continue
        total += (normalize_elo(val) if key == "lmsys_elo" else float(val)) * weight
        weight_sum += weight
    return round(total / weight_sum, 1) if weight_sum else None


def load_previous() -> dict:
    """Previous run's real values, for carry-forward. Never invented."""
    path = DOCS_DIR / "rankings.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return {
        t["name"]: {"benchmarks": t.get("benchmarks", {}), "score": t.get("score")}
        for t in data.get("tools", [])
        if t.get("name")
    }


def resolve_scores(models: list[dict], fetched: dict, previous: dict) -> tuple[dict, dict, dict]:
    """
    Merge fetched values with carry-forward. Returns (scores, benchmarks, provenance).
    A model with no fetched and no previous data is dropped entirely.
    """
    scores, benchmarks, provenance = {}, {}, {}

    for m in models:
        name = m["name"]
        fresh = fetched.get(name, {})
        prior = previous.get(name, {}).get("benchmarks", {})

        merged, carried, live = {}, 0, 0
        for key in WEIGHTS:
            if fresh.get(key) is not None:
                merged[key] = fresh[key]
                live += 1
            elif prior.get(key) is not None:
                merged[key] = prior[key]
                carried += 1
            else:
                merged[key] = None

        score = compute_composite(merged)
        if score is None:
            print(f"[scores] dropping {name} — no data, current or previous", file=sys.stderr)
            continue

        scores[name] = round(score)
        benchmarks[name] = merged
        provenance[name] = {"live": live, "carried": carried}

    return scores, benchmarks, provenance


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
            {"name": s["name"],
             "color": BRAND_META.get(s["name"], {}).get("color", "#888"),
             "score": list(s["score"])}
            for s in HISTORY_SEED["series"]
        ],
    }


def sync_history_meta(history: dict, scores: dict) -> None:
    top = {n for n, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:CARD_COUNT]}
    for series in history["series"]:
        meta = BRAND_META.get(series["name"], {})
        series["color"] = meta.get("color", series.get("color", "#888"))
        series["in_cards"] = series["name"] in top


def maybe_append_month(history: dict, scores: dict) -> dict:
    label = datetime.now(timezone.utc).strftime("%b %y")
    if label in history["months"]:
        return history

    if "real_from" not in history:
        history["real_from"] = len(history["months"])

    history["months"].append(label)
    known = {s["name"] for s in history["series"]}

    for series in history["series"]:
        prev = series["score"][-1] if series["score"] else 70
        series["score"].append(scores.get(series["name"], prev))

    pad = len(history["months"]) - 1
    for name, score in scores.items():
        if name not in known:
            history["series"].append({
                "name":  name,
                "color": BRAND_META.get(name, {}).get("color", "#888"),
                "score": [score] * pad + [score],
            })
            print(f"[history] new model: {name}", file=sys.stderr)

    print(f"[history] appended '{label}' — {len(history['months'])} months", file=sys.stderr)
    return history


# ── Rankings ───────────────────────────────────────────────────────────────────

def build_rankings(models: list[dict], scores: dict, benchmarks: dict) -> dict:
    ranked = []
    for idx, m in enumerate(models):
        name = m["name"]
        if name not in scores:
            continue
        meta = BRAND_META.get(name, {})
        ranked.append({
            "name":       name,
            "model":      m["model"],
            "company":    m["company"],
            "url":        m["url"],
            "icon":       meta.get("icon",  FALLBACK_ICONS[idx % len(FALLBACK_ICONS)]),
            "color":      meta.get("color", FALLBACK_COLORS[idx % len(FALLBACK_COLORS)]),
            "cats":       meta.get("cats", []),
            "score":      scores[name],
            "benchmarks": benchmarks[name],
        })

    ranked.sort(key=lambda t: t["score"], reverse=True)
    for i, t in enumerate(ranked):
        t["rank"] = i + 1
    return {"tools": ranked[:CARD_COUNT]}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic()
    cost = Cost()

    print(f"Research model:   {RESEARCH_MODEL}")
    print(f"Extraction model: {EXTRACT_MODEL}")

    print("Phase 1: discovering frontier models…")
    models = discover_models(client, cost)
    print(f"  → {[m['name'] + ' (' + m['model'] + ')' for m in models]}")

    print("Phase 2: fetching benchmark scores…")
    fetched = fetch_benchmarks(client, cost, models)

    live_total = sum(1 for b in fetched.values() for v in b.values() if v is not None)
    if live_total == 0:
        # Refuse to overwrite good data with nothing. Turns the Actions run red.
        sys.exit(
            "FAILED: benchmark research produced zero real datapoints. "
            "Existing rankings.json and history.json left untouched."
        )

    previous = load_previous()
    scores, benchmarks, provenance = resolve_scores(models, fetched, previous)
    if not scores:
        sys.exit("FAILED: no model had usable data. Existing files left untouched.")

    carried_total = sum(p["carried"] for p in provenance.values())
    print(f"  → {live_total} live datapoints, {carried_total} carried forward")

    print("Updating history…")
    history = load_or_seed_history()
    sync_history_meta(history, scores)
    history = maybe_append_month(history, scores)
    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    (DOCS_DIR / "history.json").write_text(json.dumps(history, indent=2))
    print(f"  → {len(history['months'])} months in history")

    print("Building rankings…")
    rankings = build_rankings(models, scores, benchmarks)
    rankings["last_updated"] = datetime.now(timezone.utc).isoformat()
    rankings["api_cost"] = f"${cost.total:.2f}"
    rankings["data_quality"] = {
        "live_datapoints":    live_total,
        "carried_datapoints": carried_total,
        "models_ranked":      len(rankings["tools"]),
    }
    (DOCS_DIR / "rankings.json").write_text(json.dumps(rankings, indent=2))

    print(f"  → {[(t['name'], t['score']) for t in rankings['tools']]}")
    print(f"Total cost: ${cost.total:.2f}")
    print("Done.")


if __name__ == "__main__":
    main()
