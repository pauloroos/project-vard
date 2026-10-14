//! Cofre de credenciais generalizado para a 0.6 Painéis.
//!
//! Alvos seguem o padrão `vard:<tipo>:<id>` onde tipo é um dos prefixos
//! conhecidos (provedor, voz, mcp) e id é livre mas validado. A migração
//! das duas chaves legadas (`elevenlabs`, `gemini`) confirma leitura antes
//! de remover a origem; falha preserva o campo no JSON.

use serde_json::Value;
#[cfg(test)]
use std::{collections::HashMap, sync::Mutex};

/// Prefixos de alvo aceitos pelo cofre generalizado.
pub const TIPOS: [&str; 3] = ["provedor", "voz", "mcp"];

/// Nomes legados que ainda podem aparecer na config da 0.5.
pub const LEGADOS: [&str; 2] = ["elevenlabs", "gemini"];

/// Constrói o alvo do cofre a partir de tipo e id.
pub fn alvo(tipo: &str, id: &str) -> Result<String, String> {
    if !TIPOS.contains(&tipo) {
        return Err(format!("tipo de segredo desconhecido: {tipo}"));
    }
    validar_id(id)?;
    Ok(format!("vard:{tipo}:{id}"))
}

/// Alvo legado compatível com a 0.5.
pub fn alvo_legado(nome: &str) -> Result<String, String> {
    if !LEGADOS.contains(&nome) {
        return Err(format!("nome de segredo legado desconhecido: {nome}"));
    }
    Ok(format!("vard:{nome}"))
}

fn validar_id(id: &str) -> Result<(), String> {
    if id.is_empty() || id.len() > 128 {
        return Err("id deve ter de 1 a 128 caracteres".into());
    }
    if !id
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
    {
        return Err("id só aceita letras, dígitos, hífen, sublinhado e ponto".into());
    }
    Ok(())
}

pub fn validar_valor(v: &str) -> Result<(), String> {
    if !(1..=4096).contains(&v.chars().count()) || v.chars().any(char::is_control) {
        return Err("valor deve ter de 1 a 4096 caracteres, sem controle".into());
    }
    Ok(())
}

pub trait Cofre: Send + Sync {
    fn ler(&self, alvo: &str) -> Result<Option<String>, String>;
    fn gravar(&self, alvo: &str, valor: &str) -> Result<(), String>;
    fn apagar(&self, alvo: &str) -> Result<(), String>;
    fn existe(&self, alvo: &str) -> Result<bool, String> {
        match self.ler(alvo) {
            Ok(Some(_)) => Ok(true),
            Ok(None) => Ok(false),
            Err(e) => Err(e),
        }
    }
}

pub struct CofreWindows;

fn entrada(alvo: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new_with_target(alvo, "vard", alvo)
        .map_err(|_| "cofre indisponível".to_string())
}

impl Cofre for CofreWindows {
    fn ler(&self, alvo: &str) -> Result<Option<String>, String> {
        match entrada(alvo)?.get_password() {
            Ok(v) => Ok(Some(v)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(_) => Err("não foi possível ler o cofre".into()),
        }
    }

    fn gravar(&self, alvo: &str, valor: &str) -> Result<(), String> {
        validar_valor(valor)?;
        entrada(alvo)?
            .set_password(valor)
            .map_err(|_| "não foi possível gravar no cofre".into())
    }

    fn apagar(&self, alvo: &str) -> Result<(), String> {
        match entrada(alvo)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(_) => Err("não foi possível apagar do cofre".into()),
        }
    }
}

#[cfg(test)]
#[derive(Default)]
pub struct CofreMemoria(pub Mutex<HashMap<String, String>>);

#[cfg(test)]
impl Cofre for CofreMemoria {
    fn ler(&self, alvo: &str) -> Result<Option<String>, String> {
        Ok(self
            .0
            .lock()
            .map_err(|_| "cofre indisponível")?
            .get(alvo)
            .cloned())
    }

    fn gravar(&self, alvo: &str, valor: &str) -> Result<(), String> {
        validar_valor(valor)?;
        self.0
            .lock()
            .map_err(|_| "cofre indisponível")?
            .insert(alvo.into(), valor.into());
        Ok(())
    }

    fn apagar(&self, alvo: &str) -> Result<(), String> {
        self.0
            .lock()
            .map_err(|_| "cofre indisponível")?
            .remove(alvo);
        Ok(())
    }
}

/// Migração das chaves legadas: grava no cofre novo, confirma leitura e só
/// então remove do JSON. Falha em qualquer etapa preserva o campo original.
pub fn migrar_legados(cfg: &mut Value, cofre: &dyn Cofre) -> Result<Vec<String>, String> {
    let mut migradas = Vec::new();
    for nome in LEGADOS {
        let campo = format!("{nome}_chave");
        let Some(v) = cfg.get(&campo) else { continue };
        let valor = v.as_str().ok_or("campo de chave inválido")?;
        if valor.is_empty() {
            migradas.push(nome.to_string());
            continue;
        }
        let alvo = alvo_legado(nome)?;
        validar_valor(valor)?;
        cofre.gravar(&alvo, valor)?;
        match cofre.ler(&alvo)? {
            Some(lido) if lido == valor => {}
            _ => return Err(format!("cofre não confirmou a migração de {nome}")),
        }
        migradas.push(nome.to_string());
    }
    if let Some(obj) = cfg.as_object_mut() {
        for nome in &migradas {
            obj.remove(&format!("{nome}_chave"));
        }
    }
    Ok(migradas)
}

/// Remove campos terminados em `_chave` de objetos e listas em qualquer profundidade.
pub fn sem_chaves(mut cfg: Value) -> Value {
    match &mut cfg {
        Value::Object(obj) => {
            obj.retain(|k, _| !k.ends_with("_chave"));
            for v in obj.values_mut() {
                *v = sem_chaves(v.take());
            }
        }
        Value::Array(vs) => {
            for v in vs {
                *v = sem_chaves(v.take());
            }
        }
        _ => {}
    }
    cfg
}

/// Preserva campos legados não vazios que já estavam no disco quando o
/// payload recebido tenta redefini-los. O valor recebido nunca define segredo.
pub fn preservar_chaves_pendentes(novo: Value, disco: &Value) -> Value {
    let mut novo = sem_chaves(novo);
    if let Some(campos) = disco.as_object() {
        for (nome, valor) in campos {
            if nome.ends_with("_chave") && valor.as_str().is_some_and(|v| !v.is_empty()) {
                if !novo.is_object() {
                    novo = Value::Object(serde_json::Map::new());
                }
                novo.as_object_mut()
                    .expect("objeto de config")
                    .insert(nome.clone(), valor.clone());
            }
        }
    }
    novo
}

pub fn janela_pode_gravar(label: &str) -> bool {
    label == "configuracoes"
}

pub const ERRO_COFRE: &str = "cofre do Windows indisponível";

#[tauri::command]
pub async fn cofre_existe(window: tauri::WebviewWindow, tipo: String, id: String) -> Result<bool, String> {
    if !matches!(window.label(), "hud" | "configuracoes") {
        return Err("janela sem permissão para consultar o cofre".into());
    }
    let alvo = alvo(&tipo, &id)?;
    tauri::async_runtime::spawn_blocking(move || CofreWindows.existe(&alvo))
        .await
        .map_err(|_| ERRO_COFRE.to_string())?
}

#[tauri::command]
pub async fn cofre_gravar(
    window: tauri::WebviewWindow,
    tipo: String,
    id: String,
    valor: String,
) -> Result<(), String> {
    if !janela_pode_gravar(window.label()) {
        return Err("janela sem permissão para gravar no cofre".into());
    }
    let alvo = alvo(&tipo, &id)?;
    tauri::async_runtime::spawn_blocking(move || CofreWindows.gravar(&alvo, &valor))
        .await
        .map_err(|_| ERRO_COFRE.to_string())?
}

#[tauri::command]
pub async fn cofre_apagar(window: tauri::WebviewWindow, tipo: String, id: String) -> Result<(), String> {
    if !janela_pode_gravar(window.label()) {
        return Err("janela sem permissão para apagar do cofre".into());
    }
    let alvo = alvo(&tipo, &id)?;
    tauri::async_runtime::spawn_blocking(move || CofreWindows.apagar(&alvo))
        .await
        .map_err(|_| ERRO_COFRE.to_string())?
}

/// Lê o valor de uma credencial. Apenas a janela de configurações pode chamar.
/// O valor nunca é logado ou impresso em erros.
#[tauri::command]
pub async fn cofre_ler(window: tauri::WebviewWindow, tipo: String, id: String) -> Result<Option<String>, String> {
    if !janela_pode_gravar(window.label()) {
        return Err("janela sem permissão para ler do cofre".into());
    }
    let alvo = alvo(&tipo, &id)?;
    tauri::async_runtime::spawn_blocking(move || CofreWindows.ler(&alvo))
        .await
        .map_err(|_| ERRO_COFRE.to_string())?
}

/// Migração de arranque: move chaves legadas para o cofre sem expor valores.
pub fn migrar_no_arranque(app: &tauri::AppHandle) {
    let resultado = (|| {
        let mut cfg = crate::comandos::ler_config_valor(app).map_err(|_| ())?;
        let nomes = migrar_legados(&mut cfg, &CofreWindows).map_err(|_| ())?;
        if !nomes.is_empty() {
            crate::comandos::gravar_config(app.clone(), cfg).map_err(|_| ())?;
        }
        Ok::<_, ()>(nomes)
    })();
    let linha = match resultado {
        Ok(nomes) if nomes.is_empty() => return,
        Ok(nomes) => format!("cofre: migrados {}", nomes.join(", ")),
        Err(()) => "cofre: aviso; migração não concluída, campos preservados no arquivo".into(),
    };
    use std::io::Write;
    let dir = tauri::Manager::path(app)
        .app_data_dir()
        .unwrap_or_else(|_| std::path::PathBuf::from("."));
    let logs = dir.join("logs");
    if std::fs::create_dir_all(&logs).is_ok() {
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(logs.join("app.log"))
        {
            let _ = writeln!(f, "{linha}");
        }
    }
}

#[cfg(test)]
mod testes {
    use super::*;
    use serde_json::json;

    #[test]
    fn alvo_aceita_tipos_conhecidos_e_ids_validos() {
        assert_eq!(alvo("provedor", "suad").unwrap(), "vard:provedor:suad");
        assert_eq!(alvo("voz", "kokoro-local").unwrap(), "vard:voz:kokoro-local");
        assert_eq!(alvo("mcp", "filesystem").unwrap(), "vard:mcp:filesystem");
    }

    #[test]
    fn alvo_recusa_tipo_desconhecido() {
        assert!(alvo("agente", "claude").is_err());
        assert!(alvo("", "x").is_err());
    }

    #[test]
    fn alvo_recusa_id_vazio_longo_ou_com_caractere_invalido() {
        assert!(alvo("provedor", "").is_err());
        assert!(alvo("provedor", &"a".repeat(129)).is_err());
        assert!(alvo("provedor", "com espaço").is_err());
        assert!(alvo("provedor", "com/barra").is_err());
        assert!(alvo("provedor", "com@arroba").is_err());
    }

    #[test]
    fn alvo_legado_so_dos_nomes_conhecidos() {
        assert_eq!(alvo_legado("elevenlabs").unwrap(), "vard:elevenlabs");
        assert_eq!(alvo_legado("gemini").unwrap(), "vard:gemini");
        assert!(alvo_legado("suad").is_err());
        assert!(alvo_legado("").is_err());
    }

    #[test]
    fn valor_vazio_longo_ou_com_controle_recusado() {
        assert!(validar_valor("").is_err());
        assert!(validar_valor(&"a".repeat(4097)).is_err());
        assert!(validar_valor("teste\n").is_err());
        assert!(validar_valor("teste\0").is_err());
        assert!(validar_valor("teste-a").is_ok());
        assert!(validar_valor(&"á".repeat(4096)).is_ok());
    }

    #[test]
    fn migracao_move_e_apaga_do_json() {
        let cofre = CofreMemoria::default();
        let mut cfg = json!({"elevenlabs_chave":"teste-e", "gemini_chave":"teste-g", "voz":"v"});
        assert_eq!(migrar_legados(&mut cfg, &cofre).unwrap(), vec!["elevenlabs", "gemini"]);
        assert_eq!(cfg, json!({"voz":"v"}));
        assert_eq!(cofre.ler("vard:elevenlabs").unwrap().as_deref(), Some("teste-e"));
        assert_eq!(cofre.ler("vard:gemini").unwrap().as_deref(), Some("teste-g"));
    }

    #[test]
    fn migracao_chave_vazia_so_remove() {
        let cofre = CofreMemoria::default();
        let mut cfg = json!({"elevenlabs_chave":""});
        assert_eq!(migrar_legados(&mut cfg, &cofre).unwrap(), vec!["elevenlabs"]);
        assert_eq!(cfg, json!({}));
        assert_eq!(cofre.ler("vard:elevenlabs").unwrap(), None);
    }

    #[test]
    fn migracao_sem_chaves_nao_mexe() {
        let mut cfg = json!({"voz":"v"});
        assert!(migrar_legados(&mut cfg, &CofreMemoria::default()).unwrap().is_empty());
        assert_eq!(cfg, json!({"voz":"v"}));
    }

    struct CofreDivergente;
    impl Cofre for CofreDivergente {
        fn ler(&self, _: &str) -> Result<Option<String>, String> { Ok(Some("outro".into())) }
        fn gravar(&self, _: &str, _: &str) -> Result<(), String> { Ok(()) }
        fn apagar(&self, _: &str) -> Result<(), String> { Ok(()) }
    }

    #[test]
    fn migracao_so_apaga_depois_de_ler_igual() {
        let mut cfg = json!({"elevenlabs_chave":"teste-e"});
        let original = cfg.clone();
        assert!(migrar_legados(&mut cfg, &CofreDivergente).is_err());
        assert_eq!(cfg, original);
    }

    /// Cofre que simula falha sem vazar detalhes sensíveis — contrato da trait.
    struct CofreFalho;
    impl Cofre for CofreFalho {
        fn ler(&self, _: &str) -> Result<Option<String>, String> { Err("não foi possível ler o cofre".into()) }
        fn gravar(&self, _: &str, _: &str) -> Result<(), String> { Err("não foi possível gravar no cofre".into()) }
        fn apagar(&self, _: &str) -> Result<(), String> { Err("não foi possível apagar do cofre".into()) }
    }

    #[test]
    fn cofre_indisponivel_sem_valor_no_erro() {
        let err = CofreFalho.gravar("vard:provedor:x", "v").unwrap_err();
        assert!(!err.contains("chave") && !err.contains("token") && !err.contains("password"));
        assert!(err.contains("cofre"));
        let err = CofreFalho.ler("vard:provedor:x").unwrap_err();
        assert!(!err.contains("chave") && !err.contains("token") && !err.contains("password"));
        assert!(err.contains("cofre"));
    }

    #[test]
    fn sem_chaves_tira_campos_de_chave() {
        let cfg = json!({"elevenlabs_chave":"e", "voz":"v", "extra":{"outra_chave":"x", "ok":1}, "lista":[{"gemini_chave":"g"}]});
        assert_eq!(sem_chaves(cfg), json!({"voz":"v", "extra":{"ok":1}, "lista":[{}]}));
    }

    #[test]
    fn preservar_chaves_pendentes_so_do_disco() {
        let disco = json!({"elevenlabs_chave":"disco", "gemini_chave":"", "voz":"antiga"});
        let novo = json!({"voz":"nova", "elevenlabs_chave":"injetada", "extra":{"outra_chave":"injetada"}});
        let finalizado = preservar_chaves_pendentes(novo, &disco);
        assert_eq!(finalizado, json!({"voz":"nova", "elevenlabs_chave":"disco", "extra":{}}));
    }

    #[test]
    fn preservar_sem_pendencia_nao_reintroduz() {
        let finalizado = preservar_chaves_pendentes(json!({"voz":"nova", "gemini_chave":"inj"}), &json!({"voz":"antiga"}));
        assert_eq!(finalizado, json!({"voz":"nova"}));
    }

    #[test]
    fn gravar_segredo_recusa_janela_hud() {
        assert!(!janela_pode_gravar("hud"));
        assert!(!janela_pode_gravar("sala"));
        assert!(janela_pode_gravar("configuracoes"));
    }

    #[test]
    fn duas_entradas_isoladas() {
        let cofre = CofreMemoria::default();
        cofre.gravar("vard:provedor:a", "va").unwrap();
        cofre.gravar("vard:provedor:b", "vb").unwrap();
        assert_eq!(cofre.ler("vard:provedor:a").unwrap().as_deref(), Some("va"));
        assert_eq!(cofre.ler("vard:provedor:b").unwrap().as_deref(), Some("vb"));
        cofre.apagar("vard:provedor:a").unwrap();
        assert_eq!(cofre.ler("vard:provedor:a").unwrap(), None);
        assert_eq!(cofre.ler("vard:provedor:b").unwrap().as_deref(), Some("vb"));
    }

    #[test]
    fn referencia_invalida_recusada() {
        assert!(alvo("desconhecido", "x").is_err());
        assert!(alvo("provedor", "").is_err());
        assert!(alvo("provedor", "com/espaço").is_err());
        assert!(alvo_legado("desconhecido").is_err());
    }

    #[test]
    fn migracao_falha_preserva_original() {
        let mut cfg = json!({"elevenlabs_chave":"teste-e", "voz":"v"});
        let original = cfg.clone();
        assert!(migrar_legados(&mut cfg, &CofreFalho).is_err());
        assert_eq!(cfg, original);
    }

    #[test]
    fn migracao_confirma_leitura_antes_de_remover() {
        let mut cfg = json!({"elevenlabs_chave":"teste-e"});
        let original = cfg.clone();
        assert!(migrar_legados(&mut cfg, &CofreDivergente).is_err());
        assert_eq!(cfg, original);
    }
}