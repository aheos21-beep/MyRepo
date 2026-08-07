# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo structure conventions

Every project must be **fully self-contained in its own folder**, named in `Title-Case-With-Hyphens`. Each folder must have an `index.html` at its root so GitHub Pages can serve it automatically at `username.github.io/MyRepo/<Project-Name>/`.

Two shared folders exist at repo root and should stay there:
- `.github/workflows/` — GitHub Actions automation. GitHub only executes workflows found here.
- `.scripts/` — repo-level utilities that are not specific to any single project (e.g. `push.sh`).

If a script is specific to one project, place it inside that project's folder (see `AI-Tools-Ranking/generate_data.py`).

## Hosting model

All projects are hosted on **GitHub Pages** (static files only — no server-side code). Dynamic data is produced by **GitHub Actions**, which runs scripts in the background, commits the output back to the repo, and Pages serves the resulting static files.

## Staying in sync

Because GitHub Actions commits directly to `main` across several independent projects on their own schedules, a local checkout can go stale fast — hours, not weeks. A `.claude/hooks/session-start.sh` hook runs `git fetch` automatically at the start of every session and surfaces a warning if local has drifted from its remote tracking branch; it never touches the working tree itself. If it warns, `git pull` before editing or auditing anything based on current file contents — working from a stale checkout risks redoing work that's already been done differently upstream.

## Claude Code skills

Personal skills have two homes, kept in sync by habit rather than automation —
no sync hook, no separate repo:
- `~/.claude/skills/` — personal, this Mac only. Makes a skill available in
  any local Claude Code session, on any project, immediately.
- `MyRepo/.claude/skills/` — committed here so cloud and mobile Claude Code
  sessions (which clone this repo into a fresh sandbox with no access to
  `~/.claude/skills`) can use it too.

Whenever a new personal skill is created, save it to `~/.claude/skills/`
*and* copy the same folder into `MyRepo/.claude/skills/`, then commit and
push. Both copies should stay identical — if one is edited later, mirror the
change into the other by hand.

## AI-Tools-Ranking

The only project with automation. Architecture:
- `generate_data.py` — reads published Arena AI (LMSYS) leaderboard snapshots and writes `rankings.json` and `history.json`. Standard library only, no API key, no cost. Run locally with `python AI-Tools-Ranking/generate_data.py`.
- `index.html` + `app.js` + `style.css` — static frontend that reads both JSON files directly via `fetch()` (cache-busted with a `?v=` timestamp).
- `vendor/chart.umd.js` — Chart.js 4.4.0, vendored rather than loaded from a CDN. Keeps the project self-contained and avoids a blocked or slow CDN silently leaving the chart blank. If Chart.js is somehow unavailable, `renderChart` writes a visible `.chart-error` message rather than returning quietly.
- GitHub Actions (`.github/workflows/daily-refresh.yml`) runs `generate_data.py` daily at 9am UTC and commits the updated JSON. Can be triggered manually from the GitHub Actions tab. Daily is viable because the source publishes daily and the run costs nothing; the countdown in `app.js` assumes this cadence and reports hours, so update it if the cron changes.

Data notes:
- Source is the `oolong-tea-2026/arena-ai-leaderboards` GitHub mirror, which publishes daily JSON snapshots of each Arena board. Every displayed number is a published Arena ELO and can be checked against that source.
- Vendors are collapsed to their single best-scoring model before ranking — the raw text board is dominated by multiple variants from the same vendor.
- Arena ELO is unbounded, so it is displayed at 1/10 scale (`SCALE_DIVISOR`), rounded to a whole number: 1509 → 151. Needs no retuning as boards drift.
- Cards can therefore show the same figure for different models (1490, 1486 and 1485 all read 149). That is intentional. Ranking always sorts on the full-precision `arena_elo`, never the rounded display value — do not re-sort on `score` in the frontend.
- `history.json` is rebuilt from dated snapshots on every run rather than appended to, so it is reproducible and self-healing. Months with no published snapshot are skipped; a model absent from a snapshot gets `null`, which the chart draws as a visible gap (`spanGaps: false`). Never backfill or interpolate these — an estimated point is indistinguishable from a real one once it is on the chart.
- The current month uses the latest snapshot (the same one the cards are built from) rather than the 1st, so the chart's final point always equals the card scores. `main()` asserts this and exits non-zero on mismatch. An earlier version ended the chart on the 1st while the cards used the latest day, which made the page look wrong even though both numbers were correct.
- `generate_data.py` stamps a content hash onto the `app.js` and `style.css` URLs in `index.html` (`app.js?v=<sha8>`). Without this a cached `app.js` survives a deploy and the page behaves like an older build while looking current — this caused cards to keep opening links after linking was removed. The hash changes only when the file changes, so daily runs produce no diff. The workflow therefore commits `index.html` as well as the JSON.
- Ranking cards are informational only — plain `div`s with no links and no hover affordance. `url` is still emitted in `rankings.json` but unused, kept so linking can be restored without reshaping `VENDOR_META`.
- A vendor missing from `VENDOR_META` still ranks correctly but shows the bare Arena vendor name and a generic icon. The script logs a `[branding] WARNING` naming any such vendor — add it to `VENDOR_META` when it appears.
- Do not reintroduce LLM-sourced benchmark numbers here. An earlier version asked an LLM to search the web for MMLU/HumanEval/MATH scores; the values could not be verified, and a plausible-but-wrong number was indistinguishable from a correct one.

## Before starting any new project

Always ask the user how the project will be hosted or used before applying any conventions. Examples:
- GitHub Pages → apply the folder and index.html conventions above
- Scriptable widget → self-contained single file, no folder structure needed
- GitHub Actions only → script goes in the project folder or `.scripts/`, no index.html needed

Do not assume GitHub Pages hosting unless the user confirms it.

## Adding a new project (GitHub Pages)

1. Create a `New-Project-Name/` folder (Title-Case-With-Hyphens).
2. Add an `index.html` inside it — this is what GitHub Pages serves.
3. If the project needs scheduled automation, add a workflow in `.github/workflows/` and put any project-specific scripts inside the project folder.
4. If the script is reusable across projects, put it in `.scripts/` instead.

## Updating an existing project

When asked to update or fix a project that already exists in the repo, **edit the files in place inside the existing project folder**. Do NOT create a new folder or duplicate files. Changes should be committed directly to `main` and pushed so GitHub Pages serves the updated version immediately. Only create a new folder if the user explicitly says it is a new, separate project.
