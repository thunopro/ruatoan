#!/bin/bash
# Daily cron: continue exam extraction on fresh Gemini quota, filter, deploy. Removes its own cron line when done.
cd "$(dirname "$0")/../.."
export PATH=/home/luongminhthu/.nvm/versions/node/v24.21.0/bin:/usr/local/bin:/usr/bin:/bin:$PATH
LOG=.cache/exams/daily.log
echo "=== $(date)" >> $LOG
while pgrep -f "python3 scripts/exams/ingest.py" >/dev/null; do sleep 60; done
rm -f .cache/exams/claude/*.claim
LANES=flash,lite CONC=40 python3 scripts/exams/ingest.py >> $LOG 2>&1
python3 scripts/exams/postfilter.py >> $LOG 2>&1
vercel --prod --yes >> $LOG 2>&1
if tail -5 $LOG | grep -qE "DONE .* left 0|STOPPED .* left 0"; then
  crontab -l | grep -v 'scripts/exams/daily.sh' | crontab -
  echo "all exams done, cron removed" >> $LOG
fi
