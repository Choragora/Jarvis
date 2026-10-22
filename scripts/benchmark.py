"""Measure real local text commands; never label these as a voice benchmark."""

import asyncio
import json
import math
import platform
import statistics
import tempfile
from pathlib import Path

import psutil

from jarvis.runtime import Runtime


async def benchmark():
    with tempfile.TemporaryDirectory(prefix="jarvis-text-benchmark-") as folder:
        runtime = Runtime(Path(folder))
        runtime.settings.speech_enabled = False
        turns = []
        for i in range(30):
            text = (
                "Lembra-te de que a nota de teste " + str(i) + " usa português de Portugal."
                if i % 2 == 0
                else "O que te pedi para recordar?"
            )
            await runtime.chat(str(i), text, "benchmark_local_text", None, None)
            metrics = json.loads(
                runtime.store.query("SELECT data FROM metrics WHERE id=?", (str(i),))[0]["data"]
            )
            turns.append(metrics)
        samples = []
        # This measures the command work from user-message persistence to useful text,
        # independently of STT, provider inference, TTS and speaker output.
        for t in turns:
            samples.append(t["local_command_ms"])
        await runtime.audio.close()
        runtime.store.close()
    return {
        "profile": "local-command-text",
        "turn_count": len(turns),
        "hardware": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cores": psutil.cpu_count(),
            "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        },
        "median_ms": statistics.median(samples),
        "p95_ms": sorted(samples)[math.ceil(len(samples) * 0.95) - 1],
        "failures": sum(t["status"] != "completed" for t in turns),
        "methodology": "30 local text commands, alternating real SQLite note writes and recall in a temporary database. No mocked tools. First command cold; subsequent commands warm. No microphone, model inference or audible output measured.",
        "voice_profiles": "unmeasured: requires Windows audio hardware, SAPI voice, STT model and authenticated Codex",
        "turns": turns,
    }


if __name__ == "__main__":
    result = asyncio.run(benchmark())
    target = Path("docs/local-text-benchmark.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "turns"}, ensure_ascii=False, indent=2))
