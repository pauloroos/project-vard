# vard-reuniao

Modo reunião do Vard: captura o microfone ("eu") e a saída de áudio do Windows ("outros", loopback WASAPI),
segmenta por VAD (silero, CPU), transcreve pelo OpenJarvis (whisper em 127.0.0.1:8000) e grava a transcrição
em `%LOCALAPPDATA%\rdl-vard\reunioes\<AAAA-MM-DD_HHMM>\`. Só em 127.0.0.1:4720.
Projeto uv separado (Python 3.12, torch cu128) em `reuniao/.venv`. Nada carrega modelo na GPU.

- Subir: `uv run --project reuniao python -m vard_reuniao`
- Variáveis: `VARD_REUNIAO_PORT` (4720), `VARD_PONTE` (http://127.0.0.1:4700, onde saem os eventos `reuniao`).
  O módulo define `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1` e `HF_HOME` antes de importar torch.
- Log: `%LOCALAPPDATA%\rdl-vard\logs\reuniao.log` (e stdout).

## Rotas
- `GET /status` -> sessão (`ativa`, `pasta`, `inicio`, `duracao_s`, `falas`, `fila`, `dispositivos`) + `versao` + `diarizacao {pronta, motivo, modo}` + `offline` (true se o processo roda com `HF_HUB_OFFLINE=1`)
- `POST /iniciar` -> `{"ok", "pasta", "inicio"}`; 409 se já ativa; 500 `{"erro": "captura"}` se não abrir os dispositivos
- `POST /encerrar` -> `{"ok", "pasta", "duracao_s", "falas", "motivo"}`; 409 se inativa
- `GET /lista?n=10` -> reuniões recentes (`pasta`, `inicio`, `fim`, `duracao_s`, `ata`, `relatorio`, `diarizada`)
- `GET /reuniao/{pasta}` -> `reuniao.json` + `falas` (nome de pasta `AAAA-MM-DD_HHMM` ou `AAAA-MM-DD_HHMM-N` quando já existia, senão 404)
- `POST /diarizar {"pasta"}` -> 202 `{"ok": true}` (roda em thread); 409 se já está rodando; 404 pasta; 503 `{"erro", "motivo"}` se o modelo não está pronto
- `POST /falante {"pasta", "n", "nome"}` -> grava `falantes.json` e reescreve a transcrição

Guardas: `Host` fora de localhost -> 421; qualquer `Origin` -> 403 (o 4720 nunca é chamado por página); sem CORS.

## Como funciona
Encerrar por voz: "Vard, encerra a reunião" na trilha "eu". Fala de "eu" parecida com uma de "outros" no mesmo
instante é eco do alto-falante e é descartada. Se o dispositivo padrão mudar, a captura reabre sozinha e a
transcrição ganha o marcador "dispositivo trocou". O áudio FLAC fica em `tmp\` e é marcado para apagar
(`apagar_audio_em`), salvo `guardar_audio = true` em `config/reuniao.toml`.
Cada evento (`iniciou`, `encerrou`) vai para `POST {VARD_PONTE}/events/publicar`; se a ponte estiver fora ou
recusar, só aparece no log.

## Testes
`uv run --project reuniao pytest -q reuniao/tests` (o `uv run pytest` da raiz não os coleta).

## Fase 2: diarização (opt-in)
Depois da reunião, o pyannote `speaker-diarization-community-1` separa os falantes da trilha "outros" (a trilha "eu" é sempre o usuário).
Ligue com `[diarizacao] ligada = true` em `config/reuniao.toml` (ou aponte outra config com `VARD_REUNIAO_CONFIG=<arquivo>`).
Com isso, `/encerrar` devolve na hora e a diarização roda numa thread: a ponte recebe `diarizando` e, ao fim, `encerrou` de novo com
"... N falantes identificados." A transcrição passa a ter `falante 1`, `falante 2`... (renomeie com `/falante` ou `reuniao_falante`).

- Instalar (uma vez, com rede): `deploy\instalar-reuniao.ps1`. Lê `[huggingface] token` do `segredos.toml` (grave com
  `deploy\gravar-segredo.ps1 -Secao huggingface -Chave token`), baixa os modelos para `%LOCALAPPDATA%\rdl-vard\modelos\hf`, prova que
  carregam offline e grava `%LOCALAPPDATA%\rdl-vard\reuniao-modelos.json` (`pronto`, `modo`, `motivo`). O token só passa por `HF_TOKEN`, nunca por linha de comando.
  Se um modelo responder 403, o script imprime a URL para aceitar as condições; rode de novo depois.
- Modos: `community-1` (pipeline completo); `reserva` (só embeddings `wespeaker-voxceleb-resnet34-LM` por fala + agrupamento por cosseno 0,7) se só ele baixou; o `speaker-diarization-3.1` entra se o community-1 falhar na carga.
- Dispositivo: CPU, salvo se a GPU tiver >= 1500 MB livres (`nvidia-smi`). ~32 s para 40 s de áudio em CPU. O serviço roda com `HF_HUB_OFFLINE=1`.
- O áudio vem de `tmp\outros.flac`: se a retenção já o apagou (`apagar_audio_em`), a diarização responde `sem_audio`.
- Fixture de teste: `tests/fixtures/dois-falantes.wav` (gerada por `gerar_dois_falantes.ps1` com o Kokoro do OpenJarvis); o teste real só roda com o modelo baixado.
