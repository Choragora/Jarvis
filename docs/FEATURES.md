# Matriz de funcionalidades

| Capacidade | Estado | Evidência / limitação |
| --- | --- | --- |
| Serviço local, HUD, conversa, definições e WebSocket autenticado | Implementada e verificada em Linux/Chromium | `browser-check.json`; sem erros JavaScript observados |
| Notas, FTS5, edição/apagamento/exportação, relações `[[título]]` e fontes | Implementada e verificada | SQLite real, persistência/reabertura e testes de interface; galáxia 2D, não renderização 3D |
| Ficheiros autorizados, criação sem substituição, organização e documentos Word | Implementada e verificada | Escrita/reabertura, hashes na movimentação, DOCX reaberto e conteúdo comparado |
| Importação de Markdown/texto | Implementada e verificada | IDs estáveis por caminho; só pastas autorizadas; sem indexação contínua |
| Rotinas, Lisboa/DST, deduplicação, reinício e execuções perdidas | Implementada e verificada | SQLite real e casos DST; criar/editar/pausar/apagar e selecionar várias aplicações na interface; editor de passos arbitrários ainda em falta |
| Fila e recibos de ações, concorrência limitada, paragem e cancelamento | Implementada e verificada no percurso independente de hardware | Estados concluído/falhou/cancelado/bloqueado/por verificar; não desfaz efeitos já realizados. Pausa/retoma individual e dependências arbitrárias ainda limitadas |
| Codex persistente, esquema instalado, isolamento, catálogo/login/logout/interrupção | Implementada; arranque e estado sem login verificados | Processo real 0.163.0 e auditoria de configuração. Login concluído/cancelado/expirado, quota e resposta real precisam de conta local; não se afirmou sucesso de inferência |
| Faster-whisper incremental, VAD, PTT, consolidação e wake phrase local | Implementada; teste acústico pendente | Motor importa. Sem microfone/modelo preparado neste ambiente. Wake via Whisper; detector dedicado de baixa potência ainda não incluído |
| TTS local SAPI, filas por geração e segmentos de resposta | Implementada; teste Windows pendente | Enumera apenas vozes SAPI locais; pt-PT depende da instalação. Não existe medição de áudio audível neste ambiente |
| Interrupção local e descarte de áudio antigo | Lógica implementada e parcialmente verificada | Gerações testadas. Barge-in e reconexão de dispositivos precisam de hardware; mãos livres só com auscultadores confirmados |
| Eco com colunas | Bloqueada no modo mãos livres | AEC acústico não implementado. PTT e comparação de conteúdo são alternativas limitadas, sem promessa de qualidade acústica |
| Dois monitores, DPI, origem negativa, nomes e captura | Implementada; teste Windows pendente | Conversão matemática testada; APIs Windows e disposição física não executadas aqui |
| Exclusões/redações e invalidação de capturas antigas | Implementada e verificada em testes de imagem/API | Mesma cadeia antes de guardar/visualizar/enviar; captura real depende do Windows |
| Visão do modelo e comparação de ecrãs | Integração de anexos implementada; pendente | Só com imagem explicitamente anexada e modelo com modalidade declarada; não se comprovou compreensão real |
| Abrir/focar/mover janelas, UIA, escrita verificada, clipboard, volume e media | Implementada; teste Windows pendente | Destino identificado, bloqueio exclusivo e revalidação de foco. Media sem retorno de estado fica por verificar. Sem cliques por imagem/DPI não testado |
| Navegação/leitura/pesquisa Web com fontes | Implementada; acesso externo dependente da rede | Leitor público com limites e bloqueio de endereços locais; não usa browser pessoal autenticado. Automação DOM geral e sessões de browser de trabalho ainda limitadas |
| Inspeção técnica de sites | Implementada com Playwright; teste público pendente | Contexto limpo, recolha antes da navegação, banners e relatório. REA não integrado; não se promete ver código servidor |
| Fish Audio streaming, saldo API e vozes | Opcional por configurar e testar | SDK oficial fixado, chave no Windows, custos explícitos; acesso gratuito/modelo não comprovados |
| Voz OpenAI API | Opcional por configurar e testar | Síntese streaming oficial; Realtime/GPT-Live não implementados |
| Ollama | Opcional por configurar e testar | Só modelos já instalados; sem descarga automática; percurso offline de conversa e memória |
| Janela compacta e painel auxiliar | Implementada; teste desktop Windows pendente | Mesma sessão/áudio. Bandeja, transparência e overlay não intrusivo avançado ainda não implementados |
| Scripts Windows e dependências reproduzíveis | Entregues; execução Windows pendente | Locks/hashes e workflow Windows. Não foi produzido/testado um executável ou instalador binário |
| Benchmark acústico de 30 turnos por perfil | Pendente de hardware/contas | Assistente de observações entregue. O benchmark de comandos locais em texto tem 30 turnos reais e é identificado separadamente |

Esta matriz não equivale a aceitação completa do briefing. As funcionalidades de Windows/voz não são declaradas prontas para uso diário sem a validação local; as lacunas de implementação acima permanecem explícitas.
