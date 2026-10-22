"""SAPI metadata selection; no assumption that OneCore/natural voices are exposed to SAPI."""

import locale


def voice_locales(language: str) -> list[str]:
    result = []
    for item in language.split(";"):
        try:
            code = locale.windows_locale.get(int(item.strip(), 16))
        except ValueError:
            code = None
        if code:
            result.append(code.replace("_", "-"))
    return result


def select_sapi_voice(voices: list[dict], requested: str | None) -> dict:
    if requested:
        selected = next((v for v in voices if v["id"] == requested), None)
        if selected:
            return selected
        raise ValueError(
            "A voz selecionada já não está disponível. Atualize a lista e escolha uma voz instalada."
        )
    selected = next((v for v in voices if "pt-PT" in voice_locales(v.get("language", ""))), None)
    if selected:
        return selected
    if not voices:
        raise ValueError(
            "O Windows não expõe nenhuma voz SAPI. Adicione uma voz nas definições de Voz do Windows e reinicie o Jarvis."
        )
    raise ValueError(
        "Não há voz SAPI pt-PT acessível. Escolha explicitamente uma das vozes listadas para testar o som. Para português de Portugal, adicione uma voz nas definições de Voz do Windows e confirme que aparece nesta lista."
    )
