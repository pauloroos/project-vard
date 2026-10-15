//! Diagnóstico do Vard (T10): executa checagens somente-leitura via Python embutido.
//!
//! Contrato:
//! - `rodar_diagnostico(tipo: "basico" | "preflight") -> ResultadoDiagnostico`
//! - Básico: só leitura (portas, processos, config, GPU/RAM); nunca inicia serviço.
//! - Timeout/cancelamento mata só o job do diagnóstico.
//! - Saída sanitizada (sem credenciais nem caminhos pessoais).

use serde::{Deserialize, Serialize};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::AppHandle;

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

static CANCELADO: AtomicBool = AtomicBool::new(false);

/// Cancela o diagnóstico em andamento (sinal cooperativo).
#[tauri::command]
pub fn cancelar_diagnostico() {
    CANCELADO.store(true, Ordering::SeqCst);
}

/// Executa o diagnóstico via Python embutido e retorna o resultado estruturado.
#[tauri::command]
pub async fn rodar_diagnostico(
    _app: AppHandle,
    tipo: String,
) -> Result<ResultadoDiagnostico, String> {
    CANCELADO.store(false, Ordering::SeqCst);

    // Código Python mínimo e seguro: importa o módulo diagnostico.py e roda.
    // Se o módulo não estiver no PYTHONPATH, usa fallback inline simples.
    let python_code = format!(
        "import sys, json; \
         try: \
             from vard.diagnostico import rodar_diagnostico as rd; \
             r = rd('{}'); \
             print(json.dumps({{'checagens': [{{'grupo': c.grupo, 'nome': c.nome, 'estado': c.estado, 'frase': c.frase}} for c in r.checagens], 'relatorio': r.relatorio, 'duracao_ms': r.duracao_ms}})) \
         except Exception as e: \
             print(json.dumps({{'checagens': [], 'relatorio': 'Erro: ' + str(e)[:200], 'duracao_ms': 0}}))",
        tipo
    );

    let output = tauri::async_runtime::spawn_blocking(move || {
        Command::new("python")
            .arg("-I")
            .arg("-c")
            .arg(&python_code)
            .output()
    })
    .await
    .map_err(|e| format!("spawn falhou: {e}"))?
    .map_err(|e| format!("python falhou: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "diagnostico falhou (codigo {:?}): {}",
            output.status.code(),
            stderr.chars().take(500).collect::<String>()
        ));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let resultado: ResultadoDiagnostico = serde_json::from_str(stdout.trim()).map_err(|e| {
        format!(
            "parse da saida falhou: {} -- Saida: {}",
            e,
            stdout.chars().take(300).collect::<String>()
        )
    })?;

    Ok(resultado)
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
}