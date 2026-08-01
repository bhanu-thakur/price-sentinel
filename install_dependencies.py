"""Install the dependencies declared by this repository."""

from pathlib import Path
import subprocess
import sys


def main():
    requirements = Path(__file__).resolve().with_name("requirements.txt")
    if not requirements.is_file():
        raise SystemExit(f"Missing dependency file: {requirements}")

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements),
    ]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
