#!/usr/bin/env python3
"""Deterministic local router for ai-learning-companion.

Reads profile.json and prints a small "context card" JSON object to
stdout - never the full profile. This is the only interface SKILL.md
should use to learn the learner's level; it must not re-derive
thresholds itself.

This script only reads the state file (upgrading its shape on disk if
it's in the old pre-migration format). It never accepts free-form input
about the learner's progress - level and concepts are always derived
from known_terms / sessions_taught already on disk.

Usage (context card, as before):
    python3 router.py [--profile PATH]

Usage (V3 arbitration - read-only, does not touch the teaching-cooldown
gate; that is checked separately via update_profile.py --check):
    python3 router.py --pick --candidate "<track>:<topic>" [--candidate ...]

Each --candidate is "track:topic" split on the FIRST colon only (so a
topic may itself contain colons), track one of ai_engineering, prompting,
english. Prints {"winner": {...}} or {"winner": null} - see
profile_lib.pick_teaching_moment for the priority rules.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib as lib

VALID_TRACKS = ("ai_engineering", "prompting", "english")


def parse_candidate(raw):
    """Split one --candidate "track:topic" value on the first colon."""
    if ":" not in raw:
        raise ValueError("candidate %r must be \"track:topic\"" % raw)
    track, topic = raw.split(":", 1)
    track = track.strip()
    topic = topic.strip()
    if track not in VALID_TRACKS:
        raise ValueError(
            "candidate %r has unknown track %r (must be one of %s)"
            % (raw, track, ", ".join(VALID_TRACKS))
        )
    if not topic:
        raise ValueError("candidate %r has an empty topic" % raw)
    return track, topic


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=lib.DEFAULT_PROFILE_PATH,
        help="Path to profile.json (default: %(default)s)",
    )
    parser.add_argument(
        "--pick",
        action="store_true",
        help="Arbitrate between --candidate teaching moments instead of printing the context card.",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        dest="candidates",
        help='A candidate teaching moment as "track:topic" (repeatable). Only used with --pick.',
    )
    args = parser.parse_args(argv)

    state, existed = lib.load_state(args.profile)
    migrated_state, changed = lib.migrate(state)

    if existed and changed:
        # Upgrade the on-disk file to the new shape so future runs (and
        # update_profile.py) don't need to migrate it again.
        lib.safe_write_json(args.profile, migrated_state)

    if args.pick:
        try:
            candidates = [parse_candidate(c) for c in args.candidates]
        except ValueError as exc:
            parser.error(str(exc))
        winner = lib.pick_teaching_moment(migrated_state, candidates)
        print(json.dumps({"winner": winner}))
        return 0

    card = lib.build_context_card(migrated_state)
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
