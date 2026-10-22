# Relatório de validação

Data: 22 de outubro de 2026. Ambiente: Linux x86_64, Python 3.12.14, 5 processadores lógicos, aproximadamente 33,3 GiB de RAM, sem GPU CUDA detetada. Este não é o equipamento Windows do utilizador.

## Resultados efetivamente obtidos

- **40 testes automáticos passaram** no Linux. Duas verificações adicionais da deteção Python no instalador são ignoradas neste sistema por exigirem `cmd.exe` real; ficam disponíveis no workflow Windows. Incluem-se na suite SQLite/FTS/persistência, documentos Word reabertos, movimentação com verificação, âmbito de caminhos/symlinks, tarefas, edição de rotinas/DST/deduplicação, redação em imagens de teste, capturas antigas, autenticação/origem, WebSocket, paragem, concorrência local, protocolo e encaminhamento da pré-visualização de voz.
- **Codex real**: instalaram-se os artefactos oficiais npm 0.163.0 com o lockfile. `initialize`, `config/read` e `account/read` funcionaram no processo persistente; o perfil dedicado foi corretamente reportado sem login. `thread/start` aceitou as **24 ferramentas estruturadas**. A configuração efetiva confirmou shell/apply-patch desligados e ausência de MCPs externos. Não foi feita inferência autenticada nem copiada uma credencial do ambiente.
- **Sete percursos no browser real passaram**, com Chromium e serviço HTTP/WebSocket reais: bootstrap autenticado; conversa que grava uma nota; pesquisa FTS e leitor de fontes; criação/pausa/apagamento de rotina; guardar definições; parar/retomar; navegação e diagnóstico em 480 px sem transbordo horizontal. Nenhum erro JavaScript observado. Evidência: `browser-check.json` e `interface-verified.png`.
- **Ruff** passou e o JavaScript foi verificado com `node --check`.
- A distribuição fonte e o wheel Python foram construídos. Isto **não é um executável Windows** e não constitui teste do WebView2.
- O motor faster-whisper importa e `ctranslate2` reportou 0 dispositivos CUDA. O modelo não foi descarregado sem hardware para o validar. `sounddevice` está instalado, mas a biblioteca nativa PortAudio não existe nesta máquina Linux; a API apresenta esse diagnóstico.

Um aviso de descontinuação da dependência Starlette/AnyIO aparece no runner de testes. Não causou falhas e não foi ocultado nem convertido num passe artificial.

## Medições

`local-text-benchmark.json` contém **30 turnos reais de comandos locais em texto**, alternando gravação SQLite e consulta. Regista mediana, p95, falhas, hardware e o primeiro turno frio. Estes números medem apenas o percurso local indicado no ficheiro; **não medem reconhecimento, inferência Codex, TTS, áudio audível ou latência de voz**.

Não há medições acústicas inventadas. A página Primeiro arranque fornece 30 casos para observações no Windows; o export identifica os resultados declarados pelo utilizador e inclui o diagnóstico. Registar «funcionou» não se transforma automaticamente numa medição acústica. A mediana/p95 de voz, ruído, pausas, eco e interrupção continua pendente até existir evidência no equipamento real.

## Simulações e testes de lógica

Os testes de falha de quota, chamadas duplicadas, resposta tardia e concorrência usam fixtures de protocolo explicitamente identificadas. Verificam que não há repetição ou execução duplicada e que comandos locais não esperam pela inferência. **Não comprovam login, qualidade de um modelo ou acesso de uma conta**. Os testes de redação usam imagens sintéticas para verificar pixels e transformação de coordenadas; não comprovam captura de monitores físicos.

## Bloqueios e verificações não executadas

- Windows, SAPI pt-PT, microfone, colunas/auscultadores, UI Automation, dois monitores, DPI misto, foco e hotplug: não estão disponíveis nesta máquina. A interface mantém os testes locais pendentes.
- Login concluído/cancelado/expirado, limites reais do plano, catálogo com acesso confirmado e compreensão de imagens: requerem a conta ChatGPT do utilizador no perfil local. O arranque do protocolo não equivale a uma resposta do modelo.
- Fish/OpenAI: não há credenciais nem autorização de faturação configuradas; não foram efetuados pedidos pagos ou testes online de voz. Não foi comprovada elegibilidade gratuita Fish.
- O leitor/inspector público foi tentado contra `https://github.com/openai/codex`, mas a validação DNS direta foi bloqueada por `Temporary failure in name resolution`. O código não suprimiu a validação de destinos para contornar o problema. A descarga Chromium do Playwright também foi recusada pela allowlist; os testes da UI usaram o Chromium já instalado. Inspeção de um site externo permanece pendente da rede apropriada.
- AEC com colunas, Realtime/GPT-Live, REA, detector wake dedicado, bandeja e as outras lacunas identificadas em `FEATURES.md` não são apresentadas como funcionalidades concluídas.

O workflow Windows foi escrito, mas **não foi executado no GitHub**. Não foi produzido um `.exe` nem instalada a aplicação no PC do utilizador. Após esta validação, o código foi enviado para a branch `main` de `Choragora/Jarvis`, com autorização explícita do utilizador; esse envio não constitui um teste no Windows.

## Correção do primeiro arranque

O utilizador observou que `INSTALAR.bat` parava ao não encontrar `py -3.12`. A deteção anterior dependia exclusivamente do launcher e não distinguia a sua ausência da ausência do intérprete. O instalador atualizado valida Python 3.12 x64 através de caminho explícito, ambiente existente, launcher, instalações habituais, registo e PATH. Não abre o alias-placeholder da Microsoft Store. Se necessário e com aceitação local, usa WinGet `Python.Python.3.12`, origem `winget`, âmbito `user` e arquitetura `x64`, conservando verificação de integridade pelo gestor. O manifesto oficial Microsoft consultado confirma o instalador Python.org 3.12.10 x64 e o respetivo SHA-256. A execução do instalador no PC do utilizador continua pendente; não foi simulada como um sucesso.

## Correção do teste de voz selecionada

O botão usava a voz guardada e ignorava a seleção ainda por guardar. Agora envia a seleção visível e guarda-a apenas no item de reprodução desse teste. O teste manual também funciona com leitura automática desativada. Uma voz inglesa explicitamente escolhida é aceite para testar o som; a escolha automática continua a exigir o identificador de idioma exato pt-PT. Uma seleção antiga indisponível dá erro claro, sem substituição silenciosa. O teste não ativa um fornecedor online ainda por guardar e respeita a paragem de emergência.

Nove testes adicionais verificam metadados sintéticos, fila real de reprodução e API, com o trabalhador de áudio desativado no teste da fila. Uma verificação Chromium confirmou o envio da seleção não guardada e a preservação das definições, sem erros JavaScript. Apenas o catálogo GET foi substituído por metadados sintéticos; o endpoint real respondeu que SAPI estava indisponível neste Linux. Evidência: `voice-preview-ui-check.json`. Estes resultados não comprovam reprodução audível, instalação de uma voz pt-PT ou compatibilidade SAPI no Windows.
