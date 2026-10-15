//! Bandeja nativa do Vard (T8): cor, dica e menu baseados no EstadoCiclo.
//!
//! Contrato:
//! - Gate `supervisor`: só ativa quando instalacao.json tem supervisor=true.
//! - Menu estável: Configurações; Ouvir/Falar marcáveis; Sala; Janela; separador;
//!   Modo jogo/Voltar conforme estado; Abrir log; Tentar de novo quando falhou;
//!   separador; Sair.
//! - Em jogo: Configurações/Sala/escuta desabilitadas; Voltar/log/Sair continuam nativos.
//! - Log abre ciclo.log ou log do serviço com falha.
//! - Tentar em liberação repete liberação, no retorno repete pendências, parado repete início.
//! - Uma notificação por motivo novo, sem repetir a cada sonda.
//! - Não inicia serviço, não carrega modelo, não toca em OpenJarvis/LM Studio/voz/reuniao.

use serde::{Deserialize, Serialize};
use crate::ciclo::FotoCiclo;

/// Cores do ponto de estado (RGBA).
pub const AMARELO: [u8; 3] = [242, 177, 52];
pub const CINZA: [u8; 3] = [90, 90, 90];
pub const VERMELHO: [u8; 3] = [200, 40, 40];
pub const VERMELHO_ESCURO: [u8; 3] = [120, 40, 40];
const BORDA: [u8; 3] = [20, 20, 20];

/// Item do menu; id "-" é separador.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ItemMenu {
    pub id: String,
    pub rotulo: String,
    pub ativo: bool,
    pub marcado: Option<bool>,
}

impl ItemMenu {
    fn novo(id: &str, rotulo: &str) -> Self {
        Self { id: id.into(), rotulo: rotulo.into(), ativo: true, marcado: None }
    }
    fn desativado(mut self) -> Self {
        self.ativo = false;
        self
    }
    fn marcavel(mut self, marcado: bool) -> Self {
        self.marcado = Some(marcado);
        self
    }
    fn separador() -> Self {
        Self::novo("-", "").desativado()
    }
}

/// Cor do ponto de estado baseada no modo do ciclo.
pub fn cor_do_modo(foto: &FotoCiclo) -> Option<[u8; 3]> {
    if foto.modo == "erro" {
        return Some(VERMELHO);
    }
    match foto.modo.as_str() {
        "ligado" | "liberando" => Some(AMARELO),
        "jogo" => Some(CINZA),
        "parado" => Some(VERMELHO_ESCURO),
        _ => Some(CINZA),
    }
}

/// Dica (tooltip) da bandeja baseada no estado do ciclo.
pub fn dica(foto: &FotoCiclo, tarefas: u32) -> String {
    let base = if foto.modo == "erro" {
        let detalhe = foto.detalhe.as_deref().unwrap_or("sem detalhe");
        format!("Vard: erro: {}", detalhe)
    } else {
        format!("Vard: {}", foto.modo)
    };
    let com_tarefas = if tarefas > 0 {
        format!("{} · {} tarefa(s)", base, tarefas)
    } else {
        base
    };
    // Windows corta tooltip em 128 chars
    if com_tarefas.len() > 120 {
        format!("{}…", &com_tarefas[..117])
    } else {
        com_tarefas
    }
}

/// Constrói os itens do menu baseado no estado do ciclo.
/// `nao_ouvir`/`nao_falar`/`topo`/`invisivel` são estados atuais dos checks.
pub fn itens_menu(
    foto: &FotoCiclo,
    nao_ouvir: bool,
    nao_falar: bool,
    topo: bool,
    invisivel: bool,
) -> Vec<ItemMenu> {
    let em_jogo = foto.modo == "jogo";
    let mut itens = Vec::new();

    // Configurações (desabilitado em jogo)
    let mut config = ItemMenu::novo("config", "Configurações");
    if em_jogo { config = config.desativado(); }
    itens.push(config);

    // Ouvir/Falar marcáveis (desabilitados em jogo)
    let mut ouvir = ItemMenu::novo("nao_ouvir", "Não ouvir").marcavel(nao_ouvir);
    let mut falar = ItemMenu::novo("nao_falar", "Não falar").marcavel(nao_falar);
    if em_jogo {
        ouvir = ouvir.desativado();
        falar = falar.desativado();
    }
    itens.push(ouvir);
    itens.push(falar);

    // Sala (desabilitado em jogo)
    let mut sala = ItemMenu::novo("sala", "Sala (tela cheia)");
    if em_jogo { sala = sala.desativado(); }
    itens.push(sala);

    // Janela submenu (sempre disponível)
    itens.push(ItemMenu::novo("mostrar", "Mostrar/ocultar"));
    itens.push(ItemMenu::novo("topo", "Sempre no topo").marcavel(topo));
    itens.push(ItemMenu::novo("invisivel", "Modo invisível").marcavel(invisivel));

    itens.push(ItemMenu::separador());

    // Dinâmicos baseados no estado
    if foto.modo == "ligado" {
        itens.push(ItemMenu::novo("jogo", "Modo jogo"));
    }
    if ["jogo", "parado", "liberando"].contains(&foto.modo.as_str()) {
        let rotulo = if foto.modo == "liberando" { "Voltando..." } else { "Voltar" };
        let mut voltar = ItemMenu::novo("voltar", rotulo);
        if foto.modo == "liberando" { voltar = voltar.desativado(); }
        itens.push(voltar);
    }
    if foto.modo == "erro" {
        itens.push(ItemMenu::novo("tentar", "Tentar de novo"));
        itens.push(ItemMenu::novo("log", "Abrir log"));
    }

    itens.push(ItemMenu::separador());
    itens.push(ItemMenu::novo("sair", "Sair"));

    itens
}

/// Pinta o ponto de estado sobre uma cópia do RGBA (`lado`×`lado`).
/// Com `cinza` (modo jogo), o resto vai para tons de cinza.
pub fn pintar_estado(rgba: &[u8], lado: u32, cor: Option<[u8; 3]>, cinza: bool) -> Vec<u8> {
    let mut saida = rgba.to_vec();
    if saida.len() != (lado as usize) * (lado as usize) * 4 {
        return saida;
    }
    for y in 0..lado {
        for x in 0..lado {
            let i = ((y * lado + x) * 4) as usize;
            match (cor, ponto(lado, x, y)) {
                (Some(c), Some(borda)) => {
                    let t = if borda { BORDA } else { c };
                    saida[i..i + 3].copy_from_slice(&t);
                    saida[i + 3] = 255;
                }
                _ if cinza => {
                    let g = (0.299 * saida[i] as f32
                        + 0.587 * saida[i + 1] as f32
                        + 0.114 * saida[i + 2] as f32)
                        .round() as u8;
                    saida[i] = g;
                    saida[i + 1] = g;
                    saida[i + 2] = g;
                }
                _ => {}
            }
        }
    }
    saida
}

/// Geometria do ponto: círculo no canto inferior direito.
/// `None` = fora; `Some(true)` = contorno.
fn ponto(lado: u32, x: u32, y: u32) -> Option<bool> {
    let l = lado as f32;
    let (cx, cy, r) = (l * 0.75, l * 0.75, l * 0.25);
    let (dx, dy) = (x as f32 + 0.5 - cx, y as f32 + 0.5 - cy);
    let d = (dx * dx + dy * dy).sqrt();
    if d > r {
        None
    } else {
        Some(d > r - (l / 16.0).max(1.0))
    }
}

/// Verifica se deve emitir notificação de erro (motivo novo).
pub fn deve_notificar_erro(anterior: Option<&str>, atual: &FotoCiclo) -> bool {
    if atual.modo != "erro" {
        return false;
    }
    match anterior {
        None => true,
        Some(prev) => prev != atual.detalhe.as_deref().unwrap_or(""),
    }
}

/// Atualiza a bandeja nativa (tooltip) com base no estado do ciclo.
/// Chamada pelo ciclo após cada transição de estado quando supervisor está ativo.
/// O ícone é atualizado via set_tooltip apenas; a cor do ponto será aplicada
/// quando houver recurso de ícone base carregado (placeholder atual).
#[cfg(not(test))]
pub fn atualizar_bandeja_nativa(app: &tauri::AppHandle, foto: &FotoCiclo) {
    use tauri::Manager;
    let Some(icone) = app.tray_by_id("hud") else {
        return;
    };
    // Tooltip reflete modo/erro e tarefas
    let tarefas = app
        .state::<crate::Bandeja>()
        .tarefas
        .lock()
        .map(|g| *g)
        .unwrap_or(0);
    let _ = icone.set_tooltip(Some(dica(foto, tarefas)));
}

#[cfg(test)]
mod testes {
    use super::*;
    use crate::ciclo::FotoCiclo;

    fn foto(modo: &str) -> FotoCiclo {
        FotoCiclo {
            modo: modo.into(),
            desde: String::new(),
            detalhe: None,
            servicos_ligados: vec![],
            supervisor_ativo: true,
        }
    }

    #[test]
    fn cor_ligado_e_amarelo() {
        assert_eq!(cor_do_modo(&foto("ligado")), Some(AMARELO));
    }

    #[test]
    fn cor_jogo_e_cinza() {
        assert_eq!(cor_do_modo(&foto("jogo")), Some(CINZA));
    }

    #[test]
    fn cor_parado_e_vermelho_escuro() {
        assert_eq!(cor_do_modo(&foto("parado")), Some(VERMELHO_ESCURO));
    }

    #[test]
    fn cor_erro_e_vermelho() {
        assert_eq!(cor_do_modo(&foto("erro")), Some(VERMELHO));
    }

    #[test]
    fn dica_erro_inclui_detalhe() {
        let mut f = foto("erro");
        f.detalhe = Some("núcleo parou".into());
        let d = dica(&f, 0);
        assert!(d.contains("erro"));
        assert!(d.contains("núcleo parou"));
    }

    #[test]
    fn dica_com_tarefas() {
        let d = dica(&foto("ligado"), 3);
        assert!(d.contains("3 tarefa(s)"));
    }

    #[test]
    fn dica_longa_truncada() {
        let mut f = foto("erro");
        f.detalhe = Some("x".repeat(200));
        let d = dica(&f, 0);
        assert!(d.len() <= 121);
        assert!(d.ends_with('…'));
    }

    #[test]
    fn menu_ligado_tem_jogo() {
        let itens = itens_menu(&foto("ligado"), false, false, true, false);
        assert!(itens.iter().any(|i| i.id == "jogo" && i.ativo));
    }

    #[test]
    fn menu_jogo_desabilita_config_sala() {
        let itens = itens_menu(&foto("jogo"), false, false, true, false);
        let config = itens.iter().find(|i| i.id == "config").unwrap();
        let sala = itens.iter().find(|i| i.id == "sala").unwrap();
        assert!(!config.ativo);
        assert!(!sala.ativo);
        // Voltar continua ativo
        let voltar = itens.iter().find(|i| i.id == "voltar").unwrap();
        assert!(voltar.ativo);
    }

    #[test]
    fn menu_erro_tem_tentar_e_log() {
        let itens = itens_menu(&foto("erro"), false, false, true, false);
        assert!(itens.iter().any(|i| i.id == "tentar"));
        assert!(itens.iter().any(|i| i.id == "log"));
    }

    #[test]
    fn menu_sempre_tem_sair() {
        for modo in &["ligado", "jogo", "parado", "erro", "liberando"] {
            let itens = itens_menu(&foto(modo), false, false, true, false);
            assert!(itens.iter().any(|i| i.id == "sair" && i.ativo));
        }
    }

    #[test]
    fn pintar_estado_aplica_cor() {
        // Grade 4x4 é pequena demais para o círculo (raio 25% = 1px, centro em 75% = 3,3);
        // usa 16x16 para garantir pixels dentro da geometria do ponto.
        let lado = 16u32;
        let rgba = vec![0u8; (lado * lado * 4) as usize];
        let pintado = pintar_estado(&rgba, lado, Some(AMARELO), false);
        let tem_amarelo = (0..pintado.len()).step_by(4).any(|i| {
            pintado[i] == AMARELO[0] && pintado[i + 1] == AMARELO[1] && pintado[i + 2] == AMARELO[2]
        });
        assert!(tem_amarelo);
    }

    #[test]
    fn pintar_estado_cinza_em_jogo() {
        let lado = 4u32;
        let mut rgba = vec![0u8; (lado * lado * 4) as usize];
        // Preenche com vermelho
        for i in (0..rgba.len()).step_by(4) {
            rgba[i] = 255; rgba[i+1] = 0; rgba[i+2] = 0; rgba[i+3] = 255;
        }
        let pintado = pintar_estado(&rgba, lado, None, true);
        // Todos os pixels devem estar em tons de cinza (R==G==B)
        let todos_cinza = (0..pintado.len()).step_by(4).all(|i| {
            pintado[i] == pintado[i+1] && pintado[i+1] == pintado[i+2]
        });
        assert!(todos_cinza);
    }

    #[test]
    fn deve_notificar_erro_novo() {
        let mut f = foto("erro");
        f.detalhe = Some("falha nova".into());
        assert!(deve_notificar_erro(None, &f));
        assert!(deve_notificar_erro(Some("falha antiga"), &f));
        assert!(!deve_notificar_erro(Some("falha nova"), &f));
    }

    #[test]
    fn nao_notifica_se_nao_erro() {
        let f = foto("ligado");
        assert!(!deve_notificar_erro(None, &f));
    }
}