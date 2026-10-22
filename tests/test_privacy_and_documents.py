from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from jarvis.app import create_app
from jarvis.desktop import redact_image
from jarvis.runtime import Runtime


def test_redaction_with_negative_monitor_origin():
    image = Image.new("RGB", (100, 80), "white")
    monitor = {"left": -100, "top": -20}
    redact_image(image, monitor, [(-90, -10, -70, 10), (10, 10, 30, 30)])
    assert image.getpixel((10, 10)) == (0, 0, 0)
    assert image.getpixel((29, 29)) == (0, 0, 0)
    assert image.getpixel((30, 30)) == (255, 255, 255)
    assert image.getpixel((0, 0)) == (255, 255, 255)


def test_old_capture_cannot_be_viewed_after_privacy_change(tmp_path):
    import json
    from jarvis.desktop import capture_fingerprint

    app = create_app(tmp_path, "test")
    name = "12345678-1234-1234-1234-123456789abc.png"
    folder = tmp_path / "captures"
    folder.mkdir()
    Image.new("RGB", (10, 10), "white").save(folder / name)
    (folder / name).with_suffix(".json").write_text(
        json.dumps({"redaction_fingerprint": capture_fingerprint(app.state.runtime.settings)})
    )
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.post("/api/session", json={"token": "test"})
        assert c.get("/api/captures/" + name).status_code == 200
        settings = c.get("/api/settings").json()
        settings["hidden_regions"] = [[0, 0, 10, 10]]
        assert c.put("/api/settings", json=settings).status_code == 200
        assert c.get("/api/captures/" + name).status_code == 409


async def test_word_document_is_reopened_and_not_overwritten(tmp_path):
    runtime = Runtime(tmp_path)
    try:
        path = Path(runtime.settings.allowed_folders[0]) / "nota.docx"
        args = {
            "path": str(path),
            "title": "Notas em português",
            "paragraphs": ["Primeiro parágrafo.", "Uma segunda ideia."],
        }
        result = await runtime.execute("document_create", args)
        assert result["status"] == "completed"
        assert result["observed_result"]["verified"]
        assert path.is_file()
        assert (await runtime.execute("document_create", args))["status"] == "failed"
    finally:
        runtime.store.close()


async def test_move_verifies_content_and_refuses_overwrite(tmp_path):
    runtime = Runtime(tmp_path)
    try:
        root = Path(runtime.settings.allowed_folders[0])
        source, destination = root / "a.txt", root / "b.txt"
        source.write_text("conteúdo original")
        result = await runtime.execute("file_move", {"path": str(source), "destination": str(destination)})
        assert result["status"] == "completed"
        assert not source.exists() and destination.read_text() == "conteúdo original"
        source.write_text("outro conteúdo")
        assert (await runtime.execute("file_move", {"path": str(source), "destination": str(destination)}))[
            "status"
        ] == "failed"
        assert source.exists()
    finally:
        runtime.store.close()


async def test_folder_index_has_stable_ids_and_sources(tmp_path):
    runtime = Runtime(tmp_path)
    try:
        root = Path(runtime.settings.allowed_folders[0])
        source = root / "ideias.md"
        source.write_text("Uma memória com fonte verificável.")
        a = await runtime.execute("memory_import_folder", {"path": str(root)})
        source.write_text("Conteúdo corrigido.")
        b = await runtime.execute("memory_import_folder", {"path": str(root)})
        assert a["observed_result"]["imported_note_ids"] == b["observed_result"]["imported_note_ids"]
        notes = runtime.store.notes("corrigido")
        assert len(notes) == 1 and notes[0]["source"] == str(source)
    finally:
        runtime.store.close()
