#!/bin/bash
# Warns (never blocks, never mutates the working tree) when the local
# checkout has drifted from its remote tracking branch. This repo is
# updated frequently by scheduled GitHub Actions across several
# independent projects, so a checkout that's a day old can already be
# behind by a large amount — this surfaces that at the start of every
# session instead of letting it be discovered mid-task (e.g. a rejected
# push, or work done against code that's since been rewritten upstream).
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

remote=$(git remote | head -1)
[ -z "$remote" ] && exit 0

# Best-effort: never fail session start just because the network is down.
git fetch "$remote" --quiet 2>/dev/null || exit 0

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || exit 0

behind=$(git rev-list --count "HEAD..$upstream" 2>/dev/null || echo 0)
ahead=$(git rev-list --count "$upstream..HEAD" 2>/dev/null || echo 0)

if [ "$behind" -gt 0 ] || [ "$ahead" -gt 0 ]; then
  context="Git sync check: local branch '$branch' is $behind commit(s) behind and $ahead commit(s) ahead of '$upstream'. This repo is updated frequently by automated workflows across multiple projects. Before making changes based on current file contents (auditing, editing, or committing), consider running 'git pull' first to avoid working from a stale checkout — or if local has commits the remote doesn't, treat that as a real divergence to resolve deliberately, not something to force-push over."
  printf '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": %s}}' "$(printf '%s' "$context" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
fi

exit 0
