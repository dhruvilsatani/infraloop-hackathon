#!/bin/bash
# Makes the sample reports for the website with YOUR model (OmniRoute), profile "not launched yet".
# Usage:  ./run_showcase.sh            Results: results_showcase/reports/new/*.md
cd "$(dirname "$0")"
OUT=results_showcase
PY=./.venv_run/bin/python
[ -x "$PY" ] || { echo "Run first: python3 -m venv .venv_run && ./.venv_run/bin/python -m pip install -r requirements.txt"; exit 1; }
curl -s -m 5 "${OMNIROUTE_BASE_URL:-http://localhost:20128/v1}/models" >/dev/null || { echo "OmniRoute is not reachable. Start it first."; exit 1; }
mkdir -p "$OUT" ~/scan_targets
export INFRALOOP_LLM_PROFILE=new
for r in GoogleCloudPlatform/microservices-demo miguelgrinberg/microblog; do
  d=~/scan_targets/$r
  [ -d "$d/.git" ] || git clone -q --depth 1 "https://github.com/$r.git" "$d" || { echo "clone failed: $r"; continue; }
  echo "=== $r"
  "$PY" evaluate.py "$d" --with-llm --profile new --out "$OUT/${r//\//__}"
  rm -rf "$d"
done
echo "ALL DONE. Reports: $OUT/*/reports/new/"
