---
name: list-skills
description: Lists every Claude Code skill you have, both your personal skills on this Mac (~/.claude/skills) and any skill found in a .claude/skills/ folder across all public repositories on the aheos21-beep GitHub account. Trigger this whenever the user runs "/list-skills", asks "what skills do I have", "list my claude code skills", "show me all my skills", "which repos have skills", "inventory my skills", or wants an audit of skills scattered across their personal folder and GitHub repos. Read-only — it never creates, edits, or deletes anything, only reports. Only covers public repos (no GitHub auth is configured for private-repo access); the output always says so explicitly rather than implying full coverage. Do NOT confuse this with claude.ai chat skills (Settings → Capabilities) — this only sees Claude Code skills (files named SKILL.md), a separate system.
---

# List Skills

Runs `scripts/list_skills.py` and relays its output. The script is stdlib-only
Python (no dependencies, no auth) that:

1. Scans `~/.claude/skills/` for personal skills.
2. Lists every public repo on the `aheos21-beep` GitHub account via the
   unauthenticated REST API, and checks each one for a `.claude/skills/`
   folder.
3. For every skill found in either place, reads its `SKILL.md` frontmatter
   to report the `name` and `description`.

Run it with:

```bash
python3 <skill_dir>/scripts/list_skills.py
```

(`<skill_dir>` is wherever this skill is actually loaded from — resolve it
rather than hardcoding a path, since the same skill exists at both
`~/.claude/skills/list-skills` and `MyRepo/.claude/skills/list-skills`, per
the dual-save convention documented in `MyRepo/CLAUDE.md`.)

Relay the script's own output directly — it's already formatted as a clean
report. Don't re-summarize or restructure it; the one thing worth adding on
top is flagging anything actionable, like a skill that exists in a GitHub
repo but not in `~/.claude/skills` (out of sync per the dual-save
convention), or vice versa.

**Coverage limits worth surfacing to the user if they seem to expect more:**
- Private repos are never checked — this deliberately uses the
  unauthenticated GitHub API (no `gh` CLI, no token) to avoid an extra
  dependency to install and keep authenticated. The script's own final line
  always states this plainly.
- Only the `aheos21-beep` account is checked. If the user has skills under a
  different GitHub account or organization, this won't find them.
- Only `.claude/skills/` at each repo's root is checked, matching where
  Claude Code actually looks for project-level skills — not arbitrary
  folders elsewhere in a repo.
- This never sees claude.ai chat skills (a separate system, uploaded via
  Settings → Capabilities on claude.ai) — only Claude Code's own `SKILL.md`
  files.

If the GitHub API rate-limits mid-run (60 requests/hour, unauthenticated),
the script logs which step got limited to stderr and still prints whatever
it found — relay that partial result along with the rate-limit note rather
than treating it as a failure.
