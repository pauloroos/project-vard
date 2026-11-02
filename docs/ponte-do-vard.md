# Ponte do Vard (opcional)

O HUD conversa só com o OpenJarvis. Existe, porém, uma segunda peça opcional: a **ponte do Vard**, um servidor local em
`http://127.0.0.1:4700` (`ponte_url` no `hud.config.json`). Ela é o setup privado do autor
(o repositório privado `rdl-vard`; não é um produto nem tem suporte). O HUD detecta a ponte sozinho:
sem ela, os recursos dependentes da ponte não ficam disponíveis.

## O que a ponte acrescenta

- **Olhos na tela.** Botão Tela, ou dizer "Vard, o que você está vendo": o HUD captura o monitor onde a janela está
  (um indicador vermelho acende por 1 s antes), manda o quadro JPEG para a ponte (`POST /see`) e fala a resposta do modelo
  de visão. Sem a ponte, a frase vira "Isso eu só faço com a minha ponte ligada."
- **Modo jogo.** Está indisponível nesta versão: `POST /modo` com `jogo` retorna 503, sem descarregar modelos ou parar serviços.
- **Eventos.** `GET /events` (SSE, com ping a cada 15 s) é o canal por onde a ponte vai avisar o HUD de coisas que
  acontecem fora da conversa. O cliente (`Ponte.eventos`) existe, mas o HUD ainda não o usa: reconexão e consumo dos eventos não estão implementados.

## Como o HUD sabe que a ponte existe

A cada 10 s ele pede `GET /status` (timeout de 5 s). Com resposta boa, o botão Tela aparece; sem resposta, ele some e os
pedidos de tela recebem a fala de "ponte desligada". A sondagem nunca trava a conversa. O modo jogo permanece indisponível.

## Contrato da ponte

| Rota | Entrada | Saída |
| --- | --- | --- |
| `GET /status` | nada | `{openjarvis, lmstudio, modelo, modo}`; `modo` é `ligado`, `ligando`, `jogo`, `parado` ou `erro` (com `detalhe`) |
| `POST /see` | multipart: `imagem` (image/jpeg) e `pergunta` | `{resposta, nuvem}`; em falha, 503 `{erro: codigo}` |
| `POST /modo` | `{modo: "jogo"}` | 503 `{ok: false, erro: "modo jogo indisponível nesta versão"}` |
| `POST /modo` | `{modo: "voltar"}` | `{ok: true, mensagem: "restauração pendente para próxima versão"}`, sem disparar script |
| `POST /modo` | `{modo: "parar"}` ou `{modo: "recarregar"}` | `{ok, pid}` ou `{ok, id}`; falhas retornam 503 `{erro: codigo}` |
| `GET /events` | nada | fluxo `text/event-stream` |

A ponte só aceita pedidos sem `Origin` ou vindos de origens conhecidas. O webview do HUD envia `http://tauri.localhost`
(app instalado) ou `http://localhost:1420` (`tauri dev`); essas duas precisam estar na lista de origens da ponte, com CORS.

## Ter a sua

Quem quiser outro backend só precisa servir essas quatro rotas em `ponte_url`. O resto do HUD não depende delas.
Para testar sem nada instalado: `PONTE=4700 npm run harness` sobe o OpenJarvis falso e uma ponte falsa juntos.
