"""
Generates docs/rankings.json and docs/news.json.
Runs daily via GitHub Actions; also usable locally.
"""
import asyncio
import json
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

DOCS_DIR = Path(__file__).parent

# ── Tool definitions ──────────────────────────────────────────────────────────

AI_TOOLS = [
    {
        "id": "chatgpt",
        "name": "ChatGPT",
        "version": "GPT-5",
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
        "version": "Claude 4",
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
        "version": "Gemini Ultra 2",
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
        "version": "Copilot Pro+",
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
        "version": "v7",
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
        "version": "Perplexity Pro",
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
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
]

SEED_ARTICLES = [
    {"title": "OpenAI Launches GPT-5 with Breakthrough Reasoning Capabilities", "url": "https://techcrunch.com/category/artificial-intelligence/", "summary": "OpenAI's latest model demonstrates significant leaps in multi-step reasoning, mathematics, and code generation — passing the bar exam in the 90th percentile.", "published": "Mon, 02 Jun 2026 08:00:00 +0000", "source": "TechCrunch AI"},
    {"title": "Anthropic's Claude 4 Sets New Benchmark on Long-Context Understanding", "url": "https://venturebeat.com/category/ai/", "summary": "Claude 4 achieves state-of-the-art results on MMLU and HumanEval, with a 1M-token context window enabling entire codebases to be analyzed at once.", "published": "Sun, 01 Jun 2026 10:30:00 +0000", "source": "VentureBeat AI"},
    {"title": "Google DeepMind Releases Gemini Ultra 2 for Enterprise Customers", "url": "https://www.theverge.com/ai-artificial-intelligence", "summary": "Gemini Ultra 2 brings native multimodal reasoning across text, images, video, and audio in a single unified model, now available via Google Cloud.", "published": "Sat, 31 May 2026 14:00:00 +0000", "source": "The Verge AI"},
    {"title": "GitHub Copilot Now Generates Full Pull Requests Autonomously", "url": "https://www.technologyreview.com/topic/artificial-intelligence/", "summary": "Microsoft's Copilot has evolved into a fully agentic coding assistant, capable of cloning repos, writing code, running tests, and submitting PRs.", "published": "Fri, 30 May 2026 09:15:00 +0000", "source": "MIT Technology Review"},
    {"title": "Midjourney v7 Introduces Consistent Characters Across Scenes", "url": "https://www.wired.com/tag/artificial-intelligence/", "summary": "Midjourney's new model maintains consistent character appearances across multiple generated images — a breakthrough for animation studios and game developers.", "published": "Thu, 29 May 2026 11:45:00 +0000", "source": "Wired AI"},
    {"title": "Perplexity AI Hits 50 Million Monthly Active Users", "url": "https://arstechnica.com/ai/", "summary": "Perplexity's AI-native search engine has reached 50M MAU, driven by its ability to cite sources, answer follow-ups, and integrate with enterprise knowledge bases.", "published": "Wed, 28 May 2026 16:00:00 +0000", "source": "Ars Technica"},
    {"title": "The EU AI Act Enters Full Enforcement — What It Means for Developers", "url": "https://techcrunch.com/category/artificial-intelligence/", "summary": "With the EU AI Act now in full force, developers of high-risk AI systems must document training data, implement human oversight, and register with national authorities.", "published": "Tue, 27 May 2026 08:30:00 +0000", "source": "TechCrunch AI"},
    {"title": "Meta Releases Llama 4 Under Open License, Shaking the AI Market", "url": "https://venturebeat.com/category/ai/", "summary": "Meta's Llama 4 series includes models up to 400B parameters, released under a commercial-friendly license that lets companies fine-tune without royalties.", "published": "Mon, 26 May 2026 12:00:00 +0000", "source": "VentureBeat AI"},
    {"title": "AI Agents Are Taking Over Software Development Workflows", "url": "https://www.technologyreview.com/topic/artificial-intelligence/", "summary": "A new wave of autonomous AI agents can handle entire development sprints — from requirements to deployment — with engineers shifting into reviewer roles.", "published": "Sun, 25 May 2026 09:00:00 +0000", "source": "MIT Technology Review"},
    {"title": "Apple Intelligence Gains On-Device LLM With Private Cloud Compute", "url": "https://www.theverge.com/ai-artificial-intelligence", "summary": "Apple's latest AI update routes sensitive queries to on-device models and only escalates to Private Cloud Compute for complex tasks, without exposing data.", "published": "Sat, 24 May 2026 15:30:00 +0000", "source": "The Verge AI"},
    {"title": "Researchers Achieve 1000x Speedup in AI Inference via New Architecture", "url": "https://www.wired.com/tag/artificial-intelligence/", "summary": "A Stanford and MIT collaboration introduces Sparse Mixture-of-Experts routing that activates only 0.1% of parameters per token, dramatically cutting inference cost.", "published": "Fri, 23 May 2026 10:00:00 +0000", "source": "Wired AI"},
    {"title": "AI-Powered Drug Discovery Cuts Clinical Trial Time by 40%", "url": "https://arstechnica.com/ai/", "summary": "Pharmaceutical companies using AI-driven molecule screening have reduced average drug development timelines from 12 years to under 7.", "published": "Thu, 22 May 2026 13:00:00 +0000", "source": "Ars Technica"},
    {"title": "OpenAI's Operator Agent Can Now Shop, Book Travel, and File Taxes", "url": "https://techcrunch.com/category/artificial-intelligence/", "summary": "OpenAI expanded its Operator agentic system: it can navigate websites, fill forms, verify identity, and complete multi-step transactions autonomously.", "published": "Wed, 21 May 2026 11:00:00 +0000", "source": "TechCrunch AI"},
    {"title": "Video Generation AI Can Now Produce Feature-Length Films", "url": "https://venturebeat.com/category/ai/", "summary": "Sora and competing systems have crossed a new threshold: they can produce coherent, hour-long video narratives with consistent characters and plots.", "published": "Tue, 20 May 2026 14:00:00 +0000", "source": "VentureBeat AI"},
    {"title": "Nvidia Announces Blackwell Ultra GPUs — 10x AI Training Throughput", "url": "https://www.technologyreview.com/topic/artificial-intelligence/", "summary": "Nvidia's Blackwell Ultra chips deliver 10 petaflops of AI training compute per GPU, enabling trillion-parameter models to train in days instead of months.", "published": "Mon, 19 May 2026 09:30:00 +0000", "source": "MIT Technology Review"},
    {"title": "Microsoft Copilot+ PCs Sell Out as AI PC Wave Hits Mainstream", "url": "https://www.theverge.com/ai-artificial-intelligence", "summary": "AI-native PCs with dedicated neural processing units have hit mainstream adoption, with Microsoft's Copilot+ lineup exceeding one million units in the first week.", "published": "Sun, 18 May 2026 17:00:00 +0000", "source": "The Verge AI"},
    {"title": "AI Models Are Now Writing 40% of All New Code on GitHub", "url": "https://www.wired.com/tag/artificial-intelligence/", "summary": "GitHub's annual Octoverse report reveals AI-generated code now accounts for 40% of all committed code, jumping from 26% the year prior.", "published": "Sat, 17 May 2026 12:00:00 +0000", "source": "Wired AI"},
    {"title": "The Hidden Environmental Cost of Training Large Language Models", "url": "https://arstechnica.com/ai/", "summary": "A new study reveals training a frontier LLM emits as much CO2 as 300 transatlantic flights, prompting calls for greener compute infrastructure.", "published": "Fri, 16 May 2026 10:30:00 +0000", "source": "Ars Technica"},
    {"title": "Gemini Live Can Now Hold Real-Time Voice Conversations in 50 Languages", "url": "https://techcrunch.com/category/artificial-intelligence/", "summary": "Google's Gemini Live now supports real-time, low-latency voice conversations in 50 languages with near-native fluency, integrating with Android and Google Home.", "published": "Thu, 15 May 2026 08:00:00 +0000", "source": "TechCrunch AI"},
    {"title": "Anthropic Publishes Safety Blueprint for Agentic AI Systems", "url": "https://venturebeat.com/category/ai/", "summary": "Anthropic's paper outlines principles for safe autonomous AI agents: minimal footprint, reversible actions, human escalation, and auditable decision trails.", "published": "Wed, 14 May 2026 14:00:00 +0000", "source": "VentureBeat AI"},
]

# ── Rankings ──────────────────────────────────────────────────────────────────

def build_rankings() -> dict:
    tools = []
    for tool in AI_TOOLS:
        m = tool["metrics"]
        jitter = random.uniform(-1.5, 1.5)
        score = round(
            m["capability_score"] * 0.60          # max 60 pts
            + min(m["growth_rate"] * 0.60, 30)    # max 30 pts
            + min(m["monthly_users"] * 0.10, 10)  # max 10 pts
            + jitter,
            1,
        )
        entry = {k: v for k, v in tool.items() if k != "metrics"}
        entry["score"] = score
        entry["metrics"] = m
        tools.append(entry)

    tools.sort(key=lambda x: x["score"], reverse=True)
    for i, t in enumerate(tools):
        t["rank"] = i + 1

    return {"tools": tools, "last_updated": datetime.now(timezone.utc).isoformat()}

# ── News ──────────────────────────────────────────────────────────────────────

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def _el_text(el, *tags):
    for tag in tags:
        child = el.find(tag, _NS) or el.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _strip_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw).strip()


def _parse_rss(xml_text: str, source_name: str) -> list:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    articles = []
    for item in items[:6]:
        title = _strip_html(_el_text(item, "title", "atom:title"))
        link = _el_text(item, "link", "atom:id")
        link_el = item.find("{http://www.w3.org/2005/Atom}link")
        if not link and link_el is not None:
            link = link_el.get("href", "")
        if not title or not link:
            continue
        raw_summary = _el_text(item, "description", "content:encoded", "atom:summary", "atom:content")
        summary = _strip_html(raw_summary)[:280]
        published = _el_text(item, "pubDate", "dc:date", "atom:published", "atom:updated")
        articles.append({"title": title, "url": link, "summary": summary, "published": published, "source": source_name})
    return articles


async def fetch_feed(session: aiohttp.ClientSession, name: str, url: str) -> list:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AIRankingBot/1.0)"}
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=headers) as resp:
            content = await resp.text(errors="replace")
        return _parse_rss(content, name)
    except Exception as exc:
        print(f"[news] {name}: {exc}", file=sys.stderr)
        return []


async def build_news() -> dict:
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[fetch_feed(session, n, u) for n, u in RSS_FEEDS])

    seen: set = set()
    articles: list = []
    for batch in results:
        for a in batch:
            if a["url"] not in seen:
                seen.add(a["url"])
                articles.append(a)

    using_seed = not articles
    if using_seed:
        print("[news] Live feeds unavailable — using seed articles.", file=sys.stderr)
        articles = list(SEED_ARTICLES)

    return {
        "articles": articles[:24],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "seed" if using_seed else "live",
    }

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating rankings…")
    rankings = build_rankings()
    (DOCS_DIR / "rankings.json").write_text(json.dumps(rankings, indent=2))
    print(f"  → {[t['name'] for t in rankings['tools']]}")

    print("Fetching news…")
    news = await build_news()
    (DOCS_DIR / "news.json").write_text(json.dumps(news, indent=2))
    print(f"  → {len(news['articles'])} articles (source: {news['source']})")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
