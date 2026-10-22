from __future__ import annotations

import asyncio
import platform
import queue
import re
import threading
import time
import uuid
from collections import deque


class Audio:
    """One microphone owner; incremental recognition and one cancellable synthesis queue."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.loop = None
        self.stream = None
        self.frames = asyncio.Queue(maxsize=100)
        self.model = None
        self.recognition_lock = asyncio.Lock()
        self.model_lock = asyncio.Lock()
        self.listening = False
        self.ptt = False
        self.wake_armed_until = 0.0
        self.worker_task = None
        self.speech_queue = queue.Queue(maxsize=100)
        self.speech_stop = threading.Event()
        self.shutdown = threading.Event()
        self.generation = 0
        self.speaking = False
        self.last_spoken = ""
        self.output_device = None
        self.voice_thread = None
        self.error = None

    def emit(self, kind, **kwargs):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(lambda: self.runtime.events.emit(kind, **kwargs))

    def devices(self):
        try:
            import sounddevice as sd

            return {
                "devices": [
                    dict(
                        id=i,
                        name=d["name"],
                        inputs=d["max_input_channels"],
                        outputs=d["max_output_channels"],
                        default_sample_rate=d["default_samplerate"],
                    )
                    for i, d in enumerate(sd.query_devices())
                ],
                "default": list(sd.default.device),
            }
        except Exception as e:
            return {"devices": [], "error": str(e)}

    def voices(self):
        if platform.system() != "Windows":
            return {"voices": [], "error": "SAPI disponível apenas no Windows."}
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            return {
                "voices": [
                    {"id": v.Id, "name": v.GetDescription(), "language": v.GetAttribute("Language")}
                    for v in voice.GetVoices()
                ]
            }
        finally:
            pythoncom.CoUninitialize()

    async def warm(self, download=False):
        self.loop = asyncio.get_running_loop()
        async with self.model_lock:
            if self.model is not None:
                return {"loaded": True, "model": self.runtime.settings.stt_model}
            self.runtime.events.emit("audio", status="loading", message="A carregar reconhecimento local…")
            from faster_whisper import WhisperModel

            cfg = self.runtime.settings

            def load():
                return WhisperModel(
                    cfg.stt_model,
                    device=cfg.stt_device,
                    compute_type="int8" if cfg.stt_device == "cpu" else "float16",
                    cpu_threads=4,
                    download_root=str(self.runtime.root / "models"),
                    local_files_only=not download,
                )

            try:
                self.model = await asyncio.to_thread(load)
                # Exercise the inference path and warm kernels; silence is not a quality test.
                import numpy as np

                await asyncio.to_thread(
                    lambda: list(
                        self.model.transcribe(
                            np.zeros(16000, dtype=np.float32), language=cfg.language, beam_size=1
                        )[0]
                    )
                )
                self.error = None
            except Exception as e:
                self.error = "Modelo STT indisponível. Prepare o modelo nas definições; requer Internet na primeira vez."
                self.runtime.events.emit("audio", status="error", message=self.error)
                raise RuntimeError(self.error) from e
            self.runtime.events.emit("audio", status="ready", message="Reconhecimento local preparado.")
            return {"loaded": True, "model": cfg.stt_model, "device": cfg.stt_device}

    async def start(self, ptt=False):
        self.loop = asyncio.get_running_loop()
        if not ptt and not self.runtime.settings.headphones_confirmed:
            raise PermissionError(
                "O modo mãos livres requer auscultadores confirmados. Com colunas, use premir para falar; AEC nativo ainda não validado."
            )
        if self.runtime.stopped:
            raise PermissionError("Retome o Jarvis antes de ligar o microfone.")
        await self.warm()
        self.ptt = ptt
        if self.stream:
            self.listening = True
            return
        import sounddevice as sd
        import webrtcvad

        self.vad = webrtcvad.Vad(self.runtime.settings.vad_aggressiveness)

        def callback(data, frames, timing, status):
            chunk = bytes(data)
            self.loop.call_soon_threadsafe(self.enqueue_frame, chunk, time.monotonic())

        self.stream = sd.RawInputStream(
            samplerate=16000,
            channels=1,
            dtype="int16",
            blocksize=480,
            device=self.runtime.settings.microphone,
            callback=callback,
        )
        self.stream.start()
        self.listening = True
        self.worker_task = asyncio.create_task(self.recognize_loop())
        self.runtime.events.emit(
            "audio", status="listening", microphone=True, mode="ptt" if ptt else "hands_free"
        )

    def enqueue_frame(self, data, at):
        if self.frames.full():
            self.frames.get_nowait()
        self.frames.put_nowait((data, at))

    async def finish_ptt(self):
        await self.frames.put((b"", time.monotonic()))

    async def stop_input(self):
        self.listening = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self.worker_task:
            self.worker_task.cancel()
            self.worker_task = None
        while not self.frames.empty():
            self.frames.get_nowait()
        self.runtime.events.emit("audio", status="off", microphone=False)

    async def transcribe(self, raw):
        import numpy as np

        async with self.recognition_lock:

            def run():
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                segments, _ = self.model.transcribe(
                    audio,
                    language=self.runtime.settings.language,
                    beam_size=1,
                    best_of=1,
                    condition_on_previous_text=False,
                    vad_filter=True,
                )
                return " ".join(s.text.strip() for s in segments).strip()

            return await asyncio.to_thread(run)

    async def recognize_loop(self):
        pre = deque(maxlen=5)
        chunks = []
        last_voice = last_partial = first_voice = 0.0
        partial_task = None
        utterance = str(uuid.uuid4())
        try:
            while True:
                data, at = await self.frames.get()
                forced = not data
                voiced = bool(data) and self.vad.is_speech(data, 16000)
                if not self.listening and not forced:
                    continue
                if voiced:
                    if not chunks:
                        chunks = list(pre)
                        first_voice = at
                        utterance = str(uuid.uuid4())
                    last_voice = at
                    # Barge-in is local and never waits for inference.
                    if (
                        self.speaking
                        and (self.ptt or self.runtime.settings.headphones_confirmed)
                        and at - first_voice >= 0.09
                    ):
                        self.runtime.interrupt_conversation()
                if chunks:
                    chunks.append(data)
                else:
                    pre.append(data)
                if chunks and at - last_partial >= 0.65 and (partial_task is None or partial_task.done()):
                    last_partial = at
                    partial_task = asyncio.create_task(self.partial(b"".join(chunks), utterance))
                end = forced or (
                    not self.ptt and chunks and at - last_voice >= self.runtime.settings.endpoint_ms / 1000
                )
                if chunks and at - first_voice > 30:
                    self.runtime.events.emit(
                        "audio",
                        status="error",
                        message="Instrução demasiado longa; divida o pedido. Nada foi executado.",
                    )
                    chunks = []
                if end and chunks:
                    raw = b"".join(chunks)
                    acoustic_end = last_voice
                    chunks = []
                    endpoint_at = time.monotonic()
                    if partial_task:
                        await partial_task
                    if len(raw) >= 16000 * 0.18 * 2:
                        text = await self.transcribe(raw)
                        # A content echo guard supplements the required headphone/PTT policy.
                        # It is not advertised as an acoustic echo canceller.
                        from difflib import SequenceMatcher

                        if (
                            self.last_spoken
                            and SequenceMatcher(None, text.casefold(), self.last_spoken.casefold()).ratio()
                            > 0.78
                        ):
                            self.runtime.events.emit(
                                "audio",
                                status="echo_rejected",
                                message="Transcrição semelhante à resposta falada foi descartada; nenhuma ação executada.",
                            )
                            text = ""
                        self.runtime.events.emit("transcript", text=text, final=True, utterance=utterance)
                        if text:
                            normalized = text.casefold().strip(" .!?")
                            active = (
                                self.ptt or time.monotonic() < self.wake_armed_until or "jarvis" in normalized
                            )
                            if "jarvis" in normalized:
                                self.wake_armed_until = time.monotonic() + 30
                                text = re.sub(r"\bjarvis\b[,\s]*", "", text, flags=re.IGNORECASE).strip()
                            if active and text:
                                self.runtime.submit_chat(
                                    text,
                                    origin="microphone",
                                    timing={
                                        "acoustic_end": acoustic_end,
                                        "endpoint_confirmed": endpoint_at,
                                        "transcript_stable": time.monotonic(),
                                    },
                                )
                    pre.clear()
                if forced and self.ptt:
                    await self.stop_input()
                    return
        except asyncio.CancelledError:
            if partial_task:
                partial_task.cancel()

    async def partial(self, raw, utterance):
        text = await self.transcribe(raw)
        self.runtime.events.emit("transcript", text=text, final=False, utterance=utterance)
        normalized = text.casefold().strip(" .!?")
        if normalized in {
            "pára",
            "para",
            "parar",
            "stop",
            "cancela",
            "cancelar",
            "jarvis para",
            "jarvis pára",
        }:
            self.runtime.emergency_stop()

    def begin_speech(self):
        self.cancel_speech()
        self.speech_stop.clear()
        self.loop = asyncio.get_running_loop()
        if not self.runtime.settings.speech_enabled:
            return self.generation
        if not self.voice_thread or not self.voice_thread.is_alive():
            self.voice_thread = threading.Thread(
                target=self.sapi_loop, name="jarvis-audio-output", daemon=True
            )
            self.voice_thread.start()
        return self.generation

    def say(self, text, generation):
        if (
            self.runtime.settings.speech_enabled
            and generation == self.generation
            and not self.speech_queue.full()
        ):
            # Strip markup/URLs from speech, retain the detailed answer in the UI.
            text = re.sub(r"https?://\S+", "", text)
            text = re.sub(r"[*#`_]", "", text).strip()
            if text:
                self.speech_queue.put((generation, text))

    def cancel_speech(self):
        self.generation += 1
        self.speech_stop.set()
        while True:
            try:
                self.speech_queue.get_nowait()
            except queue.Empty:
                break
        self.speaking = False

    def sapi_loop(self):
        if platform.system() != "Windows":
            self.emit(
                "audio",
                status="unavailable",
                message="Síntese SAPI requer Windows. Resposta disponível em texto.",
            )
            return
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            while not self.shutdown.is_set():
                try:
                    generation, text = self.speech_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if generation != self.generation:
                    continue
                cfg = self.runtime.settings
                if cfg.tts_provider != "sapi":
                    try:
                        self.play_online(generation, text, cfg)
                    except Exception:
                        self.emit(
                            "audio",
                            status="error",
                            message="Síntese online falhou. Verifique credencial, modelo, voz, saldo e autorização de custos; não houve repetição automática.",
                        )
                    continue
                voices = list(voice.GetVoices())
                selected = next((v for v in voices if v.Id == cfg.sapi_voice), None)
                if selected is None:
                    selected = next((v for v in voices if "816" in v.GetAttribute("Language").lower()), None)
                if selected is None:
                    self.emit(
                        "audio",
                        status="error",
                        message="Não existe uma voz SAPI pt-PT acessível. Escolha uma voz instalada nas definições.",
                    )
                    continue
                voice.Voice = selected
                # SAPI uses its Windows default output. Do not imply sounddevice output IDs route SAPI.
                self.last_spoken = text
                voice.Speak(text, 1)
                while not voice.WaitUntilDone(20):
                    pythoncom.PumpWaitingMessages()
                    if generation != self.generation or self.shutdown.is_set():
                        voice.Speak("", 3)
                        break
                    if not self.speaking and voice.Status.RunningState == 2:
                        self.speaking = True
                        self.emit(
                            "playback",
                            playing=True,
                            generation=generation,
                            backend="SAPI",
                            measurement="SAPI RunningState=2; nível e saída acústica não medidos",
                        )
                self.speaking = False
                self.emit("playback", playing=False, generation=generation)
        except Exception:
            self.emit(
                "audio",
                status="error",
                message="Falha na síntese Windows. Consulte o diagnóstico de vozes SAPI.",
            )
        finally:
            pythoncom.CoUninitialize()

    def play_online(self, generation, text, cfg):
        from .providers import pcm_chunks
        import sounddevice as sd

        chunks = pcm_chunks(cfg.tts_provider, cfg, text)
        pending = b""
        last_level = 0.0
        try:
            with sd.RawOutputStream(
                samplerate=24000, channels=1, dtype="int16", device=cfg.speaker, blocksize=480
            ) as stream:
                for chunk in chunks:
                    if generation != self.generation or self.shutdown.is_set():
                        stream.abort()
                        break
                    pending += chunk
                    while len(pending) >= 960:
                        if generation != self.generation:
                            stream.abort()
                            return
                        frame, pending = pending[:960], pending[960:]
                        stream.write(frame)
                        if time.monotonic() - last_level >= 0.06:
                            import numpy as np

                            rms = float(
                                np.sqrt(
                                    np.mean(
                                        (np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0)
                                        ** 2
                                    )
                                )
                            )
                            self.emit("audio_level", level=min(1, rms * 5), generation=generation)
                            last_level = time.monotonic()
                        if not self.speaking:
                            self.speaking = True
                            self.emit(
                                "playback",
                                playing=True,
                                generation=generation,
                                backend=cfg.tts_provider,
                                measurement="PCM escrito no dispositivo; latência acústica por medir",
                            )
                if pending and generation == self.generation:
                    stream.write(pending[: len(pending) // 2 * 2])
        finally:
            chunks.close()
            self.speaking = False
            self.emit("audio_level", level=0, generation=generation)
            self.emit("playback", playing=False, generation=generation)

    async def close(self):
        self.shutdown.set()
        self.cancel_speech()
        await self.stop_input()
        if self.voice_thread:
            await asyncio.to_thread(self.voice_thread.join, 2)
