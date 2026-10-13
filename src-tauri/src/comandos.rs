use base64::Engine;
use serde::Serialize;
use serde_json::Value;
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    sync::Mutex,
};

/// Ações com atalho global: chave em `atalhos` na config e o padrão. Mesma ordem de ACOES_ATALHO no front.
pub const ATALHOS: [(&str, &str); 6] = [
    ("falar", "Ctrl+Alt+Space"),
    ("parar", "Ctrl+Alt+Period"),
    ("mostrar", "Ctrl+Alt+V"),
    ("config", "Ctrl+Alt+P"),
    ("escuta", "Ctrl+Alt+L"),
    ("sala", "Ctrl+Alt+F"),
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
    let salvo = config
        .get("atalhos")
        .and_then(|a| a.get(chave))
        .and_then(|v| v.as_str())
        .unwrap_or(padrao);
    // Migração: o antigo padrão do painel roubava o ç (AltGr+, no ABNT2); só esse valor exato migra.
    if chave == "config" && salvo == "Ctrl+Alt+Comma" {
        return padrao.to_string();
    }
    salvo.to_string()
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

/// true quando o widget está na metade de baixo do monitor em que está (a barra de botões vai para cima).
#[tauri::command]
pub fn dock_em_cima(window: tauri::Window) -> Result<bool, String> {
    let pos = window.outer_position().map_err(|e| e.to_string())?;
    let tam = window.outer_size().map_err(|e| e.to_string())?;
    Ok(match window.current_monitor().map_err(|e| e.to_string())? {
        Some(m) => crate::janelas::metade_inferior(pos.y, tam.height, m.position().y, m.size().height),
        None => false,
    })
}

/// Redimensiona o widget (tamanho da config) mantendo o canto superior esquerdo; se passar da borda do monitor, encosta nela.
#[tauri::command]
pub fn redimensionar_janela(window: tauri::Window, largura: f64, altura: f64) -> Result<(), String> {
    let ok = |v: f64| v.is_finite() && (100.0..=4000.0).contains(&v);
    if !ok(largura) || !ok(altura) {
        return Err("tamanho fora do intervalo".into());
    }
    window.set_size(tauri::LogicalSize::new(largura, altura)).map_err(|e| e.to_string())?;
    let fator = window.scale_factor().map_err(|e| e.to_string())?;
    let pos = window.outer_position().map_err(|e| e.to_string())?;
    if let Some(m) = window.current_monitor().map_err(|e| e.to_string())? {
        let mon = crate::janelas::info(&m, None);
        let (x, y) = crate::janelas::encaixar(pos.x, pos.y, (largura * fator).round() as u32, (altura * fator).round() as u32, &mon);
        if (x, y) != (pos.x, pos.y) {
            window.set_position(tauri::PhysicalPosition::new(x, y)).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// Engrenagem do widget: abre o painel ou foca o existente. Assíncrono: criar janela em comando síncrono trava no Windows.
#[tauri::command]
pub async fn abrir_configuracoes(app: tauri::AppHandle) -> Result<(), String> {
    crate::janelas::abrir_configuracoes(&app).map_err(|e| e.to_string())
}

/// Esc na sala e quem mais quiser alternar por comando. Assíncrono: cria janela.
#[tauri::command]
pub async fn alternar_sala(app: tauri::AppHandle) -> Result<Option<String>, String> {
    crate::janelas::alternar_sala(&app)
}

/// Monitores para o painel escolher onde a sala abre.
#[tauri::command]
pub fn listar_monitores(window: tauri::Window) -> Result<Vec<crate::janelas::MonitorInfo>, String> {
    let principal = window.primary_monitor().map_err(|e| e.to_string())?.and_then(|m| m.name().cloned());
    Ok(window
        .available_monitors()
        .map_err(|e| e.to_string())?
        .iter()
        .map(|m| crate::janelas::info(m, principal.as_ref()))
        .collect())
}

/// Troca só as chaves de `parcial` numa config (a bandeja grava uma chave sem desfazer o resto).
pub fn mesclar(atual: Value, parcial: Value) -> Value {
    let mut base = match atual {
        Value::Object(m) => m,
        _ => serde_json::Map::new(),
    };
    if let Value::Object(p) = parcial {
        for (k, v) in p {
            base.insert(k, v);
        }
    }
    Value::Object(base)
}

/// Lê, mescla e grava a config (uma chave só; o resto fica como estava).
pub fn mesclar_config(app: &tauri::AppHandle, parcial: Value) -> Result<(), String> {
    let atual = ler_config_valor(app).unwrap_or(Value::Null);
    gravar_config(app.clone(), mesclar(atual, parcial))
}

/// Modo invisível: o cursor atravessa a janela enquanto ela está transparente (a opacidade é do CSS do widget).
#[tauri::command]
pub fn definir_invisivel(window: tauri::Window, ligado: bool) -> Result<(), String> {
    window.set_ignore_cursor_events(ligado).map_err(|e| e.to_string())
}

/// O painel mudou "invisivel": a marca da bandeja acompanha.
#[tauri::command]
pub fn marcar_invisivel_na_bandeja(estado: tauri::State<'_, crate::Bandeja>, ligado: bool) -> Result<(), String> {
    if let Ok(g) = estado.0.lock() {
        if let Some(item) = g.as_ref() {
            item.set_checked(ligado).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

const HOSTS_RELEASE: [&str; 2] = ["api.github.com", "github.com"];

fn host_do_github(host: &str) -> bool {
    HOSTS_RELEASE.contains(&host) || host.strip_suffix(".githubusercontent.com").is_some_and(|p| !p.is_empty())
}

/// Só https nos hosts do GitHub (e, em build de desenvolvimento, http em 127.0.0.1/localhost para o harness).
pub fn host_permitido(url: &str, dev: bool) -> bool {
    let (esquema, resto) = match url.split_once("://") {
        Some(x) => x,
        None => return false,
    };
    let autoridade = resto.split(['/', '?', '#']).next().unwrap_or("");
    if autoridade.contains('@') {
        return false;
    }
    let host = autoridade.split(':').next().unwrap_or("").to_ascii_lowercase();
    match esquema {
        "https" => host_do_github(&host),
        "http" => dev && (host == "127.0.0.1" || host == "localhost"),
        _ => false,
    }
}

/// Decide se um redirecionamento pode ser seguido: mesma regra do endereço inicial (https só em hosts do GitHub, incluindo
/// *.githubusercontent.com onde ficam os assets; em debug, também http local do harness).
pub fn host_de_redirect_permitido(url: &str, dev: bool) -> bool {
    host_permitido(url, dev)
}

/// Nome de arquivo simples (sem caminho) terminando em -setup.exe.
pub fn nome_de_instalador_valido(nome: &str) -> bool {
    !nome.is_empty()
        && nome.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
        && !nome.contains("..")
        && nome.to_ascii_lowercase().ends_with("-setup.exe")
}

fn cliente_http() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .user_agent(format!("Vard/{}", env!("CARGO_PKG_VERSION")))
        .timeout(std::time::Duration::from_secs(60))
        .redirect(reqwest::redirect::Policy::custom(|tentativa| {
            if tentativa.previous().len() >= 5 {
                tentativa.error("redirecionamentos demais")
            } else if host_de_redirect_permitido(tentativa.url().as_str(), cfg!(debug_assertions)) {
                tentativa.follow()
            } else {
                tentativa.error("redirecionamento para endereço fora da lista permitida")
            }
        }))
        .build()
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn versao_do_app(app: tauri::AppHandle) -> String {
    app.package_info().version.to_string()
}

/// GET da API de releases. Só por ação do usuário (botão ou caixa "ao abrir"). Corpo limitado a 1 MB.
#[tauri::command]
pub async fn buscar_release(url: String) -> Result<String, String> {
    if !host_permitido(&url, cfg!(debug_assertions)) {
        return Err("endereço fora da lista permitida".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let r = cliente_http()?
            .get(&url)
            .header("Accept", "application/vnd.github+json")
            .timeout(std::time::Duration::from_secs(10))
            .send()
            .map_err(|e| e.to_string())?;
        if !r.status().is_success() {
            return Err(format!("GitHub respondeu {}", r.status().as_u16()));
        }
        let corpo = r.bytes().map_err(|e| e.to_string())?;
        if corpo.len() > 1_000_000 {
            return Err("resposta grande demais".into());
        }
        String::from_utf8(corpo.to_vec()).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Remove o arquivo no Drop enquanto o segundo campo for true (desarmado no sucesso).
struct ApagarSeFalhar(PathBuf, bool);
impl Drop for ApagarSeFalhar {
    fn drop(&mut self) {
        if self.1 {
            let _ = fs::remove_file(&self.0);
        }
    }
}

/// Baixa o -setup.exe da release para a pasta temporária, confere o tamanho, roda o instalador e fecha o Vard.
#[tauri::command]
pub async fn instalar_atualizacao(app: tauri::AppHandle, url: String, nome: String, bytes: u64) -> Result<(), String> {
    if !host_permitido(&url, cfg!(debug_assertions)) {
        return Err("endereço fora da lista permitida".into());
    }
    if !nome_de_instalador_valido(&nome) {
        return Err("nome de instalador inválido".into());
    }
    let caminho = tauri::async_runtime::spawn_blocking(move || -> Result<PathBuf, String> {
        let dir = std::env::temp_dir().join("Vard");
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let caminho = dir.join(&nome);
        let mut r = cliente_http()?.get(&url).send().map_err(|e| e.to_string())?;
        if !r.status().is_success() {
            return Err(format!("download respondeu {}", r.status().as_u16()));
        }
        let f = fs::File::create(&caminho).map_err(|e| e.to_string())?;
        // Apaga o arquivo parcial em qualquer saída com erro depois de criado.
        let mut guarda = ApagarSeFalhar(caminho.clone(), true);
        let mut f = f;
        // take(bytes + 1): um servidor que manda mais que o anunciado não enche o disco; o excesso aparece como diferença.
        let copiados = std::io::copy(&mut (&mut r).take(bytes.saturating_add(1)), &mut f).map_err(|e| e.to_string())?;
        drop(f);
        if copiados != bytes {
            return Err("o download veio incompleto ou maior que o anunciado; tente de novo".into());
        }
        guarda.1 = false;
        Ok(caminho)
    })
    .await
    .map_err(|e| e.to_string())??;
    std::process::Command::new(&caminho).spawn().map_err(|e| e.to_string())?;
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn mesclar_troca_so_a_chave_do_parcial() {
        assert_eq!(
            mesclar(serde_json::json!({"a":1,"invisivel":false}), serde_json::json!({"invisivel":true})),
            serde_json::json!({"a":1,"invisivel":true})
        );
    }

    #[test]
    fn mesclar_sobre_nada_cria_o_objeto() {
        assert_eq!(mesclar(Value::Null, serde_json::json!({"invisivel":true})), serde_json::json!({"invisivel":true}));
    }

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
        assert_eq!(atalho_da_config(&c, "escuta", "Ctrl+Alt+L"), "Ctrl+Shift+L");
        assert_eq!(atalho_da_config(&c, "config", "Ctrl+Alt+P"), "Ctrl+Alt+P");
        assert_eq!(atalho_da_config(&Value::Null, "falar", "Ctrl+Alt+Space"), "Ctrl+Alt+Space");
    }

    #[test]
    fn painel_antigo_ctrl_alt_virgula_migra_e_escolha_do_usuario_fica() {
        let antigo = serde_json::json!({ "atalhos": { "config": "Ctrl+Alt+Comma" } });
        assert_eq!(atalho_da_config(&antigo, "config", "Ctrl+Alt+P"), "Ctrl+Alt+P");
        let outro = serde_json::json!({ "atalhos": { "config": "Ctrl+Shift+K", "escuta": "Ctrl+Alt+Comma" } });
        assert_eq!(atalho_da_config(&outro, "config", "Ctrl+Alt+P"), "Ctrl+Shift+K");
        assert_eq!(atalho_da_config(&outro, "escuta", "Ctrl+Alt+L"), "Ctrl+Alt+Comma");
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

    #[test]
    fn host_permitido_so_github_em_https() {
        assert!(host_permitido("https://api.github.com/repos/x/y/releases/latest", false));
        assert!(host_permitido("https://github.com/x/y/releases/download/v1/a-setup.exe", false));
        assert!(host_permitido("https://objects.githubusercontent.com/abc", false));
        assert!(!host_permitido("http://api.github.com/x", false));
        assert!(!host_permitido("https://evil.com/api.github.com/", false));
        assert!(!host_permitido("https://api.github.com.evil.com/", false));
        assert!(!host_permitido("https://user@api.github.com/", false));
        assert!(!host_permitido("ftp://github.com/", false));
    }

    #[test]
    fn host_permitido_local_so_em_dev() {
        assert!(host_permitido("http://127.0.0.1:8765/repos/x", true));
        assert!(host_permitido("http://localhost:8765/x", true));
        assert!(!host_permitido("http://127.0.0.1:8765/repos/x", false));
    }

    #[test]
    fn host_de_redirect_so_github_em_https() {
        assert!(host_de_redirect_permitido("https://release-assets.githubusercontent.com/x", false));
        assert!(host_de_redirect_permitido("https://objects.githubusercontent.com/abc", false));
        assert!(host_de_redirect_permitido("https://github.com/x/y", false));
        assert!(!host_de_redirect_permitido("https://evil.com/", false));
        assert!(!host_de_redirect_permitido("http://github.com/", false));
        assert!(!host_de_redirect_permitido("https://githubusercontent.com.evil.com/", false));
        assert!(!host_de_redirect_permitido("https://.githubusercontent.com/", false));
        assert!(!host_de_redirect_permitido("https://evilgithubusercontent.com/", false));
        assert!(!host_de_redirect_permitido("http://127.0.0.1:1/x", false));
        assert!(host_de_redirect_permitido("http://127.0.0.1:1/x", true));
    }

    #[test]
    fn host_permitido_aceita_subdominio_de_githubusercontent() {
        assert!(host_permitido("https://release-assets.githubusercontent.com/x", false));
    }

    #[test]
    fn nome_do_instalador() {
        assert!(nome_de_instalador_valido("Vard_0.4.0_x64-setup.exe"));
        assert!(!nome_de_instalador_valido("..\\x-setup.exe"));
        assert!(!nome_de_instalador_valido("x.msi"));
        assert!(!nome_de_instalador_valido("x-setup.exe.bat"));
        assert!(!nome_de_instalador_valido(""));
    }
}
