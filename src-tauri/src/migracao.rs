//! Migração automática de `supervisor: false` para `supervisor: true`.
//!
//! Ao abrir a 0.9.6 com `supervisor: false`:
//! 1. Faz backup do `instalacao.json` original.
//! 2. Grava `supervisor: true` no arquivo.
//! 3. Encerra a bandeja Python pelo PID registrado em `pids/bandeja.pid`
//!    (conferindo executável e horário de início; nunca por nome).
//! 4. Ajusta o atalho de inicialização (Startup) para o `vard.exe`.
//!
//! Reversão: `trocar-instalacao.ps1 -Reverter` ou equivalente documentado.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

/// Executa a migração supervisor se aplicável. Retorna Ok(true) se migrou,
/// Ok(false) se já estava migrado ou não era necessário, Err se falhou.
pub fn migrar_se_necessario(
    arquivo_instalacao: &Path,
    pasta_dados: &Path,
    vard_exe: &Path,
) -> Result<bool, String> {
    // Lê instalacao.json atual
    let conteudo = fs::read_to_string(arquivo_instalacao)
        .map_err(|e| format!("não foi possível ler {}: {e}", arquivo_instalacao.display()))?;
    let mut config: Value = serde_json::from_str(&conteudo)
        .map_err(|e| format!("instalacao.json inválido: {e}"))?;

    // Se já é supervisor, nada a fazer
    if config.get("supervisor").and_then(|v| v.as_bool()) == Some(true) {
        return Ok(false);
    }

    // Backup do instalacao.json original
    let backup_dir = pasta_dados.join("fusao").join("backup-supervisor");
    fs::create_dir_all(&backup_dir)
        .map_err(|e| format!("não foi possível criar diretório de backup: {e}"))?;
    let backup_path = backup_dir.join("instalacao.json");
    fs::copy(arquivo_instalacao, &backup_path)
        .map_err(|e| format!("falha ao fazer backup do instalacao.json: {e}"))?;

    // Atualiza supervisor para true
    config["supervisor"] = Value::Bool(true);
    let novo_conteudo = serde_json::to_string_pretty(&config)
        .map_err(|e| format!("falha ao serializar instalacao.json: {e}"))?;
    // Escrita atômica: tmp + rename
    let tmp = arquivo_instalacao.with_extension("json.tmp");
    fs::write(&tmp, &novo_conteudo)
        .map_err(|e| format!("falha ao escrever instalacao.json temporário: {e}"))?;
    fs::rename(&tmp, arquivo_instalacao)
        .map_err(|e| format!("falha ao renomear instalacao.json: {e}"))?;

    // Encerra bandeja Python pelo PID registrado
    encerrar_bandeja_python(pasta_dados);

    // Ajusta atalho de inicialização para vard.exe
    ajustar_atalho_startup(vard_exe);

    Ok(true)
}

/// Encerra a bandeja Python usando o PID registrado em `pids/bandeja.pid`.
/// Formato do arquivo: `pid|start_time_iso` ou apenas `pid`.
/// Confere que o processo é realmente python/bandeja antes de matar.
fn encerrar_bandeja_python(pasta_dados: &Path) {
    let pid_file = pasta_dados.join("pids").join("bandeja.pid");
    let conteudo = match fs::read_to_string(&pid_file) {
        Ok(c) => c,
        Err(_) => return, // Sem arquivo de PID, nada a fazer
    };
    let linha = conteudo.trim();
    if linha.is_empty() {
        return;
    }

    // Formato gravado pelo vard-modo: "pid|início". Sem o início não dá para provar que o PID é o mesmo
    // processo (PIDs são reaproveitados depois de reiniciar o PC), então não encerra nada.
    let Some((pid, inicio_registrado)) = ler_pid_e_inicio(linha) else { return };

    // Verifica se o processo existe e é python (não mata por nome cegamente)
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // tasklist /FI "PID eq N" /FO CSV /NH → verifica se é python
        let output = std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
            .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
            .output();
        if let Ok(out) = output {
            let texto = String::from_utf8_lossy(&out.stdout);
            let nome_proc = texto.to_lowercase();
            // Só mata se for python (bandeja.py roda via uv/python)
            if !nome_proc.contains("python") && !nome_proc.contains("uv") {
                eprintln!(
                    "migracao: PID {pid} não é python/uv ({}), pulando encerramento da bandeja",
                    nome_proc.trim()
                );
                return;
            }
        } else {
            return; // Não conseguiu verificar, não mata
        }
        // E o início do processo vivo tem de bater com o registrado.
        let inicio_vivo = std::process::Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command",
                   &format!("(Get-Process -Id {pid} -ErrorAction Stop).StartTime.ToString('o')")])
            .creation_flags(0x0800_0000)
            .output();
        let Ok(saida) = inicio_vivo else { return };
        if !mesmo_inicio(&inicio_registrado, String::from_utf8_lossy(&saida.stdout).trim()) {
            eprintln!("migracao: PID {pid} tem outro início; a bandeja registrada já não existe, nada encerrado");
            return;
        }

        // Mata a árvore de processos
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(0x0800_0000)
            .output();
    }

    // Remove o arquivo de PID após encerrar
    let _ = fs::remove_file(&pid_file);
}

/// Lê `pid|início` do arquivo de PID; sem os dois campos válidos devolve `None`.
fn ler_pid_e_inicio(linha: &str) -> Option<(u32, String)> {
    let (pid, inicio) = linha.split_once('|')?;
    let pid = pid.trim().parse().ok()?;
    let inicio = inicio.trim();
    if inicio.is_empty() { return None; }
    Some((pid, inicio.to_string()))
}

/// Os dois instantes (ISO 8601 com fuso) apontam para o mesmo início de processo, com folga de 2 s.
fn mesmo_inicio(registrado: &str, vivo: &str) -> bool {
    match (chrono::DateTime::parse_from_rfc3339(registrado), chrono::DateTime::parse_from_rfc3339(vivo)) {
        (Ok(a), Ok(b)) => (a - b).num_milliseconds().abs() <= 2000,
        _ => false,
    }
}

/// Ajusta o atalho Vard.lnk na pasta Startup para apontar para vard.exe.
/// Usa PowerShell/WScript.Shell porque criar .lnk nativo em Rust puro é complexo.
fn ajustar_atalho_startup(vard_exe: &Path) {
    if !vard_exe.exists() {
        eprintln!(
            "migracao: vard.exe não encontrado em {}, atalho não ajustado",
            vard_exe.display()
        );
        return;
    }

    let exe_str = vard_exe.display().to_string().replace('\\', "\\\\");
    let work_dir = vard_exe
        .parent()
        .map(|p| p.display().to_string().replace('\\', "\\\\"))
        .unwrap_or_default();

    // Script PowerShell mínimo para criar/atualizar o atalho
    let script = format!(
        r#"$s = [Environment]::GetFolderPath('Startup'); $l = Join-Path $s 'Vard.lnk'; $sh = New-Object -ComObject WScript.Shell; $sc = $sh.CreateShortcut($l); $sc.TargetPath = '{exe}'; $sc.Arguments = ''; $sc.WorkingDirectory = '{dir}'; $sc.IconLocation = '{exe},0'; $sc.Save()"#,
        exe = exe_str,
        dir = work_dir,
    );

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let encoded = base64_encode_utf16le(&script);
        let result = std::process::Command::new("powershell")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                &encoded,
            ])
            .creation_flags(0x0800_0000)
            .output();
        if let Err(e) = result {
            eprintln!("migracao: falha ao ajustar atalho de startup: {e}");
        }
    }
}

/// Codifica string UTF-8 para Base64 de UTF-16LE (formato do -EncodedCommand do PowerShell).
#[cfg(windows)]
fn base64_encode_utf16le(s: &str) -> String {
    use base64::Engine;
    let utf16: Vec<u8> = s
        .encode_utf16()
        .flat_map(|c| c.to_le_bytes())
        .collect();
    base64::engine::general_purpose::STANDARD.encode(&utf16)
}

#[cfg(test)]
mod testes {
    #[test]
    fn pid_sem_inicio_nao_serve_para_encerrar() {
        assert_eq!(super::ler_pid_e_inicio("11980"), None);
        assert_eq!(super::ler_pid_e_inicio("11980|2026-10-17T15:48:18.4412504-04:00"),
                   Some((11980, "2026-10-17T15:48:18.4412504-04:00".to_string())));
    }

    #[test]
    fn inicio_tem_de_bater_para_encerrar() {
        let reg = "2026-10-17T15:48:18.4412504-04:00";
        assert!(super::mesmo_inicio(reg, "2026-10-17T15:48:19.0000000-04:00"));
        assert!(super::mesmo_inicio(reg, "2026-10-17T19:48:18.4412504+00:00"));
        assert!(!super::mesmo_inicio(reg, "2026-10-17T16:02:00.0000000-04:00"));
        assert!(!super::mesmo_inicio(reg, "lixo"));
    }

    use super::*;
    use std::fs;

    #[test]
    fn migrar_muda_supervisor_para_true() {
        let dir = tempfile::tempdir().unwrap();
        let inst = dir.path().join("instalacao.json");
        fs::write(
            &inst,
            r#"{"raiz_codigo":".","supervisor":false,"servicos":{}}"#,
        )
        .unwrap();
        let dados = dir.path().join("dados");
        fs::create_dir_all(&dados).unwrap();
        let exe = dir.path().join("vard.exe");
        fs::write(&exe, b"falso").unwrap();

        let resultado = migrar_se_necessario(&inst, &dados, &exe);
        assert!(resultado.is_ok());
        assert!(resultado.unwrap(), "deveria ter migrado");

        let novo: Value =
            serde_json::from_str(&fs::read_to_string(&inst).unwrap()).unwrap();
        assert_eq!(novo["supervisor"], true);

        // Backup deve existir
        assert!(dados
            .join("fusao")
            .join("backup-supervisor")
            .join("instalacao.json")
            .exists());
    }

    #[test]
    fn migrar_ja_supervisor_retorna_false() {
        let dir = tempfile::tempdir().unwrap();
        let inst = dir.path().join("instalacao.json");
        fs::write(
            &inst,
            r#"{"raiz_codigo":".","supervisor":true,"servicos":{}}"#,
        )
        .unwrap();
        let dados = dir.path().join("dados");
        fs::create_dir_all(&dados).unwrap();
        let exe = dir.path().join("vard.exe");

        let resultado = migrar_se_necessario(&inst, &dados, &exe);
        assert!(resultado.is_ok());
        assert!(!resultado.unwrap(), "não deveria migrar quando já é supervisor");
    }

    #[test]
    fn encerrar_bandeja_sem_pid_nao_falha() {
        let dir = tempfile::tempdir().unwrap();
        // Sem pasta pids nem arquivo bandeja.pid — não deve panicar
        encerrar_bandeja_python(dir.path());
    }

    #[test]
    fn encerrar_bandeja_pid_invalido_nao_falha() {
        let dir = tempfile::tempdir().unwrap();
        let pids = dir.path().join("pids");
        fs::create_dir_all(&pids).unwrap();
        fs::write(pids.join("bandeja.pid"), "abc|2026-01-01T00:00:00Z").unwrap();
        // PID inválido — não deve panicar
        encerrar_bandeja_python(dir.path());
    }

    #[test]
    fn encerrar_bandeja_pid_inexistente_nao_falha() {
        let dir = tempfile::tempdir().unwrap();
        let pids = dir.path().join("pids");
        fs::create_dir_all(&pids).unwrap();
        // PID 99999999 provavelmente não existe
        fs::write(pids.join("bandeja.pid"), "99999999|2026-01-01T00:00:00Z").unwrap();
        encerrar_bandeja_python(dir.path());
    }
}