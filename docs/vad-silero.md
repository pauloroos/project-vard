# Detecção de voz e interrupção

Na aba **Voz**, escolha **Energia** (padrão existente) ou **Silero (local)** e, separadamente,
**Interromper ao falar por cima** (desligado por padrão). Salve e reinicie o aplicativo.
Nenhuma instalação existente muda de comportamento até essas escolhas serem feitas.

Silero v5 roda no navegador do widget com ONNX Runtime Web, usando o mesmo microfone e
contexto de áudio. Modelo, worklet e WASM acompanham o build; não há download por CDN
nem envio do microfone a outro serviço para detectar voz. Enquanto carrega, ou se a carga
falha, o detector de energia continua disponível. Falha de carga gera um aviso sem dados do erro.
As versões são fixadas no lockfile: vad-web 0.0.31 (ISC, publicada em 2026-09-12) e
onnxruntime-web 1.22.0 (MIT, publicada em 2025-05-09). O modelo Silero é MIT.

O início por Silero exige probabilidade de fala de pelo menos 0,8 sustentada por 150 ms
(250 ms com interrupção ligada). O fim respeita `finish_ms`; o teto continua em 12 segundos.
Com interrupção ligada, fala confirmada corta a reprodução, invalida o ciclo anterior e
inicia outra captura com pré-roll. Resposta OpenJarvis tardia é ignorada; pedido do cérebro
próprio é cancelado pela ponte, inclusive se ainda estiver sendo admitido.

O cancelamento de eco do microfone permanece habilitado. O widget também compara nível
e correlação da entrada com referências recentes da saída antes de aceitar uma interrupção.
Fones de ouvido melhoram a separação: ambientes com reverberação ou microfones distantes
podem exigir fala mais forte; o filtro é conservador e não substitui uma prova acústica no
ambiente de uso. Jogo, reunião, não ouvir e push-to-talk impedem interrupção automática.
A interrupção automática não muda as regras do nome de chamada, conversa aberta ou chamadas.

Implementação original inspirada na interação por voz do Open-LLM-VTuber, sem portar trechos
daquele projeto. As licenças dos componentes distribuídos estão em `THIRD_PARTY_NOTICES.md`.
