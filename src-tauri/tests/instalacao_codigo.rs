//! Integração dos descritores com o formato de instalação do script Windows.
use openjarvis_hud_lib::instalacao;
use std::path::{Path, PathBuf};

fn falso(caminho: &Path) -> PathBuf {
    std::fs::create_dir_all(caminho.parent().unwrap()).unwrap();
    std::fs::write(caminho, b"executavel ficticio").unwrap();
    caminho.to_path_buf()
}

#[test]
fn formato_do_script_aceita_nucleo_e_interpretes_externos_sem_booleanos() {
    let pasta = tempfile::tempdir().unwrap();
    let raiz = pasta.path().join("codigo ficticio");
    let nucleo = falso(&raiz.join("nucleo/.venv/Scripts/python.exe"));
    falso(&raiz.join("nucleo/server.py"));
    std::fs::create_dir_all(raiz.join("voz")).unwrap();
    std::fs::create_dir_all(raiz.join("reuniao")).unwrap();
    let voz = falso(&pasta.path().join("ambientes externos/voz/python.exe"));
    let reuniao = falso(&pasta.path().join("ambientes externos/reuniao/python.exe"));
    let arquivo = pasta.path().join("instalacao.json");
    std::fs::write(&arquivo, serde_json::to_vec(&serde_json::json!({
        "raiz_codigo": raiz, "servicos": {"voz_python": voz, "reuniao_python": reuniao},
        "openjarvis_src": "", "openjarvis_home": ""
    })).unwrap()).unwrap();
    let config = instalacao::ler_instalacao(&arquivo).unwrap();
    let desc = instalacao::descritor_nucleo(false, &pasta.path().join("recursos"), Path::new("ignorado"), &config, pasta.path(), "teste");
    assert_eq!(desc.comando.0, nucleo, "release sem pacote deve usar raiz_codigo");
    assert_eq!(desc.comando.1, ["-X", "utf8", "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "4700", "--timeout-graceful-shutdown", "2"]);
    let desc = instalacao::descritor_voz(&config, pasta.path()).expect("voz_python habilita voz");
    assert_eq!(desc.pasta_trabalho, Some(raiz.join("voz")));
    assert_eq!(desc.comando.0, voz);
    assert_eq!(desc.comando.1, ["-X", "utf8", "-m", "vard_voz"]);
    let desc = instalacao::descritor_reuniao(&config, pasta.path()).expect("reuniao_python habilita reunião");
    assert_eq!(desc.pasta_trabalho, Some(raiz.join("reuniao")));
    assert_eq!(desc.comando.0, reuniao);
    assert_eq!(desc.comando.1, ["-X", "utf8", "-m", "vard_reuniao"]);
}

#[test]
fn release_prefere_pacote_existente_e_prechecagem_recusa_interprete_ausente() {
    let pasta = tempfile::tempdir().unwrap();
    let config: instalacao::InstalacaoConfig = serde_json::from_value(serde_json::json!({"raiz_codigo": pasta.path().join("ausente")})).unwrap();
    assert!(instalacao::preparar_nucleo(false, pasta.path(), pasta.path(), &config, pasta.path(), "teste").is_err());
    let exe = falso(&pasta.path().join("nucleo/python/python.exe"));
    let desc = instalacao::preparar_nucleo(false, pasta.path(), pasta.path(), &config, pasta.path(), "teste").unwrap();
    assert_eq!(desc.comando.0, exe);
    assert_eq!(desc.comando.1, ["-I", "-X", "utf8", "-m", "vard", "servir"]);
}

#[test]
fn legado_sem_subpasta_nucleo_e_booleanos_continua_aceito() {
    let pasta = tempfile::tempdir().unwrap();
    let exe = falso(&pasta.path().join(".venv/Scripts/python.exe"));
    falso(&pasta.path().join("server.py"));
    falso(&pasta.path().join("voz/.venv/Scripts/python.exe"));
    falso(&pasta.path().join("reuniao/.venv/Scripts/python.exe"));
    let config = serde_json::from_value(serde_json::json!({"raiz_codigo": pasta.path(), "servicos": {"voz": true, "reuniao": true, "porta_nucleo": 4901}})).unwrap();
    let desc = instalacao::preparar_nucleo(false, pasta.path(), pasta.path(), &config, pasta.path(), "teste").unwrap();
    assert_eq!(desc.comando.0, exe);
    assert_eq!(desc.pasta_trabalho, Some(pasta.path().to_path_buf()));
    assert!(desc.comando.1.contains(&"4901".into()));
    assert!(instalacao::descritor_voz(&config, pasta.path()).is_some());
    assert!(instalacao::descritor_reuniao(&config, pasta.path()).is_some());
}

fn executavel_falso() -> &'static Path {
    static EXE: std::sync::OnceLock<(tempfile::TempDir, PathBuf)> = std::sync::OnceLock::new();
    &EXE.get_or_init(|| {
        let pasta = tempfile::tempdir().unwrap();
        let fonte = pasta.path().join("servico_falso.rs");
        std::fs::write(&fonte, r#"
use std::{env, io::{Read, Write}, net::TcpListener};
fn main() {
    println!("PASTA={}", env::current_dir().unwrap().display());
    println!("ARGS={}", env::args().skip(1).collect::<Vec<_>>().join("|"));
    for nome in ["VARD_CONFIG", "VARD_INSTALACAO", "OPENJARVIS_HOME", "PYTHONUTF8"] {
        println!("{}={}", nome, env::var(nome).unwrap_or_default());
    }
    for nome in ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "ORCA_AGENT_SECRET"] {
        println!("{}={}", nome, env::var_os(nome).is_some());
    }
    if env::var("VARD_FALSO_HTTP").as_deref() != Ok("1") { return; }
    let listener = TcpListener::bind(("127.0.0.1", env::var("VARD_PORTA").unwrap().parse::<u16>().unwrap())).unwrap();
    for mut fluxo in listener.incoming().flatten() {
        fluxo.set_read_timeout(Some(std::time::Duration::from_secs(2))).unwrap();
        let mut buffer = [0; 4096];
        let _ = fluxo.read(&mut buffer);
        let corpo = format!("{{\"ok\":true,\"versao\":\"teste\",\"pid\":{}}}", std::process::id());
        let _ = write!(fluxo, "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", corpo.len(), corpo);
    }
}
"#).unwrap();
        let exe = pasta.path().join("servico_falso.exe");
        let saida = std::process::Command::new("rustc").arg(&fonte).arg("-o").arg(&exe).output().unwrap();
        assert!(saida.status.success(), "compilação do dublê falhou");
        (pasta, exe)
    }).1
}

#[test]
fn executaveis_falsos_recebem_comando_cwd_ambiente_e_sao_encerrados() {
    use openjarvis_hud_lib::{servicos, supervisor::EstadoServico};
    use std::time::{Duration, Instant};
    let pasta = tempfile::tempdir().unwrap();
    let raiz = pasta.path().join("codigo ficticio");
    let arquivo = pasta.path().join("instalacao.json");
    struct Ambiente(Vec<(String, Option<std::ffi::OsString>)>);
    impl Drop for Ambiente {
        fn drop(&mut self) {
            for (nome, valor) in self.0.drain(..) {
                unsafe { if let Some(v) = valor { std::env::set_var(nome, v); } else { std::env::remove_var(nome); } }
            }
        }
    }
    // Os marcadores existem no pai; a prova exige removê-los efetivamente do filho.
    let nomes = ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "ORCA_AGENT_SECRET"];
    let _ambiente = Ambiente(nomes.iter().map(|n| (n.to_string(), std::env::var_os(n))).collect());
    for nome in nomes { unsafe { std::env::set_var(nome, "marcador-ficticio"); } }
    let copiar = |caminho: PathBuf| { falso(&caminho); std::fs::copy(executavel_falso(), &caminho).unwrap(); caminho };
    copiar(raiz.join("nucleo/.venv/Scripts/python.exe"));
    falso(&raiz.join("nucleo/server.py"));
    std::fs::create_dir_all(raiz.join("voz")).unwrap();
    std::fs::create_dir_all(raiz.join("reuniao")).unwrap();
    let voz = copiar(pasta.path().join("venvs/voz/python.exe"));
    let reuniao = copiar(pasta.path().join("venvs/reuniao/python.exe"));
    let oj = pasta.path().join("openjarvis source");
    copiar(oj.join(if cfg!(windows) { ".venv/Scripts/jarvis.exe" } else { ".venv/bin/jarvis" }));
    let home = pasta.path().join("openjarvis dados");
    let config: instalacao::InstalacaoConfig = serde_json::from_value(serde_json::json!({
        "raiz_codigo": raiz, "supervisor": true, "openjarvis_src": oj, "openjarvis_home": home,
        "servicos": {"voz_python": voz, "reuniao_python": reuniao, "openjarvis": true}
    })).unwrap();
    std::fs::write(&arquivo, serde_json::to_vec(&config).unwrap()).unwrap();
    let mut descritores = vec![instalacao::preparar_nucleo(false, pasta.path(), pasta.path(), &config, pasta.path(), "teste").unwrap(),
        instalacao::descritor_voz(&config, pasta.path()).unwrap(), instalacao::descritor_reuniao(&config, pasta.path()).unwrap()];
    // Lê HUD fictício; nenhuma decisão consulta a configuração do usuário.
    let desc_oj = {
        let antigo = std::env::var_os("VARD_HUD_CONFIG_DIR");
        unsafe { std::env::set_var("VARD_HUD_CONFIG_DIR", pasta.path()); }
        let desc = instalacao::descritor_openjarvis(&config, pasta.path()).unwrap();
        unsafe { if let Some(v) = antigo { std::env::set_var("VARD_HUD_CONFIG_DIR", v); } else { std::env::remove_var("VARD_HUD_CONFIG_DIR"); } }
        desc
    };
    assert_eq!(desc_oj.comando.1, ["serve", "--agent", "orchestrator"]);
    descritores.push(desc_oj);
    let mut ids = Vec::new();
    let mut portas = Vec::new();
    struct Limpeza<'a>(&'a mut Vec<String>);
    impl Drop for Limpeza<'_> { fn drop(&mut self) { servicos::parar_e_aguardar(self.0, Duration::from_secs(5)).unwrap(); } }
    let limpeza = Limpeza(&mut ids);
    for mut desc in descritores {
        let esperado = desc.pasta_trabalho.as_ref().unwrap();
        let args = desc.comando.1.join("|");
        // Usa exatamente o lançador de produção; saída do dublê só contém dados fictícios.
        desc.envs.extend([("VARD_CONFIG".into(), pasta.path().join("config").to_string_lossy().into_owned()), ("VARD_INSTALACAO".into(), arquivo.to_string_lossy().into_owned())]);
        let saida = servicos::montar_comando(&desc).output().unwrap();
        assert!(saida.status.success());
        let texto = String::from_utf8(saida.stdout).unwrap();
        assert!(texto.contains(&format!("PASTA={}", esperado.display())));
        assert!(texto.contains(&format!("ARGS={args}")));
        assert!(texto.contains(&format!("VARD_INSTALACAO={}", arquivo.display())));
        for nome in ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "ORCA_AGENT_SECRET"] {
            assert!(texto.contains(&format!("{nome}=false")));
        }
        if desc.id == "openjarvis" { assert!(texto.contains(&format!("OPENJARVIS_HOME={}", home.display()))); }
        let reserva = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        desc.porta = reserva.local_addr().unwrap().port();
        portas.push(desc.porta);
        drop(reserva);
        desc.envs.push(("VARD_FALSO_HTTP".into(), "1".into()));
        let id = desc.id.clone();
        servicos::iniciar(desc).unwrap();
        limpeza.0.push(id.clone());
        let fim = Instant::now() + Duration::from_secs(10);
        while servicos::foto(&id).unwrap().estado != EstadoServico::Ok {
            assert!(Instant::now() < fim, "dublê não respondeu");
            std::thread::sleep(Duration::from_millis(50));
        }
    }
    drop(limpeza);
    for id in ids { assert!(servicos::foto(&id).is_err(), "registro removido após liberar o processo"); }
    for porta in portas { assert!(std::net::TcpStream::connect(("127.0.0.1", porta)).is_err(), "porta do dublê deve estar livre"); }
}
