#!/bin/sh
# Keep the long transcription run going: a fresh Claude Code session for each
# round of up to 5 pages (docs/long-run.md), waiting out usage-limit resets in between.
#
# Start it from the project folder in the background, so it keeps going after the terminal closes:
#     setsid nohup tools/long_run.sh >> .cache/long-run.log 2>&1 &
# Stop it (the loop and the round in progress):
#     pkill -f '^/bin/sh tools/long_run.sh'; pkill -f '^claude -p Do one round'
# Progress: content/book/PROGRESS.md · log: .cache/long-run.log (follow it with: tail -F .cache/long-run.log)
# A round's whole session can be opened afterwards with: claude --resume <its session id in the log>
#
# Each session may only read files, edit files under content/, and run the
# project's Python tools; anything else is refused without asking.
cd "$(dirname "$0")/.." || exit 1
LOG=.cache/long-run.log
OUT=.cache/long-run-round.jsonl
PROBE=.cache/long-run-limits.jsonl
BEFORE=.cache/long-run-progress.md
PROMPT="Do one round of the long run: follow docs/long-run.md exactly."
TOOLS="Read,Glob,Grep,Edit(content/**),Bash(.venv/bin/python tools/*),Bash(ls *)"
# The only built-in tools a round uses. Leaving out the others, the MCP servers and the skills
# cuts the session's base prompt from about 22K tokens to 9K.
BUILTIN="Read,Glob,Grep,Edit,Write,Bash"
# Pinned, so that changing the model or effort in another session (saved in ~/.claude/settings.json)
# doesn't change the run. Tested on 2026-10-13/14 on the Adhan chapter: Sonnet made errors Opus didn't
# (one an added tashkeel mark), and Opus at low effort transcribed 11 pages with no slips (xhigh: 4
# slips in 14 pages) at about a third of the cost. Review rounds judge corrections, which the test
# didn't cover, so they keep xhigh.
MODEL=claude-opus-5-5
TRANSCRIBE_EFFORT=low
REVIEW_EFFORT=xhigh
# Start a round only while the 5-hour window is below this percent: a 5-page round uses up to
# about 25% of it (15-20% measured on 2026-10-13), and a round cut off by the limit loses its page.
FIVE_HOUR_START=${FIVE_HOUR_START:-70}
WAIT=1800          # seconds to wait after a round that made no progress
MAX_IDLE_ROUNDS=24 # stop after this many rounds in a row without progress (~12 hours)

# claude -p always uses an API key from the environment instead of the subscription login.
if [ -n "$ANTHROPIC_API_KEY$ANTHROPIC_AUTH_TOKEN" ]; then
    echo "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is set, so every round would be billed to it"
    echo "instead of using your Claude subscription. Unset it first (or remove this check to use the API)."
    exit 1
fi

# Anthropic's peak hours: weekdays 5-11 a.m. Pacific time (15:00-21:00 in Cairo most of the year).
# The 5-hour limit runs out faster then; the weekly limit doesn't.
peak_hours() {
    set -- $(TZ=America/Los_Angeles date '+%u %H')
    [ "$1" -le 5 ] && [ "${2#0}" -ge 5 ] && [ "${2#0}" -lt 11 ]
}

# Read how much of the usage limits is used, with a one-word Haiku request.
read_limits() {
    claude -p "Reply with the single word OK." --model haiku --tools "" --strict-mcp-config \
        --disable-slash-commands --no-session-persistence --output-format stream-json --verbose \
        > "$PROBE" 2>> "$LOG"
}

idle=0
while ! grep -q '^Status: ALL DONE' content/book/PROGRESS.md; do
    read_limits
    wait=$(.venv/bin/python tools/long_run.py wait "$PROBE" "$FIVE_HOUR_START")
    if [ "${wait%% *}" -gt 0 ] 2>/dev/null; then
        echo "=== $(date '+%F %T') ${wait#* }" >> "$LOG"
        sleep "${wait%% *}"
        continue
    fi
    cat content/book/PROGRESS.md > "$BEFORE"
    # "transcribe SLUG" or "review SLUG": the chapter the round will pick, and so its effort.
    next=$(.venv/bin/python tools/long_run.py next)
    effort=$TRANSCRIBE_EFFORT
    [ "${next%% *}" = review ] && effort=$REVIEW_EFFORT
    peak=""
    peak_hours && peak=" · peak hours: the 5-hour limit runs out faster now (the weekly one doesn't)"
    echo "=== $(date '+%F %T') round starts ($next, effort $effort)$peak" >> "$LOG"
    # 10-minute command timeout: the pipeline on a long chapter can outlast the 2-minute default.
    # A 5-minute prompt cache: on a subscription the default is 1 hour, whose cache writes cost
    # more, and calls in a round come at most about 2 minutes apart.
    BASH_DEFAULT_TIMEOUT_MS=600000 CLAUDE_CODE_PROMPT_CACHE_TTL=5m claude -p "$PROMPT" \
        --model "$MODEL" --effort "$effort" --permission-mode dontAsk --allowedTools "$TOOLS" --tools "$BUILTIN" --strict-mcp-config \
        --disable-slash-commands --output-format stream-json --verbose > "$OUT" 2>> "$LOG"
    # Log the round's session id, length, cost estimate, limits used, status changes and closing message.
    .venv/bin/python tools/long_run.py report "$OUT" "$PROBE" "$BEFORE" >> "$LOG" 2>&1
    if cmp -s "$BEFORE" content/book/PROGRESS.md; then
        idle=$((idle + 1))
        if [ "$idle" -ge "$MAX_IDLE_ROUNDS" ]; then
            echo "=== $(date '+%F %T') no progress in $idle rounds; stopping" >> "$LOG"
            echo "Stopped: no progress in $idle rounds. See $LOG."
            exit 1
        fi
        echo "=== $(date '+%F %T') no progress; waiting $((WAIT / 60)) minutes" >> "$LOG"
        sleep "$WAIT"
    else
        idle=0
    fi
done
echo "All chapters are done. See content/book/PROGRESS.md."
