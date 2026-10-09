#!/bin/sh
# Keep the long transcription run going: one chapter per fresh Claude Code
# session (docs/long-run.md), waiting out usage-limit resets in between.
#
# Start it in a terminal you leave open, ideally inside tmux or screen, and
# stop it any time with Ctrl+C:
#     tools/long_run.sh
# Progress: content/book/PROGRESS.md · log: .cache/long-run.log
#
# Each session may only read files, edit files under content/, and run the
# project's Python tools; anything else is refused without asking.
cd "$(dirname "$0")/.." || exit 1
LOG=.cache/long-run.log
PROMPT="Do one round of the long run: follow docs/long-run.md exactly."
TOOLS="Read,Glob,Grep,Edit(content/**),Bash(.venv/bin/python *),Bash(ls *)"
WAIT=1800          # seconds to wait after a round that made no progress (usually a usage limit)
MAX_IDLE_ROUNDS=24 # stop after this many rounds in a row without progress (~12 hours)

idle=0
while ! grep -q '^Status: ALL DONE' content/book/PROGRESS.md; do
    before=$(md5sum content/book/PROGRESS.md)
    echo "=== $(date '+%F %T') round starts" >> "$LOG"
    # 10-minute command timeout: the pipeline on a long chapter can outlast the 2-minute default.
    BASH_DEFAULT_TIMEOUT_MS=600000 claude -p "$PROMPT" --permission-mode dontAsk --allowedTools "$TOOLS" >> "$LOG" 2>&1
    if [ "$(md5sum content/book/PROGRESS.md)" = "$before" ]; then
        idle=$((idle + 1))
        if [ "$idle" -ge "$MAX_IDLE_ROUNDS" ]; then
            echo "=== $(date '+%F %T') no progress in $idle rounds; stopping" >> "$LOG"
            echo "Stopped: no progress in $idle rounds. See $LOG."
            exit 1
        fi
        echo "=== $(date '+%F %T') no progress (usage limit?); waiting $((WAIT / 60)) minutes" >> "$LOG"
        sleep "$WAIT"
    else
        idle=0
    fi
done
echo "All chapters are done. See content/book/PROGRESS.md."
