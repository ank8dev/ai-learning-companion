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

V2 usage (unchanged - still increments sessions_taught unconditionally,
still never touches the V3 gate/teaching fields):
    python3 update_profile.py [--profile PATH] [--term TERM ...] [--task-type TYPE]

V3 gate check - SKILL.md must call this BEFORE deciding what to teach,
and skip the digest entirely if "can_teach" comes back false. This is a
separate write (it advances turns_since_last_teach and records any
observed struggle patterns) that does NOT run the V2 update above and
does NOT touch known_terms/sessions_taught/level:
    python3 update_profile.py --check [--observe-pattern DESC ...] [--min-gap N]
    -> {"can_teach": bool, "turns_since_last_teach": N, "min_gap": N}

V3 teaching event - call once, after the digest, to record what was
actually taught (this is what resets the gate). Combine with --term/
--task-type in the same call if the same digest also covers V2-style
known-term coverage:
    python3 update_profile.py --track ai_engineering --topic mcp [--status understood]
    python3 update_profile.py --track prompting --topic "few-shot examples"
    python3 update_profile.py --track english --pattern "missing article before uncountable noun"
    python3 update_profile.py --track english --term "onboarding"

Prints the refreshed context card (same shape as router.py) to stdout
for every mode except --check, so SKILL.md doesn't need a second process
call to see the new level.
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


def apply_teaching_event(state, track, topic, status, pattern, terms, today=None):
    """Layer a V3 teaching-event record on top of a state that has
    already been through build_updated_state. Pure-ish: returns a new
    state dict, does not mutate the input.

    Always: appends one teaching_history entry, sets last_taught_at to
    today, and resets turns_since_last_teach to 0 - this is the only
    thing that resets the gate.

    track="ai_engineering"/"prompting": upserts state["ai_engineering"][
    normalize_topic(topic)], bumping times_seen and last_seen. Status
    only ever moves up (seen -> understood -> practiced): a new topic
    defaults to "seen"; an existing one keeps its status unless --status
    requests something ranked higher.

    track="english": either upserts a struggle_patterns entry (matched
    via normalize_topic, so casing/wording drift can't fragment it -
    creates it at count=1 if this is its first mention, otherwise just
    refreshes last_seen without touching count, since count is meant to
    reflect *observed* recurrences from tick_gate, not teaching passes),
    or - if no pattern was given - treats the first newly-covered --term
    as the vocabulary word this event taught.
    """
    today = today or date.today().isoformat()
    new_state = dict(state)
    new_state["ai_engineering"] = dict(state.get("ai_engineering", {}))
    new_state["struggle_patterns"] = [dict(p) for p in state.get("struggle_patterns", [])]
    new_state["teaching_history"] = list(state.get("teaching_history", []))

    status_rank = {None: 0, "seen": 1, "understood": 2, "practiced": 3}

    if track in ("ai_engineering", "prompting"):
        key = lib.normalize_topic(topic)
        entry = dict(new_state["ai_engineering"].get(key, {}))
        existing_status = entry.get("status")
        requested_status = status or existing_status or "seen"
        if status_rank.get(requested_status, 0) >= status_rank.get(existing_status, 0):
            entry["status"] = requested_status
        entry["times_seen"] = entry.get("times_seen", 0) + 1
        entry["last_seen"] = today
        new_state["ai_engineering"][key] = entry
        recorded_topic = topic
    else:  # english
        if pattern:
            key = lib.normalize_topic(pattern)
            match = next(
                (
                    p
                    for p in new_state["struggle_patterns"]
                    if lib.normalize_topic(p.get("pattern", "")) == key
                ),
                None,
            )
            if match:
                match["last_seen"] = today
            else:
                new_state["struggle_patterns"].append(
                    {"pattern": pattern, "count": 1, "last_seen": today}
                )
            recorded_topic = pattern
        else:
            recorded_topic = terms[0] if terms else None

    new_state["teaching_history"].append(
        {"track": track, "topic": recorded_topic, "at": today}
    )
    new_state["last_taught_at"] = today
    new_state["turns_since_last_teach"] = 0

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
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Advance the teaching-cooldown gate one step and report "
            "whether teaching is allowed right now. Must be checked "
            "before deciding what to teach; mutually exclusive with "
            "recording a teaching event."
        ),
    )
    parser.add_argument(
        "--observe-pattern",
        action="append",
        default=[],
        dest="observed_patterns",
        help=(
            "An English struggle pattern seen this turn (repeatable). "
            "Only meaningful with --check: bumps struggle_patterns "
            "count/last_seen without teaching it, so a recurring "
            "pattern can reach the tier-2 threshold even while gated."
        ),
    )
    parser.add_argument(
        "--min-gap",
        type=int,
        default=lib.DEFAULT_MIN_TEACH_GAP,
        help="Gated checks required since the last teach before --check reports can_teach=true (default: %(default)s)",
    )
    parser.add_argument(
        "--track",
        choices=["ai_engineering", "prompting", "english"],
        default=None,
        help="Record a teaching event on this track (resets the gate). See module docstring for the exact flag combinations per track.",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Topic name for an ai_engineering/prompting teaching event. Required with --track ai_engineering|prompting; not valid with --track english.",
    )
    parser.add_argument(
        "--status",
        choices=["seen", "understood", "practiced"],
        default=None,
        help="Status for --topic. Status only ever moves up - omit to leave an existing topic's status as-is (a brand-new topic defaults to 'seen').",
    )
    parser.add_argument(
        "--pattern",
        default=None,
        help="Struggle-pattern description for an english teaching event, e.g. 'missing article before uncountable noun'. Omit to instead teach a plain vocabulary word via --term.",
    )
    args = parser.parse_args(argv)

    if args.check:
        if args.track or args.topic or args.status or args.pattern or args.terms or args.task_type:
            parser.error("--check cannot be combined with any teaching-event or V2 flags")
        state, _existed = lib.load_state(args.profile)
        state, _changed = lib.migrate(state)
        new_state = lib.tick_gate(state, observed_patterns=args.observed_patterns)
        can_teach = lib.can_teach_now(new_state, min_gap=args.min_gap)
        lib.safe_write_json(args.profile, new_state)
        print(
            json.dumps(
                {
                    "can_teach": can_teach,
                    "turns_since_last_teach": new_state["turns_since_last_teach"],
                    "min_gap": args.min_gap,
                }
            )
        )
        return 0

    if args.track in ("ai_engineering", "prompting"):
        if not args.topic:
            parser.error("--track %s requires --topic" % args.track)
        if args.pattern:
            parser.error("--pattern is only valid with --track english")
    elif args.track == "english":
        if args.topic:
            parser.error("--topic is not valid with --track english - use --pattern or --term")
        if not args.pattern and not args.terms:
            parser.error("--track english requires --pattern or --term")

    today = date.today().isoformat()

    state, _existed = lib.load_state(args.profile)
    state, _changed = lib.migrate(state)

    # Everything above and below this line is in-memory only. Nothing
    # on disk changes until the single safe_write_json call after this.
    new_state = build_updated_state(state, args.terms, args.task_type, today=today)

    if args.track:
        new_state = apply_teaching_event(
            new_state, args.track, args.topic, args.status, args.pattern, args.terms, today=today
        )

    lib.safe_write_json(args.profile, new_state)

    card = lib.build_context_card(new_state)
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
