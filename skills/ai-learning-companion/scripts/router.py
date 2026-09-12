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

Usage:
    python3 router.py [--profile PATH]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib as lib


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=lib.DEFAULT_PROFILE_PATH,
        help="Path to profile.json (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    state, existed = lib.load_state(args.profile)
    migrated_state, changed = lib.migrate(state)

    if existed and changed:
        # Upgrade the on-disk file to the new shape so future runs (and
        # update_profile.py) don't need to migrate it again.
        lib.safe_write_json(args.profile, migrated_state)

    card = lib.build_context_card(migrated_state)
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
