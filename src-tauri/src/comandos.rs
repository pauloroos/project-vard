use base64::Engine;
use serde::Serialize;
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
};

/// Ações com atalho global: chave em `atalhos` na config e o padrão. Mesma ordem de ACOES_ATALHO no front.
pub const ATALHOS: [(&str, &str); 5] = [
    ("falar", "Ctrl+Alt+Space"),
    ("parar", "Ctrl+Alt+Period"),
    ("mostrar", "Ctrl+Alt+V"),
    ("config", "Ctrl+Alt+Comma"),
    ("escuta", "Ctrl+Alt+E"),
];

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct FalhaAtalho {
    pub chave: String,
    pub combinacao: String,
    pub erro: String,
}

/// Atalhos que não registraram no arranque (combinação inválida ou já usada por outro programa).
#[derive(Default)]
pub struct FalhasDeAtalho(pub Mutex<Vec<FalhaAtalho>>);

/// Combinação da config para a ação `chave`, ou o padrão.
pub fn atalho_da_config(config: &Value, chave: &str, padrao: &str) -> String {
    config
        .get("atalhos")
        .and_then(|a| a.get(chave))
        .and_then(|v| v.as_str())
        .unwrap_or(padrao)
        .to_string()
}

/// Ok se o plugin global-shortcut entende a combinação (o mesmo parser do registro).
pub fn validar_combinacao(combinacao: &str) -> Result<(), String> {
    combinacao
        .parse::<tauri_plugin_global_shortcut::Shortcut>()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn validar_atalho(combinacao: String) -> Result<(), String> {
    validar_combinacao(&combinacao)
}

#[tauri::command]
pub fn falhas_de_atalho(estado: tauri::State<'_, FalhasDeAtalho>) -> Vec<FalhaAtalho> {
    estado.0.lock().map(|v| v.clone()).unwrap_or_default()
}

/// Caminho do arquivo de config dentro de um diretório (separado para ser testável).
pub fn caminho_em(dir: &Path) -> PathBuf {
    dir.join("hud.config.json")
}

pub fn caminho_config(app: &tauri::AppHandle) -> PathBuf {
    let dir = tauri::Manager::path(app)
        .app_config_dir()
        .expect("app_config_dir");
    fs::create_dir_all(&dir).ok();
    caminho_em(&dir)
}

/// Lê o JSON da config; devolve `Value::Null` se não existir.
pub fn ler_config_valor(app: &tauri::AppHandle) -> Result<Value, String> {
    let p = caminho_config(app);
    if !p.exists() {
        return Ok(Value::Null);
    }
    let txt = fs::read_to_string(&p).map_err(|e| e.to_string())?;
    match serde_json::from_str(&txt) {
        Ok(v) => Ok(v),
        Err(e) => {
            // Guarda o arquivo ilegível para o usuário e deixa o HUD subir com o padrão.
            let guardado = p.with_extension("json.invalido");
            let _ = fs::rename(&p, &guardado);
            Err(format!("hud.config.json inválido (guardado como {}): {e}", guardado.display()))
        }
    }
}

#[tauri::command]
pub fn ler_config(app: tauri::AppHandle) -> Result<Value, String> {
    ler_config_valor(&app)
}

#[tauri::command]
pub fn gravar_config(app: tauri::AppHandle, config: Value) -> Result<(), String> {
    let p = caminho_config(&app);
    let tmp = p.with_extension("json.tmp");
    fs::write(
        &tmp,
        serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    fs::rename(&tmp, &p).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn definir_sempre_no_topo(window: tauri::Window, ligado: bool) -> Result<(), String> {
    window.set_always_on_top(ligado).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn definir_click_through(window: tauri::Window, ligado: bool) -> Result<(), String> {
    window
        .set_ignore_cursor_events(ligado)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn abrir_url(url: String) -> Result<(), String> {
    if !(url.starts_with("http://") || url.starts_with("https://")) {
        return Err("so http(s) e permitido".into());
    }
    tauri_plugin_opener::open_url(url, None::<&str>).map_err(|e| e.to_string())
}

/// Pasta Startup do usuario (separada para ser testavel).
pub fn atalho_logon_em(appdata: &Path) -> PathBuf {
    appdata
        .join("Microsoft")
        .join("Windows")
        .join("Start Menu")
        .join("Programs")
        .join("Startup")
        .join("Vard.lnk")
}

fn atalho_logon() -> Result<PathBuf, String> {
    let appdata = std::env::var("APPDATA").map_err(|_| "APPDATA nao definido".to_string())?;
    Ok(atalho_logon_em(Path::new(&appdata)))
}

/// Informa se o HUD abre sozinho no logon (existe o .lnk na pasta Startup).
#[tauri::command]
pub fn inicio_no_logon_ativo() -> bool {
    atalho_logon().map(|p| p.exists()).unwrap_or(false)
}

/// Cria ou remove o atalho `Vard.lnk` na pasta Startup (WScript.Shell via PowerShell, sem janela).
#[tauri::command]
pub fn definir_inicio_no_logon(ligado: bool) -> Result<(), String> {
    let lnk = atalho_logon()?;
    if !ligado {
        if lnk.exists() {
            fs::remove_file(&lnk).map_err(|e| e.to_string())?;
        }
        return Ok(());
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().map(|p| p.to_path_buf()).unwrap_or_default();
    // Caminhos entram por variavel de ambiente: nada de aspas ou escapes na linha de comando.
    let script = "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:HUD_LNK);         $s.TargetPath = $env:HUD_EXE; $s.WorkingDirectory = $env:HUD_DIR;         $s.Description = 'OpenJarvis HUD'; $s.Save()";
    let mut cmd = std::process::Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-Command", script])
        .env("HUD_LNK", &lnk)
        .env("HUD_EXE", &exe)
        .env("HUD_DIR", &dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    if let Some(pai) = lnk.parent() {
        fs::create_dir_all(pai).ok();
    }
    let saida = cmd.output().map_err(|e| e.to_string())?;
    if !saida.status.success() || !lnk.exists() {
        return Err(String::from_utf8_lossy(&saida.stderr).trim().to_string());
    }
    Ok(())
}

/// Captura o monitor onde a janela está e devolve JPEG (qualidade 85) em base64.
#[tauri::command]
pub fn capturar_tela(window: tauri::Window) -> Result<String, String> {
    let pos = window.outer_position().map_err(|e| e.to_string())?;
    let monitores = xcap::Monitor::all().map_err(|e| e.to_string())?;
    let mut alvo = None;
    let mut primeiro = None;
    for m in monitores {
        let x = m.x().map_err(|e| e.to_string())?;
        let y = m.y().map_err(|e| e.to_string())?;
        let w = m.width().map_err(|e| e.to_string())? as i32;
        let h = m.height().map_err(|e| e.to_string())? as i32;
        if alvo.is_none() && pos.x >= x && pos.x < x + w && pos.y >= y && pos.y < y + h {
            alvo = Some(m);
        } else if primeiro.is_none() {
            primeiro = Some(m);
        }
    }
    let alvo = alvo.or(primeiro).ok_or("sem monitor")?;
    let img = alvo.capture_image().map_err(|e| e.to_string())?;
    let mut buf = std::io::Cursor::new(Vec::new());
    image::codecs::jpeg::JpegEncoder::new_with_quality(&mut buf, 85)
        .encode_image(&image::DynamicImage::ImageRgba8(img).to_rgb8())
        .map_err(|e| e.to_string())?;
    Ok(base64::engine::general_purpose::STANDARD.encode(buf.into_inner()))
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn padroes_de_atalho_sao_validos() {
        for (chave, padrao) in ATALHOS {
            assert!(validar_combinacao(padrao).is_ok(), "{chave}: {padrao}");
        }
    }

    #[test]
    fn teclas_que_o_front_gera_sao_aceitas_pelo_plugin() {
        // Saídas de normalizarAtalho (src/config/atalhos.ts): letras, dígitos, F1-F24, Numpad, nomeadas e sinais.
        let mut teclas: Vec<String> = ('A'..='Z').map(|c| c.to_string()).collect();
        teclas.extend(('0'..='9').map(|c| c.to_string()));
        teclas.extend((1..=24).map(|n| format!("F{n}")));
        teclas.extend((0..=9).map(|n| format!("Numpad{n}")));
        for t in [
            "Space", "Enter", "Tab", "Insert", "Delete", "Home", "End", "PageUp", "PageDown",
            "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Period", "Comma", "Minus", "Equal",
            "Slash", "Semicolon", "Quote", "Backquote", "BracketLeft", "BracketRight", "Backslash",
        ] {
            teclas.push(t.to_string());
        }
        for t in &teclas {
            for mods in ["Ctrl+Alt", "Shift+Super", "Ctrl+Alt+Shift+Super"] {
                let c = format!("{mods}+{t}");
                assert!(validar_combinacao(&c).is_ok(), "{c}");
            }
        }
    }

    #[test]
    fn padroes_do_rust_iguais_aos_do_front() {
        let ts = include_str!("../../src/config/config.ts");
        for (chave, padrao) in ATALHOS {
            let esperado = format!("{chave}: \"{padrao}\"");
            assert!(ts.contains(&esperado), "CONFIG_PADRAO.atalhos sem {esperado}");
        }
    }

    #[test]
    fn combinacao_invalida_e_recusada() {
        assert!(validar_combinacao("Ctrl+Alt+Banana").is_err());
        assert!(validar_combinacao("").is_err());
    }

    #[test]
    fn atalho_da_config_usa_salvo_ou_padrao() {
        let c = serde_json::json!({ "atalhos": { "escuta": "Ctrl+Shift+L" } });
        assert_eq!(atalho_da_config(&c, "escuta", "Ctrl+Alt+E"), "Ctrl+Shift+L");
        assert_eq!(atalho_da_config(&c, "config", "Ctrl+Alt+Comma"), "Ctrl+Alt+Comma");
        assert_eq!(atalho_da_config(&Value::Null, "falar", "Ctrl+Alt+Space"), "Ctrl+Alt+Space");
    }

    #[test]
    fn caminho_em_termina_em_hud_config_json() {
        let p = caminho_em(Path::new("/tmp/qualquer"));
        assert_eq!(p.file_name().unwrap(), "hud.config.json");
        assert!(p.starts_with("/tmp/qualquer"));
    }

    #[test]
    fn atalho_logon_fica_na_pasta_startup() {
        let p = atalho_logon_em(Path::new("/dados"));
        assert_eq!(p.file_name().unwrap(), "Vard.lnk");
        assert!(p.ends_with("Programs/Startup/Vard.lnk"));
    }
}
