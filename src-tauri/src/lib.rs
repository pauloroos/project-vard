#[cfg(not(test))]
mod bandeja;
mod cofre;
mod comandos;
mod diagnostico;
mod janelas;
pub mod supervisor;
pub mod servicos;
pub mod nucleo;
pub mod instalacao;
pub mod ciclo;

use serde_json::Value;
#[cfg(not(test))]
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem},
    tray::TrayIconBuilder,
};
use tauri::{AppHandle, Emitter, Manager};
#[cfg(not(test))]
use std::sync::Mutex;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

const JANELA: &str = janelas::HUD;

/// Itens de marca da bandeja, guardados para o painel poder mudar as marcas.
#[cfg(not(test))]
pub struct Bandeja {
    pub invisivel: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    pub nao_ouvir: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    pub nao_falar: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    /// Tarefas em andamento (o widget avisa): entra na dica da bandeja.
    pub tarefas: Mutex<u32>,
}

#[cfg(not(test))]
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
#[cfg(not(test))]
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
        #[cfg(not(test))]
        ("mostrar", _) => alternar_visibilidade(app),
        ("escuta", _) => { let _ = app.emit_to(JANELA, "alternar-escuta", ()); }
        ("naofalar", _) => { let _ = app.emit_to(JANELA, "alternar-fala", ()); }
        ("conversa", _) => { let _ = app.emit_to(JANELA, "alternar-conversa", ()); }
        ("config", _) => janelas::alternar_configuracoes(app),
        #[cfg(not(test))]
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

/// Cria a bandeja nativa. Com supervisor=true, monta menu dinâmico via itens_menu
/// e despacha ciclo_pedir; com supervisor=false, preserva o menu antigo estático.
#[cfg(not(test))]
fn criar_bandeja(app: &AppHandle, no_topo: bool, invisivel_ligado: bool, nao_ouvir_ligado: bool, nao_falar_ligado: bool, supervisor: bool) -> tauri::Result<()> {
    if supervisor {
        return criar_bandeja_supervisor(app, no_topo, invisivel_ligado, nao_ouvir_ligado, nao_falar_ligado);
    }
    // Menu antigo (supervisor=false): comportamento exato de antes da T8b
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

/// Bandeja com supervisor ativo: menu dinâmico reconstruído a cada ciclo-estado,
/// despacho de ciclo_pedir para verbos do ciclo e abertura de logs/janelas.
#[cfg(not(test))]
fn criar_bandeja_supervisor(app: &AppHandle, no_topo: bool, invisivel_ligado: bool, nao_ouvir_ligado: bool, nao_falar_ligado: bool) -> tauri::Result<()> {
    let foto_inicial = ciclo::ciclo_info(true);
    let itens = bandeja::itens_menu(&foto_inicial, nao_ouvir_ligado, nao_falar_ligado, no_topo, invisivel_ligado);
    let menu = montar_menu_supervisor(app, &itens)?;

    // Guarda referências dos checks para sincronização externa (busca por ID via get + downcast)
    {
        use tauri::menu::IsMenuItem;
        let estado = app.state::<Bandeja>();
        if let Ok(mut g) = estado.nao_ouvir.lock() {
            *g = menu.get("nao_ouvir").and_then(|i| i.as_check_menuitem().cloned());
        }
        if let Ok(mut g) = estado.nao_falar.lock() {
            *g = menu.get("nao_falar").and_then(|i| i.as_check_menuitem().cloned());
        }
        if let Ok(mut g) = estado.invisivel.lock() {
            *g = menu.get("invisivel").and_then(|i| i.as_check_menuitem().cloned());
        }
    }

    let mut b = TrayIconBuilder::with_id("hud")
        .tooltip(bandeja::dica(&foto_inicial, 0))
        .menu(&menu)
        .on_menu_event(move |app, ev| {
            dispatch_menu_supervisor(app, ev.id().as_ref());
        });
    if let Some(icone) = app.default_window_icon() {
        b = b.icon(icone.clone());
    }
    b.build(app)?;
    Ok(())
}

/// Constrói um Menu Tauri a partir dos ItemMenu do bandeja.rs.
#[cfg(not(test))]
fn montar_menu_supervisor(app: &AppHandle, itens: &[bandeja::ItemMenu]) -> tauri::Result<Menu<tauri::Wry>> {
    use tauri::menu::IsMenuItem;
    let mut filhos: Vec<Box<dyn IsMenuItem<tauri::Wry>>> = Vec::new();
    for item in itens {
        if item.id == "-" {
            filhos.push(Box::new(MenuItem::with_id(app, "-", "", false, None::<&str>)?));
            continue;
        }
        if let Some(marcado) = item.marcado {
            let check = CheckMenuItem::with_id(app, &item.id, &item.rotulo, item.ativo, marcado, None::<&str>)?;
            filhos.push(Box::new(check));
        } else {
            let mi = MenuItem::with_id(app, &item.id, &item.rotulo, item.ativo, None::<&str>)?;
            filhos.push(Box::new(mi));
        }
    }
    let refs: Vec<&dyn IsMenuItem<tauri::Wry>> = filhos.iter().map(|b| b.as_ref()).collect();
    Menu::with_items(app, &refs)
}

/// Despacha clique do menu supervisor: verbos do ciclo vão para a fila;
/// janelas/logs são abertos diretamente; em jogo, itens desabilitados não disparam.
#[cfg(not(test))]
fn dispatch_menu_supervisor(app: &AppHandle, id: &str) {
    match id {
        // Verbos do ciclo → fila serial
        "jogo" | "voltar" | "tentar" => {
            let _ = ciclo::ciclo_pedir(id);
        }
        "sair" => {
            // Sair pede à fila; o executor encerra jobs/servidor e termina o pai.
            let _ = ciclo::ciclo_pedir("sair");
        }
        // Janelas e configuração
        "config" => {
            if let Err(e) = janelas::abrir_configuracoes(app) {
                eprintln!("painel de configurações: {e}");
            }
        }
        "sala" => alternar_sala_e_avisar(app),
        "mostrar" => alternar_visibilidade(app),
        // Checks de estado
        "nao_ouvir" => {
            let estado = app.state::<Bandeja>();
            let ligado = estado.nao_ouvir.lock().ok()
                .and_then(|g| g.as_ref().and_then(|i| i.is_checked().ok()))
                .unwrap_or(false);
            if let Err(e) = comandos::mesclar_config(app, serde_json::json!({ "nao_ouvir": ligado })) {
                eprintln!("não ouvir: {e}");
            }
            let _ = app.emit_to(JANELA, "nao-ouvir", ligado);
            let _ = app.emit_to(janelas::CONFIG, "nao-ouvir", ligado);
        }
        "nao_falar" => {
            let estado = app.state::<Bandeja>();
            let ligado = estado.nao_falar.lock().ok()
                .and_then(|g| g.as_ref().and_then(|i| i.is_checked().ok()))
                .unwrap_or(false);
            if let Err(e) = comandos::mesclar_config(app, serde_json::json!({ "nao_falar": ligado })) {
                eprintln!("não falar: {e}");
            }
            let _ = app.emit_to(JANELA, "nao-falar", ligado);
            let _ = app.emit_to(janelas::CONFIG, "nao-falar", ligado);
        }
        "topo" => {
            // Topo não está no Bandeja state; alterna baseado na janela atual
            if let Some(w) = app.get_webview_window(JANELA) {
                let atual = w.is_always_on_top().unwrap_or(false);
                let _ = w.set_always_on_top(!atual);
                let _ = app.emit_to(JANELA, "sempre-no-topo", !atual);
                let _ = app.emit_to(janelas::CONFIG, "sempre-no-topo", !atual);
            }
        }
        "invisivel" => {
            let estado = app.state::<Bandeja>();
            let ligado = estado.invisivel.lock().ok()
                .and_then(|g| g.as_ref().and_then(|i| i.is_checked().ok()))
                .unwrap_or(false);
            if let Err(e) = comandos::mesclar_config(app, serde_json::json!({ "invisivel": ligado })) {
                eprintln!("invisível: {e}");
            }
            let _ = app.emit_to(JANELA, "invisivel", ligado);
            let _ = app.emit_to(janelas::CONFIG, "invisivel", ligado);
        }
        "log" => {
            // Abre log do serviço com falha ou ciclo.log como fallback
            let dados = ciclo::pasta_dados();
            let ciclo_log = dados.join("ciclo.log");
            let alvo = if ciclo_log.exists() { ciclo_log } else { dados.join("estado.json") };
            if let Err(e) = comandos::abrir_log(&alvo) {
                eprintln!("abrir log: {e}");
            }
        }
        _ => {}
    }
}

/// Reconstrói o menu da bandeja supervisor com base no novo estado do ciclo.
/// Chamada pelo evento ciclo-estado quando supervisor está ativo.
#[cfg(not(test))]
pub fn reconstruir_menu_bandeja(app: &AppHandle, foto: &ciclo::FotoCiclo) {
    use tauri::Manager;
    let Some(icone) = app.tray_by_id("hud") else { return };
    let estado = app.state::<Bandeja>();
    let (nao_ouvir, nao_falar, tarefas) = (
        estado.nao_ouvir.lock().ok()
            .and_then(|g| g.as_ref().and_then(|i| i.is_checked().ok()))
            .unwrap_or(false),
        estado.nao_falar.lock().ok()
            .and_then(|g| g.as_ref().and_then(|i| i.is_checked().ok()))
            .unwrap_or(false),
        estado.tarefas.lock().map(|g| *g).unwrap_or(0),
    );
    // Lê topo/invisivel da config atual
    let cfg = comandos::ler_config_valor(app).unwrap_or(Value::Null);
    let topo = cfg.get("sempre_no_topo").and_then(|v| v.as_bool()).unwrap_or(true);
    let invisivel = cfg.get("invisivel").and_then(|v| v.as_bool()).unwrap_or(false);

    let itens = bandeja::itens_menu(foto, nao_ouvir, nao_falar, topo, invisivel);
    if let Ok(menu) = montar_menu_supervisor(app, &itens) {
        let _ = icone.set_menu(Some(menu));
    }
    let _ = icone.set_tooltip(Some(bandeja::dica(foto, tarefas)));
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
                #[cfg(not(test))]
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
        .invoke_handler(tauri::generate_handler![
            comandos::ler_config,
            comandos::versao_do_app,
            comandos::buscar_release,
            comandos::instalar_atualizacao,
            comandos::gravar_config,
            comandos::ler_paineis,
            comandos::gravar_paineis,
            comandos::ler_perfil,
            comandos::gravar_perfil,
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
            #[cfg(not(test))]
            comandos::marcar_invisivel_na_bandeja,
            #[cfg(not(test))]
            comandos::sincronizar_bandeja,
            #[cfg(not(test))]
            comandos::definir_tarefas_bandeja,
            cofre::cofre_existe,
            cofre::cofre_gravar,
            cofre::cofre_apagar,
            cofre::cofre_ler,
            ciclo::cmd_ciclo_info,
            ciclo::cmd_ciclo_pedir,
            diagnostico::rodar_diagnostico,
            diagnostico::cancelar_diagnostico
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            cofre::migrar_no_arranque(&handle);

            // T4: inicia serviços habilitados via instalacao.json
            let recursos = handle.path().resource_dir().unwrap_or_default();
            let raiz = instalacao::resolver_raiz(&recursos);
            let dados = ciclo::pasta_dados();
            let arquivo = instalacao::arquivo_instalacao();
            let config_instalacao = instalacao::ler_instalacao(&arquivo).unwrap_or_default();
            {
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
let supervisor = config_instalacao.supervisor;
            #[cfg(not(test))]
            criar_bandeja(&handle, no_topo, invisivel, nao_ouvir, nao_falar, supervisor)?;
            registrar_atalhos(&handle, &config);

            // T8: registra AppHandle para emissão de eventos e inicializa ciclo se supervisor ativo
            ciclo::registrar_app_handle(handle.clone());
            if config_instalacao.supervisor {
                let sessao = format!("{}-{}", std::process::id(), chrono::Utc::now().timestamp_millis());
                ciclo::inicializar_fila(&sessao);
                ciclo::iniciar_executor_da_fila();
                ciclo::iniciar_consumidor_da_caixa();
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erro ao executar o Vard");
}
