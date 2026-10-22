from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import time
import urllib.request
from pathlib import Path

from .desktop import enable_dpi
from .settings import atomic_text, data_directory


def main():
    parser = argparse.ArgumentParser(description="Jarvis para Windows")
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "stop", "diagnostics", "configure-fish", "configure-openai"],
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    root = (args.data_dir or data_directory()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    instance = root / "instance.json"
    if args.command.startswith("configure-"):
        from getpass import getpass
        from .providers import credential

        provider = args.command.removeprefix("configure-")
        credential(provider, getpass("Chave API (entrada oculta; guardada apenas no Windows): "))
        print("Credencial guardada. O modo online só é ativado ao autorizar os custos nas definições.")
        return
    if args.command != "start":
        control(args.command, instance)
        return
    # OS lock prevents a second audio owner, including launches using another port.
    lock = (root / "instance.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        print("O Jarvis já está aberto. Use PARAR_JARVIS.bat para o terminar.")
        return
    enable_dpi()
    from .app import create_app
    import uvicorn

    token = secrets.token_urlsafe(32)
    app = create_app(root, token)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)
    )
    app.state.shutdown_callback = lambda: setattr(server, "should_exit", True)
    atomic_text(instance, json.dumps({"pid": os.getpid(), "port": args.port, "token": token}))
    if os.name != "nt":
        instance.chmod(0o600)
    try:
        if args.headless:
            print("Jarvis: serviço local iniciado. Interface desktop desativada neste arranque.")
            server.run()
        else:
            import webview

            thread = threading.Thread(target=server.run, name="jarvis-service", daemon=True)
            thread.start()
            for _ in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError("O serviço não conseguiu arrancar; execute DIAGNOSTICO.bat.")
                time.sleep(0.05)
            if not server.started:
                raise RuntimeError("O serviço demorou demasiado tempo a arrancar.")
            url = f"http://127.0.0.1:{args.port}/#" + token

            class Bridge:
                def __init__(self):
                    self.window = None
                    self.panel = None

                def compact(self, enabled):
                    self.window.resize(470 if enabled else 1280, 780 if enabled else 840)
                    self.window.on_top = bool(enabled)

                def auxiliary(self):
                    if self.panel:
                        self.panel.show()
                        return
                    self.panel = webview.create_window(
                        "Jarvis · Painel auxiliar",
                        url,
                        width=500,
                        height=780,
                        min_size=(420, 600),
                        background_color="#080d14",
                        focus=False,
                    )
                    self.panel.events.loaded += lambda: self.panel.evaluate_js(
                        "document.body.classList.add('compact')"
                    )

            bridge = Bridge()
            bridge.window = webview.create_window(
                "J A R V I S",
                url,
                width=1280,
                height=840,
                min_size=(420, 600),
                background_color="#080d14",
                js_api=bridge,
            )
            webview.start(gui="edgechromium" if os.name == "nt" else None, debug=False)
            server.should_exit = True
            thread.join(timeout=8)
    finally:
        instance.unlink(missing_ok=True)
        lock.close()


def control(command, instance):
    import http.cookiejar

    if not instance.exists():
        print("O Jarvis não está em execução.")
        return
    data = json.loads(instance.read_text())
    base = f"http://127.0.0.1:{data['port']}"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request(
        base + "/api/session",
        json.dumps({"token": data["token"]}).encode(),
        {"Content-Type": "application/json"},
    )
    opener.open(request, timeout=3).close()
    path = "/api/shutdown" if command == "stop" else "/api/diagnostics"
    req = urllib.request.Request(base + path, method="POST" if command == "stop" else "GET")
    with opener.open(req, timeout=5) as response:
        print(json.dumps(json.load(response), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
