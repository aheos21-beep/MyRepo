---
name: list-skills
description: Lists every Claude Code skill you have, both your personal skills on this Mac (~/.claude/skills) and any skill found in a .claude/skills/ folder across all public repositories on the aheos21-beep GitHub account. Trigger this whenever the user runs "/list-skills", asks "what skills do I have", "list my claude code skills", "show me all my skills", "which repos have skills", "inventory my skills", or wants an audit of skills scattered across their personal folder and GitHub repos. Read-only — it never creates, edits, or deletes anything, only reports. Only covers public repos (no GitHub auth is configured for private-repo access); the output always says so explicitly rather than implying full coverage. Do NOT confuse this with claude.ai chat skills (Settings → Capabilities) — this only sees Claude Code skills (files named SKILL.md), a separate system.
---

# List Skills

Runs `scripts/list_skills.py` and formats its output into a compact table.
The script is stdlib-only Python (no dependencies, no auth) that:

1. Scans `~/.claude/skills/` for personal skills.
2. Lists every public repo on the `aheos21-beep` GitHub account via the
   unauthenticated REST API, and checks each one for a `.claude/skills/`
   folder.
3. Merges everything found into one deduplicated JSON object on stdout —
   one entry per unique skill name, with its full description, whether it's
   in `~/.claude/skills`, and which repo(s) (if any) it's in.

Run it with:

```bash
python3 <skill_dir>/scripts/list_skills.py
```

(`<skill_dir>` is wherever this skill is actually loaded from — resolve it
rather than hardcoding a path, since the same skill exists at both
`~/.claude/skills/list-skills` and `MyRepo/.claude/skills/list-skills`, per
the dual-save convention documented in `MyRepo/CLAUDE.md`.)

## Formatting the output

The script deliberately leaves each skill's full `description` un-shortened
— condensing a paragraph into a genuine 3-4 word summary needs real
judgment (what is this skill actually *for*, in a handful of words), not
string-slicing, so that's your job when relaying the result, not the
script's.

Present one row per skill as a markdown table:

| Skill | Description | Personal | Repo(s) |
|---|---|---|---|
| project-audit | audits & repairs a project | ✅ | MyRepo |

- **Description**: your own 3-4 word paraphrase of what the skill *does*,
  read from its full `description` field — not a truncation of it.
- **Personal**: ✅ if `personal` is true, otherwise blank.
- **Repo(s)**: comma-separated `repos` list, or blank if empty.

After the table, include the script's `coverage_note` and
`public_repos_checked` count so coverage limits stay visible every time —
never let the compact format imply completeness it doesn't have.

Flag anything actionable below the table: a skill with `personal: true` but
an empty `repos` list (or vice versa) is out of sync per the dual-save
convention and worth calling out by name.

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
