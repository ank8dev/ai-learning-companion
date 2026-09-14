"""Unit tests for profile_lib.py - stdlib unittest only, no dependencies.

Run with:
    python3 -m unittest scripts.test_profile_lib -v
(from skills/ai-learning-companion/), or
    python3 test_profile_lib.py -v
(from scripts/).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib as lib


def terms(n, date="2026-01-01"):
    return {"term%d" % i: date for i in range(n)}


class ThresholdLevelTest(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(lib.threshold_level(0), "beginner")
        self.assertEqual(lib.threshold_level(4), "beginner")
        self.assertEqual(lib.threshold_level(5), "intermediate")
        self.assertEqual(lib.threshold_level(19), "intermediate")
        self.assertEqual(lib.threshold_level(20), "advanced")
        self.assertEqual(lib.threshold_level(100), "advanced")


class MigrateTest(unittest.TestCase):
    def test_old_shape_gets_new_fields_with_sane_defaults(self):
        old = {"known_terms": terms(7), "sessions_taught": 3}
        new_state, changed = lib.migrate(old)

        self.assertTrue(changed)
        self.assertEqual(new_state["known_terms"], old["known_terms"])
        self.assertEqual(new_state["sessions_taught"], 3)
        self.assertEqual(new_state["level"], "intermediate")  # 7 terms
        self.assertEqual(new_state["level_history"], [])
        self.assertEqual(new_state["preferences"], {})
        self.assertEqual(new_state["task_type_counts"], {})
        self.assertIsNone(new_state["level_watch"])

    def test_never_overwrites_known_terms_or_sessions_taught(self):
        old = {
            "known_terms": {"closures": "2025-01-01"},
            "sessions_taught": 42,
            "level": "advanced",
        }
        new_state, _changed = lib.migrate(old)
        self.assertEqual(new_state["known_terms"], {"closures": "2025-01-01"})
        self.assertEqual(new_state["sessions_taught"], 42)
        self.assertEqual(new_state["level"], "advanced")  # not re-derived

    def test_does_not_mutate_input(self):
        old = {"known_terms": {}, "sessions_taught": 0}
        lib.migrate(old)
        self.assertNotIn("level", old)

    def test_already_new_shape_is_a_noop(self):
        state = lib.default_state()
        new_state, changed = lib.migrate(state)
        self.assertFalse(changed)
        self.assertEqual(new_state, state)


class MigrateV3Test(unittest.TestCase):
    """Migration from a V2-shape file to V3-shape."""

    def test_v2_shape_gets_v3_fields_with_empty_defaults(self):
        old = {
            "known_terms": terms(7),
            "sessions_taught": 3,
            "level": "intermediate",
            "level_history": [],
            "preferences": {"foo": "bar"},
            "task_type_counts": {"refactor": 2},
            "level_watch": None,
        }
        new_state, changed = lib.migrate(old)

        self.assertTrue(changed)
        # Every V2 field is untouched.
        self.assertEqual(new_state["known_terms"], old["known_terms"])
        self.assertEqual(new_state["sessions_taught"], 3)
        self.assertEqual(new_state["level"], "intermediate")
        self.assertEqual(new_state["level_history"], [])
        self.assertEqual(new_state["preferences"], {"foo": "bar"})
        self.assertEqual(new_state["task_type_counts"], {"refactor": 2})
        self.assertIsNone(new_state["level_watch"])
        # New V3 fields get empty/null defaults.
        self.assertEqual(new_state["ai_engineering"], {})
        self.assertEqual(new_state["struggle_patterns"], [])
        self.assertEqual(new_state["teaching_history"], [])
        self.assertIsNone(new_state["last_taught_at"])
        self.assertEqual(new_state["turns_since_last_teach"], 0)

    def test_does_not_mutate_input(self):
        old = {"known_terms": {}, "sessions_taught": 0}
        lib.migrate(old)
        self.assertNotIn("ai_engineering", old)
        self.assertNotIn("turns_since_last_teach", old)

    def test_v3_shape_is_a_noop(self):
        state = lib.default_state()
        new_state, changed = lib.migrate(state)
        self.assertFalse(changed)
        self.assertEqual(new_state, state)


class ComputeLevelTest(unittest.TestCase):
    def test_no_change_when_raw_matches_current(self):
        state = {
            "known_terms": terms(2),
            "level": "beginner",
            "level_history": [],
            "level_watch": None,
        }
        result = lib.compute_level(state)
        self.assertEqual(result["level"], "beginner")
        self.assertFalse(result["changed"])
        self.assertIsNone(result["level_watch"])

    def test_single_session_crossing_threshold_does_not_change_level(self):
        state = {
            "known_terms": terms(5),  # raw = intermediate
            "level": "beginner",
            "level_history": [],
            "level_watch": None,
        }
        result = lib.compute_level(state)

        self.assertEqual(result["level"], "beginner")  # unchanged
        self.assertFalse(result["changed"])
        self.assertEqual(
            result["level_watch"], {"candidate": "intermediate", "count": 1}
        )
        self.assertEqual(result["level_history"], [])

    def test_two_consecutive_sessions_confirm_the_change(self):
        state = {
            "known_terms": terms(5),
            "level": "beginner",
            "level_history": [],
            "level_watch": None,
        }
        first = lib.compute_level(state, today="2026-02-01")

        state_after_first = dict(state)
        state_after_first["level_watch"] = first["level_watch"]
        second = lib.compute_level(state_after_first, today="2026-02-02")

        self.assertEqual(second["level"], "intermediate")
        self.assertTrue(second["changed"])
        self.assertIsNone(second["level_watch"])
        self.assertEqual(len(second["level_history"]), 1)
        self.assertEqual(second["level_history"][0]["level"], "intermediate")
        self.assertEqual(second["level_history"][0]["changedAt"], "2026-02-02")

    def test_watch_resets_when_candidate_reverses_before_count_2(self):
        # Step 1: 4 terms, level=beginner, raw agrees -> no watch.
        state = {
            "known_terms": terms(4),
            "level": "beginner",
            "level_history": [],
            "level_watch": None,
        }
        step1 = lib.compute_level(state)
        self.assertIsNone(step1["level_watch"])

        # Step 2: term count crosses to 5 -> raw=intermediate, starts a
        # candidate watch at count 1. Level itself does not move yet.
        state_5_terms = dict(state)
        state_5_terms["known_terms"] = terms(5)
        state_5_terms["level_watch"] = step1["level_watch"]
        step2 = lib.compute_level(state_5_terms)
        self.assertEqual(
            step2["level_watch"], {"candidate": "intermediate", "count": 1}
        )
        self.assertFalse(step2["changed"])

        # Step 3 (the reversal): count drops back to 4, matching the
        # still-current "beginner" level. This must clear the watch
        # entirely, not just leave it at count 1.
        state_back_to_4 = dict(state)
        state_back_to_4["known_terms"] = terms(4)
        state_back_to_4["level"] = "beginner"
        state_back_to_4["level_watch"] = step2["level_watch"]
        step3 = lib.compute_level(state_back_to_4)
        self.assertIsNone(step3["level_watch"])
        self.assertFalse(step3["changed"])
        self.assertEqual(step3["level"], "beginner")

        # Step 4: count goes back up to 5 again. If the watch had truly
        # reset in step 3 (rather than silently keeping count=1 or
        # jumping straight to committed), this must restart at count 1,
        # NOT commit the change yet.
        state_5_terms_again = dict(state)
        state_5_terms_again["known_terms"] = terms(5)
        state_5_terms_again["level"] = "beginner"
        state_5_terms_again["level_watch"] = step3["level_watch"]
        step4 = lib.compute_level(state_5_terms_again)
        self.assertEqual(
            step4["level_watch"], {"candidate": "intermediate", "count": 1}
        )
        self.assertFalse(step4["changed"])
        self.assertEqual(step4["level"], "beginner")

    def test_watch_restarts_when_a_different_candidate_appears(self):
        state = {
            "known_terms": terms(5),  # raw = intermediate
            "level": "beginner",
            "level_history": [],
            "level_watch": None,
        }
        first = lib.compute_level(state)
        self.assertEqual(first["level_watch"]["candidate"], "intermediate")

        # Now a big jump to 20+ terms (raw = advanced) arrives while the
        # watch was still tracking "intermediate" at count 1. The new
        # candidate differs, so it must restart at count 1, not build on
        # the old candidate's count.
        state_jump = dict(state)
        state_jump["known_terms"] = terms(25)
        state_jump["level_watch"] = first["level_watch"]
        second = lib.compute_level(state_jump)
        self.assertEqual(
            second["level_watch"], {"candidate": "advanced", "count": 1}
        )
        self.assertFalse(second["changed"])


class RecentConceptsTest(unittest.TestCase):
    def test_orders_by_date_descending(self):
        known = {"a": "2026-01-01", "b": "2026-02-01", "c": "2026-01-15"}
        self.assertEqual(lib.recent_concepts(known), ["b", "c", "a"])

    def test_same_date_ties_break_alphabetically_by_term(self):
        known = {"zeta": "2026-01-01", "alpha": "2026-01-01", "mid": "2026-01-01"}
        self.assertEqual(lib.recent_concepts(known), ["alpha", "mid", "zeta"])

    def test_respects_limit(self):
        known = terms(10, date="2026-01-01")
        self.assertEqual(len(lib.recent_concepts(known, limit=3)), 3)


class BuildContextCardTest(unittest.TestCase):
    def test_shape(self):
        state = lib.default_state()
        state["known_terms"] = {"closures": "2026-01-01"}
        state["level"] = "beginner"
        card = lib.build_context_card(state)
        self.assertEqual(set(card.keys()), {"level", "note", "recent_concepts"})
        self.assertEqual(card["level"], "beginner")
        self.assertEqual(card["recent_concepts"], ["closures"])


class LevelNoteTest(unittest.TestCase):
    """The note always asks for English only - level changes how complex
    the English is, never which language it's in."""

    def _note(self, level, known_count=3):
        state = lib.default_state()
        state["known_terms"] = terms(known_count)
        state["level"] = level
        return lib.build_context_card(state)["note"]

    def test_every_level_is_english_only(self):
        for level in ("beginner", "intermediate", "advanced"):
            note = self._note(level)
            self.assertIn("English only", note, level)
            self.assertNotIn("their language", note, level)
            self.assertNotIn("mix", note.lower(), level)

    def test_beginner_asks_for_simple_english_and_spelled_out_terms(self):
        note = self._note("beginner")
        self.assertIn("simple English", note)
        self.assertIn("spell it out in full", note)

    def test_intermediate_explains_new_advanced_words(self):
        note = self._note("intermediate")
        self.assertIn("technical vocabulary", note)
        self.assertIn("new or advanced word", note)

    def test_advanced_needs_no_simplification(self):
        note = self._note("advanced")
        self.assertIn("full technical English", note)
        self.assertIn("no simplification", note)

    def test_note_still_reports_known_term_count(self):
        self.assertIn("User knows 7 terms.", self._note("intermediate", known_count=7))


class CanTeachNowTest(unittest.TestCase):
    def test_true_when_nothing_ever_taught(self):
        state = lib.default_state()
        self.assertIsNone(state["last_taught_at"])
        self.assertTrue(lib.can_teach_now(state))

    def test_false_right_after_a_teach(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 0
        self.assertFalse(lib.can_teach_now(state, min_gap=3))

    def test_false_below_the_gap(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 2
        self.assertFalse(lib.can_teach_now(state, min_gap=3))

    def test_true_once_gap_is_reached(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 3
        self.assertTrue(lib.can_teach_now(state, min_gap=3))

    def test_true_when_gap_is_exceeded(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 10
        self.assertTrue(lib.can_teach_now(state, min_gap=3))

    def test_full_cycle_via_tick_gate(self):
        # Simulate a teach (reset), then 3 checks tick the counter, and
        # the gate should only reopen once the 3rd tick lands.
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 0
        self.assertFalse(lib.can_teach_now(state, min_gap=3))

        state = lib.tick_gate(state)
        self.assertEqual(state["turns_since_last_teach"], 1)
        self.assertFalse(lib.can_teach_now(state, min_gap=3))

        state = lib.tick_gate(state)
        self.assertEqual(state["turns_since_last_teach"], 2)
        self.assertFalse(lib.can_teach_now(state, min_gap=3))

        state = lib.tick_gate(state)
        self.assertEqual(state["turns_since_last_teach"], 3)
        self.assertTrue(lib.can_teach_now(state, min_gap=3))


class TickGateTest(unittest.TestCase):
    def test_increments_counter(self):
        state = lib.default_state()
        state["turns_since_last_teach"] = 5
        new_state = lib.tick_gate(state)
        self.assertEqual(new_state["turns_since_last_teach"], 6)

    def test_does_not_mutate_input(self):
        state = lib.default_state()
        lib.tick_gate(state)
        self.assertEqual(state["turns_since_last_teach"], 0)

    def test_observed_pattern_is_appended_as_new(self):
        state = lib.default_state()
        new_state = lib.tick_gate(
            state, observed_patterns=["missing article"], today="2026-01-01"
        )
        self.assertEqual(len(new_state["struggle_patterns"]), 1)
        entry = new_state["struggle_patterns"][0]
        self.assertEqual(entry["pattern"], "missing article")
        self.assertEqual(entry["count"], 1)
        self.assertEqual(entry["last_seen"], "2026-01-01")

    def test_observed_pattern_increments_existing_case_insensitively(self):
        state = lib.default_state()
        state["struggle_patterns"] = [
            {"pattern": "Missing Article", "count": 1, "last_seen": "2026-01-01"}
        ]
        new_state = lib.tick_gate(
            state, observed_patterns=["  missing article  "], today="2026-01-05"
        )
        self.assertEqual(len(new_state["struggle_patterns"]), 1)
        entry = new_state["struggle_patterns"][0]
        # Original casing/text is preserved; only count/last_seen bump.
        self.assertEqual(entry["pattern"], "Missing Article")
        self.assertEqual(entry["count"], 2)
        self.assertEqual(entry["last_seen"], "2026-01-05")

    def test_blank_observed_pattern_is_ignored(self):
        state = lib.default_state()
        new_state = lib.tick_gate(state, observed_patterns=["  ", ""])
        self.assertEqual(new_state["struggle_patterns"], [])


class PickTeachingMomentTest(unittest.TestCase):
    def test_ai_engineering_beats_recurring_struggle_pattern(self):
        state = lib.default_state()
        state["struggle_patterns"] = [
            {"pattern": "missing article", "count": 3, "last_seen": "2026-01-01"}
        ]
        candidates = [
            ("english", "missing article"),
            ("ai_engineering", "mcp"),
        ]
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["track"], "ai_engineering")
        self.assertEqual(winner["topic"], "mcp")
        self.assertEqual(winner["priority"], 1)
        self.assertFalse(winner["optional"])

    def test_recurring_struggle_pattern_beats_one_off_slip(self):
        state = lib.default_state()
        state["struggle_patterns"] = [
            {"pattern": "missing article", "count": 2, "last_seen": "2026-01-01"}
        ]
        candidates = [
            ("english", "wrong preposition"),  # one-off, count 0/absent
            ("english", "missing article"),  # recurring, count 2
        ]
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["track"], "english")
        self.assertEqual(winner["topic"], "missing article")
        self.assertEqual(winner["priority"], 2)
        self.assertFalse(winner["optional"])

    def test_one_off_slip_wins_only_when_nothing_else_qualifies(self):
        state = lib.default_state()
        candidates = [("english", "wrong preposition")]
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["track"], "english")
        self.assertEqual(winner["priority"], 3)
        self.assertTrue(winner["optional"])

    def test_practiced_topic_is_filtered_out_entirely(self):
        state = lib.default_state()
        state["ai_engineering"] = {"mcp": {"status": "practiced", "times_seen": 5}}
        candidates = [
            ("ai_engineering", "mcp"),
            ("english", "wrong preposition"),
        ]
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        # mcp is filtered out (not demoted), so the one-off English slip
        # wins by default since nothing else qualifies.
        self.assertEqual(winner["track"], "english")
        self.assertEqual(winner["priority"], 3)

    def test_recently_taught_struggle_pattern_falls_to_tier_3(self):
        state = lib.default_state()
        state["struggle_patterns"] = [
            {"pattern": "missing article", "count": 5, "last_seen": "2026-01-09"}
        ]
        state["teaching_history"] = [
            {"track": "english", "topic": "missing article", "at": "2026-01-05"}
        ]
        candidates = [("english", "missing article")]
        # Within ENGLISH_RETEACH_DAYS (7) of 2026-01-05.
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["priority"], 3)
        self.assertTrue(winner["optional"])

    def test_recently_taught_ai_engineering_topic_is_skipped_this_round(self):
        state = lib.default_state()
        state["ai_engineering"] = {"mcp": {"status": "seen", "times_seen": 1}}
        state["teaching_history"] = [
            {"track": "ai_engineering", "topic": "mcp", "at": "2026-01-09"}
        ]
        candidates = [
            ("ai_engineering", "mcp"),
            ("english", "wrong preposition"),
        ]
        # Within AI_ENG_RETEACH_DAYS (1) of 2026-01-09.
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["track"], "english")
        self.assertEqual(winner["priority"], 3)

    def test_ai_engineering_topic_eligible_again_once_cooldown_passes(self):
        # Same topic/history shape as the "skipped this round" test above,
        # taught on 2026-01-08 (still status "seen"), checked at the exact
        # AI_ENG_RETEACH_DAYS (1) boundary and one day past it.
        state = lib.default_state()
        state["ai_engineering"] = {"mcp": {"status": "seen", "times_seen": 1}}
        state["teaching_history"] = [
            {"track": "ai_engineering", "topic": "mcp", "at": "2026-01-08"}
        ]
        candidates = [
            ("ai_engineering", "mcp"),
            ("english", "wrong preposition"),
        ]

        # Exactly AI_ENG_RETEACH_DAYS (1 day) later: still blocked.
        blocked = lib.pick_teaching_moment(state, candidates, today="2026-01-09")
        self.assertEqual(blocked["track"], "english")
        self.assertEqual(blocked["priority"], 3)

        # One day past the boundary (2 days since taught): eligible again.
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["track"], "ai_engineering")
        self.assertEqual(winner["topic"], "mcp")
        self.assertEqual(winner["priority"], 1)

        # pick_teaching_moment is read-only: winning again does not itself
        # upgrade the topic's status - only apply_teaching_event (a
        # separate, explicit write) can move it past "seen".
        self.assertEqual(state["ai_engineering"]["mcp"]["status"], "seen")

    def test_no_candidates_returns_none(self):
        state = lib.default_state()
        self.assertIsNone(lib.pick_teaching_moment(state, []))

    def test_all_filtered_out_returns_none(self):
        state = lib.default_state()
        state["ai_engineering"] = {"mcp": {"status": "practiced", "times_seen": 5}}
        candidates = [("ai_engineering", "mcp")]
        self.assertIsNone(lib.pick_teaching_moment(state, candidates))

    def test_tier1_prefers_lowest_status_then_input_order(self):
        state = lib.default_state()
        state["ai_engineering"] = {
            "context-engineering": {"status": "understood", "times_seen": 2},
        }
        candidates = [
            ("ai_engineering", "context-engineering"),  # understood -> rank 2
            ("prompting", "few-shot"),  # unseen -> rank 0
        ]
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["topic"], "few-shot")

    def test_tier2_prefers_higher_count_then_alphabetical(self):
        state = lib.default_state()
        state["struggle_patterns"] = [
            {"pattern": "wrong preposition", "count": 2, "last_seen": "2026-01-01"},
            {"pattern": "missing article", "count": 4, "last_seen": "2026-01-01"},
        ]
        candidates = [
            ("english", "wrong preposition"),
            ("english", "missing article"),
        ]
        winner = lib.pick_teaching_moment(state, candidates, today="2026-01-10")
        self.assertEqual(winner["topic"], "missing article")  # higher count


class ExplanationTierTest(unittest.TestCase):
    """Every boundary of explanation_tier, checked from both sides."""

    def test_zero_is_full(self):
        self.assertEqual(lib.explanation_tier(0), "full")

    def test_missing_count_is_full(self):
        self.assertEqual(lib.explanation_tier(None), "full")

    def test_one_through_three_is_short(self):
        self.assertEqual(lib.explanation_tier(1), "short")
        self.assertEqual(lib.explanation_tier(3), "short")

    def test_four_through_ten_is_reminder(self):
        self.assertEqual(lib.explanation_tier(4), "reminder")
        self.assertEqual(lib.explanation_tier(10), "reminder")

    def test_eleven_through_twenty_four_is_mention(self):
        self.assertEqual(lib.explanation_tier(11), "mention")
        self.assertEqual(lib.explanation_tier(24), "mention")

    def test_twenty_five_and_up_is_silent(self):
        self.assertEqual(lib.explanation_tier(25), "silent")
        self.assertEqual(lib.explanation_tier(1000), "silent")


class RouterPickExplanationTierCliTest(unittest.TestCase):
    """CLI-level: router.py --pick adds explanation_tier to AI-engineering/
    prompting winners only - English winners keep their V3 shape exactly."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="pick-tier-test-")
        self.profile = os.path.join(self._tmp, "profile.json")
        self.router = os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _pick(self, state, *candidates):
        with open(self.profile, "w", encoding="utf-8") as f:
            json.dump(state, f)
        args = [sys.executable, self.router, "--pick", "--profile", self.profile]
        for candidate in candidates:
            args += ["--candidate", candidate]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["winner"]

    def test_ai_engineering_winner_gets_tier_from_times_seen(self):
        state = lib.default_state()
        state["ai_engineering"] = {"git-init": {"status": "seen", "times_seen": 4}}
        winner = self._pick(state, "ai_engineering:Git-Init")
        self.assertEqual(winner["topic"], "Git-Init")
        self.assertEqual(winner["explanation_tier"], "reminder")

    def test_new_prompting_topic_gets_full_tier(self):
        winner = self._pick(lib.default_state(), "prompting:few-shot")
        self.assertEqual(winner["explanation_tier"], "full")

    def test_english_winner_has_no_tier_key(self):
        state = lib.default_state()
        state["struggle_patterns"] = [
            {"pattern": "missing article", "count": 3, "last_seen": "2026-01-01"}
        ]
        winner = self._pick(state, "english:missing article")
        self.assertEqual(winner["track"], "english")
        self.assertNotIn("explanation_tier", winner)
        self.assertEqual(set(winner), {"track", "topic", "priority", "optional"})


class GateStatusTest(unittest.TestCase):
    def test_open_when_nothing_ever_taught(self):
        self.assertEqual(
            lib.gate_status(lib.default_state()),
            {"can_teach": True, "turns_since_last_teach": 0, "min_gap": lib.DEFAULT_MIN_TEACH_GAP},
        )

    def test_closed_right_after_a_teach(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 0
        status = lib.gate_status(state)
        self.assertFalse(status["can_teach"])
        self.assertEqual(status["turns_since_last_teach"], 0)

    def test_open_once_gap_is_reached(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 3
        self.assertTrue(lib.gate_status(state)["can_teach"])
        state["turns_since_last_teach"] = 4
        status = lib.gate_status(state, min_gap=5)
        self.assertFalse(status["can_teach"])
        self.assertEqual(status["min_gap"], 5)

    def test_agrees_with_can_teach_now(self):
        for last_taught_at in (None, "2026-01-01"):
            for turns in range(6):
                state = lib.default_state()
                state["last_taught_at"] = last_taught_at
                state["turns_since_last_teach"] = turns
                with self.subTest(last_taught_at=last_taught_at, turns=turns):
                    self.assertEqual(lib.gate_status(state)["can_teach"], lib.can_teach_now(state))

    def test_does_not_mutate_input(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 2
        snapshot = json.loads(json.dumps(state))
        lib.gate_status(state)
        lib.gate_status(state)
        self.assertEqual(state, snapshot)


class RouterGateStatusCliTest(unittest.TestCase):
    """CLI-level: router.py --gate-status must never write."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="gate-status-test-")
        self.profile = os.path.join(self._tmp, "profile.json")
        self.router = os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, self.router, "--profile", self.profile] + list(args),
            capture_output=True,
            text=True,
        )

    def _write(self, state):
        with open(self.profile, "w", encoding="utf-8") as f:
            json.dump(state, f)
        with open(self.profile, encoding="utf-8") as f:
            return f.read()

    def _read(self):
        with open(self.profile, encoding="utf-8") as f:
            return f.read()

    def test_prints_gate_shape(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 1
        self._write(state)
        result = self._run("--gate-status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"can_teach": False, "turns_since_last_teach": 1, "min_gap": lib.DEFAULT_MIN_TEACH_GAP},
        )

    def test_does_not_create_missing_profile(self):
        result = self._run("--gate-status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["can_teach"])
        self.assertFalse(os.path.exists(self.profile))

    def test_does_not_upgrade_old_shape_profile_on_disk(self):
        before = self._write({"known_terms": {"x": "2026-01-01"}, "sessions_taught": 1})
        result = self._run("--gate-status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._read(), before)

    def test_does_not_advance_the_counter_on_disk(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 2
        before = self._write(state)
        for _ in range(3):
            result = self._run("--gate-status")
            self.assertEqual(json.loads(result.stdout)["turns_since_last_teach"], 2)
        self.assertEqual(self._read(), before)

    def test_rejects_combination_with_pick(self):
        result = self._run("--gate-status", "--pick", "--candidate", "english:x")
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_combination_with_check_project(self):
        result = self._run("--gate-status", "--check-project", self._tmp)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
