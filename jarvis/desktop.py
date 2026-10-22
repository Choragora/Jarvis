"""Windows-only effects; importing this module is safe on a headless Linux machine."""

from __future__ import annotations

import ctypes
import hashlib
import json
import platform
import threading
import time
from pathlib import Path

from .settings import atomic_text


def require_windows():
    if platform.system() != "Windows":
        raise RuntimeError("Esta operação requer o desktop Windows local.")


def require_interactive_desktop():
    require_windows()
    user32 = ctypes.windll.user32
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    user32.GetUserObjectInformationW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
    ]
    handle = user32.OpenInputDesktop(0, False, 1)
    if not handle:
        raise RuntimeError("Sessão bloqueada ou desktop seguro inacessível; nenhuma interação efetuada.")
    try:
        name = ctypes.create_unicode_buffer(256)
        size = ctypes.c_uint()
        if (
            not user32.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(size))
            or name.value.casefold() != "default"
        ):
            raise RuntimeError(
                "O desktop interativo não está disponível. Não é possível observar o ecrã seguro."
            )
    finally:
        user32.CloseDesktop(handle)


def capture_fingerprint(settings):
    data = json.dumps([settings.hidden_regions, settings.excluded_titles], sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def redact_image(image, monitor, regions):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    for region_left, region_top, region_right, region_bottom in regions:
        left, top = max(0, region_left - monitor["left"]), max(0, region_top - monitor["top"])
        right, bottom = (
            min(image.width, region_right - monitor["left"]),
            min(image.height, region_bottom - monitor["top"]),
        )
        if right > left and bottom > top:
            draw.rectangle((left, top, right - 1, bottom - 1), fill="black")
    return image


def enable_dpi():
    if platform.system() == "Windows":
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def local_to_desktop(monitor: dict, x: float, y: float, logical: bool = False) -> tuple[int, int]:
    scale = monitor["dpi"] / 96 if logical else 1
    return round(monitor["left"] + x * scale), round(monitor["top"] + y * scale)


def window_on_monitor(bounds, monitor):
    left, top, right, bottom = bounds
    return min(right, monitor["left"] + monitor["width"]) > max(left, monitor["left"]) and min(
        bottom, monitor["top"] + monitor["height"]
    ) > max(top, monitor["top"])


class Desktop:
    def __init__(self, root: Path, settings):
        self.root, self.settings = root, settings
        self.lock = threading.Lock()
        self.cancelled = threading.Event()

    def monitors(self) -> list[dict]:
        require_windows()
        import win32api

        result = []
        for index, (handle, _, bounds) in enumerate(win32api.EnumDisplayMonitors(), 1):
            info = win32api.GetMonitorInfo(handle)
            x, y = ctypes.c_uint(96), ctypes.c_uint(96)
            ctypes.windll.shcore.GetDpiForMonitor(int(handle), 0, ctypes.byref(x), ctypes.byref(y))
            left, top, right, bottom = bounds
            result.append(
                dict(
                    id=info["Device"],
                    name=self.settings.monitor_names.get(info["Device"], f"Ecrã {index}"),
                    number=index,
                    left=left,
                    top=top,
                    width=right - left,
                    height=bottom - top,
                    dpi=x.value,
                    work=list(info["Work"]),
                    primary=bool(info["Flags"] & 1),
                    orientation="portrait" if bottom - top > right - left else "landscape",
                )
            )
        return sorted(result, key=lambda m: m["left"])

    def windows(self) -> list[dict]:
        require_windows()
        import win32gui
        import win32process

        result = []

        def collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                title = win32gui.GetWindowText(hwnd)
                private = any(t.casefold() in title.casefold() for t in self.settings.excluded_titles)
                result.append(
                    dict(
                        id=hwnd,
                        process_id=win32process.GetWindowThreadProcessId(hwnd)[1],
                        title="[Janela excluída]" if private else title,
                        bounds=list(win32gui.GetWindowRect(hwnd)),
                        minimized=bool(win32gui.IsIconic(hwnd)),
                        foreground=hwnd == win32gui.GetForegroundWindow(),
                        excluded=private,
                    )
                )

        win32gui.EnumWindows(collect, None)
        return result

    def _target(self, hwnd: int):
        require_interactive_desktop()
        import win32gui

        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            raise RuntimeError("A janela já não está disponível.")
        title = win32gui.GetWindowText(hwnd)
        if any(t.casefold() in title.casefold() for t in self.settings.excluded_titles):
            raise PermissionError("Esta janela foi excluída.")
        if self.cancelled.is_set():
            raise InterruptedError("Paragem ativa.")
        return win32gui

    def focus(self, hwnd: int) -> dict:
        require_windows()
        with self.lock:
            gui = self._target(hwnd)
            gui.ShowWindow(hwnd, 9)
            gui.SetForegroundWindow(hwnd)
            if gui.GetForegroundWindow() != hwnd:
                raise RuntimeError("O Windows não concedeu o foco. Selecione a janela e tente novamente.")
            return {"window": hwnd, "title": gui.GetWindowText(hwnd), "foreground": True}

    def move(self, hwnd: int, monitor_id: str, zone: str) -> dict:
        require_windows()
        monitor = next((m for m in self.monitors() if m["id"] == monitor_id), None)
        if not monitor:
            raise ValueError("Monitor desligado ou desconhecido; atualize a disposição.")
        left, top, right, bottom = monitor["work"]
        if zone == "left":
            right = left + (right - left) // 2
        elif zone == "right":
            left += (right - left) // 2
        with self.lock:
            gui = self._target(hwnd)
            gui.ShowWindow(hwnd, 9)
            gui.MoveWindow(hwnd, left, top, right - left, bottom - top, True)
            observed = gui.GetWindowRect(hwnd)
            verified = max(abs(a - c) for a, c in zip(observed, (left, top, right, bottom))) <= 12
            return {
                "window": hwnd,
                "bounds": observed,
                "expected": [left, top, right, bottom],
                "verified": verified,
            }

    def type_text(self, hwnd: int, text: str) -> dict:
        require_windows()
        from pywinauto.uia_defines import IUIA
        from pywinauto.controls.uiawrapper import UIAWrapper

        # UI Automation ValuePattern targets a control directly; no blind global typing.
        with self.lock:
            gui = self._target(hwnd)
            if gui.GetForegroundWindow() != hwnd:
                raise RuntimeError(
                    "Selecione a janela de destino antes de escrever; não vou mudar o foco às cegas."
                )
            control = UIAWrapper(IUIA().iuia.GetFocusedElement())
            if control.top_level_parent().handle != hwnd or control.element_info.element.CurrentIsPassword:
                raise PermissionError("O controlo focado não é um campo de texto editável seguro.")
            value = control.iface_value
            if value.CurrentIsReadOnly:
                raise PermissionError("O controlo focado é apenas de leitura.")
            if gui.GetForegroundWindow() != hwnd or self.cancelled.is_set():
                raise InterruptedError("O foco mudou; escrita cancelada.")
            before = value.CurrentValue
            value.SetValue(before + text)
            observed = value.CurrentValue
            return {
                "window": hwnd,
                "control": control.element_info.name,
                "verified": observed == before + text,
                "characters_added": len(text),
            }

    def read_text(self, hwnd: int) -> dict:
        require_windows()
        from pywinauto import Desktop as UIA

        with self.lock:
            self._target(hwnd)
            window = UIA(backend="uia").window(handle=hwnd)
            lines = [c.window_text() for c in window.descendants()[:400] if c.window_text()]
            return {
                "window": hwnd,
                "text": "\n".join(lines)[:30000],
                "source": "Windows UI Automation",
                "trusted": False,
            }

    def capture(self, monitor_id: str) -> dict:
        require_interactive_desktop()
        if not self.settings.screen_capture:
            raise PermissionError("Ative a captura de ecrã nas permissões.")
        import mss
        from PIL import Image

        monitor = next((m for m in self.monitors() if m["id"] == monitor_id), None)
        if not monitor:
            raise ValueError("Monitor desconhecido.")
        # Redact before encoding, saving, thumbnails or provider attachment.
        with mss.mss() as capture:
            shot = capture.grab({k: monitor[k] for k in ("left", "top", "width", "height")})
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        regions = list(self.settings.hidden_regions)
        for window in self.windows():
            if window["excluded"]:
                regions.append(tuple(window["bounds"]))
        redact_image(image, monitor, regions)
        folder = self.root / "captures"
        folder.mkdir(exist_ok=True)
        import uuid

        path = folder / (str(uuid.uuid4()) + ".png")
        image.save(path)
        atomic_text(
            path.with_suffix(".json"),
            json.dumps({"redaction_fingerprint": capture_fingerprint(self.settings)}),
        )
        return {
            "path": str(path),
            "file": path.name,
            "monitor": monitor,
            "captured_at": time.time(),
            "redacted_regions": len(regions),
            "sent_to_provider": False,
        }
