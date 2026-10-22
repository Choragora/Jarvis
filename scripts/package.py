"""Produce a source delivery archive, excluding all runtime data and installed dependencies."""

import hashlib
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    target = root.parent / "Jarvis-Windows-source.zip"
    excluded = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "data",
        "dist",
        "build",
        "test-results",
        ".tools",
    }
    files = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts) or path.suffix == ".pyc" or not path.is_file():
            continue
        if path.name in {"settings.json", "instance.json", "auth.json", "memory.sqlite3"}:
            raise RuntimeError("Runtime data found in source tree; do not package it.")
        files.append(path)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path("Jarvis") / path.relative_to(root))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n")
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert "Jarvis/INICIAR_JARVIS.bat" in archive.namelist()
        assert "Jarvis/jarvis/web/app.js" in archive.namelist()
    print(f"{target}: {len(files)} source files, {target.stat().st_size} bytes, SHA-256 {digest}")


if __name__ == "__main__":
    main()
