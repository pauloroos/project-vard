# Telegram do Vard

O núcleo tem um bot próprio do Telegram (long polling direto na Bot API), desligado por padrão.
Ele sobe com o núcleo e não depende do OpenJarvis.

## Onde fica a configuração

| O quê | Onde |
| --- | --- |
| Token do bot | Cofre do Windows, alvo `vard:canal:telegram` (o app grava pela tela; o núcleo grava na migração) |
| Ligado, chats permitidos | `telegram.toml` na pasta de configuração (`VARD_CONFIG` ou `%LOCALAPPDATA%\rdl-vard\config`) |

Um `token` antigo no `telegram.toml` ainda é lido quando o cofre está vazio. O token nunca aparece
em resposta do núcleo, ferramenta do assistente, log ou erro: a tela e o assistente veem só se ele existe.

O poller sobe quando `habilitado = true`, há token e pelo menos um chat permitido. A tela (aba Sistema)
e o assistente avisam o núcleo depois de gravar (`POST /telegram/sincronizar`), e o poller liga,
religa ou desliga na hora, sem reiniciar.

## Trazer do OpenJarvis

Numa instalação com OpenJarvis, o Telegram fica em `%OPENJARVIS_HOME%\config.toml`:
`[channel] enabled` e `[channel.telegram] bot_token`, `allowed_chat_ids` (texto separado por vírgula)
e `parse_mode`. A casa do OpenJarvis vem de `OPENJARVIS_HOME`, depois de `openjarvis_home` do
`instalacao.json` e, por último, de `~/.openjarvis`. Esse bloco é gerado por `aplicar-config.ps1`
a partir de `segredos.toml` (`[telegram] token` e `chat_id`), que serve de segunda fonte.

A aba Sistema mostra **Trazer do OpenJarvis** quando há Telegram para trazer e o do Vard está vazio.
O assistente tem `trazer_telegram_do_openjarvis`. Os dois chamam `POST /telegram/trazer_openjarvis`,
e o núcleo faz a cópia no próprio processo:

- o token vai direto para o cofre, que confirma a leitura antes de seguir; falha no cofre não grava nada;
- `allowed_chat_ids` vira `chats_permitidos` e `enabled` vira `habilitado`; outras opções do
  `telegram.toml` ficam, e o `token` antigo em texto sai;
- a origem só é lida: nada muda no OpenJarvis nem no `segredos.toml`;
- repetir não muda nada (`mudou: false`);
- um Telegram já configurado no Vard só é substituído com `substituir: true`, depois de confirmação
  na tela ou no assistente.

`parse_mode` não é copiado, porque o Vard envia texto puro.

## OpenJarvis desligado

Dois programas no mesmo bot brigam pelo `getUpdates` (HTTP 409) e cada mensagem vai para um só.
Com o Telegram no Vard, mantenha o OpenJarvis desligado. Ele já não sobe quando não é quem responde
e "Manter o OpenJarvis ligado" está desmarcado. A migração avisa quando ele ainda está marcado para
subir. Se o poller do Vard receber 409, ele espera 30 s antes de tentar de novo.
