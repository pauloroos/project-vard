# Ponte do Vard (opcional)

O HUD conversa só com o OpenJarvis. Existe, porém, uma segunda peça opcional: a **ponte do Vard**, um servidor local em
`http://127.0.0.1:4700` (`ponte_url` no `hud.config.json`). Ela é o setup privado do autor
(o repositório privado `rdl-vard`; não é um produto nem tem suporte). O HUD detecta a ponte sozinho:
sem ela, nada quebra, só faltam as três coisas abaixo.

## O que a ponte acrescenta

- **Olhos na tela.** Botão Tela, ou dizer "Vard, o que você está vendo": o HUD captura o monitor onde a janela está
  (um indicador vermelho acende por 1 s antes), manda o quadro JPEG para a ponte (`POST /see`) e fala a resposta do modelo
  de visão. Sem a ponte, a frase vira "Isso eu só faço com a minha ponte ligada."
- **Modo jogo.** "Vard, modo jogo" e confirmar com "sim" (só "sim" ou "confirmo", sozinhos): a ponte descarrega o modelo e
  derruba o OpenJarvis para liberar a GPU (`POST /modo`). O HUD fica cinza, escrito MODO JOGO, e fecha o microfone.
  Ele sonda `GET /status` a cada 10 s e, quando o modo volta a `ligado`, reabre o microfone sozinho e diz "Voltei."
- **Eventos.** `GET /events` (SSE, com ping a cada 15 s) é o canal por onde a ponte vai avisar o HUD de coisas que
  acontecem fora da conversa. O cliente (`Ponte.eventos`) existe, mas o HUD ainda não o usa: reconexão e consumo dos eventos não estão implementados.

## Como o HUD sabe que a ponte existe

A cada 10 s ele pede `GET /status` (timeout de 5 s). Resposta boa: o botão Tela aparece e o modo jogo fica disponível.
Sem resposta: o botão some e os pedidos de tela ou de modo jogo recebem a fala de "ponte desligada". A sondagem nunca
trava a conversa.

## Contrato da ponte

| Rota | Entrada | Saída |
| --- | --- | --- |
| `GET /status` | nada | `{openjarvis, lmstudio, modelo, modo}`; `modo` é `ligado`, `ligando`, `jogo`, `parado` ou `erro` (com `detalhe`) |
| `POST /see` | multipart: `imagem` (image/jpeg) e `pergunta` | `{resposta, nuvem}`; em falha, 503 `{erro: codigo}` |
| `POST /modo` | `{modo: "jogo"}` (também `voltar`, `parar`, `recarregar`) | `{ok, pid}` |
| `GET /events` | nada | fluxo `text/event-stream` |

A ponte só aceita pedidos sem `Origin` ou vindos de origens conhecidas. O webview do HUD envia `http://tauri.localhost`
(app instalado) ou `http://localhost:1420` (`tauri dev`); essas duas precisam estar na lista de origens da ponte, com CORS.

## Ter a sua

Quem quiser outro backend só precisa servir essas quatro rotas em `ponte_url`. O resto do HUD não depende delas.
Para testar sem nada instalado: `PONTE=4700 npm run harness` sobe o OpenJarvis falso e uma ponte falsa juntos.
