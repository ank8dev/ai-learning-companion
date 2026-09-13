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

# V3 teaching-gate defaults (see can_teach_now / tick_gate below).
#
# turns_since_last_teach counts *gated checks* (update_profile.py --check
# calls), not literal conversation turns - the skill only calls --check
# when it thinks a candidate teaching moment might exist, so this is
# "candidate moments since the last teach", which is what actually needs
# throttling. A real per-turn counter would need a UserPromptSubmit hook;
# deliberately left out of V3.
DEFAULT_MIN_TEACH_GAP = 3

# Tier-2 arbitration (see pick_teaching_moment): once a recurring English
# struggle pattern has been taught, don't teach the identical pattern
# again for this many days - the lesson doesn't change just because the
# mistake recurred once more.
ENGLISH_RETEACH_DAYS = 7

# Tier-1 arbitration: unlike English patterns, an AI-engineering/prompting
# topic can legitimately have something new to say on a second appearance
# (a "seen" topic isn't a fixed lesson), so this cooldown is deliberately
# short - it only stops the exact same topic winning on back-to-back gated
# checks, it does not throttle the topic like tier 2 does.
AI_ENG_RETEACH_DAYS = 1


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
        # V3 fields - see module-level comment above for the gate/
        # arbitration constants that consume these.
        "ai_engineering": {},
        "struggle_patterns": [],
        "teaching_history": [],
        "last_taught_at": None,
        "turns_since_last_teach": 0,
    }


def normalize_topic(topic):
    """Trim + lowercase a topic/pattern string for matching.

    Used everywhere a topic string is compared or stored as a key
    (ai_engineering dict keys, struggle_patterns[].pattern matching,
    teaching_history topic matching) so that casing/whitespace drift
    ("MCP" vs "mcp ") can't silently fragment counts or dodge cooldowns.
    Display text (what the model shows the user) should still use the
    original, non-normalized string from the caller.
    """
    return (topic or "").strip().lower()


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

    # V3 fields. Added with empty/null defaults only - never derived from
    # or touching any V2 field above.
    if "ai_engineering" not in state or not isinstance(state["ai_engineering"], dict):
        state["ai_engineering"] = {}
        changed = True
    if "struggle_patterns" not in state or not isinstance(
        state["struggle_patterns"], list
    ):
        state["struggle_patterns"] = []
        changed = True
    if "teaching_history" not in state or not isinstance(
        state["teaching_history"], list
    ):
        state["teaching_history"] = []
        changed = True
    if "last_taught_at" not in state:
        state["last_taught_at"] = None
        changed = True
    if "turns_since_last_teach" not in state:
        state["turns_since_last_teach"] = 0
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


def can_teach_now(state, min_gap=DEFAULT_MIN_TEACH_GAP):
    """The hard "can I teach right now?" gate. Pure: never mutates state.

    Must be checked BEFORE any decision about *what* to teach - it's a
    gate, not a suggestion (see SKILL.md). Rule: teaching is allowed if
    nothing has ever been taught yet (last_taught_at is None), or if at
    least `min_gap` gated checks (see turns_since_last_teach / tick_gate)
    have happened since the last one that actually taught something.
    """
    if state.get("last_taught_at") is None:
        return True
    return state.get("turns_since_last_teach", 0) >= min_gap


def tick_gate(state, observed_patterns=(), today=None):
    """Advance the gate by one check. Pure: returns a new state dict,
    never mutates the input. Call this on every gated check, regardless
    of whether teaching ends up happening.

    - Always increments turns_since_last_teach by 1. Recording a teaching
      event (see update_profile.py) is what resets this back to 0, not
      this function.
    - `observed_patterns` lets the caller note that an English struggle
      (e.g. "missing article before uncountable noun") was seen again
      this turn, even though the gate is closed and nothing will be
      taught: it bumps count/last_seen on a matching struggle_patterns
      entry (matched via normalize_topic), or appends a new entry at
      count=1. This is how a pattern accumulates enough count to reach
      the tier-2 threshold in pick_teaching_moment while teaching itself
      stays gated - observing is not teaching.
    """
    today = today or date.today().isoformat()
    new_state = dict(state)
    new_state["turns_since_last_teach"] = state.get("turns_since_last_teach", 0) + 1

    patterns = [dict(p) for p in state.get("struggle_patterns", [])]
    for description in observed_patterns:
        description = (description or "").strip()
        if not description:
            continue
        key = normalize_topic(description)
        match = next(
            (p for p in patterns if normalize_topic(p.get("pattern", "")) == key),
            None,
        )
        if match:
            match["count"] = match.get("count", 0) + 1
            match["last_seen"] = today
        else:
            patterns.append({"pattern": description, "count": 1, "last_seen": today})
    new_state["struggle_patterns"] = patterns

    return new_state


def _recently_taught(teaching_history, track, topic, days, today):
    """True if `track`/`topic` (matched via normalize_topic) has a
    teaching_history entry within `days` days of `today`."""
    key = normalize_topic(topic)
    today_date = date.fromisoformat(today)
    for entry in teaching_history:
        if entry.get("track") != track:
            continue
        if normalize_topic(entry.get("topic", "")) != key:
            continue
        try:
            at_date = date.fromisoformat(entry.get("at", ""))
        except ValueError:
            continue
        if (today_date - at_date).days <= days:
            return True
    return False


def pick_teaching_moment(state, candidates, today=None):
    """Arbitrate between candidate teaching moments. Pure: never mutates
    state, returns a single winner dict or None.

    `candidates` is an iterable of (track, topic) tuples, track one of
    "ai_engineering", "prompting", "english". This implements the
    priority order from SKILL.md - at most one moment ever wins:

    Tier 1 (priority 1, optional False) - a genuine new AI-engineering or
    prompting concept. Qualifies unless state["ai_engineering"][topic] is
    already "practiced" (filtered out entirely, doesn't fall to a lower
    tier) or this exact topic was taught within AI_ENG_RETEACH_DAYS
    (filtered out for this check only). Tie-break: lowest status first
    (new/unseen, then "seen", then "understood"), then input order.

    Tier 2 (priority 2, optional False) - an English struggle_patterns
    entry with count >= 2, not taught within ENGLISH_RETEACH_DAYS days
    (a recently-taught recurring pattern falls through to tier 3 instead
    of winning again). Tie-break: highest count first, then topic name
    alphabetically.

    Tier 3 (priority 3, optional True) - any other English candidate: a
    one-off slip, a plain vocabulary term, or a recurring pattern that
    was filtered out of tier 2 for being taught too recently. Only
    considered if tiers 1 and 2 are both empty. optional=True tells the
    caller (SKILL.md) this should usually be skipped unless clearly
    useful. Tie-break: input order.
    """
    today = today or date.today().isoformat()
    candidates = list(candidates)
    ai_engineering = state.get("ai_engineering", {})
    struggle_patterns = state.get("struggle_patterns", [])
    teaching_history = state.get("teaching_history", [])

    tier1 = []
    for track, topic in candidates:
        if track not in ("ai_engineering", "prompting"):
            continue
        entry = ai_engineering.get(normalize_topic(topic))
        status = entry.get("status") if entry else None
        if status == "practiced":
            continue
        if _recently_taught(teaching_history, track, topic, AI_ENG_RETEACH_DAYS, today):
            continue
        status_rank = {None: 0, "seen": 1, "understood": 2}.get(status, 1)
        tier1.append((status_rank, track, topic))
    if tier1:
        tier1.sort(key=lambda item: item[0])  # stable: ties keep input order
        _rank, track, topic = tier1[0]
        return {"track": track, "topic": topic, "priority": 1, "optional": False}

    tier2 = []
    for track, topic in candidates:
        if track != "english":
            continue
        key = normalize_topic(topic)
        match = next(
            (p for p in struggle_patterns if normalize_topic(p.get("pattern", "")) == key),
            None,
        )
        if not match or match.get("count", 0) < 2:
            continue
        if _recently_taught(teaching_history, "english", topic, ENGLISH_RETEACH_DAYS, today):
            continue
        tier2.append((match.get("count", 0), topic, track))
    if tier2:
        tier2.sort(key=lambda item: (-item[0], item[1]))
        _count, topic, track = tier2[0]
        return {"track": track, "topic": topic, "priority": 2, "optional": False}

    for track, topic in candidates:
        if track == "english":
            return {"track": track, "topic": topic, "priority": 3, "optional": True}

    return None


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
