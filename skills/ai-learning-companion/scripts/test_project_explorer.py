"""Unit tests for the project-explorer additions to profile_lib.py -
stdlib unittest + real `git` in temp directories, no other dependencies.

Skipped entirely if `git` isn't on PATH (compute_project_id degrades to
its path fallback in that case, which is exercised separately here via
a plain non-git directory, so git's absence doesn't block those tests).

Run with:
    python3 -m unittest scripts.test_project_explorer -v
(from skills/ai-learning-companion/), or
    python3 test_project_explorer.py -v
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

HAS_GIT = shutil.which("git") is not None


def _run_git(args, cwd):
    subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path, remote_url=None):
    os.makedirs(path, exist_ok=True)
    _run_git(["init", "-q"], path)
    if remote_url:
        _run_git(["remote", "add", "origin", remote_url], path)
    return path


class TempDirMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="project-explorer-test-")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _path(self, *parts):
        return os.path.join(self._tmp, *parts)


@unittest.skipUnless(HAS_GIT, "git not on PATH")
class ComputeProjectIdGitTest(TempDirMixin, unittest.TestCase):
    def test_ssh_remote_gives_git_id(self):
        repo = _init_repo(self._path("repo"), "git@github.com:ank8dev/demo.git")
        self.assertEqual(
            lib.compute_project_id(repo), "git:github.com/ank8dev/demo"
        )

    def test_https_remote_gives_same_id_as_ssh(self):
        ssh_repo = _init_repo(self._path("ssh-repo"), "git@github.com:ank8dev/demo.git")
        https_repo = _init_repo(
            self._path("https-repo"), "https://github.com/ank8dev/demo.git"
        )
        self.assertEqual(
            lib.compute_project_id(ssh_repo), lib.compute_project_id(https_repo)
        )

    def test_credentials_are_stripped_from_id(self):
        repo = _init_repo(
            self._path("repo"),
            "https://x-access-token:ghp_secret123@github.com/ank8dev/demo.git",
        )
        project_id = lib.compute_project_id(repo)
        self.assertNotIn("ghp_secret123", project_id)
        self.assertNotIn("x-access-token", project_id)
        self.assertEqual(project_id, "git:github.com/ank8dev/demo")

    def test_no_remote_falls_back_to_path(self):
        repo = _init_repo(self._path("repo"))
        self.assertEqual(
            lib.compute_project_id(repo), "path:%s" % os.path.realpath(repo)
        )

    def test_subfolder_matches_root_id(self):
        repo = _init_repo(self._path("repo"), "git@github.com:ank8dev/demo.git")
        sub = self._path("repo", "src", "lib")
        os.makedirs(sub)
        self.assertEqual(lib.compute_project_id(repo), lib.compute_project_id(sub))


class ComputeProjectIdNoGitTest(TempDirMixin, unittest.TestCase):
    def test_non_git_folder_gives_real_path(self):
        plain = self._path("plain")
        os.makedirs(plain)
        self.assertEqual(
            lib.compute_project_id(plain), "path:%s" % os.path.realpath(plain)
        )

    def test_missing_git_binary_falls_back_to_path(self):
        plain = self._path("plain")
        os.makedirs(plain)
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                raise FileNotFoundError("git not found")
            return real_run(cmd, **kwargs)

        subprocess.run = fake_run
        try:
            self.assertEqual(
                lib.compute_project_id(plain), "path:%s" % os.path.realpath(plain)
            )
        finally:
            subprocess.run = real_run


class NormalizeGitRemoteTest(unittest.TestCase):
    def test_ssh_form(self):
        self.assertEqual(
            lib._normalize_git_remote("git@github.com:ank8dev/demo.git"),
            "github.com/ank8dev/demo",
        )

    def test_https_form_without_git_suffix(self):
        self.assertEqual(
            lib._normalize_git_remote("https://github.com/ank8dev/demo"),
            "github.com/ank8dev/demo",
        )

    def test_https_with_token_strips_credentials(self):
        self.assertEqual(
            lib._normalize_git_remote(
                "https://user:token@github.com/ank8dev/demo.git"
            ),
            "github.com/ank8dev/demo",
        )

    def test_unparseable_url_returns_none(self):
        self.assertIsNone(lib._normalize_git_remote("not a url"))

    def test_empty_returns_none(self):
        self.assertIsNone(lib._normalize_git_remote(""))
        self.assertIsNone(lib._normalize_git_remote(None))


class MigrateProjectExplorerFieldsTest(unittest.TestCase):
    def test_v3_shape_gets_project_explorer_fields_with_empty_defaults(self):
        old = {
            "known_terms": {},
            "sessions_taught": 3,
            "level": "intermediate",
            "level_history": [],
            "preferences": {},
            "task_type_counts": {},
            "level_watch": None,
            "ai_engineering": {"mcp": {"status": "seen"}},
            "struggle_patterns": [],
            "teaching_history": [{"track": "ai_engineering", "topic": "mcp", "at": "2026-01-01"}],
            "last_taught_at": "2026-01-01",
            "turns_since_last_teach": 2,
        }
        new_state, changed = lib.migrate(old)

        self.assertTrue(changed)
        # Every V2/V3 field is untouched.
        for key, value in old.items():
            self.assertEqual(new_state[key], value)
        # New project-explorer fields get empty defaults.
        self.assertEqual(new_state["toured_projects"], {})
        self.assertEqual(new_state["declined_tours"], {})

    def test_bad_shaped_field_is_repaired(self):
        old = {"toured_projects": "not-a-dict", "declined_tours": ["nope"]}
        new_state, changed = lib.migrate(old)
        self.assertTrue(changed)
        self.assertEqual(new_state["toured_projects"], {})
        self.assertEqual(new_state["declined_tours"], {})

    def test_default_state_is_a_noop(self):
        state = lib.default_state()
        new_state, changed = lib.migrate(state)
        self.assertFalse(changed)
        self.assertEqual(new_state, state)

    def test_does_not_mutate_input(self):
        old = {"known_terms": {}, "sessions_taught": 0}
        lib.migrate(old)
        self.assertNotIn("toured_projects", old)
        self.assertNotIn("declined_tours", old)


class IsProjectNewTest(unittest.TestCase):
    def test_true_for_unknown_project(self):
        state = lib.default_state()
        self.assertTrue(lib.is_project_new(state, "git:github.com/a/b"))

    def test_false_once_toured(self):
        state = lib.default_state()
        state = lib.mark_project_toured(state, "git:github.com/a/b", "/x")
        self.assertFalse(lib.is_project_new(state, "git:github.com/a/b"))

    def test_false_once_declined(self):
        state = lib.default_state()
        state = lib.decline_tour(state, "git:github.com/a/b", "/x")
        self.assertFalse(lib.is_project_new(state, "git:github.com/a/b"))

    def test_different_ids_are_independent(self):
        state = lib.default_state()
        state = lib.mark_project_toured(state, "git:github.com/a/b", "/x")
        self.assertTrue(lib.is_project_new(state, "git:github.com/c/d"))


class MarkProjectTouredTest(unittest.TestCase):
    def test_records_first_toured_at_and_path_hint(self):
        state = lib.default_state()
        new_state = lib.mark_project_toured(
            state, "git:github.com/a/b", "/abs/path", today="2026-01-01"
        )
        self.assertEqual(
            new_state["toured_projects"]["git:github.com/a/b"],
            {"first_toured_at": "2026-01-01", "path_hint": "/abs/path"},
        )

    def test_idempotent_keeps_original_date(self):
        state = lib.default_state()
        state = lib.mark_project_toured(
            state, "git:github.com/a/b", "/abs/path", today="2026-01-01"
        )
        state = lib.mark_project_toured(
            state, "git:github.com/a/b", "/abs/path", today="2026-06-01"
        )
        self.assertEqual(
            state["toured_projects"]["git:github.com/a/b"]["first_toured_at"],
            "2026-01-01",
        )

    def test_does_not_mutate_input(self):
        state = lib.default_state()
        lib.mark_project_toured(state, "git:github.com/a/b", "/x")
        self.assertEqual(state["toured_projects"], {})

    def test_does_not_touch_v2_v3_fields(self):
        state = lib.default_state()
        state["sessions_taught"] = 5
        state["turns_since_last_teach"] = 2
        new_state = lib.mark_project_toured(state, "git:github.com/a/b", "/x")
        self.assertEqual(new_state["sessions_taught"], 5)
        self.assertEqual(new_state["turns_since_last_teach"], 2)
        self.assertEqual(new_state["teaching_history"], [])
        self.assertIsNone(new_state["last_taught_at"])


class DeclineTourTest(unittest.TestCase):
    def test_records_declined_at_and_path_hint(self):
        state = lib.default_state()
        new_state = lib.decline_tour(
            state, "git:github.com/a/b", "/abs/path", today="2026-01-01"
        )
        self.assertEqual(
            new_state["declined_tours"]["git:github.com/a/b"],
            {"declined_at": "2026-01-01", "path_hint": "/abs/path"},
        )

    def test_idempotent_keeps_original_date(self):
        state = lib.default_state()
        state = lib.decline_tour(state, "git:github.com/a/b", "/x", today="2026-01-01")
        state = lib.decline_tour(state, "git:github.com/a/b", "/x", today="2026-06-01")
        self.assertEqual(
            state["declined_tours"]["git:github.com/a/b"]["declined_at"], "2026-01-01"
        )

    def test_separate_dict_from_toured_projects(self):
        state = lib.default_state()
        state = lib.decline_tour(state, "git:github.com/a/b", "/x")
        self.assertEqual(state["toured_projects"], {})
        self.assertIn("git:github.com/a/b", state["declined_tours"])

    def test_toured_after_declined_both_recorded(self):
        state = lib.default_state()
        state = lib.decline_tour(state, "git:github.com/a/b", "/x", today="2026-01-01")
        state = lib.mark_project_toured(state, "git:github.com/a/b", "/x", today="2026-02-01")
        self.assertIn("git:github.com/a/b", state["declined_tours"])
        self.assertIn("git:github.com/a/b", state["toured_projects"])


class RecordConceptTest(unittest.TestCase):
    def test_new_topic_defaults_to_seen(self):
        state = lib.default_state()
        new_state = lib.record_concept(state, "Docker", today="2026-01-01")
        entry = new_state["ai_engineering"]["docker"]
        self.assertEqual(entry["status"], "seen")
        self.assertEqual(entry["times_seen"], 1)
        self.assertEqual(entry["last_seen"], "2026-01-01")

    def test_status_only_moves_up(self):
        state = lib.default_state()
        state = lib.record_concept(state, "docker", status="understood")
        state = lib.record_concept(state, "docker", status="seen")
        self.assertEqual(state["ai_engineering"]["docker"]["status"], "understood")

    def test_repeat_bumps_times_seen(self):
        state = lib.default_state()
        state = lib.record_concept(state, "docker")
        state = lib.record_concept(state, "docker")
        self.assertEqual(state["ai_engineering"]["docker"]["times_seen"], 2)

    def test_does_not_touch_v3_teaching_fields(self):
        state = lib.default_state()
        new_state = lib.record_concept(state, "docker")
        self.assertEqual(new_state["teaching_history"], [])
        self.assertIsNone(new_state["last_taught_at"])
        self.assertEqual(new_state["turns_since_last_teach"], 0)
        self.assertEqual(new_state["sessions_taught"], 0)
        self.assertEqual(new_state["known_terms"], {})

    def test_does_not_mutate_input(self):
        state = lib.default_state()
        lib.record_concept(state, "docker")
        self.assertEqual(state["ai_engineering"], {})


class RouterCheckProjectCliTest(TempDirMixin, unittest.TestCase):
    """CLI-level tests: router.py --check-project must never write."""

    def setUp(self):
        super().setUp()
        self.router = os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py")

    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, self.router] + list(args),
            capture_output=True,
            text=True,
        )
        return result

    def test_check_project_does_not_create_missing_profile(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)
        result = self._run("--check-project", plain, "--profile", profile)
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["is_new"])
        self.assertFalse(os.path.exists(profile))

    def test_check_project_does_not_upgrade_old_shape_profile_on_disk(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)
        old_shape = {"known_terms": {"x": "2026-01-01"}, "sessions_taught": 1}
        with open(profile, "w", encoding="utf-8") as f:
            json.dump(old_shape, f)
        with open(profile, encoding="utf-8") as f:
            before = f.read()

        self._run("--check-project", plain, "--profile", profile)

        with open(profile, encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(before, after)

    def test_check_project_rejects_combination_with_pick(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)
        result = self._run(
            "--check-project", plain, "--pick", "--candidate", "english:x",
            "--profile", profile,
        )
        self.assertNotEqual(result.returncode, 0)


class UpdateProfileProjectExplorerCliTest(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "update_profile.py"
        )

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, self.script] + list(args),
            capture_output=True,
            text=True,
        )

    def test_mark_toured_and_record_concept_leave_v2_v3_fields_untouched(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)

        self._run("--profile", profile, "--term", "seed", "--task-type", "refactor")
        with open(profile, encoding="utf-8") as f:
            before = json.load(f)

        self._run("--profile", profile, "--mark-toured", plain)
        self._run("--profile", profile, "--record-concept", "docker")
        with open(profile, encoding="utf-8") as f:
            after = json.load(f)

        for key in (
            "sessions_taught",
            "turns_since_last_teach",
            "last_taught_at",
            "teaching_history",
            "known_terms",
            "level",
        ):
            self.assertEqual(before[key], after[key], key)

    def test_mark_toured_then_check_project_is_false(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)

        self._run("--profile", profile, "--mark-toured", plain)
        router = os.path.join(os.path.dirname(self.script), "router.py")
        result = subprocess.run(
            [sys.executable, router, "--check-project", plain, "--profile", profile],
            capture_output=True,
            text=True,
        )
        self.assertFalse(json.loads(result.stdout)["is_new"])

    def test_mark_toured_conflicts_with_record_concept(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)
        result = self._run(
            "--profile", profile, "--mark-toured", plain, "--record-concept", "x"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_mark_toured_conflicts_with_check(self):
        profile = self._path("profile.json")
        plain = self._path("plain")
        os.makedirs(plain)
        result = self._run("--profile", profile, "--check", "--mark-toured", plain)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
