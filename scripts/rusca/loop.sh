#!/bin/bash
# Re-run translate.py until no further progress (retries failed chunks). Usage: bash scripts/rusca/loop.sh [prefix ...]
cd "$(dirname "$0")/../.."
prev=-1
for i in $(seq 1 30); do
  python3 scripts/rusca/translate.py "$@" >> .cache/rusca/loop.log 2>&1
  n=$(cat .cache/rusca/tr/*.json | grep -c '"model"')
  echo "$(date +%T) round $i done=$n" >> .cache/rusca/loop.log
  [ "$n" = "$prev" ] && break
  prev=$n
done
python3 scripts/rusca/translate.py --build >> .cache/rusca/loop.log 2>&1
