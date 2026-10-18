# Voz própria (opcional)

Sem o serviço de voz, o HUD fala com a voz do OpenJarvis (`POST /v1/speech/synthesize`), quando ele está ligado: a
resposta inteira é sintetizada e só depois começa a tocar. Para respostas longas isso leva segundos.

A **voz própria** é um serviço local, separado do OpenJarvis, que recebe uma frase e devolve o áudio em fluxo, enquanto
sintetiza. Com ele no ar o HUD:

1. corta a resposta em frases (`.`, `!`, `?`, `…` e quebras de linha; abreviações como "Dr." e números como "1.200,00"
   não cortam; pedaços com menos de 12 caracteres vão junto com a frase anterior);
2. pede a primeira frase e começa a tocar assim que chega o primeiro pedaço de áudio;
3. pede a frase seguinte enquanto a atual ainda está tocando, e toca uma depois da outra, sempre na ordem.

Qualquer motor de voz serve (XTTS, Piper, F5, outro), desde que siga o contrato abaixo. O endereço fica em `voz_url`
(padrão `http://127.0.0.1:4710`); vazio desliga e o HUD volta a usar só o OpenJarvis.

## Kokoro sem OpenJarvis

O Kokoro é um motor do serviço de voz do Vard, como XTTS, Edge e Piper; não precisa do OpenJarvis.

- Biblioteca: [`kokoro-onnx`](https://github.com/thewh1teagle/kokoro-onnx) 0.6.1 (MIT), extra `kokoro` de
  `voz/pyproject.toml`. Escolhido por ser o mais leve: roda no onnxruntime, na CPU, e na GPU com o `onnxruntime-gpu`,
  sem torch.
- Modelo: Kokoro-82M v1.0 em ONNX int8 (`kokoro-v1.0.int8.onnx`, ~88 MB) e as vozes (`voices-v1.0.bin`, ~27 MB),
  Apache-2.0, das releases do kokoro-onnx. Vêm do pacote opcional `kokoro` do instalador de vozes
  (`config/pacotes/vozes.json`, hash SHA-256 conferido); nunca no teste nem na carga do serviço.
- Na aba Voz, o card **Kokoro** mostra **Instalar** quando falta o pacote: confirmar ("Instalar e usar") baixa pelo
  instalador e já deixa uma voz Kokoro escolhida. As vozes da lista vêm do `/vozes` do serviço (`por_motor.kokoro`).
- Vozes pt-BR: `pf_dora`, `pm_alex`, `pm_santa`; a escolha vai no campo `voz` do `/falar`, como as outras.
- Config antiga com `voz_provedor = "openjarvis"` e uma voz Kokoro (por exemplo `pm_alex`): o HUD pede a mesma voz ao
  serviço de voz. Com o Kokoro instalado lá, ela sai dele; sem ele, o serviço recusa a frase e ela segue a reserva
  de sempre. A aba Voz troca a config para `propria` + `kokoro` quando encontra o Kokoro no serviço (salve para
  gravar) e, sem ele, marca o Kokoro e oferece instalar.

## Quando a voz própria falha

A troca é silenciosa: o HUD não muda de estado nem avisa na tela, só registra `voz própria falhou, usei a reserva` no
console.

- Serviço fora do ar, conexão caindo no meio ou mais de **8 s** sem áudio (até o primeiro pedaço ou entre dois pedaços):
  aquela frase (refeita do começo se já tinha começado a tocar) e o resto da resposta saem pela voz do OpenJarvis. A próxima resposta tenta a voz própria de novo.
  Nas falas fixas que ainda não estão no cache o prazo é de **2 s**, para uma voz pendurada não atrasar o "Oi.".
- Qualquer outra recusa (`503` aquecendo, `400` texto inválido): só aquela frase sai pelo OpenJarvis; a seguinte tenta a
  voz própria outra vez.
- Interromper (botão, atalho ou push-to-talk) corta a frase que está tocando, cancela os pedidos em andamento e
  descarta as frases já prontas: nada toca depois.

As falas fixas ("Voltei.", "Não consegui ouvir direito." e as outras) também passam pela voz própria. O HUD guarda o WAV
de cada uma no cache do navegador (IndexedDB), com a chave `origem|voz|texto` (`origem` é `voz` ou `oj`; `voz` é o nome
que o serviço informa em `/saude`). Com o serviço fora, a fala fixa sai do cache da voz própria se já estiver lá; se não,
vai pelo OpenJarvis.

## Contrato

O serviço escuta só em `127.0.0.1`. Duas rotas:

### `GET /saude`

```json
{ "pronta": true, "voz": "Nome da voz", "device": "cuda", "aquecida": true }
```

- `pronta`: o modelo está carregado e o `/falar` atende. O HUD consulta a cada 5 s; só o `pronta` e o `voz` importam.
- `voz`: nome da voz em uso. Entra na chave do cache das falas fixas: trocar de voz no serviço faz o HUD sintetizar as
  falas fixas de novo.

### `POST /falar`

Corpo JSON:

```json
{ "texto": "Pronto, o YouTube já está aberto.", "velocidade": 1.05 }
```

- `texto`: uma frase, até 400 caracteres (o HUD nunca manda mais que isso).
- `velocidade`: o `velocidade` da configuração do HUD (1 é a velocidade normal).

Respostas:

| Caso | Status | Corpo |
| --- | --- | --- |
| Pedido com `Accept: audio/pcm` | `200` | PCM cru em fluxo (`Transfer-Encoding: chunked`), um pedaço por trecho sintetizado |
| Pedido sem `Accept: audio/pcm` | `200` | `audio/wav` inteiro (não é usado pelo HUD; útil para testar com `curl`) |
| Texto vazio ou com mais de 400 caracteres | `400` | `{"erro": "..."}` |
| Modelo ainda carregando | `503` | `{"erro": "aquecendo"}` |

Formato do fluxo (o HUD sempre pede este modo):

- `Content-Type: audio/pcm`
- PCM de 16 bits com sinal, little-endian, mono. Cabeçalhos `X-Taxa` (Hz), `X-Canais: 1` e `X-Formato: s16le`.
- Os pedaços podem ter qualquer tamanho, inclusive terminar no meio de uma amostra.
- O primeiro pedaço deve sair o quanto antes (o HUD toca depois de juntar ~100 ms); a frase inteira não precisa estar
  pronta.

A taxa padrão é **24000 Hz**. O navegador só deixa o HUD ler `X-Taxa` se o serviço mandar
`Access-Control-Expose-Headers: X-Taxa, X-Canais, X-Formato`; sem isso o HUD assume 24000. Um motor com outra taxa
precisa expor o cabeçalho (ou reamostrar para 24 kHz).

### CORS

O HUD instalado chama de `http://tauri.localhost` e o `tauri dev` de `http://localhost:1420`. O serviço precisa
responder ao preflight (`OPTIONS`) desses dois `Origin` aceitando `POST` e os cabeçalhos `content-type` e `accept`.

### `GET /vozes` (opcional)

```json
{ "vozes": ["Voz A", "Voz B", "pf_dora"], "atual": "Voz A", "por_motor": { "xtts": ["Voz A", "Voz B"], "kokoro": ["pf_dora"] } }
```

Alimenta a lista da aba Voz. `por_motor` (opcional) diz de que motor é cada voz; sem ele a aba separa pelas listas
conhecidas de `config/vozes.json`. Sem a rota (ou fora do ar) a lista fica vazia e a voz atual do serviço continua valendo.

### `voz` no `/falar` (opcional)

O corpo do `POST /falar` pode trazer `"voz": "Voz B"`, um nome da lista de `/vozes`. O HUD só manda o campo quando você escolhe uma voz no painel (`voz_propria`); sem ele o serviço usa a voz atual. Para um nome desconhecido o serviço deve responder `400`; nesse caso só aquela frase sai pelo OpenJarvis. A voz escolhida entra na chave do cache das falas fixas.

## Outros provedores

Os provedores `openjarvis` (voz do OpenJarvis; com voz Kokoro, ver acima), `elevenlabs` e `gemini` não usam este contrato: o HUD fala com eles direto, só quando escolhidos na aba Voz e, nos dois da nuvem, com a chave informada. Com um provedor na nuvem ligado, as falas fixas são sintetizadas nele uma vez no arranque, para aquecer o cache; com `propria` ou `openjarvis` nada sai da máquina.

## Testar sem um motor de voz

`VOZ=4710 npm run harness` (PowerShell: `$env:VOZ=4710; npm run harness`) sobe uma voz falsa que segue este contrato:
3 pedaços de 0,1 s de silêncio em PCM, ou um WAV de 0,3 s sem o `Accept`, e a rota `/vozes` com duas vozes. Não suba a voz falsa com um serviço de voz
de verdade na mesma porta.

Com um serviço de verdade no ar, um teste rápido (bash):

```
curl -s -H 'Accept: audio/pcm' -H 'Content-Type: application/json' -d '{"texto":"Teste.","velocidade":1}' -D - -o teste.pcm http://127.0.0.1:4710/falar
```
