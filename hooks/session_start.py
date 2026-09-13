#!/usr/bin/env python3
"""SessionStart hook for the project-explorer skill.

Runs once, on real session startup only (matcher "startup" in
hooks.json - never on resume/clear/compact, so this never re-checks
mid-session). Reads the SessionStart JSON on stdin, computes the
project_id for `cwd` via router.py --check-project, and - only if this
project has never been toured or declined before - emits a one-line
tour invitation as additionalContext. It never runs the full tour and
never touches profile.json itself; router.py --check-project is
read-only.

Coupling note (intentional, not a silent assumption): this hook reaches
into skills/ai-learning-companion/scripts/ for router.py, because that
is the one place profile_lib's schema/migration logic lives and V2/V3
must not be duplicated. If that skill is ever renamed or removed, this
hook (and the project-explorer skill) need updating to match - it is
not a coincidence that the path below still says "ai-learning-companion".

Fails silently and safely: any missing file, bad JSON, non-zero exit,
or unexpected error results in no output and exit 0, so a broken hook
never blocks session startup and never surfaces noise to the user. It
also never calls anything that writes profile.json (--check, --track,
--mark-toured, etc.) - only the read-only --check-project path.
"""

import json
import os
import subprocess
import sys

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
ROUTER_PATH = os.path.join(
    PLUGIN_ROOT, "skills", "ai-learning-companion", "scripts", "router.py"
)


def _should_skip(cwd):
    """True for paths where offering a tour is never useful."""
    if not cwd:
        return True
    real = os.path.realpath(cwd)
    home = os.path.realpath(os.path.expanduser("~"))
    return real in (home, "/", os.path.realpath("/"))


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw else {}
        cwd = payload.get("cwd")

        if _should_skip(cwd) or not os.path.isfile(ROUTER_PATH):
            return 0

        result = subprocess.run(
            [sys.executable, ROUTER_PATH, "--check-project", cwd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return 0

        check = json.loads(result.stdout)
        if not check.get("is_new"):
            return 0

        context = (
            "This looks like a new project - want a quick walkthrough of "
            "what's where? (project-explorer skill, on-demand only - do not "
            "run the full tour unasked; just offer this one line.)"
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        )
        return 0
    except Exception:
        # Never block session startup or surface hook errors to the user.
        return 0


if __name__ == "__main__":
    sys.exit(main())
