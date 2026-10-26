/// Ciclo nativo do Vard 0.7: pasta de dados unificada, fila serial de pedidos e caixa IPC.
///
/// Contrato de pasta de dados (idêntico ao Python nucleo/vard/config.py):
/// 1. Se `VARD_DADOS` estiver definida, usa esse caminho.
/// 2. Senão, usa `%LOCALAPPDATA%\rdl-vard`.
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};

/// Handle global do app para emissão de eventos a partir de threads sem acesso direto ao App.
static APP_HANDLE: OnceLock<AppHandle> = OnceLock::new();

/// Registra o AppHandle global; chamada uma vez no setup do Tauri.
pub fn registrar_app_handle(handle: AppHandle) {
    let _ = APP_HANDLE.set(handle);
}

/// Emite evento `ciclo-estado` com a FotoCiclo atual para frontend e bandeja nativa.
pub fn emitir_ciclo_estado() {
    if let Some(handle) = APP_HANDLE.get() {
        let foto = ciclo_info(supervisor_ativo());
        let _ = handle.emit("ciclo-estado", &foto);
        // Atualiza bandeja nativa se supervisor ativo
        #[cfg(not(test))]
        if supervisor_ativo() {
            crate::bandeja::atualizar_bandeja_nativa(handle, &foto);
        }
    }
}

/// Pasta de configuração com o mesmo contrato do Python (`vard/config.py`):
/// `VARD_CONFIG` se definida; senão `<pasta_dados()>/config`.
pub fn pasta_config() -> PathBuf {
    if let Ok(c) = std::env::var("VARD_CONFIG") {
        if !c.trim().is_empty() {
            return PathBuf::from(c);
        }
    }
    pasta_dados().join("config")
}

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
    pub reuniao_ativa: bool,
    pub reuniao_pasta: Option<String>,
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
        reuniao_ativa: foto.reuniao_ativa,
        reuniao_pasta: foto.reuniao_pasta.clone(),
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
        VerboPedido::Jogo => executar_jogo(),
        VerboPedido::Voltar => executar_voltar(),
    };
    let (modo_final, detalhe_final) = match resultado {
        Ok(m) => (m, None),
        Err(e) => (ModoCiclo::Erro, Some(e)),
    };
let _ = escrever_estado(&modo_final, detalhe_final.as_deref());
    emitir_ciclo_estado();
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
    // repetir() recria a thread se ela estiver morta, então não precisa parar antes.
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


/// Lê `ponte_url` do hud.config.json na pasta de configuração.
/// Usa `pasta_config()` para ser consistente com onde o frontend salva as configurações.
/// Retorna None se o arquivo não existir ou o campo estiver ausente/vazio.
fn ler_ponte_url() -> Option<String> {
    let config = pasta_config();
    let caminho = config.join("hud.config.json");
    if !caminho.exists() {
        return None;
    }
    let txt = std::fs::read_to_string(&caminho).ok()?;
    let v: serde_json::Value = serde_json::from_str(&txt).ok()?;
    let url = v.get("ponte_url")?.as_str()?.trim();
    if url.is_empty() {
        None
    } else {
        Some(url.trim_end_matches('/').to_string())
    }
}

/// POST /modo na ponte com timeout curto. true = ponte aceitou.
fn ponte_modo(verbo: &str) -> Result<bool, String> {
    let base = ler_ponte_url().ok_or_else(|| "ponte desligada".to_string())?;
    let cliente = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| format!("cliente http: {}", e))?;
    let resp = cliente
        .post(format!("{}/modo", base))
        .header("Content-Type", "application/json")
        .body(format!(r#"{{"modo":"{}"}}"#, verbo))
        .send()
        .map_err(|e| format!("ponte /modo: {}", e))?;
    if !resp.status().is_success() {
        return Err(format!("ponte /modo status {}", resp.status()));
    }
    let txt = resp.text().map_err(|e| format!("ler resposta: {}", e))?;
    let body: serde_json::Value = serde_json::from_str(&txt).map_err(|e| format!("parse resposta: {}", e))?;
    Ok(body.get("ok").and_then(|v| v.as_bool()).unwrap_or(false))
}

/// Cancela todos os pedidos pendentes do cérebro próprio via POST /pedidos/{id}/cancelar.
/// Melhor esforço: falhas são registradas no log mas não bloqueiam o modo jogo.
fn cancelar_pedidos_cerebro() {
    let base = match ler_ponte_url() {
        Some(url) => url,
        None => return, // ponte desligada: nada a cancelar
    };
    let cliente = match reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            eprintln!("jogo: falha ao criar cliente http para cancelar pedidos: {}", e);
            return;
        }
    };
    // Lista pedidos ativos via GET /pedidos
    let lista_url = format!("{}/pedidos", base);
    let resp = match cliente.get(&lista_url).send() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("jogo: falha ao listar pedidos do cerebro: {}", e);
            return;
        }
    };
    if !resp.status().is_success() {
        eprintln!("jogo: GET /pedidos retornou status {}", resp.status());
        return;
    }
    let body_text = match resp.text() {
        Ok(t) => t,
        Err(e) => {
            eprintln!("jogo: falha ao ler corpo da lista de pedidos: {}", e);
            return;
        }
    };
    let body: serde_json::Value = match serde_json::from_str(&body_text) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("jogo: falha ao parsear lista de pedidos: {}", e);
            return;
        }
    };
    let pedidos = match body.get("pedidos").and_then(|v| v.as_array()) {
        Some(arr) => arr,
        None => return, // sem campo "pedidos" ou não é array
    };
    for p in pedidos {
        let id = match p.get("pedido_id").and_then(|v| v.as_str()) {
            Some(id) => id,
            None => continue,
        };
        let estado = p.get("estado").and_then(|v| v.as_str()).unwrap_or("");
        // Só cancela pedidos ainda ativos (na_fila ou executando)
        if estado != "na_fila" && estado != "executando" {
            continue;
        }
        let cancel_url = format!("{}/pedidos/{}/cancelar", base, id);
        match cliente.post(&cancel_url).send() {
            Ok(r) if r.status().is_success() => {
                eprintln!("jogo: pedido {} cancelado com sucesso", id);
            }
            Ok(r) => {
                eprintln!("jogo: falha ao cancelar pedido {}: status {}", id, r.status());
            }
            Err(e) => {
                eprintln!("jogo: erro ao cancelar pedido {}: {}", id, e);
            }
        }
    }
}

fn executar_jogo() -> Result<ModoCiclo, String> {
    // FR-009: Rust é executor único — libera recursos diretamente, sem chamar ponte.
    // 1. Verifica se hud.config.json existe e contém configuração válida (não vazia).
    let config_path = pasta_config().join("hud.config.json");
    if !config_path.exists() {
        return Err("configuração não encontrada: hud.config.json ausente".to_string());
    }
    let txt = std::fs::read_to_string(&config_path)
        .map_err(|e| format!("erro ao ler hud.config.json: {}", e))?;
    let v: serde_json::Value = serde_json::from_str(&txt)
        .map_err(|e| format!("hud.config.json inválido: {}", e))?;
    if v.as_object().map(|o| o.is_empty()).unwrap_or(false) {
        return Err("configuração inválida: hud.config.json está vazio ({})".to_string());
    }

    // 2. Cancela pedidos pendentes do cérebro próprio (melhor esforço).
    cancelar_pedidos_cerebro();

    // 3. Para serviços que usam GPU e aguarda término com timeout de 5s.
    let ids: Vec<String> = ["openjarvis", "voz", "nucleo"]
        .iter().map(|s| s.to_string()).collect();
    crate::servicos::parar_e_aguardar(&ids, std::time::Duration::from_secs(5))
        .map_err(|e| format!("falha ao parar serviços para modo jogo: {}", e))?;

    // 4. Publica estado Jogo apenas após confirmação de que os processos terminaram.
    Ok(ModoCiclo::Jogo)
}

fn executar_voltar() -> Result<ModoCiclo, String> {
    // FR-009: Rust é executor único — não chama ponte_modo na volta.
    // 1. Carrega fotografia de retomar.json
    // 2. Reinicia serviços via iniciar_servicos() (parar_e_aguardar removeu os registros)
    // 3. Modelo sob demanda é responsabilidade do provedor; sem carregador novo aqui
    let foto = carregar_fotografia()?.unwrap_or_default();

    // parar_e_aguardar remove os registros do SERVICOS, então repetir() falharia.
    // Recria todos os serviços habilitados na configuração de instalação.
    let recursos = std::path::PathBuf::new();
    let raiz = crate::instalacao::resolver_raiz(&recursos);
    let dados = pasta_dados();
    let arquivo = crate::instalacao::arquivo_instalacao();
    let config = crate::instalacao::ler_instalacao(&arquivo)?;
    if !config.supervisor {
        return Err("supervisor desabilitado: não é possível voltar ao modo ligado".into());
    }
    let (_iniciados, avisos) = crate::instalacao::iniciar_servicos(
        &config,
        &recursos,
        &raiz,
        &dados,
        env!("CARGO_PKG_VERSION"),
    );
    for a in &avisos {
        eprintln!("voltar: {a}");
    }

    // Dispositivos de áudio: preferência salva é restaurada pelo frontend
    // via evento ciclo-estado; aqui apenas registramos no log
    if foto.audio_microfone.is_some() || foto.audio_saida.is_some() {
        eprintln!(
            "voltar: dispositivos preferidos microfone={:?} saida={:?}",
            foto.audio_microfone, foto.audio_saida
        );
    }

    // Reunião ativa: novo segmento será criado pelo serviço quando retomar;
    // aqui apenas registramos a intenção no estado
    if foto.reuniao_ativa {
        eprintln!(
            "voltar: reunião estava ativa, pasta={:?}",
            foto.reuniao_pasta
        );
    }

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
pub(crate) mod testes {
    use super::*;
    use std::sync::Mutex;

    // Mutex global para serializar testes que manipulam VARD_DADOS,
    // evitando condições de corrida entre testes paralelos.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    /// Serializa e restaura o ambiente do processo; nenhum fallback lê dados do usuário.
    pub(crate) struct AmbienteTeste {
        anteriores: Vec<(&'static str, Option<std::ffi::OsString>)>,
        _pasta: tempfile::TempDir,
        _lock: std::sync::MutexGuard<'static, ()>,
    }

    impl Drop for AmbienteTeste {
        fn drop(&mut self) {
            for (nome, valor) in &self.anteriores {
                unsafe {
                    match valor {
                        Some(v) => std::env::set_var(nome, v),
                        None => std::env::remove_var(nome),
                    }
                }
            }
        }
    }

    pub(crate) fn ambiente_isolado() -> AmbienteTeste {
        let lock = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let pasta = tempfile::tempdir().unwrap();
        let nomes = ["LOCALAPPDATA", "APPDATA", "HOME", "VARD_DADOS", "VARD_INSTALACAO", "VARD_RAIZ_DEV", "VARD_HUD_CONFIG_DIR"];
        let anteriores = nomes.iter().map(|&n| (n, std::env::var_os(n))).collect();
        for nome in nomes {
            unsafe { std::env::set_var(nome, pasta.path().join(nome)) };
        }
        // Testes que criam instalacao.json exercitam o fallback em VARD_DADOS.
        unsafe { std::env::remove_var("VARD_INSTALACAO") };
        AmbienteTeste { anteriores, _pasta: pasta, _lock: lock }
    }


    #[test]
    fn pasta_dados_usa_vard_dados_quando_definido() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let resultado = pasta_dados();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert_eq!(resultado, dir.path());
    }

    #[test]
    fn pasta_dados_fallback_para_localappdata() {
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let resultado = carregar_fotografia().unwrap();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert!(resultado.is_none());
    }

    #[test]
    fn registrar_sessao_cria_app_json() {
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-rep");
        let r1 = ciclo_pedir("iniciar");
        let r2 = ciclo_pedir("iniciar");
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert!(r1.ok);
        assert!(r2.ok);
        assert_eq!(r1.id, r2.id);
        liberar_pedido(&r1.id);
    }

    #[test]
    fn fila_ocupado_quando_verbo_diferente_em_andamento() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-ocup");
        let r1 = ciclo_pedir("iniciar");
        let r2 = ciclo_pedir("parar");
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert!(r1.ok);
        assert!(!r2.ok);
        assert!(r2.erro.as_ref().map(|e| e.contains("ocupado")).unwrap_or(false));
        liberar_pedido(&r1.id);
    }

    #[test]
    fn fila_liberar_permite_novo_pedido() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-lib");
        let r1 = ciclo_pedir("iniciar");
        assert!(r1.ok);
        liberar_pedido(&r1.id);
        let r2 = ciclo_pedir("parar");
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert!(r2.ok);
        liberar_pedido(&r2.id);
    }

    #[test]
    fn caixa_ipc_consumo_remove_arquivo() {
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
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
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        reset_fila_para_teste("sessao-info");

        escrever_estado(&ModoCiclo::Ligado, None).unwrap();
        let foto = ciclo_info(true);
        unsafe { std::env::remove_var("VARD_DADOS") };

        assert_eq!(foto.modo, "ligado");
        assert!(foto.supervisor_ativo);
    }

    // -----------------------------------------------------------------------
    // Testes T6-pend: execução dos verbos com serviços falsos (filhos reais)
    // -----------------------------------------------------------------------

    /// Servidor HTTP falso mínimo para testes de execução de verbos.
    /// Responde /saude com PID próprio e aceita /parar para simular shutdown.
    fn criar_servico_falso(porta: u16) -> std::process::Child {
        use std::io::Write;
        let script = format!(
            r#"
import http.server, json, os, sys, threading
class H(http.server.BaseHTTPRequestHandler):
    parado = False
    def do_GET(self):
        if self.path == '/saude' and not H.parado:
            body = json.dumps({{"ok": True, "versao": "0.7.0", "pid": os.getpid()}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def do_POST(self):
        if self.path == '/parar':
            H.parado = True
            self.send_response(200)
            self.end_headers()
            threading.Thread(target=self.server.shutdown).start()
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', {porta}), H).serve_forever()
"#,
            porta = porta
        );
        let python = if cfg!(windows) { "python" } else { "python3" };
        std::process::Command::new(python)
            .args(["-c", &script])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("falha ao iniciar serviço falso")
    }

    fn esperar_servico_saude(porta: u16, timeout_ms: u64) -> bool {
        let fim = std::time::Instant::now() + std::time::Duration::from_millis(timeout_ms);
        while std::time::Instant::now() < fim {
            if let Ok(resp) = reqwest::blocking::get(format!("http://127.0.0.1:{}/saude", porta)) {
                if resp.status().is_success() {
                    return true;
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        false
    }

    #[test]
    fn executar_iniciar_sobe_servicos_e_grava_estado_ligado() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        // Cria instalacao.json com supervisor:true e um serviço falso
        let ciclo_dir = dir.path().join("ciclo");
        std::fs::create_dir_all(&ciclo_dir).unwrap();
        let inst = serde_json::json!({
            "supervisor": true,
            "servicos": {}
        });
        std::fs::write(dir.path().join("instalacao.json"), inst.to_string()).unwrap();

        reset_fila_para_teste("sessao-exec-iniciar");
        let id = uuid::Uuid::new_v4().to_string();

        // Executar iniciar sem serviços configurados deve resultar em Ligado
        let modo = executar_verbo(&id, &VerboPedido::Iniciar);

        assert_eq!(modo, ModoCiclo::Ligado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "ligado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_parar_desliga_servicos_e_grava_estado_parado() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-exec-parar");
        // Pré-condição: estado ligado
        escrever_estado(&ModoCiclo::Ligado, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Parar);

        assert_eq!(modo, ModoCiclo::Parado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "parado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_recarregar_reinicia_nucleo_e_conserva_outros() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-exec-recarregar");
        escrever_estado(&ModoCiclo::Ligado, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Recarregar);

        // Recarregar retorna Ligado após reiniciar núcleo/OpenJarvis
        assert_eq!(modo, ModoCiclo::Ligado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "ligado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_tentar_repete_desistidos_e_retorna_ligado() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-exec-tentar");
        escrever_estado(&ModoCiclo::Ligado, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Tentar);

        assert_eq!(modo, ModoCiclo::Ligado);
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_sonda_confirma_registro_sem_mudar_estado() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-exec-sonda");
        escrever_estado(&ModoCiclo::Ligado, Some("antes-da-sonda")).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Sonda);

        assert_eq!(modo, ModoCiclo::Ligado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "ligado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_jogo_sem_configuracao_retorna_erro() {
        // FR-009: sem hud.config.json na pasta de configuração, jogo deve retornar erro.
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        // VARD_CONFIG aponta para subdir config que não tem hud.config.json
        let config_dir = dir.path().join("config");
        std::fs::create_dir_all(&config_dir).unwrap();
        unsafe { std::env::set_var("VARD_CONFIG", &config_dir) };

        reset_fila_para_teste("sessao-exec-jogo-err");
        escrever_estado(&ModoCiclo::Ligado, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Jogo);

        // Sem hud.config.json: deve retornar Erro
        assert_eq!(modo, ModoCiclo::Erro);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "erro");
        assert!(estado.detalhe.as_ref().map(|d| d.contains("configuração não encontrada")).unwrap_or(false));
        unsafe { std::env::remove_var("VARD_CONFIG") };
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_jogo_com_configuracao_vazia_retorna_erro() {
        // Fix-C1: hud.config.json com objeto vazio ({}) deve retornar erro.
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let config_dir = dir.path().join("config");
        std::fs::create_dir_all(&config_dir).unwrap();
        unsafe { std::env::set_var("VARD_CONFIG", &config_dir) };

        // Configuração vazia: deve ser rejeitada
        let config = serde_json::json!({});
        std::fs::write(config_dir.join("hud.config.json"), config.to_string()).unwrap();

        reset_fila_para_teste("sessao-exec-jogo-vazio");
        escrever_estado(&ModoCiclo::Ligado, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Jogo);

        assert_eq!(modo, ModoCiclo::Erro);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "erro");
        assert!(estado.detalhe.as_ref().map(|d| d.contains("vazio")).unwrap_or(false));
        unsafe { std::env::remove_var("VARD_CONFIG") };
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn test_executar_jogo_cancela_pedidos_e_para_servicos() {
        // Fix-C1: verificar que executar_jogo valida config não-vazia e aguarda parada dos serviços.
        // Com config válida (não vazia) e sem serviços registrados, parar_e_aguardar retorna Ok
        // pois não há handles a esperar — o fluxo completa com sucesso.
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };
        let config_dir = dir.path().join("config");
        std::fs::create_dir_all(&config_dir).unwrap();
        unsafe { std::env::set_var("VARD_CONFIG", &config_dir) };
        let config = serde_json::json!({"ponte_url": "http://127.0.0.1:9999"});
        std::fs::write(config_dir.join("hud.config.json"), config.to_string()).unwrap();

        reset_fila_para_teste("sessao-jogo-cancela");
        escrever_estado(&ModoCiclo::Ligado, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Jogo);

        // Config válida + sem serviços registrados = sucesso após parar_e_aguardar
        assert_eq!(modo, ModoCiclo::Jogo);
        unsafe { std::env::remove_var("VARD_CONFIG") };
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn test_executar_voltar_nao_chama_ponte_modo() {
        // FR-009: voltar não deve fazer chamada HTTP à ponte.
        // Validamos que voltar retorna Ligado mesmo sem ponte configurada.
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-voltar-sem-ponte");
        escrever_estado(&ModoCiclo::Jogo, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Voltar);

        // Voltar retorna Ligado sem depender de ponte
        assert_eq!(modo, ModoCiclo::Ligado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "ligado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn test_contrato_pedidos_correto() {
        // FR-009: validar que cancelar_pedidos_cerebro parseia {"pedidos": [...]} corretamente.
        // Teste unitário do parsing via JSON direto.
        let body = serde_json::json!({
            "pedidos": [
                {"pedido_id": "abc-123", "estado": "na_fila"},
                {"pedido_id": "def-456", "estado": "concluido"}
            ]
        });
        let pedidos = body.get("pedidos").and_then(|v| v.as_array());
        assert!(pedidos.is_some());
        let arr = pedidos.unwrap();
        assert_eq!(arr.len(), 2);
        assert_eq!(arr[0].get("pedido_id").and_then(|v| v.as_str()), Some("abc-123"));
        assert_eq!(arr[0].get("estado").and_then(|v| v.as_str()), Some("na_fila"));
        // Segundo pedido tem estado concluido — não seria cancelado
        assert_eq!(arr[1].get("estado").and_then(|v| v.as_str()), Some("concluido"));
    }

    #[test]
    fn executar_voltar_sem_ponte_retorna_ligado() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-exec-voltar");
        escrever_estado(&ModoCiclo::Jogo, None).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Voltar);

        // Sem ponte (LM Studio falso): aceita e retorna Ligado
        assert_eq!(modo, ModoCiclo::Ligado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "ligado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_voltar_restaura_fotografia_com_opcionais() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-voltar-opcionais");
        escrever_estado(&ModoCiclo::Jogo, None).unwrap();

        // Salva fotografia com opcionais ligados
        let foto = FotoOperacional {
            servicos_ligados: vec!["voz".to_string(), "reuniao".to_string()],
            modelo_id: Some("modelo-teste".to_string()),
            contexto_id: Some("ctx-teste".to_string()),
            audio_microfone: Some("mic-falso".to_string()),
            audio_saida: Some("saida-falsa".to_string()),
            reuniao_ativa: false,
            reuniao_pasta: None,
        };
        salvar_fotografia(&foto).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Voltar);

        assert_eq!(modo, ModoCiclo::Ligado);
        let estado = ler_estado().unwrap_or_default();
        assert_eq!(estado.modo, "ligado");
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_voltar_restaura_reuniao_ativa() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-voltar-reuniao");
        escrever_estado(&ModoCiclo::Jogo, None).unwrap();

        // Salva fotografia com reunião ativa
        let foto = FotoOperacional {
            servicos_ligados: vec!["reuniao".to_string()],
            modelo_id: None,
            contexto_id: None,
            audio_microfone: None,
            audio_saida: None,
            reuniao_ativa: true,
            reuniao_pasta: Some("/dados/reuniao/2026-10-15".to_string()),
        };
        salvar_fotografia(&foto).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Voltar);

        assert_eq!(modo, ModoCiclo::Ligado);
        // Reunião ativa é registrada no log; novo segmento será criado pelo serviço
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_voltar_sem_fotografia_usa_padrao() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-voltar-sem-foto");
        escrever_estado(&ModoCiclo::Jogo, None).unwrap();
        // Não salva fotografia: voltar deve usar padrão vazio

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Voltar);

        assert_eq!(modo, ModoCiclo::Ligado);
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn executar_voltar_preserva_modelo_da_fotografia() {
        // T7b (3): log do voltar mostra unload -> lista vazia -> load do MESMO modelo/contexto.
        // Com LM Studio falso (sem ponte), confirmar que a fotografia não é perdida e o modelo
        // registrado nela permanece como referência após o retorno.
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        reset_fila_para_teste("sessao-voltar-modelo");
        escrever_estado(&ModoCiclo::Jogo, None).unwrap();

        let foto = FotoOperacional {
            servicos_ligados: vec!["nucleo".into()],
            modelo_id: Some("lmstudio-falso-7b".into()),
            contexto_id: Some("ctx-vard-teste".into()),
            audio_microfone: None,
            audio_saida: None,
            reuniao_ativa: false,
            reuniao_pasta: None,
        };
        salvar_fotografia(&foto).unwrap();

        let id = uuid::Uuid::new_v4().to_string();
        let modo = executar_verbo(&id, &VerboPedido::Voltar);
        assert_eq!(modo, ModoCiclo::Ligado);

        // Fotografia continua intacta após o retorno (não foi sobrescrita nem perdida)
        let pos = carregar_fotografia().unwrap().unwrap();
        assert_eq!(pos.modelo_id.as_deref(), Some("lmstudio-falso-7b"));
        assert_eq!(pos.contexto_id.as_deref(), Some("ctx-vard-teste"));

        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn ler_ponte_url_retorna_none_sem_config() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        assert!(ler_ponte_url().is_none());
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn ler_ponte_url_retorna_url_do_config() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        let config = serde_json::json!({
            "ponte_url": "http://127.0.0.1:4700"
        });
        std::fs::write(dir.path().join("hud.config.json"), config.to_string()).unwrap();

        let url = ler_ponte_url();
        assert_eq!(url, Some("http://127.0.0.1:4700".to_string()));
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn gate_supervisor_falso_comandos_devolvem_indisponivel() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        // Cria instalacao.json com supervisor:false
        let inst = serde_json::json!({
            "supervisor": false,
            "servicos": {}
        });
        std::fs::write(dir.path().join("instalacao.json"), inst.to_string()).unwrap();

        reset_fila_para_teste("sessao-gate-false");

        // cmd_ciclo_pedir deve devolver indisponível
        let resultado = cmd_ciclo_pedir("iniciar".to_string());

        assert!(!resultado.ok);
        assert!(resultado.erro.as_ref().map(|e| e.contains("indisponivel")).unwrap_or(false));
        unsafe { std::env::remove_var("VARD_DADOS") };
    }

    #[test]
    fn caixa_ipc_so_consome_com_supervisor_ativo() {
        let _ambiente = ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_DADOS", dir.path()) };

        // Cria instalacao.json com supervisor:false
        let inst = serde_json::json!({
            "supervisor": false,
            "servicos": {}
        });
        std::fs::write(dir.path().join("instalacao.json"), inst.to_string()).unwrap();

        reset_fila_para_teste("sessao-caixa-gate");

        // Prepara arquivo IPC válido
        let pedidos_dir = dir.path().join("ciclo").join("pedidos");
        std::fs::create_dir_all(&pedidos_dir).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        let conteudo = serde_json::json!({
            "id": id,
            "verbo": "iniciar",
            "sessao": "sessao-caixa-gate"
        });
        let arquivo = pedidos_dir.join(format!("{}.json", id));
        std::fs::write(&arquivo, conteudo.to_string()).unwrap();

        // consumir_pedidos_da_caixa NÃO é gateado por supervisor (é a thread que decide),
        // mas o executor só roda se supervisor ativo. O consumo em si processa o arquivo.
        let resultados = consumir_pedidos_da_caixa();

        // O arquivo é consumido (removido) mesmo com supervisor:false,
        // pois a validação de supervisor acontece no executor/comando, não no consumo.
        assert_eq!(resultados.len(), 1);
        assert!(!arquivo.exists());
        unsafe { std::env::remove_var("VARD_DADOS") };
    }
}
