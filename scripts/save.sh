#!/usr/bin/env bash
# Snapshot after a green `make done` (CONSTITUCION §2.2): the return point while there is no git.
# Copies src/, tests/ (WITHOUT tests/holdout: a readable copy would leak the reserve), docs/, pyproject.toml,
# uv.lock and the test inventory, plus MANIFEST.sha256. Only scripts/done.py calls it.
set -euo pipefail
cd "$(dirname "$0")/.."

milestone="${1:?uso: save.sh <fase>}"
base=".snapshots/$(date +%Y-%m-%d)-fase${milestone}"
dest="$base"
i=2
while [ -e "$dest" ]; do dest="${base}-${i}"; i=$((i + 1)); done

mkdir -p "$dest"
rsync -a --exclude 'holdout/' --exclude '__pycache__/' src tests docs "$dest/"
cp pyproject.toml uv.lock "$dest/"
cp .claude/state/test-inventory.json "$dest/"
(cd "$dest" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 shasum -a 256 > MANIFEST.sha256)
echo "$dest"
