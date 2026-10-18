# vard-voz

Serviço local de voz do Vard: XTTS v2, voz "Suad Qasim", só em 127.0.0.1:4710.
Projeto uv separado (Python 3.12, torch cu128) em `voz/.venv`; o projeto principal usa 3.13.

- Subir: `uv --directory voz run python -m vard_voz` (env: `VARD_VOZ_PORT`=4710, `VARD_VOZ_DEVICE`=cuda|cpu)
- `GET /saude` -> `{"pronta","voz","device","aquecida"}`
- `GET /vozes` -> `{"vozes": [...], "atual": "Suad Qasim", "por_motor": {"xtts": [...], "kokoro": [...]}}` (Suad primeiro, resto em ordem alfabética); 503 `{"erro":"aquecendo"}` sem nenhum motor
- `POST /falar` `{"texto" (até 400 chars), "velocidade": 1.0, "voz": "Ana Florence" (opcional)}` -> `audio/wav` 24 kHz mono 16 bits; sem `voz` (ou vazia) usa a Suad; voz que não existe -> 400 `{"erro":"voz_desconhecida"}`; 503 `{"erro":"aquecendo"}` enquanto carrega
- `POST /v1/speech/transcribe` (extra `stt`, faster-whisper) -> `{"text","confidence"}`
- Modelos de transcrição (aba Transcrição das Configurações), no cache do Hugging Face:
  - `GET /v1/stt/modelos` -> `{"modelos": [{id, nome, tamanho_mb, idioma, velocidade, precisao, baixado, ativo, progresso}], "ativo", "dispositivo", "device", "pronta", "carregando", "erro"}`
  - `POST /v1/stt/modelos/{id}/baixar` (202) e `GET /v1/stt/modelos/{id}/progresso` -> `{"estado": parado|baixando|concluido|falhou, "bytes", "total", "porcentagem", "erro"}`
  - `POST /v1/stt/modelos/{id}/apagar`; o modelo em uso devolve 409 `modelo_em_uso`
  - `POST /v1/stt/ativar` `{"modelo"?, "dispositivo"?: auto|cuda|cpu}` (202): descarrega o atual e carrega o novo em segundo plano; modelo não baixado -> 409 `modelo_nao_baixado`
- Escolha do modelo: `stt_modelo`/`stt_dispositivo` do `hud.config.json` (pasta em `VARD_HUD_CONFIG_DIR`, passada pelo app) ganham de `VARD_STT_MODEL`, `VARD_STT_DEVICE` e `VARD_STT_COMPUTE`, que seguem como reserva.
- Testes: `uv run --project voz pytest -q voz/tests`
- Kokoro (sem OpenJarvis): extra `kokoro` (`kokoro-onnx==0.6.1`, MIT; fonte: https://github.com/thewh1teagle/kokoro-onnx
  e https://pypi.org/project/kokoro-onnx/) + os arquivos do modelo Kokoro-82M v1.0 (Apache-2.0) que o instalador de
  vozes baixa no pacote `kokoro` (`kokoro-v1.0.int8.onnx`, ~88 MB, e `voices-v1.0.bin`, ~27 MB, hash conferido) para
  `<VARD_DADOS ou %LOCALAPPDATA%\rdl-vard>\pacotes\ativo\kokoro` (outra pasta: `VARD_KOKORO_DIR`). Nada baixa no
  teste nem na carga: sem biblioteca ou arquivos o motor fica fora.
  - Subir com ele: `uv --directory voz run --extra kokoro python -m vard_voz`.
  - Vozes pt-BR `pf_dora`, `pm_alex`, `pm_santa` (e as en-US/en-GB de `VOZES_KOKORO`); o idioma dos fonemas segue a
    primeira letra do ID (`p` pt-br, `a` en-us, `b` en-gb). Velocidade limitada a 0,5–2.
  - CPU por padrão; com `VARD_KOKORO_DEVICE` (ou `VARD_VOZ_DEVICE`) = `cuda` e o `onnxruntime-gpu` no ambiente usa
    a GPU, com a CPU de reserva.
  - `/saude`: `kokoro` = instalado (carrega sob demanda), `kokoro_carregado` = na memória. `/vozes` lista as vozes dele
    e `por_motor` diz de que motor é cada voz. O primeiro `/falar` com voz Kokoro carrega o modelo se ele foi
    instalado depois que o serviço subiu.
- Normalização do texto antes da síntese (`vard_voz/normalizar.py`): tira ponto/"!" final, verbaliza horas, números, valores, datas, URLs e abreviações; `VARD_VOZ_DEBUG=1` loga o texto normalizado.
