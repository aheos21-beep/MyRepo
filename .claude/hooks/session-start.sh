#!/bin/bash
set -euo pipefail

REPO_URL="https://github.com/aheos21-beep/claude-skills.git"
SKILLS_DIR="$HOME/.claude/skills"
export GIT_TERMINAL_PROMPT=0

if [ -d "$SKILLS_DIR/.git" ] && git -C "$SKILLS_DIR" remote get-url origin 2>/dev/null | grep -q "aheos21-beep/claude-skills"; then
  git -C "$SKILLS_DIR" pull --ff-only origin main
else
  if [ -d "$SKILLS_DIR" ]; then
    mv "$SKILLS_DIR" "${SKILLS_DIR}.bak.$(date +%s)"
  fi
  mkdir -p "$(dirname "$SKILLS_DIR")"
  git clone --depth 1 "$REPO_URL" "$SKILLS_DIR"
fi
