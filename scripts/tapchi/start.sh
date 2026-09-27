#!/bin/bash
# (Re)start the magazine extraction jobs in the background (resumable). Usage: scripts/tapchi/start.sh [stop]
cd "$(dirname "$0")/../.." || exit 1
L=.cache/tapchi
for m in thtt ttt2; do
  [ -f $L/$m.pid ] && kill "$(cat $L/$m.pid)" 2>/dev/null
done
[ "$1" = stop ] && exit 0
GEM=8 ISSUES=14 DL=6 nohup python3 -u scripts/tapchi/run.py extract --mag thtt >> $L/extract-thtt.log 2>&1 &
echo $! > $L/thtt.pid
GEM=3 ISSUES=4 DL=3 nohup python3 -u scripts/tapchi/run.py extract --mag ttt2 >> $L/extract-ttt2.log 2>&1 &
echo $! > $L/ttt2.pid
echo started thtt=$(cat $L/thtt.pid) ttt2=$(cat $L/ttt2.pid)
