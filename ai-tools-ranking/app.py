import asyncio
import json
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from seed_news import SEED_ARTICLES

app = FastAPI(title="AI Tools Ranking")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RANKINGS_FILE = os.path.join(DATA_DIR, "rankings.json")
NEWS_FILE = os.path.join(DATA_DIR, "news.json")

AI_TOOLS = [
    {
        "id": "chatgpt",
        "name": "ChatGPT",
        "company": "OpenAI",
        "description": "The world's most popular AI assistant with advanced reasoning and multimodal capabilities.",
        "url": "https://chat.openai.com",
        "icon": "🤖",
        "color": "#10a37f",
        "metrics": {"monthly_users": 180, "growth_rate": 15, "capability_score": 95, "community_score": 98},
    },
    {
        "id": "claude",
        "name": "Claude",
        "company": "Anthropic",
        "description": "Advanced AI known for safety, nuanced reasoning, and exceptional long-context understanding.",
        "url": "https://claude.ai",
        "icon": "✨",
        "color": "#cc785c",
        "metrics": {"monthly_users": 60, "growth_rate": 38, "capability_score": 97, "community_score": 86},
    },
    {
        "id": "gemini",
        "name": "Gemini",
        "company": "Google DeepMind",
        "description": "Google's flagship multimodal AI integrated across Search, Workspace, and Android.",
        "url": "https://gemini.google.com",
        "icon": "💎",
        "color": "#4285f4",
        "metrics": {"monthly_users": 150, "growth_rate": 26, "capability_score": 92, "community_score": 88},
    },
    {
        "id": "copilot",
        "name": "GitHub Copilot",
        "company": "Microsoft / GitHub",
        "description": "AI-powered pair programmer that suggests code, tests, and docs directly in your IDE.",
        "url": "https://github.com/features/copilot",
        "icon": "🚀",
        "color": "#6e5494",
        "metrics": {"monthly_users": 50, "growth_rate": 22, "capability_score": 90, "community_score": 93},
    },
    {
        "id": "midjourney",
        "name": "Midjourney",
        "company": "Midjourney Inc.",
        "description": "Leading AI image generation tool celebrated for its artistic quality and creative depth.",
        "url": "https://www.midjourney.com",
        "icon": "🎨",
        "color": "#f56565",
        "metrics": {"monthly_users": 20, "growth_rate": 11, "capability_score": 93, "community_score": 89},
    },
    {
        "id": "perplexity",
        "name": "Perplexity AI",
        "company": "Perplexity AI Inc.",
        "description": "Real-time AI search engine that synthesizes live web sources into cited, accurate answers.",
        "url": "https://www.perplexity.ai",
        "icon": "🔍",
        "color": "#20c997",
        "metrics": {"monthly_users": 15, "growth_rate": 48, "capability_score": 88, "community_score": 83},
    },
]

RSS_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Wired AI", "https://www.wired.com/feed/category/artificial-intelligence/latest/rss"),
    ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
]


def calculate_score(metrics: dict, jitter: float = 0.0) -> float:
    user_score = min(metrics["monthly_users"] / 2.0, 50)
    growth_score = min(metrics["growth_rate"] * 0.5, 25)
    capability_score = metrics["capability_score"] * 0.15
    community_score = metrics["community_score"] * 0.10
    base = user_score + growth_score + capability_score + community_score
    return round(base + jitter, 1)


def build_rankings() -> dict:
    tools_with_scores = []
    for tool in AI_TOOLS:
        jitter = random.uniform(-1.5, 1.5)
        entry = {k: v for k, v in tool.items() if k != "metrics"}
        entry["score"] = calculate_score(tool["metrics"], jitter)
        entry["metrics"] = tool["metrics"]
        tools_with_scores.append(entry)

    tools_with_scores.sort(key=lambda x: x["score"], reverse=True)
    for i, tool in enumerate(tools_with_scores):
        tool["rank"] = i + 1

    return {
        "tools": tools_with_scores,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def _text(el, *tags: str) -> str:
    for tag in tags:
        child = el.find(tag, _NS)
        if child is not None and child.text:
            return child.text.strip()
        child = el.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _strip_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw).strip()


def _parse_rss(xml_text: str, source_name: str) -> list:
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    # RSS 2.0
    items = root.findall(".//item")
    # Atom
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items[:6]:
        title = _text(item, "title", "atom:title")
        if not title:
            continue

        # Link: RSS uses <link>, Atom uses <link href=""> or <id>
        link = _text(item, "link", "atom:id")
        link_el = item.find("{http://www.w3.org/2005/Atom}link")
        if not link and link_el is not None:
            link = link_el.get("href", "")
        if not link:
            continue

        raw_summary = _text(item, "description", "content:encoded", "atom:summary", "atom:content")
        summary = _strip_html(raw_summary)[:280]
        published = _text(item, "pubDate", "dc:date", "atom:published", "atom:updated")

        articles.append({
            "title": _strip_html(title),
            "url": link,
            "summary": summary,
            "published": published,
            "source": source_name,
        })

    return articles


async def fetch_feed(session: aiohttp.ClientSession, source_name: str, url: str) -> list:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AIRankingBot/1.0)"}
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), headers=headers) as resp:
            content = await resp.text(errors="replace")
        return _parse_rss(content, source_name)
    except Exception as exc:
        print(f"[news] Failed to fetch {url}: {exc}")
        return []


async def fetch_all_news() -> dict:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_feed(session, name, url) for name, url in RSS_FEEDS]
        results = await asyncio.gather(*tasks)

    seen_urls: set = set()
    articles: list = []
    for batch in results:
        for a in batch:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                articles.append(a)

    using_seed = not articles
    if using_seed:
        print("[news] Live feeds unavailable — using seed articles.")
        articles = list(SEED_ARTICLES)

    return {
        "articles": articles[:24],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "seed" if using_seed else "live",
    }


def load_json(path: str) -> dict | None:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


async def daily_refresh() -> None:
    print(f"[scheduler] Daily refresh started at {datetime.now(timezone.utc).isoformat()}")
    rankings = build_rankings()
    save_json(RANKINGS_FILE, rankings)
    news = await fetch_all_news()
    save_json(NEWS_FILE, news)
    print("[scheduler] Daily refresh complete.")


@app.on_event("startup")
async def startup() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(RANKINGS_FILE):
        save_json(RANKINGS_FILE, build_rankings())

    if not os.path.exists(NEWS_FILE):
        news = await fetch_all_news()
        save_json(NEWS_FILE, news)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(daily_refresh, "cron", hour=0, minute=0, id="daily_refresh")
    scheduler.start()
    app.state.scheduler = scheduler


@app.on_event("shutdown")
async def shutdown() -> None:
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()


@app.get("/api/rankings")
async def get_rankings():
    data = load_json(RANKINGS_FILE) or build_rankings()
    return JSONResponse(content=data)


@app.get("/api/news")
async def get_news():
    data = load_json(NEWS_FILE)
    if data:
        return JSONResponse(content=data)
    news = await fetch_all_news()
    save_json(NEWS_FILE, news)
    return JSONResponse(content=news)


@app.post("/api/refresh")
async def manual_refresh():
    rankings = build_rankings()
    save_json(RANKINGS_FILE, rankings)
    news = await fetch_all_news()
    save_json(NEWS_FILE, news)
    return {"status": "ok", "refreshed_at": datetime.now(timezone.utc).isoformat()}


static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open(os.path.join(static_dir, "index.html")) as f:
        return HTMLResponse(content=f.read())
