#!/usr/bin/env python3
"""Stop hook for the ai-learning-companion teaching skill.

Runs every time the main agent finishes responding. If - and only if -
the turn that just ended did real work (a file-changing tool ran, or a
Bash/PowerShell command that isn't pure navigation/reading), it emits
one hookSpecificOutput.additionalContext note sending Claude back to
check whether a teaching moment applies, with the teaching gate's
current state included. It never decides whether to teach: that stays
with SKILL.md's own update_profile.py --check and arbitration, and that
--check call is also the only thing that advances the cooldown counter.

additionalContext rather than decision "block": the docs describe it as
non-error feedback with the same loop protections as a block
(stop_hook_active and the 8-consecutive-continuation cap), and it
doesn't surface a hook error notification on every nudge.

Loop guard: if stop_hook_active is true, Claude is already continuing
because of a Stop hook (this one or another plugin's), so this exits
silently before reading anything else. One nudge per turn at most,
never a chain.

Read-only: the gate state comes from router.py --gate-status, which
never writes profile.json (not even the shape migration). This hook
never calls --check, --track, or anything else that writes.

Coupling note (intentional, same as session_start.py): this reaches
into skills/ai-learning-companion/scripts/ for router.py, because that
is the one place the profile schema lives.

Fails silently and safely: bad stdin, a missing or unreadable
transcript, or any unexpected error results in no output and exit 0.
A router failure on its own is not treated as an error - the nudge is
still sent with the gate state reported as "unavailable", because
update_profile.py --check makes the real decision either way.

Known limits: the transcript is written asynchronously and may lag at
Stop time. Tool calls come before the final message, so they're
normally present; if they aren't, the hook stays silent rather than
guessing. Edits made inside a subagent live in that subagent's own
transcript and aren't seen here.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
ROUTER_PATH = os.path.join(
    PLUGIN_ROOT, "skills", "ai-learning-companion", "scripts", "router.py"
)

FILE_CHANGE_TOOLS = frozenset(["Edit", "Write", "NotebookEdit"])
COMMAND_TOOLS = frozenset(["Bash", "PowerShell"])

# Commands that only navigate or read. A shell command is trivial only if
# every segment of it starts with one of these and writes nowhere. git is
# deliberately absent: SKILL.md treats git operations as teaching
# candidates in their own right.
TRIVIAL_COMMANDS = frozenset(
    [
        "ls", "cd", "pwd", "cat", "head", "tail", "less", "wc", "echo",
        "grep", "rg", "find", "which", "file", "stat", "tree",
    ]
)

# Arguments that turn an otherwise read-only command (find) into one
# that deletes, runs, or writes something.
_WRITING_ARGS = frozenset(
    ["-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"]
)

_REDIRECT_OUT = frozenset([">", ">>", ">|", "&>", "&>>"])
_SAFE_REDIRECT_TARGETS = frozenset(["/dev/null"])

# Tokens made only of these characters separate or group commands.
_SEPARATOR_CHARS = "();&|\n"

_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _tokenize(command):
    """Split a shell command into tokens, with operators (&&, ||, ;, |,
    redirects, newlines) as their own tokens. Non-POSIX mode keeps quotes
    on quoted tokens, so a quoted ";" or "|" can't be mistaken for an
    operator. Raises ValueError on unbalanced quotes."""
    lexer = shlex.shlex(command, posix=False, punctuation_chars=";&|<>()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    return list(lexer)


def _segments(tokens):
    """Group tokens into simple commands, split on separator tokens."""
    segment = []
    for token in tokens:
        if token and all(ch in _SEPARATOR_CHARS for ch in token):
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def is_trivial_command(command):
    """True if `command` only navigates or reads. Pure.

    Every segment (split on &&, ||, ;, |, &, newlines) must start - after
    any leading VAR=value assignments - with a TRIVIAL_COMMANDS program,
    must not redirect output anywhere but /dev/null, and must not use a
    writing argument like find -delete/-exec. Anything the tokenizer
    can't parse (unbalanced quotes) counts as non-trivial: a spurious
    nudge is cheaper than a missed one.
    """
    try:
        tokens = _tokenize(command or "")
    except ValueError:
        return False
    for segment in _segments(tokens):
        index = 0
        while index < len(segment) and _ENV_ASSIGNMENT.match(segment[index]):
            index += 1
        if index == len(segment):
            continue
        if os.path.basename(segment[index]) not in TRIVIAL_COMMANDS:
            return False
        rest = segment[index + 1:]
        for position, token in enumerate(rest):
            if token in _WRITING_ARGS:
                return False
            if token in _REDIRECT_OUT:
                target = rest[position + 1] if position + 1 < len(rest) else ""
                if target not in _SAFE_REDIRECT_TARGETS:
                    return False
    return True


def _is_turn_start(entry):
    """True for a transcript entry that begins a new turn: a real user
    message, not an injected isMeta entry, not a sidechain entry, and not
    a tool_result coming back mid-turn."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        blocks = [block for block in content if isinstance(block, dict)]
        return bool(blocks) and not all(block.get("type") == "tool_result" for block in blocks)
    return False


def current_turn(entries):
    """The entries of the most recent turn, starting at its user message.
    Pure. With no recognizable turn start, returns every dict entry."""
    entries = [entry for entry in entries if isinstance(entry, dict)]
    for index in range(len(entries) - 1, -1, -1):
        if _is_turn_start(entries[index]):
            return entries[index:]
    return entries


def turn_did_real_work(entries):
    """True if the most recent turn ran a file-changing tool or a
    non-trivial shell command. Pure: `entries` is the parsed transcript
    (a full transcript or just its tail both work)."""
    for entry in current_turn(entries):
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            if name in FILE_CHANGE_TOOLS:
                return True
            if name in COMMAND_TOOLS:
                tool_input = block.get("input")
                command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
                if not is_trivial_command(command):
                    return True
    return False


def should_nudge(payload, entries):
    """The whole decision, minus I/O. Pure. stop_hook_active always wins,
    so a continuation this hook (or any other Stop hook) caused can
    never be nudged again."""
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return False
    return turn_did_real_work(entries)


def describe_gate(gate):
    """Human-readable gate state for the nudge message. Pure."""
    if not isinstance(gate, dict) or "can_teach" not in gate:
        return "unavailable"
    if gate["can_teach"]:
        return "open"
    return "closed (%s of %s gated checks since the last teach)" % (
        gate.get("turns_since_last_teach", 0),
        gate.get("min_gap", "?"),
    )


def build_output(gate):
    """The Stop hook's stdout JSON. Pure."""
    message = (
        "ai-learning-companion Stop hook: this turn did real work (files "
        "changed or a non-trivial command ran). Check whether a teaching "
        "moment applies: use the ai-learning-companion skill and follow its "
        "Steps 2-4. Teaching gate right now: %s. If Step 2 finds a "
        "candidate, run update_profile.py --check even if the gate looks "
        "closed - that call decides, and it is what advances the cooldown. "
        "If nothing qualifies or the gate says no, stop without comment. If "
        "files changed and your reply has no Change Summary yet, add one."
    ) % describe_gate(gate)
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": message,
        }
    }


def read_current_turn(path):
    """Parse only the tail of the transcript JSONL at `path`, back to the
    most recent turn start, so a long session isn't re-parsed on every
    stop. Returns entries in file order; [] for a missing or unreadable
    file. Malformed and non-object lines are skipped."""
    if not path:
        return []
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, ValueError):
        return []
    tail = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        tail.append(entry)
        if _is_turn_start(entry):
            break
    tail.reverse()
    return tail


def query_gate(profile=None):
    """Run router.py --gate-status (read-only). Returns its JSON dict, or
    None on any failure."""
    if not os.path.isfile(ROUTER_PATH):
        return None
    command = [sys.executable, ROUTER_PATH, "--gate-status"]
    if profile:
        command += ["--profile", profile]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        gate = json.loads(result.stdout)
    except ValueError:
        return None
    return gate if isinstance(gate, dict) else None


def main(argv=None):
    parser = argparse.ArgumentParser(description="ai-learning-companion Stop hook")
    parser.add_argument(
        "--profile",
        default=None,
        help="profile.json path passed through to router.py (tests only; hooks.json never sets it)",
    )
    args, _unknown = parser.parse_known_args(argv)
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict) or payload.get("stop_hook_active"):
            return 0
        entries = read_current_turn(payload.get("transcript_path"))
        if not should_nudge(payload, entries):
            return 0
        print(json.dumps(build_output(query_gate(args.profile))))
        return 0
    except Exception:
        # Never block stopping and never surface hook errors to the user.
        return 0


if __name__ == "__main__":
    sys.exit(main())
