use base64::Engine;
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
};

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
    serde_json::from_str(&txt).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn ler_config(app: tauri::AppHandle) -> Result<Value, String> {
    ler_config_valor(&app)
}

#[tauri::command]
pub fn gravar_config(app: tauri::AppHandle, config: Value) -> Result<(), String> {
    let p = caminho_config(&app);
    fs::write(
        &p,
        serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
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
    fn caminho_em_termina_em_hud_config_json() {
        let p = caminho_em(Path::new("/tmp/qualquer"));
        assert_eq!(p.file_name().unwrap(), "hud.config.json");
        assert!(p.starts_with("/tmp/qualquer"));
    }
}
