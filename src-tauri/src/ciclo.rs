/// Ciclo nativo do Vard 0.7: pasta de dados unificada, fila serial de pedidos e caixa IPC.
///
/// Contrato de pasta de dados (idêntico ao Python nucleo/vard/config.py):
/// 1. Se `VARD_DADOS` estiver definida, usa esse caminho.
/// 2. Senão, usa `%LOCALAPPDATA%\rdl-vard`.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use serde::{Deserialize, Serialize};

/// Resolve a pasta de dados seguindo o mesmo contrato do Python.
pub fn pasta_dados() -> PathBuf {
    if let Ok(d) = std::env::var("VARD_DADOS") {
        if !d.is_empty() {
            return PathBuf::from(d);
        }
    }
    // LOCALAPPDATA\rdl-vard
    let localappdata = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| {
        // Fallback para home se LOCALAPPDATA não existir (não-Windows)
        std::env::var("HOME").unwrap_or_default()
    });
    PathBuf::from(localappdata).join("rdl-vard")
}

/// Modos do ciclo de vida.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ModoCiclo {
    Parado,
    Ligando,
    Ligado,
    Liberando,
    Jogo,
    Voltando,
    Erro,
    Saindo,
}

impl std::fmt::Display for ModoCiclo {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ModoCiclo::Parado => write!(f, "parado"),
            ModoCiclo::Ligando => write!(f, "ligando"),
            ModoCiclo::Ligado => write!(f, "ligado"),
            ModoCiclo::Liberando => write!(f, "liberando"),
            ModoCiclo::Jogo => write!(f, "jogo"),
            ModoCiclo::Voltando => write!(f, "voltando"),
            ModoCiclo::Erro => write!(f, "erro"),
            ModoCiclo::Saindo => write!(f, "saindo"),
        }
    }
}

/// Verbos aceitos pela fila de pedidos.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerboPedido {
    Iniciar,
    Jogo,
    Voltar,
    Parar,
    Recarregar,
    Sonda,
    Aba,
    Tentar,
    Sair,
}

impl std::str::FromStr for VerboPedido {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "iniciar" => Ok(VerboPedido::Iniciar),
            "jogo" => Ok(VerboPedido::Jogo),
            "voltar" => Ok(VerboPedido::Voltar),
            "parar" => Ok(VerboPedido::Parar),
            "recarregar" => Ok(VerboPedido::Recarregar),
            "sonda" => Ok(VerboPedido::Sonda),
            "aba" => Ok(VerboPedido::Aba),
            "tentar" => Ok(VerboPedido::Tentar),
            "sair" => Ok(VerboPedido::Sair),
            _ => Err(format!("verbo desconhecido: {}", s)),
        }
    }
}

impl std::fmt::Display for VerboPedido {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            VerboPedido::Iniciar => write!(f, "iniciar"),
            VerboPedido::Jogo => write!(f, "jogo"),
            VerboPedido::Voltar => write!(f, "voltar"),
            VerboPedido::Parar => write!(f, "parar"),
            VerboPedido::Recarregar => write!(f, "recarregar"),
            VerboPedido::Sonda => write!(f, "sonda"),
            VerboPedido::Aba => write!(f, "aba"),
            VerboPedido::Tentar => write!(f, "tentar"),
            VerboPedido::Sair => write!(f, "sair"),
        }
    }
}

/// Pedido atômico na pasta externa VARD_DADOS/ciclo/pedidos/.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PedidoCiclo {
    pub id: String,
    pub verbo: String,
    pub criado_em: String,
}

/// Fotografia operacional salva em VARD_DADOS/ciclo/retomar.json.
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct FotoOperacional {
    pub servicos_ligados: Vec<String>,
    pub modelo_id: Option<String>,
    pub contexto_id: Option<String>,
    pub audio_microfone: Option<String>,
    pub audio_saida: Option<String>,
    pub reuniao_ativa: bool,
    pub reuniao_pasta: Option<String>,
}

/// Estado persistido em VARD_DADOS/estado.json.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct EstadoCiclo {
    pub modo: String,
    pub desde: String,
    pub detalhe: Option<String>,
}

impl Default for EstadoCiclo {
    fn default() -> Self {
        Self {
            modo: "parado".into(),
            desde: chrono::Utc::now().to_rfc3339(),
            detalhe: None,
        }
    }
}

/// Escreve estado.json atomicamente em VARD_DADOS.
pub fn escrever_estado(modo: &ModoCiclo, detalhe: Option<&str>) -> Result<(), String> {
    let dados = pasta_dados();
    let estado = EstadoCiclo {
        modo: modo.to_string(),
        desde: chrono::Utc::now().to_rfc3339(),
        detalhe: detalhe.map(String::from),
    };
    let caminho = dados.join("estado.json");
    std::fs::create_dir_all(&dados).map_err(|e| format!("criar pasta dados: {}", e))?;
    let tmp = dados.join("estado.json.tmp");
    let json = serde_json::to_string_pretty(&estado).map_err(|e| format!("serializar estado: {}", e))?;
    std::fs::write(&tmp, json.as_bytes()).map_err(|e| format!("escrever tmp: {}", e))?;
    std::fs::rename(&tmp, &caminho).map_err(|e| format!("renomear estado: {}", e))?;
    Ok(())
}

/// Lê o estado atual de VARD_DADOS/estado.json.
pub fn ler_estado() -> Result<EstadoCiclo, String> {
    let dados = pasta_dados();
    let caminho = dados.join("estado.json");
    if !caminho.exists() {
        return Ok(EstadoCiclo::default());
    }
    let bytes = std::fs::read(&caminho).map_err(|e| format!("ler estado: {}", e))?;
    let estado: EstadoCiclo =
        serde_json::from_slice(&bytes).map_err(|e| format!("parse estado: {}", e))?;
    Ok(estado)
}

/// Salva fotografia operacional em VARD_DADOS/ciclo/retomar.json.
pub fn salvar_fotografia(foto: &FotoOperacional) -> Result<(), String> {
    let dados = pasta_dados();
    let ciclo_dir = dados.join("ciclo");
    std::fs::create_dir_all(&ciclo_dir).map_err(|e| format!("criar ciclo dir: {}", e))?;
    let caminho = ciclo_dir.join("retomar.json");
    let json = serde_json::to_string_pretty(foto).map_err(|e| format!("serializar foto: {}", e))?;
    std::fs::write(&caminho, json.as_bytes()).map_err(|e| format!("escrever foto: {}", e))?;
    Ok(())
}

/// Lê fotografia operacional de VARD_DADOS/ciclo/retomar.json.
pub fn carregar_fotografia() -> Result<Option<FotoOperacional>, String> {
    let dados = pasta_dados();
    let caminho = dados.join("ciclo").join("retomar.json");
    if !caminho.exists() {
        return Ok(None);
    }
    let bytes = std::fs::read(&caminho).map_err(|e| format!("ler foto: {}", e))?;
    let foto: FotoOperacional =
        serde_json::from_slice(&bytes).map_err(|e| format!("parse foto: {}", e))?;
    Ok(Some(foto))
}

/// Registra sessão ativa em VARD_DADOS/ciclo/app.json.
pub fn registrar_sessao(pid: u32, sessao_id: &str) -> Result<(), String> {
    use serde_json::json;
    let dados = pasta_dados();
    let ciclo_dir = dados.join("ciclo");
    std::fs::create_dir_all(&ciclo_dir).map_err(|e| format!("criar ciclo dir: {}", e))?;
    let caminho = ciclo_dir.join("app.json");
    let doc = json!({
        "pid": pid,
        "sessao_id": sessao_id,
        "criado_em": chrono::Utc::now().to_rfc3339()
    });
    let json = serde_json::to_string_pretty(&doc).map_err(|e| format!("serializar app.json: {}", e))?;
    std::fs::write(&caminho, json.as_bytes()).map_err(|e| format!("escrever app.json: {}", e))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Fila serial de pedidos e caixa IPC
// ---------------------------------------------------------------------------

/// Limite de tamanho para arquivos de pedido na caixa IPC (4 KiB).
const LIMITE_PEDIDO_BYTES: u64 = 4096;

/// Resultado da admissão de um pedido na fila.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PedidoAceito {
    pub ok: bool,
    pub id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub erro: Option<String>,
}

/// Fotografia do ciclo para o frontend (sem segredos).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FotoCiclo {
    pub modo: String,
    pub desde: String,
    pub detalhe: Option<String>,
    pub servicos_ligados: Vec<String>,
    pub supervisor_ativo: bool,
}

/// Estado interno da fila serial.
struct FilaEstado {
    /// ID do pedido atualmente em execução (se houver).
    em_andamento: Option<String>,
    /// Verbo do pedido em andamento.
    verbo_em_andamento: Option<VerboPedido>,
    /// Sessão atual (renovada a cada arranque).
    sessao_id: String,
}

lazy_static::lazy_static! {
    static ref FILA: Arc<Mutex<FilaEstado>> = Arc::new(Mutex::new(FilaEstado {
        em_andamento: None,
        verbo_em_andamento: None,
        sessao_id: String::new(),
    }));
}

/// Inicializa a sessão da fila (chamado no setup do app).
pub fn inicializar_fila(sessao_id: &str) {
    if let Ok(mut f) = FILA.lock() {
        f.sessao_id = sessao_id.to_string();
    }
}

/// Admite um pedido na fila serial. Retorna imediatamente com o ID aceito.
/// Repetição do mesmo verbo em andamento devolve o mesmo ID.
/// Verbo incompatível durante transição retorna ocupado.
pub fn ciclo_pedir(verbo_str: &str) -> PedidoAceito {
    use std::str::FromStr;
    let verbo = match VerboPedido::from_str(verbo_str) {
        Ok(v) => v,
        Err(e) => return PedidoAceito { ok: false, id: String::new(), erro: Some(e) },
    };

    let mut fila = match FILA.lock() {
        Ok(f) => f,
        Err(e) => return PedidoAceito { ok: false, id: String::new(), erro: Some(format!("lock: {}", e)) },
    };

    // Se já há um pedido em andamento com o mesmo verbo, devolve o mesmo ID.
    if let (Some(id), Some(v)) = (&fila.em_andamento, &fila.verbo_em_andamento) {
        if *v == verbo {
            return PedidoAceito { ok: true, id: id.clone(), erro: None };
        }
        // Verbo diferente durante transição → ocupado.
        return PedidoAceito {
            ok: false,
            id: String::new(),
            erro: Some(format!("ocupado: {} em andamento", v)),
        };
    }

    // Gera ID único para o novo pedido.
    let id = uuid::Uuid::new_v4().to_string();
    fila.em_andamento = Some(id.clone());
    fila.verbo_em_andamento = Some(verbo.clone());

    // Escreve estado atômico (projeção legada).
    let modo_projecao = match verbo {
        VerboPedido::Iniciar => ModoCiclo::Ligando,
        VerboPedido::Jogo => ModoCiclo::Liberando,
        VerboPedido::Voltar => ModoCiclo::Voltando,
        VerboPedido::Parar => ModoCiclo::Liberando,
        VerboPedido::Sair => ModoCiclo::Saindo,
        VerboPedido::Recarregar => ModoCiclo::Ligando,
        VerboPedido::Sonda | VerboPedido::Aba | VerboPedido::Tentar => ModoCiclo::Ligado,
    };
    drop(fila);
    let _ = escrever_estado(&modo_projecao, Some(verbo_str));

    PedidoAceito { ok: true, id, erro: None }
}

/// Libera o slot da fila quando o pedido termina.
pub fn liberar_pedido(id: &str) {
    if let Ok(mut f) = FILA.lock() {
        if f.em_andamento.as_deref() == Some(id) {
            f.em_andamento = None;
            f.verbo_em_andamento = None;
        }
    }
}

/// Retorna a fotografia atual do ciclo para o frontend.
pub fn ciclo_info(supervisor_ativo: bool) -> FotoCiclo {
    let estado = ler_estado().unwrap_or_default();
    let foto = carregar_fotografia().ok().flatten().unwrap_or_default();
    FotoCiclo {
        modo: estado.modo,
        desde: estado.desde,
        detalhe: estado.detalhe,
        servicos_ligados: foto.servicos_ligados,
        supervisor_ativo,
    }
}

// ---------------------------------------------------------------------------
// Gate supervisor e execução dos verbos
// ---------------------------------------------------------------------------

/// Verifica se o supervisor está habilitado no instalacao.json atual.
pub fn supervisor_ativo() -> bool {
    let arquivo = crate::instalacao::arquivo_instalacao();
    match crate::instalacao::ler_instalacao(&arquivo) {
        Ok(cfg) => cfg.supervisor,
        Err(_) => false,
    }
}

/// Executa o verbo admitido na fila. Chamado pela thread dona após admissão.
/// Retorna o modo final após conclusão e libera o slot da fila.
pub fn executar_verbo(id: &str, verbo: &VerboPedido) -> ModoCiclo {
    let resultado = match verbo {
        VerboPedido::Iniciar => executar_iniciar(),
        VerboPedido::Parar => executar_parar(),
        VerboPedido::Recarregar => executar_recarregar(),
        VerboPedido::Sair => executar_sair(),
        VerboPedido::Tentar => executar_tentar(),
        VerboPedido::Sonda => Ok(ModoCiclo::Ligado),
        VerboPedido::Aba => Ok(ModoCiclo::Ligado),
        VerboPedido::Jogo | VerboPedido::Voltar => {
            // Reservados para T6/T7; não executam agora.
            Err("nao-implementado".to_string())
        }
    };
    let modo_final = match resultado {
        Ok(m) => m,
        Err(e) => {
            let _ = escrever_estado(&ModoCiclo::Erro, Some(&e));
            ModoCiclo::Erro
        }
    };
    let _ = escrever_estado(&modo_final, None);
    liberar_pedido(id);
    modo_final
}

fn executar_iniciar() -> Result<ModoCiclo, String> {
    let recursos = std::path::PathBuf::new(); // placeholder; setup passa o real
    let raiz = crate::instalacao::resolver_raiz(&recursos);
    let dados = pasta_dados();
    let arquivo = crate::instalacao::arquivo_instalacao();
    let config = crate::instalacao::ler_instalacao(&arquivo)?;
    if !config.supervisor {
        return Err("supervisor desabilitado".into());
    }
    let (_iniciados, avisos) = crate::instalacao::iniciar_servicos(
        &config,
        &recursos,
        &raiz,
        &dados,
        env!("CARGO_PKG_VERSION"),
    );
    if !avisos.is_empty() {
        // Avisos não bloqueiam; serviços opcionais podem estar ausentes.
        for a in &avisos {
            eprintln!("ciclo iniciar: {a}");
        }
    }
    Ok(ModoCiclo::Ligado)
}

fn executar_parar() -> Result<ModoCiclo, String> {
    crate::servicos::encerrar_todos();
    Ok(ModoCiclo::Parado)
}

fn executar_recarregar() -> Result<ModoCiclo, String> {
    // Reinicia só núcleo e OpenJarvis; conserva voz/reunião.
    let _ = crate::servicos::parar("nucleo");
    let _ = crate::servicos::parar("openjarvis");
    std::thread::sleep(std::time::Duration::from_millis(500));
    let _ = crate::servicos::repetir("nucleo");
    let _ = crate::servicos::repetir("openjarvis");
    Ok(ModoCiclo::Ligado)
}

fn executar_sair() -> Result<ModoCiclo, String> {
    crate::servicos::encerrar_todos();
    // O pai encerra a si mesmo após liberar a fila.
    std::process::exit(0);
}

fn executar_tentar() -> Result<ModoCiclo, String> {
    crate::servicos::repetir_desistidos();
    Ok(ModoCiclo::Ligado)
}

/// Thread dona da fila: consome pedidos admitidos e executa serialmente.
pub fn iniciar_executor_da_fila() {
    std::thread::Builder::new()
        .name("ciclo-executor".into())
        .spawn(|| loop {
            // Verifica se há pedido em andamento.
            let pendente = {
                match FILA.lock() {
                    Ok(f) => f.em_andamento.clone().zip(f.verbo_em_andamento.clone()),
                    Err(_) => None,
                }
            };
            if let Some((id, verbo)) = pendente {
                // Verifica se já foi executado (estado != transição).
                let estado = ler_estado().unwrap_or_default();
                let em_transicao = matches!(
                    estado.modo.as_str(),
                    "ligando" | "liberando" | "voltando" | "saindo"
                );
                if em_transicao {
                    executar_verbo(&id, &verbo);
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(200));
        })
        .expect("falha ao iniciar executor da fila");
}

/// Loop da caixa IPC: consome arquivos periodicamente e manda para a fila.
pub fn iniciar_consumidor_da_caixa() {
    std::thread::Builder::new()
        .name("ciclo-caixa-ipc".into())
        .spawn(|| loop {
            if supervisor_ativo() {
                let _ = consumir_pedidos_da_caixa();
            }
            std::thread::sleep(std::time::Duration::from_millis(500));
        })
        .expect("falha ao iniciar consumidor da caixa IPC");
}

// ---------------------------------------------------------------------------
// Comandos Tauri (invoke_handler)
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn cmd_ciclo_info() -> FotoCiclo {
    ciclo_info(supervisor_ativo())
}

#[tauri::command]
pub fn cmd_ciclo_pedir(verbo: String) -> PedidoAceito {
    if !supervisor_ativo() {
        return PedidoAceito {
            ok: false,
            id: String::new(),
            erro: Some("indisponivel: supervisor desabilitado".into()),
        };
    }
    ciclo_pedir(&verbo)
}

// ---------------------------------------------------------------------------
// Caixa IPC: consumo de pedidos via arquivo
// ---------------------------------------------------------------------------

/// Consome pedidos da caixa IPC (VARD_DADOS/ciclo/pedidos/*.json).
/// Valida UUID, tamanho, verbo conhecido e sessão atual. Remove após consumo.
pub fn consumir_pedidos_da_caixa() -> Vec<PedidoAceito> {
    let dados = pasta_dados();
    let pedidos_dir = dados.join("ciclo").join("pedidos");
    if !pedidos_dir.exists() {
        return Vec::new();
    }

    let sessao_atual = FILA.lock().ok().map(|f| f.sessao_id.clone()).unwrap_or_default();
    let mut resultados = Vec::new();

    let entradas = match std::fs::read_dir(&pedidos_dir) {
        Ok(rd) => rd,
        Err(_) => return Vec::new(),
    };

    for entry in entradas.flatten() {
        let path = entry.path();
        // Só processa .json
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        // Não segue links simbólicos para fora da pasta
        if path.is_symlink() {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        // Limite de tamanho
        let meta = match std::fs::metadata(&path) {
            Ok(m) => m,
            Err(_) => continue,
        };
        if meta.len() > LIMITE_PEDIDO_BYTES {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        // Lê e parseia
        let bytes = match std::fs::read(&path) {
            Ok(b) => b,
            Err(_) => continue,
        };
        let pedido: serde_json::Value = match serde_json::from_slice(&bytes) {
            Ok(v) => v,
            Err(_) => {
                let _ = std::fs::remove_file(&path);
                continue;
            }
        };

        // Valida campos obrigatórios
        let id = match pedido.get("id").and_then(|v| v.as_str()) {
            Some(s) => s.to_string(),
            None => { let _ = std::fs::remove_file(&path); continue; }
        };
        let verbo_str = match pedido.get("verbo").and_then(|v| v.as_str()) {
            Some(s) => s,
            None => { let _ = std::fs::remove_file(&path); continue; }
        };
        let sessao = pedido.get("sessao").and_then(|v| v.as_str()).unwrap_or("");

        // Valida UUID
        if uuid::Uuid::parse_str(&id).is_err() {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        // Verbo conhecido
        use std::str::FromStr;
        if VerboPedido::from_str(verbo_str).is_err() {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        // Sessão atual
        if !sessao_atual.is_empty() && sessao != sessao_atual {
            let _ = std::fs::remove_file(&path);
            continue;
        }

        // Admite na fila
        let resultado = ciclo_pedir(verbo_str);
        // Remove o arquivo consumido
        let _ = std::fs::remove_file(&path);
        resultados.push(resultado);
    }
    resultados
}

#[cfg(test)]
mod testes {
    use super::*;
    use std::sync::Mutex;

    // Mutex global para serializar testes que manipulam VARD_DADOS,
    // evitando condições de corrida entre testes paralelos.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn pasta_dados_usa_vard_dados_quando_definido() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let resultado = pasta_dados();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert_eq!(resultado, dir.path());
    }

    #[test]
    fn pasta_dados_fallback_para_localappdata() {
        let _lock = ENV_LOCK.lock().unwrap();
        unsafe { std::env::remove_var("VARD_DADOS") };
        let localappdata = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| {
            std::env::var("HOME").unwrap_or_default()
        });
        let esperado = PathBuf::from(localappdata).join("rdl-vard");
        let resultado = pasta_dados();
        assert_eq!(resultado, esperado);
    }

    #[test]
    fn pasta_dados_ignora_vard_dados_vazio() {
        let _lock = ENV_LOCK.lock().unwrap();
        let _dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", "") };
        let localappdata = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| {
            std::env::var("HOME").unwrap_or_default()
        });
        let esperado = PathBuf::from(localappdata).join("rdl-vard");
        let resultado = pasta_dados();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert_eq!(resultado, esperado);
    }

    #[test]
    fn escrever_e_ler_estado_roundtrip() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let modo = ModoCiclo::Ligado;
        escrever_estado(&modo, Some("teste")).unwrap();
        let estado = ler_estado().unwrap();
        unsafe { std::env::remove_var("VARD_DADOS") };
        // escrever_estado grava o modo literal via to_string(); Ligado -> "ligado"
        assert_eq!(estado.modo, modo.to_string());
        assert_eq!(estado.detalhe, Some("teste".into()));
    }

    #[test]
    fn salvar_e_carregar_fotografia_roundtrip() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let foto = FotoOperacional {
            servicos_ligados: vec!["nucleo".into(), "voz".into()],
            modelo_id: Some("gpt-4".into()),
            contexto_id: Some("ctx-123".into()),
            audio_microfone: Some("mic-1".into()),
            audio_saida: Some("out-1".into()),
            reuniao_ativa: true,
            reuniao_pasta: Some("/tmp/reuniao".into()),
        };
        salvar_fotografia(&foto).unwrap();
        let carregada = carregar_fotografia().unwrap().unwrap();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert_eq!(carregada.servicos_ligados, foto.servicos_ligados);
        assert_eq!(carregada.modelo_id, foto.modelo_id);
        assert_eq!(carregada.reuniao_ativa, foto.reuniao_ativa);
    }

    #[test]
    fn carregar_fotografia_retorna_none_se_ausente() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let resultado = carregar_fotografia().unwrap();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert!(resultado.is_none());
    }

    #[test]
    fn registrar_sessao_cria_app_json() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        registrar_sessao(12345, "sessao-teste").unwrap();
        let caminho = dir.path().join("ciclo").join("app.json");
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert!(caminho.exists());
        let bytes = std::fs::read(caminho).unwrap();
        let doc: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(doc["pid"], 12345);
        assert_eq!(doc["sessao_id"], "sessao-teste");
    }

    #[test]
    fn verbo_pedido_parse_validos() {
        use std::str::FromStr;
        assert_eq!(VerboPedido::from_str("iniciar").unwrap(), VerboPedido::Iniciar);
        assert_eq!(VerboPedido::from_str("jogo").unwrap(), VerboPedido::Jogo);
        assert_eq!(VerboPedido::from_str("voltar").unwrap(), VerboPedido::Voltar);
        assert_eq!(VerboPedido::from_str("parar").unwrap(), VerboPedido::Parar);
        assert_eq!(VerboPedido::from_str("sair").unwrap(), VerboPedido::Sair);
    }

    #[test]
    fn verbo_pedido_parse_invalido() {
        use std::str::FromStr;
        assert!(VerboPedido::from_str("foobar").is_err());
    }

    #[test]
    fn modo_ciclo_display() {
        assert_eq!(ModoCiclo::Parado.to_string(), "parado");
        assert_eq!(ModoCiclo::Jogo.to_string(), "jogo");
        assert_eq!(ModoCiclo::Saindo.to_string(), "saindo");
    }

    // -----------------------------------------------------------------------
    // Testes T5b: fila serial, caixa IPC, comandos
    // -----------------------------------------------------------------------

    fn reset_fila_para_teste(sessao_id: &str) {
        let mut f = match FILA.lock() {
            Ok(g) => g,
            Err(poisoned) => {
                // Recupera de poison anterior (outro teste panicou segurando o lock).
                let mut g = poisoned.into_inner();
                g.em_andamento = None;
                g.verbo_em_andamento = None;
                g.sessao_id = sessao_id.to_string();
                return;
            }
        };
        f.em_andamento = None;
        f.verbo_em_andamento = None;
        f.sessao_id = sessao_id.to_string();
    }

    #[test]
    fn fila_repeticao_devolve_mesmo_id() {
        let _lock = ENV_LOCK.lock().unwrap();
        reset_fila_para_teste("sessao-rep");
        let r1 = ciclo_pedir("iniciar");
        let r2 = ciclo_pedir("iniciar");
        assert!(r1.ok);
        assert!(r2.ok);
        assert_eq!(r1.id, r2.id);
        liberar_pedido(&r1.id);
    }

    #[test]
    fn fila_ocupado_quando_verbo_diferente_em_andamento() {
        let _lock = ENV_LOCK.lock().unwrap();
        reset_fila_para_teste("sessao-ocup");
        let r1 = ciclo_pedir("iniciar");
        assert!(r1.ok);
        let r2 = ciclo_pedir("parar");
        assert!(!r2.ok);
        assert!(r2.erro.as_ref().map(|e| e.contains("ocupado")).unwrap_or(false));
        liberar_pedido(&r1.id);
    }

    #[test]
    fn fila_liberar_permite_novo_pedido() {
        let _lock = ENV_LOCK.lock().unwrap();
        reset_fila_para_teste("sessao-lib");
        let r1 = ciclo_pedir("iniciar");
        assert!(r1.ok);
        liberar_pedido(&r1.id);
        let r2 = ciclo_pedir("parar");
        assert!(r2.ok);
        liberar_pedido(&r2.id);
    }

    #[test]
    fn caixa_ipc_consumo_remove_arquivo() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-ipc");

        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        let conteudo = serde_json::json!({
            "id": id,
            "verbo": "iniciar",
            "sessao": "sessao-ipc"
        });
        let arquivo = pedidos_dir.join(format!("{}.json", id));
        std::fs::write(&arquivo, conteudo.to_string()).unwrap();

        let resultados = consumir_pedidos_da_caixa();
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert_eq!(resultados.len(), 1);
        assert!(resultados[0].ok);
        assert!(!arquivo.exists());
        liberar_pedido(&id);
    }

    #[test]
    fn caixa_ipc_uuid_invalido_removido() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-uuid");

        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let arquivo = pedidos_dir.join("nao-e-uuid.json");
        std::fs::write(&arquivo, r#"{"id":"nao-e-uuid","verbo":"iniciar","sessao":"sessao-uuid"}"#).unwrap();

        let resultados = consumir_pedidos_da_caixa();
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert!(resultados.is_empty());
        assert!(!arquivo.exists());
    }

    #[test]
    fn caixa_ipc_maior_que_4k_removido() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-grande");

        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        let grande = "x".repeat(5000);
        let conteudo = serde_json::json!({
            "id": id,
            "verbo": "iniciar",
            "sessao": "sessao-grande",
            "lixo": grande
        });
        let arquivo = pedidos_dir.join(format!("{}.json", id));
        std::fs::write(&arquivo, conteudo.to_string()).unwrap();

        let resultados = consumir_pedidos_da_caixa();
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert!(resultados.is_empty());
        assert!(!arquivo.exists());
    }

    #[test]
    fn caixa_ipc_sessao_diferente_removido() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-atual");

        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        let conteudo = serde_json::json!({
            "id": id,
            "verbo": "iniciar",
            "sessao": "sessao-passada"
        });
        let arquivo = pedidos_dir.join(format!("{}.json", id));
        std::fs::write(&arquivo, conteudo.to_string()).unwrap();

        let resultados = consumir_pedidos_da_caixa();
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert!(resultados.is_empty());
        assert!(!arquivo.exists());
    }

    #[test]
    fn caixa_ipc_verbo_desconhecido_removido() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-verbo");

        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        let conteudo = serde_json::json!({
            "id": id,
            "verbo": "decolar",
            "sessao": "sessao-verbo"
        });
        let arquivo = pedidos_dir.join(format!("{}.json", id));
        std::fs::write(&arquivo, conteudo.to_string()).unwrap();

        let resultados = consumir_pedidos_da_caixa();
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert!(resultados.is_empty());
        assert!(!arquivo.exists());
    }

    #[test]
    fn invoke_e_arquivo_simultaneos_um_so_arranque() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-dual");

        // Prepara arquivo IPC
        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let id_arq = uuid::Uuid::new_v4().to_string();
        let conteudo = serde_json::json!({
            "id": id_arq,
            "verbo": "iniciar",
            "sessao": "sessao-dual"
        });
        std::fs::write(pedidos_dir.join(format!("{}.json", id_arq)), conteudo.to_string()).unwrap();

        // Invoke direto primeiro
        let r_invoke = ciclo_pedir("iniciar");
        assert!(r_invoke.ok);

        // Consumo da caixa deve retornar ocupado (mesmo verbo já em andamento → dedup devolve mesmo id)
        let resultados = consumir_pedidos_da_caixa();
        unsafe { std::env::remove_var("VARD_DADOS") };

        // O arquivo é consumido e a dedup retorna o mesmo id do invoke
        assert_eq!(resultados.len(), 1);
        assert!(resultados[0].ok);
        assert_eq!(resultados[0].id, r_invoke.id);
        liberar_pedido(&r_invoke.id);
    }

    #[test]
    fn estado_json_escrita_atomica_e_projecao_legada() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        // Escreve estado com modo que exige projeção legada
        escrever_estado(&ModoCiclo::Ligando, Some("projecao-teste")).unwrap();
        // escrever_estado grava em dados/estado.json (raiz de VARD_DADOS), não em ciclo/
        let caminho = dir.path().join("estado.json");
        assert!(caminho.exists());

        // Lê e verifica que o modo interno é gravado corretamente
        let bytes = std::fs::read(&caminho).unwrap();
        let doc: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(doc["modo"], "ligando");

        // Verifica que não há arquivo temporário residual
        let tmp = dir.path().join("estado.json.tmp");
        assert!(!tmp.exists());

        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn ciclo_info_retorna_foto_com_supervisor() {
        let _lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-info");

        escrever_estado(&ModoCiclo::Ligado, None).unwrap();
        let foto = ciclo_info(true);
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert_eq!(foto.modo, "ligado");
        assert!(foto.supervisor_ativo);
    }
}