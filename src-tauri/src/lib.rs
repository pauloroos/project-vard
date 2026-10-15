mod cofre;
mod comandos;
mod janelas;
pub mod supervisor;
pub mod servicos;
pub mod nucleo;
pub mod instalacao;

use serde_json::Value;
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Emitter, Manager,
};
use std::sync::Mutex;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

const JANELA: &str = janelas::HUD;

/// Itens de marca da bandeja, guardados para o painel poder mudar as marcas.
pub struct Bandeja {
    pub invisivel: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    pub nao_ouvir: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    pub nao_falar: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    /// Tarefas em andamento (o widget avisa): entra na dica da bandeja.
    pub tarefas: Mutex<u32>,
}

fn alternar_visibilidade(app: &AppHandle) {
    // Com o modo invisível ligado, o atalho e a bandeja só revelam ou escondem (o widget nunca é escondido de verdade).
    let invisivel = comandos::ler_config_valor(app)
        .ok()
        .and_then(|c| c.get("invisivel").and_then(|v| v.as_bool()))
        .unwrap_or(false);
    if invisivel {
        // Janela escondida por um hide() anterior: primeiro volta a existir, senão a revelação não se vê.
        if let Some(w) = app.get_webview_window(JANELA) {
            if !w.is_visible().unwrap_or(true) {
                let _ = w.show();
            }
        }
        let _ = app.emit_to(JANELA, "alternar-revelacao", ());
        return;
    }
    if let Some(w) = app.get_webview_window(JANELA) {
        if w.is_visible().unwrap_or(false) {
            let _ = w.hide();
        } else {
            let _ = w.show();
            let _ = w.set_focus();
        }
    }
}

/// Atalho e bandeja: alterna a sala; um problema (monitor sumiu, janela não abriu) vira aviso na linha de estado do widget.
fn alternar_sala_e_avisar(app: &AppHandle) {
    let aviso = match janelas::alternar_sala(app) {
        Ok(aviso) => aviso,
        Err(e) => Some(format!("Tela cheia não abriu: {e}")),
    };
    if let Some(texto) = aviso {
        let _ = app.emit_to(JANELA, "aviso", texto);
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
        ("naofalar", _) => { let _ = app.emit_to(JANELA, "alternar-fala", ()); }
        ("conversa", _) => { let _ = app.emit_to(JANELA, "alternar-conversa", ()); }
        ("config", _) => janelas::alternar_configuracoes(app),
        ("sala", _) => alternar_sala_e_avisar(app),
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

fn criar_bandeja(app: &AppHandle, no_topo: bool, invisivel_ligado: bool, nao_ouvir_ligado: bool, nao_falar_ligado: bool) -> tauri::Result<()> {
    let mostrar = MenuItem::with_id(app, "mostrar", "Mostrar/ocultar", true, None::<&str>)?;
    let nao_ouvir = CheckMenuItem::with_id(app, "nao_ouvir", "Não ouvir", true, nao_ouvir_ligado, None::<&str>)?;
    let nao_falar = CheckMenuItem::with_id(app, "nao_falar", "Não falar", true, nao_falar_ligado, None::<&str>)?;
    let topo = CheckMenuItem::with_id(app, "topo", "Sempre no topo", true, no_topo, None::<&str>)?;
    let invisivel = CheckMenuItem::with_id(app, "invisivel", "Modo invisível", true, invisivel_ligado, None::<&str>)?;
    let config = MenuItem::with_id(app, "config", "Configurações", true, None::<&str>)?;
    let sala = MenuItem::with_id(app, "sala", "Tela cheia", true, None::<&str>)?;
    let sair = MenuItem::with_id(app, "sair", "Sair", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&mostrar, &nao_ouvir, &nao_falar, &topo, &invisivel, &config, &sala, &sair])?;

    let topo_ref = topo.clone();
    let inv_ref = invisivel.clone();
    let ouvir_ref = nao_ouvir.clone();
    let falar_ref = nao_falar.clone();
    {
        let estado = app.state::<Bandeja>();
        if let Ok(mut g) = estado.invisivel.lock() {
            *g = Some(invisivel);
        }
        if let Ok(mut g) = estado.nao_ouvir.lock() {
            *g = Some(nao_ouvir);
        }
        if let Ok(mut g) = estado.nao_falar.lock() {
            *g = Some(nao_falar);
        }
    }
    let mut b = TrayIconBuilder::with_id("hud")
        .tooltip(comandos::texto_da_dica(nao_ouvir_ligado, nao_falar_ligado, 0))
        .menu(&menu)
        .on_menu_event(move |app, ev| match ev.id().as_ref() {
            "mostrar" => alternar_visibilidade(app),
            "nao_ouvir" => {
                let ligado = ouvir_ref.is_checked().unwrap_or(false);
                if let Err(e) = comandos::mesclar_config(app, serde_json::json!({ "nao_ouvir": ligado })) {
                    eprintln!("não ouvir: {e}");
                }
                let _ = app.emit_to(JANELA, "nao-ouvir", ligado);
                let _ = app.emit_to(janelas::CONFIG, "nao-ouvir", ligado);
                comandos::atualizar_dica_bandeja(app);
            }
            "nao_falar" => {
                let ligado = falar_ref.is_checked().unwrap_or(false);
                if let Err(e) = comandos::mesclar_config(app, serde_json::json!({ "nao_falar": ligado })) {
                    eprintln!("não falar: {e}");
                }
                let _ = app.emit_to(JANELA, "nao-falar", ligado);
                let _ = app.emit_to(janelas::CONFIG, "nao-falar", ligado);
                comandos::atualizar_dica_bandeja(app);
            }
            "topo" => {
                let ligado = topo_ref.is_checked().unwrap_or(true);
                if let Some(w) = app.get_webview_window(JANELA) {
                    let _ = w.set_always_on_top(ligado);
                }
                let _ = app.emit_to(JANELA, "sempre-no-topo", ligado);
                let _ = app.emit_to(janelas::CONFIG, "sempre-no-topo", ligado);
            }
            "invisivel" => {
                let ligado = inv_ref.is_checked().unwrap_or(false);
                if let Err(e) = comandos::mesclar_config(app, serde_json::json!({ "invisivel": ligado })) {
                    eprintln!("invisível: {e}");
                }
                let _ = app.emit_to(JANELA, "invisivel", ligado);
                let _ = app.emit_to(janelas::CONFIG, "invisivel", ligado);
            }
            "config" => {
                if let Err(e) = janelas::abrir_configuracoes(app) {
                    eprintln!("painel de configurações: {e}");
                }
            }
            "sala" => alternar_sala_e_avisar(app),
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
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // No modo invisível a segunda abertura só revela (a janela já está "mostrada", mas com
            // opacidade 0 e cliques bloqueados; show() sozinho não adianta, o widget tem que alternar).
            let invisivel = comandos::ler_config_valor(app)
                .ok()
                .and_then(|c| c.get("invisivel").and_then(|v| v.as_bool()))
                .unwrap_or(false);
            if invisivel {
                if let Some(w) = app.get_webview_window(JANELA) {
                    let _ = w.unminimize();
                }
                alternar_visibilidade(app);
                return;
            }
            if let Some(w) = app.get_webview_window(JANELA) {
                let _ = w.show();
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(comandos::FalhasDeAtalho::default())
        .manage(Bandeja {
            invisivel: Mutex::new(None),
            nao_ouvir: Mutex::new(None),
            nao_falar: Mutex::new(None),
            tarefas: Mutex::new(0),
        })
        .invoke_handler(tauri::generate_handler![
            comandos::ler_config,
            comandos::versao_do_app,
            comandos::buscar_release,
            comandos::instalar_atualizacao,
            comandos::gravar_config,
            comandos::ler_paineis,
            comandos::gravar_paineis,
            comandos::definir_sempre_no_topo,
            comandos::definir_click_through,
            comandos::capturar_tela,
            comandos::abrir_url,
            comandos::inicio_no_logon_ativo,
            comandos::definir_inicio_no_logon,
            comandos::validar_atalho,
            comandos::falhas_de_atalho,
            comandos::sondar_atalhos,
            comandos::redimensionar_janela,
            comandos::dock_em_cima,
            comandos::abrir_configuracoes,
            comandos::alternar_sala,
            comandos::listar_monitores,
            comandos::definir_invisivel,
            comandos::marcar_invisivel_na_bandeja,
            comandos::sincronizar_bandeja,
            comandos::definir_tarefas_bandeja,
            cofre::cofre_existe,
            cofre::cofre_gravar,
            cofre::cofre_apagar,
            cofre::cofre_ler
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            cofre::migrar_no_arranque(&handle);

            // T4: inicia serviços habilitados via instalacao.json
            {
                let recursos = handle.path().resource_dir().unwrap_or_default();
                let raiz = instalacao::resolver_raiz(&recursos);
                let dados = handle.path().app_data_dir().unwrap_or_else(|_| raiz.join("dados"));
                let arquivo = instalacao::arquivo_instalacao(&dados);
                let config_instalacao = instalacao::ler_instalacao(&arquivo).unwrap_or_default();
                let (_iniciados, avisos) = instalacao::iniciar_servicos(
                    &config_instalacao,
                    &recursos,
                    &raiz,
                    &dados,
                    env!("CARGO_PKG_VERSION"),
                );
                for aviso in &avisos {
                    eprintln!("instalacao: {aviso}");
                }
            }

            let config = comandos::ler_config_valor(&handle).unwrap_or(Value::Null);
            let no_topo = config
                .get("sempre_no_topo")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            if let Some(w) = handle.get_webview_window(JANELA) {
                let _ = w.set_always_on_top(no_topo);
            }
            let invisivel = config
                .get("invisivel")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let nao_ouvir = config
                .get("nao_ouvir")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let nao_falar = config
                .get("nao_falar")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            criar_bandeja(&handle, no_topo, invisivel, nao_ouvir, nao_falar)?;
            registrar_atalhos(&handle, &config);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erro ao executar o Vard");
}
