"""Preview routing tests. Synthetic voice metadata never proves real Windows playback."""

import pytest
from fastapi.testclient import TestClient

from jarvis.app import create_app
from jarvis.speech import select_sapi_voice, voice_locales

ZIRA = {"id": "sapi-zira", "name": "Microsoft Zira Desktop", "language": "409"}
PT_PT = {"id": "sapi-pt-pt", "name": "Portuguese voice fixture", "language": "0816"}
PT_BR = {"id": "sapi-pt-br", "name": "Brazilian voice fixture", "language": "416"}


def test_explicit_english_voice_is_valid_without_portuguese_voice():
    assert select_sapi_voice([ZIRA], ZIRA["id"]) == ZIRA


def test_automatic_selection_prefers_exact_portugal_locale():
    assert select_sapi_voice([ZIRA, PT_BR, PT_PT], None) == PT_PT
    assert voice_locales("409;0816") == ["en-US", "pt-PT"]


def test_brazilian_voice_does_not_satisfy_automatic_portugal_selection():
    with pytest.raises(ValueError, match="pt-PT"):
        select_sapi_voice([PT_BR, ZIRA], None)


def test_language_id_must_match_instead_of_substring():
    with pytest.raises(ValueError, match="pt-PT"):
        select_sapi_voice([{"id": "other", "language": "1816"}], None)


def test_missing_explicit_voice_is_not_silently_replaced():
    with pytest.raises(ValueError, match="já não está disponível"):
        select_sapi_voice([PT_PT], "removed-voice")


def test_unsaved_preview_uses_selected_voice_without_changing_settings(tmp_path, monkeypatch):
    app = create_app(tmp_path, "preview-test")
    audio = app.state.runtime.audio
    app.state.runtime.settings.speech_enabled = False
    monkeypatch.setattr(audio, "voices", lambda: {"voices": [ZIRA]})
    # The output worker is deliberately disabled; inspect the actual queue, not a fake audible pass.
    monkeypatch.setattr(audio, "sapi_loop", lambda: None)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/session", json={"token": "preview-test"})
        response = client.post("/api/audio/test", json={"provider": "sapi", "sapi_voice": ZIRA["id"]})
        assert response.status_code == 200, response.text
        assert response.json()["voice"]["id"] == ZIRA["id"]
        assert not response.json()["verified"]
        queued = audio.speech_queue.get_nowait()
        assert queued.sapi_voice == ZIRA["id"]
        assert queued.provider == "sapi"
        assert queued.text.startswith("Hello.")
        persisted = client.get("/api/settings").json()
        assert persisted["sapi_voice"] is None
        assert persisted["speech_enabled"] is False


def test_automatic_preview_reports_missing_voice_before_queueing(tmp_path, monkeypatch):
    app = create_app(tmp_path, "preview-test")
    audio = app.state.runtime.audio
    monkeypatch.setattr(audio, "voices", lambda: {"voices": [ZIRA]})
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/session", json={"token": "preview-test"})
        result = client.post("/api/audio/test", json={"provider": "sapi", "sapi_voice": None})
        assert result.status_code == 409
        assert "pt-PT" in result.json()["detail"]
        assert audio.speech_queue.empty()


def test_voice_preview_cannot_activate_an_unsaved_paid_profile(tmp_path):
    app = create_app(tmp_path, "preview-test")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/session", json={"token": "preview-test"})
        result = client.post("/api/audio/test", json={"provider": "fish"})
        assert result.status_code == 409
        assert app.state.runtime.audio.speech_queue.empty()
        assert app.state.runtime.settings.tts_provider == "sapi"


def test_emergency_stop_blocks_voice_preview(tmp_path):
    app = create_app(tmp_path, "preview-test")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/session", json={"token": "preview-test"})
        client.post("/api/stop")
        result = client.post("/api/audio/test", json={"provider": "sapi", "sapi_voice": ZIRA["id"]})
        assert result.status_code == 409
        assert app.state.runtime.audio.speech_queue.empty()
