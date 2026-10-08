#!/usr/bin/env python3
"""Checks for parse.py. Standard library only, no test framework:

    python3 tests/test_parse.py

Exits non-zero on failure. The load-bearing claim is additivity: an export enriched
with an "## Inner Thoughts" section parses to the same messages, with the same bodies,
as the export it was made from — and an export without the section is unaffected.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import parse  # noqa: E402

PLAIN = ROOT / "sample" / "sample-export.md"
RICH = ROOT / "sample" / "sample-export-thoughts.md"

failures = []
checks = 0


def check(name, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}\n      got:  {got!r}\n      want: {want!r}")


def fail(name, detail):
    global checks
    checks += 1
    failures.append(f"{name}: {detail}")


def without_thoughts(messages):
    return [{k: v for k, v in m.items() if k != "thought"} for m in messages]


def boundaries(text):
    """Line indices of the "## Inner Thoughts" and "## Conversation" headings.

    Matched as whole lines, the way the parser does. A substring search would land
    inside the section's own prose, which mentions `## Conversation` in backticks.
    """
    lines = text.split("\n")
    at = next(n for n, l in enumerate(lines) if l.strip() == "## Inner Thoughts")
    conv = next(n for n, l in enumerate(lines) if l.strip() == "## Conversation")
    return lines, at, conv


def strip_section(text):
    """`text` with its "## Inner Thoughts" section removed."""
    lines, at, conv = boundaries(text)
    return "\n".join(lines[:at] + lines[conv:])


def replace_section(text, section):
    """`text` with its section replaced by `section` (one line per line)."""
    lines, at, conv = boundaries(text)
    body = section.split("\n")
    while body and body[-1] == "":
        body.pop()
    return "\n".join(lines[:at] + body + [""] + lines[conv:])


def main():
    plain_text, rich_text = PLAIN.read_text(encoding="utf-8"), RICH.read_text(encoding="utf-8")
    plain, rich = parse.parse(plain_text), parse.parse(rich_text)
    thought_at = lambda r: [i for i, m in enumerate(r["messages"]) if "thought" in m]

    # ── the fixture pair ────────────────────────────────────────────────────
    check("plain sample carries no thought key", thought_at(plain), [])
    check("enriched sample has the same message count", len(rich["messages"]), len(plain["messages"]))
    check("enriched sample has the same companion name", rich["companionName"], plain["companionName"])
    check("thoughts sit at the indices the section names", thought_at(rich), [3, 5, 9, 15, 19, 21, 27, 33])
    check(
        "every thought is attached to a companion message",
        [m["speaker"] for m in rich["messages"] if "thought" in m],
        ["companion"] * 8,
    )

    # ── additivity: the whole point of the section's placement ──────────────
    check("additivity: messages identical apart from the thought key",
          without_thoughts(rich["messages"]), plain["messages"])
    check("additivity: the same holds when the section is removed outright",
          parse.parse(strip_section(rich_text)), plain)

    # ── the fence rule: a thought cannot terminate its own block ────────────
    # .get, so a parser with no thought support reports this as its own failure
    # rather than dying here and hiding the checks below.
    fenced = rich["messages"][21].get("thought", "")
    check("a thought containing a ```text block survives intact",
          ("\n```text\none tortoise, one hundred and twelve stairs, fog, one gull, no plot\n```\n" in fenced
           and fenced.endswith("That is the plot. Do not add to it.")), True)

    # ── nothing from the section may reach a message body ───────────────────
    bodies = "\n".join(m["body"] for m in rich["messages"])
    for marker in ("Inner Thoughts", "This section was added by", "one gull, no plot",
                   "he will not look at it"):
        check(f"no leak of {marker!r} into any body", marker in bodies, False)

    # ── malformed input must not throw and must not corrupt the conversation ─
    intact = without_thoughts(parse.parse(strip_section(rich_text))["messages"])
    # Only the unterminated block yields a thought at all: its body runs to the end of
    # the section. Every other shape is skipped, never guessed at.
    for name, section, expected in [
        ("an index with no block", "## Inner Thoughts\n\n### 5\n\n", []),
        ("an unterminated block", "## Inner Thoughts\n\n### 5\n\n```text\nno end\n\n", [5]),
        ("an index past the end", "## Inner Thoughts\n\n### 999\n\n```text\nx\n```\n\n", []),
        ("a non-numeric index", "## Inner Thoughts\n\n### five\n\n```text\nx\n```\n\n", []),
        ("a foreign fence language", "## Inner Thoughts\n\n### 5\n\n```json\n{}\n```\n\n", []),
        ("a negative index", "## Inner Thoughts\n\n### -1\n\n```text\nx\n```\n\n", []),
        ("no section body at all", "## Inner Thoughts\n\n", []),
        ("fewer hashes than the heading", "## Inner Thoughts\n\n## Inner Thoughts\n\n", []),
    ]:
        text = replace_section(rich_text, section)
        try:
            got = parse.parse(text)
        except Exception as exc:  # noqa: BLE001 - the point is that nothing escapes
            fail(f"{name} raised", f"{type(exc).__name__}: {exc}")
            continue
        check(f"{name}: thoughts attached",
              [i for i, m in enumerate(got["messages"]) if "thought" in m], expected)
        check(f"{name}: bodies untouched", without_thoughts(got["messages"]), intact)

    # ── the heading inside a message body is not a section ──────────────────
    # Spliced into a *message body* (below "## Conversation"), carrying an entry that
    # would otherwise attach to message 5. Something that looked for the heading
    # anywhere in the file would read a thought straight out of the conversation text.
    smuggled = ("## Inner Thoughts\n\n### 5\n\n```text\nsmuggled from a body\n```\n\n"
                "Lists are easier to start when they're shorter.")
    no_section = strip_section(rich_text)
    check("the sample line the heading is spliced onto appears exactly once",
          no_section.count("Lists are easier to start"), 1)
    moved = no_section.replace("Lists are easier to start", smuggled, 1)
    got = parse.parse(moved)
    check("a heading spliced into a message body attaches no thought",
          [i for i, m in enumerate(got["messages"]) if "thought" in m], [])
    check("...and the spliced text stays inside that message's body",
          "smuggled from a body" in got["messages"][3]["body"], True)
    check("...leaving every message's speaker, date and time untouched",
          [{k: v for k, v in m.items() if k != "body"} for m in got["messages"]],
          [{k: v for k, v in m.items() if k != "body"} for m in plain["messages"]])

    # ── the CLI keeps working ───────────────────────────────────────────────
    import json
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "parse.py"), str(PLAIN), "-o", "-"],
                       capture_output=True, text=True)
    check("parse.py CLI exits 0", r.returncode, 0)
    check("parse.py CLI emits the plain sample's message count",
          len(json.loads(r.stdout)["messages"]), len(plain["messages"]))
    check("parse.py CLI writes no thought key for the plain sample", "thought" in r.stdout, False)

    if failures:
        print(f"FAIL ({len(failures)} of {checks} checks)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"ok ({checks} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
