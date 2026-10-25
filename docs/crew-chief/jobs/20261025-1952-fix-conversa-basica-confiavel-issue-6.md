# fix: conversa básica confiável (issue #6)

- **Id:** `20261025-1952-fix-conversa-basica-confiavel-issue-6`
- **Created:** 2026-10-25T19:52:36.479330
- **Distributed:** yes
- **Issue:** pauloroos/project-vard#6

## Request

JOB vard-6 — Project Vard, GitHub issue #6 "Conversa básica confiável antes de novas funcionalidades (revisão da 0.9.8)".
Scope: the 7 bugs and the 10 plan items of issue #6, in the issue's priority order (Alta bugs and plan items 1-5 first),
following docs/revisoes/2026-10-24-revisao-codex-0.9.8.md, AGENTS.md and CONTRIBUTING.md. Items that need the Windows
desktop (Tauri runtime, GPU, microphone, audio devices) are implemented as far as the code allows, the logic is tested,
and they are listed in the PR as needing the owner's check on Windows. One branch fix/issue-6-conversa-basica, one PR.

Issue body:
Revisão completa: [docs/revisoes/2026-10-24-revisao-codex-0.9.8.md](../blob/main/docs/revisoes/2026-10-24-revisao-codex-0.9.8.md)

Diagnóstico: o Vard virou três produtos (interface do OpenJarvis, assistente próprio e central de automação) antes de a conversa básica ficar confiável.

## Bugs
- [ ] **Alta:** widget preso em "pensando". Uma falha antes do laço ou durante a queda do SSE não gera evento terminal (`nucleo/vard/cerebro/pedidos.py:245`). Conferido.
- [ ] **Alta:** o histórico perde a pergunta do usuário; só a resposta é gravada (`nucleo/vard/cerebro/laco.py:278`). Conferido.
- [ ] **Alta:** `recarregar` não volta a subir o serviço, porque `parar()` encerra a thread e `repetir()` não a recria (`src-tauri/src/servicos.rs`).
- [ ] **Alta:** o modo jogo declara sucesso sem liberar a GPU. Ele procura a config na pasta errada e o `/modo` fica em laço entre Rust e Python (`src-tauri/src/ciclo.rs`).
- [ ] **Alta:** o contrato das ferramentas está quebrado. Na conversão Anthropic o nome vai vazio, e nos compatíveis os argumentos podem virar `{}` (`nucleo/vard/cerebro/provedores.py`).
- [ ] **Média:** Interromper não cancela a transcrição em andamento (`src/main.ts`).
- [ ] **Média:** trocar o microfone ou a saída nas configurações não muda o widget e nada avisa que precisa reiniciar (`src/ui/aba-voz.ts`).

## Plano (prioridade)
1. [ ] Todo pedido termina com resposta ou erro visível; sem espera infinita.
2. [ ] Corrigir o histórico.
3. [ ] Interromper cancela STT, resposta e fala.
4. [ ] Microfone e saída obedecem à configuração.
5. [ ] Serviços se recuperam sem fechar o app.
6. [ ] Mostrar as etapas (transcrevendo, pensando, falando) e os erros.
7. [ ] Falar frase por frase, sem esperar a resposta inteira.
8. [ ] Corrigir o modo jogo ou esconder a promessa até funcionar.
9. [ ] Tirar as ferramentas do caminho básico até corrigir os contratos.
10. [ ] Congelar as periféricas (Telegram, reunião, CLIs, pesquisa, resumo da manhã) e reescrever o README com uma configuração mínima.

## Teste de aceite de cada versão
Abrir, conversar 10 turnos, interromper, trocar o dispositivo, provocar uma falha e continuar.

## Decision

- Distributed: yes
- Reason: 

## Pieces

_No pieces._

## Commit message

```
fix: conversa básica confiável (issue #6)
```

## Issue comment

- no pieces

Record: docs/crew-chief/jobs/20261025-1952-fix-conversa-basica-confiavel-issue-6.md
