# Project Vard — instruções para agentes

## Projeto

Produto público MIT: widget Windows em Tauri/TypeScript/Rust, com voz, conversa, configurações,
sala e conectores. OpenJarvis é o primeiro conector; a ponte local é opcional.
Leia `README.md`, `CONTRIBUTING.md` e o spec/plano da tarefa antes de editar.
Confira o estado da branch: os próximos passos do roadmap ainda podem estar em execução.

## Regras

- Interface, código e respostas em português do Brasil; mantenha o README em PT-BR e inglês.
- Commits e PRs sem rodapés de coautoria e sem menção ou atribuição a IA.
- Antes de um commit autorizado, confira `git config user.email`: deve ser o endereço GitHub noreply
  específico do dono, confirmado na configuração do repositório; um noreply genérico não serve.
- Nenhum nome pessoal, caminho absoluto pessoal, letra de unidade, credencial ou dado real no repo,
  em capturas ou fixtures. Exemplos usam valores fictícios; parâmetros pessoais vêm da configuração.
- Segredos nunca entram em código, log, erro, prova ou documentação; use o mecanismo local da versão.
  Cofre Windows e migração de chaves são trabalho previsto para os Painéis, não recurso presumido pronto.
- Provas por testes, harness e CDP; nunca injete teclado/mouse ou dispare atalhos globais do sistema.
- Uma instância do aplicativo. Confira o mecanismo existente antes de rodar desenvolvimento junto
  de uma instalação; uma segunda instância pode reutilizar a primeira, invalidando a prova.
- Prova que abre app, Vite, harness ou serviço fecha todos os seus processos ao fim, preservando
  processos do usuário. Identifique executável, PID e início; não encerre todos os processos por nome.
- ABNT2: AltGr equivale a Ctrl+Alt. Nunca use Ctrl+Alt com vírgula, E, Q, W, C, 2 ou 3;
  essas combinações roubam caracteres. Preserve o contrato dos atalhos e teste registro sem injeção.
- Respeite o escopo: implemente o pedido sem inventar infraestrutura, política ou serviço adicional.

## Desenvolvimento e testes

Requisitos: Windows 10/11, Node.js 22+, Rust MSVC, Build Tools C++ e WebView2.
Na raiz do worktree:

```powershell
npm install
npm test
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml
npm run tauri dev
```

Confira os scripts atuais em `package.json`; `npm run check` inclui tipos de src e testes.
Em dev, `/oj` usa proxy Vite; no instalado, o conector usa o endereço configurado diretamente.
Não altere o CORS de um serviço real para fazer o dev funcionar.

## Harness e provas

Em um terminal: `npm run harness` (OpenJarvis falso em `127.0.0.1:8765`). Em outro:

```powershell
$env:VITE_OJ_ALVO = "http://127.0.0.1:8765"
npm run tauri dev
```

Para ponte/voz falsas, consulte `CONTRIBUTING.md`; reserve portas livres, sem disputar serviços reais.
Por CDP, use `window.__vardPergunta(...)`, `window.__vardOuvido(...)` e `window.__vardMover(...)`,
disponíveis só em dev. Para capturas, abra `configuracoes.html` no Vite com invoke simulado e dados fictícios.
`npm run test:real` exige `HUD_REAL=1` e `HUD_REAL_WAV` apontando para um WAV controlado.
Harness prova integração simulada; uma conta/provedor real só está validado após prova real registrada.
Não troque/teste outro modelo residente sem descarregar o anterior; evite carga JIT extra na GPU.
Modo invisível usa opacidade e clique atravessando; hide da janela prejudica a captura de voz.

## Roadmap e documentos

Use specs e planos saneados em `docs/`, copiados para este repositório antes de iniciar uma versão.
Agentes não devem depender de memória ou documentos externos de outra sessão.
Direção: 0.4 MVP → 0.5 Painéis → 0.6 app único → 0.7 cérebro próprio → 0.8 primeiro uso
→ 1.0 guia e assinatura SignPath. Reaproveite a fundação da branch v0.4 por tarefa, preservando a fonte.
Textos antigos podem ter outra sequência; confirme o plano vigente e não trate previsão como entrega.
Publique somente documentação do produto: instalação genérica, contratos, testes e decisões técnicas.
