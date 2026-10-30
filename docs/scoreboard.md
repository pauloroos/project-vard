# Scoreboard — Frente 3

## Job: 20261030-0222-frente-3-interface-interromper-dispositi

| Peça | Título | Tentativas | Status Final | Nota |
|------|--------|------------|--------------|------|
| 1 | Handler config-salva aplica microfone/saída e avisa em falha | 11 | ok | `aplicarDispositivosSalvos` + teste de regressão |
| 2 | Interromper cancela transcrição, resposta e fala | 6 | ok | AbortController em botão/atalho/push-to-talk |
| 3 | Etapas visíveis e erros no HUD/núcleo | 13 | ok | Estados renderizados; erro nunca fica preso |
| 4 | Fala frase por frase via streaming | 5 | ok | `receberEFalarEmStreaming` + reconciliação |

**Total de tentativas:** 35  
**PR:** #11  
**Branch:** `maestro/03-interface-d4d6c2ab`  
**Testes:** 1111 passed, 4 skipped (111 arquivos)  
**Prova real Windows:** pendente (roteiro de aceite no PR)