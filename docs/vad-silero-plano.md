# Silero e interrupção por voz

Escopo: detector optativo no widget, sem alterar energia/interrupção desligada por padrão.

1. Testar configuração e formulário Voz; adicionar `vad` e `interromper_ao_falar` com aviso de reinício.
2. Testar adaptador com microfone/contexto e Silero falsos; carregar modelo v5 e runtime localmente, manter energia até carregar e retornar à energia se falhar.
3. Testar controle da captura, fala sustentada e filtro de eco por correlação/energia da saída; bloquear jogo, reunião, mudo e PTT.
4. Integrar no laço existente preservando pré-roll, teto e fluxo de chamada/conversa aberta; invalidar finalizadores de ciclos interrompidos.
5. Completar cancelamento próprio durante admissão/reconciliação/reprodução e provar resposta OpenJarvis tardia ignorada.
6. Rodar testes, tipos, build, Rust e vazamento; revisar diff, rebase origin/main, integrar sem sobrescrever alterações concorrentes, registrar evidências e remover worktree após merge.

Dependências fixadas: vad-web 0.0.31 (publicada em 2026-09-12, ISC) e onnxruntime-web 1.22.0 (MIT). Silero v5 é MIT. Implementação original, sem portar código do Open-LLM-VTuber.
