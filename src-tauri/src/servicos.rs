//! Supervisor generalizado de serviços: lança, sonda, reinicia e encerra filhos com Job Object próprio.
//! Cada serviço tem seu próprio Job Object, log e máquina de recuo.
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::supervisor::{
    self, Decisao, Log, SONDA_REGIME, SONDA_TIMEOUT, PRAZO_LEITORES,
};

/// Descritor de um serviço gerenciado pelo supervisor.
#[derive(Debug, Clone)]
pub struct DescritorServico {
    /// Identificador único do serviço (ex: "nucleo", "voz").
    pub id: String,
    /// Porta HTTP onde o serviço responde /saude.
    pub porta: u16,
    /// Comando para lançar o serviço (exe + args).
    pub comando: (PathBuf, Vec<String>),
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
    parar: AtomicBool,
    reiniciar: AtomicBool,
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
            parar: AtomicBool::new(false),
            reiniciar: AtomicBool::new(false),
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
    use crate::supervisor::variaveis_tiradas;

    handle.mudar_estado(supervisor::EstadoServico::Subindo, "", None);

    let (exe, args) = &desc.comando;
    if !exe.exists() {
        return FimServico::Permanente(format!("executável não encontrado: {}", exe.display()));
    }

    let token = supervisor::token_novo();
    let mut cmd = Command::new(exe);
    cmd.args(args)
        .envs(desc.envs.iter().map(|(k, v)| (k.as_str(), v.as_str())))
        .env("VARD_TOKEN", &token)
        .env("VARD_PORTA", desc.porta.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    for v in variaveis_tiradas() {
        cmd.env_remove(v);
    }

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
    log.linha(&format!("[{}] iniciado (pid {})", desc.id, pid));

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
    let mut proxima_sonda = inicio;
    let limite_arranque = Duration::from_secs(15);

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
        let saudavel = sondar_saude(desc.porta, pid, &pids_job);
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
                    // Saúde contínua: nada a fazer além de manter o intervalo
                } else {
                    // Falha de saúde em regime: duas consecutivas encerram/reiniciam
                    // Por enquanto, marca como caiu e deixa o loop externo decidir
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
            envs: vec![("VARD_DADOS".into(), "/tmp/dados".into())],
            caminho_log: PathBuf::from("/tmp/nucleo.log"),
        };
        assert_eq!(desc.id, "nucleo");
        assert_eq!(desc.porta, 4750);
        assert_eq!(desc.comando.1.len(), 2);
    }

    #[test]
    fn sondar_saude_recusa_porta_fechada() {
        // Porta que ninguém está ouvindo deve retornar false
        assert!(!sondar_saude(59999, 99999, &[]));
    }
}