---
name: project-audit
description: Whole-project codebase audit that looks at every file in one existing project folder (not just recent changes) and reports bugs, dead/orphaned code left behind by past updates, duplicated logic, and drift from the repo's own conventions and internal consistency — then synthesizes whether the project would be built differently from scratch today. Can also repair the findings it surfaces if the user asks it to fix, clean up, or repair the project after seeing the report. Trigger this whenever the user runs "/project-audit", asks to "audit this project", "review the whole project for dead code", "clean up this project", "does this project still make sense", "would you have built this differently", "fix the issues in this project", or wants a holistic health check (and optional cleanup) of an existing project's structure and cruft. Do NOT trigger this for reviewing a pending diff, uncommitted changes, or a pull request — that is the job of the built-in /code-review command instead; this skill is for auditing (and optionally repairing) an entire existing folder regardless of what has or hasn't recently changed.
---

# Project Audit

A full-codebase health check for one project folder. The built-in `/code-review`
looks at what just changed (a diff or a PR); this skill ignores git history and
instead looks at everything that's *there* — including cruft that has quietly
survived several rounds of edits without ever being part of a "recent change."

## 0. Confirm you're looking at the current code

An audit is only as good as the code it actually reads. If the local checkout
is stale, every finding in it can be describing a version of the project that
no longer exists — wasting the whole run at best, and at worst producing
fixes that reintroduce bugs already solved differently upstream. Check this
*before* establishing scope, not after — a wrong scope choice is cheap to
correct, a full audit built on stale code is not.

If the project directory is inside a git repo with a remote configured:

1. `git fetch <remote>` to learn the true upstream state without touching
   the working tree.
2. Compare local `HEAD` to its upstream tracking branch.
   - **Up to date:** proceed normally.
   - **Behind only** (no local commits ahead, no uncommitted changes in the
     working tree): fast-forward automatically (`git pull --ff-only` or
     equivalent) before continuing. This is a safe, non-destructive sync —
     not a judgment call worth interrupting the user over.
   - **Diverged** (local has commits the remote doesn't) **or the working
     tree is dirty**: stop. Don't guess how to reconcile a real divergence —
     summarize what's diverged and ask the user how they want to proceed,
     the same way you would before any other consequential git operation.
     Findings from a repo in this state are not trustworthy until it's
     resolved.

If there's no git repo or no remote, skip this step silently — there's
nothing to sync against.

## 1. Establish scope

This skill always audits exactly one project folder — never the whole repo.
Multiple unrelated projects live side by side in this monorepo, and mixing
their findings together produces a confused, unusable report.

- If the user named a folder (e.g. `/project-audit Stock-Screener`), use it.
- If they didn't, list the project folders in the repo root (skip `.github`,
  `.scripts`, `.claude`, and any other dot-folder) and ask which one to audit.
  Don't guess from conversation context — a wrong guess wastes the whole run.
- Confirm the folder actually exists before spawning any subagents.

Also read the repo's root `CLAUDE.md` if present — it documents the
conventions this specific repo expects projects to follow (folder naming,
self-containment, where scripts belong, etc.). Findings in the "Coherence"
category should be judged against what this repo actually asks for, not
generic best practice.

## 2. Delegate the sweep to subagents

Reading every file in a project directly in the main conversation burns a lot
of context and tends to produce a shallower, more distracted pass. Instead,
spawn subagents (the `Explore` agent type is a good fit — it's read-only,
which keeps this an audit and not an accidental edit) to do the actual file
reading and cross-referencing. Run them in parallel in a single turn.

A three-way split works well because each lens needs a different kind of
attention:

**Bugs subagent** — read through the project's logic looking for actual
defects: broken control flow, off-by-one errors, unhandled edge cases,
mismatched assumptions between files (e.g. `app.js` expecting a JSON field
`rankings.json` no longer produces), race conditions in async code, etc. Not
style preferences — actual things that will misbehave or crash.

**Dead code subagent** — build a rough reference graph for the project: for
every file, what references it (an `<script src>`/`<link>` tag, an `import`,
a function call, a workflow step) and what it references in turn. Flag:
  - Files nothing points to anymore (orphaned by a past refactor)
  - Functions/variables defined but never called or read
  - Commented-out code blocks left behind
  - Data files or assets no longer fetched/loaded by anything live
  This is explicitly about leftovers from *past* updates — code that used to
  matter and was never cleaned up — not about recently-written code.

**Coherence subagent** — compare the project against the repo's own stated
conventions (from `CLAUDE.md`) and against itself: does it follow the folder
layout and naming rules, is styling/patterns consistent across its own files
(e.g. half using `const`/half `var`, inconsistent naming schemes, duplicated
logic across two files that should be one shared function), are there
obvious structural inefficiencies. This subagent should end its findings with
its own honest take on: if this project were started from scratch today,
knowing what the rest of the codebase now looks like, what would change?

Give each subagent the project's absolute path and ask it to return findings
as a list of `{file, line, summary, why_it_matters, severity}` — severity
being one of Critical / High / Medium / Low (see §3 for the rubric).

## 3. Severity rubric

Apply this consistently across all three categories so the merged report
reads as one coherent ranking rather than three subagents' different scales:

- **Critical** — actively broken: will crash, produce wrong output, or fail
  silently in normal use.
- **High** — not currently breaking anything, but a real bug waiting to
  trigger, or dead code / duplication substantial enough to be actively
  misleading to anyone reading the project.
- **Medium** — real issue, but low-impact or easily worked around — a small
  unused helper, a minor inconsistency.
- **Low** — cosmetic or very minor; worth mentioning, not worth prioritizing.

## 4. Merge and report

Once the subagents return, synthesize their findings into one report — don't
just concatenate three lists back to back. Deduplicate overlapping findings
(a dead file might get flagged by both the dead-code and coherence lenses),
and sort within each category by severity.

Output goes to chat only — this skill never writes a report file to disk.
The report itself is always read-only; it doesn't touch code. Whether the
skill goes on to actually fix anything is a separate step — see §5.

Use this structure:

```
# Project Audit: <folder name>

## Bugs
- **[Critical/High/Medium/Low]** `file:line` — one-line description of the
  defect. Why it matters: concrete failure scenario.
  (repeat per finding, most severe first)

## Dead Code
- **[severity]** `file:line` — what's unused/orphaned and how you know
  nothing references it.
  (repeat per finding)

## Architecture & Coherence
- **[severity]** `file:line` — the inconsistency or convention drift.
  (repeat per finding)

## Would this be built differently today?
A short synthesis paragraph (not a restatement of the findings above) that
answers the question directly, explicitly tying the answer back to the
concrete findings rather than offering a freestanding opinion. If the honest
answer is "no, this still holds up," say that plainly instead of manufacturing
criticism to fill the section.
```

If a category has zero findings, keep its heading and write "No issues
found" rather than omitting it — an empty section is itself informative (it
tells the user that lens came back clean).

## 5. Repair (only when asked)

Always show the report first and let the user react to it before touching
any code. Don't fold straight from "here are the findings" into editing —
the whole point of the audit is to give the user a chance to disagree with a
finding or want it handled differently before anything changes.

When the user does ask for fixes (whether in the same message as the audit
request or as a follow-up), sort findings into two tiers before touching
anything, and treat them very differently:

**Obvious fixes — just do them, don't ask first.** Most findings have
exactly one reasonable resolution: an unambiguously-dead function gets
deleted, a missing `r.ok` check gets added, a fetch that can throw gets a
catch, a falsy-`0` bug gets an explicit `is None` check, an off-by-one
display bug gets corrected. There's nothing to decide here — asking "should
I fix the obvious bug" just adds a round-trip for no benefit. Apply these
directly as part of the repair pass.

**Judgment calls — these are the ones worth pausing on.** A finding is a
judgment call when more than one resolution is genuinely defensible and
they lead to different outcomes — e.g. an abandoned feature (data + CSS
wired up, never rendered) could be ripped out *or* finished, and those are
different products; a stale numeric range (like a normalization ceiling)
could be widened, made adaptive, or something else, and picking one shapes
future behavior. Don't guess on these — name them specifically and ask
which direction, while going ahead and applying the obvious fixes in the
same pass without waiting on the answer.

**Fix only what's actually confirmed in scope.** If the user narrowed
things ("just the Critical ones," "skip the CSS stuff"), that overrides the
obvious/judgment-call split above — respect the narrower scope rather than
fixing everything obvious regardless of what they asked for.

**Low severity findings are out of scope by default.** By definition (§3)
Low means cosmetic or very minor — fixing them isn't worth the review
overhead of even a summary line, let alone a question. Leave them out of
the repair pass entirely (don't auto-fix them, don't ask about them either)
unless the user specifically asks to include Low findings too. This keeps
repair focused on things that actually matter and keeps what the user has
to review as small as possible.

**Sanity-check after editing, not just before.** Once fixes are applied,
re-verify rather than assuming the edit was correct: syntax-check any Python
touched (e.g. `python -m py_compile`), and for a static-site project like
this, a quick reread of the changed files (or a fast subagent pass) to
confirm nothing else in the project silently depended on what you just
changed. Report back a concise summary of what was actually changed
(file + one-line description per fix) — not a full diff dump.

**Confirm before publishing.** This repo's own convention (per its root
`CLAUDE.md`) is that fixes to an existing project get committed and pushed
straight to `main` so GitHub Pages serves the update immediately. That's the
right default *once the user has seen what changed* — but because pushing
updates a live public site, treat it as its own confirmation step even when
the fixes themselves were pre-approved: show the summary of changes, then
ask before committing and pushing that specific batch. Don't chain
straight from "applied the fix" to "pushed to production" without that
checkpoint.
