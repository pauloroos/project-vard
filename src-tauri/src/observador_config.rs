//! Sondagem a cada segundo, com comparação de conteúdo e supressão da gravação própria.
use serde_json::Value;
use std::{collections::HashMap, fs, io::Write, path::{Path, PathBuf}, sync::{Mutex, OnceLock}, time::Duration};
use tauri::{Emitter, Manager};

#[derive(Default)]
struct Observador {
    arquivos: Vec<(PathBuf, &'static str)>,
    ultimos: HashMap<PathBuf, Option<Vec<u8>>>,
}

impl Observador {
    fn novo(arquivos: Vec<(PathBuf, &'static str)>) -> Self {
        let ultimos = arquivos.iter().map(|(p, _)| (p.clone(), fs::read(p).ok())).collect();
        Self { arquivos, ultimos }
    }

    fn sondar(&mut self) -> Vec<(&'static str, Value)> {
        let mut eventos = Vec::new();
        for (p, evento) in &self.arquivos {
            let atual = fs::read(p).ok();
            if self.ultimos.get(p) == Some(&atual) { continue; }
            // Um temporário incompleto não muda a última versão válida.
            if let Some(bytes) = &atual {
                if let Ok(valor) = serde_json::from_slice::<Value>(bytes) {
                    if valor.is_object() {
                        if *evento == "habilidades-mudaram" && crate::habilidades::validar_habilidades(&valor).is_err() { continue; }
                        self.ultimos.insert(p.clone(), atual);
                        eventos.push((*evento, valor));
                    }
                }
            }
        }
        eventos
    }

    fn gravar(&mut self, p: &Path, valor: &Value) -> Result<(), String> {
        let pasta = p.parent().ok_or("Pasta de configuração inválida")?;
        fs::create_dir_all(pasta).map_err(|_| "Não foi possível criar a pasta de configuração")?;
        let tmp = pasta.join(format!("config.{}.tmp", uuid::Uuid::new_v4()));
        let resultado: Result<(), &str> = (|| {
            let bytes = serde_json::to_vec_pretty(valor).map_err(|_| "Configuração inválida")?;
            let mut arq = fs::OpenOptions::new().write(true).create_new(true).open(&tmp).map_err(|_| "Não foi possível preparar a gravação")?;
            arq.write_all(&bytes).map_err(|_| "Não foi possível gravar a configuração")?;
            arq.sync_all().map_err(|_| "Não foi possível sincronizar a configuração")?;
            drop(arq);
            fs::rename(&tmp, p).map_err(|_| "Não foi possível substituir a configuração")?;
            self.ultimos.insert(p.to_path_buf(), Some(bytes));
            Ok(())
        })();
        let _ = fs::remove_file(tmp);
        resultado.map_err(String::from)
    }
}

fn estado() -> &'static Mutex<Observador> {
    static ESTADO: OnceLock<Mutex<Observador>> = OnceLock::new();
    ESTADO.get_or_init(|| Mutex::new(Observador::default()))
}

pub fn gravar(p: &Path, valor: &Value) -> Result<(), String> {
    estado().lock().map_err(|_| "Observador indisponível")?.gravar(p, valor)
}

pub fn iniciar(app: tauri::AppHandle) {
    let pasta = crate::ciclo::pasta_config();
    let arquivos = vec![
        (crate::comandos::caminho_config(&app), "config-salva"),
        (pasta.join("paineis.json"), "paineis-mudaram"),
        (pasta.join("habilidades.json"), "habilidades-mudaram"),
        (pasta.join("perfil.json"), "perfil-mudou"),
    ];
    *estado().lock().expect("observador") = Observador::novo(arquivos);
    std::thread::spawn(move || {
        while app.get_webview_window("hud").is_some() {
            std::thread::sleep(Duration::from_secs(1));
            let eventos = estado().lock().map(|mut e| e.sondar()).unwrap_or_default();
            for (nome, valor) in eventos { let _ = app.emit(nome, valor); }
        }
    });
}

#[cfg(test)]
mod testes {
    use super::*;
    use serde_json::json;

    #[test]
    fn alteracao_externa_emite_evento_uma_vez() {
        let pasta = tempfile::tempdir().unwrap();
        let p = pasta.path().join("hud.config.json");
        std::fs::write(&p, r##"{"cor_elementos":"#112233"}"##).unwrap();
        let mut observador = Observador::novo(vec![(p.clone(), "config-salva")]);
        assert!(observador.sondar().is_empty());
        std::fs::write(&p, r##"{"cor_elementos":"#334455"}"##).unwrap();
        assert_eq!(observador.sondar(), vec![("config-salva", json!({"cor_elementos":"#334455"}))]);
        assert!(observador.sondar().is_empty());
    }

    #[test]
    fn gravacao_propria_nao_produz_eco_e_externa_seguinte_aparece() {
        let pasta = tempfile::tempdir().unwrap();
        let p = pasta.path().join("paineis.json");
        let mut observador = Observador::novo(vec![(p.clone(), "paineis-mudaram")]);
        observador.gravar(&p, &json!({"ativo":"local"})).unwrap();
        assert!(observador.sondar().is_empty());
        std::fs::write(&p, r#"{"ativo":"outro"}"#).unwrap();
        assert_eq!(observador.sondar(), vec![("paineis-mudaram", json!({"ativo":"outro"}))]);
    }

    #[test]
    fn arquivo_invalido_nao_emite_e_troca_atomica_e_detectada() {
        let pasta = tempfile::tempdir().unwrap();
        let p = pasta.path().join("habilidades.json");
        let mut observador = Observador::novo(vec![(p.clone(), "habilidades-mudaram")]);
        std::fs::write(&p, "{").unwrap();
        assert!(observador.sondar().is_empty());
        let tmp = pasta.path().join("externo.tmp");
        std::fs::write(&tmp, r#"{"versao":1,"habilidades":[]}"#).unwrap();
        std::fs::rename(tmp, &p).unwrap();
        assert_eq!(observador.sondar().len(), 1);
    }
}
