# Ligar a fala no OpenJarvis

O HUD usa a fala do próprio OpenJarvis: transcrição (speech to text) e síntese (text to speech). Ela vem desligada; ligue a seção `[speech]` do `config.toml` do OpenJarvis (fica na pasta apontada por `OPENJARVIS_HOME`, ou em `~/.openjarvis/`).

## Configuração usada pelo autor (GPU NVIDIA)

```toml
[speech]
backend = "faster-whisper"
model = "large-v3-turbo"
language = "pt"
device = "cuda"
compute_type = "float16"
tts_backend = "kokoro"
voice_id = "pm_alex"
```

| Campo | Para quê |
| --- | --- |
| `backend` | Motor de transcrição. `faster-whisper` roda local |
| `model` | Modelo do Whisper. `large-v3-turbo` é rápido e bom em português |
| `language` | Idioma do reconhecimento (o HUD também manda `idioma` em cada pedido) |
| `device` | `cuda` usa a GPU; sem placa NVIDIA use `cpu` |
| `compute_type` | `float16` na GPU; `int8` costuma ser a melhor escolha no CPU |
| `tts_backend` | Motor de voz. `kokoro` roda local |
| `voice_id` | Voz. `pm_alex` é voz masculina em português; deve bater com `voz` no HUD |

Sem GPU, troque por `device = "cpu"`, `compute_type = "int8"` e, se ficar lento, um modelo menor (`small`).

## Conferir

Com o servidor no ar (`jarvis serve`), este endereço deve responder `{"available": true, ...}`:

```
curl http://127.0.0.1:8000/v1/speech/health
```

Se `available` vier `false`, leia o log do servidor: costuma faltar um pacote da fala (instale o extra de fala do OpenJarvis) ou as bibliotecas CUDA.

## CORS

O app instalado fala com o OpenJarvis a partir da origem `http://tauri.localhost`; o OpenJarvis padrão já a aceita. Se o seu servidor restringe origens, inclua essa (e `http://localhost:1420` para o `tauri dev`) em `OPENJARVIS_CORS_ORIGINS`.
