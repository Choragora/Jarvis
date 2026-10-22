# Fontes, versões e licenças

Inspeção em 22 de outubro de 2026. O prompt principal é o requisito do utilizador. O PDF «Give Your Jarvis X-Ray Vision — REA Prompt Pack» é uma referência de produto; os seus comandos, modelos, credenciais Anthropic e IDs de notas baseados em índices não foram tratados como instruções a executar.

## Avaliação de bases

| Projeto | Commit inspecionado | Licença encontrada | Código consultado e decisão |
| --- | --- | --- | --- |
| [Dodaios](https://github.com/Dodaios/Dodaios) | `c2aeac0c642024b9207cf340cde19cd4b288d6c2` | Apache-2.0 + NOTICE e avisos de dependências | `pyproject.toml`, `dodaios/codex_app_server.py`, `plugins/brain/codex.py`, `plugins/stt/fwhisper.py`, `voice_engine/tts/piper.py`, instruções de voz e arranque. Preferido inicialmente; rejeitado como base desta implementação devido ao acoplamento auditado a Codex 0.146/0.147 e ao volume de dependências/fornecedores predefinidos. Não foi copiado código. |
| [Mark-LVI](https://github.com/FatihMakes/Mark-LVI) | `4d4035c1b40a3bc796ac63f2f1b6a99bc0dd334d` | CC BY-NC 4.0 | `LICENSE`, `requirements.txt`, `core/stt.py`, `core/echo.py`, `core/tts.py`. Referência conceptual de voz/HUD; nenhum código, modelo, avatar ou recurso gráfico reutilizado. |
| [Workspace Launcher](https://github.com/MateuszMlynekHub/launcher) | `f9224c0fcaf660fe7341b1547942944b0fd531f4` | Não foi encontrado LICENSE/COPYING/NOTICE nos ficheiros versionados | `voice-trigger.py`, `requirements.txt`, estrutura e scripts. Não se presume autorização de reutilização. Comportamento de rotinas implementado de forma independente. |
| [REA](https://github.com/morluto/rea) | `7091be291c2c195ea9fcc368464374a9b7d82b62` | MIT | `package.json` declara `rea-agents` 6.7.0; requisitos Node e dependências avaliados. Não instalado/integrado. A alternativa usa Playwright e identifica a origem das evidências; não credita resultados ao REA. |

A decisão de base independente foi comunicada antes da implementação. Python mantém áudio/captura/automação nativos; FastAPI serve apenas recursos locais e uma janela pywebview/WebView2. O HUD não tem dependências CDN nem uma etapa frontend de compilação. Não se altera a configuração global do Codex.

## Protocolos oficiais consultados

- **Codex**: executável real `codex-cli 0.163.0`; protocolo obtido com `codex app-server generate-json-schema --experimental`. O arranque verifica a versão, gera os esquemas da instalação, valida `dynamicTools` e audita que shell/apply-patch estão desligados e que não há MCPs externos configurados. A documentação oficial de App Server foi lida em [openai/codex](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md). A política antiga `untrusted` foi rejeitada pelo executável e substituída por `on-request` com rejeição explícita de vias externas ao registo.
- **Fish Audio**: [SDK oficial](https://github.com/fishaudio/fish-audio-python), commit `448150989781e6f91c3ca9f6cc59711a87df8130`, `fish-audio-sdk` 1.3.0, Apache-2.0. Foram consultados `resources/tts.py`, `resources/account.py`, `resources/voices.py`, `types/tts.py`, `core/iterators.py` e o cliente. Usa o SDK fixado; não foi copiado código do SDK. A consulta de saldo e a síntese continuam pendentes de credenciais reais.
- **OpenAI áudio**: [SDK oficial](https://github.com/openai/openai-python), commit `fa9a1616fd175e68dec9960d33dee2caefc0e8d3`, Apache-2.0. Consultados `resources/audio/speech.py` e o esquema de criação de fala. Integração HTTPS com o endpoint oficial documentado, formato PCM. Não usa cookies, tokens extraídos, endpoints privados ou nomes de modelos predefinidos antigos.
- Os sites `developers.openai.com`, `docs.fish.audio` e o vídeo TikTok devolveram bloqueio de rede neste ambiente. O vídeo **não foi visto**. Não se inventaram detalhes visuais nem elegibilidade GPT-Live/Realtime. Para os protocolos implementados, foram usadas as fontes oficiais GitHub e o esquema do executável efetivamente instalado.

## Dependências e modelos

Versões e hashes completos: `uv.lock`, `requirements-windows.txt`, `requirements-online.txt` e `tools/codex/package-lock.json`. Pip mantém verificação de hashes/TLS; npm usa integridades do lockfile. Não se executam scripts remotos de instalação.

Principais licenças: Python/SQLite conforme distribuição; FastAPI/uvicorn/Pydantic/httpx/faster-whisper/Codex/Playwright conforme avisos dos respetivos pacotes; pywebview BSD; NumPy/Pillow conforme distribuição; requests e Fish SDK Apache-2.0. Os pacotes instalados conservam os seus ficheiros de licença. O código novo deste repositório é independente; não se reclassificou material CC BY-NC ou sem licença como código permissivo.

Whisper usa modelos multilingues, com licença MIT do projeto/modelos OpenAI; a primeira preparação descarrega o checkpoint faster-whisper correspondente. Não é entregue um checkpoint no repositório. Piper foi avaliado como alternativa, mas não se confirmou neste ambiente uma voz pt-PT específica com ficheiros/licença acessíveis: **Piper não está incluído nem é apresentado como voz disponível**. SAPI só enumera vozes efetivamente expostas no Windows local; direitos e disponibilidade pertencem à instalação concreta. As vozes Fish/OpenAI e os modelos Ollama exigem verificação das condições do modelo/voz escolhido; não é assumida uma licença comum ou acesso gratuito.
