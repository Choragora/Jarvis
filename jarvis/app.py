from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .runtime import Runtime
from .settings import Settings, save_settings

ASSETS = Path(__file__).parent / "web"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=20000)
    captures: list[str] = Field(default_factory=list, max_length=4)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    arguments: dict = Field(default_factory=dict)


def create_app(root: Path, bootstrap_token: str | None = None):
    runtime = Runtime(root)
    token = bootstrap_token or secrets.token_urlsafe(32)
    session = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        await runtime.start()
        yield
        await runtime.close()

    app = FastAPI(title="Jarvis", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = runtime
    app.state.bootstrap_token = token
    app.state.shutdown_callback = None

    def valid_origin(origin, host):
        return origin == "http://" + host

    @app.middleware("http")
    async def protection(request: Request, call_next):
        host = request.headers.get("host", "")
        if host.split(":")[0] not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Host recusado."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and not valid_origin(origin, host):
            return JSONResponse({"detail": "Origem recusada."}, status_code=403)
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            if not secrets.compare_digest(request.cookies.get("jarvis_session", ""), session):
                return JSONResponse({"detail": "Sessão local necessária."}, status_code=401)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/session")
    async def authenticate(request: Request):
        data = await request.json()
        supplied = data.get("token", "")
        if not isinstance(supplied, str) or not secrets.compare_digest(supplied, token):
            raise HTTPException(401, "Token inválido.")
        response = JSONResponse({"authenticated": True})
        response.set_cookie("jarvis_session", session, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/")
    async def index():
        return FileResponse(ASSETS / "index.html")

    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")

    @app.get("/health")
    async def health():
        return {"service": "jarvis", "status": "running", "version": "0.1.0"}

    @app.get("/api/state")
    async def state():
        return {
            "settings": runtime.settings.model_dump(),
            "stopped": runtime.stopped,
            "codex": runtime.codex.status(),
            "messages": runtime.store.query("SELECT * FROM messages ORDER BY created DESC LIMIT 100")[::-1],
            "tasks": runtime.store.query("SELECT * FROM tasks ORDER BY created DESC LIMIT 50"),
            "notes": runtime.store.notes(),
            "routines": runtime.store.query("SELECT * FROM routines"),
            "audio": {
                "listening": runtime.audio.listening,
                "speaking": runtime.audio.speaking,
                "loaded": runtime.audio.model is not None,
            },
        }

    @app.get("/api/settings")
    async def get_settings():
        return runtime.settings.model_dump()

    @app.put("/api/settings")
    async def settings(value: Settings):
        old = runtime.settings
        if value.timezone != "Europe/Lisbon":
            raise HTTPException(422, "Este agendador usa Europe/Lisbon.")
        if value.speaker is not None and value.tts_provider == "sapi":
            raise HTTPException(
                422,
                "A saída SAPI segue o dispositivo predefinido do Windows. Altere-o nas definições de som do Windows.",
            )
        if value.tts_provider != "sapi" and not value.online_costs_accepted:
            raise HTTPException(422, "Autorize os custos antes de selecionar uma voz online.")
        if value.hands_free and not value.headphones_confirmed:
            raise HTTPException(422, "Confirme auscultadores antes de ativar mãos livres.")
        for region in value.hidden_regions:
            if region[2] <= region[0] or region[3] <= region[1]:
                raise HTTPException(422, "Região oculta inválida; use [esquerda,cima,direita,baixo].")
        await runtime.audio.stop_input()
        runtime.audio.cancel_speech()
        if (old.stt_model, old.stt_device, old.language) != (
            value.stt_model,
            value.stt_device,
            value.language,
        ):
            runtime.audio.model = None
        if old.codex_model != value.codex_model:
            await runtime.codex.interrupt()
            runtime.codex.thread_id = None
        runtime.settings = value
        runtime.desktop.settings = value
        await asyncio.to_thread(save_settings, root, value)
        return {"saved": True}

    @app.post("/api/chat")
    async def chat(message: Message):
        images = []
        if message.captures:
            if not runtime.settings.screen_send:
                raise HTTPException(
                    403, "Ative o envio de capturas e anexe apenas as que pretende partilhar."
                )
            for filename in message.captures:
                path = capture_path(filename)
                if not path.exists():
                    raise HTTPException(404, "Captura não encontrada.")
                images.append(path)
            runtime.events.emit("capture_sent", files=message.captures)
        return {"turn_id": runtime.submit_chat(message.text, images=images)}

    @app.post("/api/actions")
    async def action(action: Action):
        try:
            runtime.tools.validate(action.action, action.arguments)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        tid = runtime.store.task(action.action, action.arguments)
        asyncio.create_task(runtime.execute(action.action, action.arguments, tid))
        return {"task_id": tid}

    @app.post("/api/stop")
    async def stop():
        runtime.emergency_stop()
        return {"stopped": True}

    @app.post("/api/resume")
    async def resume():
        runtime.resume()
        return {"stopped": False}

    @app.post("/api/shutdown")
    async def shutdown():
        runtime.emergency_stop()
        if app.state.shutdown_callback:
            app.state.shutdown_callback()
        return {"shutting_down": True}

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel(task_id: str):
        if task_id in runtime.jobs:
            runtime.jobs[task_id].cancel()
        else:
            runtime.store.write(
                "UPDATE tasks SET status='cancelled' WHERE id=? AND status='waiting'", (task_id,)
            )
        return {"cancel_requested": True}

    @app.get("/api/notes")
    async def notes(q: str = ""):
        return runtime.store.notes(q)

    @app.post("/api/notes")
    async def add_note(request: Request):
        from .tools import MemorySave

        note = MemorySave.model_validate(await request.json())
        return runtime.store.note(note.title, note.body)

    @app.put("/api/notes/{note_id}")
    async def edit_note(note_id: str, request: Request):
        from .tools import MemorySave

        if not runtime.store.query("SELECT id FROM notes WHERE id=?", (note_id,)):
            raise HTTPException(404, "Nota não encontrada.")
        note = MemorySave.model_validate(await request.json())
        return runtime.store.note(note.title, note.body, note_id=note_id)

    @app.delete("/api/notes/{note_id}")
    async def delete_note(note_id: str):
        runtime.store.write("DELETE FROM notes WHERE id=?", (note_id,))
        return {"deleted": True}

    @app.get("/api/export")
    async def export():
        return JSONResponse(
            {"notes": runtime.store.notes(), "routines": runtime.store.query("SELECT * FROM routines")},
            headers={"Content-Disposition": 'attachment; filename="jarvis-memory.json"'},
        )

    @app.get("/api/graph")
    async def graph():
        notes = runtime.store.notes()
        links = []
        for a in notes:
            for b in notes:
                if a["id"] != b["id"] and "[[" + b["title"] + "]]" in a["body"]:
                    links.append({"source": a["id"], "target": b["id"]})
        return {"nodes": notes, "links": links}

    @app.get("/api/routines")
    async def routines():
        return runtime.store.query("SELECT * FROM routines")

    @app.post("/api/routines/{routine_id}/toggle")
    async def toggle(routine_id: str):
        runtime.store.write("UPDATE routines SET enabled=1-enabled WHERE id=?", (routine_id,))
        return {"updated": True}

    @app.put("/api/routines/{routine_id}")
    async def edit_routine(routine_id: str, request: Request):
        from .tools import Reminder

        args = Reminder.model_validate(await request.json())
        if not runtime.store.query("SELECT id FROM routines WHERE id=?", (routine_id,)):
            raise HTTPException(404, "Rotina não encontrada.")
        if any(day < 0 or day > 6 for day in args.weekdays):
            raise HTTPException(422, "Dias da semana inválidos.")
        steps = [{"action": "app_open", "arguments": {"application": app}} for app in args.applications]
        return runtime.store.edit_routine(routine_id, args.name, args.hour, args.minute, args.weekdays, steps)

    @app.delete("/api/routines/{routine_id}")
    async def delete_routine(routine_id: str):
        runtime.store.write("DELETE FROM routines WHERE id=?", (routine_id,))
        return {"deleted": True}

    @app.get("/api/desktop")
    async def desktop():
        try:
            return await asyncio.to_thread(
                lambda: {"monitors": runtime.desktop.monitors(), "windows": runtime.desktop.windows()}
            )
        except RuntimeError as e:
            return {"monitors": [], "windows": [], "error": str(e)}

    @app.post("/api/capture")
    async def capture(request: Request):
        from .tools import Monitor

        args = Monitor.model_validate(await request.json())
        return await runtime.execute("screen_capture", args.model_dump())

    def capture_path(filename):
        import re

        if not re.fullmatch(r"[0-9a-f-]{36}\.png", filename):
            raise HTTPException(400, "Nome de captura inválido.")
        path = root / "captures" / filename
        from .desktop import capture_fingerprint

        metadata = path.with_suffix(".json")
        if path.exists():
            if not metadata.exists() or json.loads(metadata.read_text())[
                "redaction_fingerprint"
            ] != capture_fingerprint(runtime.settings):
                raise HTTPException(
                    409,
                    "As regras de privacidade mudaram. Faça uma nova captura antes de visualizar ou enviar.",
                )
        return path

    @app.get("/api/captures/{filename}")
    async def capture_file(filename: str):
        path = capture_path(filename)
        if not path.is_file():
            raise HTTPException(404, "Captura não encontrada.")
        return FileResponse(path)

    @app.get("/api/audio/devices")
    async def devices():
        return await asyncio.to_thread(runtime.audio.devices)

    @app.get("/api/audio/voices")
    async def voices():
        return await asyncio.to_thread(runtime.audio.voices)

    @app.get("/api/providers")
    async def providers():
        from .providers import status

        return {name: await asyncio.to_thread(status, name) for name in ("fish", "openai")}

    @app.post("/api/providers/ollama/catalog")
    async def ollama_catalog():
        from .offline import catalogue

        return await catalogue()

    @app.post("/api/providers/fish/catalog")
    async def fish_catalog():
        from .providers import fish_catalog

        try:
            return await asyncio.to_thread(fish_catalog)
        except Exception as e:
            raise HTTPException(
                409,
                "Não foi possível consultar a conta Fish. Configure a credencial, dependências e acesso à API no Windows.",
            ) from e

    @app.post("/api/audio/prepare")
    async def prepare():
        try:
            return await runtime.audio.warm(download=True)
        except Exception as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/audio/start")
    async def start_audio(request: Request):
        data = await request.json()
        try:
            await runtime.audio.start(ptt=data.get("mode") == "ptt")
        except Exception as e:
            raise HTTPException(409, str(e)) from e
        return {"listening": True}

    @app.post("/api/audio/finish")
    async def finish_audio():
        await runtime.audio.finish_ptt()
        return {"finalizing": True}

    @app.post("/api/audio/stop")
    async def stop_audio():
        await runtime.audio.stop_input()
        return {"listening": False}

    @app.post("/api/audio/test")
    async def test_audio():
        generation = runtime.audio.begin_speech()
        runtime.audio.say("Olá. Sou o Jarvis. Este é um teste da voz instalada no seu Windows.", generation)
        return {"queued": True, "verified": False, "instruction": "Confirme no assistente se ouviu a frase."}

    @app.post("/api/codex/connect")
    async def connect():
        try:
            return await runtime.codex.refresh()
        except Exception as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/codex/login")
    async def login():
        try:
            return await runtime.codex.login()
        except Exception as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/codex/login/cancel")
    async def cancel_login():
        await runtime.codex.cancel_login()
        return {"cancelled": True}

    @app.post("/api/codex/logout")
    async def logout():
        await runtime.codex.logout()
        return {"logged_out": True}

    @app.get("/api/diagnostics")
    async def diagnostics():
        import platform

        return {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor(),
            "logical_cores": psutil.cpu_count(),
            "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "process_memory_mb": round(psutil.Process().memory_info().rss / 2**20, 1),
            "codex": runtime.codex.status(),
            "audio": {
                "model_loaded": runtime.audio.model is not None,
                "error": runtime.audio.error,
                "output": "Windows SAPI; dispositivo predefinido do Windows",
            },
            "metrics": [
                json.loads(m["data"])
                for m in runtime.store.query("SELECT data FROM metrics ORDER BY rowid DESC LIMIT 100")
            ],
            "pending": [
                "Teste acústico STT/TTS no Windows",
                "DPI misto e mudança de monitores",
                "Eco com colunas: AEC indisponível; use PTT ou auscultadores",
                "Fish Audio/OpenAI: opcionais; não ativados",
            ],
            "data_directory": str(root),
            "hotkey_error": runtime.hotkey_error,
        }

    @app.websocket("/api/events")
    async def events(ws: WebSocket):
        host = ws.headers.get("host", "")
        if (
            host.split(":")[0] not in {"127.0.0.1", "localhost"}
            or not valid_origin(ws.headers.get("origin"), host)
            or not secrets.compare_digest(ws.cookies.get("jarvis_session", ""), session)
        ):
            await ws.close(code=1008)
            return
        await ws.accept()
        queue = asyncio.Queue(maxsize=200)
        runtime.events.clients.add(queue)
        try:
            while True:
                await ws.send_json(await queue.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            runtime.events.clients.discard(queue)

    return app
