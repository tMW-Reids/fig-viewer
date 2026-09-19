#!/usr/bin/env python3
"""Parse a Figment chat export (.md) into JSON.

The viewer (index.html) reads exports directly, so this is optional. Use it when
you want the messages as JSON for your own scripts.

    python3 parse.py EXPORT.md              # writes EXPORT.json next to the input
    python3 parse.py EXPORT.md -o out.json
    python3 parse.py EXPORT.md -o -         # to stdout

Output: {"companionName": "...", "messages": [{"speaker", "date", "time", "body"}, ...]}
where speaker is "user" or "companion". The viewer accepts this file too.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HEADER_RE = re.compile(r"^\*\*(.+?)\*\* · (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC$")


def _companion_name(lines, first_other):
    """companionName from the Settings JSON block, else the H1, else the first non-You speaker."""
    stripped = [l.strip() for l in lines]
    try:
        s = stripped.index("## Settings")
        f = stripped.index("```json", s)
        e = stripped.index("```", f + 1)
        name = json.loads("\n".join(lines[f + 1:e])).get("companionName")
        if name:
            return str(name)
    except (ValueError, json.JSONDecodeError, AttributeError):
        pass
    h1 = next((l[2:].strip() for l in lines if l.startswith("# ") and l[2:].strip()), "")
    return h1 or first_other or "companion"


def parse(text):
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    stripped = [l.strip() for l in lines]
    start = stripped.index("## Conversation") + 1 if "## Conversation" in stripped else 0

    messages = []
    first_other = ""
    i, n = start, len(lines)
    while i < n:
        m = HEADER_RE.match(stripped[i])
        if not m:
            i += 1
            continue
        speaker, date, time = m.groups()
        i += 1
        body = []
        while i < n and not HEADER_RE.match(stripped[i]):
            body.append(lines[i])
            i += 1
        while body and body[0].strip() == "":
            body.pop(0)
        while body and body[-1].strip() == "":
            body.pop()
        is_user = speaker == "You"
        if not is_user and not first_other:
            first_other = speaker
        messages.append({
            "speaker": "user" if is_user else "companion",
            "date": date,
            "time": time,
            "body": "\n".join(body),
        })

    return {"companionName": _companion_name(lines, first_other), "messages": messages}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Parse a Figment chat export into JSON.")
    ap.add_argument("export", type=Path, help="the .md export file")
    ap.add_argument("-o", "--out", help="output path (default: next to the input; '-' for stdout)")
    args = ap.parse_args(argv)

    result = parse(args.export.read_text(encoding="utf-8"))
    payload = json.dumps(result, ensure_ascii=False)
    if args.out == "-":
        sys.stdout.write(payload + "\n")
        return
    out = Path(args.out) if args.out else args.export.with_suffix(".json")
    out.write_text(payload, encoding="utf-8")
    print(f"{result['companionName']}: {len(result['messages'])} messages -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
