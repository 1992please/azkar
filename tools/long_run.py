"""Helpers for tools/long_run.sh: read the Claude usage limits, and sum up a round for the log.

Usage: python tools/long_run.py wait PROBE START
       python tools/long_run.py next [PROGRESS]
       python tools/long_run.py report ROUND PROBE PROGRESS_BEFORE

PROBE and ROUND are the output of `claude -p ... --output-format stream-json --verbose`.
Its rate_limit_event lines give the account's use of the 5-hour and the weekly limit
(0 to 1) and when each resets.

wait prints "SECONDS REASON": how long to wait before the next round may start (0: start now).
A round doesn't start while the 5-hour window is at START percent or more, because a round
cut off by the limit loses the page it was working on (tools/long_run.sh gives transcription
and review rounds different STARTs). When a limit is reached (the 5-hour or the weekly one),
the next round waits until it resets.

next prints what the next round will do and on which chapter: "transcribe SLUG", "review SLUG"
or "none". It picks the chapter as docs/long-run.md tells the round to: the first in the table
whose status is `in progress`, `transcribed` or `todo`.

report prints the log lines for a finished round: its length and cost, how much of each
limit it used, the chapter statuses it changed in PROGRESS.md, and its closing message.
"""

import argparse
import datetime
import json
import pathlib
import time

from book import PROGRESS, statuses

NAMES = {"five_hour": "5-hour", "seven_day": "weekly"}


def read_stream(path: str) -> list[dict]:
    events = []
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def limits(events: list[dict]) -> tuple[dict, tuple | None]:
    """{window: (use 0-1, reset time)} as last reported, and (window, reset time) if a request was refused."""
    windows, refused = {}, None
    for event in events:
        if event.get("type") != "rate_limit_event":
            continue
        info = event.get("rate_limit_info") or {}
        for name, window in (info.get("unifiedWindows") or {}).items():
            windows[name] = (window.get("utilization"), window.get("resetsAt"))
        if info.get("status") == "rejected" and info.get("resetsAt"):
            refused = (info.get("rateLimitType"), info["resetsAt"])
    return windows, refused


def when(timestamp: float) -> str:
    return datetime.datetime.fromtimestamp(timestamp).strftime("%a %F %H:%M")


def wait(args: argparse.Namespace) -> None:
    windows, refused = limits(read_stream(args.probe))
    now = time.time()
    waits = []
    if refused and refused[1] > now:
        waits.append((refused[1], f"the {NAMES.get(refused[0], refused[0])} limit is reached"))
    use, reset = windows.get("five_hour", (None, None))
    if use is not None and reset and reset > now and use * 100 >= args.start:
        waits.append((reset, f"the 5-hour limit is at {use:.0%} (this round starts below {args.start:g}%)"))
    if not waits:
        print("0 go")
        return
    reset, reason = max(waits)
    # A minute's margin, so the next check sees the window already reset.
    print(f"{int(reset - now) + 60} {reason}; waiting until it resets on {when(reset)}")


def next_round(args: argparse.Namespace) -> None:
    for slug, status in statuses(pathlib.Path(args.progress).read_text(encoding="utf-8")).items():
        if status.startswith("transcribed"):
            print(f"review {slug}")
            return
        if status.startswith(("in progress", "todo")):
            print(f"transcribe {slug}")
            return
    print("none")


def report(args: argparse.Namespace) -> None:
    events = read_stream(args.round)
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        print(f"the round ended without a result; its output is in {args.round}")
    else:
        print(f"session {result.get('session_id')} · {result.get('num_turns')} turns"
              f" · {result.get('duration_ms', 0) / 60000:.0f} min"
              f" · ≈ ${result.get('total_cost_usd', 0):.2f} at API prices"
              + (" · ended with an error" if result.get("is_error") else ""))

    before, _ = limits(read_stream(args.probe))
    after, _ = limits(events)
    used = []
    for name, label in NAMES.items():
        if name not in after:
            continue
        use, reset = after[name]
        old, old_reset = before.get(name, (None, None))
        if old is not None and old_reset == reset:
            used.append(f"{label} {old:.0%} → {use:.0%} (+{(use - old) * 100:.0f})")
        else:
            used.append(f"{label} {use:.0%}")
    if used:
        print("limits: " + " · ".join(used))

    old = statuses(pathlib.Path(args.progress_before).read_text(encoding="utf-8"))
    new = statuses(PROGRESS.read_text(encoding="utf-8"))
    for slug, status in new.items():
        if old.get(slug) != status:
            print(f"{slug}: {old.get(slug)} → {status}")

    if result is not None:
        print(result.get("result", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("wait")
    w.add_argument("probe")
    w.add_argument("start", type=float)
    n = commands.add_parser("next")
    n.add_argument("progress", nargs="?", default=str(PROGRESS))
    r = commands.add_parser("report")
    r.add_argument("round")
    r.add_argument("probe")
    r.add_argument("progress_before")
    args = parser.parse_args()
    {"wait": wait, "next": next_round, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
