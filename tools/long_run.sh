#!/bin/sh
# Keep the long transcription run going: a fresh Claude Code session for each
# round of up to 10 pages (docs/long-run.md), waiting out usage-limit resets in between.
#
# Start it in a terminal you leave open, ideally inside tmux or screen, and
# stop it any time with Ctrl+C:
#     tools/long_run.sh
# Progress: content/book/PROGRESS.md · log: .cache/long-run.log
# A round's whole session can be opened afterwards with: claude --resume <its session id in the log>
#
# Each session may only read files, edit files under content/, and run the
# project's Python tools; anything else is refused without asking.
cd "$(dirname "$0")/.." || exit 1
LOG=.cache/long-run.log
OUT=.cache/long-run-round.json
PROMPT="Do one round of the long run: follow docs/long-run.md exactly."
TOOLS="Read,Glob,Grep,Edit(content/**),Bash(.venv/bin/python tools/*),Bash(ls *)"
WAIT=1800          # seconds to wait after a round that made no progress (usually a usage limit)
MAX_IDLE_ROUNDS=24 # stop after this many rounds in a row without progress (~12 hours)

# claude -p always uses an API key from the environment instead of the subscription login.
if [ -n "$ANTHROPIC_API_KEY$ANTHROPIC_AUTH_TOKEN" ]; then
    echo "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is set, so every round would be billed to it"
    echo "instead of using your Claude subscription. Unset it first (or remove this check to use the API)."
    exit 1
fi

idle=0
while ! grep -q '^Status: ALL DONE' content/book/PROGRESS.md; do
    before=$(md5sum content/book/PROGRESS.md)
    echo "=== $(date '+%F %T') round starts" >> "$LOG"
    # 10-minute command timeout: the pipeline on a long chapter can outlast the 2-minute default.
    BASH_DEFAULT_TIMEOUT_MS=600000 claude -p "$PROMPT" --permission-mode dontAsk --allowedTools "$TOOLS" \
        --output-format json > "$OUT" 2>> "$LOG"
    # Log the round's session id, length, cost estimate and closing message.
    .venv/bin/python - "$OUT" >> "$LOG" 2>&1 <<'EOF'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
try:
    r = json.loads(raw)
except ValueError:
    print(raw)
    sys.exit()
print(f"session {r.get('session_id')} · {r.get('num_turns')} turns · {r.get('duration_ms', 0) / 60000:.0f} min"
      f" · ≈ ${r.get('total_cost_usd', 0):.2f} at API prices" + (" · ended with an error" if r.get("is_error") else ""))
print(r.get("result", ""))
EOF
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
