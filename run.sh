#!/bin/bash
# run.sh — Daily cron entry point.
# Fetches emails, generates summaries, sends appropriate emails.
#
# Crontab:
#   Daily Mon–Fri at 08:30: 30 8 * * 1-5 "..." >> run.log 2>&1
#   Weekly Saturday at 07:00: 0 7 * * 6 "..." >> run.log 2>&1

set -e
cd "$(dirname "$0")"

# Use the project's virtualenv
source .venv/bin/activate

TODAY=$(date +%Y-%m-%d)
DOW=$(date +%u)   # 1=Mon … 7=Sun

echo ""
echo "=== $(date '+%Y-%m-%d %H:%M:%S') — Bloomberg Archiver ==="

# 1. Fetch new emails from Gmail
echo "[1/4] Fetching emails..."
python3 fetch.py

# 2. Generate daily summary (exits cleanly if no emails today)
echo "[2/4] Generating daily summary..."
if python3 summarize.py --date "$TODAY" --mode daily; then
    # 3. Send daily email
    echo "[3/4] Sending daily email..."
    python3 send_brief.py --mode daily --date "$TODAY"
else
    echo "[3/4] Skipping daily email — no content."
fi

# 4a. On Saturday: weekly summary + email
if [ "$DOW" = "6" ]; then
    echo "[4/4] Saturday — generating weekly summary..."
    if python3 summarize.py --date "$TODAY" --mode weekly; then
        python3 send_brief.py --mode weekly --date "$TODAY"
    fi
fi

# 4b. On last day of month: monthly summary + email
LAST_DAY=$(python3 -c "
from datetime import datetime, timedelta
d = datetime.strptime('$TODAY', '%Y-%m-%d').replace(day=28) + timedelta(days=4)
print((d - timedelta(days=d.day)).strftime('%d'))
")
if [ "$(date +%d)" = "$LAST_DAY" ]; then
    echo "[4/4] Last day of month — generating monthly summary..."
    if python3 summarize.py --date "$TODAY" --mode monthly; then
        python3 send_brief.py --mode monthly --date "$TODAY"
    fi
fi

echo "=== Done $(date '+%H:%M:%S') ==="
