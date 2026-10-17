# vard-voz

Serviço local de voz do Vard: XTTS v2, voz "Suad Qasim", só em 127.0.0.1:4710.
Projeto uv separado (Python 3.12, torch cu128) em `voz/.venv`; o projeto principal usa 3.13.

- Subir: `uv --directory voz run python -m vard_voz` (env: `VARD_VOZ_PORT`=4710, `VARD_VOZ_DEVICE`=cuda|cpu)
- `GET /saude` -> `{"pronta","voz","device","aquecida"}`
- `GET /vozes` -> `{"vozes": [...], "atual": "Suad Qasim"}` (Suad primeiro, resto em ordem alfabética); 503 `{"erro":"aquecendo"}` enquanto carrega
- `POST /falar` `{"texto" (até 400 chars), "velocidade": 1.0, "voz": "Ana Florence" (opcional)}` -> `audio/wav` 24 kHz mono 16 bits; sem `voz` (ou vazia) usa a Suad; voz que não existe -> 400 `{"erro":"voz_desconhecida"}`; 503 `{"erro":"aquecendo"}` enquanto carrega
- `POST /v1/speech/transcribe` (extra `stt`, faster-whisper) -> `{"text","confidence"}`
- Modelos de transcrição (aba Transcrição das Configurações), no cache do Hugging Face:
  - `GET /v1/stt/modelos` -> `{"modelos": [{id, nome, tamanho_mb, idioma, velocidade, precisao, baixado, ativo, progresso}], "ativo", "dispositivo", "device", "pronta", "carregando", "erro"}`
  - `POST /v1/stt/modelos/{id}/baixar` (202) e `GET /v1/stt/modelos/{id}/progresso` -> `{"estado": parado|baixando|concluido|falhou, "bytes", "total", "porcentagem", "erro"}`
  - `POST /v1/stt/modelos/{id}/apagar`; o modelo em uso devolve 409 `modelo_em_uso`
  - `POST /v1/stt/ativar` `{"modelo"?, "dispositivo"?: auto|cuda|cpu}` (202): descarrega o atual e carrega o novo em segundo plano; modelo não baixado -> 409 `modelo_nao_baixado`
- Escolha do modelo: `stt_modelo`/`stt_dispositivo` do `hud.config.json` (pasta em `VARD_HUD_CONFIG_DIR`, passada pelo app) ganham de `VARD_STT_MODEL`, `VARD_STT_DEVICE` e `VARD_STT_COMPUTE`, que seguem como reserva.
- Testes: `uv run --project voz pytest -q voz/tests`
- Normalização do texto antes da síntese (`vard_voz/normalizar.py`): tira ponto/"!" final, verbaliza horas, números, valores, datas, URLs e abreviações; `VARD_VOZ_DEBUG=1` loga o texto normalizado.
