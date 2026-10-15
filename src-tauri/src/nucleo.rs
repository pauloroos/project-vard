//! Adaptador do núcleo Python: constrói o descritor de serviço para o comando da T1/T2.
//! Em release usa o Python embutido em build/nucleo/python; em dev usa uv no repo.

use std::path::{Path, PathBuf};

use crate::servicos::DescritorServico;

/// Porta padrão do núcleo (pode ser sobrescrita por config).
pub const PORTA_PADRAO: u16 = 4700;

/// Constrói o comando (exe, args) para lançar o núcleo.
/// - `dev`: true = usa `uv run --project nucleo --frozen python -X utf8 -m vard servir`
/// - `recursos`: resource_dir do app (release: contém nucleo/python/python.exe)
/// - `repo`: raiz do repositório (dev: CARGO_MANIFEST_DIR/..)
pub fn comando(dev: bool, recursos: &Path, repo: &Path) -> (PathBuf, Vec<String>) {
    if dev {
        let projeto = repo.join("nucleo");
        let args = vec![
            "run".into(),
            "--project".into(),
            projeto.to_string_lossy().into_owned(),
            "--frozen".into(),
            "python".into(),
            "-X".into(),
            "utf8".into(),
            "-m".into(),
            "vard".into(),
            "servir".into(),
        ];
        (PathBuf::from("uv"), args)
    } else {
        let exe = recursos.join("nucleo").join("python").join("python.exe");
        let args = vec![
            "-I".into(),
            "-X".into(),
            "utf8".into(),
            "-m".into(),
            "vard".into(),
            "servir".into(),
        ];
        (exe, args)
    }
}

/// Variáveis de ambiente passadas ao núcleo.
pub fn ambiente(
    token: &str,
    porta: u16,
    dados: &Path,
    config: &Path,
    versao: &str,
) -> Vec<(String, String)> {
    vec![
        ("VARD_TOKEN".into(), token.into()),
        ("VARD_PORTA".into(), porta.to_string()),
        ("VARD_DADOS".into(), dados.to_string_lossy().into_owned()),
        ("VARD_CONFIG".into(), config.to_string_lossy().into_owned()),
        ("VARD_VERSAO_APP".into(), versao.into()),
    ]
}

/// Constrói um DescritorServico completo para o núcleo.
pub fn descritor_nucleo(
    dev: bool,
    recursos: &Path,
    repo: &Path,
    porta: u16,
    dados: &Path,
    config: &Path,
    versao: &str,
) -> DescritorServico {
    let cmd = comando(dev, recursos, repo);
    let envs = ambiente("", porta, dados, config, versao); // token é gerado pelo loop_servico
    let caminho_log = dados.join("logs").join("nucleo.log");

    DescritorServico {
        id: "nucleo".into(),
        porta,
        comando: cmd,
        envs,
        caminho_log,
    }
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn comando_release_usa_python_embutido() {
        let (exe, args) = comando(false, Path::new("R"), Path::new("X"));
        assert!(
            exe.ends_with("nucleo/python/python.exe") || exe.ends_with(r"nucleo\python\python.exe"),
            "exe={exe:?}"
        );
        assert_eq!(&args[..3], &["-I", "-X", "utf8"]);
        assert!(args.contains(&"vard".to_string()));
        assert!(args.contains(&"servir".to_string()));
    }

    #[test]
    fn comando_dev_usa_uv_no_repo() {
        let (exe, args) = comando(true, Path::new("R"), Path::new("X"));
        assert_eq!(exe, PathBuf::from("uv"));
        assert!(args.iter().any(|a| a.ends_with("nucleo")));
        assert!(args.contains(&"servir".to_string()));
    }

    #[test]
    fn ambiente_tem_token_porta_e_pastas() {
        use std::collections::HashMap;
        let a: HashMap<_, _> = ambiente("t", 4700, Path::new("D"), Path::new("C"), "0.7.0")
            .into_iter()
            .collect();
        assert_eq!(a["VARD_TOKEN"], "t");
        assert_eq!(a["VARD_PORTA"], "4700");
        assert_eq!(a["VARD_DADOS"], "D");
        assert_eq!(a["VARD_CONFIG"], "C");
        assert_eq!(a["VARD_VERSAO_APP"], "0.7.0");
    }

    #[test]
    fn descritor_nucleo_tem_id_e_porta() {
        let desc = descritor_nucleo(
            false,
            Path::new("R"),
            Path::new("X"),
            4700,
            Path::new("D"),
            Path::new("C"),
            "0.7.0",
        );
        assert_eq!(desc.id, "nucleo");
        assert_eq!(desc.porta, 4700);
        assert!(desc.caminho_log.to_string_lossy().contains("nucleo.log"));
    }
}