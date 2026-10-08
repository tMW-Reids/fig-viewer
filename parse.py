#!/usr/bin/env python3
"""Parse a Figment chat export (.md) into JSON.

The viewer (index.html) reads exports directly, so this is optional. Use it when
you want the messages as JSON for your own scripts.

    python3 parse.py EXPORT.md              # writes EXPORT.json next to the input
    python3 parse.py EXPORT.md -o out.json
    python3 parse.py EXPORT.md -o -         # to stdout

Output: {"companionName": "...", "messages": [{"speaker", "date", "time", "body"}, ...]}
where speaker is "user" or "companion". The viewer accepts this file too.

A message also carries "thought" when the export has one for it; see
_inner_thoughts below. The app's own exports never do.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HEADER_RE = re.compile(r"^\*\*(.+?)\*\* · (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC$")

# Inner thoughts (an enriched export only; see _inner_thoughts below).
THOUGHT_HEADING = "## Inner Thoughts"
THOUGHT_INDEX_RE = re.compile(r"^### (\d+)$")
THOUGHT_FENCE_RE = re.compile(r"^(`{3,})([^\s`]*)\s*$")


def _inner_thoughts(lines, before):
    """{message index: thought} from the "## Inner Thoughts" section above `before`.

    The app renders a companion's inner thought outside and above the bubble, so
    its own export drops it. fig-chat-export recovers it from the DOM and writes
    it into an enriched export as its own section, ahead of "## Conversation":

        ## Inner Thoughts

        ### 5

        ```text
        the thought
        ```

    The section is placed there because this parser — like the viewer's, and any
    older copy of either — reads every line between two message headers into that
    message's body. A thought written next to its own message would be swallowed
    into the *previous* message's body and change what is rendered. Everything
    before "## Conversation" is skipped instead, so this section is invisible to
    a parser that does not know about it, and the conversation below stays the
    app's own bytes.

    The index is the 0-based position of the message in the conversation, so an
    entry only ever annotates a message that exists. A thought is stored with the
    backtick run that closes it made longer than any run inside it, so a thought
    cannot terminate its own block.
    """
    at = next((i for i in range(min(before, len(lines))) if lines[i].strip() == THOUGHT_HEADING), -1)
    if at == -1:
        return {}
    out = {}
    i = at + 1
    while i < before:
        if lines[i].strip().startswith("## "):
            break
        m = THOUGHT_INDEX_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        j = i + 1
        while j < before and lines[j].strip() == "":
            j += 1
        fence = THOUGHT_FENCE_RE.match(lines[j].strip()) if j < before else None
        if not fence or (fence.group(2) and fence.group(2) != "text"):
            i += 1
            continue
        run, body, k = len(fence.group(1)), [], j + 1
        while k < before:
            close = THOUGHT_FENCE_RE.match(lines[k].strip())
            if close and len(close.group(1)) >= run:
                break
            body.append(lines[k])
            k += 1
        out[int(m.group(1))] = "\n".join(body).strip()
        i = k + 1
    return out


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
    thoughts = _inner_thoughts(lines, start)

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
        message = {
            "speaker": "user" if is_user else "companion",
            "date": date,
            "time": time,
            "body": "\n".join(body),
        }
        # Only when there is one, so an export without a thoughts section parses
        # to exactly the JSON it did before.
        thought = thoughts.get(len(messages))
        if thought:
            message["thought"] = thought
        messages.append(message)

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
