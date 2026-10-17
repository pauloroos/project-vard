//! Migração automática de `supervisor: false` para `supervisor: true`.
//!
//! Pré-checa o núcleo, preserva configuração e atalho e aguarda saúde própria.
//! Só encerra a bandeja Python depois da confirmação. Sem saúde em 60 s, restaura
//! os arquivos e entrega ao caminho legado após liberar os filhos próprios.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

/// Executa a migração supervisor se aplicável. Retorna Ok(true) se migrou,
/// Ok(false) se já estava migrado ou não era necessário, Err se falhou.
pub fn migrar_se_necessario(
    arquivo_instalacao: &Path,
    pasta_dados: &Path,
    vard_exe: &Path,
    nucleo: Result<crate::servicos::DescritorServico, String>,
    atalho: &Path,
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

    // Não altera configuração, atalho nem processos antes da pré-checagem.
    if let Err(motivo) = nucleo {
        crate::instalacao::registrar_setup(pasta_dados, &format!("migração não realizada: {motivo}"));
        return Err(motivo);
    }

    // Backup do instalacao.json original
    let backup_dir = pasta_dados.join("fusao").join("backup-supervisor");
    fs::create_dir_all(&backup_dir)
        .map_err(|e| format!("não foi possível criar diretório de backup: {e}"))?;
    let backup_path = backup_dir.join("instalacao.json");
    fs::copy(arquivo_instalacao, &backup_path)
        .map_err(|e| format!("falha ao fazer backup do instalacao.json: {e}"))?;
    let backup_atalho = backup_dir.join("Vard.lnk");
    if atalho.exists() {
        fs::copy(atalho, &backup_atalho).map_err(|_| "falha ao preservar atalho")?;
    } else if backup_atalho.exists() {
        fs::remove_file(&backup_atalho).map_err(|_| "falha ao atualizar backup do atalho")?;
    }
    fs::write(backup_dir.join("atalho-existia"), if atalho.exists() { "sim" } else { "nao" })
        .map_err(|_| "falha ao registrar estado do atalho")?;

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

    // Ajusta atalho de inicialização para vard.exe
    if let Err(erro) = ajustar_atalho_startup(vard_exe, atalho) {
        reverter(arquivo_instalacao, pasta_dados, atalho)?;
        return Err(erro);
    }

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
fn ajustar_atalho_startup(vard_exe: &Path, atalho: &Path) -> Result<(), String> {
    if !vard_exe.exists() {
        return Err("migração: executável do aplicativo não encontrado".into());
    }

    let exe_str = vard_exe.display().to_string().replace('\'', "''");
    let work_dir = vard_exe
        .parent()
        .map(|p| p.display().to_string().replace('\'', "''"))
        .unwrap_or_default();

    // Script PowerShell mínimo para criar/atualizar o atalho
    let script = format!(
        r#"$ErrorActionPreference = 'Stop'; $l = '{atalho}'; $sh = New-Object -ComObject WScript.Shell; $sc = $sh.CreateShortcut($l); $sc.TargetPath = '{exe}'; $sc.Arguments = ''; $sc.WorkingDirectory = '{dir}'; $sc.IconLocation = '{exe},0'; $sc.Save()"#,
        exe = exe_str,
        dir = work_dir,
        atalho = atalho.display().to_string().replace('\'', "''"),
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
        let saida = result.map_err(|_| "migração: falha ao executar ajuste de atalho")?;
        if !saida.status.success() { return Err("migração: ajuste de atalho recusado".into()); }
    }
    Ok(())
}

/// Restaura bytes da configuração e o estado exato do atalho, inclusive ausência.
pub fn reverter(arquivo: &Path, dados: &Path, atalho: &Path) -> Result<(), String> {
    let backup = dados.join("fusao/backup-supervisor");
    let tmp = arquivo.with_extension("json.tmp");
    fs::copy(backup.join("instalacao.json"), &tmp).map_err(|_| "falha ao ler backup da instalação")?;
    fs::rename(tmp, arquivo).map_err(|_| "falha ao restaurar instalação")?;
    match fs::read_to_string(backup.join("atalho-existia")).map_err(|_| "backup do atalho incompleto")?.as_str() {
        "sim" => { fs::copy(backup.join("Vard.lnk"), atalho).map_err(|_| "falha ao restaurar atalho")?; }
        "nao" => { if atalho.exists() { fs::remove_file(atalho).map_err(|_| "falha ao remover atalho criado")?; } }
        _ => return Err("backup do atalho inválido".into()),
    }
    crate::instalacao::registrar_setup(dados, "migração revertida: configuração e atalho restaurados");
    Ok(())
}

pub fn atalho_startup() -> Result<PathBuf, String> {
    std::env::var_os("APPDATA").map(PathBuf::from)
        .map(|p| p.join("Microsoft/Windows/Start Menu/Programs/Startup/Vard.lnk"))
        .ok_or_else(|| "pasta Startup indisponível".into())
}

/// Só confirma a troca depois que o núcleo próprio respondeu à sonda com PID.
pub fn aguardar_saude(prazo: std::time::Duration, mut saudavel: impl FnMut() -> bool) -> bool {
    let fim = std::time::Instant::now() + prazo;
    loop {
        if saudavel() { return true; }
        if std::time::Instant::now() >= fim { return false; }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
}

pub fn confirmar(dados: &Path) {
    encerrar_bandeja_python(dados);
    crate::instalacao::registrar_setup(dados, "migração confirmada: núcleo próprio respondeu");
}

/// Retorno transacional: restaura os arquivos mesmo se a parada falhar, mas só
/// entrega o controle ao script antigo depois que todos os filhos próprios saíram.
pub fn concluir_ou_reverter(
    arquivo: &Path, dados: &Path, atalho: &Path, respondeu: bool,
    parar: impl FnOnce() -> Result<(), String>,
    iniciar_antigo: impl FnOnce() -> Result<(), String>,
) -> Result<bool, String> {
    if respondeu { confirmar(dados); return Ok(true); }
    crate::instalacao::registrar_setup(dados, "setup: núcleo não confirmou saúde no prazo de 60 s; revertendo migração");
    let parada = parar();
    reverter(arquivo, dados, atalho)?;
    parada?;
    iniciar_antigo()?;
    Ok(false)
}

/// Comando legado vetorizado e com ambiente limpo; nunca executado pelas provas.
pub fn comando_legado(config: &crate::instalacao::InstalacaoConfig, arquivo: &Path, dados: &Path) -> Result<std::process::Command, String> {
    let raiz = Path::new(&config.raiz_codigo);
    let novo = raiz.join("scripts/windows/vard-modo.ps1");
    let script = if novo.is_file() { novo } else { raiz.join("deploy/vard-modo.ps1") };
    if !script.is_file() { return Err("caminho antigo: vard-modo.ps1 não encontrado".into()); }
    let mut comando = std::process::Command::new("powershell.exe");
    crate::servicos::limpar_ambiente(&mut comando);
    comando.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"])
        .arg(script).args(["iniciar", "-Instalacao"]).arg(arquivo)
        .current_dir(raiz).env("VARD_INSTALACAO", arquivo).env("VARD_DADOS", dados)
        .stdin(std::process::Stdio::null());
    Ok(comando)
}

pub fn iniciar_legado(config: &crate::instalacao::InstalacaoConfig, arquivo: &Path, dados: &Path) -> Result<(), String> {
    let mut comando = comando_legado(config, arquivo, dados)?;
    let logs = dados.join("logs");
    fs::create_dir_all(&logs).map_err(|_| "falha ao criar logs do retorno")?;
    comando.stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::piped());
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        comando.creation_flags(0x0800_0000);
    }
    let mut filho = comando.spawn().map_err(|_| "falha ao iniciar caminho antigo")?;
    crate::instalacao::registrar_setup(dados, &format!("retorno: powershell.exe iniciou caminho antigo (pid {}; início {})", filho.id(), chrono::Utc::now().to_rfc3339()));
    fn registrar_saida(saida: impl std::io::Read + Send + 'static, caminho: PathBuf) -> std::thread::JoinHandle<()> {
        std::thread::spawn(move || {
            use std::io::BufRead;
            let mut log = crate::supervisor::Log::abrir(caminho);
            for linha in std::io::BufReader::new(saida).lines().map_while(Result::ok) {
                log.linha(&crate::supervisor::redigir(&linha));
            }
        })
    }
    let saida = filho.stdout.take().map(|s| registrar_saida(s, logs.join("retorno-legado.log")));
    let erros = filho.stderr.take().map(|s| registrar_saida(s, logs.join("retorno-legado-erros.log")));
    std::thread::spawn(move || {
        let _ = filho.wait();
        if let Some(t) = saida { let _ = t.join(); }
        if let Some(t) = erros { let _ = t.join(); }
    });
    Ok(())
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
    fn cenario_retorno() -> (tempfile::TempDir, PathBuf, PathBuf, PathBuf) {
        let pasta = tempfile::tempdir().unwrap();
        let arquivo = pasta.path().join("instalacao.json");
        let atalho = pasta.path().join("Vard.lnk");
        let backup = pasta.path().join("fusao/backup-supervisor");
        fs::create_dir_all(&backup).unwrap();
        fs::write(&arquivo, r#"{"supervisor":true}"#).unwrap();
        fs::write(backup.join("instalacao.json"), r#"{"supervisor":false,"campo_preservado":42}"#).unwrap();
        fs::write(backup.join("atalho-existia"), "sim").unwrap();
        fs::write(backup.join("Vard.lnk"), b"atalho original ficticio").unwrap();
        fs::write(&atalho, b"atalho novo ficticio").unwrap();
        (pasta, arquivo, atalho, backup)
    }

    #[test]
    fn prazo_sem_saude_restaura_backup_e_atalho_antes_de_iniciar_antigo() {
        let (pasta, arquivo, atalho, _) = cenario_retorno();
        let parado = std::cell::Cell::new(false);
        let iniciado = std::cell::Cell::new(false);
        let saudavel = aguardar_saude(std::time::Duration::ZERO, || false);
        assert!(!saudavel);
        let confirmado = concluir_ou_reverter(&arquivo, pasta.path(), &atalho, saudavel,
            || { parado.set(true); Ok(()) },
            || {
                assert!(parado.get());
                let config: Value = serde_json::from_str(&fs::read_to_string(&arquivo).unwrap()).unwrap();
                assert_eq!(config["supervisor"], false);
                assert_eq!(config["campo_preservado"], 42);
                assert_eq!(fs::read(&atalho).unwrap(), b"atalho original ficticio");
                iniciado.set(true);
                Ok(())
            }).unwrap();
        assert!(!confirmado && iniciado.get());
        let log = fs::read_to_string(pasta.path().join("logs/setup.log")).unwrap();
        assert!(log.contains("60 s") && log.contains("restaurados"));
    }

    #[test]
    fn parada_incompleta_restaura_arquivos_mas_nao_disputa_portas_com_legado() {
        let (pasta, arquivo, atalho, _) = cenario_retorno();
        assert!(concluir_ou_reverter(&arquivo, pasta.path(), &atalho, false,
            || Err("parada incompleta".into()), || panic!("não pode iniciar legado com filho vivo")).is_err());
        assert_eq!(fs::read(&atalho).unwrap(), b"atalho original ficticio");
        assert!(fs::read_to_string(arquivo).unwrap().contains("false"));
    }

    #[test]
    fn retorno_remove_atalho_quando_era_ausente_e_confirmacao_preserva_migracao() {
        let (pasta, arquivo, atalho, backup) = cenario_retorno();
        assert!(aguardar_saude(std::time::Duration::ZERO, || true));
        assert!(concluir_ou_reverter(&arquivo, pasta.path(), &atalho, true,
            || panic!("não deve parar serviço saudável"), || panic!("não deve iniciar antigo")).unwrap());
        assert_eq!(fs::read(&atalho).unwrap(), b"atalho novo ficticio");
        fs::write(backup.join("atalho-existia"), "nao").unwrap();
        reverter(&arquivo, pasta.path(), &atalho).unwrap();
        assert!(!atalho.exists());
    }

    #[test]
    fn comando_de_retorno_usa_script_da_raiz_e_arquivo_explicito() {
        let pasta = tempfile::tempdir().unwrap();
        let script = pasta.path().join("scripts/windows/vard-modo.ps1");
        fs::create_dir_all(script.parent().unwrap()).unwrap();
        fs::write(&script, "# dublê: nunca executado").unwrap();
        let arquivo = pasta.path().join("instalacao ficticia.json");
        let config = crate::instalacao::InstalacaoConfig { raiz_codigo: pasta.path().to_string_lossy().into_owned(), ..Default::default() };
        let cmd = comando_legado(&config, &arquivo, pasta.path()).unwrap();
        let args: Vec<_> = cmd.get_args().collect();
        assert!(args.contains(&script.as_os_str()));
        assert_eq!(args.last(), Some(&arquivo.as_os_str()));
        assert_eq!(cmd.get_current_dir(), Some(pasta.path()));
    }
    #[test]
    fn nao_migra_sem_nucleo_disponivel() {
        let dir = tempfile::tempdir().unwrap();
        let inst = dir.path().join("instalacao.json");
        let original = serde_json::json!({"raiz_codigo": dir.path().join("ausente"), "supervisor": false});
        std::fs::write(&inst, original.to_string()).unwrap();
        let resultado = super::migrar_se_necessario(&inst, dir.path(), &dir.path().join("vard-ausente.exe"), Err("nucleo ausente".into()), &dir.path().join("Vard.lnk"));
        assert!(resultado.is_err(), "sem núcleo montável a migração deve ser recusada");
        assert_eq!(std::fs::read_to_string(inst).unwrap(), original.to_string());
    }
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

        let resultado = migrar_se_necessario(&inst, &dados, &exe, Ok(crate::nucleo::descritor_nucleo(false, dir.path(), dir.path(), 0, &dados, &dados, "teste")), &dir.path().join("Vard.lnk"));
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

        let resultado = migrar_se_necessario(&inst, &dados, &exe, Ok(crate::nucleo::descritor_nucleo(false, dir.path(), dir.path(), 0, &dados, &dados, "teste")), &dir.path().join("Vard.lnk"));
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
