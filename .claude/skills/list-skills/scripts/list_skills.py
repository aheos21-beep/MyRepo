#!/usr/bin/env python3
"""
Lists every Claude Code skill across two places:
  1. Personal skills on this Mac: ~/.claude/skills/
  2. Any .claude/skills/ folder in a PUBLIC repo on the configured GitHub account

Stdlib only, no dependencies, no auth — uses the unauthenticated GitHub REST
API, which only sees public repos. If a private repo has skills, this will
not find them; the script says so explicitly at the end rather than silently
under-reporting as if it were complete.
"""
from __future__ import annotations  # keeps `str | None`-style hints working on Python < 3.10

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_USER = "aheos21-beep"
API = "https://api.github.com"
HEADERS = {"User-Agent": "list-skills-claude-code-skill", "Accept": "application/vnd.github+json"}

PERSONAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


def api_get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def list_public_repos(user: str) -> list[dict]:
    repos, page = [], 1
    while True:
        try:
            batch = api_get(f"{API}/users/{user}/repos?per_page=100&page={page}&type=owner")
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                print(f"[list-skills] GitHub API rate-limited while listing repos "
                      f"(HTTP 403) — results may be incomplete.", file=sys.stderr)
                break
            raise
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def repo_skill_dirs(user: str, repo: str) -> list[str]:
    """Names of subfolders under .claude/skills/ in a repo's default branch, or [] if none."""
    try:
        contents = api_get(f"{API}/repos/{user}/{repo}/contents/.claude/skills")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        if exc.code == 403:
            print(f"[list-skills] Rate-limited checking {repo} — skipped.", file=sys.stderr)
            return []
        raise
    if not isinstance(contents, list):
        return []
    return sorted(item["name"] for item in contents if item.get("type") == "dir")


def fetch_description(user: str, repo: str, skill: str) -> str | None:
    url = f"https://raw.githubusercontent.com/{user}/{repo}/HEAD/.claude/skills/{skill}/SKILL.md"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode()
    except Exception:
        return None
    return parse_frontmatter_description(text)


def parse_frontmatter_description(skill_md_text: str) -> str | None:
    if not skill_md_text.startswith("---"):
        return None
    end = skill_md_text.find("\n---", 3)
    if end == -1:
        return None
    frontmatter = skill_md_text[3:end]
    match = re.search(r'^description:\s*"?(.*?)"?\s*$', frontmatter, re.MULTILINE)
    if not match:
        return None
    desc = match.group(1).strip()
    return (desc[:157] + "...") if len(desc) > 160 else desc


def local_skills() -> list[tuple[str, str | None]]:
    if not PERSONAL_SKILLS_DIR.is_dir():
        return []
    out = []
    for d in sorted(PERSONAL_SKILLS_DIR.iterdir()):
        skill_md = d / "SKILL.md"
        if skill_md.is_file():
            out.append((d.name, parse_frontmatter_description(skill_md.read_text())))
    return out


def main():
    print(f"=== Personal skills (~/.claude/skills) ===")
    local = local_skills()
    if not local:
        print("  (none)")
    for name, desc in local:
        print(f"  - {name}: {desc or '(no description found)'}")

    print(f"\n=== Public GitHub repos for {GITHUB_USER} with Claude Code skills ===")
    repos = list_public_repos(GITHUB_USER)
    any_found = False
    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        name = repo["name"]
        skills = repo_skill_dirs(GITHUB_USER, name)
        if not skills:
            continue
        any_found = True
        print(f"\n  {name} ({repo['html_url']})")
        for skill in skills:
            desc = fetch_description(GITHUB_USER, name, skill)
            print(f"    - {skill}: {desc or '(no description found)'}")

    if not any_found:
        print("  (no public repos with a .claude/skills/ folder found)")

    print(f"\n[list-skills] Checked {len(repos)} public repo(s) for {GITHUB_USER}. "
          f"Private repos are not included — this uses the unauthenticated GitHub "
          f"API, which cannot see them.")


if __name__ == "__main__":
    main()
