//! Instalação: caminhos, configuração externa e descritores de execução para serviços.
//!
//! Lê `instalacao.json` externo (configurado na 0.5) e gera `DescritorServico` para cada
//! serviço habilitado. Valida vetor/cwd/prazos seguindo as regras de `externo.rs` da v0.4,
//! mas sem comando arbitrário de "iniciar instalação" nem script legado.

use std::path::Path;

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
            servicos: ServicosConfig::default(),
        }
    }
}

/// Configuração dos serviços opcionais.
#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(default)]
pub struct ServicosConfig {
    /// Voz habilitada.
    pub voz: bool,
    /// Reunião habilitada.
    pub reuniao: bool,
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
pub const PRAZO_NUCLEO_S: u64 = 15;
pub const PRAZO_OPENJARVIS_S: u64 = 120;
pub const PRAZO_OPCIONAIS_S: u64 = 120;

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
/// Em dev usa `uv run --project nucleo --frozen python -X utf8 -m vard servir`;
/// em release usa o Python embutido em `build/nucleo/python/python.exe`.
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
    let desc_nucleo = crate::nucleo::descritor_nucleo(dev, recursos, repo, porta, dados, &dados.join("config"), versao);
    desc_nucleo
}

/// Constrói o descritor de serviço para a voz (opcional).
/// Retorna None se desabilitada ou se a venv não existe.
pub fn descritor_voz(
    config: &InstalacaoConfig,
    dados: &Path,
) -> Option<DescritorServico> {
    if !config.servicos.voz {
        return None;
    }
    let raiz = Path::new(&config.raiz_codigo);
    let venv_python = raiz.join("voz").join(".venv").join("Scripts").join("python.exe");
    if !venv_python.exists() {
        return None;
    }
    let porta = if config.servicos.porta_voz > 0 {
        config.servicos.porta_voz
    } else {
        PORTA_VOZ_PADRAO
    };
    let _cwd = raiz.join("voz");
    let args = vec![
        "-X".into(),
        "utf8".into(),
        "-m".into(),
        "vard_voz".into(),
    ];
    let envs = vec![
        ("VARD_VOZ_PORT".into(), porta.to_string()),
        ("VARD_DADOS".into(), dados.to_string_lossy().into_owned()),
    ];
    Some(DescritorServico {
        id: "voz".into(),
        porta,
        comando: (venv_python, args),
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
    if !config.servicos.reuniao {
        return None;
    }
    let raiz = Path::new(&config.raiz_codigo);
    let venv_python = raiz
        .join("reuniao")
        .join(".venv")
        .join("Scripts")
        .join("python.exe");
    if !venv_python.exists() {
        return None;
    }
    let porta = if config.servicos.porta_reuniao > 0 {
        config.servicos.porta_reuniao
    } else {
        PORTA_REUNIAO_PADRAO
    };
    let _cwd = raiz.join("reuniao");
    let args = vec![
        "-X".into(),
        "utf8".into(),
        "-m".into(),
        "vard_reuniao".into(),
    ];
    let envs = vec![
        ("VARD_REUNIAO_PORT".into(), porta.to_string()),
        ("VARD_DADOS".into(), dados.to_string_lossy().into_owned()),
        ("HF_HUB_OFFLINE".into(), "1".into()),
        ("PYANNOTE_METRICS_ENABLED".into(), "0".into()),
    ];
    Some(DescritorServico {
        id: "reuniao".into(),
        porta,
        comando: (venv_python, args),
        envs,
        caminho_log: dados.join("logs").join("reuniao.log"),
    })
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
}