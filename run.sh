#!/usr/bin/env bash
# run.sh — one command to run THE OTHER HALF
#
#   ./run.sh              check for new deaths once, then serve the site
#   ./run.sh demo         offline demo data, then serve
#   ./run.sh watch        serve the site + keep checking every 30 min
#   ./run.sh name "X Y"   force an edit for one person, then serve
#
set -e
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

# use the project virtualenv, creating it via setup.sh if needed
[ -x .venv/bin/python ] || ./setup.sh
PY="$PWD/.venv/bin/python"

serve() {
  echo "→ http://localhost:$PORT"
  cd site && exec "$PY" -m http.server "$PORT"
}

case "${1:-once}" in
  demo)  "$PY" watcher.py --demo; serve ;;
  once)  "$PY" watcher.py --once; serve ;;
  name)  [ -n "$2" ] || { echo "usage: ./run.sh name \"Person Name\""; exit 1; }
         "$PY" watcher.py --name "$2"; serve ;;
  watch) "$PY" watcher.py --poll 1800 &
         WATCHER=$!
         trap 'kill $WATCHER 2>/dev/null' EXIT
         serve ;;
  *)     echo "usage: ./run.sh [demo|once|watch|name \"Person Name\"]"; exit 1 ;;
esac
