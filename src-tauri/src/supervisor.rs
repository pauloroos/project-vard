//! Regras puras do supervisor de serviços: recuo, log com rotação, sanitização e saúde.
//! Sem processo, sem rede, sem relógio próprio — tudo é injetado ou puro.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::LazyLock;
use std::time::{Duration, Instant};

use regex::Regex;
use serde::Serialize;

pub const RECUO_S: [u64; 3] = [1, 3, 10];
pub const JANELA_QUEDAS: Duration = Duration::from_secs(60);
pub const QUEDAS_PARA_DESISTIR: usize = 3;
pub const SAIDA_SEM_TOKEN: i32 = 2;
pub const SAIDA_PORTA_OCUPADA: i32 = 3;
pub const LOG_MAX_BYTES: u64 = 5 * 1024 * 1024;

/// Tempo de saúde seguida que zera a sequência de recuo.
const SAUDE_PARA_ZERAR: Duration = Duration::from_secs(60);

/// Sonda de regime: intervalo entre sondas quando o serviço está saudável.
pub const SONDA_REGIME: Duration = Duration::from_secs(2);

/// Timeout da sonda HTTP.
pub const SONDA_TIMEOUT: Duration = Duration::from_secs(1);

/// Prazo para esperar os leitores de stdout/stderr depois que o filho sai.
pub const PRAZO_LEITORES: Duration = Duration::from_secs(2);

// Re-exporta JobHandle para uso em servicos.rs
#[cfg(windows)]
pub use job::JobHandle;
#[cfg(not(windows))]
pub use job_stub::JobHandle;

// ---------------------------------------------------------------------------------------------------------------------
// Job Object (único lugar com `unsafe`)
// ---------------------------------------------------------------------------------------------------------------------
#[cfg(windows)]
mod job {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectBasicProcessIdList,
        JobObjectExtendedLimitInformation, QueryInformationJobObject, SetInformationJobObject,
        TerminateJobObject, JOBOBJECT_BASIC_PROCESS_ID_LIST,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    /// Job Object com KILL_ON_JOB_CLOSE: quando o app morre, o Windows mata o serviço e os netos.
    pub struct JobHandle {
        handle: HANDLE,
    }

    // SAFETY: o HANDLE de um Job Object é um identificador do kernel, válido em qualquer thread.
    unsafe impl Send for JobHandle {}
    unsafe impl Sync for JobHandle {}

    const ERROR_MORE_DATA: i32 = 234;
    const CAPACIDADE_PIDS: usize = 64;

    impl JobHandle {
        pub fn novo() -> Result<JobHandle, String> {
            let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
            if handle.is_null() {
                return Err(format!("CreateJobObjectW: {}", std::io::Error::last_os_error()));
            }
            let job = JobHandle { handle };
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = unsafe {
                SetInformationJobObject(
                    job.handle,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const core::ffi::c_void,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                )
            };
            if ok == 0 {
                return Err(format!(
                    "SetInformationJobObject: {}",
                    std::io::Error::last_os_error()
                ));
            }
            Ok(job)
        }

        pub fn inerte() -> JobHandle {
            JobHandle {
                handle: std::ptr::null_mut(),
            }
        }

        pub fn adotar(&self, filho: &Child) -> Result<(), String> {
            if self.handle.is_null() {
                return Err("Job Object indisponível".to_string());
            }
            let ok = unsafe { AssignProcessToJobObject(self.handle, filho.as_raw_handle() as HANDLE) };
            if ok == 0 {
                return Err(format!(
                    "AssignProcessToJobObject: {}",
                    std::io::Error::last_os_error()
                ));
            }
            Ok(())
        }

        pub fn terminar(&self) {
            if self.handle.is_null() {
                return;
            }
            unsafe {
                TerminateJobObject(self.handle, 1);
            }
        }

        pub fn pids(&self) -> Vec<u32> {
            if self.handle.is_null() {
                return Vec::new();
            }
            let mut buf = vec![0usize; 1 + CAPACIDADE_PIDS];
            let bytes = (buf.len() * std::mem::size_of::<usize>()) as u32;
            let ok = unsafe {
                QueryInformationJobObject(
                    self.handle,
                    JobObjectBasicProcessIdList,
                    buf.as_mut_ptr() as *mut core::ffi::c_void,
                    bytes,
                    std::ptr::null_mut(),
                )
            };
            if ok == 0 && std::io::Error::last_os_error().raw_os_error() != Some(ERROR_MORE_DATA) {
                return Vec::new();
            }
            let base = buf.as_ptr() as *const u8;
            let desloc_n =
                std::mem::offset_of!(JOBOBJECT_BASIC_PROCESS_ID_LIST, NumberOfProcessIdsInList);
            let desloc_lista =
                std::mem::offset_of!(JOBOBJECT_BASIC_PROCESS_ID_LIST, ProcessIdList);
            unsafe {
                let n = (std::ptr::read_unaligned(base.add(desloc_n) as *const u32) as usize)
                    .min(CAPACIDADE_PIDS);
                (0..n)
                    .map(|i| {
                        std::ptr::read_unaligned(
                            base.add(desloc_lista + i * std::mem::size_of::<usize>())
                                as *const usize,
                        ) as u32
                    })
                    .collect()
            }
        }
    }

    impl Drop for JobHandle {
        fn drop(&mut self) {
            if !self.handle.is_null() {
                unsafe {
                    CloseHandle(self.handle);
                }
            }
        }
    }
}

#[cfg(not(windows))]
mod job_stub {
    use std::process::Child;

    pub struct JobHandle;

    impl JobHandle {
        pub fn novo() -> Result<JobHandle, String> {
            Ok(JobHandle)
        }
        pub fn inerte() -> JobHandle {
            JobHandle
        }
        pub fn adotar(&self, _filho: &Child) -> Result<(), String> {
            Err("Job Object só existe no Windows".to_string())
        }
        pub fn terminar(&self) {}
        pub fn pids(&self) -> Vec<u32> {
            Vec::new()
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum EstadoServico {
    Subindo,
    Ok,
    Caiu,
    Desistiu,
    Ausente,
}

#[derive(Debug, PartialEq)]
pub enum Decisao {
    Esperar(Duration),
    Desistir(String),
}

/// Máquina de recuo com relógio injetável.
pub struct Recuo {
    quedas: Vec<Instant>,
    seguidas: usize,
    saudavel_desde: Option<Instant>,
}

impl Default for Recuo {
    fn default() -> Self {
        Self::new()
    }
}

impl Recuo {
    pub fn new() -> Self {
        Recuo {
            quedas: Vec::new(),
            seguidas: 0,
            saudavel_desde: None,
        }
    }

    /// Uma queda: limpa as que passaram da janela; 3 na janela = desistir; senão espera RECUO_S[seguidas-1].
    pub fn registrar_queda(&mut self, agora: Instant) -> Decisao {
        self.quedas.retain(|q| agora.saturating_duration_since(*q) <= JANELA_QUEDAS);
        self.quedas.push(agora);
        self.saudavel_desde = None;

        if self.quedas.len() >= QUEDAS_PARA_DESISTIR {
            return Decisao::Desistir(format!(
                "o serviço caiu {} vezes em menos de {} s",
                self.quedas.len(),
                JANELA_QUEDAS.as_secs()
            ));
        }

        self.seguidas += 1;
        let i = (self.seguidas - 1).min(RECUO_S.len() - 1);
        Decisao::Esperar(Duration::from_secs(RECUO_S[i]))
    }

    /// /saude ok: depois de 60 s seguidos de saúde, zera `seguidas`.
    pub fn registrar_saude(&mut self, agora: Instant) {
        let desde = *self.saudavel_desde.get_or_insert(agora);
        if agora.saturating_duration_since(desde) >= SAUDE_PARA_ZERAR {
            self.seguidas = 0;
        }
    }

    /// Uma sonda de /saude falhou: a sequência de "60 s seguidos" recomeça.
    pub fn registrar_falha_saude(&mut self) {
        self.saudavel_desde = None;
    }

    pub fn zerar(&mut self) {
        self.quedas.clear();
        self.seguidas = 0;
        self.saudavel_desde = None;
    }
}

/// Saída que não adianta repetir: Some(motivo). 2 = sem token; 3 = porta ocupada.
pub fn saida_permanente(codigo: Option<i32>, porta: u16) -> Option<String> {
    match codigo {
        Some(SAIDA_SEM_TOKEN) => Some("o serviço não recebeu o token (erro do app)".to_string()),
        Some(SAIDA_PORTA_OCUPADA) => Some(format!("porta {porta} ocupada por outro programa")),
        _ => None,
    }
}

/// 32 bytes aleatórios do sistema, em hexadecimal (64 caracteres).
pub fn token_novo() -> String {
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).expect("gerador aleatório do sistema indisponível");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn precisa_girar(tamanho: u64) -> bool {
    tamanho > LOG_MAX_BYTES
}

/// Variáveis de ambiente Python que devem ser removidas ao lançar filhos.
pub fn variaveis_tiradas() -> &'static [&'static str] {
    &["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "PYTHONSTARTUP"]
}

/// `{"ok":true,"versao":"...","pid":N}` com N == pid do filho ou N em `pids_do_job`.
pub fn saude_aceita(corpo: &str, pid_filho: u32, pids_do_job: &[u32]) -> bool {
    let Ok(v) = serde_json::from_str::<serde_json::Value>(corpo) else {
        return false;
    };
    if v.get("ok").and_then(|x| x.as_bool()) != Some(true) {
        return false;
    }
    if !v.get("versao").is_some_and(|x| x.is_string()) {
        return false;
    }
    let Some(pid) = v.get("pid").and_then(|x| x.as_u64()) else {
        return false;
    };
    pid == u64::from(pid_filho) || pids_do_job.iter().any(|p| u64::from(*p) == pid)
}

/// Última linha não vazia, sem caracteres de controle, até 200 caracteres.
pub fn ultima_linha(texto: &str) -> String {
    let linha = texto
        .lines()
        .rev()
        .map(|l| l.trim())
        .find(|l| !l.is_empty())
        .unwrap_or("");
    linha.chars().filter(|c| !c.is_control()).take(200).collect()
}

static PADROES: LazyLock<Vec<(Regex, &'static str)>> = LazyLock::new(|| {
    [
        (r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}", "${1}***"),
        (r"\bsk-[A-Za-z0-9_-]{8,}", "sk-***"),
        (
            r#"(?i)\b((?:api[_-]?key|token|secret|password|senha)=)[^&\s"']+"#,
            "${1}***",
        ),
        (
            r#"(?i)(x-vard-token["']?\s*[:=]\s*["']?)[^"'\s,}]+"#,
            "${1}***",
        ),
    ]
    .into_iter()
    .filter_map(|(p, t)| Regex::new(p).ok().map(|r| (r, t)))
    .collect()
});

/// Tira segredos de uma linha de log antes de gravar.
pub fn redigir(texto: &str) -> String {
    let mut saida = texto.to_string();
    for (re, troca) in PADROES.iter() {
        saida = re.replace_all(&saida, *troca).into_owned();
    }
    saida
}

/// Como `redigir`, e antes troca o token do arranque atual (valor literal) por `***`.
pub fn redigir_com_token(texto: &str, token: &str) -> String {
    if token.is_empty() {
        return redigir(texto);
    }
    redigir(&texto.replace(token, "***"))
}

// ---------------------------------------------------------------------------------------------------------------------
// Log com rotação
// ---------------------------------------------------------------------------------------------------------------------
pub struct Log {
    caminho: PathBuf,
    arquivo: Option<File>,
    tamanho: u64,
}

impl Log {
    pub fn abrir(caminho: PathBuf) -> Log {
        if let Some(pai) = caminho.parent() {
            let _ = fs::create_dir_all(pai);
        }
        let arquivo = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&caminho)
            .ok();
        let tamanho = arquivo
            .as_ref()
            .and_then(|f| f.metadata().ok())
            .map(|m| m.len())
            .unwrap_or(0);
        Log {
            caminho,
            arquivo,
            tamanho,
        }
    }

    fn girar(&mut self) {
        self.arquivo = None;
        let velho = self.caminho.with_extension("log.1");
        let _ = fs::remove_file(&velho);
        let _ = fs::rename(&self.caminho, &velho);
        self.arquivo = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.caminho)
            .ok();
        self.tamanho = 0;
    }

    /// Grava uma linha já sanitizada pelo chamador. O supervisor/serviço é responsável
    /// por chamar `redigir` ou `redigir_com_token` antes de passar o texto aqui.
    pub fn linha(&mut self, texto: &str) {
        if precisa_girar(self.tamanho) {
            self.girar();
        }
        let saida = format!("{}\n", texto);
        if let Some(f) = self.arquivo.as_mut() {
            if f.write_all(saida.as_bytes()).is_ok() {
                self.tamanho += saida.len() as u64;
            }
        }
    }
}

#[cfg(test)]
mod testes {
    use super::*;
    use std::time::{Duration, Instant};

    fn base() -> Instant {
        use std::sync::OnceLock;
        static BASE: OnceLock<Instant> = OnceLock::new();
        *BASE.get_or_init(Instant::now)
    }

    fn t(s: u64) -> Instant {
        base() + Duration::from_secs(s)
    }

    #[test]
    fn primeira_queda_espera_1s() {
        let mut r = Recuo::new();
        assert_eq!(
            r.registrar_queda(t(0)),
            Decisao::Esperar(Duration::from_secs(1))
        );
    }

    #[test]
    fn segunda_queda_espera_3s() {
        let mut r = Recuo::new();
        r.registrar_queda(t(0));
        assert_eq!(
            r.registrar_queda(t(5)),
            Decisao::Esperar(Duration::from_secs(3))
        );
    }

    #[test]
    fn tres_quedas_em_60s_desiste() {
        let mut r = Recuo::new();
        r.registrar_queda(t(0));
        r.registrar_queda(t(10));
        assert!(matches!(
            r.registrar_queda(t(50)),
            Decisao::Desistir(_)
        ));
    }

    #[test]
    fn terceira_queda_espalhada_espera_10s() {
        let mut r = Recuo::new();
        r.registrar_queda(t(0));
        r.registrar_queda(t(40));
        assert_eq!(
            r.registrar_queda(t(90)),
            Decisao::Esperar(Duration::from_secs(10))
        );
    }

    #[test]
    fn saude_por_60s_zera_a_sequencia() {
        let mut r = Recuo::new();
        r.registrar_queda(t(0));
        r.registrar_saude(t(2));
        r.registrar_saude(t(70));
        assert_eq!(
            r.registrar_queda(t(200)),
            Decisao::Esperar(Duration::from_secs(1))
        );
    }

    #[test]
    fn falha_de_saude_recomeca_os_60s() {
        let mut r = Recuo::new();
        r.registrar_queda(t(0));
        r.registrar_saude(t(2));
        r.registrar_falha_saude();
        r.registrar_saude(t(70));
        assert_eq!(
            r.registrar_queda(t(200)),
            Decisao::Esperar(Duration::from_secs(3))
        );
    }

    #[test]
    fn saida_3_nao_insiste() {
        assert!(saida_permanente(Some(3), 4750).unwrap().contains("porta 4750 ocupada"));
        assert!(saida_permanente(Some(1), 4750).is_none());
        assert!(saida_permanente(None, 4750).is_none());
    }

    #[test]
    fn saida_2_nao_insiste() {
        assert!(saida_permanente(Some(2), 4750).is_some());
    }

    #[test]
    fn token_tem_64_hex_e_muda() {
        let a = token_novo();
        assert_eq!(a.len(), 64);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, token_novo());
    }

    #[test]
    fn saude_aceita_pid_do_filho() {
        assert!(saude_aceita(r#"{"ok":true,"versao":"0.7.0","pid":11}"#, 11, &[]));
    }

    #[test]
    fn saude_aceita_pid_do_job() {
        assert!(saude_aceita(r#"{"ok":true,"versao":"0.7.0","pid":42}"#, 11, &[11, 42]));
    }

    #[test]
    fn saude_recusa_pid_fora_dos_dois() {
        assert!(!saude_aceita(r#"{"ok":true,"versao":"0.7.0","pid":99}"#, 11, &[11, 42]));
    }

    #[test]
    fn saude_recusa_corpo_incompleto() {
        assert!(!saude_aceita(r#"{"ok":false,"versao":"0.7.0","pid":11}"#, 11, &[]));
        assert!(!saude_aceita(r#"{"versao":"0.7.0","pid":11}"#, 11, &[]));
        assert!(!saude_aceita(r#"{"ok":true,"pid":11}"#, 11, &[]));
        assert!(!saude_aceita("não é json", 11, &[]));
    }

    #[test]
    fn ultima_linha_ignora_vazias_e_corta() {
        assert_eq!(ultima_linha("a\n\nporta 4750 ocupada\n"), "porta 4750 ocupada");
    }

    #[test]
    fn gira_acima_de_5mb() {
        assert!(!precisa_girar(5 * 1024 * 1024));
        assert!(precisa_girar(5 * 1024 * 1024 + 1));
    }

    #[test]
    fn token_nu_sai_do_log() {
        let tok = "ab".repeat(32);
        let linha = format!("token={tok} bearer {tok}");
        let limpa = redigir_com_token(&linha, &tok);
        assert!(!limpa.contains(&tok), "token vazou: {limpa}");
        assert!(limpa.contains("***"));
    }

    #[test]
    fn segredo_generico_sai_do_log() {
        // Usa fragmentos que exercitam os padroes sem acionar o detector de vazamento do repo.
        let chave = format!("{}{}", "sk-", "A".repeat(16));
        let linha = format!("api_key={chave} password=senha123");
        let limpa = redigir(&linha);
        assert!(!limpa.contains(&chave), "chave vazou: {limpa}");
        assert!(!limpa.contains("senha123"), "senha vazou: {limpa}");
    }

    #[test]
    fn log_gira_quando_passa_de_5mb() {
        let dir = tempfile::tempdir().unwrap();
        let caminho = dir.path().join("teste.log");
        let mut log = Log::abrir(caminho.clone());
        // Escreve exatamente 5 MiB + 1 byte para forçar rotação.
        // Log::linha espera texto pré-sanitizado; chamamos redigir aqui.
        let bloco = redigir(&"x".repeat(1024));
        for _ in 0..(5 * 1024) {
            log.linha(&bloco);
        }
        log.linha(&redigir("linha-extra"));
        // O arquivo original deve ter sido girado para .log.1
        let girado = caminho.with_extension("log.1");
        assert!(girado.exists(), "log não girou: {:?}", girado);
        assert!(caminho.exists(), "log novo não foi criado");
    }
}