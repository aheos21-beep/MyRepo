"""
Builds rankings.json from published Arena AI leaderboard data.

Data source: daily JSON snapshots of the Arena AI (LMSYS Chatbot Arena)
leaderboards, mirrored to GitHub by oolong-tea-2026/arena-ai-leaderboards.
No API key, no cost, no model inference — every number here is a published
Arena ELO rating that can be checked against the source.

This replaces an earlier approach that asked an LLM to search the web for
benchmark scores. That was abandoned because the scores it returned could not
be verified, and a plausible-but-wrong number was indistinguishable from a
correct one.

Note: the text board is dominated by multiple variants from the same vendor
(7 of the top 13 were Anthropic), so vendors are collapsed to their single
best-scoring entry before ranking.

Run locally with: python AI-Tools-Ranking/generate_data.py
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DOCS_DIR = Path(__file__).parent

REPO = "oolong-tea-2026/arena-ai-leaderboards"
BASE = f"https://raw.githubusercontent.com/{REPO}/main/data"
SOURCE_NAME = "Arena AI (LMSYS) leaderboards"

CARD_COUNT = 5

# Arena ELO is an unbounded rating, so it is displayed at 1/10 scale rather than
# squeezed into an arbitrary 0-100 window: 1509 -> 151. Nothing needs retuning as
# the boards drift.
#
# The displayed value is rounded to a whole number, so models a few ELO points
# apart can show the same figure (1490, 1486 and 1485 all read 149). That is
# intentional. Ranking always uses the full-precision ELO in `arena_elo`, never
# the rounded display value, so the order stays correct even when it looks tied.
SCALE_DIVISOR = 10

BOARDS = {
    "text":     {"label": "Overall",  "required": True},
    "code":     {"label": "Code",     "required": False},
    "vision":   {"label": "Vision",   "required": False},
    "document": {"label": "Document", "required": False},
}
RANK_BOARD = "text"
CHIP_BOARDS = ["code", "vision", "document"]

# Arena reports vendors; the site shows consumer-facing product brands.
VENDOR_META = {
    "Anthropic":     {"brand": "Claude",     "icon": "✨", "color": "#cc785c", "url": "https://claude.ai"},
    "OpenAI":        {"brand": "ChatGPT",    "icon": "🤖", "color": "#10a37f", "url": "https://chat.openai.com"},
    "Google":        {"brand": "Gemini",     "icon": "💎", "color": "#4285f4", "url": "https://gemini.google.com"},
    "Meta":          {"brand": "Meta AI",    "icon": "🦙", "color": "#0668e1", "url": "https://ai.meta.com"},
    "Moonshot":      {"brand": "Kimi",       "icon": "🌙", "color": "#7c3aed", "url": "https://kimi.moonshot.cn"},
    "DeepSeek":      {"brand": "DeepSeek",   "icon": "🌊", "color": "#6366f1", "url": "https://chat.deepseek.com"},
    "Alibaba":       {"brand": "Qwen",       "icon": "🔷", "color": "#f59e0b", "url": "https://qwen.ai"},
    "Mistral":       {"brand": "Mistral",    "icon": "🌀", "color": "#f7931e", "url": "https://mistral.ai"},
    "SpaceXAI":      {"brand": "Grok",       "icon": "🌑", "color": "#e879f9", "url": "https://grok.com"},
    "xAI":           {"brand": "Grok",       "icon": "🌑", "color": "#e879f9", "url": "https://grok.com"},
    "Baidu":         {"brand": "Ernie",      "icon": "🐻", "color": "#2932e1", "url": "https://ernie.baidu.com"},
    "Perplexity AI": {"brand": "Perplexity", "icon": "🔍", "color": "#20c997", "url": "https://perplexity.ai"},
    "Z.ai":          {"brand": "GLM",        "icon": "🔮", "color": "#9b59b6", "url": "https://z.ai"},
    "MiniMax":       {"brand": "MiniMax",    "icon": "⚡", "color": "#ef4444", "url": "https://minimax.io"},
    "Bytedance":     {"brand": "Doubao",     "icon": "🎵", "color": "#0ea5e9", "url": "https://doubao.com"},
    "Tencent":       {"brand": "Hunyuan",    "icon": "🐧", "color": "#14b8a6", "url": "https://hunyuan.tencent.com"},
    "Xiaomi":        {"brand": "MiMo",       "icon": "📱", "color": "#fb923c", "url": "https://xiaomi.com"},
    "IBM":           {"brand": "Granite",    "icon": "🧱", "color": "#64748b", "url": "https://ibm.com/granite"},
}
FALLBACK_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#1abc9c", "#9b59b6"]

# The mirror's earliest published snapshot. History is built from real snapshots
# only — months with no snapshot are skipped, and a model absent from a snapshot
# gets null rather than an interpolated value. Nothing here is ever estimated.
HISTORY_FIRST_SNAPSHOT = "2026-03-21"
HISTORY_START = (2026, 3)


# ── Fetching ───────────────────────────────────────────────────────────────────

def fetch_json(url: str, required: bool = True) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and not required:
            return None
        if required:
            raise
        print(f"[fetch] {url} -> HTTP {exc.code}", file=sys.stderr)
        return None
    except Exception as exc:
        if required:
            raise
        print(f"[fetch] {url} -> {exc}", file=sys.stderr)
        return None


def load_board(date: str, name: str, required: bool) -> list[dict]:
    data = fetch_json(f"{BASE}/{date}/{name}.json", required=required)
    return (data or {}).get("models", [])


# ── Shaping ────────────────────────────────────────────────────────────────────

def scaled(elo: float) -> int:
    """Arena ELO at 1/10 scale, rounded for display: 1509 -> 151."""
    return round(elo / SCALE_DIVISOR)


def best_per_vendor(rows: list[dict]) -> dict[str, dict]:
    """Collapse a board to each vendor's single highest-scoring entry."""
    best: dict[str, dict] = {}
    for row in rows:
        vendor, score = row.get("vendor"), row.get("score")
        if not vendor or score is None:
            continue
        if vendor not in best or score > best[vendor]["score"]:
            best[vendor] = row
    return best


def meta_for(vendor: str, idx: int = 0) -> dict:
    """
    Falls back to the raw Arena vendor string for an unmapped vendor. The card
    still renders and ranks correctly, but shows the bare vendor name and a
    generic icon. Add the vendor to VENDOR_META to give it proper branding.

    `url` is still emitted but unused — cards are not links. It is kept so the
    linking behaviour can be restored without reshaping VENDOR_META.
    """
    meta = VENDOR_META.get(vendor)
    if meta:
        return meta
    return {
        "brand": vendor,
        "icon": "🤖",
        "color": FALLBACK_COLORS[idx % len(FALLBACK_COLORS)],
        "url": "",
    }


# ── Rankings ───────────────────────────────────────────────────────────────────

def build_rankings(date: str) -> tuple[dict, list[str]]:
    boards = {
        name: best_per_vendor(load_board(date, name, cfg["required"]))
        for name, cfg in BOARDS.items()
    }

    rank_board = boards[RANK_BOARD]
    if not rank_board:
        sys.exit(f"FAILED: '{RANK_BOARD}' board empty for {date} — files left untouched.")

    ordered = sorted(rank_board.values(), key=lambda r: -r["score"])
    top = ordered[:CARD_COUNT]

    tools = []
    for idx, row in enumerate(top):
        vendor = row["vendor"]
        meta = meta_for(vendor, idx)

        chips = {
            name: scaled(entry["score"])
            for name in CHIP_BOARDS
            if (entry := boards.get(name, {}).get(vendor))
        }

        tools.append({
            "name":       meta["brand"],
            "model":      row["model"],
            "company":    vendor,
            "url":        meta["url"],
            "icon":       meta["icon"],
            "color":      meta["color"],
            "score":      scaled(row["score"]),
            "arena_elo":  row["score"],
            "arena_rank": row.get("rank"),
            "votes":      row.get("votes"),
            "benchmarks": chips,
            "rank":       idx + 1,
        })

    unmapped = [t["company"] for t in tools if t["company"] not in VENDOR_META]
    if unmapped:
        print(
            f"[branding] WARNING: ranked vendor(s) missing from VENDOR_META: "
            f"{', '.join(unmapped)} — showing the raw vendor name and a generic "
            f"icon. Add them to VENDOR_META.",
            file=sys.stderr,
        )

    rankings = {
        "tools": tools,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": date,
        "source": SOURCE_NAME,
        "source_url": f"https://github.com/{REPO}",
        "api_cost": "Fetch",
    }
    return rankings, [t["company"] for t in tools]


# ── History (rebuilt from real dated snapshots every run) ──────────────────────

def history_dates(today: datetime) -> list[tuple[str, str]]:
    """(snapshot_date, label) for the first of each month since the mirror began."""
    out = [(HISTORY_FIRST_SNAPSHOT, "Mar 26")]
    year, month = HISTORY_START
    month += 1
    while (year, month) <= (today.year, today.month):
        out.append((f"{year:04d}-{month:02d}-01",
                    datetime(year, month, 1).strftime("%b %y")))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def build_history(today: datetime, vendors: list[str]) -> dict:
    """
    Rebuilt from published snapshots on every run, so it is fully reproducible
    and self-healing. Months without a snapshot are skipped entirely; a vendor
    absent from a snapshot gets null, which the chart draws as a gap. No value
    here is ever estimated or interpolated.
    """
    months: list[str] = []
    series: dict[str, list] = {v: [] for v in vendors}

    for date, label in history_dates(today):
        rows = load_board(date, RANK_BOARD, required=False)
        if not rows:
            print(f"[history] no snapshot for {date} — month skipped", file=sys.stderr)
            continue
        best = best_per_vendor(rows)
        months.append(label)
        for vendor in vendors:
            entry = best.get(vendor)
            series[vendor].append(scaled(entry["score"]) if entry else None)

    if not months:
        sys.exit("FAILED: no historical snapshots resolved — files left untouched.")

    for vendor in vendors:
        gaps = sum(1 for v in series[vendor] if v is None)
        if gaps:
            print(f"[history] {vendor}: absent from {gaps}/{len(months)} snapshots "
                  f"— drawn as gaps, not filled in", file=sys.stderr)

    return {
        "months": months,
        "series": [
            {
                "name":  meta_for(vendor, idx)["brand"],
                "color": meta_for(vendor, idx)["color"],
                "score": series[vendor],
            }
            for idx, vendor in enumerate(vendors)
        ],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_NAME,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Source: {SOURCE_NAME}")
    print("Resolving latest snapshot…")
    latest = fetch_json(f"{BASE}/latest.json")
    date = latest.get("path") or latest.get("date")
    if not date:
        sys.exit("FAILED: latest.json had no usable date — files left untouched.")
    print(f"  → {date}")

    print("Building rankings…")
    rankings, vendors = build_rankings(date)
    for t in rankings["tools"]:
        chips = " ".join(f"{k}={v:.0f}" for k, v in t["benchmarks"].items())
        print(f"  {t['rank']}. {t['name']:<11} {t['model']:<28} "
              f"score {t['score']:>6}  elo {t['arena_elo']:.0f}  {chips}")

    print("Rebuilding history from dated snapshots…")
    history = build_history(datetime.now(timezone.utc), vendors)
    print(f"  → {len(history['months'])} months: {', '.join(history['months'])}")

    (DOCS_DIR / "rankings.json").write_text(json.dumps(rankings, indent=2) + "\n")
    (DOCS_DIR / "history.json").write_text(json.dumps(history, indent=2) + "\n")
    print("Done.")


if __name__ == "__main__":
    main()
