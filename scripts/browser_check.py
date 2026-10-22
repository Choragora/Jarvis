"""Exercise the running UI against real local APIs; never simulate voice or monitor hardware."""

import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    instance = Path(os.environ.get("JARVIS_INSTANCE", "/workspace/scratch/jarvis-ui/instance.json"))
    data = json.loads(instance.read_text())
    base = f"http://127.0.0.1:{data['port']}"
    errors = []
    checks = []
    with sync_playwright() as p:
        options = {"headless": True}
        if os.environ.get("JARVIS_CHROMIUM"):
            options["executable_path"] = os.environ["JARVIS_CHROMIUM"]
        browser = p.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/#" + data["token"])
        expect(page.locator("#connection")).to_contain_text("Ligado ao seu PC")
        if page.locator("#resume-header").is_visible():
            page.locator("#resume-header").click()
        checks.append("authenticated bootstrap and WebSocket connection")
        page.locator("#chat-input").fill(
            "Lembra-te de que esta é uma nota descartável do teste de interface."
        )
        page.locator("#send").click()
        expect(page.locator("#messages")).to_contain_text("Guardei na memória:")
        checks.append("typed chat executes real memory tool and displays receipt")
        page.locator('.nav-item[data-view="memory"]').click()
        page.locator("#note-search").fill("descartável")
        expect(page.locator("#notes .note")).to_have_count(1)
        page.locator("#notes .note").get_by_role("button", name="Abrir", exact=True).click()
        expect(page.locator("#note-dialog")).to_be_visible()
        page.locator("#note-dialog .dialog-close").click()
        checks.append("FTS note search and source reader")
        # Use API cleanup for the exact disposable note created by this test.
        page.evaluate(
            "async () => {const ns=await (await fetch('/api/notes?q=descartável')).json(); for(const n of ns)await fetch('/api/notes/'+n.id,{method:'DELETE'});}"
        )
        page.locator('.nav-item[data-view="routines"]').click()
        page.locator('#routine-form input[name="name"]').fill("Rotina descartável do teste")
        page.locator("#routine-form .primary-button").click()
        expect(page.locator("#routines")).to_contain_text("Rotina descartável do teste")
        page.locator("#routines .note").get_by_role("button", name="Editar", exact=True).click()
        page.locator('#routine-form input[name="name"]').fill("Rotina descartável editada")
        page.locator("#routine-form .primary-button").click()
        expect(page.locator("#routines")).to_contain_text("Rotina descartável editada")
        page.locator("#routines .note").get_by_role("button", name="Pausar", exact=True).click()
        expect(page.locator("#routines")).to_contain_text("Em pausa")
        page.locator("#routines .note").get_by_role("button", name="Apagar", exact=True).click()
        checks.append("persistent routine creation, editing, pause and deletion")
        page.locator('.nav-item[data-view="settings"]').click()
        expect(page.locator("#tts-provider")).to_have_value("sapi")
        page.locator("#settings-form .settings-save button").click()
        expect(page.locator("#saved-status")).to_contain_text("Guardado")
        checks.append("real settings form, no paid profile enabled")
        page.locator("#stop").click()
        expect(page.locator("#resume-header")).to_be_visible()
        page.locator("#resume-header").click()
        page.locator('.nav-item[data-view="conversation"]').click()
        expect(page.locator("#resume")).to_be_hidden()
        checks.append("emergency stop and explicit resume")
        page.set_viewport_size({"width": 480, "height": 820})
        page.locator("#menu").click()
        page.locator('.nav-item[data-view="diagnostics"]').click()
        expect(page.locator("#diagnostics")).to_contain_text("platform")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks.append("480 px navigation and diagnostics, no horizontal overflow")
        page.set_viewport_size({"width": 1440, "height": 1050})
        page.locator('.nav-item[data-view="conversation"]').click()
        Path("docs").mkdir(exist_ok=True)
        page.screenshot(path="docs/interface-verified.png", full_page=True)
        browser.close()
    assert not errors, errors
    report = {
        "passed": checks,
        "javascript_errors": errors,
        "method": "Real Chromium + running local server; Windows desktop, audio and authenticated Codex inference not tested.",
    }
    Path("docs/browser-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
