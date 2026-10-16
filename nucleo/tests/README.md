# Testes sem acesso ao PC real

`conftest.py` instala a guarda de `guarda_pc.py` antes da coleta. Voz e reunião
importam a mesma guarda. Por padrão, conexões externas e conexões loopback nas
portas 1234, 8000, 4700, 4710 e 4720 falham antes do acesso ao sistema.
`httpx` com transporte simulado, `respx` e `TestClient` continuam funcionando;
servidores falsos usam portas livres e encerram threads, sockets e filhos no `finally`.

CLIs de agentes, SSH, GitHub CLI, LM Studio, PowerShell, taskkill e sondas do
Windows exigem dublês. A fixture `powershell_isolado` permite apenas `-File`
sob o diretório temporário do teste. Ela serve a harnesses revisados que extraem
funções via AST ou executam cópias com caminhos e sondas substituídos.
Não basta copiar um script arbitrário para obter isolamento: revise seus efeitos,
substitua todas as dependências externas e mantenha as asserções do contrato.

As variáveis de pastas pessoais, configuração, dados e caches de modelos apontam
para pastas temporárias antes dos imports. A reunião usa PyAudio falso: nenhuma
enumeração ou captura de dispositivo real pertence à suíte padrão.

Provas dependentes do PC usam `@pytest.mark.pc_real` e são puladas por padrão.
Para uma execução manual e deliberada, selecione o teste específico e passe
`--pc-real`; as antigas opções adicionais continuam exigidas quando presentes.
Esse modo permite acessar o ambiente do operador e nunca é requisito da suíte normal.

Provas manuais preservadas:

- `test_wer.py`: OpenJarvis, WAV e referência controlados, definidos pelo preflight.
- `test_preflight.py::test_reuniao_wav_a_16k_mono`: WAV controlado da prova real.
- `test_patch_openjarvis.py`: checkout externo indicado por `VARD_TESTE_OPENJARVIS_SRC`.
- `test_runtime_instalado.py`: seis verificações que exigem bundle previamente montado;
  os três testes de recusa/hash executam cópia do montador dentro de tmp na suíte normal.
- `test_entrada.py::test_wheel_instalado_fora_do_repo`: build, venv e instalação de
  dependências por ferramentas que podem acessar a rede fora da guarda do processo pai.
- `test_vard_modo.py`: estado da instalação e ciclo real de jogo/retorno;
  ainda exigem `VARD_TESTE_REAL=1` ou `VARD_TESTE_CICLO=1`.
- `test_modo.py`: destacamento de processos PowerShell no Windows.
- `reuniao/tests/test_diarizacao.py::test_real_dois_falantes_der_abaixo_de_30_por_cento`:
  modelo previamente baixado e execução deliberada de inferência.

`test_guarda_pc.py` comprova os bloqueios sem enviar chamadas proibidas e comprova
que um servidor falso em porta livre permanece acessível. A guarda é defesa contra
regressões acidentais, não uma sandbox do sistema operacional: subprocessos
permitidos também precisam ser auditados e usar apenas estado fictício.
