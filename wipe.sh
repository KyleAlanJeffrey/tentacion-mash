#!/usr/bin/env bash
# wipe.sh — erase every edit from the cloud so the timeline can be rebuilt.
#
# Deletes each edit through the worker's own DELETE /api/edits/:slug endpoint,
# which drops BOTH the D1 metadata row and the R2 image. After this the DB is
# empty and the next generator run regenerates everyone from scratch.
#
#   ./wipe.sh            wipe production (asks you to confirm)
#   ./wipe.sh --yes      wipe without the confirmation prompt
#
# Needs INGEST_TOKEN (the same secret the generator uploads with) and, if your
# domain differs, WORKER_URL. Both are read from the environment or ./.env.
set -euo pipefail
cd "$(dirname "$0")"

# load local credentials if present (same as run.sh)
if [ -f .env ]; then set -a; . ./.env; set +a; fi

WORKER_URL="${WORKER_URL:-${SELF_URL:-https://xxx5050.com}}"
WORKER_URL="${WORKER_URL%/}"

if [ -z "${INGEST_TOKEN:-}" ]; then
  echo "INGEST_TOKEN is not set — put it in .env or the environment." >&2
  echo "(it's the worker secret: Worker -> Settings -> Variables and Secrets)" >&2
  exit 1
fi

# prefer the project venv python, fall back to system python3, for JSON parsing
PY="python3"; [ -x .venv/bin/python ] && PY=".venv/bin/python"

echo "target: $WORKER_URL"
slugs=$(curl -fsS "$WORKER_URL/api/edits" |
  "$PY" -c 'import sys, json; [print(e["slug"]) for e in json.load(sys.stdin)]')

count=$(printf '%s\n' "$slugs" | grep -c . || true)
if [ "$count" -eq 0 ]; then
  echo "already empty — nothing to wipe."
  exit 0
fi

echo "this will PERMANENTLY delete $count edit(s) — D1 rows and R2 images — from $WORKER_URL"
if [ "${1:-}" != "--yes" ]; then
  read -r -p "type 'wipe' to continue: " ans
  [ "$ans" = "wipe" ] || { echo "aborted."; exit 1; }
fi

ok=0; fail=0
while IFS= read -r slug; do
  [ -n "$slug" ] || continue
  # </dev/null so curl doesn't swallow the slug list on stdin
  if curl -fsS -X DELETE -H "authorization: Bearer $INGEST_TOKEN" \
       "$WORKER_URL/api/edits/$slug" </dev/null >/dev/null; then
    ok=$((ok + 1)); printf '  deleted %s\n' "$slug"
  else
    fail=$((fail + 1)); printf '  FAILED  %s\n' "$slug"
  fi
done < <(printf '%s\n' "$slugs")

remaining=$(curl -fsS "$WORKER_URL/api/edits" |
  "$PY" -c 'import sys, json; print(len(json.load(sys.stdin)))')
echo "wiped $ok, failed $fail — $remaining edit(s) remain."

cat <<'NEXT'

next — rebuild the timeline with the current splice code:
  MAX_NEW_PER_RUN=1000 WORKER_URL=$WORKER_URL INGEST_TOKEN=$INGEST_TOKEN \
    .venv/bin/python generator/watcher.py --publish
  (run it again if it reports a cap; it only makes new edits each pass)

the deployed container still runs the OLD code until you `npx wrangler deploy`,
so regenerating locally like this is what applies the new alignment.
NEXT
