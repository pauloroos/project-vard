# Referência visual do openjarvis-hud (prompt do Paulo, 12/10/2026)

Atue como um Engenheiro Frontend Sênior e UI/UX Designer especializado em interfaces de ficção científica (FUI/HUD).

Crie uma interface de voz ao vivo para desktop inspirada no JARVIS (Stark Industries), feita para rodar como um widget flutuante e frameless em Tauri (HTML5 Canvas/SVG, Tailwind CSS e Web Audio API).

### 1. Conceito Visual & Estética
- Tema: Central holográfica militar-futurista de alta tecnologia (Iron Man Mark HUD).
- Paleta de Cores: Fundo: transparência escura com efeito de vidro fosco (`rgba(8, 12, 20, 0.75)` com `backdrop-blur-md`). Cor primária (Jarvis normal): azul ciano elétrico (`#00f0ff`) com brilho neon (`box-shadow`/`drop-shadow` em tons de `#00a2ff`). Acentos de processamento: âmbar/laranja quântico (`#ff9900`) e dourado Stark. Tipografia: estilo técnico/mono (ex: JetBrains Mono ou Share Tech Mono), texto em caixa alta, tamanho ultra-compacto com tracking alargado.
- Formato: widget compacto circular ou octogonal central flutuante com telemetria orbital. Suporte nativo para arraste de janela (`data-tauri-drag-region`).

### 2. O Núcleo Vivo (Reactive Core / Reator Arc)
- Camadas concêntricas: pelo menos 3 anéis circulares concêntricos que giram em eixos e direções opostas com marcações de escala militar/métrica (ticks, graus, nós).
- Visualizador de frequência de áudio: FFT radial que reage a um `AnalyserNode` da Web Audio API; barras ou partículas pulsam para fora a partir do anel central conforme graves, médios e agudos.
- Núcleo interno (esfera de energia): esfera de plasma/partículas orgânica com ruído Perlin/Simplex para movimento fluido mesmo sem áudio.

### 3. Estados da Entidade
1. IDLE: respiração suave (0,8 Hz), anéis lentos em ciano frio, partículas calmas.
2. LISTENING: foco no microfone; anéis externos desaceleram; visualizador radial expande com a amplitude da voz humana.
3. PROCESSING: cor alterna para dourado/âmbar; rotação acelera e os anéis se contraem; glifos e números hexadecimais piscam ao redor.
4. SPEAKING: esfera central pulsa em sincronia com o buffer de saída do TTS; ondas sonoras radiais disparam do centro; anéis reagem às frequências da fala.

### 4. Telemetria e HUD Periférico
- Mini medidores de dB (entrada do microfone e saída do TTS) nas laterais, em barras segmentadas.
- Status técnico discreto no topo: `JARVIS CORE // LOCAL ENGINE: ONLINE` com latência (ms) e taxa de amostragem (`48.0 kHz`).
- Botões discretos: Mute Mic, Parar Resposta (Interrupt), Modo Compacto/Expandido.

Adaptações decididas: sem Tailwind e sem Three.js (TypeScript puro + Canvas 2D); rótulos e falas em português; ciano como base e âmbar só em "pensando".
