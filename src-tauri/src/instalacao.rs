//! Instalação: caminhos, configuração externa e descritores de execução para serviços.
//!
//! Lê `instalacao.json` externo (configurado na 0.5) e gera `DescritorServico` para cada
//! serviço habilitado. Valida vetor/cwd/prazos seguindo as regras de `externo.rs` da v0.4,
//! mas sem comando arbitrário de "iniciar instalação" nem script legado.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::servicos::DescritorServico;

/// Limite de itens no vetor de argumentos (mesmo da v0.4).
const MAX_ITENS: usize = 32;
/// Limite total de caracteres no vetor de argumentos.
const MAX_CARACTERES: usize = 4096;

/// Configuração externa lida de `instalacao.json`.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct InstalacaoConfig {
    /// Raiz do código-fonte (dev) ou instalação (release).
    pub raiz_codigo: String,
    /// Caminho do OpenJarvis source (dev).
    #[serde(default)]
    pub openjarvis_src: String,
    /// Caminho do OpenJarvis home/dados.
    #[serde(default)]
    pub openjarvis_home: String,
    /// Modelo configurado ("modelo-local", "nuvem", etc.).
    #[serde(default)]
    pub modelo: String,
    /// Tamanho do contexto.
    #[serde(default)]
    pub contexto: u32,
    /// Se true, o app inicia e supervisiona os serviços automaticamente.
    /// Padrão false para preservar lado a lado com vard-modo.ps1.
    #[serde(default)]
    pub supervisor: bool,
    /// Serviços opcionais habilitados e suas configurações.
    #[serde(default)]
    pub servicos: ServicosConfig,
}

impl Default for InstalacaoConfig {
    fn default() -> Self {
        Self {
            raiz_codigo: String::new(),
            openjarvis_src: String::new(),
            openjarvis_home: String::new(),
            modelo: String::new(),
            contexto: 16000,
            supervisor: false,
            servicos: ServicosConfig::default(),
        }
    }
}

/// Decide se o serviço OpenJarvis deve subir.
///
/// Regra: sobe apenas quando `servicos.openjarvis` é true E
/// (`cerebro == "openjarvis"` OU `usar_openjarvis == true`) no hud.config.json.
/// A pasta registrada no setup vem de app_config_dir (identifier deste build).
/// Sem HUD/campo, conserva o cérebro histórico: OpenJarvis; opção extra desligada.
pub fn deve_subir_openjarvis(config: &InstalacaoConfig) -> bool {
    if !config.servicos.openjarvis {
        return false;
    }
    let pasta = crate::nucleo::pasta_hud().map(Path::to_path_buf).or_else(|| {
        std::env::var_os("VARD_HUD_CONFIG_DIR").filter(|p| !p.is_empty()).map(PathBuf::from)
    });
    let hud = pasta
        .and_then(|p| std::fs::read_to_string(crate::comandos::caminho_em(&p)).ok())
        .and_then(|texto| serde_json::from_str::<serde_json::Value>(&texto).ok())
        .unwrap_or_default();
    let cerebro = hud.get("cerebro").and_then(|v| v.as_str()).unwrap_or("openjarvis");
    cerebro == "openjarvis" || hud.get("usar_openjarvis").and_then(|v| v.as_bool()) == Some(true)
}

/// Resolve o caminho do arquivo `instalacao.json` seguindo o contrato do Python:
/// 1. Se `VARD_INSTALACAO` estiver definida, é o caminho direto do arquivo.
/// 2. Senão, usa `<pasta_dados()>/instalacao.json` (VARD_DADOS ou %LOCALAPPDATA%/rdl-vard).
///
/// O arquivo pode não existir; o chamador decide como tratar (default ou erro).
pub fn arquivo_instalacao() -> PathBuf {
    if let Ok(p) = std::env::var("VARD_INSTALACAO") {
        if !p.is_empty() {
            return PathBuf::from(p);
        }
    }
    crate::ciclo::pasta_dados().join("instalacao.json")
}

/// Resolve a raiz do código/repo em tempo de execução (independente de VARD_INSTALACAO).
/// - Se `VARD_RAIZ_DEV` estiver definida, usa esse caminho (dev).
/// - Caso contrário, tenta achar o marcador do repo subindo a partir dos recursos.
/// - Fallback: diretório corrente.
pub fn resolver_raiz(recursos: &Path) -> PathBuf {
    if let Ok(p) = std::env::var("VARD_RAIZ_DEV") {
        return PathBuf::from(p);
    }
    // Tenta subir a partir do recurso até achar Cargo.toml (marcador do repo)
    let mut dir = recursos.to_path_buf();
    for _ in 0..10 {
        if dir.join("Cargo.toml").exists() && dir.join("src-tauri").exists() {
            return dir;
        }
        if !dir.pop() {
            break;
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

/// Configuração dos serviços opcionais.
#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(default)]
pub struct ServicosConfig {
    /// Voz habilitada.
    pub voz: bool,
    /// Intérprete externo; sua presença também habilita a voz.
    pub voz_python: String,
    /// Reunião habilitada.
    pub reuniao: bool,
    /// Intérprete externo; sua presença também habilita a reunião.
    pub reuniao_python: String,
    /// OpenJarvis habilitado.
    pub openjarvis: bool,
    /// Porta do núcleo (sobrescreve padrão se > 0).
    #[serde(default)]
    pub porta_nucleo: u16,
    /// Porta da voz (sobrescreve padrão se > 0).
    #[serde(default)]
    pub porta_voz: u16,
    /// Porta da reunião (sobrescreve padrão se > 0).
    #[serde(default)]
    pub porta_reuniao: u16,
}

/// Portas padrão dos serviços.
pub const PORTA_NUCLEO_PADRAO: u16 = 4700;
pub const PORTA_VOZ_PADRAO: u16 = 4710;
pub const PORTA_REUNIAO_PADRAO: u16 = 4720;

/// Prazos de arranque por serviço (segundos).
pub const PRAZO_NUCLEO_S: u64 = 60;
pub const PRAZO_OPENJARVIS_S: u64 = 120;
pub const PRAZO_OPCIONAIS_S: u64 = 120;

fn ambiente_instalacao(dados: &Path) -> Vec<(String, String)> {
    let configurada = std::env::var("VARD_CONFIG").ok();
    let arquivo = std::env::var_os("VARD_INSTALACAO").filter(|v| !v.is_empty())
        .map(PathBuf::from).unwrap_or_else(|| dados.join("instalacao.json"));
    vec![
        ("VARD_CONFIG".into(), crate::nucleo::resolver_pasta_config(dados, configurada.as_deref()).to_string_lossy().into_owned()),
        ("VARD_INSTALACAO".into(), arquivo.to_string_lossy().into_owned()),
        ("PYTHONUTF8".into(), "1".into()),
        ("VARD_MARCA_TELEGRAM".into(), dados.join("ultimo-telegram.json").to_string_lossy().into_owned()),
    ]
}

/// Pré-checagem sem lançar processo: executável, módulo e cwd devem existir.
pub fn preparar_nucleo(dev: bool, recursos: &Path, repo: &Path, config: &InstalacaoConfig, dados: &Path, versao: &str) -> Result<DescritorServico, String> {
    let mut desc = descritor_nucleo(dev, recursos, repo, config, dados, versao);
    if desc.comando.0 == Path::new("uv") {
        desc.comando.0 = std::env::var_os("PATH").and_then(|p| std::env::split_paths(&p)
            .map(|p| p.join(if cfg!(windows) { "uv.exe" } else { "uv" })).find(|p| p.is_file()))
            .ok_or("núcleo: uv não encontrado")?;
    }
    if !desc.comando.0.is_file() { return Err("núcleo: intérprete não encontrado".into()); }
    let pasta = desc.pasta_trabalho.as_ref().ok_or("núcleo: pasta de trabalho ausente")?;
    if !pasta.is_dir() { return Err("núcleo: pasta de trabalho não encontrada".into()); }
    if desc.comando.1.iter().any(|a| a == "server:app") && !pasta.join("server.py").is_file() {
        return Err("núcleo: módulo server.py não encontrado".into());
    }
    Ok(desc)
}

/// Log persistente também em builds sem console. Nunca registra o ambiente.
pub fn registrar_setup(dados: &Path, mensagem: &str) {
    let mut log = crate::supervisor::Log::abrir(dados.join("logs/setup.log"));
    log.linha(&crate::supervisor::redigir(mensagem));
}

/// Valida um vetor de argumentos de comando.
/// Lista vazia é Ok (nada a rodar). O executável não pode ser `.cmd`, `.bat` nem `.ps1`;
/// nada de caracteres de controle; no máximo 32 itens e 4.096 caracteres.
pub fn validar_comando(args: &[String]) -> Result<(), String> {
    if args.is_empty() {
        return Ok(());
    }
    if args.len() > MAX_ITENS {
        return Err(format!("comando com mais de {MAX_ITENS} itens"));
    }
    if args.iter().map(|a| a.chars().count()).sum::<usize>() > MAX_CARACTERES {
        return Err(format!("comando com mais de {MAX_CARACTERES} caracteres"));
    }
    if args.iter().any(|a| a.chars().any(|c| c.is_control())) {
        return Err("comando com caractere de controle".to_string());
    }
    let exe = args[0].trim();
    if exe.is_empty() {
        return Err("executável do comando vazio".to_string());
    }
    let minusculo = exe.to_ascii_lowercase();
    if [".cmd", ".bat", ".ps1"]
        .iter()
        .any(|ext| minusculo.ends_with(ext))
    {
        return Err(
            "o executável não pode ser .cmd, .bat nem .ps1 (use powershell.exe -File ...)"
                .to_string(),
        );
    }
    Ok(())
}

/// Junta argumentos com espaço, com aspas em item que tem espaço (só para log/exibição).
pub fn exibir_comando(args: &[String]) -> String {
    args.iter()
        .map(|a| {
            if a.contains(' ') {
                format!("\"{a}\"")
            } else {
                a.clone()
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

/// Constrói o descritor de serviço para o núcleo Python.
/// Prefere o pacote no release; sem pacote usa `raiz_codigo`, como o script.
/// Sem raiz configurada em dev, preserva a execução por uv no checkout.
pub fn descritor_nucleo(
    dev: bool,
    recursos: &Path,
    repo: &Path,
    config: &InstalacaoConfig,
    dados: &Path,
    versao: &str,
) -> DescritorServico {
    let porta = if config.servicos.porta_nucleo > 0 {
        config.servicos.porta_nucleo
    } else {
        PORTA_NUCLEO_PADRAO
    };
    let configurada = std::env::var("VARD_CONFIG").ok();
    let pasta_config = crate::nucleo::resolver_pasta_config(dados, configurada.as_deref());
    let empacotado = recursos.join("nucleo/python/python.exe").is_file();
    let mut desc = crate::nucleo::descritor_nucleo(dev && config.raiz_codigo.trim().is_empty(), recursos, repo, porta, dados, &pasta_config, versao);
    if (dev || !empacotado) && !config.raiz_codigo.trim().is_empty() {
        let raiz = Path::new(&config.raiz_codigo);
        let pasta = if raiz.join("nucleo/server.py").is_file() { raiz.join("nucleo") } else { raiz.to_path_buf() };
        desc.comando = (pasta.join(".venv/Scripts/python.exe"), vec![
            "-X".into(), "utf8".into(), "-m".into(), "uvicorn".into(), "server:app".into(),
            "--host".into(), "127.0.0.1".into(), "--port".into(), porta.to_string(),
            "--timeout-graceful-shutdown".into(), "2".into(),
        ]);
        desc.pasta_trabalho = Some(pasta);
    }
    desc.envs.extend(ambiente_instalacao(dados));
    desc
}

/// Pasta do hud.config.json (VARD_HUD_CONFIG_DIR) para um serviço filho; sem pasta registrada, nada.
fn variavel_pasta_hud(pasta: Option<&Path>) -> Option<(String, String)> {
    pasta.map(|p| ("VARD_HUD_CONFIG_DIR".into(), p.to_string_lossy().into_owned()))
}

/// Constrói o descritor de serviço para a voz (opcional).
/// Retorna None se desabilitada ou se a venv não existe.
pub fn descritor_voz(
    config: &InstalacaoConfig,
    dados: &Path,
) -> Option<DescritorServico> {
    if !config.servicos.voz && config.servicos.voz_python.trim().is_empty() {
        return None;
    }
    let raiz = Path::new(&config.raiz_codigo);
    let venv_python = if config.servicos.voz_python.trim().is_empty() {
        raiz.join("voz/.venv/Scripts/python.exe")
    } else { PathBuf::from(&config.servicos.voz_python) };
    if !venv_python.exists() {
        return None;
    }
    let porta = if config.servicos.porta_voz > 0 {
        config.servicos.porta_voz
    } else {
        PORTA_VOZ_PADRAO
    };
    let pasta_trabalho = Some(raiz.join("voz"));
    let args = vec![
        "-X".into(),
        "utf8".into(),
        "-m".into(),
        "vard_voz".into(),
    ];
    let mut envs = vec![
        ("VARD_VOZ_PORT".into(), porta.to_string()),
        ("VARD_DADOS".into(), dados.to_string_lossy().into_owned()),
    ];
    // A voz lê a escolha da aba Transcrição (stt_modelo, stt_dispositivo) no hud.config.json desta pasta.
    envs.extend(variavel_pasta_hud(crate::nucleo::pasta_hud()));
    envs.extend(ambiente_instalacao(dados));
    Some(DescritorServico {
        id: "voz".into(),
        porta,
        comando: (venv_python, args),
        pasta_trabalho,
        envs,
        caminho_log: dados.join("logs").join("voz.log"),
    })
}

/// Constrói o descritor de serviço para a reunião (opcional).
/// Retorna None se desabilitada ou se a venv não existe.
pub fn descritor_reuniao(
    config: &InstalacaoConfig,
    dados: &Path,
) -> Option<DescritorServico> {
    if !config.servicos.reuniao && config.servicos.reuniao_python.trim().is_empty() {
        return None;
    }
    let raiz = Path::new(&config.raiz_codigo);
    let venv_python = if config.servicos.reuniao_python.trim().is_empty() {
        raiz.join("reuniao/.venv/Scripts/python.exe")
    } else { PathBuf::from(&config.servicos.reuniao_python) };
    if !venv_python.exists() {
        return None;
    }
    let porta = if config.servicos.porta_reuniao > 0 {
        config.servicos.porta_reuniao
    } else {
        PORTA_REUNIAO_PADRAO
    };
    let pasta_trabalho = Some(raiz.join("reuniao"));
    let args = vec![
        "-X".into(),
        "utf8".into(),
        "-m".into(),
        "vard_reuniao".into(),
    ];
    let mut envs = vec![
        ("VARD_REUNIAO_PORT".into(), porta.to_string()),
        ("VARD_DADOS".into(), dados.to_string_lossy().into_owned()),
        ("HF_HUB_OFFLINE".into(), "1".into()),
        ("PYANNOTE_METRICS_ENABLED".into(), "0".into()),
    ];
    envs.extend(ambiente_instalacao(dados));
    Some(DescritorServico {
        id: "reuniao".into(),
        porta,
        comando: (venv_python, args),
        pasta_trabalho,
        envs,
        caminho_log: dados.join("logs").join("reuniao.log"),
    })
}

/// Constrói o descritor de serviço para o OpenJarvis (opcional).
/// Retorna None se desabilitado ou se o caminho fonte não existe.
pub fn descritor_openjarvis(
    config: &InstalacaoConfig,
    dados: &Path,
) -> Option<DescritorServico> {
    if !deve_subir_openjarvis(config) {
        return None;
    }
    let src = Path::new(&config.openjarvis_src);
    if !src.exists() {
        return None;
    }
    let home = if config.openjarvis_home.is_empty() {
        dados.join("openjarvis")
    } else {
        PathBuf::from(&config.openjarvis_home)
    };
    // O entrypoint do OpenJarvis é `jarvis serve --agent orchestrator` dentro do venv/source.
    let jarvis = if cfg!(windows) {
        src.join(".venv/Scripts/jarvis.exe")
    } else {
        src.join(".venv/bin/jarvis")
    };
    if !jarvis.exists() {
        return None;
    }
    let args = vec![
        "serve".into(),
        "--agent".into(),
        "orchestrator".into(),
    ];
    let mut envs = vec![
        ("OPENJARVIS_HOME".into(), home.to_string_lossy().into_owned()),
        ("VARD_DADOS".into(), dados.to_string_lossy().into_owned()),
    ];
    // Mesmas DLLs CUDA usadas pelo vard-modo; só altera o PATH do filho.
    let mut caminhos: Vec<PathBuf> = ["cudnn", "cublas"].iter()
        .map(|sub| src.join(format!(".venv/Lib/site-packages/nvidia/{sub}/bin")))
        .filter(|p| p.is_dir()).collect();
    if !caminhos.is_empty() {
        if let Some(path) = std::env::var_os("PATH") { caminhos.extend(std::env::split_paths(&path)); }
        if let Ok(path) = std::env::join_paths(caminhos) { envs.push(("PATH".into(), path.to_string_lossy().into_owned())); }
    }
    envs.push(("OPENJARVIS_CHAT_EXTRA".into(), std::env::var("OPENJARVIS_CHAT_EXTRA").unwrap_or_else(|_| r#"{"reasoning_effort":"none"}"#.into())));
    if let Some(pasta) = crate::nucleo::pasta_hud() {
        envs.push(("VARD_HUD_CONFIG_DIR".into(), pasta.to_string_lossy().into_owned()));
    }
    envs.extend(ambiente_instalacao(dados));
    Some(DescritorServico {
        id: "openjarvis".into(),
        porta: 8000,
        comando: (jarvis, args),
        pasta_trabalho: Some(src.to_path_buf()),
        envs,
        caminho_log: dados.join("logs").join("openjarvis.log"),
    })
}

/// Inicia os serviços habilitados na configuração de instalação.
/// Retorna lista de IDs iniciados e avisos sobre opcionais indisponíveis.
/// Se `config.supervisor` for false, retorna imediatamente sem iniciar nada.
pub fn iniciar_servicos(
    config: &InstalacaoConfig,
    recursos: &Path,
    repo: &Path,
    dados: &Path,
    versao: &str,
) -> (Vec<String>, Vec<String>) {
    let mut iniciados = Vec::new();
    let mut avisos = Vec::new();

    if !config.supervisor {
        return (iniciados, avisos);
    }

    // Núcleo sempre inicia quando supervisor está ligado
    let desc_nucleo = preparar_nucleo(
        cfg!(debug_assertions),
        recursos,
        repo,
        config,
        dados,
        versao,
    );
    match desc_nucleo.and_then(crate::servicos::iniciar) {
        Ok(()) => iniciados.push("nucleo".into()),
        Err(e) => avisos.push(format!("nucleo: {e}")),
    }

    // Voz opcional
    match descritor_voz(config, dados) {
        Some(desc) => match crate::servicos::iniciar(desc) {
            Ok(()) => iniciados.push("voz".into()),
            Err(e) => avisos.push(format!("voz: {e}")),
        },
        None if config.servicos.voz || !config.servicos.voz_python.trim().is_empty() => {
            avisos.push("voz: venv ausente ou desabilitada".into());
        }
        _ => {}
    }

    // Reunião opcional
    match descritor_reuniao(config, dados) {
        Some(desc) => match crate::servicos::iniciar(desc) {
            Ok(()) => iniciados.push("reuniao".into()),
            Err(e) => avisos.push(format!("reuniao: {e}")),
        },
        None if config.servicos.reuniao || !config.servicos.reuniao_python.trim().is_empty() => {
            avisos.push("reuniao: venv ausente ou desabilitada".into());
        }
        _ => {}
    }

    // OpenJarvis opcional
    match descritor_openjarvis(config, dados) {
        Some(desc) => match crate::servicos::iniciar(desc) {
            Ok(()) => iniciados.push("openjarvis".into()),
            Err(e) => avisos.push(format!("openjarvis: {e}")),
        },
        None if deve_subir_openjarvis(config) => {
            avisos.push("openjarvis: fonte ou executável ausente".into());
        }
        _ => {}
    }

    for id in &iniciados { registrar_setup(dados, &format!("setup: serviço {id} registrado para arranque")); }
    for aviso in &avisos { registrar_setup(dados, &format!("setup: aviso: {aviso}")); }
    (iniciados, avisos)
}

/// Lê e valida `instalacao.json` de um caminho. Arquivo ausente retorna padrão.
pub fn ler_instalacao(caminho: &Path) -> Result<InstalacaoConfig, String> {
    if !caminho.exists() {
        return Ok(InstalacaoConfig::default());
    }
    let texto = std::fs::read_to_string(caminho)
        .map_err(|e| format!("instalacao.json ilegível: {e}"))?;
    let conf: InstalacaoConfig = serde_json::from_str(&texto)
        .map_err(|e| format!("instalacao.json inválido: {e}"))?;
    Ok(conf)
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn validar_comando_vazio_e_ok() {
        assert!(validar_comando(&[]).is_ok());
    }

    #[test]
    fn validar_comando_recusa_cmd_bat_ps1() {
        for ext in ["x.cmd", "X.BAT", "y.ps1"] {
            assert!(
                validar_comando(&[ext.into()]).is_err(),
                "{ext} deveria ser recusado"
            );
        }
        assert!(validar_comando(&[
            "powershell.exe".into(),
            "-File".into(),
            "a.ps1".into()
        ])
        .is_ok());
    }

    #[test]
    fn validar_comando_recusa_controle_e_tamanho() {
        assert!(validar_comando(&["a\nb".into()]).is_err());
        assert!(validar_comando(&vec!["a".into(); 33]).is_err());
    }

    #[test]
    fn validar_comando_recusa_executavel_vazio() {
        assert!(validar_comando(&["  ".into()]).is_err());
    }

    #[test]
    fn exibir_comando_poe_aspas_so_em_item_com_espaco() {
        assert_eq!(
            exibir_comando(&["a".into(), "X:\\a b\\c.ps1".into()]),
            "a \"X:\\a b\\c.ps1\""
        );
        assert_eq!(exibir_comando(&[]), "");
    }

    #[test]
    fn instalacao_config_padrao_tem_servicos_desligados() {
        let c = InstalacaoConfig::default();
        assert!(!c.servicos.voz);
        assert!(!c.servicos.reuniao);
        assert!(!c.servicos.openjarvis);
        assert_eq!(c.servicos.porta_nucleo, 0);
    }

    #[test]
    fn ler_instalacao_ausente_retorna_padrao() {
        let dir = tempfile::tempdir().unwrap();
        let c = ler_instalacao(&dir.path().join("nao-existe.json")).unwrap();
        assert_eq!(c.contexto, 16000);
        assert!(!c.servicos.voz);
    }

    #[test]
    fn ler_instalacao_invalido_e_erro() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("instalacao.json");
        std::fs::write(&p, "{invalido").unwrap();
        let e = ler_instalacao(&p).unwrap_err();
        assert!(e.starts_with("instalacao.json inválido: "), "{e}");
    }

    #[test]
    fn ler_instalacao_valido_le_campos() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("instalacao.json");
        std::fs::write(
            &p,
            r#"{"raiz_codigo":"X:/DEV","modelo":"local","contexto":8000,"servicos":{"voz":true,"porta_nucleo":5700}}"#,
        )
        .unwrap();
        let c = ler_instalacao(&p).unwrap();
        assert_eq!(c.raiz_codigo, "X:/DEV");
        assert_eq!(c.modelo, "local");
        assert_eq!(c.contexto, 8000);
        assert!(c.servicos.voz);
        assert_eq!(c.servicos.porta_nucleo, 5700);
    }

    #[test]
    fn descritor_voz_desabilitado_retorna_none() {
        let mut c = InstalacaoConfig::default();
        c.servicos.voz = false;
        assert!(descritor_voz(&c, Path::new("/tmp")).is_none());
    }

    #[test]
    fn descritor_reuniao_desabilitado_retorna_none() {
        let mut c = InstalacaoConfig::default();
        c.servicos.reuniao = false;
        assert!(descritor_reuniao(&c, Path::new("/tmp")).is_none());
    }

    #[test]
    fn descritor_voz_venv_ausente_retorna_none() {
        let dir = tempfile::tempdir().unwrap();
        let mut c = InstalacaoConfig::default();
        c.servicos.voz = true;
        c.raiz_codigo = dir.path().to_string_lossy().into_owned();
        // venv não existe → None
        assert!(descritor_voz(&c, dir.path()).is_none());
    }

    #[test]
    fn descritor_voz_com_venv_retorna_descritor() {
        let dir = tempfile::tempdir().unwrap();
        let venv_dir = dir.path().join("voz").join(".venv").join("Scripts");
        std::fs::create_dir_all(&venv_dir).unwrap();
        std::fs::write(venv_dir.join("python.exe"), b"fake").unwrap();
        let mut c = InstalacaoConfig::default();
        c.servicos.voz = true;
        c.raiz_codigo = dir.path().to_string_lossy().into_owned();
        let desc = descritor_voz(&c, dir.path()).expect("deveria retornar descritor");
        assert_eq!(desc.id, "voz");
        assert_eq!(desc.porta, PORTA_VOZ_PADRAO);
        assert!(desc.caminho_log.to_string_lossy().contains("voz.log"));
    }

    #[test]
    fn descritor_reuniao_com_venv_retorna_descritor() {
        let dir = tempfile::tempdir().unwrap();
        let venv_dir = dir.path().join("reuniao").join(".venv").join("Scripts");
        std::fs::create_dir_all(&venv_dir).unwrap();
        std::fs::write(venv_dir.join("python.exe"), b"fake").unwrap();
        let mut c = InstalacaoConfig::default();
        c.servicos.reuniao = true;
        c.raiz_codigo = dir.path().to_string_lossy().into_owned();
        let desc = descritor_reuniao(&c, dir.path()).expect("deveria retornar descritor");
        assert_eq!(desc.id, "reuniao");
        assert_eq!(desc.porta, PORTA_REUNIAO_PADRAO);
        // Verifica que HF_HUB_OFFLINE está no ambiente
        assert!(desc.envs.iter().any(|(k, _)| k == "HF_HUB_OFFLINE"));
    }

    #[test]
    fn variavel_pasta_hud_so_com_pasta_registrada() {
        let pasta = Path::new("pasta-ficticia");
        assert_eq!(
            variavel_pasta_hud(Some(pasta)),
            Some(("VARD_HUD_CONFIG_DIR".to_string(), "pasta-ficticia".to_string()))
        );
        assert_eq!(variavel_pasta_hud(None), None);
    }

    #[test]
    fn descritor_voz_usa_porta_sobrescrita() {
        let dir = tempfile::tempdir().unwrap();
        let venv_dir = dir.path().join("voz").join(".venv").join("Scripts");
        std::fs::create_dir_all(&venv_dir).unwrap();
        std::fs::write(venv_dir.join("python.exe"), b"fake").unwrap();
        let mut c = InstalacaoConfig::default();
        c.servicos.voz = true;
        c.servicos.porta_voz = 9710;
        c.raiz_codigo = dir.path().to_string_lossy().into_owned();
        let desc = descritor_voz(&c, dir.path()).unwrap();
        assert_eq!(desc.porta, 9710);
    }

    #[test]
    fn portas_padrao_sao_corretas() {
        assert_eq!(PORTA_NUCLEO_PADRAO, 4700);
        assert_eq!(PORTA_VOZ_PADRAO, 4710);
        assert_eq!(PORTA_REUNIAO_PADRAO, 4720);
    }

    #[test]
    fn prazos_sao_positivos() {
        assert!(PRAZO_NUCLEO_S > 0);
        assert!(PRAZO_OPENJARVIS_S > 0);
        assert!(PRAZO_OPCIONAIS_S > 0);
    }

    #[test]
    fn iniciar_servicos_sem_opcionais_nao_inicia_voz_nem_reuniao() {
        let mut c = InstalacaoConfig::default();
        c.supervisor = true;
        let dir = tempfile::tempdir().unwrap();
        let (iniciados, _avisos) = iniciar_servicos(
            &c,
            dir.path(),
            dir.path(),
            dir.path(),
            "0.7.0-test",
        );
        // Voz e reunião desabilitadas não devem aparecer na lista de iniciados
        assert!(
            !iniciados.iter().any(|s| s == "voz"),
            "voz não deveria iniciar quando desabilitada"
        );
        assert!(
            !iniciados.iter().any(|s| s == "reuniao"),
            "reuniao não deveria iniciar quando desabilitada"
        );
    }

    #[test]
    fn iniciar_servicos_com_supervisor_desligado_retorna_listas_vazias() {
        let mut c = InstalacaoConfig::default();
        c.supervisor = false;
        c.servicos.voz = true;
        c.servicos.reuniao = true;
        let dir = tempfile::tempdir().unwrap();
        let (iniciados, avisos) = iniciar_servicos(
            &c,
            dir.path(),
            dir.path(),
            dir.path(),
            "0.7.0-test",
        );
        assert!(iniciados.is_empty(), "nenhum serviço deve iniciar com supervisor desligado");
        assert!(avisos.is_empty(), "nenhum aviso deve ser gerado com supervisor desligado");
    }

    #[test]
    fn iniciar_servicos_com_voz_habilitada_mas_venv_ausente_gera_aviso() {
        let mut c = InstalacaoConfig::default();
        c.supervisor = true;
        c.servicos.voz = true;
        c.raiz_codigo = "/tmp/nao-existe".into();
        let dir = tempfile::tempdir().unwrap();
        let (_iniciados, avisos) = iniciar_servicos(
            &c,
            dir.path(),
            dir.path(),
            dir.path(),
            "0.7.0-test",
        );
        assert!(
            avisos.iter().any(|a| a.contains("voz")),
            "deveria ter aviso sobre voz: {:?}",
            avisos
        );
    }

    // ----------------------------------------------------------------------------------------------
    // Contrato de arquivo_instalacao (deve ser idêntico ao Python nucleo/vard/instalacao.py)
    // ----------------------------------------------------------------------------------------------

    #[test]
    fn arquivo_instalacao_usa_vard_instalacao_quando_definido() {
        let _ambiente = crate::ciclo::testes::ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        let caminho = dir.path().join("custom").join("instalacao.json");
        unsafe { std::env::set_var("VARD_INSTALACAO", &caminho) };
        unsafe { std::env::remove_var("VARD_DADOS") };
        let resultado = super::arquivo_instalacao();
        unsafe { std::env::remove_var("VARD_INSTALACAO") };
        assert_eq!(resultado, caminho);
    }

    #[test]
    fn arquivo_instalacao_usa_vard_dados_quando_instalacao_ausente() {
        let _ambiente = crate::ciclo::testes::ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::remove_var("VARD_INSTALACAO") };
        let dados = dir.path().join("meus_dados");
        unsafe { std::env::set_var("VARD_DADOS", &dados) };
        let resultado = super::arquivo_instalacao();
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert_eq!(resultado, dados.join("instalacao.json"));
    }

    #[test]
    fn arquivo_instalacao_fallback_para_app_data() {
        let _ambiente = crate::ciclo::testes::ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::remove_var("VARD_INSTALACAO") };
        unsafe { std::env::remove_var("VARD_DADOS") };
        // Sem VARD_DADOS, pasta_dados() usa LOCALAPPDATA/rdl-vard;
        // o teste valida apenas que arquivo_instalacao() termina com instalacao.json.
        let resultado = super::arquivo_instalacao();
        assert!(resultado.ends_with("instalacao.json"), "esperado terminar com instalacao.json: {:?}", resultado);
    }

    #[test]
    fn arquivo_instalacao_ignora_vard_instalacao_vazia() {
        let _ambiente = crate::ciclo::testes::ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_INSTALACAO", "") };
        let dados = dir.path().join("dados_env");
        unsafe { std::env::set_var("VARD_DADOS", &dados) };
        let resultado = super::arquivo_instalacao();
        unsafe { std::env::remove_var("VARD_INSTALACAO") };
        unsafe { std::env::remove_var("VARD_DADOS") };
        assert_eq!(resultado, dados.join("instalacao.json"));
    }

    // ----------------------------------------------------------------------------------------------
    // deve_subir_openjarvis: OpenJarvis só sobe quando cerebro=openjarvis ou usar_openjarvis=true
    // ----------------------------------------------------------------------------------------------

    #[test]
    fn deve_subir_openjarvis_le_hud_config_e_ignora_campos_da_instalacao() {
        let _ambiente = crate::ciclo::testes::ambiente_isolado();
        let dir = tempfile::tempdir().unwrap();
        unsafe { std::env::set_var("VARD_HUD_CONFIG_DIR", dir.path()) };
        let caminho = dir.path().join("hud.config.json");
        let config: InstalacaoConfig = serde_json::from_str(
            r#"{"servicos":{"openjarvis":true},"cerebro":"proprio","usar_openjarvis":false}"#,
        ).unwrap();
        for (hud, esperado) in [
            (None, true),
            (Some("{}"), true),
            (Some(r#"{"cerebro":"openjarvis"}"#), true),
            (Some(r#"{"cerebro":"proprio"}"#), false),
            (Some(r#"{"cerebro":"proprio","usar_openjarvis":false}"#), false),
            (Some(r#"{"cerebro":"proprio","usar_openjarvis":true}"#), true),
            (Some(r#"{"cerebro":"proprio","usar_openjarvis":"true"}"#), false),
            (Some("{invalido"), true),
        ] {
            if let Some(texto) = hud { std::fs::write(&caminho, texto).unwrap(); }
            else { let _ = std::fs::remove_file(&caminho); }
            assert_eq!(deve_subir_openjarvis(&config), esperado, "hud: {hud:?}");
        }
        let config: InstalacaoConfig = serde_json::from_str(
            r#"{"servicos":{"openjarvis":true},"cerebro":"openjarvis","usar_openjarvis":true}"#,
        ).unwrap();
        std::fs::write(&caminho, r#"{"cerebro":"proprio"}"#).unwrap();
        assert!(!deve_subir_openjarvis(&config));
    }

    #[test]
    fn deve_subir_openjarvis_falso_quando_servico_desabilitado() {
        let mut c = InstalacaoConfig::default();
        c.servicos.openjarvis = false;
        assert!(!super::deve_subir_openjarvis(&c));
    }

    /// Prova de que o valor de CARGO_MANIFEST_DIR não vazou para o binário de release.
    /// Em debug, o compilador sempre embeda caminhos nos metadados DWARF/pdb;
    /// a garantia vale apenas para o artefato final distribuído (release).
    #[cfg(not(debug_assertions))]
    #[test]
    fn binario_release_nao_contem_valor_de_manifest_dir() {
        let exe = std::env::current_exe().expect("caminho do executável de teste");
        let bytes = std::fs::read(&exe).expect("leitura do binário");
        let texto = String::from_utf8_lossy(&bytes);
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        assert!(
            !texto.contains(manifest_dir),
            "binário de release contém o valor de CARGO_MANIFEST_DIR ('{}') como string literal — \
             paths do build host não devem ser embedados no artefato final (exe: {:?})",
            manifest_dir,
            exe
        );
    }
}
