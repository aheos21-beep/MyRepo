# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo structure conventions

Every project must be **fully self-contained in its own folder**, named in `Title-Case-With-Hyphens`. Each folder must have an `index.html` at its root so GitHub Pages can serve it automatically at `username.github.io/MyRepo/<Project-Name>/`.

Two shared folders exist at repo root and should stay there:
- `.github/workflows/` — GitHub Actions automation. GitHub only executes workflows found here.
- `scripts/` — repo-level utilities that are not specific to any single project (e.g. `push.sh`).

If a script is specific to one project, place it inside that project's folder (see `AI-Tools-Ranking/generate_data.py`).

## Hosting model

All projects are hosted on **GitHub Pages** (static files only — no server-side code). Dynamic data is produced by **GitHub Actions**, which runs scripts in the background, commits the output back to the repo, and Pages serves the resulting static files.

## AI-Tools-Ranking

The only project with automation. Architecture:
- `generate_data.py` — fetches RSS feeds and calculates rankings; writes `rankings.json` and `news.json` into its own folder. Run locally with `pip install aiohttp && python AI-Tools-Ranking/generate_data.py`.
- `index.html` + `app.js` + `style.css` — static frontend that reads `rankings.json` and `news.json` directly via `fetch()`.
- GitHub Actions (`.github/workflows/daily-refresh.yml`) runs `generate_data.py` at 6am and 6pm UTC and commits the updated JSON files. Can be triggered manually from the GitHub Actions tab.

## Before starting any new project

Always ask the user how the project will be hosted or used before applying any conventions. Examples:
- GitHub Pages → apply the folder and index.html conventions above
- Scriptable widget → self-contained single file, no folder structure needed
- GitHub Actions only → script goes in the project folder or `scripts/`, no index.html needed

Do not assume GitHub Pages hosting unless the user confirms it.

## Adding a new project (GitHub Pages)

1. Create a `New-Project-Name/` folder (Title-Case-With-Hyphens).
2. Add an `index.html` inside it — this is what GitHub Pages serves.
3. If the project needs scheduled automation, add a workflow in `.github/workflows/` and put any project-specific scripts inside the project folder.
4. If the script is reusable across projects, put it in `scripts/` instead.
