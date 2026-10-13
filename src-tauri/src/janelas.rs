// Janelas do Vard: o widget (hud), o painel de configurações e a sala. Funções puras testáveis no fim.
use serde::Serialize;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

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
    fn atalho_do_painel() {
        assert_eq!(acao_do_atalho(false, false, false), AcaoJanela::Criar);
        assert_eq!(acao_do_atalho(true, true, true), AcaoJanela::Fechar);
        assert_eq!(acao_do_atalho(true, true, false), AcaoJanela::Focar);
        assert_eq!(acao_do_atalho(true, false, false), AcaoJanela::Focar);
    }
}
