"""Real Windows cmd checks; explicitly skipped when a Windows runner is unavailable."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows cmd.exe")
ROOT = Path(__file__).resolve().parents[1]


def run_check(environment):
    return subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "INSTALAR.bat", "--check-python"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def test_python_without_launcher_or_path_entry():
    env = os.environ.copy()
    env["JARVIS_PYTHON"] = sys.executable
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    result = run_check(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "JARVIS_PYTHON=" + sys.executable in result.stdout


def test_invalid_explicit_path_falls_back_to_installed_python():
    env = os.environ.copy()
    env["JARVIS_PYTHON"] = str(ROOT / "missing-python.exe")
    env["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    )
    result = run_check(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "JARVIS_PYTHON=" in result.stdout
    assert "missing-python.exe" not in result.stdout
