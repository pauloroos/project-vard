mod comandos;

use serde_json::Value;
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Emitter, Manager,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

const JANELA: &str = "hud";

fn alternar_visibilidade(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(JANELA) {
        if w.is_visible().unwrap_or(false) {
            let _ = w.hide();
        } else {
            let _ = w.show();
            let _ = w.set_focus();
        }
    }
}

fn atalho(config: &Value, chave: &str, padrao: &str) -> String {
    config
        .get("atalhos")
        .and_then(|a| a.get(chave))
        .and_then(|v| v.as_str())
        .unwrap_or(padrao)
        .to_string()
}

fn registrar_atalhos(app: &AppHandle, config: &Value) {
    let gs = app.global_shortcut();
    let falar = atalho(config, "falar", "Ctrl+Alt+Space");
    let parar = atalho(config, "parar", "Ctrl+Alt+Period");
    let mostrar = atalho(config, "mostrar", "Ctrl+Alt+V");

    let h = app.clone();
    if let Err(e) = gs.on_shortcut(falar.as_str(), move |_, _, ev| {
        let nome = match ev.state() {
            ShortcutState::Pressed => "ptt-inicio",
            ShortcutState::Released => "ptt-fim",
        };
        let _ = h.emit_to(JANELA, nome, ());
    }) {
        eprintln!("atalho falar ({falar}): {e}");
    }
    let h = app.clone();
    if let Err(e) = gs.on_shortcut(parar.as_str(), move |_, _, ev| {
        if ev.state() == ShortcutState::Pressed {
            let _ = h.emit_to(JANELA, "parar", ());
        }
    }) {
        eprintln!("atalho parar ({parar}): {e}");
    }
    let h = app.clone();
    if let Err(e) = gs.on_shortcut(mostrar.as_str(), move |_, _, ev| {
        if ev.state() == ShortcutState::Pressed {
            alternar_visibilidade(&h);
        }
    }) {
        eprintln!("atalho mostrar ({mostrar}): {e}");
    }
}

fn criar_bandeja(app: &AppHandle, no_topo: bool) -> tauri::Result<()> {
    let mostrar = MenuItem::with_id(app, "mostrar", "Mostrar/ocultar", true, None::<&str>)?;
    let topo = CheckMenuItem::with_id(app, "topo", "Sempre no topo", true, no_topo, None::<&str>)?;
    let config = MenuItem::with_id(app, "config", "Configurações", true, None::<&str>)?;
    let sair = MenuItem::with_id(app, "sair", "Sair", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&mostrar, &topo, &config, &sair])?;

    let topo_ref = topo.clone();
    let mut b = TrayIconBuilder::with_id("hud")
        .tooltip("OpenJarvis HUD")
        .menu(&menu)
        .on_menu_event(move |app, ev| match ev.id().as_ref() {
            "mostrar" => alternar_visibilidade(app),
            "topo" => {
                let ligado = topo_ref.is_checked().unwrap_or(true);
                if let Some(w) = app.get_webview_window(JANELA) {
                    let _ = w.set_always_on_top(ligado);
                }
                let _ = app.emit_to(JANELA, "sempre-no-topo", ligado);
            }
            "config" => {
                if let Some(w) = app.get_webview_window(JANELA) {
                    let _ = w.show();
                }
                let _ = app.emit_to(JANELA, "abrir-configuracoes", ());
            }
            "sair" => app.exit(0),
            _ => {}
        });
    if let Some(icone) = app.default_window_icon() {
        b = b.icon(icone.clone());
    }
    b.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            comandos::ler_config,
            comandos::gravar_config,
            comandos::definir_sempre_no_topo,
            comandos::definir_click_through,
            comandos::capturar_tela,
            comandos::abrir_url,
            comandos::inicio_no_logon_ativo,
            comandos::definir_inicio_no_logon
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let config = comandos::ler_config_valor(&handle).unwrap_or(Value::Null);
            let no_topo = config
                .get("sempre_no_topo")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            if let Some(w) = handle.get_webview_window(JANELA) {
                let _ = w.set_always_on_top(no_topo);
            }
            criar_bandeja(&handle, no_topo)?;
            registrar_atalhos(&handle, &config);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erro ao executar o openjarvis-hud");
}
