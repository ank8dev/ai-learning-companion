"""Shared, dependency-free helpers for the ai-learning-companion profile.

This module is the only place that knows the on-disk schema of
profile.json. router.py (read-only context card) and update_profile.py
(the only writer) both import it so the schema, migration, and level
logic live in exactly one place.
"""

import json
import os
import tempfile
from datetime import date

DEFAULT_PROFILE_PATH = os.path.expanduser(
    "~/.claude/ai-learning-companion/profile.json"
)

# Existing 5/20 thresholds from SKILL.md, now centralized here.
BEGINNER_MAX = 5
INTERMEDIATE_MAX = 20


def threshold_level(known_count):
    """Map a known_terms count to the level it implies, in isolation.

    This is the "raw" level - compute_level() below decides whether the
    learner's actual level should move to match it.
    """
    if known_count < BEGINNER_MAX:
        return "beginner"
    if known_count < INTERMEDIATE_MAX:
        return "intermediate"
    return "advanced"


def default_state():
    """A brand-new profile, in the current (post-migration) shape."""
    return {
        "known_terms": {},
        "sessions_taught": 0,
        "level": "beginner",
        "level_history": [],
        "preferences": {},
        "task_type_counts": {},
        "level_watch": None,
    }


def load_state(path):
    """Load profile state from disk.

    Returns (state, existed) where `existed` is True only if the file
    was present and parsed as a JSON object. Missing, unreadable, or
    malformed files fall back to a fresh default state - SKILL.md has
    always tolerated this rather than blocking the digest on it.
    """
    if not os.path.exists(path):
        return default_state(), False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return default_state(), False
    if not isinstance(data, dict):
        return default_state(), False
    return data, True


def migrate(state):
    """Fill in any fields missing from an old-shape profile.

    Never removes or overwrites known_terms or sessions_taught. Returns
    (new_state, changed) - new_state is a shallow copy, so the caller's
    original dict is left untouched.
    """
    state = dict(state)
    changed = False

    if "known_terms" not in state or not isinstance(state["known_terms"], dict):
        state["known_terms"] = {}
        changed = True
    if "sessions_taught" not in state:
        state["sessions_taught"] = 0
        changed = True
    if "level" not in state:
        state["level"] = threshold_level(len(state["known_terms"]))
        changed = True
    if "level_history" not in state:
        state["level_history"] = []
        changed = True
    if "preferences" not in state:
        state["preferences"] = {}
        changed = True
    if "task_type_counts" not in state:
        state["task_type_counts"] = {}
        changed = True
    if "level_watch" not in state:
        state["level_watch"] = None
        changed = True

    return state, changed


def compute_level(state, today=None):
    """Decide whether the learner's level should change. Pure function:
    takes state, returns a result dict - never mutates `state` or touches
    disk. The caller merges the result back into whatever state it saves.

    Hysteresis rule (deliberately simple, documented here since the spec
    asked for one clear rule): compare the "raw" level implied by the
    current known_terms count against the profile's current level. If
    they already agree, there's nothing to do. If they disagree, that
    raw level becomes (or remains) a "candidate" with a count. Only once
    the SAME candidate has been seen on 2 consecutive compute_level
    calls does the level actually change (and get a level_history
    entry). Any call that doesn't match the standing candidate - whether
    it falls back to the current level or jumps to some other level -
    resets the watch to start over. This means a one-off session that
    crosses a threshold can't flip the level by itself, but two sessions
    in a row agreeing on a new level will.
    """
    known_count = len(state.get("known_terms", {}))
    current_level = state.get("level") or threshold_level(known_count)
    raw_level = threshold_level(known_count)
    level_history = list(state.get("level_history", []))
    level_watch = state.get("level_watch")

    if raw_level == current_level:
        return {
            "level": current_level,
            "changed": False,
            "reason": "known_terms count matches current level",
            "level_history": level_history,
            "level_watch": None,
        }

    if level_watch and level_watch.get("candidate") == raw_level:
        new_count = level_watch.get("count", 0) + 1
    else:
        new_count = 1

    if new_count >= 2:
        changed_at = today or date.today().isoformat()
        level_history.append(
            {
                "level": raw_level,
                "changedAt": changed_at,
                "reason": (
                    "known_terms count (%d) matched '%s' for 2 consecutive "
                    "sessions" % (known_count, raw_level)
                ),
            }
        )
        return {
            "level": raw_level,
            "changed": True,
            "reason": "confirmed after 2 consecutive sessions at this threshold",
            "level_history": level_history,
            "level_watch": None,
        }

    return {
        "level": current_level,
        "changed": False,
        "reason": "watching candidate '%s' (%d/2)" % (raw_level, new_count),
        "level_history": level_history,
        "level_watch": {"candidate": raw_level, "count": new_count},
    }


def recent_concepts(known_terms, limit=5):
    """Most-recently-added known terms, most recent first.

    Tie-break rule (explicit, not incidental dict/JSON ordering): a
    single digest can add several terms with the same date, so we sort
    by date descending, then by term name ascending as the tie-break.
    Implemented as two stable sorts - first by name ascending, then by
    date descending - so equal-date groups come out name-ordered.
    """
    by_name = sorted(known_terms.items(), key=lambda kv: kv[0])
    by_date_desc = sorted(by_name, key=lambda kv: kv[1], reverse=True)
    return [term for term, _added in by_date_desc[:limit]]


def _level_note(level, known_count):
    if level == "beginner":
        return (
            "User knows %d terms. Explain mostly in their language, "
            "calling out English terms." % known_count
        )
    if level == "intermediate":
        return (
            "User knows %d terms. Explain in a mix of English and "
            "their language." % known_count
        )
    return (
        "User knows %d terms. Default to English, only drop back to "
        "their language for a genuinely new or hard concept." % known_count
    )


def build_context_card(state):
    """The only thing exposed to the model - never the full profile."""
    known_terms = state.get("known_terms", {})
    level = state.get("level", "beginner")
    return {
        "level": level,
        "note": _level_note(level, len(known_terms)),
        "recent_concepts": recent_concepts(known_terms),
    }


def safe_write_json(path, data):
    """Write `data` to `path` atomically: write to a temp file in the
    same directory, then os.replace() over the original. A crash
    mid-write leaves the original file untouched instead of truncated
    or half-written.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".profile-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
