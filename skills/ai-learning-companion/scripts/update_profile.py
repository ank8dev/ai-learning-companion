#!/usr/bin/env python3
"""The only writer of profile.json for ai-learning-companion.

SKILL.md must never hand-edit profile.json itself - after a digest, it
reports which terms were newly covered and calls this script, which is
the sole place that mutates the file.

Crash-safety: the entire new state (new terms, incremented
sessions_taught, incremented task_type_counts, and the result of
compute_level) is built up in a single in-memory dict first. Only after
all of that succeeds does the script write - once, atomically - via
profile_lib.safe_write_json. If anything raises before that point
(including compute_level itself), the function returns/exits without
ever calling safe_write_json, so profile.json on disk is left exactly
as it was. There is no separate "save terms" then "save level" step
that could leave the file half-updated.

Usage:
    python3 update_profile.py [--profile PATH] [--term TERM ...] [--task-type TYPE]

Prints the refreshed context card (same shape as router.py) to stdout,
so SKILL.md doesn't need a second process call to see the new level.
"""

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib as lib


def build_updated_state(state, new_terms, task_type, today=None):
    """Pure-ish builder: takes the current (already-migrated) state and
    returns a brand new state dict with terms/counters/level applied.
    Does not touch disk and does not mutate the input.
    """
    today = today or date.today().isoformat()

    new_state = dict(state)
    new_state["known_terms"] = dict(state.get("known_terms", {}))
    new_state["task_type_counts"] = dict(state.get("task_type_counts", {}))

    for term in new_terms:
        if term not in new_state["known_terms"]:
            new_state["known_terms"][term] = today

    new_state["sessions_taught"] = state.get("sessions_taught", 0) + 1

    if task_type:
        new_state["task_type_counts"][task_type] = (
            new_state["task_type_counts"].get(task_type, 0) + 1
        )

    level_result = lib.compute_level(new_state, today=today)
    new_state["level"] = level_result["level"]
    new_state["level_history"] = level_result["level_history"]
    new_state["level_watch"] = level_result["level_watch"]

    return new_state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=lib.DEFAULT_PROFILE_PATH,
        help="Path to profile.json (default: %(default)s)",
    )
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        dest="terms",
        help="A newly-covered term to add (repeatable)",
    )
    parser.add_argument(
        "--task-type",
        default=None,
        help="e.g. refactor, newfeature - increments task_type_counts",
    )
    args = parser.parse_args(argv)

    state, _existed = lib.load_state(args.profile)
    state, _changed = lib.migrate(state)

    # Everything above and below this line is in-memory only. Nothing
    # on disk changes until the single safe_write_json call after this.
    new_state = build_updated_state(state, args.terms, args.task_type)

    lib.safe_write_json(args.profile, new_state)

    card = lib.build_context_card(new_state)
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
