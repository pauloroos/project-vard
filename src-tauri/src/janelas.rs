// Janelas do Vard: o widget (hud), o painel de configurações e a sala. Funções puras testáveis no fim.
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

pub const HUD: &str = "hud";

/// Um monitor em pixels físicos, como o painel lista e como as contas usam.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct MonitorInfo {
    pub nome: String,
    pub x: i32,
    pub y: i32,
    pub largura: u32,
    pub altura: u32,
    pub escala: f64,
    pub principal: bool,
}

/// Converte o monitor do Tauri; `principal` é o nome do monitor principal, se conhecido.
pub fn info(m: &tauri::Monitor, principal: Option<&String>) -> MonitorInfo {
    let nome = m.name().cloned().unwrap_or_default();
    MonitorInfo {
        principal: principal.is_some_and(|p| *p == nome),
        x: m.position().x,
        y: m.position().y,
        largura: m.size().width,
        altura: m.size().height,
        escala: m.scale_factor(),
        nome,
    }
}

/// Posição (física) para uma janela `largura`x`altura` caber no monitor, mexendo o mínimo.
pub fn encaixar(x: i32, y: i32, largura: u32, altura: u32, m: &MonitorInfo) -> (i32, i32) {
    let max_x = m.x + m.largura as i32 - largura as i32;
    let max_y = m.y + m.altura as i32 - altura as i32;
    (x.min(max_x).max(m.x), y.min(max_y).max(m.y))
}

pub const CONFIG: &str = "configuracoes";

/// O que fazer com o painel quando o atalho dispara.
#[derive(Debug, PartialEq)]
pub enum AcaoJanela {
    Criar,
    Focar,
    Fechar,
}

/// Atalho do painel: cria se não existe, fecha se já está visível e na frente, senão traz para frente.
pub fn acao_do_atalho(existe: bool, visivel: bool, focada: bool) -> AcaoJanela {
    match (existe, visivel && focada) {
        (false, _) => AcaoJanela::Criar,
        (true, true) => AcaoJanela::Fechar,
        (true, false) => AcaoJanela::Focar,
    }
}

/// Abre o painel ou traz o que já existe para frente (nunca dois). Decorado, opaco, não sempre no topo.
pub fn abrir_configuracoes(app: &AppHandle) -> tauri::Result<()> {
    if let Some(w) = app.get_webview_window(CONFIG) {
        let _ = w.unminimize();
        w.show()?;
        w.set_focus()?;
        return Ok(());
    }
    WebviewWindowBuilder::new(app, CONFIG, WebviewUrl::App("configuracoes.html".into()))
        .title("Configurações - Vard")
        .inner_size(640.0, 720.0)
        .min_inner_size(520.0, 480.0)
        .decorations(true)
        .resizable(true)
        .always_on_top(false)
        .center()
        .build()?;
    Ok(())
}

/// Atalho `config`: abre, traz para frente ou fecha.
pub fn alternar_configuracoes(app: &AppHandle) {
    let w = app.get_webview_window(CONFIG);
    let (visivel, focada) = w
        .as_ref()
        .map(|w| (w.is_visible().unwrap_or(false), w.is_focused().unwrap_or(false)))
        .unwrap_or((false, false));
    let r = match acao_do_atalho(w.is_some(), visivel, focada) {
        AcaoJanela::Fechar => w.map(|w| w.close()).unwrap_or(Ok(())),
        AcaoJanela::Criar | AcaoJanela::Focar => abrir_configuracoes(app),
    };
    if let Err(e) = r {
        eprintln!("painel de configurações: {e}");
    }
}

pub const SALA: &str = "sala";

/// O widget só é escondido por nós se estava visível; assim, ao fechar a sala, não reaparece um widget que o usuário já tinha escondido.
static WIDGET_ESCONDIDO_PELA_SALA: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

/// Decisão pura: esconder o widget quando a sala abre apenas se ele está visível.
pub fn deve_esconder_widget(widget_visivel: bool) -> bool {
    widget_visivel
}

/// Esconde o widget (a janela segue viva: microfone, VAD e eventos continuam). Só mexe na visibilidade.
fn esconder_widget(app: &AppHandle) {
    if let Some(hud) = app.get_webview_window(HUD) {
        let visivel = hud.is_visible().unwrap_or(false);
        if deve_esconder_widget(visivel) {
            match hud.hide() {
                Ok(()) => {
                    WIDGET_ESCONDIDO_PELA_SALA.store(true, std::sync::atomic::Ordering::SeqCst);
                    eprintln!("[info] sala aberta: widget escondido (is_visible={})", hud.is_visible().unwrap_or(true));
                }
                Err(e) => eprintln!("[erro] não consegui esconder o widget: {e}"),
            }
        }
    }
}

/// Mostra o widget de volta (mesma posição: hide/show não move a janela) se foi a sala que o escondeu.
fn mostrar_widget(app: &AppHandle) {
    if !WIDGET_ESCONDIDO_PELA_SALA.swap(false, std::sync::atomic::Ordering::SeqCst) {
        return;
    }
    if let Some(hud) = app.get_webview_window(HUD) {
        match hud.show() {
            Ok(()) => eprintln!("[info] sala fechada: widget mostrado (is_visible={})", hud.is_visible().unwrap_or(false)),
            Err(e) => eprintln!("[erro] não consegui mostrar o widget de volta: {e}"),
        }
    }
}

/// Monitor da sala: o de nome `nome`; se ele sumiu (ou o nome é vazio), o principal. `true` = caiu no principal.
pub fn escolher_monitor(lista: &[MonitorInfo], nome: &str) -> Option<(usize, bool)> {
    if lista.is_empty() {
        return None;
    }
    if !nome.is_empty() {
        if let Some(i) = lista.iter().position(|m| m.nome == nome) {
            return Some((i, false));
        }
    }
    let i = lista.iter().position(|m| m.principal).unwrap_or(0);
    Some((i, !nome.is_empty()))
}

/// Abre a sala (tela cheia no monitor escolhido) ou fecha a que está aberta. Devolve um aviso quando o monitor sumiu.
pub fn alternar_sala(app: &AppHandle) -> Result<Option<String>, String> {
    if let Some(w) = app.get_webview_window(SALA) {
        w.close().map_err(|e| e.to_string())?;
        return Ok(None);
    }
    let hud = app.get_webview_window(HUD).ok_or("janela do widget não existe")?;
    let principal = hud.primary_monitor().map_err(|e| e.to_string())?.and_then(|m| m.name().cloned());
    let lista: Vec<MonitorInfo> = hud
        .available_monitors()
        .map_err(|e| e.to_string())?
        .iter()
        .map(|m| info(m, principal.as_ref()))
        .collect();
    let config = crate::comandos::ler_config_valor(app).unwrap_or(serde_json::Value::Null);
    let pedido = config.get("sala_monitor").and_then(|v| v.as_str()).unwrap_or("");
    let (i, caiu) = escolher_monitor(&lista, pedido).ok_or("nenhum monitor encontrado")?;
    let alvo = &lista[i];
    // Escondida até estar no lugar: posiciona no canto do monitor (físico), tela cheia nele, depois mostra.
    let w = WebviewWindowBuilder::new(app, SALA, WebviewUrl::App("sala.html".into()))
        .title("Vard - sala")
        .decorations(false)
        .skip_taskbar(true)
        .visible(false)
        .build()
        .map_err(|e| e.to_string())?;
    // O aviso de fechamento é ligado antes de posicionar: se algo falhar daqui em diante, o widget ainda fica sabendo.
    let h = app.clone();
    w.on_window_event(move |ev| {
        if let tauri::WindowEvent::Destroyed = ev {
            mostrar_widget(&h);
            let _ = h.emit_to(HUD, "sala-fechada", ());
        }
    });
    let posicionar = || -> tauri::Result<()> {
        w.set_position(tauri::PhysicalPosition::new(alvo.x, alvo.y))?;
        w.set_fullscreen(true)?;
        w.show()?;
        let _ = w.set_focus(); // Esc fecha: o teclado precisa estar na sala
        Ok(())
    };
    if let Err(e) = posicionar() {
        let _ = w.close(); // nada de janela invisível esquecida: o próximo atalho tenta de novo
        return Err(e.to_string());
    }
    esconder_widget(app); // só depois de a sala estar no lugar; se ela falhou, voltamos acima sem esconder
    // "Monitor N" como no painel (mesma ordem de available_monitors): o nome do sistema é algo como DISPLAY1 com prefixo.
    Ok(caiu.then(|| format!("O monitor escolhido não está conectado; a sala abriu no Monitor {}.", i + 1)))
}

/// Dock: a barra de botões fica em cima quando o centro da janela está abaixo do centro do monitor (pixels físicos).
pub fn metade_inferior(y: i32, altura: u32, mon_y: i32, mon_altura: u32) -> bool {
    let centro_janela = y as i64 * 2 + altura as i64; // 2 × centro, sem divisão
    let centro_monitor = mon_y as i64 * 2 + mon_altura as i64;
    centro_janela > centro_monitor
}

#[cfg(test)]
mod testes {
    use super::*;

    fn mon(nome: &str, x: i32, principal: bool) -> MonitorInfo {
        MonitorInfo { nome: nome.into(), x, y: 0, largura: 1920, altura: 1080, escala: 1.0, principal }
    }

    #[test]
    fn encaixar_dentro_nao_mexe() {
        assert_eq!(encaixar(100, 100, 320, 360, &mon("A", 0, true)), (100, 100));
    }

    #[test]
    fn encaixar_passou_da_borda() {
        assert_eq!(encaixar(1800, 900, 480, 540, &mon("A", 0, true)), (1440, 540));
        assert_eq!(encaixar(-100, 0, 480, 540, &mon("B", -1920, false)), (-480, 0));
    }

    #[test]
    fn encaixar_maior_que_o_monitor() {
        assert_eq!(encaixar(50, 50, 4000, 3000, &mon("A", 0, true)), (0, 0));
    }

    #[test]
    fn monitor_escolhido() {
        let l = [mon("DISPLAY1", 0, true), mon("DISPLAY2", 1920, false)];
        assert_eq!(escolher_monitor(&l, "DISPLAY2"), Some((1, false)));
        assert_eq!(escolher_monitor(&l, ""), Some((0, false)));
    }

    #[test]
    fn monitor_ausente_cai_no_principal() {
        let l = [mon("B", -1920, false), mon("A", 0, true)];
        assert_eq!(escolher_monitor(&l, "TV"), Some((1, true)));
    }

    #[test]
    fn esconde_widget_so_se_visivel() {
        assert!(deve_esconder_widget(true));
        assert!(!deve_esconder_widget(false));
    }

    #[test]
    fn sem_monitor() {
        assert_eq!(escolher_monitor(&[], "TV"), None);
    }

    #[test]
    fn atalho_do_painel() {
        assert_eq!(acao_do_atalho(false, false, false), AcaoJanela::Criar);
        assert_eq!(acao_do_atalho(true, true, true), AcaoJanela::Fechar);
        assert_eq!(acao_do_atalho(true, true, false), AcaoJanela::Focar);
        assert_eq!(acao_do_atalho(true, false, false), AcaoJanela::Focar);
    }

    #[test]
    fn metade_inferior_pelo_centro_da_janela() {
        // monitor 0..1080: centro em 540. Janela 360 de altura.
        assert!(!metade_inferior(0, 360, 0, 1080));      // centro 180
        assert!(metade_inferior(700, 360, 0, 1080));     // centro 880
        assert!(!metade_inferior(360, 360, 0, 1080));    // centro 540 = empate: em cima
        assert!(metade_inferior(-200, 360, -1080, 1080)); // monitor acima do principal
    }
}
