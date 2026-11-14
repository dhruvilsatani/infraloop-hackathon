#!/bin/bash
# Runs the real pipeline with YOUR model (OmniRoute) on a set of repos, one after another.
# Usage:  ./run_my_model.sh            (uses repos_to_test.txt, 20 repos by default)
# Results: results_mymodel/reports/prod/*.md, results_mymodel/*/results.json, timing in run.log
cd "$(dirname "$0")"
LIST=${1:-repos_to_test.txt}
OUT=results_mymodel
# Use the Python environment that is already active (e.g. in the VS Code terminal); otherwise make one.
if [ -n "$VIRTUAL_ENV" ] || [ -n "$CONDA_PREFIX" ]; then
  PY=python
elif python3 -c "import langgraph" 2>/dev/null; then
  PY=python3
else
  if [ ! -x ./.venv_run/bin/python ]; then
    echo "First run: creating a Python environment and installing packages (about a minute)..."
    python3 -m venv .venv_run && ./.venv_run/bin/python -m pip install -q -r requirements.txt || { echo "Could not set up packages"; exit 1; }
  fi
  PY=./.venv_run/bin/python
fi
echo "Using: $($PY -c 'import sys;print(sys.executable)')"
mkdir -p "$OUT" ~/scan_targets
while read -r r; do
  [ -z "$r" ] && continue
  d=~/scan_targets/$r
  [ -d "$d/.git" ] || git clone -q --depth 1 "https://github.com/$r.git" "$d" || { echo "clone failed: $r" >> $OUT/run.log; continue; }
  echo "=== $r" | tee -a $OUT/run.log
  "${PY}" evaluate.py "$d" --with-llm --out "$OUT/${r//\//__}" 2>&1 | tee -a $OUT/run.log
  rm -rf "$d"
done < "$LIST"
echo "ALL DONE" | tee -a $OUT/run.log
