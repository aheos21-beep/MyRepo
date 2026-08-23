# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo structure conventions

Every project must be **fully self-contained in its own folder**, named in `Title-Case-With-Hyphens`. Each folder must have an `index.html` at its root so GitHub Pages can serve it automatically at `username.github.io/MyRepo/<Project-Name>/`.

Two shared folders exist at repo root and should stay there:
- `.github/workflows/` — GitHub Actions automation. GitHub only executes workflows found here.
- `.scripts/` — repo-level utilities that are not specific to any single project (e.g. `push.sh`).

If a script is specific to one project, place it inside that project's folder (see `Stock-Screener/fetch_data.py`).

## Hosting model

All projects are hosted on **GitHub Pages** (static files only — no server-side code). Dynamic data is produced by **GitHub Actions**, which runs scripts in the background, commits the output back to the repo, and Pages serves the resulting static files.

## Staying in sync

Because GitHub Actions commits directly to `main` across several independent projects on their own schedules, a local checkout can go stale fast — hours, not weeks. A `.claude/hooks/session-start.sh` hook runs `git fetch` automatically at the start of every session and surfaces a warning if local has drifted from its remote tracking branch; it never touches the working tree itself. If it warns, `git pull` before editing or auditing anything based on current file contents — working from a stale checkout risks redoing work that's already been done differently upstream.

## Claude Code skills

Two separate skill systems exist here, and only one of them needs anything
committed to this repo:

- **claude.ai account skills** — created/saved via the skill-creator "save"
  flow and tracked in `~/.claude/skills/manifest.json` with
  `"source": "custom"` (e.g. `llm-council`, `who-to-hire`,
  `cibc-fact-finder`). These sync automatically into *every* Claude Code
  session — local Mac, cloud, or mobile sandbox — regardless of which repo
  (if any) is open. **Do not mirror these into `MyRepo/.claude/skills/`** —
  a copy there is never read by anything and just adds stale clutter.
  `cibc-fact-finder`, `llm-council`, and `session-start-hook` were removed
  from this repo for exactly that reason (see commit `c52711b`); rely on
  the automatic account sync instead of re-adding them.
- **Project-scoped Claude Code skills** — plain `SKILL.md` folders authored
  directly on disk, never registered as an account skill (e.g.
  `project-audit`). These are only visible to a session that has the
  containing folder checked out, so they still need the manual mirror:
  - `~/.claude/skills/` — available to any local Claude Code session on
    this Mac immediately.
  - `MyRepo/.claude/skills/` — committed here so cloud and mobile sessions
    (which clone this repo into a fresh sandbox with no access to
    `~/.claude/skills`) get them too.

  Whenever you create one of *these*, save it to `~/.claude/skills/` *and*
  copy the same folder into `MyRepo/.claude/skills/`, then commit and push.
  Both copies should stay identical — if one is edited later, mirror the
  change into the other by hand.

If you're unsure which kind a skill is, check
`~/.claude/skills/manifest.json`: an entry with `"source": "custom"` is an
account skill and doesn't belong in the repo.

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
