mod comandos;
mod janelas;

use serde_json::Value;
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Emitter, Manager,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

const JANELA: &str = janelas::HUD;

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

fn acionar(app: &AppHandle, chave: &str, estado: ShortcutState) {
    match (chave, estado) {
        ("falar", ShortcutState::Pressed) => { let _ = app.emit_to(JANELA, "ptt-inicio", ()); }
        ("falar", ShortcutState::Released) => { let _ = app.emit_to(JANELA, "ptt-fim", ()); }
        (_, ShortcutState::Released) => {}
        ("parar", _) => { let _ = app.emit_to(JANELA, "parar", ()); }
        ("mostrar", _) => alternar_visibilidade(app),
        ("escuta", _) => { let _ = app.emit_to(JANELA, "alternar-escuta", ()); }
        ("config", _) => janelas::alternar_configuracoes(app),
        _ => {}
    }
}

fn registrar_atalhos(app: &AppHandle, config: &Value) {
    let gs = app.global_shortcut();
    for (chave, padrao) in comandos::ATALHOS {
        let combinacao = comandos::atalho_da_config(config, chave, padrao);
        let h = app.clone();
        if let Err(e) = gs.on_shortcut(combinacao.as_str(), move |_, _, ev| acionar(&h, chave, ev.state())) {
            eprintln!("atalho {chave} ({combinacao}): {e}");
            if let Ok(mut falhas) = app.state::<comandos::FalhasDeAtalho>().0.lock() {
                falhas.push(comandos::FalhaAtalho { chave: chave.to_string(), combinacao: combinacao.clone(), erro: e.to_string() });
            }
        }
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
        .tooltip("Vard")
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
                if let Err(e) = janelas::abrir_configuracoes(app) {
                    eprintln!("painel de configurações: {e}");
                }
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
        .manage(comandos::FalhasDeAtalho::default())
        .invoke_handler(tauri::generate_handler![
            comandos::ler_config,
            comandos::gravar_config,
            comandos::definir_sempre_no_topo,
            comandos::definir_click_through,
            comandos::capturar_tela,
            comandos::abrir_url,
            comandos::inicio_no_logon_ativo,
            comandos::definir_inicio_no_logon,
            comandos::validar_atalho,
            comandos::falhas_de_atalho,
            comandos::redimensionar_janela,
            comandos::abrir_configuracoes
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
        .expect("erro ao executar o Vard");
}
