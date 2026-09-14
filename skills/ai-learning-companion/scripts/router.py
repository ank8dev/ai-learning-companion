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
profile_lib.pick_teaching_moment for the priority rules. An
ai_engineering/prompting winner also carries "explanation_tier" (full,
short, reminder, mention, or silent - see profile_lib.explanation_tier);
an english winner does not.

Usage (project-explorer - read-only, does not write anything, including
the migration upgrade the other modes perform; independent of the V3
gate/arbitration above):
    python3 router.py --check-project PATH

Prints {"project_id": "...", "is_new": bool} - see
profile_lib.compute_project_id / is_project_new.

Usage (teaching-gate status - read-only, same no-write rule as
--check-project, including no migration upgrade; unlike
update_profile.py --check it never ticks the gate counter, so the Stop
hook can call it on every turn):
    python3 router.py --gate-status

Prints {"can_teach": bool, "turns_since_last_teach": N, "min_gap": N} -
see profile_lib.gate_status.
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
    parser.add_argument(
        "--check-project",
        default=None,
        metavar="PATH",
        help=(
            "Compute the project_id for PATH and report whether it has "
            "been toured/declined before. Read-only: unlike the other "
            "modes, does not upgrade profile.json on disk even if its "
            "shape is old. Mutually exclusive with --pick."
        ),
    )
    parser.add_argument(
        "--gate-status",
        action="store_true",
        help=(
            "Report the teaching gate's current state without advancing "
            "it. Read-only: never writes profile.json, not even the shape "
            "upgrade. Mutually exclusive with --pick and --check-project."
        ),
    )
    args = parser.parse_args(argv)

    if args.gate_status:
        if args.pick or args.candidates or args.check_project is not None:
            parser.error("--gate-status cannot be combined with --pick or --check-project")
        state, _existed = lib.load_state(args.profile)
        migrated_state, _changed = lib.migrate(state)
        print(json.dumps(lib.gate_status(migrated_state)))
        return 0

    if args.check_project is not None:
        if args.pick or args.candidates:
            parser.error("--check-project cannot be combined with --pick")
        state, _existed = lib.load_state(args.profile)
        migrated_state, _changed = lib.migrate(state)
        project_id = lib.compute_project_id(args.check_project)
        is_new = lib.is_project_new(migrated_state, project_id)
        print(json.dumps({"project_id": project_id, "is_new": is_new}))
        return 0

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
        if winner and winner["track"] in ("ai_engineering", "prompting"):
            # Added here rather than inside pick_teaching_moment so the
            # arbitration logic itself stays untouched. English winners
            # keep their V3 shape exactly.
            entry = migrated_state["ai_engineering"].get(lib.normalize_topic(winner["topic"]), {})
            winner["explanation_tier"] = lib.explanation_tier(entry.get("times_seen"))
        print(json.dumps({"winner": winner}))
        return 0

    card = lib.build_context_card(migrated_state)
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
