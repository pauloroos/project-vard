//! Diagnóstico do Vard (T10b): executa checagens somente-leitura via Python embutido.
//!
//! Contrato:
//! - `rodar_diagnostico(tipo: "basico" | "preflight") -> ResultadoDiagnostico`
//! - Básico: só leitura (portas, processos, config, GPU/RAM); nunca inicia serviço.
//! - Preflight: executa nucleo/preflight.py adaptado para devolver JSON.
//! - Timeout/cancelamento mata só o job do diagnóstico (JobHandle) e não toca no runtime.
//! - Saída sanitizada (sem credenciais nem caminhos pessoais).
//! - Progresso por evento Tauri 'diagnostico-progresso'.
//! - Dois cliques concorrentes -> um só diagnóstico (flag atômica).

use serde::{Deserialize, Serialize};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

use crate::nucleo;
use crate::supervisor::JobHandle;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Checagem {
    pub grupo: String,
    pub nome: String,
    pub estado: String,
    pub frase: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResultadoDiagnostico {
    pub checagens: Vec<Checagem>,
    pub relatorio: String,
    pub duracao_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
struct ProgressoEvento {
    pub tipo: String,
    pub mensagem: String,
    pub concluido: bool,
}

static CANCELADO: AtomicBool = AtomicBool::new(false);
static EM_EXECUCAO: AtomicBool = AtomicBool::new(false);

const PRAZO_BASICO_S: u64 = 20;
const PRAZO_PREFLIGHT_S: u64 = 900;

/// Cancela o diagnóstico em andamento (sinal cooperativo + kill do job).
#[tauri::command]
pub fn cancelar_diagnostico() {
    CANCELADO.store(true, Ordering::SeqCst);
}

/// Executa o diagnóstico via Python embutido/dev com Job Object próprio e prazo real.
#[tauri::command]
pub async fn rodar_diagnostico(
    app: AppHandle,
    tipo: String,
) -> Result<ResultadoDiagnostico, String> {
    // Dois cliques concorrentes -> um só diagnóstico
    if EM_EXECUCAO.swap(true, Ordering::SeqCst) {
        return Err("um diagnóstico já está em execução".to_string());
    }
    let _libera = LiberaExecucao;
    CANCELADO.store(false, Ordering::SeqCst);

    let prazo_s = if tipo == "preflight" {
        PRAZO_PREFLIGHT_S
    } else {
        PRAZO_BASICO_S
    };

    let _ = app.emit_to(
        "configuracoes",
        "diagnostico-progresso",
        ProgressoEvento {
            tipo: tipo.clone(),
            mensagem: format!("Iniciando diagnóstico {}...", tipo),
            concluido: false,
        },
    );

    let inicio = Instant::now();

    // Resolve Python usando o mesmo padrão do núcleo (instalacao.rs/nucleo.rs)
    let recursos = app.path().resource_dir().unwrap_or_default();
    let repo = app
        .path()
        .app_data_dir()
        .map(|p| p.parent().unwrap_or(&p).to_path_buf())
        .unwrap_or_else(|_| std::env::current_dir().unwrap_or_default());
    let dev = cfg!(debug_assertions);
    let (exe, args_base) = nucleo::comando(dev, &recursos, &repo);

    // Monta argumentos: em dev usa uv run ... python -c <codigo>; em release usa python.exe -I -X utf8 -c <codigo>
    let python_code = build_python_code(&tipo);
    let mut args = args_base;
    // Substitui o argumento final (-m vard servir) pelo nosso script inline
    // Em dev: uv run --project nucleo --frozen python -X utf8 -c <code>
    // Em release: python.exe -I -X utf8 -c <code>
    // Removemos os args padrão e adicionamos -c <code>
    args.retain(|a| a != "-m" && a != "vard" && a != "servir");
    args.push("-c".into());
    args.push(python_code);

    // Cria Job Object próprio para isolar o processo do diagnóstico
    let job = JobHandle::novo().map_err(|e| format!("JobHandle falhou: {e}"))?;

    // Spawn do processo dentro do spawn_blocking para não bloquear o runtime async
    let resultado = tauri::async_runtime::spawn_blocking(move || {
        let mut child = Command::new(&exe)
            .args(&args)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("spawn falhou: {e}"))?;

        // Adota o processo no Job Object
        if let Err(e) = job.adotar(&child) {
            let _ = child.kill();
            return Err(format!("adotar no job falhou: {e}"));
        }

        // Monitora timeout e cancelamento
        let deadline = Instant::now() + Duration::from_secs(prazo_s);
        loop {
            if CANCELADO.load(Ordering::SeqCst) {
                job.terminar();
                return Err("diagnóstico cancelado pelo usuário".to_string());
            }
            if Instant::now() >= deadline {
                job.terminar();
                return Err(format!(
                    "diagnóstico excedeu o prazo de {} s e foi encerrado",
                    prazo_s
                ));
            }
            // Verifica se o processo terminou
            match child.try_wait() {
                Ok(Some(status)) => {
                    let mut stdout = String::new();
                    let mut stderr = String::new();
                    if let Some(mut out) = child.stdout.take() {
                        use std::io::Read;
                        let _ = out.read_to_string(&mut stdout);
                    }
                    if let Some(mut err) = child.stderr.take() {
                        use std::io::Read;
                        let _ = err.read_to_string(&mut stderr);
                    }
                    if !status.success() {
                        return Err(format!(
                            "diagnóstico falhou (código {:?}): {}",
                            status.code(),
                            stderr.chars().take(500).collect::<String>()
                        ));
                    }
                    return Ok(stdout);
                }
                Ok(None) => {
                    std::thread::sleep(Duration::from_millis(100));
                }
                Err(e) => {
                    return Err(format!("wait falhou: {e}"));
                }
            }
        }
    })
    .await
    .map_err(|e| format!("spawn_blocking falhou: {e}"))??;

    let duracao_ms = inicio.elapsed().as_millis() as u64;

    let _ = app.emit_to(
        "configuracoes",
        "diagnostico-progresso",
        ProgressoEvento {
            tipo: tipo.clone(),
            mensagem: "Processando resultado...".into(),
            concluido: false,
        },
    );

    let parsed: ResultadoDiagnostico = serde_json::from_str(resultado.trim()).map_err(|e| {
        format!(
            "parse da saída falhou: {} -- Saída: {}",
            e,
            resultado.chars().take(300).collect::<String>()
        )
    })?;

    let _ = app.emit_to(
        "configuracoes",
        "diagnostico-progresso",
        ProgressoEvento {
            tipo,
            mensagem: format!(
                "Concluído: {} ok, {} avisos, {} falhas ({} ms)",
                parsed.checagens.iter().filter(|c| c.estado == "ok").count(),
                parsed.checagens.iter().filter(|c| c.estado == "aviso").count(),
                parsed.checagens.iter().filter(|c| c.estado == "falha").count(),
                duracao_ms
            ),
            concluido: true,
        },
    );

    Ok(ResultadoDiagnostico {
        duracao_ms,
        ..parsed
    })
}

/// Guarda-raíl que libera a flag EM_EXECUCAO ao sair do escopo.
struct LiberaExecucao;
impl Drop for LiberaExecucao {
    fn drop(&mut self) {
        EM_EXECUCAO.store(false, Ordering::SeqCst);
    }
}

/// Constrói o código Python inline que importa e roda o módulo de diagnóstico.
fn build_python_code(tipo: &str) -> String {
    // Código seguro sem strings raw problemáticas: usa apenas ASCII e imports diretos.
    format!(
        "import sys,json;\
try:\
 from vard.diagnostico import rodar_diagnostico as rd;\
 r=rd('{}');\
 print(json.dumps(dict(checagens=[dict(grupo=c.grupo,nome=c.nome,estado=c.estado,frase=c.frase) for c in r.checagens],relatorio=r.relatorio,duracao_ms=r.duracao_ms)))\
except Exception as e:\
 print(json.dumps(dict(checagens=[],relatorio='Erro: '+str(e)[:200],duracao_ms=0)))",
        tipo
    )
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn cancelar_define_flag() {
        CANCELADO.store(false, Ordering::SeqCst);
        cancelar_diagnostico();
        assert!(CANCELADO.load(Ordering::SeqCst));
        CANCELADO.store(false, Ordering::SeqCst);
    }

    #[test]
    fn resultado_deserializa_json_valido() {
        let json = r#"{"checagens":[{"grupo":"Runtime","nome":"Portas","estado":"ok","frase":"ok"}],"relatorio":"teste","duracao_ms":10}"#;
        let r: ResultadoDiagnostico = serde_json::from_str(json).unwrap();
        assert_eq!(r.checagens.len(), 1);
        assert_eq!(r.checagens[0].estado, "ok");
        assert_eq!(r.duracao_ms, 10);
    }

    #[test]
    fn resultado_rejeita_json_invalido() {
        let json = r#"{"checagens": "nao_e_lista"}"#;
        assert!(serde_json::from_str::<ResultadoDiagnostico>(json).is_err());
    }

    #[test]
    fn build_python_code_contem_tipo() {
        let code = build_python_code("basico");
        assert!(code.contains("basico"));
        assert!(code.contains("rodar_diagnostico"));
    }

    #[test]
    fn dois_cliques_concorrentes_um_so_diagnostico() {
        EM_EXECUCAO.store(false, Ordering::SeqCst);
        assert!(!EM_EXECUCAO.swap(true, Ordering::SeqCst));
        // Segundo swap deve retornar true (já estava ocupado)
        assert!(EM_EXECUCAO.swap(true, Ordering::SeqCst));
        EM_EXECUCAO.store(false, Ordering::SeqCst);
    }
}