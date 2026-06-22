#!/bin/bash
# Watches iCloud Drive "Claude Output" for an updated Asset Classes.html
# and pushes it to GitHub whenever the Cowork scheduled task drops a new version.

REPO="/Users/christosmylonas/Documents/MyRepo"
SOURCE="/Users/christosmylonas/Library/Mobile Documents/com~apple~CloudDocs/Claude Output/Asset Classes.html"
DEST="${REPO}/Asset Classes.html"
LOG="${REPO}/watcher.log"

timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

if [ ! -f "${SOURCE}" ]; then
    echo "[$(timestamp)] No update found: source file missing from Claude Output." >> "${LOG}"
    exit 0
fi

# Compare content hashes (md5 -q on macOS prints hash only)
SRC_HASH=$(md5 -q "${SOURCE}" 2>/dev/null)
DST_HASH=$([ -f "${DEST}" ] && md5 -q "${DEST}" 2>/dev/null || echo "none")

if [ "${SRC_HASH}" = "${DST_HASH}" ]; then
    echo "[$(timestamp)] No update found: hash unchanged (${SRC_HASH})." >> "${LOG}"
    exit 0
fi

echo "[$(timestamp)] Update detected — source hash ${SRC_HASH} vs repo hash ${DST_HASH}. Copying..." >> "${LOG}"

cp "${SOURCE}" "${DEST}"
if [ $? -ne 0 ]; then
    echo "[$(timestamp)] ERROR: cp failed (exit $?)." >> "${LOG}"
    exit 1
fi

cd "${REPO}" || { echo "[$(timestamp)] ERROR: cannot cd to repo." >> "${LOG}"; exit 1; }
rm -f .git/index.lock .git/HEAD.lock
chmod +x push.sh

# Capture push.sh output to a temp file so watcher.log isn't modified concurrently
# (concurrent writes cause "unstaged changes" when push.sh later runs git pull --rebase)
PUSH_TMP=$(mktemp /tmp/assetwatcher_push.XXXXXX)
./push.sh > "${PUSH_TMP}" 2>&1
PUSH_EXIT=$?
cat "${PUSH_TMP}" >> "${LOG}"
rm -f "${PUSH_TMP}"

if [ ${PUSH_EXIT} -eq 0 ]; then
    COMMIT=$(git log -1 --format="%H %s" 2>/dev/null)
    echo "[$(timestamp)] SUCCESS: pushed to GitHub. Commit: ${COMMIT}" >> "${LOG}"
else
    echo "[$(timestamp)] ERROR: push.sh exited with code ${PUSH_EXIT}." >> "${LOG}"
fi
