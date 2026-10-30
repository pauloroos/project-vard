# Changelog

## [Unreleased] - 2026-10-30

### Frente 3 — interface: interromper, dispositivos, etapas e fala por frase (PR #11)

- **Interromper**: botão, atalho e push-to-talk cancelam transcrição, resposta e fala via `AbortController`; texto tardio é descartado; SSE/ponte com erro cancelado volta ao repouso sem mensagem de erro.
- **Dispositivos**: handler `config-salva` aplica microfone/saída ao vivo e avisa "Reinicie para aplicar" quando `setSinkId` falha ou o microfone está aberto; preferência revalidada em `devicechange`.
- **Etapas visíveis**: estados transcrevendo/pensando/falando renderizados no HUD e no núcleo; todo erro, queda do SSE ou falha da ponte vira estado de erro visível.
- **Fala frase por frase**: `receberEFalarEmStreaming` sintetiza e toca cada frase assim que pronta, sem esperar a resposta inteira; reconciliação inicial captura texto produzido antes do SSE.
- **Tratamento de cancelamento**: snapshot com `estado: "cancelado"` ou `erro: "cancelado"` retorna ao repouso sem invocar streaming nem lançar exceção.

Refs #6