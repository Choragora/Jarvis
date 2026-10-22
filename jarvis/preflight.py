"""Readiness report, without turning unavailable hardware into a pass."""

import importlib.util
import json
import platform
import subprocess

from .codex import PINNED_VERSION, executable_command


def main():
    results = {"platform": platform.platform(), "python": platform.python_version(), "checks": []}
    for module in ("fastapi", "sounddevice", "faster_whisper", "webview", "mss"):
        found = importlib.util.find_spec(module) is not None
        results["checks"].append({"name": module, "status": "installed" if found else "missing"})
    try:
        command = executable_command()
        version = subprocess.run(
            command + ["--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        results["checks"].append(
            {
                "name": "Codex",
                "version": version,
                "status": "installed" if version == "codex-cli " + PINNED_VERSION else "wrong_version",
            }
        )
    except Exception:
        results["checks"].append({"name": "Codex", "status": "missing_or_unusable"})
    results["checks"].extend(
        {"name": name, "status": "pending_local_test"}
        for name in ("STT acústico", "SAPI pt-PT", "dois monitores e DPI misto", "conta ChatGPT", "WebView2")
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(c["status"] in {"missing", "missing_or_unusable", "wrong_version"} for c in results["checks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
