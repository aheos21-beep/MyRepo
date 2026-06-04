#!/bin/zsh
cd /Users/christosmylonas/Documents/MyRepo

# Remove stale lock file if it exists
rm -f .git/HEAD.lock
rm -f .git/index.lock

# Pull any remote changes first, then push
git add -A
git commit -m "Auto-push: $(date +%Y-%m-%d)" || true
git pull --rebase
git push
