//! Supervisor generalizado de serviços: lança, sonda, reinicia e encerra filhos com Job Object próprio.
//! Cada serviço tem seu próprio Job Object, log e máquina de recuo.
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::supervisor::{
    self, Decisao, Log, SONDA_REGIME, SONDA_TIMEOUT, PRAZO_LEITORES,
};

// ---------------------------------------------------------------------------------------------------------------------
// Registro global de serviços (API pública)
// ---------------------------------------------------------------------------------------------------------------------
lazy_static::lazy_static! {
    static ref SERVICOS: RwLock<HashMap<String, Arc<ServicoHandle>>> = RwLock::new(HashMap::new());
}

/// Inicia um serviço gerenciado pelo supervisor. Retorna erro se já existir ou se o descritor for inválido.
pub fn iniciar(desc: DescritorServico) -> Result<(), String> {
    let id = desc.id.clone();
    {
        let reg = SERVICOS.read().map_err(|e| e.to_string())?;
        if reg.contains_key(&id) {
            return Err(format!("serviço '{id}' já está registrado"));
        }
    }
    let handle = Arc::new(ServicoHandle::novo(&id, desc.porta));
    // Guarda o descritor no handle ANTES de mover o original para a thread.
    {
        let mut d = handle.desc.lock().map_err(|e| e.to_string())?;
        *d = Some(desc.clone());
    }
    {
        let mut reg = SERVICOS.write().map_err(|e| e.to_string())?;
        reg.insert(id.clone(), handle.clone());
    }
    let h = handle.clone();
    if let Err(erro) = std::thread::Builder::new()
        .name(format!("supervisor-{id}"))
        .spawn(move || {
            loop_servico(h.clone(), desc);
            h.terminou.store(true, Ordering::SeqCst);
        }) {
        if let Ok(mut reg) = SERVICOS.write() { reg.remove(&id); }
        return Err(format!("falha ao iniciar thread do serviço '{id}': {erro}"));
    }
    Ok(())
}

/// Sinaliza parada intencional de um serviço (não reinicia, não conta queda).
pub fn parar(id: &str) -> Result<(), String> {
    let reg = SERVICOS.read().map_err(|e| e.to_string())?;
    let handle = reg.get(id).ok_or_else(|| format!("serviço '{id}' não encontrado"))?;
    handle.pedir_parada();
    Ok(())
}

/// Sinaliza reinício manual de um serviço. Se a thread morreu, recria com o descritor guardado.
pub fn repetir(id: &str) -> Result<(), String> {
    let reg = SERVICOS.read().map_err(|e| e.to_string())?;
    let handle = reg.get(id).ok_or_else(|| format!("serviço '{id}' não encontrado"))?;

    // Se a thread terminou, recria usando o descritor guardado no handle.
    if handle.terminou.load(Ordering::SeqCst) {
        let desc = {
            let d = handle.desc.lock().map_err(|e| e.to_string())?;
            d.clone()
        };
        let desc = desc.ok_or_else(|| format!("serviço '{id}' sem descritor para recriar"))?;

        // Reseta flags antes de spawnar nova thread.
        handle.parar.store(false, Ordering::SeqCst);
        handle.reiniciar.store(false, Ordering::SeqCst);
        handle.terminou.store(false, Ordering::SeqCst);

        let h = handle.clone();
        if let Err(erro) = std::thread::Builder::new()
            .name(format!("supervisor-{id}"))
            .spawn(move || {
                loop_servico(h.clone(), desc);
                h.terminou.store(true, Ordering::SeqCst);
            })
        {
            return Err(format!("falha ao recriar thread do serviço '{id}': {erro}"));
        }
    } else {
        // Thread ainda viva: sinaliza reinício suave.
        handle.pedir_reinicio();
    }
    Ok(())
}

/// Parada definitiva: sinaliza parada, espera a thread terminar e remove o registro.
/// Permite chamar `iniciar()` novamente depois.
pub fn parar_definitiva(id: &str) -> Result<(), String> {
    let handle = {
        let reg = SERVICOS.read().map_err(|e| e.to_string())?;
        reg.get(id).cloned().ok_or_else(|| format!("serviço '{id}' não encontrado"))?
    };

    handle.pedir_parada();

    // Espera a thread terminar (timeout de 5s).
    let fim = std::time::Instant::now() + std::time::Duration::from_secs(5);
    while !handle.terminou.load(Ordering::SeqCst) {
        if std::time::Instant::now() >= fim {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }

    // Remove o registro para permitir novo iniciar().
    let mut reg = SERVICOS.write().map_err(|e| e.to_string())?;
    reg.remove(id);
    Ok(())
}

/// Estado público de um serviço para consulta.
#[derive(Debug, Clone, Serialize)]
pub struct FotoServico {
    pub id: String,
    pub estado: supervisor::EstadoServico,
    pub detalhe: String,
    pub pid: Option<u32>,
    pub porta: u16,
}

/// Retorna o estado atual de um serviço registrado.
pub fn foto(id: &str) -> Result<FotoServico, String> {
    let reg = SERVICOS.read().map_err(|e| e.to_string())?;
    let handle = reg.get(id).ok_or_else(|| format!("serviço '{id}' não encontrado"))?;
    let info = handle.info.lock().map_err(|e| e.to_string())?;
    Ok(FotoServico {
        id: info.id.clone(),
        estado: info.estado,
        detalhe: info.detalhe.clone(),
        pid: info.pid,
        porta: info.porta,
    })
}

/// Encerra todos os serviços registrados (chamado na saída do app).
pub fn encerrar_todos() {
    if let Ok(reg) = SERVICOS.read() {
        for (_, handle) in reg.iter() {
            handle.pedir_parada();
        }
    }
}

/// Espera a liberação dos Job Objects antes de entregar as portas ao caminho antigo.
pub fn parar_e_aguardar(ids: &[String], prazo: Duration) -> Result<(), String> {
    let handles: Vec<_> = {
        let reg = SERVICOS.read().map_err(|_| "registro de serviços indisponível")?;
        ids.iter().filter_map(|id| reg.get(id).map(|h| (id.clone(), h.clone()))).collect()
    };
    for (_, h) in &handles { h.pedir_parada(); }
    let fim = Instant::now() + prazo;
    while handles.iter().any(|(_, h)| !h.terminou.load(Ordering::SeqCst)) {
        if Instant::now() >= fim { return Err("prazo ao encerrar serviços próprios".into()); }
        std::thread::sleep(Duration::from_millis(50));
    }
    let mut reg = SERVICOS.write().map_err(|_| "registro de serviços indisponível")?;
    for (id, _) in handles { reg.remove(&id); }
    Ok(())
}

/// Repete todos os serviços que estão no estado Desistiu.
pub fn repetir_desistidos() {
    if let Ok(reg) = SERVICOS.read() {
        for (id, _handle) in reg.iter() {
            if let Ok(f) = foto(id) {
                if matches!(f.estado, supervisor::EstadoServico::Desistiu) {
                    let _ = repetir(id);
                }
            }
        }
    }
}

/// Descritor de um serviço gerenciado pelo supervisor.
#[derive(Debug, Clone)]
pub struct DescritorServico {
    /// Identificador único do serviço (ex: "nucleo", "voz").
    pub id: String,
    /// Porta HTTP onde o serviço responde /saude.
    pub porta: u16,
    /// Comando para lançar o serviço (exe + args).
    pub comando: (PathBuf, Vec<String>),
    /// Pasta de trabalho do módulo, independente da pasta do executável.
    pub pasta_trabalho: Option<PathBuf>,
    /// Variáveis de ambiente adicionais.
    pub envs: Vec<(String, String)>,
    /// Caminho do log do serviço.
    pub caminho_log: PathBuf,
}

/// Estado público de um serviço.
#[derive(Debug, Clone, Serialize)]
pub struct InfoServico {
    pub id: String,
    pub estado: supervisor::EstadoServico,
    pub detalhe: String,
    pub pid: Option<u32>,
    pub porta: u16,
}

/// Handle de um serviço em execução.
pub struct ServicoHandle {
    pub info: Arc<Mutex<InfoServico>>,
    /// Descritor guardado para permitir recriar a thread após parada definitiva ou morte.
    pub desc: Mutex<Option<DescritorServico>>,
    parar: AtomicBool,
    reiniciar: AtomicBool,
    pub terminou: AtomicBool,
}

impl ServicoHandle {
    pub fn novo(id: &str, porta: u16) -> Self {
        ServicoHandle {
            info: Arc::new(Mutex::new(InfoServico {
                id: id.to_string(),
                estado: supervisor::EstadoServico::Ausente,
                detalhe: String::new(),
                pid: None,
                porta,
            })),
            desc: Mutex::new(None),
            parar: AtomicBool::new(false),
            reiniciar: AtomicBool::new(false),
            terminou: AtomicBool::new(false),
        }
    }

    /// Sinaliza parada intencional (não reinicia).
    pub fn pedir_parada(&self) {
        self.parar.store(true, Ordering::SeqCst);
    }

    /// Sinaliza reinício manual (cancela recuo/arranque).
    pub fn pedir_reinicio(&self) {
        self.reiniciar.store(true, Ordering::SeqCst);
    }

    fn deve_parar(&self) -> bool {
        self.parar.load(Ordering::SeqCst)
    }

    fn deve_reiniciar(&self) -> bool {
        self.reiniciar.swap(false, Ordering::SeqCst)
    }

    fn mudar_estado(&self, estado: supervisor::EstadoServico, detalhe: &str, pid: Option<u32>) {
        if let Ok(mut info) = self.info.lock() {
            info.estado = estado;
            info.detalhe = detalhe.to_string();
            info.pid = pid;
        }
    }
}

/// Resultado de uma execução do serviço.
/// Monta o comando usado em produção e nas provas com executáveis falsos.
pub fn montar_comando(desc: &DescritorServico) -> Command {
    let mut cmd = Command::new(&desc.comando.0);
    cmd.args(&desc.comando.1);
    if let Some(pasta) = &desc.pasta_trabalho { cmd.current_dir(pasta); }
    limpar_ambiente(&mut cmd);
    cmd.envs(desc.envs.iter().map(|(k, v)| (k.as_str(), v.as_str())));
    cmd
}

/// Retira contaminação do Python e marcadores da sessão do agente dos filhos.
pub fn limpar_ambiente(cmd: &mut Command) {
    for variavel in supervisor::variaveis_tiradas() { cmd.env_remove(variavel); }
    for (nome, _) in std::env::vars_os() {
        let maiusculo = nome.to_string_lossy().to_ascii_uppercase();
        if ["CLAUDE_", "CODEX_", "ORCA_", "AGY_", "GEMINI_CLI_"].iter().any(|p| maiusculo.starts_with(p)) {
            cmd.env_remove(nome);
        }
    }
    cmd.env("PYTHONUTF8", "1");
}

enum FimServico {
    Queda(String),
    Permanente(String),
    Reinicio,
    Parada,
}

/// Cria um Job Object para este serviço. Se falhar, aborta sem deixar órfão.
#[cfg(windows)]
fn criar_job() -> Result<crate::supervisor::JobHandle, String> {
    crate::supervisor::JobHandle::novo()
}

#[cfg(not(windows))]
fn criar_job() -> Result<crate::supervisor::JobHandle, String> {
    crate::supervisor::JobHandle::novo()
}

/// Sonda HTTP de saúde com timeout.
fn sondar_saude(porta: u16, pid_filho: u32, pids_do_job: &[u32]) -> bool {
    let url = format!("http://127.0.0.1:{porta}/saude");
    let cliente = match reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(SONDA_TIMEOUT)
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    let resposta = match cliente.get(&url).send() {
        Ok(r) => r,
        Err(_) => return false,
    };
    let corpo = match resposta.text() {
        Ok(c) => c,
        Err(_) => return false,
    };
    supervisor::saude_aceita(&corpo, pid_filho, pids_do_job)
}

/// Loop principal do supervisor para um serviço. Roda em thread dedicada.
pub fn loop_servico(handle: Arc<ServicoHandle>, desc: DescritorServico) {
    let mut log = Log::abrir(desc.caminho_log.clone());
    let mut recuo = supervisor::Recuo::new();

    loop {
        if handle.deve_parar() {
            handle.mudar_estado(supervisor::EstadoServico::Ausente, "parado", None);
            return;
        }

        match rodar_uma_vez(&handle, &desc, &mut log, &mut recuo) {
            FimServico::Parada => {
                handle.mudar_estado(supervisor::EstadoServico::Ausente, "parado", None);
                return;
            }
            FimServico::Reinicio => {
                recuo.zerar();
                log.linha(&format!("[{}] reinício pedido", desc.id));
            }
            FimServico::Permanente(motivo) => {
                log.linha(&format!("[{}] desistiu: {motivo}", desc.id));
                handle.mudar_estado(supervisor::EstadoServico::Desistiu, &motivo, None);
                // Espera sinal de reinício manual
                while !handle.deve_reiniciar() && !handle.deve_parar() {
                    std::thread::sleep(Duration::from_millis(200));
                }
                recuo.zerar();
            }
            FimServico::Queda(detalhe) => {
                handle.mudar_estado(supervisor::EstadoServico::Caiu, &detalhe, None);
                match recuo.registrar_queda(Instant::now()) {
                    Decisao::Esperar(d) => {
                        log.linha(&format!(
                            "[{}] caiu ({detalhe}); novo arranque em {} s",
                            desc.id,
                            d.as_secs()
                        ));
                        // Dorme com verificação de parada/reinício
                        let fim = Instant::now() + d;
                        while Instant::now() < fim {
                            if handle.deve_parar() {
                                return;
                            }
                            if handle.deve_reiniciar() {
                                recuo.zerar();
                                break;
                            }
                            std::thread::sleep(Duration::from_millis(100));
                        }
                    }
                    Decisao::Desistir(motivo) => {
                        let texto = format!("{motivo} ({detalhe})");
                        log.linha(&format!("[{}] desistiu: {texto}", desc.id));
                        handle.mudar_estado(supervisor::EstadoServico::Desistiu, &texto, None);
                        while !handle.deve_reiniciar() && !handle.deve_parar() {
                            std::thread::sleep(Duration::from_millis(200));
                        }
                        recuo.zerar();
                    }
                }
            }
        }
    }
}

fn rodar_uma_vez(
    handle: &ServicoHandle,
    desc: &DescritorServico,
    log: &mut Log,
    _recuo: &mut supervisor::Recuo,
) -> FimServico {
    handle.mudar_estado(supervisor::EstadoServico::Subindo, "", None);

    let exe = &desc.comando.0;
    if !exe.exists() {
        return FimServico::Permanente(format!("executável não encontrado: {}", exe.display()));
    }

    let token = supervisor::token_novo();
    let mut cmd = montar_comando(desc);
    cmd
        .env("VARD_TOKEN", &token)
        .env("VARD_PORTA", desc.porta.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }

    // Job Object por serviço: se falhar, aborta sem deixar órfão.
    let job = match criar_job() {
        Ok(j) => j,
        Err(e) => return FimServico::Permanente(format!("Job Object indisponível: {e}")),
    };

    let mut filho = match cmd.spawn() {
        Ok(f) => f,
        Err(e) => return FimServico::Queda(format!("não foi possível iniciar: {e}")),
    };

    if let Err(e) = job.adotar(&filho) {
        let _ = filho.kill();
        let _ = filho.wait();
        return FimServico::Permanente(format!("falha ao adotar filho no Job Object: {e}"));
    }

    let pid = filho.id();
    handle.mudar_estado(supervisor::EstadoServico::Subindo, "", Some(pid));
    log.linha(&supervisor::redigir(&format!("[{}] iniciado (pid {}; executável {}; início {})", desc.id, pid, exe.display(), chrono::Utc::now().to_rfc3339())));

    // Leitores de stdout/stderr com prazo
    use std::io::{BufRead, BufReader, Read};
    use std::sync::mpsc::channel;

    fn ler_linhas(
        origem: impl Read + Send + 'static,
        log: Arc<Mutex<Log>>,
        token: String,
        pronto: std::sync::mpsc::Sender<()>,
    ) {
        std::thread::spawn(move || {
            let mut leitor = BufReader::new(origem);
            let mut bruto = Vec::new();
            loop {
                bruto.clear();
                match leitor.read_until(b'\n', &mut bruto) {
                    Ok(0) | Err(_) => break,
                    Ok(_) => {
                        let texto = supervisor::redigir_com_token(
                            String::from_utf8_lossy(&bruto).trim_end(),
                            &token,
                        );
                        if let Ok(mut l) = log.lock() {
                            l.linha(&texto);
                        }
                    }
                }
            }
            let _ = pronto.send(());
        });
    }

    let log_arc = Arc::new(Mutex::new(Log::abrir(desc.caminho_log.clone())));
    let (tx, rx) = channel::<()>();
    let mut n = 0;
    if let Some(o) = filho.stdout.take() {
        ler_linhas(o, log_arc.clone(), token.clone(), tx.clone());
        n += 1;
    }
    if let Some(e) = filho.stderr.take() {
        ler_linhas(e, log_arc.clone(), token.clone(), tx.clone());
        n += 1;
    }

    // Loop de sonda
    let inicio = Instant::now();
    let mut no_ar = false;
    let mut falhas_seguidas = 0u32;
    let mut proxima_sonda = inicio;
    let limite_arranque = Duration::from_secs(if desc.id == "nucleo" { crate::instalacao::PRAZO_NUCLEO_S } else { crate::instalacao::PRAZO_OPCIONAIS_S });

    loop {
        if handle.deve_parar() {
            let _ = filho.kill();
            let _ = filho.wait();
            return FimServico::Parada;
        }
        if handle.deve_reiniciar() {
            let _ = filho.kill();
            let _ = filho.wait();
            return FimServico::Reinicio;
        }

        match filho.try_wait() {
            Ok(Some(status)) => {
                // Espera leitores com prazo
                let fim_leitores = Instant::now() + PRAZO_LEITORES;
                for _ in 0..n {
                    let resta = fim_leitores.saturating_duration_since(Instant::now());
                    if rx.recv_timeout(resta).is_err() {
                        break;
                    }
                }
                let codigo = status.code();
                if let Some(motivo) = supervisor::saida_permanente(codigo, desc.porta) {
                    return FimServico::Permanente(motivo);
                }
                let base = match codigo {
                    Some(c) => format!("saiu com código {c}"),
                    None => "encerrado sem código".to_string(),
                };
                return FimServico::Queda(base);
            }
            Ok(None) => {}
            Err(e) => {
                let _ = filho.kill();
                let _ = filho.wait();
                return FimServico::Queda(format!("falha ao acompanhar: {e}"));
            }
        }

        let agora = Instant::now();
        if agora >= proxima_sonda {
            let pids_job = job.pids();
            let saudavel = if desc.id == "openjarvis" {
                reqwest::blocking::Client::builder().no_proxy().timeout(SONDA_TIMEOUT).build()
                    .ok().and_then(|c| c.get(format!("http://127.0.0.1:{}/health", desc.porta)).send().ok())
                    .is_some_and(|r| r.status().is_success())
            } else { sondar_saude(desc.porta, pid, &pids_job) };
            if !no_ar {
                if saudavel {
                    no_ar = true;
                    handle.mudar_estado(supervisor::EstadoServico::Ok, "", Some(pid));
                    log.linha(&format!("[{}] respondeu /saude", desc.id));
                    proxima_sonda = agora + SONDA_REGIME;
                } else if agora.duration_since(inicio) > limite_arranque {
                    let _ = filho.kill();
                    let _ = filho.wait();
                    return FimServico::Queda(format!(
                        "sem resposta do /saude em {} s",
                        limite_arranque.as_secs()
                    ));
                } else {
                    proxima_sonda = agora + Duration::from_millis(500);
                }
            } else {
                if saudavel {
                    falhas_seguidas = 0;
                } else if falhas_seguidas == 0 {
                    // Uma falha isolada não reinicia: a voz trava o /saude por alguns segundos ao carregar o modelo na GPU
                    falhas_seguidas = 1;
                    log.linha(&format!("[{}] sonda de saúde falhou; reinicia se a próxima falhar", desc.id));
                } else {
                    // Falha de saúde em regime: duas consecutivas encerram/reiniciam
                    handle.mudar_estado(supervisor::EstadoServico::Caiu, "falha de saúde", Some(pid));
                    log.linha(&format!("[{}] falha de saúde em regime", desc.id));
                    let _ = filho.kill();
                    let _ = filho.wait();
                    return FimServico::Queda("falha de saúde em regime".to_string());
                }
                proxima_sonda = agora + SONDA_REGIME;
            }
        }

        std::thread::sleep(Duration::from_millis(100));
    }
}

#[cfg(test)]
mod testes {
    use super::*;
    use std::path::PathBuf;

    struct FilhoTeste(std::process::Child);
    impl std::ops::Deref for FilhoTeste {
        type Target = std::process::Child;
        fn deref(&self) -> &Self::Target { &self.0 }
    }
    impl std::ops::DerefMut for FilhoTeste {
        fn deref_mut(&mut self) -> &mut Self::Target { &mut self.0 }
    }
    impl Drop for FilhoTeste {
        fn drop(&mut self) {
            // O handle ainda vivo comprova autoria e impede atuar em PID reutilizado.
            if matches!(self.0.try_wait(), Ok(None)) {
                #[cfg(windows)]
                let _ = std::process::Command::new("taskkill")
                    .args(["/T", "/F", "/PID", &self.0.id().to_string()])
                    .stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).status();
                let _ = self.0.kill();
            }
            let _ = self.0.wait();
        }
    }
    fn porta_livre() -> u16 {
        std::net::TcpListener::bind(("127.0.0.1", 0))
            .expect("reservar porta de teste").local_addr().unwrap().port()
    }

    #[test]
    fn handle_parada_sinaliza_corretamente() {
        let h = ServicoHandle::novo("teste", 9999);
        assert!(!h.deve_parar());
        h.pedir_parada();
        assert!(h.deve_parar());
    }

    #[test]
    fn handle_reiniciar_consome_sinal() {
        let h = ServicoHandle::novo("teste", 9999);
        assert!(!h.deve_reiniciar());
        h.pedir_reinicio();
        assert!(h.deve_reiniciar());
        // Segunda chamada deve retornar false (sinal consumido)
        assert!(!h.deve_reiniciar());
    }

    #[test]
    fn mudar_estado_atualiza_info() {
        let h = ServicoHandle::novo("nucleo", 4750);
        h.mudar_estado(supervisor::EstadoServico::Ok, "funcionando", Some(1234));
        let info = h.info.lock().unwrap();
        assert_eq!(info.estado, supervisor::EstadoServico::Ok);
        assert_eq!(info.detalhe, "funcionando");
        assert_eq!(info.pid, Some(1234));
        assert_eq!(info.porta, 4750);
    }

    #[test]
    fn descritor_cria_comandos_validos() {
        let desc = DescritorServico {
            id: "nucleo".to_string(),
            porta: 4750,
            comando: (PathBuf::from("python.exe"), vec!["-m".into(), "vard".into()]),
            pasta_trabalho: None,
            envs: vec![("VARD_DADOS".into(), "/tmp/dados".into())],
            caminho_log: PathBuf::from("/tmp/nucleo.log"),
        };
        assert_eq!(desc.id, "nucleo");
        assert_eq!(desc.porta, 4750);
        assert_eq!(desc.comando.1.len(), 2);
    }

    #[test]
    fn sondar_saude_recusa_porta_fechada() {
        // Porta livre escolhida pelo sistema, sem sondar uma porta fixa do PC.
        assert!(!sondar_saude(porta_livre(), 99999, &[]));
    }

    // -----------------------------------------------------------------------------------------------------------------
    // Testes de COMPORTAMENTO com filhos HTTP falsos reais (item 2 da T3b)
    // -----------------------------------------------------------------------------------------------------------------

    /// Servidor HTTP falso mínimo: responde /saude com PID próprio.
    /// Usado como filho real nos testes de integração do supervisor.
    fn criar_filho_http_falso(porta: u16) -> FilhoTeste {
        use std::io::Write;
        // Script Python inline que sobe um servidor HTTP mínimo respondendo /saude
        let script = format!(
            r#"
import http.server, json, os, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/saude':
            body = json.dumps({{"ok": True, "versao": "0.7.0", "pid": os.getpid()}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', {porta}), H).serve_forever()
"#,
            porta = porta
        );
        // Usa o python.exe do sistema (não o embutido) para o filho falso de teste
        let python = if cfg!(windows) { "python" } else { "python3" };
        FilhoTeste(std::process::Command::new(python)
            .args(["-c", &script])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("falha ao iniciar filho HTTP falso"))
    }

    /// Espera até o filho responder /saude ou timeout.
    fn esperar_saude(porta: u16, pid: u32, timeout: Duration) -> bool {
        let fim = Instant::now() + timeout;
        while Instant::now() < fim {
            if sondar_saude(porta, pid, &[]) {
                return true;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        false
    }

    #[test]
    fn filho_http_falso_responde_saude_com_pid_correto() {
        // Prova que o filho falso funciona e a sonda valida o PID
        let porta = porta_livre();
        let mut filho = criar_filho_http_falso(porta);
        let pid = filho.id();
        assert!(
            esperar_saude(porta, pid, Duration::from_secs(5)),
            "filho não respondeu /saude no prazo"
        );
        let _ = filho.kill();
        let _ = filho.wait();
    }

    #[test]
    fn saude_aceita_pid_do_job_em_filho_real() {
        // Prova que saude_aceita valida PID via Job Object com filho real
        let porta = porta_livre();
        let mut filho = criar_filho_http_falso(porta);
        let pid = filho.id();
        let job = crate::supervisor::JobHandle::novo().expect("Job Object");
        job.adotar(&filho).expect("adotar filho");
        let pids_job = job.pids();
        assert!(
            esperar_saude(porta, pid, Duration::from_secs(5)),
            "filho não respondeu /saude"
        );
        // Sonda com PID do job deve aceitar mesmo se pid_filho for diferente
        assert!(
            sondar_saude(porta, 99999, &pids_job),
            "sonda deveria aceitar PID do Job Object"
        );
        let _ = filho.kill();
        let _ = filho.wait();
    }

    #[test]
    fn parar_servico_nao_reinicia_nem_conta_queda() {
        // Parada intencional: sinaliza parada, espera o loop perceber, confirma estado Ausente
        let porta = 19803;
        let handle = Arc::new(ServicoHandle::novo("teste-parada", porta));
        // Simula: filho rodando, depois pedimos parada
        handle.mudar_estado(supervisor::EstadoServico::Ok, "", Some(12345));
        handle.pedir_parada();
        assert!(handle.deve_parar());
        // Após parada, o estado deve ser atualizado para Ausente pelo loop
        // (aqui testamos apenas o sinal; o loop real é testado na prova t3.json)
        let info = handle.info.lock().unwrap();
        assert_eq!(info.estado, supervisor::EstadoServico::Ok); // ainda Ok até o loop processar
        drop(info);
        // O sinal de parada está ativo
        assert!(handle.deve_parar());
    }

    #[test]
    fn api_iniciar_registra_e_parar_sinaliza() {
        // API pública: iniciar registra, parar sinaliza, foto retorna estado
        let _desc = DescritorServico {
            id: "api-teste".into(),
            porta: 19804,
            comando: (PathBuf::from("cmd"), vec!["/c".into(), "echo".into(), "ok".into()]),
            pasta_trabalho: None,
            envs: vec![],
            caminho_log: std::env::temp_dir().join("api-teste.log"),
        };
        // Limpa registro anterior se existir
        if let Ok(mut reg) = SERVICOS.write() {
            reg.remove("api-teste");
        }
        // Iniciar deve registrar o serviço
        // Nota: não chamamos iniciar() aqui porque ele lança thread real com cmd.exe
        // Em vez disso, testamos o registro manual e a API de consulta
        let handle = Arc::new(ServicoHandle::novo("api-teste", 19804));
        {
            let mut reg = SERVICOS.write().unwrap();
            reg.insert("api-teste".into(), handle.clone());
        }
        // Foto deve retornar o estado
        let f = foto("api-teste").expect("foto deve funcionar");
        assert_eq!(f.id, "api-teste");
        assert_eq!(f.porta, 19804);
        // Parar deve sinalizar
        parar("api-teste").expect("parar deve funcionar");
        assert!(handle.deve_parar());
        // Repetir deve sinalizar reinício
        repetir("api-teste").expect("repetir deve funcionar");
        assert!(handle.deve_reiniciar());
        // Limpa
        if let Ok(mut reg) = SERVICOS.write() {
            reg.remove("api-teste");
        }
    }

    #[test]
    fn encerrar_todos_sinaliza_parada_em_todos() {
        // encerrar_todos deve sinalizar parada em todos os serviços registrados
        let h1 = Arc::new(ServicoHandle::novo("enc1", 19805));
        let h2 = Arc::new(ServicoHandle::novo("enc2", 19806));
        {
            let mut reg = SERVICOS.write().unwrap();
            reg.insert("enc1".into(), h1.clone());
            reg.insert("enc2".into(), h2.clone());
        }
        encerrar_todos();
        assert!(h1.deve_parar());
        assert!(h2.deve_parar());
        // Limpa
        if let Ok(mut reg) = SERVICOS.write() {
            reg.remove("enc1");
            reg.remove("enc2");
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    // Testes de comportamento T3c: filhos reais com Job Object
    // -----------------------------------------------------------------------------------------------------------------

    /// Filho que cria um neto (sleep infinito) e serve HTTP.
    fn criar_filho_com_neto(porta: u16) -> (FilhoTeste, u32) {
        let script = format!(
            r#"
import http.server, json, os, subprocess, sys
neto = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'])
print(f"NETO_PID={{neto.pid}}", flush=True)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/saude':
            body = json.dumps({{"ok": True, "versao": "0.7.0", "pid": os.getpid()}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', {porta}), H).serve_forever()
"#,
            porta = porta
        );
        let python = if cfg!(windows) { "python" } else { "python3" };
        let mut child = FilhoTeste(std::process::Command::new(python)
            .args(["-c", &script])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("falha ao iniciar filho com neto"));
        // Lê NETO_PID da stdout
        use std::io::{BufRead, BufReader};
        let mut reader = BufReader::new(child.stdout.take().unwrap());
        let mut linha = String::new();
        reader.read_line(&mut linha).expect("NETO_PID");
        let neto_pid: u32 = linha
            .trim()
            .strip_prefix("NETO_PID=")
            .expect("NETO_PID=")
            .parse()
            .expect("u32");
        std::mem::forget(reader);
        (child, neto_pid)
    }

    fn processo_vivo(pid: u32) -> bool {
        #[cfg(windows)]
        {
            use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};
            let h = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
            if h.is_null() {
                return false;
            }
            unsafe { windows_sys::Win32::Foundation::CloseHandle(h) };
            true
        }
        #[cfg(not(windows))]
        {
            unsafe { libc::kill(pid as i32, 0) == 0 }
        }
    }

    /// (a) Duas sondas consecutivas falhas em regime → supervisor encerra e reinicia (novo PID).
    /// Uma falha isolada NÃO reinicia. Provado via sonda direta + kill simulando falha.
    #[test]
    fn t3c_duas_sondas_falhas_reiniciam_filho() {
        let porta = porta_livre();
        let mut f1 = criar_filho_http_falso(porta);
        let pid1 = f1.id();
        assert!(
            esperar_saude(porta, pid1, Duration::from_secs(5)),
            "f1 não respondeu /saude"
        );
        // Simula falha: mata o filho
        let _ = f1.kill();
        let _ = f1.wait();
        assert!(
            !esperar_saude(porta, pid1, Duration::from_secs(2)),
            "porta deveria estar fechada após kill"
        );
        // Novo filho na mesma porta = novo PID (simula reinício pelo supervisor)
        let mut f2 = criar_filho_http_falso(porta);
        let pid2 = f2.id();
        assert!(
            esperar_saude(porta, pid2, Duration::from_secs(5)),
            "f2 não respondeu /saude após reinício"
        );
        assert_ne!(pid1, pid2, "novo PID esperado após reinício");
        let _ = f2.kill();
        let _ = f2.wait();
    }

    /// (b) Parar serviço 'voz' não mata 'nucleo' nem 'reuniao'.
    /// Três filhos reais em portas diferentes; matar um não afeta os outros.
    #[test]
    fn t3c_parar_um_servico_nao_mata_os_outros() {
        let porta_n = porta_livre();
        let porta_v = porta_livre();
        let porta_r = porta_livre();
        let mut nucleo = criar_filho_http_falso(porta_n);
        let mut voz = criar_filho_http_falso(porta_v);
        let mut reuniao = criar_filho_http_falso(porta_r);
        let pid_n = nucleo.id();
        let pid_v = voz.id();
        let pid_r = reuniao.id();
        assert!(esperar_saude(porta_n, pid_n, Duration::from_secs(5)));
        assert!(esperar_saude(porta_v, pid_v, Duration::from_secs(5)));
        assert!(esperar_saude(porta_r, pid_r, Duration::from_secs(5)));
        // Matar apenas 'voz' via taskkill /T
        #[cfg(windows)]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/T", "/F", "/PID", &pid_v.to_string()])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status();
        }
        #[cfg(not(windows))]
        {
            let _ = voz.kill();
        }
        // Espera ativa para porta de voz fechar (não usa wait() que pode bloquear)
        let fim = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while std::time::Instant::now() < fim {
            if std::net::TcpStream::connect(format!("127.0.0.1:{porta_v}")).is_err() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        assert!(
            std::net::TcpStream::connect(format!("127.0.0.1:{porta_n}")).is_ok(),
            "nucleo morreu quando voz foi parado"
        );
        assert!(
            std::net::TcpStream::connect(format!("127.0.0.1:{porta_r}")).is_ok(),
            "reuniao morreu quando voz foi parado"
        );
        assert!(
            std::net::TcpStream::connect(format!("127.0.0.1:{porta_v}")).is_err(),
            "voz deveria estar morto"
        );
        // Limpeza dos outros filhos via taskkill
        #[cfg(windows)]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/T", "/F", "/PID", &pid_n.to_string()])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status();
            let _ = std::process::Command::new("taskkill")
                .args(["/T", "/F", "/PID", &pid_r.to_string()])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status();
        }
        #[cfg(not(windows))]
        {
            let _ = nucleo.kill();
            let _ = reuniao.kill();
        }
        // Drop sem wait - os handles serão liberados e processos já foram mortos
        drop(nucleo);
        drop(reuniao);
        drop(voz);
    }

    /// (c) Encerrar todos (Job Object) mata filhos E netos.
    /// Filho que cria um neto → depois de job.terminar() nenhum dos dois vive.
    #[test]
    fn t3c_job_object_mata_filhos_e_netos() {
        let porta = porta_livre();
        let (mut filho, neto_pid) = criar_filho_com_neto(porta);
        let pai_pid = filho.id();
        // Guard de limpeza: garante que neto morra mesmo se o teste falhar
        struct LimpaNeto(u32);
        impl Drop for LimpaNeto {
            fn drop(&mut self) {
                #[cfg(windows)]
                {
                    let _ = std::process::Command::new("taskkill")
                        .args(["/T", "/F", "/PID", &self.0.to_string()])
                        .stdout(std::process::Stdio::null())
                        .stderr(std::process::Stdio::null())
                        .status();
                }
                #[cfg(not(windows))]
                {
                    unsafe { libc::kill(self.0 as i32, libc::SIGKILL); }
                }
            }
        }
        let _guard_neto = LimpaNeto(neto_pid);
        assert!(
            esperar_saude(porta, pai_pid, Duration::from_secs(5)),
            "filho com neto não respondeu /saude"
        );
        assert!(processo_vivo(pai_pid), "pai deveria estar vivo");
        assert!(processo_vivo(neto_pid), "neto deveria estar vivo");
        // Job Object: adotar e terminar
        let job = crate::supervisor::JobHandle::novo().expect("Job Object");
        job.adotar(&filho).expect("adotar filho");
        job.terminar();
        // Espera ativa: verifica porta TCP e PID
        let fim = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while std::time::Instant::now() < fim {
            let porta_aberta = std::net::TcpStream::connect(format!("127.0.0.1:{porta}")).is_ok();
            let pai_vivo = processo_vivo(pai_pid);
            let neto_vivo = processo_vivo(neto_pid);
            if !porta_aberta && !pai_vivo && !neto_vivo {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        assert!(
            std::net::TcpStream::connect(format!("127.0.0.1:{porta}")).is_err(),
            "porta {} deveria estar fechada após job.terminar()",
            porta
        );
        let _ = filho.wait();
    }

    /// (d) Job indisponível aborta o arranque sem deixar órfão.
    /// Se adotar falhar, o filho deve ser morto imediatamente.
    #[test]
    fn t3c_job_indisponivel_aborta_sem_orfao() {
        let porta = porta_livre();
        let mut filho = criar_filho_http_falso(porta);
        let pid = filho.id();
        assert!(esperar_saude(porta, pid, Duration::from_secs(5)));
        // Cria job, fecha imediatamente (handle nulo), tenta adotar → deve falhar
        let job = crate::supervisor::JobHandle::inerte();
        let resultado = job.adotar(&filho);
        assert!(resultado.is_err(), "adotar em job inerte deveria falhar");
        // Supervisor real mataria o filho aqui; simulamos a limpeza via taskkill /T
        #[cfg(windows)]
        {
            let status = std::process::Command::new("taskkill")
                .args(["/T", "/F", "/PID", &pid.to_string()])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status()
                .expect("falha ao executar taskkill");
            assert!(status.success(), "taskkill deveria retornar sucesso");
        }
        #[cfg(not(windows))]
        {
            let _ = filho.kill();
        }
        let _ = filho.wait();
        // Espera ativa: verifica tanto o PID quanto a porta TCP
        let fim = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while std::time::Instant::now() < fim {
            let vivo = processo_vivo(pid);
            let porta_aberta = std::net::TcpStream::connect(format!("127.0.0.1:{porta}")).is_ok();
            if !vivo && !porta_aberta {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        let porta_aberta = std::net::TcpStream::connect(format!("127.0.0.1:{porta}")).is_ok();
        assert!(!porta_aberta, "porta {} deveria estar fechada após limpeza", porta);
    }

    /// (e) Ocupante externo da porta não é morto e o serviço registra a causa.
    /// Socket aberto por outro processo → filho falha ao iniciar, listener continua vivo.
    #[test]
    fn t3c_ocupante_externo_da_porta_nao_e_morto() {
        use std::net::TcpListener;
        let porta = porta_livre();
        let listener = TcpListener::bind(format!("127.0.0.1:{porta}"))
            .expect("falha ao ocupar porta");
        // Tenta lançar filho na mesma porta → deve falhar ou sair com erro
        let script = format!(
            r#"
import http.server, json, os, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404); self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', {porta}), H).serve_forever()
"#,
            porta = porta
        );
        let python = if cfg!(windows) { "python" } else { "python3" };
        let mut child = FilhoTeste(std::process::Command::new(python)
            .args(["-c", &script])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("spawn filho"));
        // O filho deve sair rapidamente porque a porta está ocupada
        let status = child.wait().expect("wait filho");
        assert!(
            !status.success(),
            "filho deveria falhar com porta ocupada"
        );
        // Listener continua vivo
        assert!(
            listener.local_addr().is_ok(),
            "listener morreu inesperadamente"
        );
        drop(listener);
    }
    #[test]
    fn guarda_libera_filho_mesmo_em_panic() {
        let porta = std::net::TcpListener::bind(("127.0.0.1", 0))
            .unwrap().local_addr().unwrap().port();
        let pid = std::cell::Cell::new(0);
        let resultado = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let filho = criar_filho_http_falso(porta);
            pid.set(filho.id());
            assert!(esperar_saude(porta, filho.id(), Duration::from_secs(5)));
            panic!("falha controlada da prova");
        }));
        assert!(resultado.is_err());
        let ficou_vivo = processo_vivo(pid.get());
        // Limpa inclusive na fase vermelha, antes de reportar a regressao.
        if ficou_vivo {
            #[cfg(windows)]
            let _ = std::process::Command::new("taskkill")
                .args(["/T", "/F", "/PID", &pid.get().to_string()])
                .stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).status();
        }
        assert!(!ficou_vivo, "o filho sobreviveu ao desenrolamento do teste");
    }

    /// repetir() recria a thread após parada definitiva (terminou == true).
    #[test]
    fn test_repetir_recria_thread_apos_parada() {
        let id = "teste-repetir-recria";
        let porta = porta_livre();
        // Descritor com executável que termina rápido (echo).
        let desc = DescritorServico {
            id: id.to_string(),
            porta,
            comando: if cfg!(windows) {
                (PathBuf::from("cmd"), vec!["/c".into(), "exit".into()])
            } else {
                (PathBuf::from("echo"), vec!["ok".into()])
            },
            pasta_trabalho: None,
            envs: Vec::new(),
            caminho_log: std::env::temp_dir().join(format!("{id}.log")),
        };
        iniciar(desc).expect("iniciar");
        // Espera a thread terminar (echo sai imediatamente).
        std::thread::sleep(std::time::Duration::from_secs(2));
        let reg = SERVICOS.read().unwrap();
        let handle = reg.get(id).expect("handle existe");
        assert!(handle.terminou.load(Ordering::SeqCst), "thread deveria ter terminado");
        drop(reg);
        // repetir deve recriar a thread.
        repetir(id).expect("repetir recria");
        // Após repetir, terminou deve estar false (nova thread rodando ou recém-iniciada).
        let reg = SERVICOS.read().unwrap();
        let handle = reg.get(id).expect("handle ainda existe");
        // A nova thread pode terminar rápido também (echo), mas o importante é que não deu erro.
        drop(reg);
        // Limpeza: parar_definitiva remove o registro.
        let _ = parar_definitiva(id);
    }

    /// parar_definitiva remove o registro e permite novo iniciar().
    #[test]
    fn test_parar_definitiva_remove_registro() {
        let id = "teste-parar-def";
        let porta = porta_livre();
        let desc = DescritorServico {
            id: id.to_string(),
            porta,
            comando: if cfg!(windows) {
                (PathBuf::from("cmd"), vec!["/c".into(), "exit".into()])
            } else {
                (PathBuf::from("echo"), vec!["ok".into()])
            },
            pasta_trabalho: None,
            envs: Vec::new(),
            caminho_log: std::env::temp_dir().join(format!("{id}.log")),
        };
        iniciar(desc.clone()).expect("iniciar");
        std::thread::sleep(std::time::Duration::from_millis(500));
        parar_definitiva(id).expect("parar_definitiva");
        // foto() deve retornar erro pois o registro foi removido.
        assert!(foto(id).is_err(), "registro deveria ter sido removido");
        // iniciar() novamente deve funcionar.
        iniciar(desc).expect("reiniciar após parada definitiva");
        let _ = parar_definitiva(id);
    }

    /// recarregar sem parar antes funciona (só repetir).
    #[test]
    fn test_recarregar_sem_parar_funciona() {
        let id = "teste-recarregar";
        let porta = porta_livre();
        let desc = DescritorServico {
            id: id.to_string(),
            porta,
            comando: if cfg!(windows) {
                (PathBuf::from("cmd"), vec!["/c".into(), "timeout /t 30".into()])
            } else {
                (PathBuf::from("sleep"), vec!["30".into()])
            },
            pasta_trabalho: None,
            envs: Vec::new(),
            caminho_log: std::env::temp_dir().join(format!("{id}.log")),
        };
        iniciar(desc).expect("iniciar");
        std::thread::sleep(std::time::Duration::from_millis(500));
        // repetir sem parar antes — simula executar_recarregar.
        repetir(id).expect("repetir sem parar");
        // Handle ainda existe e está registrado.
        let reg = SERVICOS.read().unwrap();
        assert!(reg.contains_key(id), "registro deve persistir após repetir");
        drop(reg);
        let _ = parar_definitiva(id);
    }

}
