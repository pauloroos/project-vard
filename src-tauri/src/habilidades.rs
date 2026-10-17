//! Contrato e persistência da Oficina. Nunca grava capacidades de fábrica como receitas;
//! os ajustes opcionais delas (nome, quando, instrucoes) ficam em "fabrica", por ID.
use serde_json::{Map, Value};
use std::{collections::HashSet, fs, io::Write, path::Path};

const IDS_FABRICA: [&str; 10] = ["conversa", "computador", "oficina", "consultas", "memoria", "reuniao", "sistema", "resumo-manha", "pesquisa", "agente-remoto"];

fn objeto<'a>(valor: &'a Value, _campos: &[&str]) -> Result<&'a Map<String, Value>, String> {
    let obj = valor.as_object().ok_or("Objeto inválido em habilidades.json")?;
    Ok(obj)
}
fn texto(valor: &Value) -> bool {
    valor.as_str().is_some_and(|s| s.chars().any(|c| !c.is_whitespace() && c != '\u{feff}' && !('\u{1c}'..='\u{1f}').contains(&c)))
}
fn data(valor: &Value) -> bool {
    let Some(s) = valor.as_str() else { return false; };
    let formato = regex::Regex::new(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{3})?Z$").unwrap();
    formato.is_match(s) && !s.starts_with("0000") && chrono::DateTime::parse_from_rfc3339(s).is_ok_and(|d| d.timestamp_subsec_nanos() < 1_000_000_000)
}
/// Nome, quando e instrucoes: obrigatórios nas receitas; nos ajustes de fábrica, só os presentes são conferidos.
fn validar_textos(h: &Map<String, Value>, exigir: bool) -> Result<(), String> {
    let presente = |campo: &str| exigir || h.contains_key(campo);
    let nulo = Value::Null;
    let campo = |nome: &str| h.get(nome).unwrap_or(&nulo);
    if (presente("nome") && !texto(campo("nome"))) || (presente("instrucoes") && !texto(campo("instrucoes")))
        || (presente("quando") && !campo("quando").as_array().is_some_and(|f| !f.is_empty() && f.iter().all(texto))) {
        return Err("Preencha nome, frases de exemplo e instruções".into());
    }
    // Mesma contagem UTF-16 de maxlength no HTML e String.length no TypeScript.
    if campo("nome").as_str().is_some_and(|s| s.encode_utf16().count() > 80) { return Err("Nome deve ter até 80 caracteres".into()); }
    if let Some(frases) = campo("quando").as_array() {
        if frases.len() > 10 { return Err("Use até 10 frases de exemplo".into()); }
        if frases.iter().any(|f| f.as_str().unwrap_or("").encode_utf16().count() > 200) { return Err("Cada frase deve ter até 200 caracteres".into()); }
    }
    if campo("instrucoes").as_str().is_some_and(|s| s.encode_utf16().count() > 4000) { return Err("Instruções devem ter até 4000 caracteres".into()); }
    Ok(())
}
pub fn validar_habilidades(valor: &Value) -> Result<(), String> {
    let obj = objeto(valor, &["versao", "habilidades", "desligadas"])?;
    if obj.get("versao").and_then(Value::as_f64) != Some(1.0) { return Err("Versão de habilidades inválida".into()); }
    let habilidades = obj.get("habilidades").and_then(Value::as_array).ok_or("Lista de habilidades inválida")?;
    if habilidades.len() > 200 { return Err("Cadastre até 200 habilidades".into()); }
    if let Some(desligadas) = obj.get("desligadas") {
        let lista = desligadas.as_array().ok_or("Lista de desligadas inválida")?;
        let mut ids = HashSet::new();
        for id in lista {
            let id = id.as_str().ok_or("ID de fábrica inválido")?;
            if !IDS_FABRICA.contains(&id) || !ids.insert(id) { return Err("ID de fábrica inválido ou repetido".into()); }
        }
    }
    let formato_id = regex::Regex::new(r"^[a-z0-9]+(?:-[a-z0-9]+)*$").unwrap();
    let mut ids: HashSet<&str> = IDS_FABRICA.into_iter().collect();
    for bruto in habilidades {
        let h = objeto(bruto, &["id", "nome", "quando", "instrucoes", "ligada", "situacao", "criada_em", "validada_em"])?;
        let id = bruto["id"].as_str().ok_or("Habilidade sem ID")?;
        if !formato_id.is_match(id) || !ids.insert(id) { return Err("ID de habilidade inválido ou repetido".into()); }
        validar_textos(h, true)?;
        let situacao = bruto["situacao"].as_str().unwrap_or("");
        if !bruto["ligada"].is_boolean() || !["treinada", "validada"].contains(&situacao) || !data(&bruto["criada_em"]) {
            return Err("Estado ou data de criação inválidos".into());
        }
        if bruto.get("validada_em").is_none() || (if situacao == "treinada" { !bruto["validada_em"].is_null() } else { !data(&bruto["validada_em"]) }) {
            return Err("Data de validação incompatível com a situação".into());
        }
    }
    if let Some(fabrica) = obj.get("fabrica") {
        let fabrica = fabrica.as_object().ok_or("Ajustes de fábrica inválidos")?;
        for (id, ajuste) in fabrica {
            let ajuste = ajuste.as_object().filter(|_| IDS_FABRICA.contains(&id.as_str())).ok_or("Ajustes de fábrica inválidos")?;
            validar_textos(ajuste, false)?;
        }
    }
    Ok(())
}
pub fn ler_em(caminho: &Path) -> Result<Value, String> {
    let texto = match fs::read_to_string(caminho) {
        Ok(texto) => texto,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Value::Null),
        Err(_) => return Err("Não foi possível ler habilidades.json".into()),
    };
    let valor = serde_json::from_str(&texto).map_err(|_| "habilidades.json inválido".to_string())?;
    validar_habilidades(&valor)?;
    Ok(valor)
}
pub fn gravar_em(caminho: &Path, valor: &Value) -> Result<(), String> {
    validar_habilidades(valor)?;
    let pasta = caminho.parent().ok_or("Pasta de habilidades inválida")?;
    fs::create_dir_all(pasta).map_err(|_| "Não foi possível criar a pasta de habilidades")?;
    let temporario = pasta.join(format!("habilidades.{}.tmp", uuid::Uuid::new_v4()));
    let resultado = (|| {
        let mut arq = fs::OpenOptions::new().write(true).create_new(true).open(&temporario).map_err(|_| "Não foi possível preparar habilidades.json")?;
        let bytes = serde_json::to_vec_pretty(valor).map_err(|_| "Não foi possível serializar habilidades.json")?;
        arq.write_all(&bytes).map_err(|_| "Não foi possível gravar habilidades.json")?;
        arq.sync_all().map_err(|_| "Não foi possível sincronizar habilidades.json")?;
        drop(arq);
        fs::rename(&temporario, caminho).map_err(|_| "Não foi possível substituir habilidades.json")
    })();
    let _ = fs::remove_file(&temporario);
    resultado.map_err(String::from)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    #[test]
    fn contrato_compartilhado() {
        let casos: Vec<Value> = serde_json::from_str(include_str!("../../tests/fixtures/habilidades/contrato.json")).unwrap();
        for caso in casos {
            assert_eq!(validar_habilidades(&caso["valor"]).is_ok(), caso["valido"].as_bool().unwrap(), "{}", caso["nome"]);
            if let Some(erro) = caso["erro"].as_str() {
                assert_eq!(validar_habilidades(&caso["valor"]).unwrap_err(), erro, "{}", caso["nome"]);
            }
        }
    }

    #[test]
    fn ausente_gravar_ler_e_substituir() {
        let pasta = tempfile::tempdir().unwrap();
        let caminho = pasta.path().join("config/habilidades.json");
        assert_eq!(ler_em(&caminho).unwrap(), Value::Null);
        let cfg = json!({"versao":1,"habilidades":[],"desligadas":["sistema"]});
        gravar_em(&caminho, &cfg).unwrap();
        assert_eq!(ler_em(&caminho).unwrap(), cfg);
        let novo = json!({"versao":1,"habilidades":[]});
        gravar_em(&caminho, &novo).unwrap();
        assert_eq!(ler_em(&caminho).unwrap(), novo);
        assert_eq!(std::fs::read_dir(caminho.parent().unwrap()).unwrap().count(), 1);
    }

    #[test]
    fn erro_de_validacao_preserva_arquivo() {
        let pasta = tempfile::tempdir().unwrap();
        let caminho = pasta.path().join("habilidades.json");
        let cfg = json!({"versao":1,"habilidades":[]});
        gravar_em(&caminho, &cfg).unwrap();
        let antes = std::fs::read(&caminho).unwrap();
        assert!(gravar_em(&caminho, &json!({"versao":2})).is_err());
        assert_eq!(std::fs::read(&caminho).unwrap(), antes);
        std::fs::write(&caminho, "{quebrado").unwrap();
        assert!(ler_em(&caminho).is_err());
        assert_eq!(std::fs::read_to_string(&caminho).unwrap(), "{quebrado");
    }

    #[test]
    fn falha_na_troca_limpa_temporario_e_preserva_destino() {
        let pasta = tempfile::tempdir().unwrap();
        let caminho = pasta.path().join("habilidades.json");
        std::fs::create_dir(&caminho).unwrap();
        std::fs::write(caminho.join("preservado.txt"), "preservado").unwrap();
        assert!(gravar_em(&caminho, &json!({"versao":1,"habilidades":[]})).is_err());
        assert_eq!(std::fs::read_to_string(caminho.join("preservado.txt")).unwrap(), "preservado");
        assert_eq!(std::fs::read_dir(pasta.path()).unwrap().count(), 1);
    }
}
