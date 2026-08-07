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
    """
    Emits one JSON object to stdout: a deduplicated, merged view of every
    skill found across ~/.claude/skills and every public repo's
    .claude/skills/. Deliberately does NOT try to shorten each skill's
    description itself — turning a paragraph into a genuine 3-4 word summary
    needs real judgment, which belongs to whoever's reading this output
    (a human, or the agent relaying it), not a string-slicing heuristic here.
    """
    local = dict(local_skills())  # name -> full description

    repos = list_public_repos(GITHUB_USER)
    repo_names_by_skill: dict[str, list[str]] = {}
    descriptions = dict(local)

    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        repo_name = repo["name"]
        for skill in repo_skill_dirs(GITHUB_USER, repo_name):
            repo_names_by_skill.setdefault(skill, []).append(repo_name)
            if skill not in descriptions:
                desc = fetch_description(GITHUB_USER, repo_name, skill)
                if desc:
                    descriptions[skill] = desc

    all_names = sorted(set(descriptions) | set(repo_names_by_skill))
    result = {
        "skills": [
            {
                "name": name,
                "description": descriptions.get(name, "(no description found)"),
                "personal": name in local,
                "repos": repo_names_by_skill.get(name, []),
            }
            for name in all_names
        ],
        "public_repos_checked": len(repos),
        "coverage_note": (
            "Private repos are not included — this uses the unauthenticated "
            "GitHub API, which cannot see them."
        ),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
