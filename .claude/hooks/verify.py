"""Stop-hook gate: an agent may not end a turn on a red test suite.

Claude Code treats exit code 2 as "block the turn and hand stderr back to the
agent". pytest exits 1 for test failures and 2..5 for its own errors, so this
wrapper runs the suite and translates any non-zero result into exit 2, with the
pytest output on stderr where the agent will actually read it.

Documented cap: after 8 consecutive blocks Claude Code overrides the hook and
lets the turn end anyway. That is a backstop against an unfixable loop, not a
licence to keep retrying.
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]


def main():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return 0
    sys.stderr.write(
        "Stop hook: the test suite is not green, so this turn is blocked.\n"
        f"Command: python -m pytest tests -q   (cwd {REPO})\n"
        f"pytest exit code: {result.returncode}\n\n"
        f"{result.stdout}\n{result.stderr}\n"
        "Fix the cause. Do not edit a test to make it pass; if a test is "
        "genuinely wrong, stop and say so (see AGENTS.md, 'Tests come first').\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
