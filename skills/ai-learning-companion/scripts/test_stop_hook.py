"""Unit tests for hooks/stop_teaching_check.py - stdlib unittest only, no
dependencies.

Run with:
    python3 -m unittest scripts.test_stop_hook -v
(from skills/ai-learning-companion/), or
    python3 test_stop_hook.py -v
(from scripts/).
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib as lib

HOOK_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "..", "hooks", "stop_teaching_check.py",
    )
)

_spec = importlib.util.spec_from_file_location("stop_teaching_check", HOOK_PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def prompt(text="please do it"):
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_results():
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        },
    }


def meta(text="injected skill text"):
    return {"type": "user", "isMeta": True, "message": {"role": "user", "content": text}}


def tool_use(name, **tool_input):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": name, "input": tool_input}],
        },
    }


def reply(text="done"):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


class IsTrivialCommandTest(unittest.TestCase):
    def test_reading_and_navigation_are_trivial(self):
        for command in [
            "ls -la",
            "cd src && cat app.py",
            "grep -rn foo . | head -20",
            "cat a.txt | wc -l",
            "find . -name '*.py' 2>/dev/null",
            "/bin/ls -la",
            "FOO=1 ls",
            "",
            "   ",
        ]:
            with self.subTest(command=command):
                self.assertTrue(hook.is_trivial_command(command))

    def test_real_commands_are_not_trivial(self):
        for command in [
            "npm install",
            "cd app && npm test",
            "python3 script.py",
            "FOO=1 npm run build",
            "/usr/bin/make",
            "ls\nnpm install",
            "ls; rm -rf build",
        ]:
            with self.subTest(command=command):
                self.assertFalse(hook.is_trivial_command(command))

    def test_git_always_counts_as_real_work(self):
        self.assertFalse(hook.is_trivial_command("git status"))
        self.assertFalse(hook.is_trivial_command("cd repo && git log -1"))

    def test_writing_redirects_are_not_trivial(self):
        self.assertFalse(hook.is_trivial_command("echo hi > out.txt"))
        self.assertFalse(hook.is_trivial_command("cat a >> b"))
        self.assertFalse(hook.is_trivial_command("echo hi>out.txt"))

    def test_writing_find_arguments_are_not_trivial(self):
        self.assertFalse(hook.is_trivial_command("find . -name '*.tmp' -delete"))
        self.assertFalse(hook.is_trivial_command("find . -name x -exec rm {} \\;"))

    def test_quoted_separators_are_not_operators(self):
        self.assertTrue(hook.is_trivial_command("grep -E 'a|b' file.txt"))
        self.assertTrue(hook.is_trivial_command("echo 'x; rm -rf y'"))

    def test_unparseable_command_counts_as_real_work(self):
        self.assertFalse(hook.is_trivial_command("echo 'oops"))


class TurnDidRealWorkTest(unittest.TestCase):
    def test_file_changing_tools_count(self):
        for name in ["Edit", "Write", "NotebookEdit"]:
            with self.subTest(tool=name):
                entries = [prompt(), tool_use(name, file_path="a.py"), tool_results(), reply()]
                self.assertTrue(hook.turn_did_real_work(entries))

    def test_non_trivial_command_counts(self):
        entries = [prompt(), tool_use("Bash", command="npm test"), tool_results(), reply()]
        self.assertTrue(hook.turn_did_real_work(entries))

    def test_powershell_command_counts(self):
        entries = [prompt(), tool_use("PowerShell", command="npm test"), tool_results(), reply()]
        self.assertTrue(hook.turn_did_real_work(entries))

    def test_read_only_tools_do_not_count(self):
        entries = [
            prompt(),
            tool_use("Read", file_path="a.py"),
            tool_results(),
            tool_use("Grep", pattern="foo"),
            tool_results(),
            reply(),
        ]
        self.assertFalse(hook.turn_did_real_work(entries))

    def test_trivial_command_does_not_count(self):
        entries = [prompt(), tool_use("Bash", command="ls -la"), tool_results(), reply()]
        self.assertFalse(hook.turn_did_real_work(entries))

    def test_pure_discussion_does_not_count(self):
        self.assertFalse(hook.turn_did_real_work([prompt(), reply()]))

    def test_work_in_a_previous_turn_only_does_not_count(self):
        entries = [
            prompt("first"),
            tool_use("Edit", file_path="a.py"),
            tool_results(),
            reply(),
            prompt("second"),
            reply(),
        ]
        self.assertFalse(hook.turn_did_real_work(entries))

    def test_tool_results_do_not_start_a_new_turn(self):
        entries = [
            prompt(),
            tool_use("Edit", file_path="a.py"),
            tool_results(),
            tool_use("Read", file_path="a.py"),
            tool_results(),
            reply(),
        ]
        self.assertTrue(hook.turn_did_real_work(entries))

    def test_meta_entries_do_not_start_a_new_turn(self):
        entries = [prompt(), tool_use("Write", file_path="a.py"), meta(), reply()]
        self.assertTrue(hook.turn_did_real_work(entries))

    def test_user_text_block_list_starts_a_new_turn(self):
        text_prompt = {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": "next"}]},
        }
        entries = [prompt(), tool_use("Edit", file_path="a.py"), tool_results(), text_prompt, reply()]
        self.assertFalse(hook.turn_did_real_work(entries))

    def test_sidechain_entries_are_ignored(self):
        sidechain_edit = tool_use("Edit", file_path="a.py")
        sidechain_edit["isSidechain"] = True
        self.assertFalse(hook.turn_did_real_work([prompt(), sidechain_edit, reply()]))

    def test_malformed_entries_are_ignored(self):
        entries = [
            prompt(),
            "garbage",
            {"type": "assistant", "message": None},
            {"type": "assistant", "message": {"content": "just a string"}},
            {
                "type": "assistant",
                "message": {"content": [None, {"type": "tool_use", "name": "Bash", "input": "not a dict"}]},
            },
        ]
        # A Bash call whose input isn't an object has no command to judge,
        # so it counts as trivial instead of crashing the hook.
        self.assertFalse(hook.turn_did_real_work(entries))
        # Malformed entries don't hide real work that comes after them.
        entries.append(tool_use("Edit", file_path="a.py"))
        self.assertTrue(hook.turn_did_real_work(entries))

    def test_empty_transcript_does_not_count(self):
        self.assertFalse(hook.turn_did_real_work([]))


class ShouldNudgeTest(unittest.TestCase):
    def setUp(self):
        self.work = [prompt(), tool_use("Edit", file_path="a.py"), tool_results(), reply()]

    def test_real_work_nudges(self):
        self.assertTrue(hook.should_nudge({"stop_hook_active": False}, self.work))

    def test_missing_flag_counts_as_false(self):
        self.assertTrue(hook.should_nudge({}, self.work))

    def test_stop_hook_active_never_nudges(self):
        self.assertFalse(hook.should_nudge({"stop_hook_active": True}, self.work))

    def test_no_real_work_never_nudges(self):
        self.assertFalse(hook.should_nudge({"stop_hook_active": False}, [prompt(), reply()]))

    def test_non_dict_payload_never_nudges(self):
        self.assertFalse(hook.should_nudge(["not", "a", "dict"], self.work))


class BuildOutputTest(unittest.TestCase):
    def test_shape_is_additional_context_not_block(self):
        output = hook.build_output({"can_teach": True, "turns_since_last_teach": 0, "min_gap": 3})
        self.assertEqual(set(output), {"hookSpecificOutput"})
        self.assertNotIn("decision", output)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertIsInstance(output["hookSpecificOutput"]["additionalContext"], str)

    def test_open_gate(self):
        message = hook.build_output({"can_teach": True, "turns_since_last_teach": 0, "min_gap": 3})
        self.assertIn("Teaching gate right now: open.", message["hookSpecificOutput"]["additionalContext"])

    def test_closed_gate_reports_progress(self):
        message = hook.build_output({"can_teach": False, "turns_since_last_teach": 1, "min_gap": 3})
        self.assertIn("closed (1 of 3", message["hookSpecificOutput"]["additionalContext"])

    def test_missing_gate_is_unavailable(self):
        for gate in [None, {}, "nonsense"]:
            with self.subTest(gate=gate):
                message = hook.build_output(gate)["hookSpecificOutput"]["additionalContext"]
                self.assertIn("Teaching gate right now: unavailable.", message)

    def test_message_points_at_check_and_change_summary(self):
        message = hook.build_output(None)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("update_profile.py --check", message)
        self.assertIn("Change Summary", message)


class ReadCurrentTurnTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="stop-hook-test-")
        self.path = os.path.join(self._tmp, "transcript.jsonl")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, lines):
        with open(self.path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write((line if isinstance(line, str) else json.dumps(line)) + "\n")

    def test_missing_or_empty_path_gives_nothing(self):
        self.assertEqual(hook.read_current_turn(os.path.join(self._tmp, "nope.jsonl")), [])
        self.assertEqual(hook.read_current_turn(None), [])
        self.assertEqual(hook.read_current_turn(""), [])

    def test_returns_only_the_last_turn_in_order(self):
        first, second = prompt("first"), prompt("second")
        edit, read = tool_use("Edit", file_path="a"), tool_use("Read", file_path="a")
        self._write([first, edit, tool_results(), second, read])
        self.assertEqual(hook.read_current_turn(self.path), [second, read])

    def test_skips_malformed_and_non_object_lines(self):
        p, edit = prompt(), tool_use("Edit", file_path="a")
        self._write(["not json", "[1, 2]", p, "", edit])
        self.assertEqual(hook.read_current_turn(self.path), [p, edit])

    def test_no_turn_start_returns_everything(self):
        edit = tool_use("Edit", file_path="a")
        self._write([edit, tool_results()])
        self.assertEqual(hook.read_current_turn(self.path), [edit, tool_results()])


class StopHookCliTest(unittest.TestCase):
    """End-to-end: the real script, real stdin, a temp transcript and a temp
    profile. CLAUDE_PLUGIN_ROOT is removed from the environment so the hook
    resolves router.py from this checkout, not an installed plugin copy."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="stop-hook-cli-test-")
        self.profile = os.path.join(self._tmp, "profile.json")
        self.transcript = os.path.join(self._tmp, "transcript.jsonl")
        self.env = dict(os.environ)
        self.env.pop("CLAUDE_PLUGIN_ROOT", None)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_transcript(self, entries):
        with open(self.transcript, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _run(self, stdin):
        return subprocess.run(
            [sys.executable, HOOK_PATH, "--profile", self.profile],
            input=stdin,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=30,
        )

    def _payload(self, **overrides):
        payload = {
            "session_id": "s1",
            "transcript_path": self.transcript,
            "cwd": self._tmp,
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "done",
        }
        payload.update(overrides)
        return json.dumps(payload)

    def test_real_work_turn_emits_additional_context_with_open_gate(self):
        self._write_transcript([prompt(), tool_use("Edit", file_path="a.py"), tool_results(), reply()])
        result = self._run(self._payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertIn("gate right now: open", output["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("decision", output)
        self.assertFalse(os.path.exists(self.profile))

    def test_closed_gate_still_nudges_and_profile_is_untouched(self):
        state = lib.default_state()
        state["last_taught_at"] = "2026-01-01"
        state["turns_since_last_teach"] = 1
        with open(self.profile, "w", encoding="utf-8") as f:
            json.dump(state, f)
        with open(self.profile, encoding="utf-8") as f:
            before = f.read()
        self._write_transcript([prompt(), tool_use("Bash", command="npm test"), tool_results(), reply()])

        result = self._run(self._payload())

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("closed (1 of 3", output["hookSpecificOutput"]["additionalContext"])
        with open(self.profile, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def test_stop_hook_active_is_silent(self):
        self._write_transcript([prompt(), tool_use("Edit", file_path="a.py"), tool_results(), reply()])
        result = self._run(self._payload(stop_hook_active=True))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_discussion_only_turn_is_silent(self):
        self._write_transcript([prompt(), reply()])
        result = self._run(self._payload())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_missing_transcript_is_silent(self):
        result = self._run(self._payload(transcript_path=os.path.join(self._tmp, "nope.jsonl")))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_garbage_or_empty_stdin_is_silent(self):
        for stdin in ["not json at all", "", "[1, 2, 3]"]:
            with self.subTest(stdin=stdin):
                result = self._run(stdin)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
