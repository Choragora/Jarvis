"""Optional metered TTS. Credentials stay in Windows Credential Manager, outside the renderer."""

from __future__ import annotations

import platform


SERVICE = "JarvisPT"


def credential(provider: str, value: str | None = None):
    if platform.system() != "Windows":
        raise RuntimeError("Configure credenciais no Gestor de Credenciais do seu Windows local.")
    from keyring.backends.Windows import WinVaultKeyring

    vault = WinVaultKeyring()
    if value is None:
        return vault.get_password(SERVICE, provider)
    if not value.strip():
        raise ValueError("Credencial vazia.")
    vault.set_password(SERVICE, provider, value.strip())
    return None


def status(provider: str):
    try:
        return {"configured": bool(credential(provider)), "provider": provider}
    except RuntimeError:
        return {
            "configured": False,
            "provider": provider,
            "reason": "Credencial configurável apenas no Windows.",
        }


def fish_catalog():
    from fishaudio import FishAudio

    key = credential("fish")
    if not key:
        raise PermissionError(
            "Execute CONFIGURAR_FISH.bat para guardar a chave no Windows; nunca a cole na conversa."
        )
    with FishAudio(api_key=key, timeout=10) as client:
        credits = client.account.get_credits(check_free_credit=True)
        voices = client.voices.list(page_size=30, language="pt")
    return {
        "credits": credits.model_dump(mode="json"),
        "voices": [{"id": v.id, "name": v.title} for v in voices.items],
        "model_access": "Só uma síntese real verifica acesso ao modelo. Créditos gratuitos não comprovam acesso gratuito a todos os modelos.",
    }


def pcm_chunks(provider, settings, text):
    """Yield signed little-endian 16-bit mono PCM from the documented streaming endpoints."""
    if not settings.online_costs_accepted:
        raise PermissionError("Confirme os custos do fornecedor antes de ativar síntese online.")
    key = credential(provider)
    if not key:
        raise PermissionError("Credencial não configurada no Windows.")
    if provider == "fish":
        from fishaudio import FishAudio, TTSConfig

        if not settings.fish_model or not settings.fish_voice:
            raise ValueError("Escolha explicitamente o modelo e a voz Fish Audio.")
        client = FishAudio(api_key=key, timeout=5)
        stream = client.tts.stream(
            text=text,
            model=settings.fish_model,
            reference_id=settings.fish_voice,
            config=TTSConfig(format="pcm", sample_rate=24000, latency="balanced"),
        )
        try:
            yield from stream
        finally:
            # SDK AudioStream wraps a generator; close its underlying iterator when supported.
            close = getattr(iter(stream), "close", None)
            if close:
                close()
            client.close()
    elif provider == "openai":
        import httpx

        if not settings.openai_audio_model or not settings.openai_voice:
            raise ValueError(
                "Indique um modelo de síntese e uma voz oficialmente disponíveis na sua conta API."
            )
        with httpx.Client(timeout=httpx.Timeout(20, read=5)) as client:
            with client.stream(
                "POST",
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": settings.openai_audio_model,
                    "voice": settings.openai_voice,
                    "input": text,
                    "response_format": "pcm",
                },
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Síntese OpenAI recusada (HTTP {response.status_code}); sem repetição automática."
                    )
                yield from response.iter_bytes(2048)
    else:
        raise ValueError("Fornecedor de áudio desconhecido.")
