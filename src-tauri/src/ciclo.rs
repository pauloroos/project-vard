/// Ciclo nativo do Vard 0.7: pasta de dados unificada, fotografia operacional e pedidos atômicos.
///
/// Contrato de pasta de dados (idêntico ao Python nucleo/vard/config.py):
/// 1. Se `VARD_DADOS` estiver definida, usa esse caminho.
/// 2. Senão, usa `%LOCALAPPDATA%\rdl-vard`.
use std::path::PathBuf;

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
        assert_eq!(estado.modo, "ligado");
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
}